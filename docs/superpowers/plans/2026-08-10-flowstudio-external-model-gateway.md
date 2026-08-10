# FlowStudio External Model Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route every active FlowStudio text, multimodal, and image-model request through the configured external API—Gemini for fast/multimodal work, GPT-5.5 for reasoning and prompt work, and GPT Image 2 for images—while leaving legacy local/GPU adapters present but disabled and keeping all 3D generation inactive.

**Architecture:** Add one neutral `model_api` boundary that owns configuration, OpenAI-compatible HTTP transport, stage routing, retry/audit behavior, structured-output parsing, and GPT Image 2 multipart requests. Existing domain services continue to own prompts and Pydantic validation, but receive the shared gateway instead of constructing provider-specific transports. Startup builds only external clients by default; legacy local adapters and Hunyuan paths require explicit flags that remain false.

**Tech Stack:** Python 3.12, FastAPI, Pydantic Settings, standard-library `urllib`, Pillow, pytest, React/Vite/TypeScript.

---

## Task 1: Define the neutral runtime profile and hard-off feature guards

**Files:**
- Create: `backend/app/services/model_api/__init__.py`
- Create: `backend/app/services/model_api/config.py`
- Create: `backend/app/services/model_api/types.py`
- Modify: `backend/app/config.py`
- Modify: `.env.example`
- Test: `backend/tests/test_model_api_config.py`

- [ ] **Step 1: Write failing configuration tests**

Cover these contracts:

```python
def test_model_api_profile_prefers_neutral_env_names(monkeypatch): ...
def test_model_api_profile_falls_back_to_existing_gemini_credentials(monkeypatch): ...
def test_model_api_profile_defaults_legacy_and_3d_off(monkeypatch): ...
def test_stage_routes_match_approved_models(): ...
```

Assert `gemini-3.6-flash` for `intent`, `perception`, and other fast stages; `gpt-5.5` for `rerepresentation`, `semantic_divergence`, and `prompt_composition`; `gpt-image-2` for images. Verify `MODEL_API_BASE/KEY` override the compatibility `GEMINI_API_BASE/KEY`, and both `ENABLE_LEGACY_LOCAL_MODELS` and `ENABLE_3D_GENERATION` default to false.

- [ ] **Step 2: Run the focused test to verify RED**

Run: `PYTHONPATH=backend .flowstudio-run/py312-test-venv/bin/python -m pytest backend/tests/test_model_api_config.py -q`

Expected: FAIL because the neutral profile and stage types do not exist.

- [ ] **Step 3: Implement the smallest typed profile**

Add `ModelStage`, `ModelRoute`, and immutable `ModelApiProfile`. Resolve settings once from the existing `Settings` instance—never reread or mutate environment variables in request handlers. Keep old setting names for rollback compatibility, but make the neutral names authoritative.

```python
profile = ModelApiProfile.from_settings(settings)
route = profile.route_for(ModelStage.REREPRESENTATION)
assert route.primary_model == "gpt-5.5"
assert route.fallback_model == "gemini-3.6-flash"
```

- [ ] **Step 4: Run focused tests to verify GREEN**

Run the same pytest command; expected PASS.

- [ ] **Step 5: Commit only Task 1 files**

```bash
git add .env.example backend/app/config.py backend/app/services/model_api/__init__.py backend/app/services/model_api/config.py backend/app/services/model_api/types.py backend/tests/test_model_api_config.py
git commit -m "feat: define external model runtime profile"
```

## Task 2: Build the shared structured-text transport and stage gateway

**Files:**
- Create: `backend/app/services/model_api/transport.py`
- Create: `backend/app/services/model_api/text_gateway.py`
- Modify: `backend/app/services/model_api/__init__.py`
- Test: `backend/tests/test_model_api_text_gateway.py`

- [ ] **Step 1: Write failing transport and routing tests**

Use an injected fake opener—never the network—to prove:

```python
def test_fast_stage_uses_gemini_then_gpt_fallback(): ...
def test_reasoning_stage_uses_gpt_then_gemini_fallback(): ...
def test_retries_only_timeout_429_and_5xx(): ...
def test_extracts_json_from_chat_completion_and_fenced_content(): ...
def test_structured_call_performs_at_most_one_schema_repair(): ...
def test_audit_event_contains_no_key_or_image_bytes(): ...
```

- [ ] **Step 2: Run focused tests to verify RED**

Run: `PYTHONPATH=backend .flowstudio-run/py312-test-venv/bin/python -m pytest backend/tests/test_model_api_text_gateway.py -q`

- [ ] **Step 3: Implement the transport boundary**

`OpenAICompatibleTransport` owns `/chat/completions` and `/models`, Bearer auth, JSON decoding, timeouts, and bounded exponential backoff. Classify connection errors, timeouts, 429, and 5xx as retryable; treat other 4xx and invalid successful response bodies as terminal. Audit only request id, stage, model, latency, attempt, status/error type, and usage counts.

- [ ] **Step 4: Implement stage-aware structured calls**

`TextModelGateway.complete_json(stage, messages, validator, repair_instruction)` selects the route, attempts the primary provider, falls back only on transport/capability failure, and allows one schema-repair request on the active provider. Return a typed `StructuredModelResult` containing parsed value plus model/provider/audit metadata; never return a raw completion to domain code.

- [ ] **Step 5: Run focused tests to verify GREEN**

Run the Task 2 pytest command; expected PASS.

- [ ] **Step 6: Commit only Task 2 files**

```bash
git add backend/app/services/model_api backend/tests/test_model_api_text_gateway.py
git commit -m "feat: add structured external text gateway"
```

## Task 3: Route intent, rerepresentation, and semantic divergence through the gateway

**Files:**
- Modify: `backend/app/services/encoding/qwen_intent_encoder.py`
- Modify: `backend/app/services/rerepresentation/gemini_client.py`
- Modify: `backend/app/services/divergence/semantic_model_clients.py`
- Modify: `backend/app/services/divergence/semantic_divergence_service.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_four_stage_encoding.py`
- Test: `backend/tests/test_four_stage_rerepresentation.py`
- Test: `backend/tests/test_semantic_divergence_models.py`
- Create: `backend/tests/test_external_model_runtime_wiring.py`

- [ ] **Step 1: Add failing adapter and startup tests**

Prove the three existing domain contracts still return `IntentIR`, `DecisionIR`, and validated semantic candidates, while their model selection comes from `ModelStage`. Add a startup wiring test that monkeypatches legacy adapter constructors to raise and confirms default application construction never instantiates or probes them.

- [ ] **Step 2: Run focused tests to verify RED**

Run:

```bash
PYTHONPATH=backend .flowstudio-run/py312-test-venv/bin/python -m pytest \
  backend/tests/test_four_stage_encoding.py \
  backend/tests/test_four_stage_rerepresentation.py \
  backend/tests/test_semantic_divergence_models.py \
  backend/tests/test_external_model_runtime_wiring.py -q
```

- [ ] **Step 3: Adapt domain services without rewriting domain prompts**

Keep each service's prompt and Pydantic parsing logic. Replace private `urllib` calls with injected `TextModelGateway.complete_json(...)`. Rename public-facing exceptions only if necessary; retain import aliases for existing tests/callers. Existing `QwenIntentEncoder`, `GeminiClient`, and `LocalVlmSemanticGenerator` remain as rollback adapters, but default startup uses external gateway-backed adapters and does not construct local endpoints.

- [ ] **Step 4: Make fallback provider-to-provider, not API-to-local**

Fast stages route Gemini → GPT-5.5; reasoning stages route GPT-5.5 → Gemini. Rule-based non-model product behavior may remain where it is a deliberate domain fallback, but no failure may activate Qwen, DeepSeek, a localhost VLM, or a GPU process unless `ENABLE_LEGACY_LOCAL_MODELS=true` was explicitly set before startup.

- [ ] **Step 5: Run focused and adjacent regression tests**

Run the Step 2 command plus:

```bash
PYTHONPATH=backend .flowstudio-run/py312-test-venv/bin/python -m pytest \
  backend/tests/test_interaction_orchestration.py \
  backend/tests/test_semantic_divergence_service.py \
  backend/tests/test_realtime_observation.py -q
```

- [ ] **Step 6: Commit only Task 3 files**

```bash
git add backend/app/main.py backend/app/services/encoding/qwen_intent_encoder.py \
  backend/app/services/rerepresentation/gemini_client.py \
  backend/app/services/divergence/semantic_model_clients.py \
  backend/app/services/divergence/semantic_divergence_service.py \
  backend/tests/test_four_stage_encoding.py backend/tests/test_four_stage_rerepresentation.py \
  backend/tests/test_semantic_divergence_models.py backend/tests/test_external_model_runtime_wiring.py
git commit -m "feat: route FlowStudio text stages to external models"
```

## Task 4: Add GPT Image 2 generation and edit requests

**Files:**
- Create: `backend/app/services/model_api/image_gateway.py`
- Modify: `backend/app/services/model_api/__init__.py`
- Modify: `backend/app/services/generation/qwen_image_client.py`
- Modify: `backend/app/services/generation/four_stage_generation.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_model_api_image_gateway.py`
- Test: `backend/tests/test_four_stage_generation.py`

- [ ] **Step 1: Write failing image gateway tests**

Use tiny in-memory PNG fixtures and a fake transport to prove:

```python
def test_explicit_text_generation_posts_gpt_image_2_json(): ...
def test_whole_edit_posts_source_image_multipart(): ...
def test_region_edit_posts_source_and_alpha_mask_multipart(): ...
def test_mask_must_match_source_dimensions_and_have_alpha(): ...
def test_decodes_and_validates_b64_png_response(): ...
def test_product_conditioned_path_never_silently_becomes_text_only(): ...
```

- [ ] **Step 2: Run focused tests to verify RED**

Run: `PYTHONPATH=backend .flowstudio-run/py312-test-venv/bin/python -m pytest backend/tests/test_model_api_image_gateway.py backend/tests/test_four_stage_generation.py -q`

- [ ] **Step 3: Implement GPT Image 2 calls**

`ImageModelGateway.generate(prompt, ...)` posts `/images/generations`; `edit(prompt, source, mask=None, ...)` posts `/images/edits`. Use model `gpt-image-2`; omit unsupported `input_fidelity`; decode `data[0].b64_json`; require a valid non-empty PNG. Before masked edits, use Pillow to require equal dimensions and an alpha-bearing mask, converting a valid mask to RGBA without changing geometry.

- [ ] **Step 4: Replace the active Qwen image call site**

Keep `QwenImageClient` unchanged as rollback code. Introduce an external image adapter matching its async `generate` and `generate_conditioned` contract, and wire that adapter in `main.py`. For product edits, a missing source image is a structured error—not permission to call text-only generation.

- [ ] **Step 5: Run focused tests to verify GREEN**

Run the Step 2 command; expected PASS.

- [ ] **Step 6: Commit only Task 4 files**

```bash
git add backend/app/main.py backend/app/services/model_api backend/app/services/generation/qwen_image_client.py \
  backend/app/services/generation/four_stage_generation.py backend/tests/test_model_api_image_gateway.py \
  backend/tests/test_four_stage_generation.py
git commit -m "feat: route image generation to gpt image 2"
```

## Task 5: Prevent legacy GPU bootstrap and all 3D execution by default

**Files:**
- Modify: `backend/app/services/system_services.py`
- Modify: `backend/app/services/generation/generation_orchestrator.py`
- Modify: `backend/app/main.py`
- Modify: `scripts/dev_stack.sh`
- Test: `backend/tests/test_system_services.py`
- Test: `backend/tests/test_generation_orchestrator.py`
- Test: `backend/tests/test_external_model_runtime_wiring.py`

- [ ] **Step 1: Write failing hard-off tests**

Monkeypatch subprocess launch, remote-worker submission, and Hunyuan methods to raise. Confirm default startup/health/structured generation executes none of them. Confirm an attempted 3D request returns a stable `3D_GENERATION_DISABLED` result and does not enqueue a job.

- [ ] **Step 2: Run focused tests to verify RED**

Run:

```bash
PYTHONPATH=backend .flowstudio-run/py312-test-venv/bin/python -m pytest \
  backend/tests/test_system_services.py backend/tests/test_generation_orchestrator.py \
  backend/tests/test_external_model_runtime_wiring.py -q
```

- [ ] **Step 3: Guard service discovery and orchestration**

When legacy mode is false, `system_services` must not declare local planner/VLM/Qwen-image as required, probe their ports, or start subprocesses. When 3D is false, force `run_hy3d=false`, skip remote Hunyuan submission, and return the structured disabled status at the boundary. Update the local dev script so its default starts only backend/frontend; legacy services require an explicit opt-in flag.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run the Step 2 command; expected PASS.

- [ ] **Step 5: Commit only Task 5 files**

```bash
git add backend/app/main.py backend/app/services/system_services.py \
  backend/app/services/generation/generation_orchestrator.py scripts/dev_stack.sh \
  backend/tests/test_system_services.py backend/tests/test_generation_orchestrator.py \
  backend/tests/test_external_model_runtime_wiring.py
git commit -m "fix: keep legacy gpu and 3d runtime disabled"
```

## Task 6: Add safe API capability probes and local evaluation artifacts

**Files:**
- Create: `scripts/probe_model_api.py`
- Create: `backend/tests/test_probe_model_api.py`
- Modify: `.gitignore`
- Modify: `README.md`

- [ ] **Step 1: Write failing probe-script tests**

Test argument parsing, `--list-models`, `--text-only`, `--with-images`, output-directory creation, secret redaction, and the guarantee that no 3D/remote-worker function is imported or called. Network methods remain injected/faked in unit tests.

- [ ] **Step 2: Run focused tests to verify RED**

Run: `PYTHONPATH=backend .flowstudio-run/py312-test-venv/bin/python -m pytest backend/tests/test_probe_model_api.py -q`

- [ ] **Step 3: Implement the opt-in paid probe**

The script first lists models/capabilities, then—only when requested—runs one tiny structured Gemini call, one tiny structured GPT-5.5 call, one 1024px GPT Image 2 generation, and one identity-preserving edit. Write a redacted manifest, text JSON, and PNGs beneath `outputs/api_model_eval/<UTC timestamp>/`. Never write or print an API key.

- [ ] **Step 4: Document local-only startup and feature flags**

Document ports `18001`/`5184`, required neutral credential variables, compatibility fallback to the previous Gemini variables, paid-probe commands, disabled legacy/3D defaults, and the exact opt-in rollback flags.

- [ ] **Step 5: Run focused tests to verify GREEN**

Run the Step 2 command; expected PASS.

- [ ] **Step 6: Commit only Task 6 files**

```bash
git add .gitignore README.md scripts/probe_model_api.py backend/tests/test_probe_model_api.py
git commit -m "test: add external model capability probes"
```

## Task 7: Verify all regressions, live APIs, and the local frontend

**Files:**
- Modify only if verification reveals an in-scope defect.

- [ ] **Step 1: Run the complete local test and build matrix**

```bash
PYTHONPATH=backend .flowstudio-run/py312-test-venv/bin/python -m pytest backend/tests -q
node --experimental-strip-types --test frontend/tests/*.test.ts
frontend/node_modules/.bin/tsc -p frontend/tsconfig.json --noEmit
npm --prefix frontend run build
```

Expected: all commands exit 0.

- [ ] **Step 2: Restart only the local backend with the neutral profile**

Keep frontend on `127.0.0.1:5184`, restart backend on `127.0.0.1:18001`, and explicitly set the remote-worker URL empty, legacy models false, auto-bootstrap false, and 3D false. Confirm `/health`, application bootstrap, and WebSocket connection without any localhost model/GPU probes.

- [ ] **Step 3: Run model capability listing before paid calls**

```bash
PYTHONPATH=backend .flowstudio-run/py312-test-venv/bin/python scripts/probe_model_api.py --list-models
```

Require exact availability for the configured model ids. If a configured id is unavailable, stop paid probes and report the capability mismatch; do not silently substitute an unapproved model.

- [ ] **Step 4: Run the bounded live text and image probes**

```bash
PYTHONPATH=backend .flowstudio-run/py312-test-venv/bin/python scripts/probe_model_api.py --text-only
PYTHONPATH=backend .flowstudio-run/py312-test-venv/bin/python scripts/probe_model_api.py --with-images
```

Inspect saved JSON and PNGs. Confirm the edit preserves source identity and no remote/GPU/3D job was created.

- [ ] **Step 5: Browser-smoke the live local frontend**

At `http://127.0.0.1:5184/`, confirm initialization ends, Perception/AI Behavior/Composer render, a text interaction returns structured external-model output, image results render when invoked, and browser console/network contain no legacy-model, remote-worker, Hunyuan, or GPU endpoints.

- [ ] **Step 6: Record verification evidence and final status**

Report exact test counts, build exits, model-listing result, saved evaluation artifact directory, live probe outcomes, browser result, and any paid-call/provider limitation. Do not claim a provider path is working without a fresh successful call.
