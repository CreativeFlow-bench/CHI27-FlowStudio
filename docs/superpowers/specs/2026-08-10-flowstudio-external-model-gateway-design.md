# FlowStudio External Model Gateway Design

**Date:** 2026-08-10

**Status:** Approved for local implementation

## Goal

Replace every model request on the FlowStudio product runtime path with an external API request. Use Gemini and GPT-5.5 for text, multimodal understanding, structured reasoning, and prompt composition; use GPT Image 2 for candidate image generation and editing. Keep the previous Qwen, DeepSeek, and local VLM adapters as disabled rollback code. Do not run or extend any 3D/Hunyuan path in this phase.

All implementation, testing, and runtime changes in this phase are local-only. The GPU source and services are not modified.

## Baseline and source ownership

The local `backend/`, `frontend/`, `remote_worker/`, and `scripts/` trees were synchronized from `/root/flowstudio_app` on the GPU before this design was finalized. Content-level rsync verification reported no source differences for the synchronized set. The pre-sync local Git state and source archive are stored under `.flowstudio-run/local-source-backups/20260810-110930`.

The local repository is now the only implementation workspace. A later GPU deployment requires a separate explicit user request and a fresh diff review.

## Scope

This phase changes product-runtime model calls used by:

- intent and interaction encoding;
- Perception and multimodal interpretation;
- four-stage re-representation;
- semantic divergence;
- complex decision and prompt composition;
- candidate image generation;
- reference-image editing and mask-guided editing.

Offline research files, historical outputs, model weights, 3D pipelines, Hunyuan scripts, OSS publication, and case-library publication are not changed.

## Model routing

| Runtime stage | Primary model | External fallback | Output contract |
| --- | --- | --- | --- |
| Intent encoding and fast multimodal interpretation | `gemini-3.6-flash` | `gpt-5.5` | Validated `IntentIR` JSON |
| Perception summaries and lightweight structured classification | `gemini-3.6-flash` | `gpt-5.5` | Existing typed JSON or bounded text contract |
| Four-stage re-representation and decision | `gpt-5.5` | `gemini-3.6-flash` | Validated `DecisionIR` JSON |
| Semantic divergence | `gpt-5.5` | `gemini-3.6-flash` | Validated semantic-candidate JSON |
| Prompt composition and complex planning | `gpt-5.5` | `gemini-3.6-flash` | Existing prompt/plan schema |
| Candidate image generation and editing | `gpt-image-2` | None | PNG bytes plus request metadata |

Fallback is external-API-only. A timeout, rate limit, server failure, schema failure, or missing model must never silently invoke Qwen, DeepSeek, a local VLM, or a local image model.

## Architecture

Create one model boundary under `backend/app/services/model_api/`:

- `config.py` resolves neutral model settings and backward-compatible environment aliases.
- `transport.py` owns authentication, timeouts, retryable status handling, request IDs, safe audit metadata, and OpenAI-compatible JSON transport.
- `text_gateway.py` routes typed text and multimodal requests by runtime stage and validates provider responses before returning them to existing domain services.
- `image_gateway.py` calls GPT Image 2 and returns decoded PNG bytes.
- `types.py` defines stage names, provider/model selections, request metadata, and normalized gateway exceptions.

Existing domain services remain responsible for prompts and Pydantic validation. They depend on the gateway transport instead of opening HTTP connections independently. This keeps domain behavior testable without binding it to a provider.

The first implementation uses the existing OpenAI-compatible API base and key. Text requests use the compatible chat-completions JSON contract already supported by the current code and relay. The transport boundary keeps the protocol isolated so a future direct Responses API migration does not change domain services.

## Configuration

Add these neutral settings:

- `MODEL_API_BASE`
- `MODEL_API_KEY`
- `MODEL_FAST_TEXT=gemini-3.6-flash`
- `MODEL_REASONING_TEXT=gpt-5.5`
- `MODEL_IMAGE=gpt-image-2`
- `MODEL_API_TIMEOUT_SEC`
- `ENABLE_LEGACY_LOCAL_MODELS=false`
- `ENABLE_3D_GENERATION=false`

For backward compatibility, `MODEL_API_BASE` and `MODEL_API_KEY` fall back to the existing `GEMINI_API_BASE` and `GEMINI_API_KEY` values when the neutral variables are absent. Secrets remain only in the local `.env`; they are never copied from the GPU, committed, logged, or included in test artifacts.

Startup preflight checks the configured model catalog when the relay provides `/models`. The application reports unavailable model access explicitly instead of changing model IDs automatically.

## Legacy rollback adapters

The existing Qwen, DeepSeek, local VLM, and Qwen-Image classes remain in the repository. Product startup must not instantiate or probe them unless `ENABLE_LEGACY_LOCAL_MODELS=true` is set explicitly.

The default and documented local configuration keep this flag `false`. Tests patch every legacy transport with a fail-fast sentinel and prove that normal startup, text generation, image generation, and external fallback do not touch those transports.

System-service status must describe legacy GPU services as optional and disabled. It must not mark Qwen planner or Qwen Image as required for the external-model runtime profile.

## GPT Image 2 flow

The current four-stage product path requires a source identity image. Whole-object changes call `POST /images/edits` with the source image and prompt. Part or region changes call the same endpoint with the source image, prompt, and mask.

Before a masked request, the gateway verifies that source and mask are PNG files with equal dimensions and converts the mask to an alpha-bearing RGBA PNG when necessary. Invalid files fail locally with a structured error before a paid API request.

An explicit text-only generation path may call `POST /images/generations`. It is not used as an implicit fallback when a required source identity image is missing.

The gateway decodes `data[0].b64_json`, validates the PNG signature and bounded size, and returns bytes to the existing artifact persistence and Solution Space flow. Prompts, seeds, selected semantic direction, provider request ID, latency, and output path are recorded; keys and raw image bodies are not logged.

## 3D and Hunyuan guard

This phase does not remove historical 3D code. It prevents runtime entry:

- `ENABLE_3D_GENERATION=false` is the local default;
- `REMOTE_CREATIVEFLOW_AUTO_HY3D=false` remains set;
- image-phase payloads set `run_hy3d=false` explicitly;
- local tests fail if `/jobs/hy3d`, `/jobs/hy3d-from-staged`, a mesh worker, or a Hunyuan subprocess is invoked.

A user request for 3D while the guard is disabled returns a structured `3D_GENERATION_DISABLED` error. Image completion is not labelled as completion of the full CreativeFlow 3D pipeline.

## Error handling

Transport retries are bounded and apply only to timeouts, connection failures, HTTP 429, and HTTP 5xx responses. Invalid authentication, unsupported model IDs, invalid request payloads, and schema-invalid outputs are surfaced without repeated paid calls, except for the existing single bounded JSON repair round.

Every gateway error includes stage, provider, model, retryability, and a safe message. It excludes credentials, full image data, and provider response bodies that may contain sensitive input.

If both configured text APIs fail, the domain service uses its existing deterministic rule behavior only where that behavior is already part of the product contract. It may not invoke a legacy model and may not fabricate a successful model result.

## Local development topology

- Local backend: `http://127.0.0.1:18001`
- Local frontend: `http://127.0.0.1:5184`
- Frontend API/WS configuration points to port `18001` for this development profile.
- External model traffic leaves only from the local backend through the configured API base.
- GPU tunnels and GPU worker services are not required for text/image development after the gateway is active.

The frontend can be started before the gateway implementation to support incremental visual review. Generation actions remain disabled or return an explicit unavailable result until the corresponding local backend adapter is green.

## Testing and acceptance

Implementation follows red-green TDD and adds tests for:

1. configuration precedence and secret redaction;
2. stage-to-model routing;
3. Gemini-primary and GPT-primary external fallback;
4. structured JSON extraction, validation, and one repair round;
5. retry classification and bounded retry counts;
6. legacy transport non-invocation under the default profile;
7. GPT Image 2 generation and edit multipart payloads;
8. source/mask dimension and alpha validation;
9. PNG response decoding and size bounds;
10. Hunyuan/mesh endpoint non-invocation;
11. current backend and frontend regression suites;
12. local browser startup without an initialization stall.

After unit and integration tests pass, run a paid live probe with the existing key in this order:

1. list or preflight the configured model IDs without logging credentials;
2. one small structured Gemini request;
3. one small structured GPT-5.5 request;
4. one GPT Image 2 text generation;
5. one GPT Image 2 identity-preserving edit using an existing concrete snowman reference.

Live outputs go under `outputs/api_model_eval/<timestamp>/` with a redacted JSON manifest, latency, model IDs, prompts, and image files. No batch, Hunyuan, mesh, OSS upload, or website sync runs in this phase.

Acceptance requires valid typed text outputs, viewable PNG outputs, zero legacy-model calls, zero 3D calls, passing regression suites, and a locally opened frontend connected to the local backend.
