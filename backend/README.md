# FlowStudio Backend

FastAPI backend prototype for FlowStudio.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Useful endpoints

- `GET /health`
- `GET /api/v1/remote-worker/health`
- `POST /api/v1/sessions`
- `POST /api/v1/assets`
- `POST /api/v1/assets/upload`
- `POST /api/v1/parts/discover`
- `POST /api/v1/generation/replace`
- `POST /api/v1/generation/drag`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/candidates/{candidate_id}`
- `WS /ws/sessions/{session_id}`
- `POST /api/v1/candidates`

## CreativeFlow integration

For the GPU worker bridge:

```bash
export REMOTE_CREATIVEFLOW_WORKER_URL=http://127.0.0.1:18100
export REMOTE_CREATIVEFLOW_REAL_JOBS=true
```

Use `REMOTE_CREATIVEFLOW_REAL_JOBS=true` for the prototype path that should
return Qwen-image / Hy3D artifacts. Set it to `false` only for dry-run request
construction tests.
