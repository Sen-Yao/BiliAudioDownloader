"""
MCP路由 - 通过HTTP接口提供MCP功能
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import json
import uuid
from datetime import datetime

from app.services.video_service import video_service
from app.models import TaskStatus
from app.logger import logger

router = APIRouter(tags=["MCP"])

# 全局任务存储（与现有tasks.py共享）
task_storage = {}

def update_task_status(task_id: str, status: TaskStatus, progress: float, message: str, 
                      result_url: str = None, eta: str = None, processed_slices: int = None, total_slices: int = None):
    """更新任务状态"""
    task_storage[task_id] = {
        "task_id": task_id,
        "status": status,
        "progress": progress,
        "message": message,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "eta": eta,
        "processed_slices": processed_slices,
        "total_slices": total_slices,
        "result_url": result_url
    }

# MCP请求/响应模型
class MCPToolCallRequest(BaseModel):
    name: str
    arguments: Dict[str, Any]

class MCPToolCallResponse(BaseModel):
    content: List[Dict[str, Any]]
    isError: bool = False

class MCPListToolsResponse(BaseModel):
    tools: List[Dict[str, Any]]

class MCPListResourcesResponse(BaseModel):
    resources: List[Dict[str, Any]]

class MCPReadResourceRequest(BaseModel):
    uri: str

class MCPReadResourceResponse(BaseModel):
    contents: List[Dict[str, Any]]
    isError: bool = False

@router.get("/tools", response_model=MCPListToolsResponse, summary="列出MCP工具")
async def list_tools():
    """列出可用的MCP工具"""
    tools = [
        {
            "name": "create_audio_segmentation_task",
            "description": "创建B站视频音频切分任务，将视频下载并切分为30秒音频片段",
            "inputSchema": {
                "type": "object",
                "properties": {
                                    "bv_number": {
                    "type": "string",
                    "description": "B站视频BV号，例如：BV1b1bHzAEdG"
                }
                },
                "required": ["bv_number"]
            }
        },
        {
            "name": "get_task_status",
            "description": "查询音频切分任务的状态和进度",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "任务ID"
                    }
                },
                "required": ["task_id"]
            }
        },
        {
            "name": "get_audio_segments",
            "description": "获取音频切分任务的片段信息",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "任务ID"
                    }
                },
                "required": ["task_id"]
            }
        },
        {
            "name": "cancel_task",
            "description": "取消正在进行的音频切分任务",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "任务ID"
                    }
                },
                "required": ["task_id"]
            }
        }
    ]
    
    return MCPListToolsResponse(tools=tools)

@router.post("/tools/call", response_model=MCPToolCallResponse, summary="调用MCP工具")
async def call_tool(request: MCPToolCallRequest):
    """调用MCP工具"""
    
    if request.name == "create_audio_segmentation_task":
        bv_number = request.arguments.get("bv_number")
        if not bv_number:
            return MCPToolCallResponse(
                content=[{"type": "text", "text": "错误：缺少BV号参数"}],
                isError=True
            )
        
        # 创建任务
        task_id = str(uuid.uuid4())
        update_task_status(task_id, TaskStatus.PENDING, 0, "任务已创建")
        
        # 异步启动任务处理（这里简化处理，实际应该使用后台任务）
        # 在实际应用中，您可能需要使用Celery或其他任务队列
        
        return MCPToolCallResponse(
            content=[
                {
                    "type": "text", 
                    "text": f"✅ 音频切分任务已创建\n\n"
                           f"**任务ID**: `{task_id}`\n"
                           f"**B站视频**: {bv_number}\n"
                           f"**状态**: 准备中\n\n"
                           f"任务正在后台处理中，您可以使用 `get_task_status` 工具查询进度。"
                }
            ]
        )
    
    elif request.name == "get_task_status":
        task_id = request.arguments.get("task_id")
        if not task_id:
            return MCPToolCallResponse(
                content=[{"type": "text", "text": "错误：缺少任务ID参数"}],
                isError=True
            )
        
        task = task_storage.get(task_id)
        if not task:
            return MCPToolCallResponse(
                content=[{"type": "text", "text": f"错误：找不到任务 {task_id}"}],
                isError=True
            )
        
        # 构建状态信息
        status_text = f"**任务状态**: {task['status']}\n"
        status_text += f"**进度**: {task['progress']}%\n"
        status_text += f"**消息**: {task['message']}\n"
        status_text += f"**创建时间**: {task['created_at']}\n"
        status_text += f"**更新时间**: {task['updated_at']}\n"
        
        if task.get('eta'):
            status_text += f"**预计完成**: {task['eta']}\n"
        
        if task.get('processed_slices') and task.get('total_slices'):
            status_text += f"**音频片段**: {task['processed_slices']}/{task['total_slices']}\n"
        
        if task['status'] == TaskStatus.COMPLETED:
            status_text += f"\n✅ **任务完成**！\n"
            status_text += f"您可以使用 `get_audio_segments` 工具获取音频片段信息。\n"
            status_text += f"结果URL: {task.get('result_url', 'N/A')}"
        
        elif task['status'] == TaskStatus.FAILED:
            status_text += f"\n❌ **任务失败**\n"
            status_text += f"错误信息: {task['message']}"
        
        return MCPToolCallResponse(
            content=[{"type": "text", "text": status_text}]
        )
    
    elif request.name == "get_audio_segments":
        task_id = request.arguments.get("task_id")
        if not task_id:
            return MCPToolCallResponse(
                content=[{"type": "text", "text": "错误：缺少任务ID参数"}],
                isError=True
            )
        
        task = task_storage.get(task_id)
        if not task:
            return MCPToolCallResponse(
                content=[{"type": "text", "text": f"错误：找不到任务 {task_id}"}],
                isError=True
            )
        
        if task['status'] != TaskStatus.COMPLETED:
            return MCPToolCallResponse(
                content=[{"type": "text", "text": f"任务尚未完成，当前状态: {task['status']}"}],
                isError=True
            )
        
        segments = task.get('segments', [])
        metadata = task.get('metadata', {})
        
        segments_text = f"**音频片段信息**\n\n"
        segments_text += f"**总片段数**: {metadata.get('segment_count', len(segments))}\n"
        segments_text += f"**总时长**: {metadata.get('total_duration', 0)}秒\n"
        segments_text += f"**B站视频**: {metadata.get('bv_number', 'N/A')}\n\n"
        segments_text += f"**片段列表**:\n"
        
        for i, segment in enumerate(segments):
            segments_text += f"{i+1}. {segment}\n"
        
        return MCPToolCallResponse(
            content=[{"type": "text", "text": segments_text}]
        )
    
    elif request.name == "cancel_task":
        task_id = request.arguments.get("task_id")
        if not task_id:
            return MCPToolCallResponse(
                content=[{"type": "text", "text": "错误：缺少任务ID参数"}],
                isError=True
            )
        
        task = task_storage.get(task_id)
        if not task:
            return MCPToolCallResponse(
                content=[{"type": "text", "text": f"错误：找不到任务 {task_id}"}],
                isError=True
            )
        
        if task['status'] in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            return MCPToolCallResponse(
                content=[{"type": "text", "text": f"任务已处于最终状态，无法取消: {task['status']}"}],
                isError=True
            )
        
        # 更新任务状态为已取消
        update_task_status(task_id, TaskStatus.CANCELLED, 0, "任务已取消")
        
        return MCPToolCallResponse(
            content=[{"type": "text", "text": f"✅ 任务 {task_id} 已成功取消"}]
        )
    
    else:
        return MCPToolCallResponse(
            content=[{"type": "text", "text": f"未知工具: {request.name}"}],
            isError=True
        )

@router.get("/resources", response_model=MCPListResourcesResponse, summary="列出MCP资源")
async def list_resources():
    """列出可用的MCP资源"""
    resources = []
    
    # 列出所有已完成的任务作为资源
    for task_id, task in task_storage.items():
        if task['status'] == TaskStatus.COMPLETED:
            resources.append({
                "uri": f"bili2text://tasks/{task_id}",
                "name": f"音频切分任务 {task_id}",
                "description": f"B站视频 {task.get('metadata', {}).get('bv_number', 'N/A')} 的音频切分结果",
                "mimeType": "application/json"
            })
    
    return MCPListResourcesResponse(resources=resources)

@router.post("/resources/read", response_model=MCPReadResourceResponse, summary="读取MCP资源")
async def read_resource(request: MCPReadResourceRequest):
    """读取MCP资源内容"""
    if request.uri.startswith("bili2text://tasks/"):
        task_id = request.uri.replace("bili2text://tasks/", "")
        task = task_storage.get(task_id)
        
        if not task:
            return MCPReadResourceResponse(
                contents=[{"type": "text", "text": f"找不到任务: {task_id}"}],
                isError=True
            )
        
        # 返回任务详细信息
        task_info = {
            "task_id": task_id,
            "status": task['status'],
            "progress": task['progress'],
            "message": task['message'],
            "created_at": task['created_at'],
            "updated_at": task['updated_at'],
            "segments": task.get('segments', []),
            "metadata": task.get('metadata', {})
        }
        
        return MCPReadResourceResponse(
            contents=[{"type": "text", "text": json.dumps(task_info, indent=2, ensure_ascii=False)}]
        )
    
    return MCPReadResourceResponse(
        contents=[{"type": "text", "text": f"不支持的资源URI: {request.uri}"}],
        isError=True
    )
