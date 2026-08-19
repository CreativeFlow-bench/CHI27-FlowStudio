"""Phase 4 tests: GenerationSpecBuilder + quality gate + GPU-serialized jobs."""

from __future__ import annotations

import asyncio

import pytest

from app.api.four_stage import _hy3d_artifact_paths, _hy3d_job_payload
from app.models import (
    DecisionIR,
    DecisionOption,
    DivergenceSelection,
    FourStageRun,
    FourStageStage,
    IntentCore,
    IntentIR,
    IntentObservations,
    IntentTarget,
)
from app.services.generation.four_stage_generation import FourStageGenerationService
from app.services.generation.four_stage_quality import GenerationQualityGate
from app.services.generation.four_stage_spec_builder import GenerationSpecBuilder
from app.services.generation.image_batch import generate_accepted_image_batch
from app.services.storage.four_stage_store import FourStageStore


def _run_with_decision() -> FourStageRun:
    return FourStageRun(
        run_id="run_gen",
        session_id="sess_gen",
        source_event_ids=["evt_1"],
        stage=FourStageStage.awaiting_gate,
        intent_ir=IntentIR(
            ir_id="ir_gen",
            run_id="run_gen",
            session_id="sess_gen",
            source_event_ids=["evt_1"],
            target=IntentTarget(part_id="lid_knob", object_type="teapot"),
            observations=IntentObservations(text="make the lid knob more organic"),
            intent=IntentCore(
                operation="explore_variations",
                scope="part",
                goal="organic lid knob",
                constraints=["preserve socket"],
                preferred_axes=["Aesthetic", "Structural"],
            ),
        ),
        decision=DecisionIR(
            decision_id="decision_gen",
            run_id="run_gen",
            intent_ir_id="ir_gen",
            options=[
                DecisionOption(
                    option_id="opt_1",
                    label="Organic gourd-like knob",
                    rationale="soft",
                    confidence=0.8,
                    constraints=["preserve socket"],
                    divergence_seeds=["gourd shoulder", "soft taper"],
                )
            ],
        ),
        divergence_selection=DivergenceSelection(
            selected_candidate_ids=["cand_curled_brim", "cand_soft_socket"],
            selected_keywords=["卷曲帽檐", "柔和插接"],
            resolved_prompt_phrases=[
                "curl only the hat brim into a smooth outward roll",
                "soften only the lid knob socket transition",
            ],
        ),
    )


def test_spec_builder_writes_constraints_into_every_prompt() -> None:
    run = _run_with_decision()
    spec = GenerationSpecBuilder(candidate_count=4).build_spec(run, "opt_1")
    assert spec.selected_option_id == "opt_1"
    assert spec.run_id == "run_gen"
    assert len(spec.prompt_candidates) == 4
    assert len(spec.seeds) == 4
    assert "preserve socket" in spec.preserved_constraints
    for prompt in spec.prompt_candidates:
        assert "preserve socket" in prompt.lower()
    axes = [prompt.split(" — ")[-1].split(";")[0].strip() for prompt in spec.prompt_candidates]
    assert len(set(axes)) >= 2
    assert spec.target.part_id == "lid_knob"
    for prompt in spec.prompt_candidates:
        normalized = prompt.lower()
        assert "change only lid_knob" in normalized
        assert "preserve every non-target part" in normalized
        assert "change the overall silhouette" not in normalized
        assert "change the material appearance" not in normalized

    # Reproducible seeds for the same run/option.
    again = GenerationSpecBuilder(candidate_count=4).build_spec(run, "opt_1")
    assert again.seeds == spec.seeds
    assert again.generation_id == spec.generation_id


def test_spec_builder_requires_white_background_complete_single_object() -> None:
    spec = GenerationSpecBuilder(candidate_count=4).build_spec(
        _run_with_decision(),
        "opt_1",
    )

    assert spec.require_white_background is True
    assert spec.require_single_object is True
    assert spec.require_full_object is True
    for prompt in spec.prompt_candidates:
        normalized = prompt.lower()
        assert "pure white rgb(255,255,255) background" in normalized
        assert "one complete object only" in normalized
        assert "no crop" in normalized


def test_hy3d_artifact_paths_accept_current_worker_item_schema() -> None:
    summary = {
        "items": [
            {
                "mesh_pbr_glb": "/runs/candidate/mesh_pbr.glb",
                "mesh_pbr_obj": "/runs/candidate/mesh_pbr.obj",
                "multiview_grid": "/runs/candidate/multiview_grid.png",
            }
        ]
    }

    assert _hy3d_artifact_paths(summary) == (
        "/runs/candidate/mesh_pbr.glb",
        "/runs/candidate/mesh_pbr.obj",
        "/runs/candidate/multiview_grid.png",
    )


def test_hy3d_job_payload_returns_mesh_when_completed() -> None:
    payload = _hy3d_job_payload(
        {
            "status": "completed",
            "message": "done",
            "result": {
                "result_json": {
                    "items": [{"ok": True, "mesh_pbr_glb": "/runs/m.glb", "mesh_pbr_obj": "/runs/m.obj"}],
                }
            },
        },
        "rw_done",
    )
    assert payload["status"] == "completed"
    assert payload["remote_job_id"] == "rw_done"
    assert payload["mesh_url"]
    assert payload["obj_url"]


def test_image_batch_retries_rejections_and_returns_only_accepted_artifacts() -> None:
    attempts: list[tuple[int, int]] = []

    async def generate(index: int, prompt: str, seed: int, attempt: int):
        attempts.append((index, attempt))
        if index == 0 and attempt == 0:
            return None
        if index == 1:
            return None
        return {"candidate_id": f"candidate_{index}", "url": f"/{index}.png"}

    artifacts = asyncio.run(
        generate_accepted_image_batch(
            ["a", "b", "c"],
            [10, 20, 30],
            generate_attempt=generate,
            minimum_accepted=2,
            max_attempts_per_prompt=2,
        )
    )

    assert [item["candidate_id"] for item in artifacts] == ["candidate_0", "candidate_2"]
    assert attempts == [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0)]


def test_image_batch_fails_when_minimum_quality_count_is_not_met() -> None:
    async def reject_all(index: int, prompt: str, seed: int, attempt: int):
        return None

    with pytest.raises(RuntimeError, match="accepted image count 0 is below required 2"):
        asyncio.run(
            generate_accepted_image_batch(
                ["a", "b"],
                [10, 20],
                generate_attempt=reject_all,
                minimum_accepted=2,
                max_attempts_per_prompt=1,
            )
        )


def test_spec_builder_propagates_run_hy3d() -> None:
    run = _run_with_decision()
    run.run_hy3d = True
    spec = GenerationSpecBuilder().build_spec(run, "opt_1")
    assert spec.run_hy3d is True
    run.run_hy3d = False
    assert GenerationSpecBuilder().build_spec(run, "opt_1").run_hy3d is False


def test_material_spec_opens_appearance_but_locks_white_model_geometry() -> None:
    run = _run_with_decision()
    assert run.intent_ir is not None
    run.intent_ir.intent.scope = "material"
    run.intent_ir.target.part_id = None
    spec = GenerationSpecBuilder(candidate_count=4).build_spec(run, "opt_1")

    assert spec.target.scope == "material"
    assert "allow color and material appearance to change visibly" in spec.preserved_constraints
    assert len(set(spec.prompt_candidates)) == 4
    for prompt in spec.prompt_candidates:
        normalized = prompt.lower()
        assert "part-aware semantic material transfer" in normalized
        assert "preserving exact geometry" in normalized
        assert "preserve category-defining semantic features and part roles" in normalized
        assert "never coat every part with one uniform donor material" in normalized
        assert "change the overall silhouette" not in normalized
        assert "change the internal structure" not in normalized

    result = GenerationQualityGate().evaluate(
        spec,
        [{"url": "http://files/material.png", "candidate_id": "material_1"}],
    )
    check = next(item for item in result.checks if item["name"] == "material_geometry_lock")
    assert check["passed"] is True


def test_scenario_profiles_separate_narrative_and_product_structure_invariants() -> None:
    narrative = _run_with_decision()
    assert narrative.intent_ir is not None
    narrative.intent_ir.target.object_type = "frog character"
    narrative.intent_ir.target.part_id = None
    narrative.intent_ir.intent.scope = "whole"
    narrative.intent_ir.intent.operation = "semantic_transfer"
    narrative.intent_ir.intent.goal = "turn the same character into an ancient stone relic"
    narrative.divergence_selection = DivergenceSelection(
        selected_candidate_ids=["narrative_weathered", "narrative_moss"],
        selected_keywords=["weathered basalt", "moss-covered relic"],
        resolved_prompt_phrases=[
            "transfer the character into weathered basalt",
            "add age-consistent moss to the same stone character",
        ],
        dimensions={"Scenario": ["narrative_character"]},
    )
    narrative_spec = GenerationSpecBuilder(candidate_count=4).build_spec(narrative, "opt_1")
    assert all("Change the overall silhouette" in prompt or "Change the material appearance" in prompt or "Change the internal structure" in prompt or "Add ornament" in prompt for prompt in narrative_spec.prompt_candidates)
    assert all("do not replace the source character" in prompt for prompt in narrative_spec.prompt_candidates)
    assert all("Front-facing studio view" in prompt for prompt in narrative_spec.prompt_candidates)
    assert narrative_spec.model == "gpt-image-2"

    narrative.intent_ir.intent.scope = "material"
    narrative_material_spec = GenerationSpecBuilder(candidate_count=4).build_spec(narrative, "opt_1")
    narrative_quality = GenerationQualityGate().evaluate(
        narrative_material_spec,
        [{"url": "/files/frog.png", "candidate_id": "frog_1"}],
    )
    assert narrative_quality.passed is True

    structure = _run_with_decision()
    assert structure.intent_ir is not None
    structure.intent_ir.target.object_type = "coffee table"
    structure.intent_ir.target.part_id = None
    structure.intent_ir.intent.scope = "whole"
    structure.intent_ir.intent.operation = "structure_transfer"
    structure.intent_ir.intent.goal = "reshape the table with flowing lava supports"
    structure.divergence_selection = DivergenceSelection(
        selected_candidate_ids=["structure_lava", "structure_crust"],
        selected_keywords=["flowing lava", "cooled crust"],
        resolved_prompt_phrases=[
            "translate the support structure into flowing lava",
            "form cooled crust around the same load-bearing table structure",
        ],
        dimensions={"Scenario": ["product_structure"]},
    )
    structure_spec = GenerationSpecBuilder(candidate_count=4).build_spec(structure, "opt_1")
    assert all("USER-SELECTED DIRECTION:" in prompt for prompt in structure_spec.prompt_candidates)
    assert all("horizontal usable tabletop" in prompt for prompt in structure_spec.prompt_candidates)
    assert all("texture-only recoloring is insufficient" in prompt for prompt in structure_spec.prompt_candidates)


def test_trusted_intent_context_derives_narrative_scenario_after_canonical_selection() -> None:
    run = _run_with_decision()
    assert run.intent_ir is not None
    run.intent_ir.target.object_type = "frog character"
    run.intent_ir.target.part_id = None
    run.intent_ir.intent.scope = "whole"
    run.intent_ir.intent.operation = "semantic_transfer"
    run.intent_ir.intent.goal = "turn the same character into an ancient stone statue"
    run.divergence_selection = DivergenceSelection(
        selected_candidate_ids=["canonical_stone"],
        selected_keywords=["风化石雕"],
        resolved_prompt_phrases=["transfer the same frog character into weathered carved stone"],
        dimensions={"semantic_transfer": ["风化石雕"]},
    )

    spec = GenerationSpecBuilder(candidate_count=4).build_spec(run, "opt_1")

    assert all("USER-SELECTED DIRECTION:" in prompt for prompt in spec.prompt_candidates)
    assert all("do not replace the source character" in prompt for prompt in spec.prompt_candidates)
    assert all("preserve category-defining facial and limb cues" in prompt for prompt in spec.prompt_candidates)
    assert all("Front-facing studio view" in prompt for prompt in spec.prompt_candidates)


def test_trusted_intent_context_derives_product_structure_after_canonical_selection() -> None:
    run = _run_with_decision()
    assert run.intent_ir is not None
    run.intent_ir.target.object_type = "coffee table"
    run.intent_ir.target.part_id = None
    run.intent_ir.intent.scope = "whole"
    run.intent_ir.intent.operation = "structure_transfer"
    run.intent_ir.intent.goal = "reshape the table as a flowing molten lava structure"
    run.divergence_selection = DivergenceSelection(
        selected_candidate_ids=["canonical_lava"],
        selected_keywords=["熔岩支撑"],
        resolved_prompt_phrases=["translate the table supports into a flowing molten load-bearing system"],
        dimensions={"shape": ["熔岩支撑"]},
    )

    spec = GenerationSpecBuilder(candidate_count=4).build_spec(run, "opt_1")

    assert all("USER-SELECTED DIRECTION:" in prompt for prompt in spec.prompt_candidates)
    assert all("horizontal usable tabletop" in prompt for prompt in spec.prompt_candidates)
    assert all("plausible load-bearing support system" in prompt for prompt in spec.prompt_candidates)
    assert all("Front-facing studio view" in prompt for prompt in spec.prompt_candidates)


@pytest.mark.parametrize(
    ("object_type", "goal"),
    [
        ("tablet stand", "reshape it with a flowing edge structure"),
        ("turntable", "reshape it with flowing supports"),
        ("catering cart", "turn it into an ancient stone statue relic"),
        ("几何体", "将它重塑为流动的支撑结构"),
    ],
)
def test_scenario_identity_matching_does_not_use_unsafe_substrings(
    object_type: str,
    goal: str,
) -> None:
    run = _run_with_decision()
    assert run.intent_ir is not None
    run.intent_ir.target.object_type = object_type
    run.intent_ir.target.part_id = None
    run.intent_ir.intent.scope = "whole"
    run.intent_ir.intent.goal = goal

    spec = GenerationSpecBuilder(candidate_count=2).build_spec(run, "opt_1")

    assert all("Narrative transfer" not in prompt for prompt in spec.prompt_candidates)
    assert all("Structure transfer" not in prompt for prompt in spec.prompt_candidates)
    assert all("plausible load-bearing support system" not in prompt for prompt in spec.prompt_candidates)


@pytest.mark.parametrize(
    ("object_type", "goal", "required"),
    [
        ("snowman character", "turn it into an ancient stone relic", "do not replace the source character"),
        ("茶几", "将茶几的支撑改为流动熔岩结构", "horizontal usable tabletop"),
    ],
)
def test_scenario_identity_matching_preserves_explicit_aliases(
    object_type: str,
    goal: str,
    required: str,
) -> None:
    run = _run_with_decision()
    assert run.intent_ir is not None
    run.intent_ir.target.object_type = object_type
    run.intent_ir.target.part_id = None
    run.intent_ir.intent.scope = "whole"
    run.intent_ir.intent.goal = goal

    spec = GenerationSpecBuilder(candidate_count=2).build_spec(run, "opt_1")

    assert all(required in prompt for prompt in spec.prompt_candidates)
    assert all("Front-facing studio view" in prompt for prompt in spec.prompt_candidates)
    assert all("USER-SELECTED DIRECTION:" in prompt for prompt in spec.prompt_candidates)


def test_each_candidate_uses_one_user_direction_without_cross_contamination() -> None:
    run = _run_with_decision()
    run.divergence_selection = DivergenceSelection(
        selected_candidate_ids=["c1", "c2", "c3", "c4"],
        selected_keywords=["woven rattan", "frosted polymer", "brushed aluminum", "warm cork"],
        resolved_prompt_phrases=[
            "apply woven rattan only to the selected semantic region",
            "apply frosted polymer only to the selected semantic region",
            "apply brushed aluminum only to the selected semantic region",
            "apply warm cork only to the selected semantic region",
        ],
    )
    spec = GenerationSpecBuilder(candidate_count=4).build_spec(run, "opt_1")
    for index, expected in enumerate(run.divergence_selection.resolved_prompt_phrases):
        prompt = spec.prompt_candidates[index]
        assert f"USER-SELECTED DIRECTION: {expected}" in prompt
        assert all(other not in prompt for other in run.divergence_selection.resolved_prompt_phrases if other != expected)


def test_eight_prompts_round_robin_two_full_phrases_without_taxonomy_or_planner_seeds() -> None:
    run = _run_with_decision()
    assert run.intent_ir is not None and run.decision is not None
    run.intent_ir.intent.preferred_axes = ["Aesthetic", "Structural"]
    run.decision.options[0].divergence_seeds = ["planner silhouette seed"]
    run.divergence_selection = DivergenceSelection(
        selected_candidate_ids=["c1", "c2"],
        selected_keywords=["卷曲帽檐", "柔和插接"],
        resolved_prompt_phrases=[
            "curl only the hat brim into a smooth outward roll",
            "soften only the lid knob socket transition",
        ],
    )

    spec = GenerationSpecBuilder(candidate_count=8).build_spec(run, "opt_1")

    assert spec.keywords == ["卷曲帽檐", "柔和插接"]
    assert spec.selected_keywords == ["卷曲帽檐", "柔和插接"]
    for index, prompt in enumerate(spec.prompt_candidates):
        expected = run.divergence_selection.resolved_prompt_phrases[index % 2]
        other = run.divergence_selection.resolved_prompt_phrases[(index + 1) % 2]
        normalized = prompt.lower()
        assert expected in prompt
        assert other not in prompt
        assert "aesthetic" not in normalized
        assert "planner silhouette seed" not in normalized
        assert "preserve teapot identity" in normalized
        assert "change only lid_knob" in normalized
        assert "one complete object only" in normalized
        assert "pure white rgb(255,255,255) background" in normalized


def test_spec_builder_rejects_missing_explicit_candidate_selection_and_never_uses_seeds() -> None:
    run = _run_with_decision()
    assert run.decision is not None
    run.divergence_selection = None
    run.decision.options[0].divergence_seeds = ["forbidden seed fallback"]

    with pytest.raises(ValueError, match="explicit semantic divergence candidate selection"):
        GenerationSpecBuilder(candidate_count=8).build_spec(run, "opt_1")


def test_quality_gate_blocks_missing_artifacts_and_passes_valid() -> None:
    run = _run_with_decision()
    spec = GenerationSpecBuilder().build_spec(run, "opt_1")
    gate = GenerationQualityGate()
    assert gate.evaluate(spec, []).passed is False
    result = gate.evaluate(
        spec,
        [
            {"url": "http://files/gen_1.png", "candidate_id": "c1"},
            {"url": "http://files/gen_2.png", "candidate_id": "c2"},
        ],
    )
    assert result.passed is True
    names = {check["name"] for check in result.checks}
    assert {"artifacts_non_empty", "constraints_preserved_in_prompts"} <= names


async def _immediate_poll(remote_job_id: str) -> dict:
    return {
        "status": "completed",
        "artifacts": [{"url": f"http://files/{remote_job_id}_1.png", "candidate_id": "c1"}],
    }


def test_generation_job_completes_run_and_records_artifacts() -> None:
    store = FourStageStore()
    orchestrator = _FakeOrchestrator(store)

    async def dispatch(run, spec):
        return {"remote_job_id": f"remote_{run.run_id}"}

    service = FourStageGenerationService(
        store,
        dispatch=dispatch,
        poll=_immediate_poll,
        lock=asyncio.Lock(),
    )
    service.set_completion_callbacks(
        on_complete=orchestrator.finalize,
        on_failed=orchestrator.fail,
    )

    async def scenario() -> None:
        run = _run_with_decision()
        run.stage = FourStageStage.generation
        run.generation_spec = GenerationSpecBuilder().build_spec(run, "opt_1")
        store.save_run(run)
        result = await service.start_generation(run, run.generation_spec)
        assert result["status"] == "queued"
        # wait for the background job
        for _ in range(100):
            if store.get_run(run.run_id).stage == FourStageStage.completed:
                break
            await asyncio.sleep(0.01)
        finished = store.get_run(run.run_id)
        assert finished.stage == FourStageStage.completed
        assert finished.generation_artifacts
        job = store.get_generation_job(result["job_id"])
        assert job["status"] == "completed"

    asyncio.run(scenario())


def test_generation_failure_marks_run_failed_retryable() -> None:
    store = FourStageStore()
    orchestrator = _FakeOrchestrator(store)

    async def dispatch(run, spec):
        return {"remote_job_id": "remote_fail"}

    async def failing_poll(remote_job_id: str) -> dict:
        return {"status": "failed", "error": {"code": "remote_broken"}}

    service = FourStageGenerationService(
        store,
        dispatch=dispatch,
        poll=failing_poll,
        lock=asyncio.Lock(),
    )
    service.set_completion_callbacks(
        on_complete=orchestrator.finalize,
        on_failed=orchestrator.fail,
    )

    async def scenario() -> None:
        run = _run_with_decision()
        run.stage = FourStageStage.generation
        run.generation_spec = GenerationSpecBuilder().build_spec(run, "opt_1")
        store.save_run(run)
        result = await service.start_generation(run, run.generation_spec)
        for _ in range(100):
            if store.get_run(run.run_id).stage == FourStageStage.failed:
                break
            await asyncio.sleep(0.01)
        finished = store.get_run(run.run_id)
        assert finished.stage == FourStageStage.failed
        assert finished.error["retryable"] is True
        job = store.get_generation_job(result["job_id"])
        assert job["status"] == "failed"

    asyncio.run(scenario())


def test_gpu_lock_serializes_generation_jobs() -> None:
    store = FourStageStore()
    order: list[str] = []

    async def slow_dispatch(run, spec):
        order.append(f"start:{run.run_id}")
        await asyncio.sleep(0.03)
        order.append(f"end:{run.run_id}")
        return {"remote_job_id": f"remote_{run.run_id}"}

    service = FourStageGenerationService(
        store,
        dispatch=slow_dispatch,
        poll=_immediate_poll,
        lock=asyncio.Lock(),
    )

    async def scenario() -> None:
        runs = [_run_with_decision() for _ in range(2)]
        for index, run in enumerate(runs):
            run.run_id = f"run_gen_{index}"
            run.stage = FourStageStage.generation
            run.generation_spec = GenerationSpecBuilder().build_spec(run, "opt_1")
            store.save_generation_job(
                {
                    "job_id": f"genjob_{index}",
                    "run_id": run.run_id,
                    "session_id": run.session_id,
                    "spec": run.generation_spec.model_dump(mode="json"),
                    "status": "queued",
                }
            )
        await asyncio.gather(
            *[
                service._run_job(run, run.generation_spec, f"genjob_{index}")
                for index, run in enumerate(runs)
            ]
        )

    asyncio.run(scenario())
    assert order == [
        "start:run_gen_0",
        "end:run_gen_0",
        "start:run_gen_1",
        "end:run_gen_1",
    ]


def test_recover_pending_jobs_requeues_and_redispatches() -> None:
    store = FourStageStore()
    run = _run_with_decision()
    run.stage = FourStageStage.generation
    run.generation_spec = GenerationSpecBuilder().build_spec(run, "opt_1")
    store.save_run(run)
    store.save_generation_job(
        {
            "job_id": "genjob_running",
            "run_id": run.run_id,
            "session_id": run.session_id,
            "spec": run.generation_spec.model_dump(mode="json"),
            "status": "running",
            "lease_expires_at": "2000-01-01T00:00:00+00:00",
        }
    )
    store.save_generation_job(
        {
            "job_id": "genjob_completed",
            "run_id": "run_c",
            "session_id": "sess_c",
            "spec": {"generation_id": "gen_2"},
            "status": "completed",
        }
    )

    async def dispatch(run, spec):
        return {
            "remote_job_id": "remote_rec",
            "artifacts": [{"url": "/files/x.png", "candidate_id": "c1"}],
        }

    async def poll(remote_job_id):
        return {"status": "running"}

    service = FourStageGenerationService(store, dispatch=dispatch, poll=poll)

    async def on_complete(run_id: str, artifacts: list[dict]) -> None:
        finished = store.get_run(run_id)
        finished.stage = FourStageStage.completed
        finished.generation_artifacts = artifacts
        store.save_run(finished)

    async def on_failed(run_id: str, error: Exception) -> None:
        failed_run = store.get_run(run_id)
        failed_run.stage = FourStageStage.failed
        failed_run.error = {"code": "generation_failed", "message": str(error)}
        store.save_run(failed_run)

    service.set_completion_callbacks(on_complete=on_complete, on_failed=on_failed)
    recovered = service.recover_pending_jobs()
    assert recovered == 1
    job = store.get_generation_job("genjob_running")
    assert job["status"] == "completed"
    assert job["artifacts"] == [{"url": "/files/x.png", "candidate_id": "c1"}]
    assert store.get_generation_job("genjob_completed")["status"] == "completed"
    assert store.get_run(run.run_id).stage == FourStageStage.completed


def test_real_dispatch_builds_generation_request(monkeypatch) -> None:
    from app.main import _four_stage_dispatch

    async def fake_images(spec, *, session_id=None, run_id=None):
        return [
            {
                "candidate_id": "c1",
                "url": "/files/four_stage/x/candidate_01.png",
                "prompt": "p",
                "seed": 1,
            }
        ]

    monkeypatch.setattr("app.main._four_stage_generate_images", fake_images)
    run = _run_with_decision()
    run.stage = FourStageStage.generation
    spec = GenerationSpecBuilder().build_spec(run, "opt_1")
    result = asyncio.run(_four_stage_dispatch(run, spec))
    assert result["remote_job_id"].startswith("direct_")
    assert result["artifacts"][0]["url"].startswith("/files/")


def test_dispatch_rejects_run_hy3d_when_3d_runtime_is_disabled(monkeypatch) -> None:
    from app.main import _four_stage_dispatch
    from app.services.generation.generation_orchestrator import ThreeDGenerationDisabled

    calls = {"images": 0, "hy3d": 0}

    async def fake_images(spec, *, session_id=None, run_id=None):
        calls["images"] += 1
        return [{"url": "/files/i.png", "candidate_id": "c1"}]

    async def fake_hy3d(run, spec):
        calls["hy3d"] += 1
        return [{"url": "/files/m.glb", "candidate_id": "c1", "kind": "mesh_glb"}]

    monkeypatch.setattr("app.main._four_stage_generate_images", fake_images)
    monkeypatch.setattr("app.main._four_stage_dispatch_hy3d", fake_hy3d)
    run = _run_with_decision()
    run.stage = FourStageStage.generation
    spec = GenerationSpecBuilder().build_spec(run, "opt_1")
    asyncio.run(_four_stage_dispatch(run, spec))
    assert calls["images"] == 1
    assert calls["hy3d"] == 0

    run.run_hy3d = True
    spec3d = GenerationSpecBuilder().build_spec(run, "opt_1")
    with pytest.raises(ThreeDGenerationDisabled) as error:
        asyncio.run(_four_stage_dispatch(run, spec3d))
    assert error.value.code == "3D_GENERATION_DISABLED"
    assert calls["hy3d"] == 0


def test_qwen_image_client_generate_payload(monkeypatch) -> None:
    import json

    from app.services.generation.qwen_image_client import QwenImageClient

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"\x89PNG fake"

    def fake_open(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    client = QwenImageClient("http://127.0.0.1:18082")
    monkeypatch.setattr(client, "_open", fake_open)
    data = asyncio.run(client.generate("organic knob", seed=42))
    assert data == b"\x89PNG fake"
    assert captured["payload"]["prompt"] == "organic knob"
    assert captured["payload"]["seed"] == 42
    assert captured["payload"]["width"] == 512
    assert captured["payload"]["steps"] == 4


class _FakeOrchestrator:
    def __init__(self, store: FourStageStore) -> None:
        self.store = store

    async def finalize(self, run_id: str, artifacts: list[dict]) -> None:
        run = self.store.get_run(run_id)
        run.stage = FourStageStage.completed
        run.generation_artifacts = artifacts
        self.store.save_run(run)

    async def fail(self, run_id: str, error: Exception) -> None:
        run = self.store.get_run(run_id)
        run.stage = FourStageStage.failed
        run.error = {"code": "generation_failed", "message": str(error), "retryable": True}
        self.store.save_run(run)
