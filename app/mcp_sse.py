from typing import List
import asyncio
import uuid
import json

from fastapi import APIRouter, Request

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
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


@router.post("/messages")
async def handle_messages(request: Request):
    await sse_transport.handle_post_message(
        request.scope, request.receive, request._send
    )


