import os
import time
from datetime import datetime, timedelta
import uuid
import os
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from app.services.video_service import video_service
from app.models import TaskStatus, TaskRequest, TaskResponse, TaskStatusResponse, AudioSegmentResponse
from app.logger import logger
from app.config import settings


# 任务存储（用于简单的任务状态管理）
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

def process_video_task(task_id: str, bv_number: str):
    """
    处理视频下载和音频切分任务
    
    Args:
        task_id: 任务ID
        bv_number: B站视频BV号
    """
    start_time = time.time()
    
    try:
        # 更新任务状态为下载中
        update_task_status(task_id, TaskStatus.DOWNLOADING, 0, "准备处理")
        logger.info(f"开始处理任务: {task_id}", extra={"task_id": task_id})
        
        # 1. 下载视频
        success, message = video_service.download_video(bv_number, task_id)
        if not success:
            raise Exception(f"视频下载失败: {message}")
        
        update_task_status(task_id, TaskStatus.PROCESSING, 30, "视频下载完成，正在提取音频")
        
        # 2. 提取音频
        success, message, audio_path = video_service.extract_audio(task_id, bv_number)
        if not success:
            raise Exception(f"音频提取失败: {message}")
        
        update_task_status(task_id, TaskStatus.PROCESSING, 60, "音频提取完成，正在切分音频")
        
        # 3. 分割音频
        success, message, slices_dir = video_service.split_audio(audio_path, task_id)
        if not success:
            raise Exception(f"音频分割失败: {message}")
        
        # 获取切片数量和总时长
        slice_files = sorted([f for f in os.listdir(slices_dir) if f.endswith('.wav')])
        total_slices = len(slice_files)
        
        # 计算总时长（假设每个片段30秒）
        total_duration = total_slices * 30
        
        # 构建片段文件路径列表（相对于容器内的路径）
        segments = [os.path.join(slices_dir, f) for f in slice_files]
        
        # 构建元数据
        metadata = {
            "total_duration": total_duration,
            "segment_count": total_slices,
            "bv_number": bv_number,
            "task_id": task_id
        }
        
        # 计算处理时间
        duration = time.time() - start_time
        
        # 任务完成
        update_task_status(
            task_id, TaskStatus.COMPLETED, 100, "音频切分完成",
            result_url=f"/api/v1/tasks/{task_id}/segments"
        )
        
        # 保存结果到任务存储
        task_storage[task_id]["segments"] = segments
        task_storage[task_id]["metadata"] = metadata
        
        logger.info(f"任务完成: {task_id}, 耗时: {duration:.2f}秒, 片段数: {total_slices}", extra={"task_id": task_id})
        
    except Exception as e:
        # 任务失败
        duration = time.time() - start_time
        error_message = str(e)
        
        logger.error(f"任务失败: {task_id}, 错误: {error_message}", extra={"task_id": task_id})
        
        # 清理临时文件
        try:
            video_service.cleanup_temp_files(task_id)
        except:
            pass
        
        # 更新任务状态为失败
        update_task_status(task_id, TaskStatus.FAILED, 0, f"任务失败: {error_message}")


# API路由
router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("/", response_model=TaskResponse)
async def create_task(request: TaskRequest, background_tasks: BackgroundTasks) -> TaskResponse:
    """创建视频下载和音频切分任务"""
    try:
        task_id = str(uuid.uuid4())
        logger.info(f"创建新任务: {task_id}, BV号: {request.bv_number}")
        
        # 初始化任务状态
        update_task_status(task_id, TaskStatus.PENDING, 0, "任务已创建，正在排队处理")
        
        # 启动后台任务
        background_tasks.add_task(
            process_video_task,
            task_id=task_id,
            bv_number=request.bv_number
        )
        
        return TaskResponse(
            task_id=task_id,
            status=TaskStatus.PENDING,
            message="任务已创建，正在排队处理",
            created_at=datetime.now()
        )
        
    except Exception as e:
        logger.error(f"创建任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """获取任务状态"""
    if task_id not in task_storage:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return TaskStatusResponse(**task_storage[task_id])


@router.get("/{task_id}/segments", response_model=AudioSegmentResponse)
async def get_audio_segments(task_id: str) -> AudioSegmentResponse:
    """获取音频片段信息"""
    if task_id not in task_storage:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task_info = task_storage[task_id]
    if task_info["status"] != TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="任务尚未完成")
    
    if "segments" not in task_info or "metadata" not in task_info:
        raise HTTPException(status_code=404, detail="音频片段信息不存在")
    
    return AudioSegmentResponse(
        segments=task_info["segments"],
        metadata=task_info["metadata"]
    )


@router.get("/{task_id}/download/{segment_index}")
async def download_audio_segment(task_id: str, segment_index: int):
    """下载指定的音频片段"""
    if task_id not in task_storage:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task_info = task_storage[task_id]
    if task_info["status"] != TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="任务尚未完成")
    
    if "segments" not in task_info:
        raise HTTPException(status_code=404, detail="音频片段信息不存在")
    
    segments = task_info["segments"]
    if segment_index < 0 or segment_index >= len(segments):
        raise HTTPException(status_code=400, detail="音频片段索引超出范围")
    
    segment_path = segments[segment_index]
    if not os.path.exists(segment_path):
        raise HTTPException(status_code=404, detail="音频片段文件不存在")
    
    filename = os.path.basename(segment_path)
    return FileResponse(segment_path, media_type="audio/wav", filename=filename)



