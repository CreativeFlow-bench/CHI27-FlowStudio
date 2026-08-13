"""Trusted orchestration for post-Gate semantic divergence."""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable
import hashlib
import json
from time import perf_counter
from typing import Any

from app.models import (
    FourStageRun,
    KnowledgeEvidence,
    KnowledgeRoute,
    SemanticCandidate,
    SemanticDivergenceParams,
    SemanticDivergenceRequest,
    SemanticDivergenceResponse,
)
from app.models.semantic_divergence import SemanticTarget
from app.services.divergence.knowledge_adapters import vernacular_en_label
from app.services.divergence.semantic_model_clients import (
    SemanticModelOutputError,
    SemanticModelUnavailable,
)
from app.services.encoding.four_stage_encoding import infer_text_part


class SemanticDivergenceStateConflict(RuntimeError):
    """The accepted Gate changed while semantic divergence was in flight."""


# Async progress callback signature: receives a phase event dict.
SemanticDivergenceProgress = Callable[[dict[str, Any]], Awaitable[None]]


class SemanticDivergenceService:
    """Build trusted context and run the primary/fallback candidate pipeline."""

    def __init__(
        self,
        *,
        store: Any,
        knowledge_router: Any,
        gemini: Any,
        local_vlm: Any,
        validator: Any,
        call_timeout_sec: float = 25.0,
    ) -> None:
        self.store = store
        self.knowledge_router = knowledge_router
        self.gemini = gemini
        self.local_vlm = local_vlm
        self.validator = validator
        self.call_timeout_sec = max(5.0, float(call_timeout_sec))
        self._inflight: dict[str, asyncio.Task[SemanticDivergenceResponse]] = {}
        # Late SSE joiners (Accept worker often starts diverge first) still receive
        # subsequent phase events via this fan-out registry.
        self._progress_subscribers: dict[str, list[SemanticDivergenceProgress]] = {}

    def _subscribe_progress(
        self, request_key: str, callback: SemanticDivergenceProgress
    ) -> None:
        self._progress_subscribers.setdefault(request_key, []).append(callback)

    def _unsubscribe_progress(
        self, request_key: str, callback: SemanticDivergenceProgress
    ) -> None:
        subscribers = self._progress_subscribers.get(request_key)
        if not subscribers:
            return
        try:
            subscribers.remove(callback)
        except ValueError:
            return
        if not subscribers:
            self._progress_subscribers.pop(request_key, None)

    async def _emit_progress(self, request_key: str, event: dict[str, Any]) -> None:
        """Fan-out progress to every live SSE subscriber for this request key."""
        payload = dict(event)
        payload.setdefault("request_key", request_key)
        for callback in list(self._progress_subscribers.get(request_key, ())):
            try:
                await callback(payload)
            except Exception:
                pass

    @staticmethod
    def request_key(run: FourStageRun, params: SemanticDivergenceParams) -> str:
        if run.decision is None:
            raise ValueError("semantic divergence requires a DecisionIR")
        material = {
            "run_id": run.run_id,
            "decision_id": run.decision.decision_id,
            "temperature": params.temperature,
            "strictness": params.strictness,
            "per_group_count": params.per_group_count,
            "candidate_count": params.candidate_count,
            "inherited_keywords": sorted(set(params.inherited_keywords)),
        }
        return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()

    async def diverge(
        self,
        run: FourStageRun,
        params: SemanticDivergenceParams,
    ) -> SemanticDivergenceResponse:
        key = self.request_key(run, params)
        persisted = self._persisted_response(run, key)
        if persisted is not None:
            return persisted

        task = self._inflight.get(key)
        if task is None:
            task = asyncio.create_task(self._diverge_once(run, params, key))
            self._inflight[key] = task
            task.add_done_callback(
                lambda completed, request_key=key: self._cleanup_inflight(
                    request_key, completed
                )
            )
        response = await asyncio.shield(task)
        run.semantic_divergence = response
        return response

    async def diverge_with_progress(
        self,
        run: FourStageRun,
        params: SemanticDivergenceParams,
        on_progress: SemanticDivergenceProgress | None = None,
    ) -> SemanticDivergenceResponse:
        """Run ``diverge`` while emitting incremental stage progress.

        Subscribers can join an already-running ``diverge()`` task and still
        receive subsequent phase events (Accept worker vs SSE race).
        """
        key = self.request_key(run, params)
        if on_progress is not None:
            self._subscribe_progress(key, on_progress)
        try:
            persisted = self._persisted_response(run, key)
            if persisted is not None:
                await self._emit_progress(
                    key,
                    {
                        "phase": "short_circuit",
                        "status": persisted.status,
                        "candidates": [
                            c.model_dump(mode="json") for c in persisted.candidates
                        ],
                        "validation_counts": dict(persisted.validation_counts),
                    },
                )
                return persisted

            task = self._inflight.get(key)
            if task is None:
                task = asyncio.create_task(self._diverge_once(run, params, key))
                self._inflight[key] = task
                task.add_done_callback(
                    lambda completed, request_key=key: self._cleanup_inflight(
                        request_key, completed
                    )
                )
            else:
                await self._emit_progress(
                    key,
                    {
                        "phase": "primary_call",
                        "message": "Joined in-flight divergence…",
                    },
                )
            response = await asyncio.shield(task)
            run.semantic_divergence = response
            return response
        finally:
            if on_progress is not None:
                self._unsubscribe_progress(key, on_progress)

    def _cleanup_inflight(
        self, request_key: str, task: asyncio.Task[SemanticDivergenceResponse]
    ) -> None:
        if self._inflight.get(request_key) is task:
            self._inflight.pop(request_key, None)

    async def _diverge_once(
        self,
        run: FourStageRun,
        params: SemanticDivergenceParams,
        key: str,
    ) -> SemanticDivergenceResponse:
        persisted = self._persisted_response(run, key)
        if persisted is not None:
            return persisted
        started = perf_counter()

        await self._emit_progress(
            key,
            {
                "phase": "evidence",
                "message": "Collecting knowledge evidence",
            },
        )

        request = self._build_request(run, params)
        try:
            route = self.knowledge_router.choose_route(request)
            evidence = await self._collect_evidence(request, route)
        except Exception as exc:
            await self._emit_progress(
                key,
                {
                    "phase": "evidence",
                    "status": "failed",
                    "message": f"evidence failed: {exc}",
                },
            )
            raise
        counts: Counter[str] = Counter()
        primary_candidates: list[SemanticCandidate] = []
        primary_accepted: list[SemanticCandidate] = []
        fallback_used = False
        fallback_reason: str | None = None
        primary_model = str(getattr(self.gemini, "model", "primary"))
        generator_model = primary_model
        primary_report = None

        await self._emit_progress(
            key,
            {
                "phase": "primary_call",
                "message": f"Calling primary model {primary_model}",
                "generator_model": primary_model,
            },
        )

        try:
            primary_candidates = await self._call_model(
                self.gemini, "gemini", request, evidence
            )
            primary_model = str(
                getattr(self.gemini, "last_used_model", None) or primary_model
            )
            generator_model = primary_model
            counts["primary_generated"] = len(primary_candidates)
            primary_report = self.validator.validate(request, primary_candidates)
            counts["primary_accepted"] = len(primary_report.accepted)
            counts.update(primary_report.rejection_counts)
            primary_accepted = list(primary_report.accepted)
            needs_fallback = primary_report.needs_fallback
            await self._emit_progress(
                key,
                {
                    "phase": "primary_returned",
                    "provider": "gemini",
                    "generator_model": primary_model,
                    "generated": len(primary_candidates),
                    "accepted": len(primary_accepted),
                    "rejection_counts": dict(counts),
                    "needs_fallback": needs_fallback,
                    "preview_labels": [
                        candidate.display_label_zh or candidate.label_en
                        for candidate in primary_accepted[:16]
                    ],
                    "candidates": [
                        candidate.model_dump(mode="json") for candidate in primary_accepted
                    ],
                },
            )
        except Exception as exc:
            needs_fallback = True
            fallback_reason = self._primary_failure_reason(exc)
            await self._emit_progress(
                key,
                {
                    "phase": "primary_failed",
                    "provider": "gemini",
                    "generator_model": primary_model,
                    "reason": fallback_reason,
                    "message": f"Primary {primary_model} failed; will try fallback",
                },
            )

        # Agile: keep a usable primary set instead of waiting on a slow spare model.
        if needs_fallback and len(primary_accepted) >= 8:
            needs_fallback = False
            counts["agile_skip_fallback"] = 1

        if needs_fallback:
            fallback_used = True
            fallback_reason = fallback_reason or "insufficient_valid_candidates"
            fallback_model = str(getattr(self.local_vlm, "model", "fallback"))
            generator_model = fallback_model
            await self._emit_progress(
                key,
                {
                    "phase": "fallback_call",
                    "message": f"Calling fallback model {fallback_model}",
                    "generator_model": fallback_model,
                },
            )
            try:
                fallback_candidates = await self._call_model(
                    self.local_vlm, "local_vlm", request, evidence
                )
                fallback_model = str(
                    getattr(self.local_vlm, "last_used_model", None) or fallback_model
                )
                generator_model = fallback_model
                counts["fallback_generated"] = len(fallback_candidates)
                fallback_report = self.validator.validate(request, fallback_candidates)
                counts["fallback_accepted"] = len(fallback_report.accepted)
                counts.update(fallback_report.rejection_counts)
                await self._emit_progress(
                    key,
                    {
                        "phase": "fallback_returned",
                        "provider": "local_vlm",
                        "generator_model": fallback_model,
                        "generated": len(fallback_candidates),
                        "accepted": len(fallback_report.accepted),
                        "rejection_counts": dict(counts),
                        "preview_labels": [
                            candidate.display_label_zh or candidate.label_en
                            for candidate in fallback_report.accepted[:16]
                        ],
                        "candidates": [
                            candidate.model_dump(mode="json")
                            for candidate in fallback_report.accepted
                        ],
                    },
                )
            except Exception as exc:
                await self._emit_progress(
                    key,
                    {
                        "phase": "fallback_failed",
                        "provider": "local_vlm",
                        "generator_model": generator_model,
                        "message": f"fallback failed: {exc}",
                    },
                )
                if primary_accepted:
                    accepted = primary_accepted
                    generator_model = primary_model
                    counts["final_accepted"] = len(accepted)
                    counts["agile_partial_after_fallback_fail"] = 1
                    await self._emit_progress(
                        key,
                        {
                            "phase": "completed",
                            "accepted": len(accepted),
                            "validation_counts": dict(counts),
                            "fallback_used": True,
                            "message": (
                                f"Using {len(accepted)} primary candidates "
                                "after fallback failure"
                            ),
                            "preview_labels": [
                                candidate.display_label_zh or candidate.label_en
                                for candidate in accepted[:16]
                            ],
                            "candidates": [
                                candidate.model_dump(mode="json") for candidate in accepted
                            ],
                        },
                    )
                    return self._persist(
                        run,
                        self._response(
                            run,
                            key,
                            generator_model,
                            evidence.route,
                            counts,
                            started,
                            status="completed",
                            fallback_used=True,
                            fallback_reason=fallback_reason,
                            candidates=accepted,
                        ),
                    )
                return self._persist(
                    run,
                    self._response(
                        run,
                        key,
                        generator_model,
                        evidence.route,
                        counts,
                        started,
                        status="failed",
                        fallback_used=True,
                        fallback_reason=fallback_reason,
                        candidates=[],
                    ),
                )

            merged = [
                *(primary_report.accepted if primary_report is not None else []),
                *fallback_report.accepted,
            ]
            try:
                final_report = self.validator.validate(request, merged)
            except Exception:
                accepted = [
                    *(primary_accepted or []),
                    *list(fallback_report.accepted),
                ]
                counts["final_accepted"] = len(accepted)
                counts["agile_partial_after_merge_fail"] = 1
                await self._emit_progress(
                    key,
                    {
                        "phase": "completed",
                        "accepted": len(accepted),
                        "validation_counts": dict(counts),
                        "fallback_used": True,
                        "message": f"Selected {len(accepted)} partial candidates",
                        "preview_labels": [
                            candidate.display_label_zh or candidate.label_en
                            for candidate in accepted[:16]
                        ],
                        "candidates": [
                            candidate.model_dump(mode="json") for candidate in accepted
                        ],
                    },
                )
                return self._persist(
                    run,
                    self._response(
                        run,
                        key,
                        generator_model,
                        evidence.route,
                        counts,
                        started,
                        status="completed",
                        fallback_used=True,
                        fallback_reason=fallback_reason,
                        candidates=accepted,
                    ),
                )
            counts.update(final_report.rejection_counts)
            counts["final_accepted"] = len(final_report.accepted)
            if final_report.needs_fallback:
                accepted = list(final_report.accepted) or primary_accepted or list(
                    fallback_report.accepted
                )
                if not accepted:
                    await self._emit_progress(
                        key,
                        {
                            "phase": "final_failed",
                            "message": "merged candidates still need fallback",
                        },
                    )
                    return self._persist(
                        run,
                        self._response(
                            run,
                            key,
                            generator_model,
                            evidence.route,
                            counts,
                            started,
                            status="failed",
                            fallback_used=True,
                            fallback_reason=fallback_reason,
                            candidates=[],
                        ),
                    )
                counts["final_accepted"] = len(accepted)
                counts["agile_partial_soft_gate"] = 1
            else:
                accepted = final_report.accepted
        else:
            accepted = (
                primary_report.accepted if primary_report is not None else primary_accepted
            )
            counts["final_accepted"] = len(accepted)

        await self._emit_progress(
            key,
            {
                "phase": "completed",
                "accepted": len(accepted),
                "validation_counts": dict(counts),
                "fallback_used": fallback_used,
                "message": f"Selected {len(accepted)} candidates",
                "preview_labels": [
                    candidate.display_label_zh or candidate.label_en for candidate in accepted[:16]
                ],
                "candidates": [candidate.model_dump(mode="json") for candidate in accepted],
            },
        )

        return self._persist(
            run,
            self._response(
                run,
                key,
                generator_model,
                evidence.route,
                counts,
                started,
                status="completed",
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
                candidates=accepted,
            ),
        )

    def _persisted_response(
        self, run: FourStageRun, request_key: str
    ) -> SemanticDivergenceResponse | None:
        response = run.semantic_divergence
        if (
            response is not None
            and response.status == "completed"
            and response.request_key == request_key
        ):
            return response
        get_run = getattr(self.store, "get_run", None)
        if not callable(get_run):
            return None
        stored = get_run(run.run_id)
        response = stored.semantic_divergence if stored is not None else None
        if (
            response is None
            or response.status != "completed"
            or response.request_key != request_key
        ):
            return None
        run.semantic_divergence = response
        return response

    def _build_request(
        self, run: FourStageRun, params: SemanticDivergenceParams
    ) -> SemanticDivergenceRequest:
        if run.source_context is None or run.intent_ir is None or run.decision is None:
            raise ValueError("semantic divergence requires source context, IntentIR, and DecisionIR")
        preflight = bool(getattr(params, "preflight", False))
        if run.scope_gate is None:
            raise ValueError("semantic divergence requires a scope Gate")
        if not preflight and run.scope_gate.status != "accepted":
            raise ValueError("semantic divergence requires an accepted scope Gate")

        source = run.source_context
        intent_ir = run.intent_ir
        scope = run.scope_gate.scope or intent_ir.intent.scope
        gate_label = str(
            getattr(run.scope_gate, "target", None) or run.decision.semantic_target or ""
        ).strip()
        text_goal = intent_ir.intent.goal or intent_ir.observations.text or ""
        text_part = infer_text_part(text_goal)
        part_id = text_part or intent_ir.target.part_id or source.target_part_id or gate_label or None
        label_zh = gate_label or text_part or part_id or source.object_type
        label_en = vernacular_en_label(str(label_zh))
        selected_constraints: list[str] = []
        selected_option_id = (
            run.gate_decision.selected_option_id if run.gate_decision is not None else None
        )
        for option in run.decision.options:
            if option.option_id == selected_option_id:
                selected_constraints = option.constraints
                break
        constraints = list(
            dict.fromkeys([*intent_ir.intent.constraints, *selected_constraints])
        )
        event_ids = run.source_event_ids or intent_ir.source_event_ids
        return SemanticDivergenceRequest(
            run_id=run.run_id,
            decision_id=run.decision.decision_id,
            session_id=run.session_id,
            asset_id=source.asset_id,
            object_identity=source.object_type,
            semantic_target=SemanticTarget(
                level=scope,
                part_id=part_id,
                label_zh=str(label_zh) if label_zh else None,
                label_en=label_en or None,
                mask_ref=source.target_mask_ref,
                semantic_role=intent_ir.intent.operation,
            ),
            scope=scope,
            user_semantic_intent=text_goal,
            behavior_summary=self._behavior_summary(run, event_ids),
            behavior_window_id=self._behavior_window_id(run.run_id, event_ids),
            hard_constraints=constraints,
            params=params,
        )

    async def _collect_evidence(
        self, request: SemanticDivergenceRequest, route: KnowledgeRoute
    ) -> KnowledgeEvidence:
        try:
            return await asyncio.to_thread(self.knowledge_router.collect, request, route)
        except Exception as exc:  # optional knowledge must never choose model fallback
            degraded_route = route.model_copy(deep=True)
            degraded_route.mode = "model_only"
            if "knowledge_collection_failed" not in degraded_route.reasons:
                degraded_route.reasons.append("knowledge_collection_failed")
            partial_sources = [
                source
                for source, enabled in (
                    ("wikidata", route.use_wikidata),
                    ("getty_aat", route.use_getty_aat),
                    ("asknature", route.use_asknature),
                )
                if enabled
            ]
            if not partial_sources:
                partial_sources = ["knowledge"]
            for source in partial_sources:
                degraded_route.source_statuses[source] = "partial"
            return KnowledgeEvidence(
                route=degraded_route,
                partial_sources=partial_sources,
                errors=[f"knowledge_collection: {type(exc).__name__}"],
            )

    async def _call_model(
        self,
        generator: Any,
        provider: str,
        request: SemanticDivergenceRequest,
        evidence: KnowledgeEvidence,
    ) -> list[Any]:
        started = perf_counter()
        error_type: str | None = None
        timeout = float(
            getattr(generator, "call_timeout_sec", None) or self.call_timeout_sec
        )
        try:
            return await asyncio.wait_for(
                generator.generate(request, evidence),
                timeout=timeout + 2.0,
            )
        except asyncio.TimeoutError as exc:
            error_type = "TimeoutError"
            raise SemanticModelUnavailable(
                f"{getattr(generator, 'model', provider)} timed out after {timeout:.0f}s"
            ) from exc
        except Exception as exc:
            error_type = type(exc).__name__
            raise
        finally:
            self._audit_model(
                provider=provider,
                model=str(
                    getattr(generator, "last_used_model", None)
                    or getattr(generator, "model", provider)
                ),
                run_id=request.run_id,
                latency_ms=max(0, round((perf_counter() - started) * 1000)),
                error_type=error_type,
            )

    def _audit_model(self, **audit: Any) -> None:
        try:
            self.store.record_model_call(**audit)
        except Exception:
            pass  # audit failure must not turn a valid generation into a model failure

    def _persist(
        self, run: FourStageRun, response: SemanticDivergenceResponse
    ) -> SemanticDivergenceResponse:
        preflight = False
        # Infer preflight from pending Gate so accept-time cache hits still work.
        if run.scope_gate is not None and run.scope_gate.status != "accepted":
            preflight = True
        conditional_update = getattr(
            self.store, "update_semantic_divergence_if_current", None
        )
        if callable(conditional_update):
            updated = conditional_update(
                run.run_id,
                expected_decision_id=response.decision_id,
                response=response,
                require_accepted=not preflight,
            )
            if not updated:
                raise SemanticDivergenceStateConflict(
                    "run decision or accepted Gate changed during semantic divergence"
                )
        else:
            # Lightweight test stores retain the earlier persistence contract;
            # production FourStageStore uses the conditional field update.
            persisted = run.model_copy(update={"semantic_divergence": response})
            self.store.save_run(persisted)
        run.semantic_divergence = response
        return response

    @staticmethod
    def _response(
        run: FourStageRun,
        request_key: str,
        generator_model: str,
        route: KnowledgeRoute,
        counts: Counter[str],
        started: float,
        *,
        status: str,
        fallback_used: bool,
        fallback_reason: str | None,
        candidates: list[Any],
    ) -> SemanticDivergenceResponse:
        assert run.decision is not None
        return SemanticDivergenceResponse(
            divergence_id=f"semantic_{request_key[:24]}",
            run_id=run.run_id,
            decision_id=run.decision.decision_id,
            request_key=request_key,
            status=status,
            generator_model=generator_model,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            knowledge_route=route,
            validation_counts=dict(counts),
            latency_ms=max(0, round((perf_counter() - started) * 1000)),
            candidates=candidates,
        )

    @staticmethod
    def _primary_failure_reason(exc: Exception) -> str:
        if isinstance(exc, SemanticModelUnavailable):
            return "primary_model_unavailable"
        if isinstance(exc, SemanticModelOutputError):
            return "primary_invalid_output"
        return "primary_technical_failure"

    @staticmethod
    def _behavior_window_id(run_id: str, event_ids: list[str]) -> str:
        material = json.dumps([run_id, *event_ids], ensure_ascii=False)
        return f"window_{hashlib.sha256(material.encode()).hexdigest()[:16]}"

    @classmethod
    def _behavior_summary(cls, run: FourStageRun, event_ids: list[str]) -> str:
        locked = set(event_ids)
        events = [
            {
                "event_id": event.event_id,
                "type": event.type,
                "payload": cls._safe_value(event.payload),
            }
            for event in run.events
            if event.event_id in locked
        ]
        return json.dumps(events, ensure_ascii=False, sort_keys=True)[:4000]

    @classmethod
    def _safe_value(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): cls._safe_value(item)
                for key, item in value.items()
                if not any(
                    token in str(key).casefold()
                    for token in ("image", "data_url", "base64")
                )
            }
        if isinstance(value, list):
            return [cls._safe_value(item) for item in value[:16]]
        if isinstance(value, str):
            if value.startswith("data:"):
                return "[redacted-data-url]"
            return value[:500]
        return value


__all__ = ["SemanticDivergenceService", "SemanticDivergenceStateConflict"]
