"""Fast command boundary and durable task processor for interaction flows."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any
from uuid import uuid4

from app.models import (
    DivergenceSelection,
    GateAction,
    IntentRevision,
    IntentRevisionStatus,
    InteractionAggregateType,
    InteractionAuditEvent,
    InteractionCommandMeta,
    InteractionDomainEvent,
    InteractionProjection,
    InteractionTask,
    InteractionTaskStatus,
    InteractionTaskType,
    RevisionGateRequest,
    SemanticDivergenceParams,
    now_utc,
)
from app.services.interaction.domain import assert_intent_transition
from app.services.pipeline.four_stage_orchestrator import FourStageConflict, FourStageError, FourStageOrchestrator
from app.services.storage.four_stage_store import FourStageStore
from app.services.storage.websocket_manager import WebSocketManager


class InteractionOrchestrator:
    """Coordinates durable commands without putting model latency on clicks."""

    def __init__(
        self,
        store: FourStageStore,
        pipeline: FourStageOrchestrator,
        observation: Any,
        websocket_manager: WebSocketManager,
    ) -> None:
        self.store = store
        self.pipeline = pipeline
        self.observation = observation
        self.websocket_manager = websocket_manager
        self._workers: dict[str, asyncio.Task[None]] = {}
        self._worker_owner = f"api-{uuid4().hex[:8]}"

    def _meta(self, meta: InteractionCommandMeta | None) -> InteractionCommandMeta:
        return meta or InteractionCommandMeta(
            command_id=f"cmd_{uuid4().hex[:12]}",
            idempotency_key=f"idem_{uuid4().hex[:16]}",
        )

    def _event(
        self,
        *,
        event_type: str,
        revision: IntentRevision,
        aggregate_type: InteractionAggregateType,
        aggregate_id: str,
        payload: dict[str, Any],
        meta: InteractionCommandMeta,
    ) -> InteractionDomainEvent:
        return InteractionDomainEvent(
            event_id=f"evt_{uuid4().hex[:12]}",
            event_type=event_type,
            session_id=revision.session_id,
            revision_id=revision.revision_id,
            intent_seq=revision.intent_seq,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=revision.version,
            correlation_id=meta.command_id,
            causation_id=meta.command_id,
            payload=payload,
        )

    async def accept_gate(
        self,
        revision_id: str,
        request: RevisionGateRequest,
    ) -> tuple[IntentRevision, InteractionTask | None, list[InteractionDomainEvent]]:
        revision = self._require_revision(revision_id)
        meta = self._meta(
            InteractionCommandMeta(
                command_id=request.command_id or f"cmd_{uuid4().hex[:12]}",
                idempotency_key=request.idempotency_key or request.command_id or f"idem_{uuid4().hex[:16]}",
                expected_version=request.expected_version,
            )
            if request.command_id or request.idempotency_key
            else None
        )
        existing_audit = self.store.find_interaction_audit_by_idempotency(
            revision.session_id, meta.idempotency_key
        )
        if existing_audit is not None:
            return revision, self._task_for_revision(revision), []
        if meta.expected_version is not None and meta.expected_version != revision.version:
            raise FourStageConflict(
                f"expected revision version {meta.expected_version}, current {revision.version}"
            )
        if revision.status in {IntentRevisionStatus.accepted, IntentRevisionStatus.rejected}:
            if (revision.status == IntentRevisionStatus.accepted) == request.accepted:
                return revision, self._task_for_revision(revision), []
            raise FourStageConflict("revision Gate was already resolved")
        if revision.status != IntentRevisionStatus.awaiting_gate:
            raise FourStageConflict("revision Gate is not awaiting confirmation")

        target = IntentRevisionStatus.accepted if request.accepted else IntentRevisionStatus.rejected
        assert_intent_transition(revision.status, target)
        revision.status = target
        revision.version += 1
        task: InteractionTask | None = None
        event_type = "GateAccepted" if request.accepted else "GateRejected"
        events = [
            self._event(
                event_type=event_type,
                revision=revision,
                aggregate_type=InteractionAggregateType.intent_revision,
                aggregate_id=revision.revision_id,
                payload={
                    "accepted": request.accepted,
                    "gate_id": revision.gate_id,
                    "gate_question": revision.gate_question,
                },
                meta=meta,
            )
        ]
        if request.accepted:
            revision.semantic_divergence_status = "running"
            revision.semantic_divergence_error = None
            task_key = f"divergence:{revision.revision_id}:{revision.version}"
            existing_task = self.store.get_interaction_task(
                f"task_divergence_{revision.revision_id}"
            )
            if existing_task is None:
                task = InteractionTask(
                    task_id=f"task_divergence_{revision.revision_id}",
                    task_type=InteractionTaskType.semantic_divergence,
                    session_id=revision.session_id,
                    revision_id=revision.revision_id,
                    input_json={
                        "run_id": revision.run_id,
                        "decision_id": None,
                        "selected_option_id": request.selected_option_id,
                        "reason": request.reason,
                        "divergence_params": (
                            request.divergence_params.model_dump(mode="json")
                            if request.divergence_params
                            else SemanticDivergenceParams().model_dump(mode="json")
                        ),
                    },
                    idempotency_key=task_key,
                )
                events.append(
                    self._event(
                        event_type="DivergenceQueued",
                        revision=revision,
                        aggregate_type=InteractionAggregateType.generation_task,
                        aggregate_id=task.task_id,
                        payload={
                            "task_id": task.task_id,
                            "status": task.status.value,
                            "task": task.model_dump(mode="json"),
                        },
                        meta=meta,
                    )
                )
            else:
                # Prior accept already inserted this task (e.g. failed worker).
                # Re-queue so Gate accept can recover without UNIQUE collisions.
                if existing_task.status in {
                    InteractionTaskStatus.failed,
                    InteractionTaskStatus.cancelled,
                }:
                    existing_task.status = InteractionTaskStatus.queued
                    existing_task.error_code = None
                    existing_task.error_message = None
                    existing_task.completed_at = None
                    existing_task.progress = 0.0
                    existing_task.cancel_requested = False
                    existing_task.attempt = 0
                    self.store.update_interaction_task(existing_task)
                task = None
        audit = InteractionAuditEvent(
            audit_id=f"audit_{uuid4().hex[:12]}",
            command_id=meta.command_id,
            command_type="AcceptGate" if request.accepted else "RejectGate",
            idempotency_key=meta.idempotency_key,
            session_id=revision.session_id,
            revision_id=revision.revision_id,
            payload=request.model_dump(mode="json"),
            correlation_id=meta.command_id,
        )
        persisted_task, persisted_events = self.store.commit_interaction_command(
            revision=revision, audit=audit, events=events, task=task
        )
        await self._publish(persisted_events)
        schedule_id = (
            persisted_task.task_id
            if persisted_task is not None
            else (f"task_divergence_{revision.revision_id}" if request.accepted else None)
        )
        if schedule_id:
            self._schedule(schedule_id)
        return revision, persisted_task, persisted_events

    async def save_selection(
        self,
        revision_id: str,
        selection: DivergenceSelection,
        meta: InteractionCommandMeta | None = None,
    ) -> tuple[IntentRevision, list[InteractionDomainEvent]]:
        revision = self._require_revision(revision_id)
        meta = self._meta(meta)
        existing_audit = self.store.find_interaction_audit_by_idempotency(
            revision.session_id, meta.idempotency_key
        )
        if revision.status not in {
            IntentRevisionStatus.accepted,
            IntentRevisionStatus.generating,
            IntentRevisionStatus.completed,
        }:
            raise FourStageConflict("keywords require an accepted revision")
        if (
            selection.expected_selection_version is not None
            and selection.expected_selection_version != revision.selection_version
        ):
            raise FourStageConflict(
                "expected selection version "
                f"{selection.expected_selection_version}, current {revision.selection_version}"
            )
        if meta.expected_version is not None and meta.expected_version != revision.version:
            raise FourStageConflict(
                f"expected revision version {meta.expected_version}, current {revision.version}"
            )
        if existing_audit is not None:
            return revision, []

        prior = [
            item
            for item in self.store.list_revisions(revision.session_id)
            if item.intent_seq < revision.intent_seq
            and item.status
            in {
                IntentRevisionStatus.accepted,
                IntentRevisionStatus.generating,
                IntentRevisionStatus.completed,
            }
        ]
        base = list(prior[-1].effective_keywords) if prior else list(revision.base_keywords)
        delta = list(dict.fromkeys(selection.selected_keywords))
        revision.base_keywords = base
        revision.delta_keywords = delta
        revision.effective_keywords = list(dict.fromkeys([*base, *delta]))
        revision.divergence_selection = selection.model_copy(
            deep=True,
            update={
                "selected_keywords": revision.effective_keywords,
                "resolved_prompt_phrases": list(
                    dict.fromkeys(selection.resolved_prompt_phrases)
                ),
                "expected_selection_version": None,
                "expected_version": None,
            },
        )
        revision.selection_version += 1
        revision.version += 1
        event = self._event(
            event_type="SelectionSaved",
            revision=revision,
            aggregate_type=InteractionAggregateType.divergence_selection,
            aggregate_id=revision.revision_id,
            payload={
                "selection": revision.divergence_selection.model_dump(mode="json"),
                "selection_version": revision.selection_version,
            },
            meta=meta,
        )
        audit = InteractionAuditEvent(
            audit_id=f"audit_{uuid4().hex[:12]}",
            command_id=meta.command_id,
            command_type="UpdateDivergenceSelection",
            idempotency_key=meta.idempotency_key,
            session_id=revision.session_id,
            revision_id=revision.revision_id,
            payload=selection.model_dump(mode="json"),
            correlation_id=meta.command_id,
        )
        _, events = self.store.commit_interaction_command(
            revision=revision, audit=audit, events=[event]
        )
        await self._publish(events)
        return revision, events

    async def start_generation(
        self,
        revision_id: str,
        meta: InteractionCommandMeta | None = None,
    ) -> tuple[IntentRevision, InteractionTask, list[InteractionDomainEvent]]:
        revision = self._require_revision(revision_id)
        meta = self._meta(meta)
        # Braindead Generate: selected keywords are enough. Revive a prior
        # failed attempt so the user can click Generate again without Gate dance.
        if revision.status == IntentRevisionStatus.failed:
            revision.status = IntentRevisionStatus.accepted
            revision.error = None
            revision.version += 1
            self.store.save_revision(revision)
        if revision.status not in {
            IntentRevisionStatus.accepted,
            IntentRevisionStatus.generating,
        }:
            raise FourStageConflict("generation requires an accepted revision")
        if not revision.delta_keywords:
            raise FourStageConflict("generation requires an explicit selection for the current revision")
        self.observation.prepare_generation_retry(revision_id)
        revision = self._require_revision(revision_id)
        task_key = f"generation:{revision.revision_id}:{revision.selection_version}:{revision.version}"
        existing = self.store.find_interaction_task_by_idempotency(revision.session_id, task_key)
        if existing is not None:
            if existing.status in {
                InteractionTaskStatus.failed,
                InteractionTaskStatus.cancelled,
            }:
                retried = await self.retry_task(existing.task_id)
                return revision, retried, []
            return revision, existing, []
        task = InteractionTask(
            task_id=f"task_generation_{revision.revision_id}_{revision.selection_version}_{revision.version}",
            task_type=InteractionTaskType.solution_generation,
            session_id=revision.session_id,
            revision_id=revision.revision_id,
            input_json={"revision_id": revision.revision_id, "run_id": revision.run_id},
            idempotency_key=task_key,
        )
        revision.version += 1
        event = self._event(
            event_type="GenerationQueued",
            revision=revision,
            aggregate_type=InteractionAggregateType.generation_task,
            aggregate_id=task.task_id,
            payload={
                "task_id": task.task_id,
                "status": task.status.value,
                "task": task.model_dump(mode="json"),
            },
            meta=meta,
        )
        audit = InteractionAuditEvent(
            audit_id=f"audit_{uuid4().hex[:12]}",
            command_id=meta.command_id,
            command_type="StartGeneration",
            idempotency_key=meta.idempotency_key,
            session_id=revision.session_id,
            revision_id=revision.revision_id,
            payload={"selection_version": revision.selection_version},
            correlation_id=meta.command_id,
        )
        persisted_task, events = self.store.commit_interaction_command(
            revision=revision, audit=audit, events=[event], task=task
        )
        if persisted_task is None:
            raise FourStageError("generation task was not persisted")
        await self._publish(events)
        self._schedule(persisted_task.task_id)
        return revision, persisted_task, events

    def projection(self, session_id: str) -> InteractionProjection:
        revisions = [item.model_dump(mode="json") for item in self.store.list_revisions(session_id)]
        batches = [item.model_dump(mode="json") for item in self.store.list_solution_batches(session_id)]
        tasks = self.store.list_interaction_tasks(session_id)
        events = self.store.list_interaction_events(session_id, limit=1_000_000)
        return InteractionProjection(
            revisions=revisions,
            tasks=tasks,
            solution_batches=batches,
            last_event_cursor=events[-1].event_cursor if events else 0,
        )

    def events(self, session_id: str, after_cursor: int = 0) -> list[InteractionDomainEvent]:
        return self.store.list_interaction_events(session_id, after_cursor=after_cursor)

    async def retry_task(self, task_id: str) -> InteractionTask:
        task = self.store.get_interaction_task(task_id)
        if task is None:
            raise FourStageError("interaction task not found")
        if task.status not in {InteractionTaskStatus.failed, InteractionTaskStatus.cancelled}:
            return task
        task.status = InteractionTaskStatus.queued
        task.error_code = None
        task.error_message = None
        task.completed_at = None
        task.cancel_requested = False
        task.attempt = 0
        self.store.update_interaction_task(task)
        self._schedule(task.task_id)
        return task

    def cancel_task(self, task_id: str) -> InteractionTask:
        task = self.store.cancel_interaction_task(task_id)
        if task is None:
            raise FourStageError("interaction task not found")
        return task

    def _task_for_revision(self, revision: IntentRevision) -> InteractionTask | None:
        tasks = self.store.list_interaction_tasks(revision.session_id, revision.revision_id)
        return next(
            (
                item
                for item in reversed(tasks)
                if item.task_type == InteractionTaskType.semantic_divergence
            ),
            None,
        )

    def _require_revision(self, revision_id: str) -> IntentRevision:
        revision = self.store.get_revision(revision_id)
        if revision is None:
            raise FourStageError("intent revision not found")
        return revision

    def _schedule(self, task_id: str) -> None:
        current = self._workers.get(task_id)
        if current is not None and not current.done():
            return
        running = asyncio.create_task(self._run_task(task_id))
        self._workers[task_id] = running
        running.add_done_callback(lambda done: self._workers.pop(task_id, None))

    async def _run_task(self, task_id: str) -> None:
        task = self.store.claim_interaction_task(
            lease_owner=self._worker_owner,
            task_type=None,
            task_id=task_id,
        )
        if task is None or task.task_id != task_id:
            return
        heartbeat = asyncio.create_task(self._renew_lease_loop(task.task_id))
        try:
            if task.revision_id:
                revision = self.store.get_revision(task.revision_id)
                if revision is not None:
                    await self._publish(
                        [
                            self._event(
                                event_type=(
                                    "DivergenceStarted"
                                    if task.task_type == InteractionTaskType.semantic_divergence
                                    else "GenerationStarted"
                                ),
                                revision=revision,
                                aggregate_type=InteractionAggregateType.generation_task,
                                aggregate_id=task.task_id,
                                payload={
                                    "task_id": task.task_id,
                                    "status": task.status.value,
                                    "task": task.model_dump(mode="json"),
                                },
                                meta=InteractionCommandMeta(
                                    command_id=f"worker_{task.task_id}",
                                    idempotency_key=f"worker-start:{task.task_id}:{task.attempt}",
                                ),
                            )
                        ]
                    )
            if task.task_type == InteractionTaskType.semantic_divergence:
                await self._run_divergence(task)
            elif task.task_type == InteractionTaskType.solution_generation:
                await self._run_generation(task)
            elif task.task_type == InteractionTaskType.intent_planning:
                if task.revision_id:
                    await self.observation.plan_revision(task.revision_id)
            if task.cancel_requested:
                raise FourStageConflict("task cancellation requested")
            task.status = InteractionTaskStatus.succeeded
            task.progress = 1.0
            task.completed_at = now_utc()
            task.lease_owner = None
            task.lease_expires_at = None
            self.store.update_interaction_task(task, lease_owner=self._worker_owner)
            if task.task_type == InteractionTaskType.solution_generation and task.revision_id:
                revision = self.store.get_revision(task.revision_id)
                if revision is not None:
                    await self._publish(
                        [
                            self._event(
                                event_type="GenerationCompleted",
                                revision=revision,
                                aggregate_type=InteractionAggregateType.generation_task,
                                aggregate_id=task.task_id,
                                payload={
                                    "task_id": task.task_id,
                                    "task": task.model_dump(mode="json"),
                                    "result_ref": task.result_ref,
                                },
                                meta=InteractionCommandMeta(
                                    command_id=f"worker_{task.task_id}",
                                    idempotency_key=f"worker-success:{task.task_id}:{task.attempt}",
                                ),
                            )
                        ]
                    )
        except asyncio.CancelledError:
            task.status = InteractionTaskStatus.cancelled
            task.completed_at = now_utc()
            self.store.update_interaction_task(task, lease_owner=self._worker_owner)
            raise
        except FourStageConflict as exc:
            if task.cancel_requested:
                task.status = InteractionTaskStatus.cancelled
                task.error_code = "cancelled"
                task.error_message = str(exc)[:500]
                task.completed_at = now_utc()
                task.lease_owner = None
                task.lease_expires_at = None
                self.store.update_interaction_task(task, lease_owner=self._worker_owner)
                return
            task.status = InteractionTaskStatus.failed
            task.error_code = "task_conflict"
            task.error_message = str(exc)[:500]
            task.completed_at = now_utc()
            task.lease_owner = None
            task.lease_expires_at = None
            self.store.update_interaction_task(task, lease_owner=self._worker_owner)
            await self._publish_task_failure(task)
        except Exception as exc:
            task.status = InteractionTaskStatus.failed
            task.error_code = "task_failed"
            task.error_message = str(exc)[:500]
            task.completed_at = now_utc()
            task.lease_owner = None
            task.lease_expires_at = None
            self.store.update_interaction_task(task, lease_owner=self._worker_owner)
            if task.revision_id:
                revision = self.store.get_revision(task.revision_id)
                if revision is not None:
                    revision.semantic_divergence_status = (
                        "failed" if task.task_type == InteractionTaskType.semantic_divergence else revision.semantic_divergence_status
                    )
                    revision.semantic_divergence_error = task.error_message
                    revision.version += 1
                    self.store.save_revision(revision)
                    await self._publish_task_failure(task, revision=revision)
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat

    async def _renew_lease_loop(self, task_id: str) -> None:
        try:
            while True:
                await asyncio.sleep(20)
                if not self.store.renew_interaction_task(
                    task_id,
                    lease_owner=self._worker_owner,
                    lease_seconds=60,
                ):
                    return
        except asyncio.CancelledError:
            return

    async def _run_divergence(self, task: InteractionTask) -> None:
        if task.cancel_requested:
            raise FourStageConflict("task cancellation requested")
        if not task.revision_id:
            raise FourStageError("divergence task has no revision")
        revision = self._require_revision(task.revision_id)
        # Fast Gate accept can outrun plan_revision; wait for the cloud LLM.
        run = None
        for _ in range(300):
            revision = self._require_revision(task.revision_id)
            run = self.store.get_run(revision.run_id or "") if revision.run_id else None
            if run is not None and run.decision is not None:
                break
            if task.cancel_requested:
                raise FourStageConflict("task cancellation requested")
            await asyncio.sleep(0.2)
        if run is None or run.decision is None:
            revision = await self.observation.plan_revision(task.revision_id)
            run = self.store.get_run(revision.run_id or "") if revision.run_id else None
        if run is None or run.decision is None:
            raise FourStageError("revision planner result is not ready")
        raw_params = dict(task.input_json.get("divergence_params") or {})
        # Keep request_key aligned with the browser SSE payload (do not clobber
        # inherited_keywords with a stale/empty revision.base_keywords).
        inherited = list(
            raw_params.get("inherited_keywords")
            or revision.base_keywords
            or []
        )
        params = SemanticDivergenceParams.model_validate(
            {**raw_params, "inherited_keywords": inherited, "preflight": False}
        )
        selected = task.input_json.get("selected_option_id")
        # Accept Gate only — let the browser SSE own the progress stream.
        await self.pipeline.resolve_gate(
            run.run_id,
            run.decision.decision_id,
            GateAction.accept_option,
            selected_option_id=selected,
            reason=task.input_json.get("reason"),
            auto_generate=False,
            divergence_params=params,
            run_divergence=False,
        )
        service = self.pipeline.semantic_divergence_service
        if service is None:
            raise FourStageError("semantic divergence service is not configured")
        # Prefer joining an in-flight SSE task (has progress subscribers).
        key = service.request_key(
            self.store.get_run(run.run_id) or run,
            params,
        )
        for _ in range(50):
            current = self.store.get_run(run.run_id)
            if (
                current is not None
                and current.semantic_divergence is not None
                and current.semantic_divergence.status == "completed"
                and current.semantic_divergence.candidates
            ):
                updated = current
                break
            if key in getattr(service, "_inflight", {}):
                updated_response = await self.pipeline.refresh_semantic_divergence(
                    run.run_id, params
                )
                updated = self.store.get_run(run.run_id) or run
                updated.semantic_divergence = updated_response
                break
            await asyncio.sleep(0.1)
        else:
            updated_response = await self.pipeline.refresh_semantic_divergence(
                run.run_id, params
            )
            updated = self.store.get_run(run.run_id) or run
            updated.semantic_divergence = updated_response
        revision = self._require_revision(task.revision_id)
        if revision.status == IntentRevisionStatus.awaiting_gate:
            revision.status = IntentRevisionStatus.accepted
        revision.semantic_divergence_status = "completed"
        revision.semantic_divergence_error = None
        revision.base_keywords = inherited
        revision.gate_target = updated.scope_gate.target if updated.scope_gate else revision.gate_target
        revision.gate_scope = updated.scope_gate.scope if updated.scope_gate else revision.gate_scope
        revision.version += 1
        self.store.save_revision(revision)
        await self._publish(
            [
                self._event(
                    event_type="DivergenceCompleted",
                    revision=revision,
                    aggregate_type=InteractionAggregateType.generation_task,
                    aggregate_id=task.task_id,
                    payload={
                        "task_id": task.task_id,
                        "candidate_count": len(
                            updated.semantic_divergence.candidates
                            if updated.semantic_divergence
                            else []
                        ),
                        "task": task.model_copy(
                            update={
                                "status": InteractionTaskStatus.succeeded,
                                "progress": 1.0,
                                "completed_at": now_utc(),
                            }
                        ).model_dump(mode="json"),
                    },
                    meta=InteractionCommandMeta(
                        command_id=f"worker_{task.task_id}",
                        idempotency_key=f"worker-success:{task.task_id}:{task.attempt}",
                    ),
                )
            ]
        )

    async def _run_generation(self, task: InteractionTask) -> None:
        if task.cancel_requested:
            raise FourStageConflict("task cancellation requested")
        if not task.revision_id:
            raise FourStageError("generation task has no revision")
        batch = await self.observation.start_generation(task.revision_id, drive=False)
        task.result_ref = batch.batch_id
        task.progress = 0.25
        revision = self._require_revision(task.revision_id)
        if not revision.run_id:
            raise FourStageError("generation task has no run")
        # Queues a background GPU job and returns immediately — wait for it.
        started = await self.pipeline.start_generation(revision.run_id)
        job_id = str((started or {}).get("job_id") or "")
        deadline = asyncio.get_event_loop().time() + 1800.0
        while True:
            if task.cancel_requested:
                if job_id and self.pipeline.generation_service is not None:
                    await self.pipeline.generation_service.cancel_job(job_id)
                raise FourStageConflict("task cancellation requested")
            run = self.store.get_run(revision.run_id)
            if run is None:
                raise FourStageError("generation run disappeared")
            job = self.store.get_generation_job(job_id) if job_id else None
            job_status = (job or {}).get("status")
            artifacts = list(run.generation_artifacts or [])
            if job_status == "completed" or (
                run.stage.value == "completed" and artifacts
            ):
                break
            if job_status in {"failed", "cancelled"} or run.stage.value in {
                "failed",
                "cancelled",
            }:
                message = (
                    ((job or {}).get("error") or {}).get("message")
                    or (run.error or {}).get("message")
                    or f"generation {job_status or run.stage.value}"
                )
                batch.status = "failed"
                revision.status = IntentRevisionStatus.failed
                revision.error = message
                self.store.save_solution_batch(batch)
                self.store.save_revision(revision)
                raise FourStageError(message)
            if asyncio.get_event_loop().time() > deadline:
                raise FourStageError("generation timed out waiting for images")
            task.progress = min(0.9, 0.25 + 0.08 * len(artifacts))
            self.store.update_interaction_task(task, lease_owner=self._worker_owner)
            await asyncio.sleep(2.0)

        run = self.store.get_run(revision.run_id)
        if run is None:
            raise FourStageError("generation run disappeared")
        artifacts = list(run.generation_artifacts or [])
        batch = next(
            (
                item
                for item in self.store.list_solution_batches(task.session_id)
                if item.batch_id == task.result_ref
            ),
            batch,
        )
        batch.artifacts = artifacts
        if not artifacts:
            batch.status = "failed"
            revision.status = IntentRevisionStatus.failed
            revision.error = "generation produced no images"
            self.store.save_solution_batch(batch)
            self.store.save_revision(revision)
            raise FourStageError("generation produced no images")
        batch.status = "completed"
        revision.status = IntentRevisionStatus.completed
        revision.error = None
        self.store.save_solution_batch(batch)
        self.store.save_revision(revision)
        task.progress = 1.0

    async def _publish_task_failure(
        self,
        task: InteractionTask,
        *,
        revision: IntentRevision | None = None,
    ) -> None:
        if revision is None and task.revision_id:
            revision = self.store.get_revision(task.revision_id)
        if revision is None:
            return
        await self._publish(
            [
                self._event(
                    event_type=(
                        "DivergenceFailed"
                        if task.task_type == InteractionTaskType.semantic_divergence
                        else "GenerationFailed"
                    ),
                    revision=revision,
                    aggregate_type=InteractionAggregateType.generation_task,
                    aggregate_id=task.task_id,
                    payload={
                        "task_id": task.task_id,
                        "error": task.error_message,
                        "task": task.model_dump(mode="json"),
                    },
                    meta=InteractionCommandMeta(
                        command_id=f"worker_{task.task_id}",
                        idempotency_key=f"worker-failure:{task.task_id}:{task.attempt}",
                    ),
                )
            ]
        )

    async def _publish(self, events: list[InteractionDomainEvent]) -> None:
        pending = [event for event in events if event.event_cursor == 0]
        if pending:
            self.store.append_interaction_events(pending)
        # Dispatch from the durable outbox rather than only from the current
        # request. If a websocket send or process crashes after the database
        # commit, the next command retries the unpublished row in cursor order;
        # client event-id dedupe makes the send safely at-least-once.
        for event in self.store.list_pending_interaction_outbox():
            await self.websocket_manager.broadcast_message(
                event.session_id,
                {
                    "type": "interaction.event",
                    "event_id": event.event_id,
                    "session_id": event.session_id,
                    "timestamp": event.occurred_at.isoformat(),
                    "payload": event.payload,
                    "event_cursor": event.event_cursor,
                    "event_type": event.event_type,
                    "revision_id": event.revision_id,
                    "aggregate_type": event.aggregate_type.value,
                    "aggregate_id": event.aggregate_id,
                    "aggregate_version": event.aggregate_version,
                    "correlation_id": event.correlation_id,
                },
            )
            self.store.mark_interaction_outbox_published(event.event_id)


__all__ = ["InteractionOrchestrator"]
