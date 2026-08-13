"""EvidenceAssembler: bounded, auditable evidence for the Gemini judge.

Strategy doc 8.3:
- full IntentIR, top-5 retrieval matches only (never the whole corpus);
- at most 1 viewport image + 3 annotation/mask/reference images, URLs only;
- prior retrieval text is wrapped as explicitly untrusted evidence data;
- asset/part semantics, user hard constraints and recent Gate feedback are
  included as separate bounded fields.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.models import FourStageRun, IntentIR, RetrievalBundle


class EvidenceAssembler:
    def __init__(
        self,
        *,
        max_images: int = 4,
        max_image_bytes: int = 5_242_880,
    ) -> None:
        self.max_images = max_images
        self.max_image_bytes = max_image_bytes

    def assemble(
        self,
        *,
        run: FourStageRun,
        intent_ir: IntentIR,
        retrieval: RetrievalBundle,
        feedback_lookup: Callable[[str], float] | None = None,
    ) -> dict[str, Any]:
        images: list[dict[str, Any]] = []
        refs = list(intent_ir.observations.image_refs or [])
        for index, ref in enumerate(refs[: self.max_images]):
            images.append(
                {
                    "role": "viewport" if index == 0 else "reference",
                    "url": ref,
                }
            )
        matches = [
            match.model_dump(mode="json") for match in (retrieval.matches or [])[:5]
        ]
        feedback = {}
        if feedback_lookup is not None:
            for match in matches:
                case_id = match.get("case_id")
                if case_id:
                    feedback[case_id] = feedback_lookup(case_id)
        return {
            "intent_ir": intent_ir.model_dump(mode="json"),
            "retrieval_evidence": {
                "untrusted_prior_data": True,
                "retrieval_id": retrieval.retrieval_id,
                "abstained": retrieval.abstained,
                "abstain_reason": retrieval.abstain_reason,
                "matches": matches,
            },
            "images": images,
            "hard_constraints": list(intent_ir.intent.constraints),
            "context": {
                "session_id": run.session_id,
                "asset_id": intent_ir.target.asset_id,
                "object_type": intent_ir.target.object_type,
                "part_id": intent_ir.target.part_id,
                "scope": intent_ir.intent.scope,
                "recent_gate_feedback": feedback,
            },
        }
