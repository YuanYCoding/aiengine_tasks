# AI Engine Batch Service

基于 FastAPI + Playwright + Docker 的 AI 引擎批量交互与网络抓包平台。提供浏览器端 API 参数捕获、单轮对话调试、以及 Excel 驱动的批量测试三大核心能力。

## 功能概览

### 1. 浏览器抓包（CDP Network Capture）

通过 Docker 容器内的 Chromium 浏览器 + Chrome DevTools Protocol，自动捕获 AI 平台 API 请求中的关键参数：

- **自动登录**：支持用户名/密码自动填写
- **实时抓包**：基于 URL 关键词过滤，捕获请求/响应的 Headers、Body、Cookie
- **VNC 可视化**：通过 noVNC 在浏览器中直接操作远程 Chromium，无需本地浏览器
- **参数自动提取**：自动解析 `processId`、`sessionId`、`voigpt-client-id`、`variableNode` 等关键参数
- **cURL 手动解析**：支持粘贴 cURL 或原始 HTTP 请求文本，自动解析参数

### 2. AI 对话调试

- 初始化对话（A 接口）
- 发送消息并获取 AI 回复（B 接口）
- SSE 流式接收（C 接口），支持断流重试
- 会话历史管理（保留最近 5 轮对话，支持回放和导出）

### 3. 批量测试 / 批量训练

- **Excel 测试集导入**：按 "Call ID + 用户话术" 格式批量导入
- **在线编辑器**：内置表格编辑器，支持从 Excel 直接粘贴数据
- **模板下载**：一键下载测试用例模板
- **多轮对话测试**：按 Call ID 分组，每组独立对话，逐条发送话术
- **实时进度**：通过 WebSocket 实时推送进度和日志
- **结果导出**：支持 Excel (.xlsx) 和纯文本 (.txt) 格式

## 技术架构

```
┌─────────────────────────────────────────────────────┐
│                   Docker Container                    │
│                                                       │
│  ┌──────────────┐  ┌──────────────┐                  │
│  │  FastAPI App  │  │  Xvfb + VNC  │                  │
│  │  (port 8000)  │  │  (display    │                  │
│  │               │  │   100-199)   │                  │
│  └──────┬───────┘  └──────┬───────┘                  │
│         │                  │                          │
│  ┌──────┴──────────────────┴───────┐                  │
│  │         Playwright Chromium       │                  │
│  │    (CDP Network Capture + Auto)   │                  │
│  └──────────────────────────────────┘                  │
│                                                       │
│  ┌──────────────────────────────────┐                  │
│  │        AI Platform API            │                  │
│  │  (antaios-op.100credit.com)      │                  │
│  └──────────────────────────────────┘                  │
└─────────────────────────────────────────────────────┘
```

## 目录结构

```
├── main.py              # FastAPI 入口，API 路由 + WebSocket + 会话管理
├── api_engine.py        # AI 平台 HTTP 客户端（A/B/C 三种接口封装）
├── batch_worker.py      # 批量测试引擎（Excel 解析、分组执行、结果导出）
├── cdp_capture.py       # CDP 浏览器抓包引擎（Playwright + DevTools Protocol）
├── requirements.txt     # Python 依赖
├── Dockerfile           # Docker 镜像构建
├── start.sh             # 容器启动脚本
└── static/
    ├── index.html       # 主前端页面（单文件 SPA）
    └── vnc.html         # noVNC 浏览器远程操作页面
```

## API 接口

### 页面路由

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 主工作台页面 |
| GET | `/vnc` | VNC 远程浏览器页面 |

### 浏览器抓包 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/proxy/start` | 启动浏览器并开始抓包 |
| POST | `/api/proxy/stop` | 停止浏览器 |
| GET | `/api/proxy/status` | 查询抓包状态 |
| GET | `/api/proxy/packets` | 获取已捕获的数据包 |
| DELETE | `/api/proxy/packets` | 清空数据包 |
| POST | `/api/proxy/keyword` | 更新 URL 过滤关键词 |

### 对话 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat/init` | 创建新对话 |
| POST | `/api/chat/send` | 发送消息 |

### 批量处理 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/upload` | 上传 Excel 测试集 |
| POST | `/api/template/download` | 下载测试模板 |
| POST | `/api/batch/run` | 启动批量测试 |
| POST | `/api/batch/stop` | 停止批量测试 |
| GET | `/api/batch/status` | 查询批量进度 |
| GET | `/api/export/excel` | 导出结果为 Excel |
| GET | `/api/export/txt` | 导出结果为文本 |

### 其他

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/parse/manual` | 手动解析 cURL/HTTP 请求 |
| POST | `/api/client/config` | 更新/查询 API 客户端配置 |
| WS | `/ws` | 实时事件推送（WebSocket） |
| WS | `/api/vnc/ws` | VNC WebSocket 代理 |

## Docker 部署

### 构建镜像

```bash
docker build -t aiengine-tasks .
```

### 运行容器

```bash
docker run -d \
  --name aiengine \
  -p 8000:8000 \
  -e PORT=8000 \
  aiengine-tasks
```

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PORT` | `8000` | 应用监听端口 |
| `DISPLAY` | `:99` | Xvfb 虚拟显示器编号 |
| `HEADLESS` | `false` | 浏览器是否无头模式 |

## 技术栈

- **后端框架**: FastAPI + Uvicorn
- **浏览器自动化**: Playwright + Chrome DevTools Protocol
- **数据解析**: pandas + openpyxl
- **远程桌面**: Xvfb + x11vnc + noVNC
- **容器化**: Docker (python:3.11-slim)
- **前端**: 原生 JavaScript（单文件 SPA，无构建步骤）
- **实时通信**: WebSocket + SSE

## 使用流程

### 参数捕获

1. 打开工作台 → 点击「开始监听」
2. 在 VNC 窗口中登录 AI 平台
3. 进入训练页面并触发一次对话
4. CDP 自动捕获请求参数 → 点击「应用配置」同步到 API 设置

### 批量测试

1. 准备 Excel 文件（第一列 Call ID，第二列用户话术）
2. 上传文件或使用在线编辑器
3. 配置线程数、对话消息上限、重试次数
4. 点击「开始批量训练」
5. 实时查看进度 → 完成后导出结果

## License

MIT
