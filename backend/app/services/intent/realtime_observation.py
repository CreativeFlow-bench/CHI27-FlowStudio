"""Always-on observation, immutable Send cutoffs, and multi-intent revisions."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models import (
    BehaviorCommitRequest,
    BehaviorPatchRequest,
    BehaviorSession,
    BehaviorStartRequest,
    BehaviorStatus,
    DivergenceSelection,
    FourStageRun,
    FourStageRunCreateRequest,
    FourStageStage,
    GateAction,
    IntentRevision,
    IntentRevisionCreateRequest,
    IntentRevisionStatus,
    InteractionTaskStatus,
    LiveObservationState,
    RealtimeObservationSnapshot,
    RevisionGateRequest,
    SemanticDivergenceParams,
    SolutionBatch,
    UiBrief,
    UserEvent,
    VersionGraphNode,
    VersionGraphNodeCreateRequest,
    VersionGraphNodeUpdateRequest,
    VersionGraphState,
    VersionNodeStatus,
    now_utc,
)
from app.services.encoding.four_stage_encoding import (
    RuleIntentEncoder,
    infer_text_part,
    infer_text_parts,
)
from app.services.model_api.text_gateway import TextModelGateway
from app.services.model_api.transport import ModelTransportUnavailable
from app.services.model_api.types import ModelStage
from app.services.pipeline.four_stage_orchestrator import (
    FourStageConflict,
    FourStageError,
    FourStageOrchestrator,
)
from app.services.rerepresentation import RuleDecisionService
from app.services.storage.experiment_project_store import ExperimentProjectStore
from app.services.storage.four_stage_store import FourStageStore

logger = logging.getLogger(__name__)

_PHASE_BY_TOOL = {
    "hover": "focus",
    "select": "focus",
    "brush": "shape_connect",
    "clay": "shape_connect",
    "drag": "shape_connect",
    "move": "shape_connect",
    "add": "shape_connect",
    "smooth": "surface_reference",
    "annotation": "surface_reference",
    "image": "surface_reference",
    "model": "surface_reference",
    "save": "commit",
    "version": "commit",
    "generate": "diverge",
    "compare": "compare",
}

_WHOLE_SCOPE_MARKERS = {
    "silhouette", "contour", "outline", "overall", "whole", "profile",
    "轮廓", "外形", "整体", "外轮廓",
}
_SURFACE_SCOPE_MARKERS = {
    "surface", "material", "texture", "color", "colour", "gloss", "roughness",
    "stone statue", "stone sculpture", "wooden", "wood grain", "metal", "marble",
    "表面", "材质", "纹理", "颜色", "光泽", "粗糙度",
    "石像", "石雕", "木质", "木头", "木纹", "金属", "大理石",
}
_IDENTITY_TRANSFORM_MARKERS = {
    "become", "make this", "turn this into", "turn into",
    "变成", "做成", "改成",
}
_BLENDER_GENERIC_MESH = re.compile(
    r"^(?:cube|mball|sphere|plane|cylinder|torus|cone|mesh|nurbs|suzanne|ico_sphere)(?:\.\d+)?$",
    re.I,
)
_GENERIC_TARGET_MARKERS = {
    "", "object", "unknown", "item", "thing", "model", "asset", "current object",
    "当前对象", "当前部件",
}
_PRESERVATION_MARKERS = {
    "保持", "保留", "维持", "不改变", "不要改变", "不改", "不动", "不变",
    "preserve", "retain", "keep", "unchanged", "without changing", "do not change",
    "don't change",
}

_GATE_QUESTION_SYSTEM = """你是 FlowStudio 的 Gate 证据路由器。只输出一个 JSON 对象，不要 Markdown。
字段必须且只能是：
{"scope":"part|material|whole","target_label":"..."}

输入会分成三条证据通道，按优先级使用：
1) location：用户画笔/雕刻标出的位置或部件。有 location 时，target_label 优先用它。
2) semantic：用户真正输入的文字意图。用它判断 scope（part/material/whole）和语义目标。
3) 若 location 与 semantic 都为空：根据 object_type / behaviors 自行判断。

规则：
1. scope=part：改局部形状/连接/部件；scope=material：改表面/材质/颜色；scope=whole：改整体轮廓。
2. target_label 必须是给人看的短称呼（如 帽子、鼻子、雪人），禁止 obj_group_*/cube_* / unknown / object。
3. 不要输出 question 字段；系统会按固定模板生成问句。
4. semantic 若明确说整体轮廓/外形，即使有 location 也可用 whole。
5. semantic 若点名部件，优先该部件；否则用 location；再否则用物体类型。
6. semantic 若是整体身份转化（become / wooden / 变成木质），target 用物体类型，不要用 hover 网格名。
"""


def _fixed_gate_question(scope: str, target: str, semantic: str = "") -> str:
    text = (semantic or "").lower()
    if (
        scope != "part"
        and _has_requested_scope_marker(text, _IDENTITY_TRANSFORM_MARKERS)
        and _has_requested_scope_marker(text, _SURFACE_SCOPE_MARKERS)
    ):
        return f"你想改变这个 {target} 的材质和轮廓吗？"
    if scope == "material":
        return f"你想改变这个 {target} 的表面或材质吗？"
    if scope == "whole":
        return f"你想改变这个 {target} 的整体轮廓吗？"
    return f"你想改变这个 {target} 的形状或连接吗？"


def _is_generic_mesh_id(value: str) -> bool:
    lower = str(value or "").strip().lower()
    return (
        not lower
        or lower in _GENERIC_TARGET_MARKERS
        or lower.startswith("obj_group")
        or lower.startswith("cube_")
        or lower.startswith("mesh_")
        or bool(_BLENDER_GENERIC_MESH.match(lower))
    )


def _is_invented_drawing_semantic(text: str) -> bool:
    """Frontend used to invent user_text from drawing; ignore those as semantics."""
    value = str(text or "").strip()
    if not value:
        return True
    needles = (
        "请根据刚才",
        "请根据画面",
        "2d 笔刷",
        "2d笔刷",
        "freehand_contour",
        "理解意图并调整造型",
    )
    lower = value.lower()
    return any(item in lower for item in needles)


_LOCATION_TOOLS = {
    "annotation",
    "brush",
    "clay",
    "drag",
    "move",
    "smooth",
}


def _behavior_location(behaviors: list[BehaviorSession]) -> dict[str, str] | None:
    """Latest drawing/sculpt target is the spatial evidence channel."""
    for item in reversed(behaviors):
        if item.tool not in _LOCATION_TOOLS:
            continue
        part_id = str(item.target.get("part_id") or "").strip()
        label = str(item.target.get("label") or "").strip()
        if _is_generic_mesh_id(part_id) and _is_generic_mesh_id(label):
            # Drawing without a resolved part still counts as location evidence;
            # caller may fill from source_context selection.
            return {"tool": item.tool, "part_id": "", "label": ""}
        return {
            "tool": item.tool,
            "part_id": "" if _is_generic_mesh_id(part_id) else part_id,
            "label": "" if _is_generic_mesh_id(label) else (label or part_id),
        }
    return None


def _annotation_shape(behaviors: list[BehaviorSession]) -> str:
    for item in reversed(behaviors):
        if item.tool != "annotation":
            continue
        summary = item.operation_summary if isinstance(item.operation_summary, dict) else {}
        shape = str(summary.get("inferred_shape") or summary.get("annotation_shape") or "").strip()
        if shape:
            return shape
    return ""


def _has_requested_scope_marker(text: str, markers: set[str]) -> bool:
    """Return true only when a scope word describes the requested edit.

    Gate scope compression must not turn preservation language such as
    “保持整体身份” or “不改变轮廓” into the edit target.
    """

    lowered = text.lower()
    clause_separators = {",", "，", ".", "。", ";", "；", "!", "！", "?", "？"}
    for marker in markers:
        start = 0
        while True:
            index = lowered.find(marker, start)
            if index < 0:
                break
            before = lowered[max(0, index - 24):index]
            after = lowered[index + len(marker): index + len(marker) + 24]
            preserved_before = any(
                (position := before.rfind(preserve)) >= 0
                and not any(char in clause_separators for char in before[position + len(preserve):])
                for preserve in _PRESERVATION_MARKERS
            )
            preserved_after = False
            for preserve in _PRESERVATION_MARKERS:
                position = after.find(preserve)
                if position < 0:
                    continue
                between = after[:position]
                if not any(char in clause_separators for char in between):
                    preserved_after = True
                    break
            if not preserved_before and not preserved_after:
                return True
            start = index + len(marker)
    return False


class RealtimeObservationService:
    """Session layer above FourStageRun.

    A FourStageRun belongs to exactly one immutable IntentRevision. Observation
    continues independently and never opens a Gate by itself.
    """

    def __init__(
        self,
        store: FourStageStore,
        orchestrator: FourStageOrchestrator,
        recorder: ExperimentProjectStore | None = None,
        text_gateway: TextModelGateway | None = None,
        files_root: Path | None = None,
    ) -> None:
        self.store = store
        self.orchestrator = orchestrator
        self.recorder = recorder
        self.text_gateway = text_gateway
        self.gate_llm_enabled = text_gateway is not None
        self.files_root = files_root
        self._locks: dict[str, asyncio.Lock] = {}
        self._refine_locks: dict[str, asyncio.Lock] = {}
        self._generation_locks: dict[str, asyncio.Lock] = {}
        self._generation_tasks: dict[str, asyncio.Task[None]] = {}

    def _lock(self, session_id: str) -> asyncio.Lock:
        return self._locks.setdefault(session_id, asyncio.Lock())

    def _refine_lock(self, session_id: str) -> asyncio.Lock:
        return self._refine_locks.setdefault(session_id, asyncio.Lock())

    def _generation_lock(self, session_id: str) -> asyncio.Lock:
        return self._generation_locks.setdefault(session_id, asyncio.Lock())

    async def commit_behavior(
        self,
        session_id: str,
        request: BehaviorCommitRequest,
    ) -> BehaviorSession:
        async with self._lock(session_id):
            reserved = self.store.get_behavior(request.behavior_id) if request.behavior_id else None
            if reserved and reserved.session_id != session_id:
                raise FourStageConflict("behavior belongs to another session")
            if reserved and reserved.status == BehaviorStatus.committed:
                return reserved
            started_at = request.started_at or (reserved.started_at if reserved else now_utc())
            if self.store.is_stale_history(session_id, started_at):
                raise FourStageConflict("history cleared")
            behavior = BehaviorSession(
                behavior_id=reserved.behavior_id if reserved else request.behavior_id or f"behavior_{uuid4().hex[:10]}",
                session_id=session_id,
                behavior_seq=reserved.behavior_seq if reserved else self.store.next_behavior_seq(session_id),
                tool=request.tool,
                target=request.target,
                status=BehaviorStatus.committed,
                started_at=started_at,
                ended_at=request.ended_at or now_utc(),
                stroke_count=request.stroke_count,
                operation_summary=request.operation_summary,
                start_views=request.start_views,
                end_views=request.end_views,
                evidence_refs=request.evidence_refs,
            )
            self.store.save_behavior(behavior)
            state = self._rule_observation(session_id, behavior)
            state.updated_at = now_utc()
            self.store.save_live_observation(state)
        await self._emit(
            session_id,
            "observation.behavior_committed",
            {"behavior": behavior.model_dump(mode="json")},
        )
        return behavior

    async def start_behavior(
        self,
        session_id: str,
        request: BehaviorStartRequest,
    ) -> BehaviorSession:
        async with self._lock(session_id):
            existing = self.store.get_behavior(request.behavior_id) if request.behavior_id else None
            if existing:
                if existing.session_id != session_id:
                    raise FourStageConflict("behavior belongs to another session")
                return existing
            started_at = request.started_at or now_utc()
            if self.store.is_stale_history(session_id, started_at):
                raise FourStageConflict("history cleared")
            behavior = BehaviorSession(
                behavior_id=request.behavior_id or f"behavior_{uuid4().hex[:10]}",
                session_id=session_id,
                behavior_seq=self.store.next_behavior_seq(session_id),
                tool=request.tool,
                target=request.target,
                status=BehaviorStatus.active,
                started_at=started_at,
            )
            self.store.save_behavior(behavior)
        return behavior

    async def cancel_behavior(self, session_id: str, behavior_id: str) -> None:
        async with self._lock(session_id):
            behavior = self.store.get_behavior(behavior_id)
            if behavior and behavior.session_id == session_id:
                self._purge_behavior_artifacts(behavior)
                self.store.delete_behavior(behavior_id)

    async def patch_behavior(
        self,
        session_id: str,
        behavior_id: str,
        request: BehaviorPatchRequest,
    ) -> BehaviorSession:
        async with self._lock(session_id):
            behavior = self.store.get_behavior(behavior_id)
            if behavior is None:
                raise FourStageError("behavior not found")
            if behavior.session_id != session_id:
                raise FourStageConflict("behavior belongs to another session")
            if request.operation_summary:
                behavior.operation_summary = {
                    **behavior.operation_summary,
                    **request.operation_summary,
                }
            if request.evidence_refs is not None:
                merged = list(behavior.evidence_refs)
                for ref in request.evidence_refs:
                    if ref and ref not in merged:
                        merged.append(ref)
                behavior.evidence_refs = merged
            if request.stroke_count is not None:
                behavior.stroke_count = request.stroke_count
            return self.store.save_behavior(behavior)

    def _purge_behavior_artifacts(self, behavior: BehaviorSession) -> None:
        """Best-effort delete uploaded screenshots / annotation files for a behavior."""
        if self.files_root is None:
            return
        root = self.files_root.resolve()
        artifact_ids: set[str] = set()
        summary = behavior.operation_summary or {}
        for key in (
            "viewport_screenshot_artifact_id",
            "annotation_artifact_id",
        ):
            value = summary.get(key)
            if isinstance(value, str) and value.strip():
                artifact_ids.add(value.strip())
        urls: list[str] = []
        for key in (
            "viewport_screenshot_url",
            "stroke_url",
        ):
            value = summary.get(key)
            if isinstance(value, str) and value.strip():
                urls.append(value.strip())
        for view_set in (behavior.start_views, behavior.end_views):
            for value in (view_set.front, view_set.side, view_set.top):
                if value:
                    urls.append(value)
        for ref in behavior.evidence_refs:
            if ref:
                urls.append(ref)
        for url in urls:
            if "/files/screenshots/" in url:
                artifact_ids.add(url.split("/files/screenshots/")[1].split("/")[0])
            elif "/files/annotations/" in url:
                artifact_ids.add(url.split("/files/annotations/")[1].split("/")[0])
        for artifact_id in artifact_ids:
            for folder in ("screenshots", "annotations"):
                path = (root / folder / artifact_id).resolve()
                if root in path.parents and path.exists():
                    shutil.rmtree(path, ignore_errors=True)

    async def refine_observation(self, session_id: str) -> LiveObservationState:
        """Incrementally encode + retrieve committed Behaviors without opening a Gate."""
        async with self._refine_lock(session_id):
            baseline = self.store.get_live_observation(session_id) or LiveObservationState(
                session_id=session_id
            )
            behaviors = [
                item
                for item in self.store.list_behaviors(
                    session_id,
                    start_seq=baseline.encoded_through_seq + 1,
                )
                if item.status == BehaviorStatus.committed
            ]
            if not behaviors:
                return baseline
            delta_end_seq = behaviors[-1].behavior_seq
            run = FourStageRun(
                run_id=f"live_{session_id}_{delta_end_seq}",
                session_id=session_id,
                events=self._behavior_events(behaviors),
                source_event_ids=[item.behavior_id for item in behaviors],
            )
            try:
                intent_ir = await self.orchestrator.encoding_service.encode(run)
            except Exception:
                # Deterministic rule state remains current. A later Behavior
                # retries this still-unencoded delta without blocking input.
                return self.store.get_live_observation(session_id) or baseline

            state = self.store.get_live_observation(session_id) or baseline
            state.encoded_through_seq = max(state.encoded_through_seq, delta_end_seq)
            state.intent_summary = intent_ir.intent.goal or state.intent_summary
            state.operation = intent_ir.intent.operation or state.operation
            state.scope = intent_ir.intent.scope or state.scope
            encoded_target = intent_ir.target.model_dump(mode="json", exclude_none=True)
            if encoded_target:
                state.target = encoded_target
            state.intent_confidence = max(state.intent_confidence, intent_ir.confidence)
            fingerprint_payload = {
                "scope": state.scope,
                "operation": state.operation,
                "target": state.target,
            }
            fingerprint = hashlib.sha256(
                json.dumps(fingerprint_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
            if fingerprint != state.retrieval_fingerprint:
                try:
                    retrieval = await self.orchestrator.retrieval_service.retrieve(run, intent_ir)
                    state.retrieval_query = [
                        item.case_id or item.prior_ir_id for item in retrieval.matches[:5]
                    ]
                    state.retrieval_fingerprint = fingerprint
                except Exception:
                    # Encoding progress is still committed; retrieval refresh
                    # retries when the semantic fingerprint changes again.
                    pass
            state.updated_at = now_utc()
            self.store.save_live_observation(state)
            await self._emit(
                session_id,
                "observation.updated",
                {"observation": state.model_dump(mode="json")},
            )
            return state

    async def create_revision(
        self,
        session_id: str,
        request: IntentRevisionCreateRequest,
    ) -> IntentRevision:
        """Atomically lock all Behaviors committed before this Send."""
        async with self._lock(session_id):
            revisions = self.store.list_revisions(session_id)
            latest_seq = self.store.next_behavior_seq(session_id) - 1
            cutoff_seq = (
                min(request.cutoff_seq, latest_seq)
                if request.cutoff_seq is not None
                else latest_seq
            )
            window_start_seq = revisions[-1].cutoff_seq + 1 if revisions else 1
            behaviors = self.store.list_behaviors(
                session_id, start_seq=window_start_seq, end_seq=cutoff_seq
            )
            behaviors = [item for item in behaviors if item.status == BehaviorStatus.committed]
            revision = IntentRevision(
                revision_id=f"intent_{uuid4().hex[:10]}",
                session_id=session_id,
                intent_seq=self.store.next_intent_seq(session_id),
                parent_revision_id=revisions[-1].revision_id if revisions else None,
                window_start_seq=window_start_seq,
                cutoff_seq=cutoff_seq,
                behavior_ids=[item.behavior_id for item in behaviors],
                user_text=request.user_text.strip(),
                source_context=request.source_context,
            )
            self._apply_fast_gate_draft(
                revision, behaviors, live_signals=request.live_signals
            )
            self.store.save_revision(revision)
            # Fast Gate: surface provisional question immediately. LLM polish and
            # full planner encoding continue in background (plan_revision).
            revision.status = IntentRevisionStatus.awaiting_gate
            revision.gate_provisional = True
            self.store.save_revision(revision)
        await self._emit(
            session_id,
            "intent.revision_locked",
            {"revision": revision.model_dump(mode="json")},
        )
        return revision

    def _apply_fast_gate_draft(
        self,
        revision: IntentRevision,
        behaviors: list[BehaviorSession],
        live_signals: dict[str, Any] | None = None,
    ) -> None:
        """Fill a provisional Gate from text/behavior evidence before encoding."""
        signals = dict(live_signals or revision.live_signals or {})
        if signals:
            revision.live_signals = signals
        raw_part = str(revision.source_context.target_part_id or "").strip()
        named_part = raw_part if raw_part and not _is_generic_mesh_id(raw_part) else None
        gate_target, gate_scope, gate_question = self._compress_revision_gate(
            revision,
            behaviors,
            planner_target=named_part,
            planner_scope="part" if named_part else None,
            live_signals=signals,
        )
        revision.gate_target = gate_target
        revision.gate_scope = gate_scope
        revision.gate_question = gate_question
        revision.gate_provisional = True
        revision.gate_id = revision.gate_id or f"fgate_{revision.revision_id[-8:]}"
        if gate_scope == "whole":
            revision.source_context.target_part_id = None
        elif gate_scope == "part" and gate_target and not _is_generic_mesh_id(gate_target):
            revision.source_context.target_part_id = gate_target

    async def plan_revision(self, revision_id: str, *, run_hy3d: bool = False) -> IntentRevision:
        revision = self._require_revision(revision_id)
        behaviors = self.store.list_behaviors(
            revision.session_id,
            start_seq=revision.window_start_seq,
            end_seq=revision.cutoff_seq,
        )
        behaviors = [item for item in behaviors if item.status == BehaviorStatus.committed]
        events = self._behavior_events(behaviors)
        if revision.user_text:
            events.append(
                UserEvent(
                    type="text_committed",
                    event_id=f"text_{revision.revision_id}",
                    session_id=revision.session_id,
                    payload={"text": revision.user_text},
                )
            )
        try:
            async with asyncio.timeout(90):
                planner = self._planner_for_revision(revision, behaviors)
                run = await planner.create_run(
                    FourStageRunCreateRequest(
                        session_id=revision.session_id,
                        idempotency_key=f"revision:{revision.revision_id}",
                        episode_id=revision.revision_id,
                        run_hy3d=run_hy3d,
                        events=events,
                        source_context=revision.source_context,
                    ),
                    auto_advance=False,
                )
                revision.run_id = run.run_id
                self.store.save_revision(revision)
                await self._emit(
                    revision.session_id,
                    "intent.revision_updated",
                    {"revision": revision.model_dump(mode="json")},
                )
                run = await planner.advance_run(run.run_id)
                if run.scope_gate is None:
                    raise FourStageError("planner did not produce a scope Gate")
                gate_target, gate_scope, gate_question = await self._compose_revision_gate(
                    revision,
                    behaviors,
                    run.scope_gate.target,
                    run.scope_gate.scope,
                )
                run.scope_gate.target = gate_target
                run.scope_gate.scope = gate_scope
                run.scope_gate.question = gate_question
                self._sync_gate_contract(revision, behaviors, run, gate_target, gate_scope)
                if run.decision is not None:
                    run.decision.gate_question = gate_question
                self.store.save_run(run)
                revision.gate_id = run.scope_gate.gate_id
                revision.gate_question = gate_question
                revision.gate_target = gate_target
                revision.gate_scope = gate_scope
                revision.gate_provisional = False
                revision.status = IntentRevisionStatus.awaiting_gate
            planner = self._planner_for_revision(revision, behaviors)
            run = self.store.get_run(revision.run_id or "") if revision.run_id else None
            if (
                run is not None
                and hasattr(planner, "encoding_service")
                and hasattr(planner.encoding_service, "generate_phenomenon")
            ):
                try:
                    phenomenon = await planner.encoding_service.generate_phenomenon(
                        run, run.intent_ir
                    )
                    if phenomenon:
                        run.phenomenon = phenomenon
                        revision.phenomenon = phenomenon
                        self.store.save_run(run)
                except Exception:
                    pass
        except TimeoutError:
            logger.info("plan_revision timed out after 90s · keep Fast Gate for %s", revision_id)
            if not revision.gate_question:
                self._apply_fast_gate_draft(
                    revision, behaviors, live_signals=revision.live_signals
                )
            revision.status = IntentRevisionStatus.awaiting_gate
            revision.gate_provisional = True
            revision.error = "planner timed out; using fast gate"
        except Exception as exc:
            # Keep the Fast-Gate provisional question visible; only fail when we
            # never had anything to show.
            if revision.gate_question:
                revision.error = str(exc)[:500]
                revision.status = IntentRevisionStatus.awaiting_gate
                revision.gate_provisional = True
            else:
                revision.status = IntentRevisionStatus.failed
                revision.error = str(exc)[:500]
                revision.gate_provisional = False
        # Fast Gate accept may race ahead while planner runs — never demote a
        # terminal/accepted revision back to awaiting_gate.
        revision = self._merge_plan_revision_result(revision)
        self.store.save_revision(revision)
        await self._emit(
            revision.session_id,
            "intent.revision_updated",
            {"revision": revision.model_dump(mode="json")},
        )
        if (
            revision.status == IntentRevisionStatus.accepted
            and revision.semantic_divergence_status == "failed"
            and revision.run_id
        ):
            await self._retry_failed_divergence(revision)
        return revision

    def _merge_plan_revision_result(self, planned: IntentRevision) -> IntentRevision:
        latest = self._require_revision(planned.revision_id)
        locked = latest.status in {
            IntentRevisionStatus.accepted,
            IntentRevisionStatus.rejected,
            IntentRevisionStatus.generating,
            IntentRevisionStatus.completed,
        }
        if planned.run_id:
            latest.run_id = planned.run_id
        if planned.gate_id:
            latest.gate_id = planned.gate_id
        if planned.gate_question:
            latest.gate_question = planned.gate_question
        if planned.gate_target:
            latest.gate_target = planned.gate_target
        if planned.gate_scope:
            latest.gate_scope = planned.gate_scope
        if planned.phenomenon:
            latest.phenomenon = planned.phenomenon
        if planned.error and not locked:
            latest.error = planned.error
        if locked:
            if planned.gate_provisional is False:
                latest.gate_provisional = False
            return latest
        latest.status = planned.status
        latest.gate_provisional = planned.gate_provisional
        return latest

    async def _retry_failed_divergence(self, revision: IntentRevision) -> None:
        task = self.store.get_interaction_task(f"task_divergence_{revision.revision_id}")
        if task is None or task.status != InteractionTaskStatus.failed:
            return
        from app.services.interaction.orchestrator import InteractionOrchestrator

        # Prefer the live interaction worker if the app wired one; otherwise
        # re-queue for the next claim cycle.
        orchestrator = getattr(self, "interaction_orchestrator", None)
        if isinstance(orchestrator, InteractionOrchestrator):
            await orchestrator.retry_task(task.task_id)
            return
        task.status = InteractionTaskStatus.queued
        task.error_code = None
        task.error_message = None
        task.completed_at = None
        task.cancel_requested = False
        task.attempt = 0
        self.store.update_interaction_task(task)

    def _planner_for_revision(
        self,
        revision: IntentRevision,
        behaviors: list[BehaviorSession],
    ) -> FourStageOrchestrator:
        """Use the deterministic pipeline when the requested Gate is explicit.

        The resulting run is stored in the same database and remains fully
        compatible with the canonical orchestrator for Gate resolution,
        divergence selection, and generation. A separate orchestrator avoids
        mutating shared model services while concurrent intents are planning.
        """

        if not self._has_explicit_gate_scope(revision, behaviors):
            return self.orchestrator
        return FourStageOrchestrator(
            self.store,
            encoding_service=RuleIntentEncoder(),
            retrieval_service=self.orchestrator.retrieval_service,
            decision_service=RuleDecisionService(),
            generation_service=self.orchestrator.generation_service,
            websocket_manager=self.orchestrator.websocket_manager,
        )

    @staticmethod
    def _has_explicit_gate_scope(
        revision: IntentRevision,
        behaviors: list[BehaviorSession],
    ) -> bool:
        text = revision.user_text.strip()
        if text and not _is_invented_drawing_semantic(text):
            if infer_text_part(text):
                return True
            lower = text.lower()
            if _has_requested_scope_marker(lower, _SURFACE_SCOPE_MARKERS):
                return True
            if _has_requested_scope_marker(lower, _IDENTITY_TRANSFORM_MARKERS):
                return True
            if _has_requested_scope_marker(lower, _WHOLE_SCOPE_MARKERS):
                return True
        return any(
            item.target.get("part_id")
            and item.tool in {"brush", "clay", "drag", "move", "smooth", "annotation"}
            for item in behaviors
        )

    async def resolve_gate(
        self,
        revision_id: str,
        request: RevisionGateRequest,
    ) -> IntentRevision:
        revision = self._require_revision(revision_id)
        if revision.status in {IntentRevisionStatus.accepted, IntentRevisionStatus.rejected}:
            already_accepted = revision.status == IntentRevisionStatus.accepted
            if already_accepted == request.accepted:
                return revision
            raise FourStageConflict("revision Gate was already resolved")
        if revision.status != IntentRevisionStatus.awaiting_gate:
            raise FourStageConflict("revision Gate is not awaiting confirmation")
        run = self._require_revision_run(revision)
        if run.decision is None:
            raise FourStageError("revision decision is not ready")
        if request.accepted:
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
            inherited_keywords = list(prior[-1].effective_keywords) if prior else []
            divergence_params = (
                request.divergence_params or SemanticDivergenceParams()
            ).model_copy(update={"inherited_keywords": inherited_keywords})
            revision.base_keywords = inherited_keywords
            revision.effective_keywords = inherited_keywords
            if prior and prior[-1].divergence_selection is not None:
                inherited_phrases = list(
                    prior[-1].divergence_selection.resolved_prompt_phrases
                )
                revision.divergence_selection = DivergenceSelection(
                    selected_keywords=inherited_keywords,
                    resolved_prompt_phrases=inherited_phrases,
                )
            revision.semantic_divergence_status = "running"
            revision.semantic_divergence_error = None
            self.store.save_revision(revision)
            try:
                gate_is_already_accepted = (
                    run.gate_decision is not None
                    and run.gate_decision.action == GateAction.accept_option
                    and run.gate_decision.decision_id == run.decision.decision_id
                    and run.scope_gate is not None
                    and run.scope_gate.status == "accepted"
                )
                if gate_is_already_accepted:
                    await self.orchestrator.refresh_semantic_divergence(
                        run.run_id,
                        divergence_params,
                    )
                    updated = self._require_revision_run(revision)
                else:
                    updated = await self.orchestrator.resolve_gate(
                        run.run_id,
                        run.decision.decision_id,
                        GateAction.accept_option,
                        selected_option_id=request.selected_option_id,
                        reason=request.reason,
                        auto_generate=False,
                        divergence_params=divergence_params,
                    )
            except Exception as exc:
                revision.semantic_divergence_status = "failed"
                revision.semantic_divergence_error = str(exc)
                self.store.save_revision(revision)
                raise
            revision.status = IntentRevisionStatus.accepted
            revision.semantic_divergence_status = "completed"
            revision.semantic_divergence_error = None
            if updated.scope_gate:
                revision.gate_target = updated.scope_gate.target
                revision.gate_scope = updated.scope_gate.scope
        else:
            await self.orchestrator.resolve_gate(
                run.run_id,
                run.decision.decision_id,
                GateAction.reject_all,
                reason=request.reason,
                auto_generate=False,
            )
            revision.status = IntentRevisionStatus.rejected
            revision.base_keywords = []
            revision.effective_keywords = []
        self.store.save_revision(revision)
        await self._emit(
            revision.session_id,
            "intent.revision_updated",
            {"revision": revision.model_dump(mode="json")},
        )
        return revision

    async def save_selection(
        self,
        revision_id: str,
        selection: DivergenceSelection,
    ) -> IntentRevision:
        revision = self._require_revision(revision_id)
        if revision.status not in {
            IntentRevisionStatus.accepted,
            IntentRevisionStatus.generating,
            IntentRevisionStatus.completed,
        }:
            raise FourStageConflict("keywords require an accepted revision")
        prior = [
            item
            for item in self.store.list_revisions(revision.session_id)
            if item.intent_seq < revision.intent_seq
            and item.status in {
                IntentRevisionStatus.accepted,
                IntentRevisionStatus.generating,
                IntentRevisionStatus.completed,
            }
        ]
        excluded = set(selection.excluded_inherited_keywords or [])
        prior_effective = list(prior[-1].effective_keywords) if prior else []
        base = [keyword for keyword in prior_effective if keyword not in excluded]
        base_phrases = (
            list(prior[-1].divergence_selection.resolved_prompt_phrases)
            if prior and prior[-1].divergence_selection is not None
            else []
        )
        run = self._require_revision_run(revision)
        updated_run = await self.orchestrator.save_divergence_selection(
            run.run_id,
            selection,
        )
        canonical = updated_run.divergence_selection
        if canonical is None:
            raise FourStageError("semantic divergence selection was not persisted")
        delta = list(canonical.selected_keywords)
        delta_phrases = list(canonical.resolved_prompt_phrases)
        effective = list(dict.fromkeys([*base, *delta]))
        effective_phrases = list(dict.fromkeys([*base_phrases, *delta_phrases]))
        selection = canonical.model_copy(
            deep=True,
            update={
                "selected_keywords": effective,
                "resolved_prompt_phrases": effective_phrases,
            },
        )
        revision.base_keywords = base
        revision.delta_keywords = delta
        revision.effective_keywords = effective
        revision.divergence_selection = selection.model_copy(deep=True)
        run = self._require_revision_run(revision)
        run.divergence_selection = selection.model_copy(deep=True)
        self._sync_gate_contract(
            revision,
            [],
            run,
            revision.gate_target or run.scope_gate.target,
            revision.gate_scope or run.scope_gate.scope,
        )
        self.store.save_run(run)
        self.store.save_revision(revision)
        return revision

    def attach_source_image(self, revision_id: str, source_image_ref: str) -> IntentRevision:
        """Attach/refresh the viewport identity image used by Generate."""
        revision = self._require_revision(revision_id)
        image_ref = str(source_image_ref or "").strip()
        if not image_ref:
            raise FourStageError("source_image_ref is required")
        revision.source_context = revision.source_context.model_copy(
            update={"source_image_ref": image_ref}
        )
        run = self.store.get_run(revision.run_id) if revision.run_id else None
        if run is not None and run.source_context is not None:
            run.source_context = run.source_context.model_copy(
                update={"source_image_ref": image_ref}
            )
            self.store.save_run(run)
        self.store.save_revision(revision)
        return revision

    def prepare_generation_retry(self, revision_id: str) -> IntentRevision:
        """Reset a failed Generate attempt so keywords can fire again."""
        revision = self._require_revision(revision_id)
        if revision.status == IntentRevisionStatus.failed:
            revision.status = IntentRevisionStatus.accepted
            revision.error = None
            self.store.save_revision(revision)
        run = self.store.get_run(revision.run_id) if revision.run_id else None
        if run is not None and run.stage.value == "failed":
            # Soft-reset: keep Gate + keyword selection, rebuild the job only.
            run.stage = FourStageStage.awaiting_gate
            run.error = None
            run.failed_stage = None
            run.generation_spec = None
            run.generation_artifacts = []
            self.store.save_run(run)
        for batch in self.store.list_solution_batches(revision.session_id):
            if batch.revision_id != revision_id:
                continue
            if batch.status in {"failed", "cancelled"}:
                batch.status = "queued"
                batch.artifacts = []
                self.store.save_solution_batch(batch)
        return revision

    async def start_generation(self, revision_id: str, *, drive: bool = True) -> SolutionBatch:
        revision = self.prepare_generation_retry(revision_id)
        if revision.status not in {
            IntentRevisionStatus.accepted,
            IntentRevisionStatus.generating,
        }:
            raise FourStageConflict("generation requires an accepted revision")
        if not revision.delta_keywords:
            raise FourStageConflict(
                "generation requires an explicit selection for the current revision"
            )
        existing = next(
            (
                item
                for item in self.store.list_solution_batches(revision.session_id)
                if item.revision_id == revision_id
            ),
            None,
        )
        if existing is not None and existing.status in {"queued", "generating"} and drive:
            run = self.store.get_run(existing.run_id) if existing.run_id else None
            stuck = (
                existing.status == "generating"
                and (
                    not existing.artifacts
                    and (
                        run is None
                        or run.stage.value in {"awaiting_gate", "failed", "cancelled"}
                        or not (run.generation_artifacts or [])
                    )
                )
            )
            if stuck:
                existing.status = "queued"
                existing.artifacts = []
                self.store.save_solution_batch(existing)
            self._schedule_generation_queue(revision.session_id)
            return existing
        if existing is not None and existing.status == "completed" and existing.artifacts:
            return existing
        if revision.divergence_selection is not None:
            # Re-evaluate inheritance at Generate time so a prior bubble that
            # was accepted later is still included in this cumulative branch.
            try:
                revision = await self.save_selection(
                    revision_id,
                    revision.divergence_selection.model_copy(
                        deep=True,
                        update={"selected_keywords": list(revision.delta_keywords)},
                    ),
                )
            except FourStageConflict:
                # Keywords already chosen by the user — attach them as-is and generate.
                run = self._require_revision_run(revision)
                phrases = list(
                    revision.divergence_selection.resolved_prompt_phrases
                    or revision.delta_keywords
                )
                run.divergence_selection = revision.divergence_selection.model_copy(
                    deep=True,
                    update={
                        "selected_keywords": list(revision.delta_keywords),
                        "resolved_prompt_phrases": phrases or list(revision.delta_keywords),
                        "selected_candidate_ids": list(
                            revision.divergence_selection.selected_candidate_ids
                            or [f"kw_{index}" for index, _ in enumerate(revision.delta_keywords)]
                        ),
                    },
                )
                self.store.save_run(run)
        run = self._require_revision_run(revision)
        # Prefer revision identity image; keep run.spec source in sync for Qwen.
        image_ref = revision.source_context.source_image_ref
        if image_ref and run.source_context is not None:
            if run.source_context.source_image_ref != image_ref:
                run.source_context = run.source_context.model_copy(
                    update={"source_image_ref": image_ref}
                )
                self.store.save_run(run)
        if existing is not None:
            existing.status = "queued" if drive else "generating"
            existing.artifacts = []
            existing.base_keywords = list(revision.base_keywords)
            existing.delta_keywords = list(revision.delta_keywords)
            existing.cumulative_keywords = list(revision.effective_keywords)
            existing.source_context = revision.source_context
            self.store.save_solution_batch(existing)
            if drive:
                self._schedule_generation_queue(revision.session_id)
            return existing
        batch = SolutionBatch(
            batch_id=f"batch_{revision.revision_id}",
            session_id=revision.session_id,
            revision_id=revision.revision_id,
            intent_seq=revision.intent_seq,
            run_id=run.run_id,
            append_index=len(self.store.list_solution_batches(revision.session_id)) + 1,
            parent_batch_id=(
                self.store.list_solution_batches(revision.session_id)[-1].batch_id
                if self.store.list_solution_batches(revision.session_id)
                else None
            ),
            base_keywords=list(revision.base_keywords),
            delta_keywords=list(revision.delta_keywords),
            cumulative_keywords=list(revision.effective_keywords),
            source_context=revision.source_context,
            gate_id=revision.gate_id,
            status="queued" if drive else "generating",
        )
        self.store.save_solution_batch(batch)
        if drive:
            self._schedule_generation_queue(revision.session_id)
        return batch

    def _schedule_generation_queue(self, session_id: str) -> None:
        current = self._generation_tasks.get(session_id)
        if current is not None and not current.done():
            return
        task = asyncio.create_task(self.advance_generation_queue(session_id))
        self._generation_tasks[session_id] = task

        def cleanup(done: asyncio.Task[None]) -> None:
            if self._generation_tasks.get(session_id) is done:
                self._generation_tasks.pop(session_id, None)
            try:
                done.exception()
            except (asyncio.CancelledError, Exception):
                pass

        task.add_done_callback(cleanup)

    async def advance_generation_queue(self, session_id: str) -> None:
        """Run requested batches in intent order; completed rows stay append-only."""
        while True:
            queued: SolutionBatch | None = None
            async with self._generation_lock(session_id):
                batches = self.store.list_solution_batches(session_id)
                active = False
                for batch in batches:
                    run = self.store.get_run(batch.run_id)
                    if run and run.stage.value in {"completed", "failed", "cancelled"}:
                        batch.status = run.stage.value
                        batch.artifacts = list(run.generation_artifacts)
                        self.store.save_solution_batch(batch)
                        revision = self.store.get_revision(batch.revision_id)
                        if revision:
                            revision.status = (
                                IntentRevisionStatus.completed
                                if run.stage.value == "completed"
                                else IntentRevisionStatus.failed
                            )
                            revision.error = (run.error or {}).get("message")
                            self.store.save_revision(revision)
                    elif batch.status == "generating":
                        # A batch marked generating while the run is still at
                        # gate / missing will park the whole serial queue.
                        stuck = run is None or run.stage.value not in {
                            "generation",
                            "completed",
                        }
                        if stuck:
                            batch.status = "queued"
                            self.store.save_solution_batch(batch)
                        else:
                            active = True
                if active:
                    return
                queued = next((item for item in batches if item.status == "queued"), None)
                if queued is None:
                    return
                revision = self._require_revision(queued.revision_id)
                revision.status = IntentRevisionStatus.generating
                self.store.save_revision(revision)
                queued.status = "generating"
                self.store.save_solution_batch(queued)
            # Never hold the Observation/session lock while a GPU job runs.
            # A remote adapter may take minutes; new Behaviors and Sends must
            # remain writable throughout that period.
            await self.orchestrator.start_generation(queued.run_id)
            # Synchronous/local adapters may already be complete and loop to
            # the next batch. Remote adapters remain active and exit above.

    async def on_run_finished(self, run_id: str) -> None:
        for batch in self.store.list_solution_batches(
            run.session_id if (run := self.store.get_run(run_id)) else ""
        ):
            if batch.run_id == run_id:
                self._schedule_generation_queue(batch.session_id)
                return

    def create_version_node(
        self,
        session_id: str,
        request: VersionGraphNodeCreateRequest,
    ) -> VersionGraphNode:
        existing = self.store.find_version_node(
            session_id,
            request.parent_node_id,
            request.candidate_id,
        )
        if existing is not None:
            return existing
        if request.parent_node_id:
            parent = self.store.get_version_node(request.parent_node_id)
            if parent is None:
                raise FourStageError("version parent not found")
            if parent.session_id != session_id:
                raise FourStageConflict("version parent belongs to another session")
        node = VersionGraphNode(
            node_id=f"version_{uuid4().hex[:10]}",
            session_id=session_id,
            version_number=self.store.next_version_number(session_id),
            parent_node_id=request.parent_node_id,
            candidate_id=request.candidate_id,
            label=request.label,
            preview_url=request.preview_url,
            status=(
                VersionNodeStatus.mesh_ready
                if request.parent_node_id is None
                else request.status
            ),
        )
        self.store.save_version_node(node)
        state = self.store.get_version_graph_state(session_id)
        if state.active_node_id is None:
            self.store.set_active_version_node(session_id, node.node_id)
        self._record(
            session_id,
            "version.node_created",
            {"node": node.model_dump(mode="json")},
            correlation_id=node.node_id,
        )
        return node

    def update_version_node(
        self,
        session_id: str,
        node_id: str,
        request: VersionGraphNodeUpdateRequest,
    ) -> VersionGraphNode:
        node = self.store.get_version_node(node_id)
        if node is None:
            raise FourStageError("version node not found")
        if node.session_id != session_id:
            raise FourStageConflict("version node belongs to another session")
        for field, value in request.model_dump(exclude_unset=True).items():
            if field == "status" and value is None:
                continue
            setattr(node, field, value)
        saved = self.store.save_version_node(node)
        self._record(
            session_id,
            "version.node_updated",
            {"node": saved.model_dump(mode="json")},
            correlation_id=saved.node_id,
        )
        return saved

    def activate_version_node(
        self,
        session_id: str,
        node_id: str,
    ) -> VersionGraphState:
        node = self.store.get_version_node(node_id)
        if node is None:
            raise FourStageError("version node not found")
        if node.session_id != session_id:
            raise FourStageConflict("version node belongs to another session")
        self.store.set_active_version_node(session_id, node_id)
        self._record(
            session_id,
            "version.node_activated",
            {"node_id": node_id},
            correlation_id=node_id,
        )
        return self.store.get_version_graph_state(session_id)

    def delete_version_node(
        self,
        session_id: str,
        node_id: str,
    ) -> VersionGraphState:
        nodes = self.store.list_version_nodes(session_id)
        target = next((item for item in nodes if item.node_id == node_id), None)
        if target is None:
            raise FourStageError("version node not found")
        if target.session_id != session_id:
            raise FourStageConflict("version node belongs to another session")
        if len(nodes) <= 1:
            raise FourStageError("cannot delete the only version")

        to_delete = {node_id}
        growing = True
        while growing:
            growing = False
            for item in nodes:
                if item.parent_node_id in to_delete and item.node_id not in to_delete:
                    to_delete.add(item.node_id)
                    growing = True
        remaining = [item for item in nodes if item.node_id not in to_delete]
        if not remaining:
            raise FourStageError("cannot delete all versions")

        self.store.delete_version_nodes(session_id, to_delete)
        state = self.store.get_version_graph_state(session_id)
        if state.active_node_id is None or state.active_node_id in to_delete:
            fallback = (
                target.parent_node_id
                if target.parent_node_id and target.parent_node_id not in to_delete
                else sorted(remaining, key=lambda item: item.version_number)[0].node_id
            )
            self.store.set_active_version_node(session_id, fallback)
        self._record(
            session_id,
            "version.node_deleted",
            {"node_id": node_id, "deleted_ids": sorted(to_delete)},
            correlation_id=node_id,
        )
        return self.store.get_version_graph_state(session_id)

    def snapshot(self, session_id: str) -> RealtimeObservationSnapshot:
        revisions = self.store.list_revisions(session_id)
        batches = self.store.list_solution_batches(session_id)
        by_run = {item.run_id: item for item in batches}
        for revision in revisions:
            if not revision.run_id:
                continue
            run = self.store.get_run(revision.run_id)
            batch = by_run.get(revision.run_id)
            if run and batch:
                if run.stage.value in {"generation", "completed", "failed", "cancelled"}:
                    batch.status = run.stage.value
                    batch.artifacts = list(run.generation_artifacts)
                    self.store.save_solution_batch(batch)
                if run.stage.value == "completed":
                    revision.status = IntentRevisionStatus.completed
                    self.store.save_revision(revision)
                elif run.stage.value in {"failed", "cancelled"}:
                    revision.status = IntentRevisionStatus.failed
                    revision.error = (run.error or {}).get("message")
                    self.store.save_revision(revision)
        observation = self.store.get_live_observation(session_id) or LiveObservationState(
            session_id=session_id
        )
        current_batches = self.store.list_solution_batches(session_id)
        brief = self._ui_brief(observation, revisions, current_batches)
        digest = hashlib.sha256(
            json.dumps(brief.model_dump(mode="json"), sort_keys=True).encode("utf-8")
        ).hexdigest()[:20]
        self._record(
            session_id,
            "model.ui_brief_emitted",
            {"ui_brief": brief.model_dump(mode="json")},
            correlation_id=brief.question_id or observation.session_id,
            idempotency_key=f"ui-brief:{digest}",
            actor="model",
        )
        return RealtimeObservationSnapshot(
            observation=observation,
            behaviors=self.store.list_behaviors(session_id),
            revisions=revisions,
            solution_batches=current_batches,
            version_graph=self.store.get_version_graph_state(session_id),
            ui_brief=brief,
        )

    @staticmethod
    def _ui_brief(
        observation: LiveObservationState,
        revisions: list[IntentRevision],
        batches: list[SolutionBatch],
    ) -> UiBrief:
        pending = [
            item for item in revisions if item.status == IntentRevisionStatus.awaiting_gate
        ]
        phenomenon = observation.intent_summary or (
            f"当前正在调整{observation.scope}范围的{observation.operation}操作。"
            if observation.behavior_count
            else "当前工作区尚未记录明确的调整。"
        )
        next_question = "接下来想先调整哪个部分？"
        requires_response = False
        question_id = None
        status = "idle"
        details_ref = None
        if pending:
            active = pending[0]
            phenomenon = observation.intent_summary or (
                f"已识别到一个关于{active.gate_scope or '当前对象'}的调整意图。"
            )
            next_question = ""
            requires_response = False
            question_id = None
            details_ref = active.revision_id
            status = "awaiting_gate"
        elif any(item.status in {"queued", "generating", "generation"} for item in batches):
            completed = sum(len(item.artifacts) for item in batches)
            phenomenon = f"方案正在生成，当前已收到 {completed} 个结果。"
            next_question = ""
            status = "generating"
        return UiBrief(
            phenomenon=phenomenon[:140],
            next_question=next_question[:100],
            requires_response=requires_response,
            question_id=question_id,
            status=status,
            confidence=observation.intent_confidence or observation.confidence,
            details_ref=details_ref,
            pending_decision_count=len(pending),
        )

    def _rule_observation(self, session_id: str, behavior: BehaviorSession) -> LiveObservationState:
        state = self.store.get_live_observation(session_id) or LiveObservationState(
            session_id=session_id
        )
        state.latest_behavior_seq = behavior.behavior_seq
        state.behavior_count += 1
        state.operation = behavior.tool
        state.target = dict(behavior.target)
        state.scope = "part" if behavior.target.get("part_id") else "whole"
        self._describe_context(state, behavior)
        state.updated_at = now_utc()
        return state

    @staticmethod
    def _describe_context(state: LiveObservationState, behavior: BehaviorSession) -> None:
        """Report the observable 3D context of the latest committed behavior.

        This is a *description*, not an inference: it records how confidently
        we can name the current target so downstream display can decide whether
        to surface a part label. A concrete part selection reads as a specific
        target; a whole-object edit stays deliberately low-confidence because
        there is no single named part to describe.
        """
        has_named_target = bool(
            behavior.target.get("part_id")
            or behavior.target.get("part_label")
            or behavior.target.get("label")
        )
        state.confidence = 0.7 if has_named_target else 0.4

    async def _upgrade_gate_with_llm(
        self,
        revision: IntentRevision,
        behaviors: list[BehaviorSession],
        *,
        planner_target: str | None,
        planner_scope: str | None,
    ) -> None:
        gate_target, gate_scope, gate_question = await self._compose_revision_gate(
            revision,
            behaviors,
            planner_target,
            planner_scope,
        )
        revision.gate_target = gate_target
        revision.gate_scope = gate_scope
        revision.gate_question = gate_question

    async def _compose_revision_gate(
        self,
        revision: IntentRevision,
        behaviors: list[BehaviorSession],
        planner_target: str | None,
        planner_scope: str | None,
    ) -> tuple[str, str, str]:
        """Evidence-first Gate: location / semantic / LLM fill, then fixed question."""
        fallback = self._compress_revision_gate(
            revision,
            behaviors,
            planner_target,
            planner_scope,
            live_signals=revision.live_signals,
        )
        gateway = self.text_gateway
        if (
            not self.gate_llm_enabled
            or gateway is None
            or not getattr(gateway.profile, "api_key", None)
        ):
            return fallback

        semantic = revision.user_text.strip()
        if _is_invented_drawing_semantic(semantic):
            semantic = ""
        location = _behavior_location(behaviors)
        selected_part_id = str(revision.source_context.target_part_id or "").strip()
        if location is not None and not location.get("label") and not location.get("part_id"):
            if selected_part_id and not _is_generic_mesh_id(selected_part_id):
                location = {
                    **location,
                    "part_id": selected_part_id,
                    "label": selected_part_id,
                }
        # Fast Gate already locked scope from signals/location. Do not let the
        # LLM invent a generic「部件」when the user typed nothing.
        if not semantic:
            return fallback
        # Strong deterministic evidence: skip LLM when text already names scope/part
        # or drawing locked a part and there is no conflicting semantic.
        if (
            infer_text_part(semantic)
            or _has_requested_scope_marker(semantic.lower(), _SURFACE_SCOPE_MARKERS)
            or _has_requested_scope_marker(semantic.lower(), _IDENTITY_TRANSFORM_MARKERS)
            or _has_requested_scope_marker(semantic.lower(), _WHOLE_SCOPE_MARKERS)
        ):
            return fallback
        if location and location.get("label"):
            return fallback

        payload = {
            "location": location,
            "semantic": semantic or None,
            "object_type": revision.source_context.object_type,
            "selected_part_id": selected_part_id or None,
            "planner_target": planner_target,
            "planner_scope": planner_scope,
            "behaviors": [
                {
                    "tool": item.tool,
                    "part_id": item.target.get("part_id"),
                    "label": item.target.get("label"),
                    "stroke_count": item.stroke_count,
                }
                for item in behaviors[-6:]
            ],
            "rule_fallback": {
                "target": fallback[0],
                "scope": fallback[1],
                "question": fallback[2],
            },
            "hint": (
                "有 location 就提供位置；有 semantic 就提供语义；"
                "两者都没有再自行判断。不要把 behavior 列表和文字糊成一句。"
            ),
        }

        def validator(raw: dict[str, Any]) -> tuple[str, str, str]:
            scope = str(raw.get("scope") or "").strip().lower()
            if scope in {"material_region", "surface"}:
                scope = "material"
            if scope not in {"part", "material", "whole"}:
                raise ValueError(f"invalid scope: {scope}")
            label = str(raw.get("target_label") or "").strip()
            if _is_generic_mesh_id(label):
                raise ValueError(f"invalid target_label: {label}")
            return label, scope, _fixed_gate_question(scope, label, semantic)

        try:
            models = gateway.profile.ordered_text_models(
                ModelStage.INTENT,
                extras=[
                    "gpt-4.1-mini",
                    "gpt-4o-mini",
                    "gemini-2.5-flash",
                    "gemini-2.0-flash",
                ],
            )
            result = await gateway.complete_json(
                ModelStage.INTENT,
                [
                    {"role": "system", "content": _GATE_QUESTION_SYSTEM},
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False),
                    },
                ],
                validator=validator,
                repair_instruction=(
                    "Fix the JSON. scope must be part|material|whole; "
                    "target_label must be a short human label, never obj_group_*."
                ),
                temperature=0,
                max_tokens=120,
                models=models,
                timeout_sec=3.5,
                max_retries=1,
                allow_repair=True,
            )
            return result.value
        except (ModelTransportUnavailable, Exception) as exc:  # noqa: BLE001
            logger.info("gate LLM compose fallback: %s", exc)
            return fallback

    @staticmethod
    def _compress_revision_gate(
        revision: IntentRevision,
        behaviors: list[BehaviorSession],
        planner_target: str | None,
        planner_scope: str | None,
        live_signals: dict[str, Any] | None = None,
    ) -> tuple[str, str, str]:
        """Deterministic Gate from evidence channels.

        Priority:
        1. Real semantic text (scope markers / named parts)
        2. Drawing/sculpt location
        3. Selected mesh part / planner
        4. Whole object
        """
        raw_text = revision.user_text.strip()
        semantic = "" if _is_invented_drawing_semantic(raw_text) else raw_text
        text = semantic.lower()
        text_parts = infer_text_parts(semantic) if semantic else []
        text_part = text_parts[0] if text_parts else (infer_text_part(semantic) if semantic else None)

        location = _behavior_location(behaviors)
        mesh_part_id = str(revision.source_context.target_part_id or "").strip()
        if _is_generic_mesh_id(mesh_part_id):
            mesh_part_id = ""
        if location is not None:
            loc_part = str(location.get("part_id") or "").strip()
            loc_label = str(location.get("label") or "").strip()
            if _is_generic_mesh_id(loc_part):
                loc_part = ""
            if _is_generic_mesh_id(loc_label):
                loc_label = ""
            if not loc_part and not loc_label and mesh_part_id:
                loc_part = mesh_part_id
                loc_label = mesh_part_id
            location_part_id = loc_part
            location_label = loc_label or loc_part
        else:
            location_part_id = ""
            location_label = ""

        recent_target = behaviors[-1].target if behaviors else {}
        mesh_label = str(recent_target.get("label") or "").strip()
        if _is_generic_mesh_id(mesh_label):
            mesh_label = ""
        if text_part:
            part_id = text_part
            if (
                mesh_label
                and str(mesh_part_id).strip().lower() == str(text_part).strip().lower()
            ):
                part_label = mesh_label
            elif location_label and str(location_part_id).strip().lower() == str(text_part).strip().lower():
                part_label = location_label
            else:
                part_label = text_part
        elif location_part_id or location_label:
            part_id = location_part_id or location_label
            part_label = location_label or location_part_id
        elif mesh_part_id and location is not None:
            # Drawing present but unlabeled — keep selection if concrete.
            part_id = mesh_part_id
            part_label = mesh_label or mesh_part_id
        elif mesh_part_id and not location:
            part_id = mesh_part_id
            part_label = mesh_label or mesh_part_id
        else:
            part_id = ""
            part_label = ""

        identity = bool(semantic and _has_requested_scope_marker(text, _IDENTITY_TRANSFORM_MARKERS))
        surface = bool(semantic and _has_requested_scope_marker(text, _SURFACE_SCOPE_MARKERS))
        if semantic and not text_part and (identity or surface):
            if identity or _is_generic_mesh_id(part_id) or _is_generic_mesh_id(part_label):
                part_id = ""
                part_label = ""

        object_type = str(revision.source_context.object_type).strip()
        normalized_planner_target = str(planner_target or "").strip()
        planner_target_is_generic = _is_generic_mesh_id(normalized_planner_target)

        if surface and identity and not text_part:
            scope = "whole"
        elif surface:
            scope = "material"
        elif text_part:
            scope = "part"
        elif identity or (semantic and _has_requested_scope_marker(text, _WHOLE_SCOPE_MARKERS)):
            scope = "whole"
        elif location is not None and (location_part_id or location_label or part_id):
            scope = "part"
        elif part_id:
            scope = "part"
        else:
            scope = str(planner_scope or "whole").strip().lower()
            if scope in {"material_region", "surface"}:
                scope = "material"
            elif scope not in {"part", "material"}:
                scope = "whole"

        live = live_signals if isinstance(live_signals, dict) and live_signals else {}
        if not live and isinstance(getattr(revision, "live_signals", None), dict):
            live = revision.live_signals
        view_mode = str(live.get("view_mode") or "")
        orbit = int(live.get("viewport_orbit_count") or 0)
        zoom = int(live.get("viewport_zoom_count") or 0)
        dwell = float(live.get("dwell_ms") or 0)
        shape = _annotation_shape(behaviors)
        named = bool(part_label or part_id) and not _is_generic_mesh_id(part_label or part_id)
        generic_part = _is_generic_mesh_id(part_label or part_id or normalized_planner_target)
        unlabeled_drawing = location is not None and not (location_part_id or location_label)
        contour_drawing = shape in {
            "closed_contour",
            "horizontal_stroke",
            "vertical_stroke",
            "freehand_contour",
            "point_mark",
        }
        if not text_part and not surface:
            if scope == "part" and generic_part:
                scope = "whole"
                part_id = ""
                part_label = ""
            if not named and (unlabeled_drawing or contour_drawing):
                scope = "whole"
                part_id = ""
                part_label = ""
            elif named and view_mode == "detail" and dwell >= 800:
                scope = "part"
            elif not named and (view_mode in {"survey", "empty"} or orbit >= 2 or zoom >= 2):
                scope = "whole"

        def _display_part_label(raw: str) -> str:
            cleaned = str(raw or "").strip()
            if _is_generic_mesh_id(cleaned):
                return "部件"
            return cleaned

        if scope == "part":
            target = _display_part_label(
                part_label or ("" if planner_target_is_generic else normalized_planner_target)
            )
            return target, scope, _fixed_gate_question(scope, target, semantic)
        if scope == "material":
            if len(text_parts) > 1:
                target = object_type or "当前对象"
                return target, scope, _fixed_gate_question(scope, target, semantic)
            explicit_part = text_part or location_part_id or mesh_part_id
            if identity and not text_part:
                explicit_part = ""
            target = (
                (text_part or location_label or mesh_label or explicit_part).strip()
                if explicit_part
                else text_part if len(text_parts) == 1
                else object_type
            )
            target = _display_part_label(target) if explicit_part else (target or object_type)
            return target, scope, _fixed_gate_question(scope, target, semantic)
        if identity and not text_part:
            target = object_type or "当前对象"
            return target, "whole", _fixed_gate_question("whole", target, semantic)
        target = object_type if planner_target_is_generic or part_id else normalized_planner_target or object_type
        return target, "whole", _fixed_gate_question("whole", target, semantic)

    @staticmethod
    def _sync_gate_contract(
        revision: IntentRevision,
        behaviors: list[BehaviorSession],
        run: FourStageRun,
        gate_target: str,
        gate_scope: str,
    ) -> None:
        if run.intent_ir is None:
            return
        run.intent_ir.intent.scope = gate_scope
        if run.decision is not None:
            run.decision.recommended_scope = gate_scope
            run.decision.semantic_target = gate_target
        if gate_scope == "part":
            recent_target = behaviors[-1].target if behaviors else {}
            text_part = infer_text_part(revision.user_text)
            part_id = str(
                text_part
                or gate_target
                or revision.source_context.target_part_id
                or recent_target.get("part_id")
                or ""
            ).strip()
            run.intent_ir.target.part_id = part_id
            run.source_context.target_part_id = part_id
            revision.source_context.target_part_id = part_id
        elif gate_scope == "whole":
            run.intent_ir.target.part_id = None
            run.source_context.target_part_id = None
            revision.source_context.target_part_id = None

    @staticmethod
    def _behavior_events(behaviors: list[BehaviorSession]) -> list[UserEvent]:
        events: list[UserEvent] = []
        aliases = {"clay": "brush_end", "move": "drag_end", "select": "selection_ended"}
        for item in behaviors:
            payload: dict[str, Any] = {
                **item.target,
                **item.operation_summary,
                "stroke_count": item.stroke_count,
                "behavior_seq": item.behavior_seq,
                "start_views": item.start_views.model_dump(mode="json", exclude_none=True),
                "end_views": item.end_views.model_dump(mode="json", exclude_none=True),
                "evidence_refs": item.evidence_refs,
            }
            events.append(
                UserEvent(
                    type=aliases.get(item.tool, f"{item.tool}_end"),
                    event_id=item.behavior_id,
                    session_id=item.session_id,
                    timestamp=item.ended_at or item.started_at,
                    payload=payload,
                )
            )
        return events

    def _require_revision(self, revision_id: str) -> IntentRevision:
        revision = self.store.get_revision(revision_id)
        if revision is None:
            raise FourStageError(f"revision not found: {revision_id}")
        return revision

    def _require_revision_run(self, revision: IntentRevision) -> FourStageRun:
        run = self.store.get_run(revision.run_id) if revision.run_id else None
        if run is None:
            raise FourStageError("revision planner run is not ready")
        return run

    def _record(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
        actor: str = "system",
    ) -> None:
        if self.recorder is None:
            return
        self.recorder.append_system_event(
            session_id,
            event_type,
            actor=actor,
            payload=payload,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    async def _emit(self, session_id: str, event_type: str, payload: dict[str, Any]) -> None:
        recorded_type = {
            "observation.behavior_committed": "behavior.committed",
            "observation.updated": "model.observation_updated",
            "intent.revision_locked": "model.revision_locked",
            "intent.revision_updated": "model.revision_updated",
        }.get(event_type, event_type)
        body = next((value for value in payload.values() if isinstance(value, dict)), {})
        correlation_id = next(
            (
                str(body[key])
                for key in ("behavior_id", "revision_id", "run_id", "gate_id", "batch_id")
                if body.get(key)
            ),
            None,
        )
        self._record(
            session_id,
            recorded_type,
            payload,
            correlation_id=correlation_id,
            idempotency_key=(f"{recorded_type}:{correlation_id}" if correlation_id else None),
            actor="model" if recorded_type.startswith("model.") else "system",
        )
        manager = self.orchestrator.websocket_manager
        if manager is not None:
            await manager.broadcast(session_id, event_type, payload)


__all__ = ["RealtimeObservationService"]
