# CreativeFlow 大型生成后端协作接口（v1）

## 1. 协作边界

本接口是前端/业务后端与 CreativeFlow GPU 生成服务器之间的稳定边界。

协作者只依赖 `/api/v1` 的请求与返回格式，不依赖以下内部实现：

- Planner 与 source attribute 提取；
- Wikidata、Getty AAT、AskNatureNet 的查询和映射；
- Low Fidelity、Part、Texture 的提示词；
- Qwen-Image/Qwen2.5-VL 的模型与参数实现；
- SAM3D 部件解析；
- Hunyuan3D、PBR 材质生成与 Blender 三视图渲染；
- GPU 服务器内部路径。

因此，CreativeFlow 内部逻辑可以持续调整。v1 已有字段不删除、不改名、不改变
含义；不兼容调整使用 `/api/v2`。新增可选字段可以继续加入 v1。

## 2. 当前网络拓扑

当前 DatabaseMart 跳板机使用共享公网 IPv4：

- 公网 IP：`93.127.141.73`
- SSH 映射端口：`10053`
- 没有可用的公网 HTTP/HTTPS 端口映射；
- GPU worker 的 API 仅监听 `127.0.0.1:18080`。

立即可用的正式联调路径：

```text
协作者业务后端
  │  本地端口 18080
  │
  ├─ SSH LocalForward（加密）
  │
93.127.141.73:10053
  │  跳板机 127.0.0.1:18080
  │
  ├─ GPU 发起的 SSH RemoteForward（加密）
  │
27774 GPU Worker 127.0.0.1:18080
  │
  └─ CreativeFlow /api/v1
```

这条链路不会向公网暴露 GPU SSH、Qwen 服务端口或服务器文件路径。

## 3. 给协作者开通权限

不要把 `administrator` 密码或 GPU root 密码交给协作者。让协作者提供一条
SSH 公钥，例如：

```text
ssh-ed25519 AAAA... teammate-name
```

将其以受限模式加入跳板机 `~/.ssh/authorized_keys`：

```text
restrict,port-forwarding,permitopen="127.0.0.1:18080" ssh-ed25519 AAAA... teammate-name
```

受限 key 只允许访问 CreativeFlow API 转发端口，不能开启 shell。

协作者建立隧道：

```bash
ssh -NT \
  -p 10053 \
  -L 18080:127.0.0.1:18080 \
  administrator@93.127.141.73
```

之后其业务后端使用：

```bash
export CREATIVEFLOW_BASE_URL=http://127.0.0.1:18080
export CREATIVEFLOW_API_KEY='通过安全渠道单独提供'
```

浏览器前端不应直接保存 API key。推荐：

```text
浏览器前端 → 协作者业务后端 → CreativeFlow API
```

## 4. 鉴权

所有 `/api/v1` 请求都需要：

```http
X-CreativeFlow-Key: <API_KEY>
```

API key 应通过密码管理器或加密消息单独提供，不写入 Git，不放在前端代码里。

## 5. 接口概览

| 方法 | Route | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/variations/capabilities` | 查询 variation、参数默认值和必需资产 |
| `POST` | `/api/v1/assets` | 上传 source image、mesh、JSON、mask 等 |
| `POST` | `/api/v1/variation-jobs` | 提交 Low Fidelity、Part 或 Texture 任务 |
| `GET` | `/api/v1/variation-jobs/{job_id}` | 查询进度并获取候选结果 |
| `POST` | `/api/v1/variation-jobs/{job_id}/cancel` | 取消任务 |
| `GET` | `/api/v1/artifact-file` | 下载已授权任务产物 |
| `GET` | `/docs` | OpenAPI/Swagger 文档 |

任务是异步执行的。提交接口立即返回 `job_id`，业务后端轮询状态接口。

## 6. 上传输入资产

```bash
curl -X POST "$CREATIVEFLOW_BASE_URL/api/v1/assets" \
  -H "X-CreativeFlow-Key: $CREATIVEFLOW_API_KEY" \
  -F "flowstudio_asset_id=snowman-source" \
  -F "session_id=team-demo-001" \
  -F "file=@snowman.png"
```

返回示例：

```json
{
  "asset_id": "rasset_0123456789",
  "flowstudio_asset_id": "snowman-source",
  "session_id": "team-demo-001",
  "filename": "snowman.png",
  "content_type": "image/png",
  "size_bytes": 583102
}
```

外部接口只返回不可猜测的 `asset_id`，不返回服务器绝对路径。

支持：

- 图片：PNG、JPEG、WebP；
- 3D：GLB、OBJ、ZIP；
- 结构数据：JSON、NPY。

## 7. 提交 Texture / PBR 材质迁移

```bash
curl -X POST "$CREATIVEFLOW_BASE_URL/api/v1/variation-jobs" \
  -H "X-CreativeFlow-Key: $CREATIVEFLOW_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "client_job_id": "material-snowman-001",
    "variation": "texture",
    "object_type": "snowman",
    "source": {
      "image_asset_id": "rasset_0123456789"
    },
    "prompt": "保持主体结构与全部元素，只迁移主体材质和PBR外观",
    "kg": {
      "top_k": 8,
      "candidate_pool_size": 20,
      "scoring_enabled": true,
      "generate_all_retrieved": false,
      "cache_mode": "cache_first",
      "request_timeout_sec": 8
    },
    "image": {
      "width": 768,
      "height": 768,
      "steps": 20,
      "seed": 42,
      "source_strength": 0.62,
      "attempts_per_candidate": 3,
      "require_white_background": true
    },
    "mesh": {
      "enabled": true,
      "max_candidates": 4
    }
  }'
```

## 8. 提交 Low Fidelity

将 `variation` 改为 `low_fidelity`。必需输入：

- `object_type`：具体 source 名词，不能使用泛化的 `object`；
- `source.image_asset_id`。

Low Fidelity 只迁移整体轮廓、长宽高、质量分布、主体形状和曲线节奏，保留
source 身份、主要元素、颜色关系和可识别特征。

## 9. 提交 Part

Part 必须来自真实 SAM3D 解析。必需输入：

```json
{
  "variation": "part",
  "source": {
    "image_asset_id": "rasset_image",
    "mesh_asset_id": "rasset_mesh",
    "brush_mask_asset_id": "rasset_brush",
    "sam3d_manifest_asset_id": "rasset_sam3d_manifest",
    "part_semantics_asset_id": "rasset_part_semantics"
  },
  "target_part": {
    "part_id": "sam3d_10",
    "label": "handle grip"
  },
  "socket_constraints": {
    "preserve_attachment": true
  }
}
```

其中 brush mask 只用于解析用户选择对应的 SAM3D part 语义，不作为伪造的
二维局部拼接结果。最终 Part 仍需遵循真实 3D part selection、连接关系和后续
部件原位替换。

## 10. 参数说明

### KG 参数

| 参数 | 说明 |
| --- | --- |
| `top_k` | 最终进入 mapping 和生成的 KG direction 数量 |
| `candidate_pool_size` | top-k 选择之前的候选池规模 |
| `scoring_enabled` | 是否启用当前候选评分 |
| `generate_all_retrieved` | 跳过 top-k，直接生成全部检索候选 |
| `cache_mode` | `cache_first`、`network_first` 或 `cache_only` |
| `request_timeout_sec` | 单次图谱请求超时 |

当 `generate_all_retrieved=true` 时，`top_k` 不生效。

### 生图参数

| 参数 | 说明 |
| --- | --- |
| `width` / `height` | Qwen-Image 输出尺寸 |
| `steps` | 推理步数 |
| `seed` | 第一个候选的随机种子基值 |
| `source_strength` | source-conditioned generation 强度 |
| `attempts_per_candidate` | 候选未通过视觉 QA 时的最大重试次数 |
| `require_white_background` | 是否强制纯白背景、无场景、单体 |

### 3D 参数

| 参数 | 说明 |
| --- | --- |
| `enabled` | 是否继续执行 Hunyuan3D/PBR/多视图阶段 |
| `max_candidates` | 进入重型 3D 阶段的最大候选数 |

## 11. 查询状态和结果

```bash
curl \
  -H "X-CreativeFlow-Key: $CREATIVEFLOW_API_KEY" \
  "$CREATIVEFLOW_BASE_URL/api/v1/variation-jobs/$JOB_ID"
```

主要返回字段：

```json
{
  "job_id": "rw_creativeflow_texture_xxx",
  "client_job_id": "material-snowman-001",
  "variation": "texture",
  "status": "running",
  "stage": "knowledge_graph_expansion",
  "progress": 0.25,
  "message": "…",
  "error": null,
  "candidates": [
    {
      "candidate_id": "direction_01",
      "label": "…",
      "prompt": "…",
      "image_url": "/api/v1/artifact-file?path=…",
      "mesh_glb_url": null,
      "mesh_obj_url": null,
      "multiview_url": null,
      "graph_anchor": "…",
      "mapping": {}
    }
  ],
  "result_manifest_url": "/api/v1/artifact-file?path=…"
}
```

`status` 取值：

- `queued`
- `running`
- `completed`
- `failed`
- `cancelled`

同一个 variation 下重复提交相同 `client_job_id` 不会重复启动昂贵 GPU 任务。

## 12. Python 调用示例

```python
import os
import time
import requests

base_url = os.environ["CREATIVEFLOW_BASE_URL"]
headers = {"X-CreativeFlow-Key": os.environ["CREATIVEFLOW_API_KEY"]}

with open("source.png", "rb") as source:
    upload = requests.post(
        f"{base_url}/api/v1/assets",
        headers=headers,
        data={"flowstudio_asset_id": "demo-source", "session_id": "demo"},
        files={"file": ("source.png", source, "image/png")},
        timeout=60,
    )
upload.raise_for_status()
asset_id = upload.json()["asset_id"]

job = requests.post(
    f"{base_url}/api/v1/variation-jobs",
    headers=headers,
    json={
        "client_job_id": "demo-texture-001",
        "variation": "texture",
        "object_type": "snowman",
        "source": {"image_asset_id": asset_id},
        "kg": {"top_k": 8, "candidate_pool_size": 20},
        "image": {"seed": 42, "steps": 20},
        "mesh": {"enabled": True, "max_candidates": 4},
    },
    timeout=60,
)
job.raise_for_status()
job_id = job.json()["job_id"]

while True:
    response = requests.get(
        f"{base_url}/api/v1/variation-jobs/{job_id}",
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    result = response.json()
    if result["status"] in {"completed", "failed", "cancelled"}:
        break
    time.sleep(5)

print(result)
```

## 13. 正式公网 HTTPS 升级

如果希望协作者不建立 SSH 隧道，需要在 DatabaseMart 控制台增加公网端口映射，
或换用带独立 IPv4 和 sudo 权限的 VPS。推荐最终拓扑：

```text
协作者后端
  → https://creativeflow-api.example.com
  → Caddy/Nginx（TLS、限流、日志）
  → SSH/WireGuard 私网隧道
  → GPU Worker 127.0.0.1:18080
```

公网升级只更换 `CREATIVEFLOW_BASE_URL`，请求 schema 与结果结构不变。
