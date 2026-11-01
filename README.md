# life-saver-mcp

禅道（ZenTao）的 MCP 服务器。给任意支持 Model Context Protocol 的客户端用：把禅道上的需求 / 任务 / BUG 连编号一起取出来（正文、备注、操作记录、附件），搜禅道，查工时，也能写回（开始、记工时、完成、解决、关闭、加备注）。

底层取数与写入逻辑在 [`life-saver-core`](https://www.npmjs.com/package/life-saver-core) 里，和 [DSH 插件版](https://github.com/kaminof3tt/dsh-life-saver) 共用同一份实现——两边的工具描述、参数、排版都来自同一个源，不会各写一套然后慢慢漂移。

## 六个工具

| 工具 | 干什么 |
| --- | --- |
| `zentao_read` | 按编号或链接读一条需求 / 任务 / BUG：正文、备注、操作记录、附件落盘，关联需求一起递归取 |
| `zentao_search` | 在需求 / 任务 / BUG 里搜关键词，给出编号与标题 |
| `zentao_status` | 体检：两条取数通道配没配齐、能不能连、探到的是哪套禅道 |
| `zentao_workhours` | 某账号在任意时间段做了哪些工作、消耗多少工时，以及「有动作但没记工时」的漏项 |
| `zentao_task_op` | 写任务：开始 / 记工时 / 完成 / 暂停 / 激活 / 关闭 / 取消 / 备注 |
| `zentao_bug_op` | 写 BUG：确认 / 解决 / 关闭 / 备注 / 记工时 |

写操作**会真的写入禅道**，没有预览；默认只允许动自己名下的单子（`ZENTAO_WRITE_ALLOW_OTHERS=1` 才放开）。

## 两条取数通道

- **db**：直连禅道只读库 + SFTP 取附件。快、能批量、不惊动禅道的审计日志。
- **http**：账号密码登录换 cookie 再走页面。需要账号有对应权限，但和人工看到的一致（页面皮肤差异会自动探测）。
- **auto**（默认）：先 db，失败自动降级到 http，并在结果里说明降级原因。

只配 http 也能用，只配 db 也能用；两个都配最稳（db 挂了还有 http 兜底）。

## 安装

```bash
npm i -g life-saver-mcp
```

然后在 MCP 客户端里登记。以「命令 + 环境变量」这种配置为例：

```json
{
  "mcpServers": {
    "zentao": {
      "command": "npx",
      "args": ["-y", "life-saver-mcp"],
      "env": {
        "ZENTAO_BASE_URL": "http://zentao.example.com",
        "ZENTAO_ACCOUNT": "your-account",
        "ZENTAO_PASSWORD": "your-password",
        "ZENTAO_DB_HOST": "10.0.0.9",
        "ZENTAO_DB_PORT": "3306",
        "ZENTAO_DB_NAME": "zentao",
        "ZENTAO_DB_USER": "reader",
        "ZENTAO_DB_PASSWORD": "readonly-password"
      }
    }
  }
}
```

先跑一次体检，确认配置能被解析（不连禅道、不回显密码）：

```bash
ZENTAO_BASE_URL=... ZENTAO_ACCOUNT=... life-saver-mcp --check
```

## 配置

全部从环境变量读。密码**只**从环境变量读，不落盘、不进配置文件、不打印。

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `ZENTAO_MODE` | `auto` | `auto` / `db` / `http` |
| `ZENTAO_BASE_URL` | — | 禅道根地址，例如 `http://zentao.example.com`（带不带 `/zentao` 后缀都行） |
| `ZENTAO_ACCOUNT` | — | 禅道登录账号 |
| `ZENTAO_SKIN` | `auto` | 详情页皮肤：`auto` / `detail-section` / `detail` / `article`；探测总失败时钉死一档 |
| `ZENTAO_HTTP_TIMEOUT_MS` | `60000` | 单次 HTTP 超时 |
| `ZENTAO_DB_HOST` | — | 只读库地址 |
| `ZENTAO_DB_PORT` | `3306` | 只读库端口 |
| `ZENTAO_DB_NAME` | `zentao` | 库名 |
| `ZENTAO_DB_USER` | — | 只读账号 |
| `ZENTAO_DB_PREFIX` | `zt_` | 表前缀 |
| `ZENTAO_DB_CONNECTION_LIMIT` | `4` | 连接池上限 |
| `ZENTAO_SFTP_HOST` | — | 附件读取用的 SFTP 主机（通常与库同机） |
| `ZENTAO_SFTP_PORT` | `22` | SFTP 端口 |
| `ZENTAO_SFTP_USER` | — | SFTP 账号 |
| `ZENTAO_SFTP_UPLOAD_BASE` | — | 禅道 upload 目录绝对路径，例如 `/var/www/zentao/data/upload` |
| `ZENTAO_SFTP_PRIVATE_KEY` | — | 改用私钥登录时的私钥路径 |
| `ZENTAO_PASSWORD` | — | 禅道登录密码 |
| `ZENTAO_DB_PASSWORD` | — | 只读库密码 |
| `ZENTAO_SFTP_PASSWORD` | — | SFTP 密码 |
| `ZENTAO_WRITE_ENABLED` | `1` | 写能力总开关；置 `0` 即只读 |
| `ZENTAO_WRITE_MODE` | `http` | 写走哪条线：`http`（推荐，副作用由禅道自己写全）/ `db` / `auto` |
| `ZENTAO_WRITE_ALLOW_OTHERS` | `0` | 是否允许改不是指派给自己的任务 / BUG |
| `ZENTAO_DISCOVERY` | `1` | 是否自探索部署差异（皮肤、登录算法、库列能力） |
| `ZENTAO_DISCOVERY_TTL_MS` | `600000` | 探测结果缓存时长 |
| `ZENTAO_OUTPUT_DIR` | — | 附件落盘目录；留空则放到 `当前目录/zentao-extract/<kind>-<id>` |
| `ZENTAO_MAX_ATTACHMENTS` | `40` | 单个对象最多落盘多少个附件 |
| `ZENTAO_MAX_ATTACHMENT_BYTES` | `20971520` | 单个附件大小上限（超过只记录不落盘） |
| `ZENTAO_MAX_RELATED` | `8` | 最多递归取多少个关联对象 |

也可以用 `--config <file>` 从 JSON 补一批非密码配置（环境变量优先，密码仍然只认环境变量）。见 [`life-saver-mcp.example.json`](./life-saver-mcp.example.json)。

## 附件

附件（截图、文档）会落到 `ZENTAO_OUTPUT_DIR` 或 `<当前目录>/zentao-extract/<kind>-<id>/`，工具结果里返回绝对路径。MCP 客户端如果支持图片内容块，可以让模型直接看截图；本服务器目前只返回路径与文件名，避免把二进制塞进上下文。

## 开发

```bash
git clone https://github.com/kaminof3tt/life-saver-mcp.git
cd life-saver-mcp
npm i
npm run build        # tsc → lib/
npm test             # 配置解析、tools/list、tools/call 错误路径、真实 stdio 握手
```

依赖 `life-saver-core`。本地要联调未发布的核心包时，先把它装进来（只改 `node_modules`，不动 manifest）：

```bash
npm i --no-save ../dsh-life-saver/packages/core
```

`npm run build` 之后可以直接 `node lib/index.js --check` 看配置摘要，或 `node lib/index.js` 在 stdio 上起服务。

## 发布

推一个 `v*` tag，或手动触发 `release` workflow（`workflow_dispatch` 带版本号）。workflow 会先确认目标版本的 `life-saver-core` 已经发布到 npm，再改 manifest 里的版本与依赖、构建、发布，全程不需要跨仓凭证。只在 CI 里发布（`NPM_TOKEN` 是仓里的 secret），本地直接 `npm publish` 会绕过版本断言。

另一个 workflow 是 `ci`：推到 `main` 与每个 PR 都跑构建、类型检查和测试。**在 `life-saver-core` 上 npm 之前，它会先探一次依赖能不能安装**——查不到就只留一条 warning 跳过，不会因为 `ETARGET` 红一片；等 core 上线后，同一个 workflow 自动开始真正干活。

## 声明

- 非官方项目，与禅道官方无关。
- 写操作直接改生产禅道的数据，请先用只读账号 + `ZENTAO_WRITE_ENABLED=0` 跑一段时间再放开。
- 密码只走环境变量；本仓库不含任何真实站点地址、账号或人名。

MIT
