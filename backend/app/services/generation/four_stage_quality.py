"""Generation quality gate (strategy doc 9.3): structural, auditable checks.

Full VLM/QA of rendered images lives in the remote worker; this gate runs on
returned artifacts and blocks everything when a candidate fails. Failed gate =
retryable failure, never a placeholder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models import GenerationSpec


@dataclass
class QualityGateResult:
    passed: bool
    checks: list[dict[str, Any]] = field(default_factory=list)
    reason: str | None = None


class GenerationQualityGate:
    def evaluate(
        self,
        spec: GenerationSpec,
        artifacts: list[dict[str, Any]],
    ) -> QualityGateResult:
        checks: list[dict[str, Any]] = []
        checks.append(
            {
                "name": "artifacts_non_empty",
                "passed": bool(artifacts),
                "detail": f"artifacts={len(artifacts)}",
            }
        )
        urls = [artifact.get("url") for artifact in artifacts if artifact.get("url")]
        checks.append(
            {
                "name": "artifact_urls_present",
                "passed": len(urls) == len(artifacts) and bool(urls),
                "detail": f"urls={len(urls)}",
            }
        )
        if spec.prompt_candidates:
            goal_prefix = spec.prompt_candidates[0].split(" — ", 1)[0].strip().lower()
            has_goal = bool(goal_prefix) and all(
                prompt.split(" — ", 1)[0].strip().lower() == goal_prefix
                for prompt in spec.prompt_candidates
            )
            checks.append(
                {
                    "name": "prompt_intent_consistency",
                    "passed": has_goal,
                    "detail": "object and goal prefix are identical across candidates",
                }
            )
        if spec.preserved_constraints:
            preserved = all(
                any(constraint.lower() in prompt.lower() for constraint in spec.preserved_constraints)
                for prompt in spec.prompt_candidates
            )
            checks.append(
                {
                    "name": "constraints_preserved_in_prompts",
                    "passed": preserved,
                    "detail": f"constraints={spec.preserved_constraints}",
                }
            )
        if spec.target.scope == "part":
            forbidden = ("change the overall silhouette", "change the material appearance")
            part_needle = f"change only {spec.target.part_id or ''}".lower()
            local_only = bool(spec.target.part_id) and all(
                part_needle in prompt.lower()
                and not any(value in prompt.lower() for value in forbidden)
                for prompt in spec.prompt_candidates
            )
            checks.append(
                {
                    "name": "part_prompt_locality",
                    "passed": local_only,
                    "detail": f"target_part_id={spec.target.part_id}",
                }
            )
        if spec.target.scope in {"material", "material_region"}:
            forbidden = (
                "change the overall silhouette",
                "change the internal structure",
                "add/remove structural features",
            )
            surface_only = all(
                "part-aware semantic material transfer" in prompt.lower()
                and "preserving exact geometry" in prompt.lower()
                and "preserve category-defining semantic features and part roles" in prompt.lower()
                and "never coat every part with one uniform donor material" in prompt.lower()
                and not any(value in prompt.lower() for value in forbidden)
                for prompt in spec.prompt_candidates
            )
            checks.append(
                {
                    "name": "material_geometry_lock",
                    "passed": surface_only,
                    "detail": "appearance may change; geometry must remain fixed",
                }
            )
        if len(spec.prompt_candidates) >= 2:
            distinct = len(
                {prompt.split(" — ")[-1].split(";")[0].strip() for prompt in spec.prompt_candidates}
            )
            checks.append(
                {
                    "name": "candidate_axis_diversity",
                    "passed": distinct >= 2,
                    "detail": f"distinct_axes={distinct}",
                }
            )
        passed = all(check["passed"] for check in checks)
        return QualityGateResult(
            passed=passed,
            checks=checks,
            reason=None if passed else "quality gate failed",
        )
