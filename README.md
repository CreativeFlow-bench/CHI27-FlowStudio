# FlowStudio

CHI27 interaction-aware CreativeFlow prototype：本地 FastAPI + React/Three.js，云端文本/图片模型走中继。

## Setup

```bash
cp .env.example .env
cp .env.model_api.example .env.model_api   # 只在这里填 MODEL_API_KEY
```

`.env` / `.env.model_api` 不要提交。

## Run

```bash
FLOWSTUDIO_KEEP_RUNNING=1 scripts/dev_stack.sh
```

- Frontend: http://127.0.0.1:5184  
- Backend:  http://127.0.0.1:18001  

或分开起：

```bash
# backend
cd backend && PYTHONPATH=..:. uvicorn app.main:app --host 127.0.0.1 --port 18001

# frontend
cd frontend && npm install && npm run dev
```

## Models

默认：`gemini-3.6-flash`（文本）/ `gpt-image-2`（图片），配置见 `.env.model_api`。

探测：

```bash
curl -s 'http://127.0.0.1:18001/api/v1/model-api/probe?include_image=true'
```

## Docs

设计与协议细节在 `docs/`，不要把运行说明堆进本文件。
