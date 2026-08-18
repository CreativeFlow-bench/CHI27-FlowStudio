# FlowStudio

CHI27 interaction-aware CreativeFlow prototype：FastAPI + React/Three.js。  
文本/图片默认走云端 `MODEL_API`；GPU 单机跑 backend / worker / Hunyuan。

## Setup

```bash
cp .env.example .env
cp .env.model_api.example .env.model_api   # 只在这里填 MODEL_API_KEY
```

`.env` / `.env.model_api` 不要提交。Qwen planner 已退役（规则兜底）。

## Run（本机）

```bash
FLOWSTUDIO_KEEP_RUNNING=1 scripts/dev_stack.sh
```

- Frontend: http://127.0.0.1:5184  
- Backend:  http://127.0.0.1:18001  

## GPU 单机

当前主 GPU：`connect.westb.seetacloud.com:36536`。  
旧 westd 已替换；weste 上的 Qwen planner **不再接入**。

服务器：

```bash
cd /root/flowstudio_app
FLOWSTUDIO_CLOUD_ROOT=/root/flowstudio_app \
FLOWSTUDIO_WORKER_DIR=/root/flowstudio_app/remote_worker \
FLOWSTUDIO_START_VLM=0 \
bash scripts/cloud_start.sh
```

公网入口由 `8080` gateway + `cloudflared` quick tunnel 提供（URL 见 `logs/cloudflared-quick.log`，重启会变）。

## Docs

细节在 `docs/`。
