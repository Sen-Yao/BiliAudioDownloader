from typing import Optional, List
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"





class TaskRequest(BaseModel):
    """任务请求模型"""
    bv_number: str = Field(..., description="B站视频BV号", example="BV1b1bHzAEdG")


class TaskResponse(BaseModel):
    """任务响应模型"""
    task_id: str = Field(..., description="任务ID")
    status: TaskStatus = Field(..., description="任务状态")
    message: str = Field(..., description="状态消息")
    created_at: datetime = Field(..., description="创建时间")


class TaskStatusResponse(BaseModel):
    """任务状态响应模型"""
    task_id: str = Field(..., description="任务ID")
    status: TaskStatus = Field(..., description="任务状态")
    progress: float = Field(..., description="进度百分比", ge=0, le=100)
    message: str = Field(..., description="状态消息")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    eta: Optional[str] = Field(None, description="预计完成时间 (格式: 2025-08-16T15:57:12)")
    processed_slices: Optional[int] = Field(None, description="已处理的音频片段数")
    total_slices: Optional[int] = Field(None, description="总音频片段数")
    result_url: Optional[str] = Field(None, description="结果文件下载URL")


class AudioSegmentResponse(BaseModel):
    """音频片段切分结果响应模型"""
    segments: List[str] = Field(..., description="音频片段文件路径列表")
    metadata: dict = Field(..., description="元数据信息")





class HealthResponse(BaseModel):
    """健康检查响应模型"""
    status: str = Field(..., description="服务状态")
    version: str = Field(..., description="API版本")
    timestamp: datetime = Field(..., description="检查时间")
    uptime: float = Field(..., description="运行时间（秒）")


class ErrorResponse(BaseModel):
    """错误响应模型"""
    error: str = Field(..., description="错误类型")
    message: str = Field(..., description="错误消息")
    detail: Optional[str] = Field(None, description="详细信息")
    timestamp: datetime = Field(..., description="错误时间")
