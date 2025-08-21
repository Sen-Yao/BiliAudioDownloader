# BiliAudioDownloader

基于FastAPI的B站视频下载和音频切分服务，支持HTTP API和MCP协议。

## 🚀 特性

- ✅ 下载B站视频并提取音频
- ✅ 将音频切分为30秒片段
- ✅ 支持HTTP API和MCP协议
- ✅ Docker一键部署
- ✅ 自动清理临时文件

## 🛠️ 快速部署

### 1. 获取B站cookies
```bash
# 在浏览器中登录B站
# 按F12打开开发者工具
# 在Console中输入：document.cookie
# 复制输出的cookies字符串
```

### 2. 部署服务
```bash
# 构建镜像
docker build -t bili-audio-downloader .

# 运行容器（使用环境变量配置cookies）
docker run -d \
    --name bili-audio-downloader \
    --restart unless-stopped \
    -p 8000:8000 \
    -e BILI2TEXT_BILIBILI_COOKIES="SESSDATA=your_sessdata;bili_jct=your_bili_jct;DedeUserID=your_dedeuserid" \
    bili-audio-downloader
```

### 3. 验证部署
```bash
# 健康检查
curl http://localhost:8000/health

# API文档
open http://localhost:8000/docs
```

## 📊 使用示例

### HTTP API
```bash
# 创建任务
curl -X POST "http://localhost:8000/api/v1/tasks/" \
  -H "Content-Type: application/json" \
  -d '{"bv_number": "BV1b1bHzAEdG"}'

# 查询状态
curl "http://localhost:8000/api/v1/tasks/{task_id}"

# 获取音频片段
curl "http://localhost:8000/api/v1/tasks/{task_id}/segments"
```

### MCP协议（REST）
```bash
# 列出工具
curl "http://localhost:8000/mcp/tools"

# 调用工具
curl -X POST "http://localhost:8000/mcp/tools/call" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "create_audio_segmentation_task",
    "arguments": {"bv_number": "BV1b1bHzAEdG"}
  }'
```

### MCP协议（Streamable HTTP / SSE）
- 服务已提供基于 SSE 的双通道端点：
  - 下行（服务器->客户端，SSE）: `GET http://localhost:8000/mcp/sse`
  - 上行（客户端->服务器，POST）: `POST http://localhost:8000/mcp/messages?session_id=<id>`

- 客户端配置示例：
  - transport: `sse`
  - url: `http://localhost:8000/mcp/sse`
  - headers: 可选（鉴权等）

使用方式（低层示例）：
```bash
# 1) 连接 SSE，读取首个 event: endpoint，获取带 session_id 的上行URL
curl -N http://localhost:8000/mcp/sse

# 2) 向上行URL POST JSON-RPC 消息（以 listTools 为例）
# 假设上一步拿到的上行地址是 /mcp/messages?session_id=XXXX
curl -X POST "http://localhost:8000/mcp/messages?session_id=XXXX" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## 🔧 环境变量

| 变量名 | 说明 | 默认值 | 必需 |
|--------|------|--------|------|
| `BILI2TEXT_BILIBILI_COOKIES` | B站cookies | 无 | ✅ |
| `BILI2TEXT_DEBUG` | 调试模式 | `false` | ❌ |
| `BILI2TEXT_LOG_LEVEL` | 日志级别 | `INFO` | ❌ |
| `BILI2TEXT_MAX_CONCURRENT_TASKS` | 最大并发任务数 | `3` | ❌ |

## 📁 项目结构

```
BiliAudioDownloader/
├── app/                    # 应用代码
│   ├── main.py            # FastAPI应用入口
│   ├── tasks.py           # 任务处理
│   ├── mcp_routes.py      # MCP协议路由
│   ├── models.py          # 数据模型
│   ├── config.py          # 配置管理
│   └── services/          # 服务层
├── Dockerfile             # Docker配置
├── requirements.txt       # Python依赖
└── README.md             # 项目说明
```

## 📋 API接口

### 任务管理
- `POST /api/v1/tasks/` - 创建音频切分任务
- `GET /api/v1/tasks/{task_id}` - 查询任务状态
- `GET /api/v1/tasks/{task_id}/segments` - 获取音频片段
- `GET /api/v1/tasks/{task_id}/download/{index}` - 下载音频片段

### MCP工具
- `create_audio_segmentation_task` - 创建音频切分任务
- `get_task_status` - 查询任务状态
- `get_audio_segments` - 获取音频片段信息
- `cancel_task` - 取消任务

## 🔗 相关链接

- [API文档](http://localhost:8000/docs)
- [健康检查](http://localhost:8000/health)
- [MCP工具列表](http://localhost:8000/mcp/tools)

