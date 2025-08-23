from typing import List
import asyncio
import uuid
import json
import time

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

import mcp.server as mcp_server
import mcp.types as types
from mcp.server.sse import SseServerTransport
from pydantic import AnyUrl

from app.models import TaskStatus
from app.tasks import task_storage, update_task_status, process_video_task


router = APIRouter(tags=["MCP-SSE"])


# SSE 传输器，指示客户端将上行消息 POST 到 /mcp/messages
sse_transport = SseServerTransport("/mcp/messages")

# MCP Server 实例
server = mcp_server.Server("BiliAudioDownloader")

# 服务器信息
SERVER_INFO = {
    "name": "BiliAudioDownloader",
    "version": "1.0.0",
    "description": "B站视频音频切分服务 - 支持MCP协议",
    "capabilities": {
        "tools": {},
        "resources": {},
        "prompts": {}
    }
}

# 会话存储
sessions = {}

def generate_session_id():
    """生成会话ID"""
    return str(uuid.uuid4())

def create_mcp_message(event_type: str, data: dict) -> str:
    """创建MCP消息格式"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

@server.list_tools()
async def list_tools() -> List[types.Tool]:
    return [
        types.Tool(
            name="create_audio_segmentation_task",
            description="创建B站视频音频切分任务，将视频下载并切分为30秒音频片段",
            inputSchema={
                "type": "object",
                "properties": {
                    "bv_number": {
                        "type": "string",
                        "description": "B站视频BV号，例如：BV1b1bHzAEdG",
                    }
                },
                "required": ["bv_number"],
            },
        ),
        types.Tool(
            name="get_task_status",
            description="查询音频切分任务的状态和进度",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务ID"}
                },
                "required": ["task_id"],
            },
        ),
        types.Tool(
            name="get_audio_segments",
            description="获取音频切分任务的片段信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务ID"}
                },
                "required": ["task_id"],
            },
        ),
        types.Tool(
            name="cancel_task",
            description="取消正在进行的音频切分任务",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务ID"}
                },
                "required": ["task_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict | None):
    args = arguments or {}

    if name == "create_audio_segmentation_task":
        bv_number = args.get("bv_number")
        if not bv_number:
            return [types.TextContent(type="text", text="错误：缺少BV号参数")]

        task_id = str(uuid.uuid4())
        update_task_status(task_id, TaskStatus.PENDING, 0, "任务已创建")

        # 后台执行实际处理，避免阻塞事件循环
        asyncio.create_task(asyncio.to_thread(process_video_task, task_id, bv_number))

        text = (
            "✅ 音频切分任务已创建\n\n"
            f"任务ID: {task_id}\nB站视频: {bv_number}\n状态: 准备中\n\n"
            "任务正在后台处理中，您可以使用 get_task_status 查询进度。"
        )
        return [types.TextContent(type="text", text=text)]

    if name == "get_task_status":
        task_id = args.get("task_id")
        if not task_id:
            return [types.TextContent(type="text", text="错误：缺少任务ID参数")]

        task = task_storage.get(task_id)
        if not task:
            return [types.TextContent(type="text", text=f"错误：找不到任务 {task_id}")]

        status_text = (
            f"任务状态: {task['status']}\n"
            f"进度: {task['progress']}%\n"
            f"消息: {task['message']}\n"
            f"创建时间: {task['created_at']}\n"
            f"更新时间: {task['updated_at']}\n"
        )
        if task.get("eta"):
            status_text += f"预计完成: {task['eta']}\n"
        if task.get("processed_slices") and task.get("total_slices"):
            status_text += (
                f"音频片段: {task['processed_slices']}/{task['total_slices']}\n"
            )
        if task["status"] == TaskStatus.COMPLETED:
            status_text += "\n✅ 任务完成！\n"
            status_text += "可使用 get_audio_segments 获取音频片段信息。\n"
            status_text += f"结果URL: {task.get('result_url', 'N/A')}"
        elif task["status"] == TaskStatus.FAILED:
            status_text += "\n❌ 任务失败\n"
            status_text += f"错误信息: {task['message']}"

        return [types.TextContent(type="text", text=status_text)]

    if name == "get_audio_segments":
        task_id = args.get("task_id")
        if not task_id:
            return [types.TextContent(type="text", text="错误：缺少任务ID参数")]

        task = task_storage.get(task_id)
        if not task:
            return [types.TextContent(type="text", text=f"错误：找不到任务 {task_id}")]

        if task["status"] != TaskStatus.COMPLETED:
            return [
                types.TextContent(
                    type="text", text=f"任务尚未完成，当前状态: {task['status']}"
                )
            ]

        segments = task.get("segments", [])
        metadata = task.get("metadata", {})

        segments_text = (
            "音频片段信息\n\n"
            f"总片段数: {metadata.get('segment_count', len(segments))}\n"
            f"总时长: {metadata.get('total_duration', 0)}秒\n"
            f"B站视频: {metadata.get('bv_number', 'N/A')}\n\n"
            "片段列表:\n"
        )
        for i, segment in enumerate(segments):
            segments_text += f"{i + 1}. {segment}\n"

        return [types.TextContent(type="text", text=segments_text)]

    if name == "cancel_task":
        task_id = args.get("task_id")
        if not task_id:
            return [types.TextContent(type="text", text="错误：缺少任务ID参数")]

        task = task_storage.get(task_id)
        if not task:
            return [types.TextContent(type="text", text=f"错误：找不到任务 {task_id}")]

        if task["status"] in [
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        ]:
            return [
                types.TextContent(
                    type="text",
                    text=f"任务已处于最终状态，无法取消: {task['status']}",
                )
            ]

        update_task_status(task_id, TaskStatus.CANCELLED, 0, "任务已取消")
        return [types.TextContent(type="text", text=f"✅ 任务 {task_id} 已成功取消")]

    return [types.TextContent(type="text", text=f"未知工具: {name}")]


@server.list_resources()
async def list_resources() -> List[types.Resource]:
    resources: List[types.Resource] = []
    for task_id, task in task_storage.items():
        if task["status"] == TaskStatus.COMPLETED:
            resources.append(
                types.Resource(
                    uri=f"bili2text://tasks/{task_id}",
                    name=f"音频切分任务 {task_id}",
                    description=f"B站视频 {task.get('metadata', {}).get('bv_number', 'N/A')} 的音频切分结果",
                    mimeType="application/json",
                )
            )
    return resources


@server.read_resource()
async def read_resource(uri: AnyUrl) -> str:
    uri_str = str(uri)
    if uri_str.startswith("bili2text://tasks/"):
        task_id = uri_str.replace("bili2text://tasks/", "")
        task = task_storage.get(task_id)
        if not task:
            return json.dumps({"error": f"找不到任务: {task_id}"}, ensure_ascii=False)

        task_info = {
            "task_id": task_id,
            "status": task["status"],
            "progress": task["progress"],
            "message": task["message"],
            "created_at": task["created_at"],
            "updated_at": task["updated_at"],
            "segments": task.get("segments", []),
            "metadata": task.get("metadata", {}),
        }
        return json.dumps(task_info, indent=2, ensure_ascii=False)

    return json.dumps({"error": f"不支持的资源URI: {uri_str}"}, ensure_ascii=False)


@router.get("/sse")
async def handle_sse(request: Request):
    """改进的MCP/SSE端点，符合MCP协议规范"""
    
    async def generate_sse():
        session_id = generate_session_id()
        sessions[session_id] = {
            "created_at": time.time(),
            "last_activity": time.time()
        }
        
        # 发送初始化消息
        init_message = {
            "jsonrpc": "2.0",
            "id": None,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": SERVER_INFO["capabilities"],
                "clientInfo": {
                    "name": "MCP Client",
                    "version": "1.0.0"
                },
                "serverInfo": SERVER_INFO
            }
        }
        
        yield create_mcp_message("message", init_message)
        
        # 发送初始化响应
        init_response = {
            "jsonrpc": "2.0",
            "id": None,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": SERVER_INFO["capabilities"],
                "serverInfo": SERVER_INFO
            }
        }
        
        yield create_mcp_message("message", init_response)
        
        # 发送端点信息
        endpoint_data = {
            "endpoint": f"/mcp/messages?session_id={session_id}"
        }
        yield create_mcp_message("endpoint", endpoint_data)
        
        # 发送ping消息保持连接
        while True:
            try:
                await asyncio.sleep(15)  # 每15秒发送一次ping
                ping_data = {
                    "timestamp": time.time(),
                    "session_id": session_id
                }
                yield create_mcp_message("ping", ping_data)
                
                # 更新会话活动时间
                if session_id in sessions:
                    sessions[session_id]["last_activity"] = time.time()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                error_data = {
                    "error": {
                        "code": -32603,
                        "message": "Internal error",
                        "data": str(e)
                    }
                }
                yield create_mcp_message("error", error_data)
                break
    
    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "X-Accel-Buffering": "no"  # 禁用nginx缓冲
        }
    )

@router.post("/messages")
async def handle_messages(request: Request):
    """处理MCP消息"""
    try:
        body = await request.json()
        
        # 验证JSON-RPC格式
        if not isinstance(body, dict) or "jsonrpc" not in body:
            return Response(
                content=json.dumps({
                    "jsonrpc": "2.0",
                    "id": body.get("id") if isinstance(body, dict) else None,
                    "error": {
                        "code": -32600,
                        "message": "Invalid Request"
                    }
                }),
                media_type="application/json"
            )
        
        # 处理不同的方法
        method = body.get("method")
        params = body.get("params", {})
        request_id = body.get("id")
        
        if method == "tools/list":
            tools = await list_tools()
            tools_data = [tool.model_dump() for tool in tools]
            return Response(
                content=json.dumps({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": tools_data
                    }
                }),
                media_type="application/json"
            )
        
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            if not tool_name:
                return Response(
                    content=json.dumps({
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32602,
                            "message": "Invalid params: missing tool name"
                        }
                    }),
                    media_type="application/json"
                )
            
            # 调用工具
            result = await call_tool(tool_name, arguments)
            content_data = [content.model_dump() for content in result]
            
            return Response(
                content=json.dumps({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": content_data
                    }
                }),
                media_type="application/json"
            )
        
        elif method == "resources/list":
            resources = await list_resources()
            resources_data = [resource.model_dump() for resource in resources]
            return Response(
                content=json.dumps({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "resources": resources_data
                    }
                }),
                media_type="application/json"
            )
        
        elif method == "resources/read":
            uri = params.get("uri")
            if not uri:
                return Response(
                    content=json.dumps({
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32602,
                            "message": "Invalid params: missing uri"
                        }
                    }),
                    media_type="application/json"
                )
            
            content = await read_resource(AnyUrl(uri))
            return Response(
                content=json.dumps({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "contents": [{
                            "type": "text",
                            "text": content
                        }]
                    }
                }),
                media_type="application/json"
            )
        
        else:
            return Response(
                content=json.dumps({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }),
                media_type="application/json"
            )
    
    except json.JSONDecodeError:
        return Response(
            content=json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": "Parse error"
                }
            }),
            media_type="application/json"
        )
    except Exception as e:
        return Response(
            content=json.dumps({
                "jsonrpc": "2.0",
                "id": body.get("id") if isinstance(body, dict) else None,
                "error": {
                    "code": -32603,
                    "message": "Internal error",
                    "data": str(e)
                }
            }),
            media_type="application/json"
        )

@router.options("/sse")
async def handle_sse_options():
    """处理SSE的OPTIONS请求"""
    return Response(
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Cache-Control",
            "Access-Control-Max-Age": "86400"
        }
    )

@router.options("/messages")
async def handle_messages_options():
    """处理消息的OPTIONS请求"""
    return Response(
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "86400"
        }
    )

@router.get("/")
async def mcp_root():
    """MCP服务器根端点 - 提供服务器信息"""
    return {
        "name": SERVER_INFO["name"],
        "version": SERVER_INFO["version"],
        "description": SERVER_INFO["description"],
        "protocol": "mcp",
        "endpoints": {
            "sse": "/mcp/sse",
            "messages": "/mcp/messages",
            "health": "/mcp/health"
        },
        "capabilities": SERVER_INFO["capabilities"]
    }

@router.get("/health")
async def mcp_health():
    """MCP服务器健康检查"""
    return {
        "status": "healthy",
        "server": SERVER_INFO["name"],
        "version": SERVER_INFO["version"],
        "timestamp": time.time(),
        "active_sessions": len(sessions)
    }

@router.get("/discover")
async def mcp_discover():
    """MCP服务器发现端点 - 用于LangFlow等应用发现MCP服务器"""
    return {
        "servers": [
            {
                "name": SERVER_INFO["name"],
                "version": SERVER_INFO["version"],
                "description": SERVER_INFO["description"],
                "transport": "sse",
                "endpoint": "/mcp/sse",
                "capabilities": SERVER_INFO["capabilities"]
            }
        ]
    }


