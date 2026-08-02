from pathlib import Path
from uuid import UUID

from app.models import CandidateRequest, LegacyCandidate


class CreativeFlowAdapter:
    """LEGACY local stub boundary — frozen (Phase E).

    Canonical generation path is RemoteCreativeFlowWorkerAdapter via
    POST /api/v1/generation/*. Do not extend this class for new features.
    """

    def __init__(self, root: Path | None) -> None:
        self.root = root

    @property
    def is_configured(self) -> bool:
        return self.root is not None and self.root.exists()

    async def generate_candidates(self, job_id: UUID, request: CandidateRequest) -> list[LegacyCandidate]:
        raise RuntimeError(
            "CreativeFlowAdapter.generate_candidates is frozen. "
            "Use POST /api/v1/generation/replace|drag|diverge (remote worker)."
        )

    async def _generate_with_pipeline(
        self, job_id: UUID, request: CandidateRequest
    ) -> list[LegacyCandidate]:
        # TODO: Replace this boundary with the real CreativeFlow structured transfer call.
        # The API contract is intentionally shaped around source part, relation intent,
        # drag intent, and multiple candidates so the frontend can be developed in parallel.
        return self._generate_stub_candidates(job_id, request, source="creativeflow-configured-stub")

    def _generate_stub_candidates(
        self,
        job_id: UUID,
        request: CandidateRequest,
        source: str = "local-stub",
    ) -> list[LegacyCandidate]:
        relation = request.relation_prompt or self._relation_from_drag(request)
        return [
            LegacyCandidate(
                id=f"{job_id}-{index}",
                label=f"Candidate {index + 1}",
                relation=relation,
                mesh_url=None,
                thumbnail_url=None,
                scores={
                    "novelty": round(0.55 + index * 0.04, 3),
                    "intent_alignment": round(0.82 - index * 0.02, 3),
                    "identity_preservation": round(0.78 - index * 0.015, 3),
                },
                metadata={
                    "asset_id": request.asset_id,
                    "source_part_id": request.source_part_id,
                    "adapter": source,
                },
            )
            for index in range(request.candidate_count)
        ]

    def _relation_from_drag(self, request: CandidateRequest) -> str:
        if request.drag_intent is None:
            return "semantic part variation"
        drag = request.drag_intent
        dx = drag.end[0] - drag.start[0]
        dy = drag.end[1] - drag.start[1]
        dz = drag.end[2] - drag.start[2]
        return f"near-space regeneration from drag vector ({dx:.2f}, {dy:.2f}, {dz:.2f})"
