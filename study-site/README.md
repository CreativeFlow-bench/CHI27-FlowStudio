# FlowStudio Study Site

独立的参与者实验编排网站。它不依赖 FlowStudio 主前端或后端。

## 当前流程

- P001–P020：正式实验账号，按 G1–G4 循环分配平衡顺序；
- P021–P025：预测试或备用账号；
- 登录与知情同意；
- 实验前问卷；
- 两次开放式创意探索，每次 12–15 分钟，每项任务后填写 Raw NASA-TLX；
- 每个系统的一项任务结束后填写适配版 CSI 和完整 SUS；
- 中场休息、最终系统比较和半结构化访谈问卷；
- 每次提交后持久化，重新登录可继续当前步骤。

两个任务主题为圣诞解谜游戏关键道具和新中式手包；后者仍待研究团队最终确认。G1–G4 同时平衡系统顺序、任务顺序及系统与任务的对应关系。

## 启动

首次或需要重置账号时：

```bash
cd study-site
npm run seed
```

启动网站：

```bash
cd study-site
npm start
```

打开 `http://127.0.0.1:5190`。可通过 `PORT=5191 npm start` 修改端口。

## 服务器部署

生产数据保存在 `data/study.sqlite3`，使用 WAL 和单参与者事务写入。`deploy/` 提供无 sudo 环境下的应用守护、Cloudflare Quick Tunnel 守护和每 10 分钟备份；备份保留 14 天。

```bash
chmod +x deploy/*.sh
deploy/start.sh
deploy/start-quick-tunnel.sh
deploy/install-cron.sh
curl --fail http://127.0.0.1:5190/api/health
```

Quick Tunnel 仅用于部署验收和临时访问。正式实验应在 Cloudflare Dashboard 中建立 Named Tunnel 固定 hostname，并继续将源站指向 `http://127.0.0.1:5190`。

## 私有数据

- `private/participant-credentials.csv`：研究员使用的账号与明文密码；
- `private/admin-credential.txt`：独立管理者账号与密码；
- `private/reviewer-credential.txt`：P000 问卷审阅账号与密码，不写入实验数据；
- `data/accounts.json`：服务端账号、加盐哈希和任务编排；
- `data/responses.json`：参与者回答和进度。

`data/` 与 `private/` 已加入 `.gitignore`。不要将凭证表发给参与者群组，也不要提交到版本库。
