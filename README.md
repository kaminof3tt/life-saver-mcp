# Life Saver MCP

图片识别 & 网页内容分析 MCP Server。支持直接传图、蓝湖设计稿、禅道 Bug/需求/任务以及任意网页 URL 的智能分析。

## 功能

### `analyze_image` — 图片识别

传入图片（本地路径 / base64 / 图片 URL），AI 自动识别场景并结构化输出。

- UI 原型/设计稿 → 组件结构、布局、交互说明、样式标注
- Bug 截图 → 异常描述、可能原因、影响范围、修复建议
- 需求文档 → 关键需求、验收标准、业务规则
- 通用图片 → 客观描述

支持格式：PNG / JPEG / GIF（自动提取关键帧）/ WebP / BMP，单文件限制 10MB。

### `analyze_url` — 网页内容分析

传入 URL，自动识别来源并拉取内容后 AI 整理输出。

| 来源 | 认证方式 | 能力 |
|------|----------|------|
| 蓝湖 (`lanhuapp.com`) | Cookie | 设计稿图片、Axure 原型截图、设计标注、切图提取 |
| 禅道 (`zentao`) | Cookie | Bug/需求/任务详情、图片、附件、历史记录 |
| 通用网页 | 无 | 抓取文字和图片 |

### 蓝湖能力

**设计稿 URL**（无 `docId` 参数）：

```
https://lanhuapp.com/web/#/item/project/product?tid=xxx&pid=xxx
https://lanhuapp.com/web/#/item/project/stage?tid=xxx&pid=xxx
```

自动提取：
- 设计图列表 + 图片下载（转 base64 传 AI）
- 设计标注（Sketch JSON → 文字/形状/图层信息、颜色、字体、阴影、圆角等）
- 设计 Token（渐变、边框、非均匀圆角等高风险元素）
- 切图/素材（下载链接 + 多分辨率 URL：1x/2x/3x/iOS/Android）

**PRD 文档 URL**（带 `docId` 参数）：

```
https://lanhuapp.com/web/#/item/project/product?tid=xxx&pid=xxx&docId=xxx
```

自动提取：
- Axure 原型页面截图（Playwright 渲染，支持缓存）
- 页面文字内容
- 文档版本信息

蓝湖需要 Cookie 认证，DDS API 需要单独的 `DDS_COOKIE`（默认复用 `LANHU_COOKIE`）。

### 禅道支持的 URL 格式

```
?m=bug&f=view&bugID=1081                              # Bug
?m=story&f=view&id=572                                 # 研发需求
?m=requirement&f=view&storyID=495                       # 用户需求
?m=projectstory&f=view&storyID=434&projectID=146        # 项目需求
?m=task&f=view&taskID=314                               # 任务
```

禅道页面通过 ZIN 框架解析，自动提取：
- 基本信息字段（产品、模块、优先级、状态、指派等）
- 正文内容（重现步骤 / 需求描述 / 任务描述）
- 内嵌图片（自动下载转 base64 传给 AI）
- 附件文件（提取文件名、类型、大小、下载链接，供调用方判断是否需要下载解析）
- 历史记录 / 备注

## 快速开始

### 安装

```bash
pip install -e .
```

### 配置

`life-saver-mcp.json`：

```json
{
  "handlers": {
    "lanhu": {
      "enabled": true,
      "auth": { "type": "cookie", "env": "LANHU_COOKIE" }
    },
    "zentao": {
      "enabled": true,
      "url": "http://zentao.example.com",
      "auth": { "type": "cookie", "env": "ZENTAO_COOKIE" }
    }
  },
  "providers": [
    {
      "type": "openai",
      "api_key_env": "OPENAI_API_KEY",
      "base_url": "https://api.openai.com/v1",
      "models": ["gpt-4o"],
      "default": true
    }
  ]
}
```

配置文件查找顺序：`--config` 参数 > `LIFE_SAVER_CONFIG` 环境变量 > 当前目录 `life-saver-mcp.json` > `~/.config/life-saver-mcp/config.json` > 内置默认配置。

### 环境变量

| 变量 | 说明 |
|------|------|
| `OPENAI_API_KEY` | OpenAI API Key（或兼容接口的 Key） |
| `GOOGLE_API_KEY` | Google Gemini API Key |
| `ANTHROPIC_API_KEY` | Anthropic Claude API Key |
| `LANHU_COOKIE` | 蓝湖 Cookie（从浏览器 DevTools → Network → 任意请求的 Cookie header 复制） |
| `DDS_COOKIE` | 蓝湖 DDS API Cookie（可选，默认复用 `LANHU_COOKIE`） |
| `ZENTAO_COOKIE` | 禅道 Cookie（同上，需包含 `zentaosid` 和 `zp`） |
| `LIFE_SAVER_CONFIG` | 自定义配置文件路径 |

### 获取禅道 Cookie

1. 浏览器打开禅道并登录
2. F12 → Network → 随便点一个请求
3. 复制 Cookie header 中的完整内容（至少包含 `zentaosid` 和 `zp`）

### 启动

```bash
# stdio 模式（本地 MCP 客户端）
life-saver-mcp --transport stdio

# HTTP 模式（远程部署）
life-saver-mcp --transport streamable-http --port 8000

# SSE 模式（兼容旧客户端）
life-saver-mcp --transport sse --port 8000
```

### MCP 客户端配置

**Cursor / Claude Desktop**（stdio）：

```json
{
  "mcpServers": {
    "life-saver": {
      "command": "life-saver-mcp",
      "args": ["--transport", "stdio"]
    }
  }
}
```

**远程 HTTP**：

```json
{
  "mcpServers": {
    "life-saver": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

## AI Provider

支持所有 OpenAI 兼容接口，通过 `base_url` 和 `api_key_env` 配置：

```json
{
  "type": "openai",
  "api_key_env": "YOUR_API_KEY",
  "base_url": "https://your-api-endpoint.com/v1",
  "models": ["your-model-name"],
  "default": true
}
```

内置 Provider 类型：`openai`（兼容所有 OpenAI 接口）、`google`、`anthropic`。

无 Provider 时，`analyze_url` 仍可工作，返回原始抓取内容（文字 + 图片数量 + 附件列表），不调用 AI 分析。

## 架构

```
用户输入
  │
  ├─ 图片 ────────► analyze_image ──► AI 分析 ──► 结构化结果
  │
  └─ URL ─────────► analyze_url
                       │
                       ▼
                  URL Router（域名匹配）
                       │
                 ┌─────┼──────────┐
                 ▼     ▼          ▼
             Lanhu   Zentao   Generic
            Handler  Handler  Handler
                 │     │          │
           ┌─────┤     │          │
           ▼     ▼     │          │
      Axure    Design  │          │
      Screenshot Info  │          │
      (Playwright)     │          │
           │     │     │          │
           │ Annotations          │
           │ + Slices │          │
           └─────┤     │          │
                 ▼     ▼          ▼
                  PageContent
                  ├─ text_sections
                  ├─ images (base64)
                  └─ attachments (metadata)
                       │
                       ▼
                  AI Analyzer
                  (多模态：文字 + 图片)
                       │
                       ▼
                  结构化 JSON
```

## 项目结构

```
src/life_saver_mcp/
├── server.py                   # MCP Server 入口（FastMCP）
├── config.py                   # 配置加载
├── models.py                   # Pydantic 数据模型
├── providers/                  # AI Provider 层
│   ├── base.py                 #   BaseProvider 抽象类
│   ├── openai_provider.py      #   OpenAI（兼容 base_url）
│   ├── google_provider.py      #   Google Gemini
│   └── anthropic_provider.py   #   Anthropic Claude
├── handlers/                   # URL Handler 层
│   ├── base.py                 #   BaseHandler 抽象类
│   ├── router.py               #   URL 域名路由
│   ├── generic.py              #   通用网页抓取（BeautifulSoup）
│   ├── lanhu.py                #   蓝湖主逻辑（Cookie + API）
│   ├── lanhu_axure.py          #   蓝湖 Axure 原型下载 + Playwright 截图
│   ├── lanhu_annotations.py    #   蓝湖设计标注提取（Sketch JSON）
│   ├── lanhu_slices.py         #   蓝湖切图/素材提取（多分辨率 URL）
│   └── zentao.py               #   禅道（Cookie + ZIN JSON 解析）
└── analysis/                   # 分析引擎
    ├── prompts.py              #   场景识别 Prompt 模板
    ├── scenario.py             #   结果解析
    └── image_utils.py          #   GIF 多帧提取等图片工具
```

## 扩展

### 新增 AI Provider

1. 在 `providers/` 下新建文件，继承 `BaseProvider`
2. 实现 `analyze_image`、`analyze_text`、`analyze_multimodal` 三个方法
3. 在 `server.py` 的 `PROVIDER_REGISTRY` 中注册
4. 在 `life-saver-mcp.json` 的 `providers` 中添加配置

### 新增 URL Handler

1. 在 `handlers/` 下新建文件，继承 `BaseHandler`
2. 实现 `can_handle(url)` 和 `fetch_content(url)` 方法
3. 在 `handlers/__init__.py` 中导出
4. 在 `handlers/router.py` 的 `create_router` 中注册
5. 在 `life-saver-mcp.json` 的 `handlers` 中添加配置

## 参考项目

- **蓝湖功能参考**：[lanhu-mcp](https://github.com/dsphper/lanhu-mcp) — 蓝湖 Axure 文档提取 MCP Server，本项目的蓝湖 Handler（Axure 截图、设计标注、切图提取、DDS Schema 等）基于该项目的实现思路和 API 调用方式进行适配。

## License

MIT
