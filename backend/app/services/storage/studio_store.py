from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models import (
    ApiErrorBody,
    ActionAtom,
    AnalogyDirection,
    AssetCreateRequest,
    AssetRecord,
    AssetVersionRecord,
    ArtifactRecord,
    Candidate,
    CaseCreateRequest,
    CaseRecord,
    DesignPhase,
    InteractionInterpretation,
    IntentDraft,
    IntentDraftCreateRequest,
    IntentDraftUpdateRequest,
    JobRecord,
    JobStage,
    JobStatus,
    MemoryRecord,
    SessionCreateRequest,
    SessionRecord,
    SessionUpdateRequest,
    StageState,
    StoreStateImportResponse,
    StoreStateSnapshot,
    UserEvent,
    WorkerJobRecord,
    now_utc,
)


class InMemoryStudioStore:
    def __init__(self) -> None:
        self.sessions: dict[str, SessionRecord] = {}
        self.assets: dict[str, AssetRecord] = {}
        self.jobs: dict[str, JobRecord] = {}
        self.candidates: dict[str, Candidate] = {}
        self.cases: dict[str, CaseRecord] = {}
        self.asset_versions: dict[str, AssetVersionRecord] = {}
        self.action_atoms: dict[str, ActionAtom] = {}
        self.session_action_atoms: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=500))
        self.directions: dict[str, AnalogyDirection] = {}
        self.session_directions: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=200))
        self.intent_drafts: dict[str, IntentDraft] = {}
        self.artifacts: dict[str, ArtifactRecord] = {}
        self.worker_jobs: dict[str, WorkerJobRecord] = {}
        self.memories: dict[str, MemoryRecord] = {}
        self.events: dict[str, UserEvent] = {}
        self.interpretations: dict[str, InteractionInterpretation] = {}
        self.session_events: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=100))
        self.session_interpretations: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=100))
        self.persistence_path: Path | None = None
        self._autosave_enabled = False

    def configure_persistence(self, path: Path, *, load_existing: bool = True) -> None:
        self.persistence_path = path
        self._autosave_enabled = True
        path.parent.mkdir(parents=True, exist_ok=True)
        if load_existing and path.exists():
            self.load_persisted_state(path)

    def load_persisted_state(self, path: Path | None = None) -> StoreStateImportResponse | None:
        source = path or self.persistence_path
        if source is None or not source.exists():
            return None
        snapshot = StoreStateSnapshot.model_validate_json(source.read_text(encoding="utf-8"))
        return self.import_state(snapshot, replace=True, autosave=False)

    def persist_state(self) -> None:
        if not self._autosave_enabled or self.persistence_path is None:
            return
        self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.persistence_path.with_suffix(f"{self.persistence_path.suffix}.tmp")
        tmp.write_text(self.export_state().model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(self.persistence_path)

    def _autosave(self) -> None:
        try:
            self.persist_state()
        except OSError:
            # Autosave is a recovery aid for the prototype, not a reason to fail
            # user-facing operations. Explicit export remains available for audit.
            return

    def create_session(self, req: SessionCreateRequest) -> SessionRecord:
        session_id = f"sess_{uuid4().hex[:10]}"
        session = SessionRecord(
            session_id=session_id,
            title=req.title,
            user_id=req.user_id,
            metadata=req.metadata,
        )
        self.sessions[session_id] = session
        self._autosave()
        return session

    def get_session(self, session_id: str) -> SessionRecord | None:
        return self.sessions.get(session_id)

    def update_session(self, session_id: str, req: SessionUpdateRequest) -> SessionRecord | None:
        session = self.sessions.get(session_id)
        if session is None:
            return None
        if req.title is not None:
            session.title = req.title
        if req.status is not None:
            session.status = req.status
        if req.metadata is not None:
            session.metadata.update(req.metadata)
        session.updated_at = now_utc()
        self.sessions[session_id] = session
        self._autosave()
        return session

    def save_stage(self, session_id: str, stage: StageState) -> StageState | None:
        session = self.sessions.get(session_id)
        if session is None:
            return None
        stage.updated_at = now_utc()
        session.stage = stage
        session.updated_at = now_utc()
        self.sessions[session_id] = session
        self._autosave()
        return stage

    def reset_session_workspace(self, session_id: str) -> SessionRecord:
        """清空会话工作区历史（用户不下载即删除）。

        移除该会话的资产/产物/行为原子/意图草稿/候选/任务/记忆，并把 stage
        重置为空白；保留 SessionRecord 本体，使前端刷新后回到空白工作区。
        """
        session = self.sessions.get(session_id)
        if session is None:
            raise KeyError(f"session not found: {session_id}")
        for asset_id in [
            asset_id
            for asset_id, asset in self.assets.items()
            if asset.session_id == session_id
        ]:
            self.assets.pop(asset_id, None)
        for artifact_id in [
            artifact_id
            for artifact_id, artifact in self.artifacts.items()
            if artifact.session_id == session_id
        ]:
            self.artifacts.pop(artifact_id, None)
        for atom_id in list(self.session_action_atoms.get(session_id, [])):
            self.action_atoms.pop(atom_id, None)
        self.session_action_atoms.pop(session_id, None)
        for draft_id in [
            draft_id
            for draft_id, draft in self.intent_drafts.items()
            if draft.session_id == session_id
        ]:
            self.intent_drafts.pop(draft_id, None)
        for candidate_id in [
            candidate_id
            for candidate_id, candidate in self.candidates.items()
            if candidate.session_id == session_id
        ]:
            self.candidates.pop(candidate_id, None)
        for job_id in [
            job_id
            for job_id, job in self.jobs.items()
            if job.session_id == session_id
        ]:
            self.jobs.pop(job_id, None)
        for memory_id in [
            memory_id
            for memory_id, memory in self.memories.items()
            if memory.session_id == session_id
        ]:
            self.memories.pop(memory_id, None)
        for event_id in list(self.session_events.get(session_id, [])):
            self.events.pop(event_id, None)
        self.session_events.pop(session_id, None)
        for interpretation_id in list(self.session_interpretations.get(session_id, [])):
            self.interpretations.pop(interpretation_id, None)
        self.session_interpretations.pop(session_id, None)
        for direction_id in list(self.session_directions.get(session_id, [])):
            self.directions.pop(direction_id, None)
        self.session_directions.pop(session_id, None)
        session.status = "active"
        session.stage = StageState(phase="idle", confidence=1.0)
        session.metadata = {
            key: value
            for key, value in session.metadata.items()
            if key not in {"live_signals", "live_signals_updated_at", "live_signals_source", "candidate_memory"}
        }
        session.updated_at = now_utc()
        self.sessions[session_id] = session
        self._autosave()
        return session

    def create_asset(self, req: AssetCreateRequest) -> AssetRecord:
        asset_id = f"asset_{uuid4().hex[:10]}"
        parts = req.parts or []
        asset = AssetRecord(
            asset_id=asset_id,
            session_id=req.session_id,
            object_type=req.object_type,
            label=req.label or f"{req.object_type} source model",
            mesh_url=req.mesh_url,
            obj_url=req.obj_url,
            thumbnail_url=req.thumbnail_url,
            parts=parts,
            metadata=req.metadata,
        )
        self.assets[asset_id] = asset
        stage = self.sessions[req.session_id].stage
        stage.active_asset_id = asset_id
        stage.updated_at = now_utc()
        self.sessions[req.session_id].stage = stage
        self._autosave()
        return asset

    def get_asset(self, asset_id: str) -> AssetRecord | None:
        return self.assets.get(asset_id)

    def create_asset_version(
        self,
        asset_id: str,
        *,
        version_id: str | None = None,
        mesh_url: str | None,
        obj_url: str | None,
        thumbnail_url: str | None,
        edit_ops: list[dict[str, Any]],
        parent_version_id: str | None,
        source: str,
        metadata: dict[str, Any],
    ) -> AssetVersionRecord:
        version = AssetVersionRecord(
            version_id=version_id or f"ver_{uuid4().hex[:10]}",
            asset_id=asset_id,
            parent_version_id=parent_version_id,
            mesh_url=mesh_url,
            obj_url=obj_url,
            thumbnail_url=thumbnail_url,
            edit_ops=edit_ops,
            source=source,
            metadata=metadata,
        )
        self.asset_versions[version.version_id] = version
        asset = self.assets.get(asset_id)
        if asset is not None:
            asset.metadata = {
                **(asset.metadata or {}),
                "current_version_id": version.version_id,
                "version_count": len(self.list_asset_versions(asset_id)),
            }
            if obj_url:
                asset.obj_url = obj_url
            if mesh_url:
                asset.mesh_url = mesh_url
            self.assets[asset_id] = asset
        self._autosave()
        return version

    def get_asset_version(self, version_id: str) -> AssetVersionRecord | None:
        return self.asset_versions.get(version_id)

    def list_asset_versions(self, asset_id: str, limit: int = 50) -> list[AssetVersionRecord]:
        rows = [
            version
            for version in self.asset_versions.values()
            if version.asset_id == asset_id
        ]
        return sorted(rows, key=lambda item: item.created_at, reverse=True)[: max(1, limit)]

    def create_job(self, request: Any, stage: JobStage = JobStage.queued) -> JobRecord:
        job_id = f"job_{uuid4().hex[:10]}"
        job = JobRecord(
            job_id=job_id,
            session_id=request.session_id,
            status=JobStatus.queued,
            stage=stage,
            request=request,
            message="Job queued",
        )
        self.jobs[job_id] = job
        self._autosave()
        return job

    def get_job(self, job_id: str) -> JobRecord | None:
        return self.jobs.get(job_id)

    def save_job(self, job: JobRecord) -> JobRecord:
        job.updated_at = now_utc()
        self.jobs[job.job_id] = job
        self._autosave()
        return job

    def fail_job(self, job: JobRecord, code: str, message: str, retryable: bool = True) -> JobRecord:
        job.status = JobStatus.failed
        job.stage = JobStage.failed
        job.progress = 1
        job.error = ApiErrorBody(code=code, message=message, retryable=retryable)
        return self.save_job(job)

    def save_candidate(self, candidate: Candidate) -> Candidate:
        self.candidates[candidate.candidate_id] = candidate
        job = self.jobs.get(candidate.job_id)
        if job and candidate.candidate_id not in job.candidate_ids:
            job.candidate_ids.append(candidate.candidate_id)
            self.save_job(job)
        self._autosave()
        return candidate

    def get_candidate(self, candidate_id: str) -> Candidate | None:
        return self.candidates.get(candidate_id)

    def save_artifact(self, artifact: ArtifactRecord) -> ArtifactRecord:
        self.artifacts[artifact.artifact_id] = artifact
        self._autosave()
        return artifact

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        return self.artifacts.get(artifact_id)

    def list_artifacts(
        self,
        *,
        session_id: str | None = None,
        asset_id: str | None = None,
        candidate_id: str | None = None,
        worker: str | None = None,
        artifact_type: str | None = None,
        limit: int = 100,
    ) -> list[ArtifactRecord]:
        rows = sorted(self.artifacts.values(), key=lambda item: item.created_at, reverse=True)
        if session_id:
            rows = [item for item in rows if item.session_id == session_id]
        if asset_id:
            rows = [item for item in rows if item.asset_id == asset_id]
        if candidate_id:
            rows = [item for item in rows if item.candidate_id == candidate_id]
        if worker:
            rows = [item for item in rows if item.worker == worker]
        if artifact_type:
            rows = [item for item in rows if item.type == artifact_type]
        return rows[: max(1, min(limit, 500))]

    def recent_session_job(self, session_id: str) -> JobRecord | None:
        jobs = [job for job in self.jobs.values() if job.session_id == session_id]
        if not jobs:
            return None
        return sorted(jobs, key=lambda job: job.updated_at, reverse=True)[0]

    def save_worker_job(self, job: WorkerJobRecord) -> WorkerJobRecord:
        job.updated_at = now_utc()
        self.worker_jobs[job.job_id] = job
        self._autosave()
        return job

    def get_worker_job(self, job_id: str) -> WorkerJobRecord | None:
        return self.worker_jobs.get(job_id)

    def create_case(self, req: CaseCreateRequest) -> CaseRecord:
        case_id = f"case_{uuid4().hex[:10]}"
        case = CaseRecord(
            case_id=case_id,
            session_id=req.session_id,
            title=req.title,
            asset_id=req.asset_id,
            accepted_candidate_ids=req.accepted_candidate_ids,
            notes=req.notes,
            report_url=f"/files/cases/{case_id}/report.html",
            metadata=req.metadata,
        )
        self.cases[case_id] = case
        stage = self.sessions[req.session_id].stage
        stage.phase = DesignPhase.finalizing
        stage.confidence = 0.85
        stage.current_goal = f"Saved case: {req.title}"
        self.save_stage(req.session_id, stage)
        self._autosave()
        return case

    def get_case(self, case_id: str) -> CaseRecord | None:
        return self.cases.get(case_id)

    def create_intent_draft(self, req: IntentDraftCreateRequest) -> IntentDraft:
        draft_id = f"draft_{uuid4().hex[:10]}"
        title = (req.title or req.text or "Untitled intent").strip() or "Untitled intent"
        draft = IntentDraft(
            draft_id=draft_id,
            session_id=req.session_id,
            asset_id=req.asset_id,
            title=title[:96],
            text=req.text,
            behavior_atoms=req.behavior_atoms,
            image_refs=req.image_refs,
            model_refs=req.model_refs,
            metadata=req.metadata,
        )
        for atom in draft.behavior_atoms:
            self.save_action_atom(req.session_id, atom)
        self.intent_drafts[draft_id] = draft
        self.save_memory(
            MemoryRecord(
                memory_id=f"mem_{uuid4().hex[:10]}",
                session_id=req.session_id,
                category="working",
                type="intent_draft",
                source_id=draft_id,
                asset_id=req.asset_id,
                confidence=0.82,
                content=draft.model_dump(mode="json"),
                tags=["intent_draft", "behavior_composition"],
            )
        )
        self._autosave()
        return draft

    def save_action_atom(self, session_id: str, atom: ActionAtom) -> ActionAtom:
        is_new = atom.atom_id not in self.action_atoms
        self.action_atoms[atom.atom_id] = atom
        if atom.atom_id not in self.session_action_atoms[session_id]:
            self.session_action_atoms[session_id].append(atom.atom_id)
        if is_new:
            self.save_memory(
                MemoryRecord(
                    memory_id=f"mem_{uuid4().hex[:10]}",
                    session_id=session_id,
                    category="episodic",
                    type=f"action_atom:{atom.tool}",
                    source_id=atom.atom_id,
                    asset_id=_payload_asset_id(atom.target) or _payload_asset_id(atom.evidence),
                    part_id=_payload_part_id(atom.target) or _payload_part_id(atom.evidence),
                    confidence=0.8,
                    content=atom.model_dump(mode="json"),
                    tags=["action_atom", atom.tool],
                )
            )
        self._autosave()
        return atom

    def get_action_atom(self, atom_id: str) -> ActionAtom | None:
        return self.action_atoms.get(atom_id)

    def list_action_atoms(self, session_id: str, limit: int = 100) -> list[ActionAtom]:
        ids = list(self.session_action_atoms[session_id])[-max(1, min(limit, 500)) :]
        return [self.action_atoms[item_id] for item_id in ids if item_id in self.action_atoms]

    def save_direction(self, session_id: str, direction: AnalogyDirection) -> AnalogyDirection:
        self.directions[direction.direction_id] = direction
        if direction.direction_id not in self.session_directions[session_id]:
            self.session_directions[session_id].append(direction.direction_id)
        self.save_memory(
            MemoryRecord(
                memory_id=f"mem_{uuid4().hex[:10]}",
                session_id=session_id,
                category="working",
                type="analogy_direction",
                source_id=direction.direction_id,
                content=direction.model_dump(mode="json"),
                confidence=direction.score,
                tags=[
                    "analogy_direction",
                    direction.dimension,
                    str(direction.metadata.get("status") or "suggested"),
                ],
            )
        )
        self._autosave()
        return direction

    def get_direction(self, direction_id: str) -> AnalogyDirection | None:
        return self.directions.get(direction_id)

    def list_directions(self, session_id: str, limit: int = 100) -> list[AnalogyDirection]:
        ids = list(self.session_directions[session_id])[-max(1, min(limit, 200)) :]
        rows = [self.directions[item_id] for item_id in ids if item_id in self.directions]
        return rows[::-1]

    def get_intent_draft(self, draft_id: str) -> IntentDraft | None:
        return self.intent_drafts.get(draft_id)

    def update_intent_draft(
        self,
        draft_id: str,
        req: IntentDraftUpdateRequest,
    ) -> IntentDraft | None:
        draft = self.intent_drafts.get(draft_id)
        if draft is None:
            return None
        if req.title is not None:
            draft.title = req.title.strip()[:96] or draft.title
        if req.text is not None:
            draft.text = req.text
        if req.behavior_atoms is not None:
            draft.behavior_atoms = req.behavior_atoms
            for atom in draft.behavior_atoms:
                self.save_action_atom(draft.session_id, atom)
        if req.image_refs is not None:
            draft.image_refs = req.image_refs
        if req.model_refs is not None:
            draft.model_refs = req.model_refs
        if req.status is not None:
            draft.status = req.status
        if req.metadata is not None:
            draft.metadata = {**draft.metadata, **req.metadata}
        draft.updated_at = now_utc()
        self.intent_drafts[draft_id] = draft
        self._autosave()
        return draft

    def list_intent_drafts(self, session_id: str, include_archived: bool = False) -> list[IntentDraft]:
        rows = [item for item in self.intent_drafts.values() if item.session_id == session_id]
        if not include_archived:
            rows = [item for item in rows if item.status != "archived"]
        return sorted(rows, key=lambda item: item.updated_at, reverse=True)

    def save_event(self, event: UserEvent) -> UserEvent:
        self.events[event.event_id] = event
        self.session_events[event.session_id].append(event.event_id)
        self.save_memory(
            MemoryRecord(
                memory_id=f"mem_{uuid4().hex[:10]}",
                session_id=event.session_id,
                category="episodic",
                type=f"event:{event.type}",
                source_id=event.event_id,
                asset_id=_payload_asset_id(event.payload),
                part_id=_payload_part_id(event.payload),
                candidate_id=event.payload.get("candidate_id"),
                content={
                    "event_id": event.event_id,
                    "event_type": event.type,
                    "timestamp": event.timestamp.isoformat(),
                    "payload": event.payload,
                },
                tags=[event.type],
            )
        )
        self._autosave()
        return event

    def recent_events(self, session_id: str, limit: int = 20) -> list[UserEvent]:
        ids = list(self.session_events[session_id])[-limit:]
        return [self.events[event_id] for event_id in ids if event_id in self.events]

    def save_interpretation(
        self, interpretation: InteractionInterpretation
    ) -> InteractionInterpretation:
        self.interpretations[interpretation.interpretation_id] = interpretation
        self.session_interpretations[interpretation.session_id].append(
            interpretation.interpretation_id
        )
        self.save_memory(
            MemoryRecord(
                memory_id=f"mem_{uuid4().hex[:10]}",
                session_id=interpretation.session_id,
                category="working",
                type="interpretation",
                source_id=interpretation.interpretation_id,
                asset_id=interpretation.target.asset_id,
                part_id=interpretation.target.part_id,
                candidate_id=interpretation.features.get("candidate_id")
                if isinstance(interpretation.features, dict)
                else None,
                confidence=interpretation.confidence,
                content={
                    "primary_intent": interpretation.primary_intent.value,
                    "ambiguity": interpretation.ambiguity,
                    "assistance_policy": interpretation.assistance_policy.value,
                    "evidence": interpretation.evidence,
                    "target": interpretation.target.model_dump(mode="json"),
                },
                tags=[interpretation.primary_intent.value, interpretation.action_type],
            )
        )
        self._autosave()
        return interpretation

    def get_interpretation(self, interpretation_id: str) -> InteractionInterpretation | None:
        return self.interpretations.get(interpretation_id)

    def recent_interpretations(
        self, session_id: str, limit: int = 20
    ) -> list[InteractionInterpretation]:
        ids = list(self.session_interpretations[session_id])[-limit:]
        return [self.interpretations[item_id] for item_id in ids if item_id in self.interpretations]

    def save_memory(self, memory: MemoryRecord) -> MemoryRecord:
        memory.updated_at = now_utc()
        self.memories[memory.memory_id] = memory
        self._autosave()
        return memory

    def list_memories(
        self,
        *,
        session_id: str,
        category: str | None = None,
        asset_id: str | None = None,
        part_id: str | None = None,
        candidate_id: str | None = None,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        rows = [item for item in self.memories.values() if item.session_id == session_id]
        if category:
            rows = [item for item in rows if item.category == category]
        if asset_id:
            rows = [item for item in rows if item.asset_id == asset_id]
        if part_id:
            rows = [item for item in rows if item.part_id == part_id]
        if candidate_id:
            rows = [item for item in rows if item.candidate_id == candidate_id]
        rows = sorted(rows, key=lambda item: item.updated_at, reverse=True)
        return rows[: max(1, min(limit, 500))]

    def memory_by_category(self, session_id: str, limit_per_category: int = 20) -> dict[str, list[MemoryRecord]]:
        categories = ["working", "episodic", "semantic", "procedural", "reflective"]
        return {
            category: self.list_memories(
                session_id=session_id,
                category=category,
                limit=limit_per_category,
            )
            for category in categories
        }

    def export_state(self) -> StoreStateSnapshot:
        return StoreStateSnapshot(
            sessions=sorted(self.sessions.values(), key=lambda item: item.created_at),
            assets=sorted(self.assets.values(), key=lambda item: item.created_at),
            jobs=sorted(self.jobs.values(), key=lambda item: item.created_at),
            candidates=sorted(self.candidates.values(), key=lambda item: item.candidate_id),
            cases=sorted(self.cases.values(), key=lambda item: item.created_at),
            asset_versions=sorted(self.asset_versions.values(), key=lambda item: item.created_at),
            artifacts=sorted(self.artifacts.values(), key=lambda item: item.created_at),
            worker_jobs=sorted(self.worker_jobs.values(), key=lambda item: item.created_at),
            memories=sorted(self.memories.values(), key=lambda item: item.created_at),
            intent_drafts=sorted(self.intent_drafts.values(), key=lambda item: item.created_at),
            action_atoms=sorted(self.action_atoms.values(), key=lambda item: item.created_at),
            directions=sorted(self.directions.values(), key=lambda item: item.direction_id),
            events=sorted(self.events.values(), key=lambda item: item.timestamp),
            interpretations=sorted(
                self.interpretations.values(),
                key=lambda item: item.created_at,
            ),
            session_action_atoms={
                key: list(value) for key, value in self.session_action_atoms.items()
            },
            session_directions={key: list(value) for key, value in self.session_directions.items()},
            session_events={key: list(value) for key, value in self.session_events.items()},
            session_interpretations={
                key: list(value) for key, value in self.session_interpretations.items()
            },
        )

    def import_state(
        self,
        snapshot: StoreStateSnapshot,
        replace: bool = False,
        autosave: bool = True,
    ) -> StoreStateImportResponse:
        if snapshot.version != 1:
            raise ValueError(f"Unsupported store snapshot version: {snapshot.version}")
        if replace:
            self.sessions.clear()
            self.assets.clear()
            self.jobs.clear()
            self.candidates.clear()
            self.cases.clear()
            self.asset_versions.clear()
            self.artifacts.clear()
            self.worker_jobs.clear()
            self.memories.clear()
            self.intent_drafts.clear()
            self.action_atoms.clear()
            self.directions.clear()
            self.session_action_atoms.clear()
            self.session_directions.clear()
            self.events.clear()
            self.interpretations.clear()
            self.session_events.clear()
            self.session_interpretations.clear()

        for item in snapshot.sessions:
            self.sessions[item.session_id] = item
        for item in snapshot.assets:
            self.assets[item.asset_id] = item
        for item in snapshot.jobs:
            self.jobs[item.job_id] = item
        for item in snapshot.candidates:
            self.candidates[item.candidate_id] = item
        for item in snapshot.cases:
            self.cases[item.case_id] = item
        for item in snapshot.asset_versions:
            self.asset_versions[item.version_id] = item
        for item in snapshot.artifacts:
            self.artifacts[item.artifact_id] = item
        for item in snapshot.worker_jobs:
            self.worker_jobs[item.job_id] = item
        for item in snapshot.memories:
            self.memories[item.memory_id] = item
        for item in snapshot.intent_drafts:
            self.intent_drafts[item.draft_id] = item
        for item in snapshot.action_atoms:
            self.action_atoms[item.atom_id] = item
        for item in snapshot.directions:
            self.directions[item.direction_id] = item
        for session_id, atom_ids in snapshot.session_action_atoms.items():
            self.session_action_atoms[session_id] = deque(atom_ids[-500:], maxlen=500)
        for session_id, direction_ids in snapshot.session_directions.items():
            self.session_directions[session_id] = deque(direction_ids[-200:], maxlen=200)
        for item in snapshot.events:
            self.events[item.event_id] = item
        for item in snapshot.interpretations:
            self.interpretations[item.interpretation_id] = item

        for session_id, event_ids in snapshot.session_events.items():
            merged = list(self.session_events[session_id])
            for event_id in event_ids:
                if event_id not in merged:
                    merged.append(event_id)
            self.session_events[session_id] = deque(merged[-100:], maxlen=100)
        for session_id, interpretation_ids in snapshot.session_interpretations.items():
            merged = list(self.session_interpretations[session_id])
            for interpretation_id in interpretation_ids:
                if interpretation_id not in merged:
                    merged.append(interpretation_id)
            self.session_interpretations[session_id] = deque(merged[-100:], maxlen=100)

        response = StoreStateImportResponse(
            replaced=replace,
            imported={
                "sessions": len(snapshot.sessions),
                "assets": len(snapshot.assets),
                "jobs": len(snapshot.jobs),
                "candidates": len(snapshot.candidates),
                "cases": len(snapshot.cases),
                "artifacts": len(snapshot.artifacts),
                "worker_jobs": len(snapshot.worker_jobs),
                "memories": len(snapshot.memories),
                "intent_drafts": len(snapshot.intent_drafts),
                "action_atoms": len(snapshot.action_atoms),
                "directions": len(snapshot.directions),
                "events": len(snapshot.events),
                "interpretations": len(snapshot.interpretations),
            },
        )
        if autosave:
            self._autosave()
        return response

def _payload_asset_id(payload: dict[str, Any]) -> str | None:
    value = payload.get("active_asset_id") or payload.get("asset_id")
    if value:
        return str(value)
    selection = payload.get("selection")
    if isinstance(selection, dict) and selection.get("asset_id"):
        return str(selection["asset_id"])
    return None


def _payload_part_id(payload: dict[str, Any]) -> str | None:
    value = payload.get("part_id")
    if value:
        return str(value)
    selection = payload.get("selection")
    if isinstance(selection, dict) and selection.get("part_id"):
        return str(selection["part_id"])
    return None
