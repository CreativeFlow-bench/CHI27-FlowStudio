# FlowStudio GPU 常驻 Observation 定点移植清单

日期：2026-08-05  
目标运行目录：`/root/flowstudio_app`  
状态：已定点合并到 GPU、构建启用；雪人双 IntentRevision / 双 8 候选仅通过队列与数据契约验收，视觉 identity / 部件约束验收失败；C7 未完成

## 1. 移植原则

- GPU 当前代码是独立重构版本，不以本地仓库整目录覆盖。
- 主部署包只包含常驻 Observation、多 IntentRevision、Gate 泡泡和 Solution Batch 所需的 19 个定点文件（18 个运行文件 + 1 个测试文件）。
- 不包含 `.env`、SQLite、`storage/`、`intentdatabase/`、模型文件、远端 worker、既有 `frontend/dist` 或远端独有的 `FourStageGateOverlay.tsx`。
- 前端 `dist` 必须在 GPU 源码合入并通过 TypeScript 检查后现场构建，再原子切换。
- 后端数据库仅通过 `CREATE TABLE IF NOT EXISTS` 增加 Observation 表，不删除或改写已有 four-stage 数据表。

## 2. 已保留的 GPU 重构内容

远端快照中的以下能力在合并树中仍然存在：

- 8 张候选逐张生成并实时进入 Solution Space；
- Hunyuan3D / Qwen 图像 / remote worker 调度；
- `FourStageGateOverlay.tsx` 远端独有组件文件；
- 当前 `main.py` 中的远端生成、轮询和服务初始化；
- 当前 `studioStore.ts` 的候选、模型版本、编辑器及 CreativeFlow 主线。

旧的全局 Gate 计时器与单 run 状态仍保留为兼容代码，但在 `REVISION_GATED_INTERACTION` 模式下不接收 four-stage WebSocket Gate，也不再作为主 UI 入口。

## 3. 定点文件

后端：

1. `backend/app/api/__init__.py`
2. `backend/app/api/realtime_observation.py`
3. `backend/app/main.py`
4. `backend/app/models/__init__.py`
5. `backend/app/models/realtime_observation.py`
6. `backend/app/services/encoding/four_stage_encoding.py`
7. `backend/app/services/generation/four_stage_spec_builder.py`
8. `backend/app/services/intent/realtime_observation.py`
9. `backend/app/services/storage/four_stage_store.py`

测试：

10. `backend/tests/test_realtime_observation.py`

前端：

11. `frontend/src/components/ThreeViewport.tsx`
12. `frontend/src/components/overlays/PlannerClarificationOverlay.tsx`
13. `frontend/src/components/panels/AIBehaviorPanel.tsx`
14. `frontend/src/components/panels/IntentComposer.tsx`
15. `frontend/src/components/panels/PerceptionPanel.tsx`
16. `frontend/src/main.tsx`
17. `frontend/src/state/studioStore.ts`
18. `frontend/src/styles.css`
19. `frontend/src/types.ts`

实际部署补丁：

| 补丁 | SHA-256 | 作用 |
| --- | --- | --- |
| `tmp/flowstudio_realtime_observation_gpu_patch_20260805_v2.tgz` | `5817c27a7fe9ac8acdb0b4f7ebbbc3e3bd8707012885ebf124516c47b343bec4` | 19 个定点文件主包 |
| `tmp/flowstudio_gate_compression_patch_20260805_v3.tgz` | `2c416ed7ec182e3d8f3803144159ebfe799031023e010fc5b039476db54710a9` | Gate 目标与一句问句压缩 |
| `tmp/flowstudio_frontend_revision_selection_fix_20260805.tgz` | `3456e15b83d273c48c1a92448a5778322935ebf5a362fb7a88ed32bee6d87845` | 已接受 revision 切换后恢复选词；修正右栏状态 |
| `tmp/flowstudio_frontend_keyword_panel_fix_20260805.tgz` | `dbe755eda0fa347e3768d8d3925ea710587985d9087052216c7f702d6cbf0cb8` | 修复关键词列表被压成 0px、实际无法点击 |

## 4. GPU 基线防误覆盖校验

部署前至少校验以下 GPU 原文件摘要；不一致则停止并重新合并：

| 文件 | GPU 快照 SHA-256 |
| --- | --- |
| `backend/app/main.py` | `6c9faaae1f63e667f1e8cb117952ad06a3283a3e1958bfe535aeb015dc7d0ce4` |
| `backend/app/services/encoding/four_stage_encoding.py` | `e07bd6878f96d96362622a836a5be66837d00031c60dd6369f408c13aa418098` |
| `backend/app/services/generation/four_stage_spec_builder.py` | `3c1718c9de86dfe69d422888bcfc2bdc94e604bbdad5cadf766763fe6785f449` |
| `backend/app/services/storage/four_stage_store.py` | `deb4e00912f866fcd251d252eb43b99e2f2e0a7df9aec2c1bb3243aabc064fa2` |
| `frontend/src/main.tsx` | `ac0299b685b8fcb33443c0a159bef30035f4973dd2525e6ceaedeededd84b604` |
| `frontend/src/state/studioStore.ts` | `abd7302838cd739c9d5e4778bdac540a3acfa97eefa35e7aa0e1db931046ef71` |
| `frontend/src/styles.css` | `5e8b3c3aad7657389917b8a9718800db393b5ad4e3e582230c334f4167613490` |
| `frontend/src/types.ts` | `a07d1f191d4cff3308b1351f4fb225968dceb32966c7898653c4b43bf9dbc255` |

## 5. 部署与回滚边界

部署前在 GPU 创建：

```text
/root/flowstudio_backups/realtime_observation_20260805_<timestamp>/
  source_files/      # 被替换文件的原件
  frontend_dist/     # 当前可用 dist
  checksums.txt
  process_snapshot.txt
```

部署顺序：

1. 校验远端基线摘要；
2. 备份定点源文件和当前 `frontend/dist`；
3. 解包到临时目录，不直接解压覆盖运行目录；
4. 逐文件复制到 `/root/flowstudio_app`；
5. 使用远端 Python 环境做 import / API tests；
6. 在远端执行 TypeScript 检查与 Vite build；
7. 原子替换 `frontend/dist`；
8. 仅重启 18000 后端和 5173 静态前端，不重启 Qwen、Planner、remote worker 或 18100 worker；
9. 执行 API、WebSocket、双 Gate、关键词继承和两批 8 个结果追加验收。

任一检查失败时恢复 `source_files/` 与 `frontend_dist/`，再恢复原后端/前端进程命令；不得通过清空 SQLite 回滚。

## 6. 合并、部署与回滚记录

GPU 部署前与三个后续定点补丁均创建了独立备份：

```text
/root/flowstudio_backups/realtime_observation_20260805_20260805_201407
/root/flowstudio_backups/gate_compression_20260805_20260805_203016
/root/flowstudio_backups/frontend_revision_selection_20260805_20260805_210436
/root/flowstudio_backups/frontend_keyword_panel_20260805_20260805_215828
```

当前运行态（2026-08-05 22:36 CST 复核）：

```text
backend  : PID 41481 · uvicorn :18000
frontend : PID 45941 · http.server :5173
health   : backend/frontend 均通过
```

Qwen、Planner、18100 worker 和 CreativeFlow 主线未因这些前后端定点部署而重启或覆盖。GitHub 提交与 GitHub Pages 部署按用户要求保持暂停。

## 7. 验证结果

验证基线是从 `/root/flowstudio_app` 只读下载的源码快照，再只覆盖上述定点文件：

- 远端独有 `frontend/src/components/overlays/FourStageGateOverlay.tsx` 保留；
- 本地 Observation / Encoding / Generation 聚焦回归：37 passed；
- GPU 合并树聚焦回归：30 passed；
- GPU 快照合并树 TypeScript：通过；
- GPU 快照合并树 Vite production build：通过；
- 部署包未包含环境配置、数据、模型或现有 `dist`。

部署后在线证据：

- 无 Send 时不创建 Gate；两个快速 Send 创建两个稳定 revision 泡泡；
- Gate 问句由泛化 planner 文本压缩为“整体轮廓 / 形状或连接 / 表面或材质”之一，且不显示 `obj_group_*`；
- 第一版接受词 `soft silhouette`，第二版接受后继承并追加 `outward extension`；
- 雪人链路完成两个 SolutionBatch；两批 `append_index=1,2`，第二批 `parent_batch_id` 指向第一批；
- 两批均为 `completed` 且各含 8 个真实生成 artifact，第一批未被第二批覆盖；
- 前端生产构建已包含关键词面板可点击修复。

视觉复核纠错：两次 Send 锁定的 `viewport.jpg` 均为空白深色图，第二个 revision 的
`target_part_id=null`、`gate_scope=whole`。因此这次证据只证明多 revision、关键词继承、
顺序追加与每批 8 个 artifact，不证明原物体精确 identity，也不证明“帽子连接”局部约束。

C7 未完成：必须先增加空白快照拦截、文本/行为目标冲突处理与 part mask/anchor 传递，
再重跑 snowman；teapot、water gun 与用户侧前端选词/泡泡切换复验也仍需补齐。
