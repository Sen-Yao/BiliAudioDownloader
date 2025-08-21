import os
import subprocess
import yt_dlp
from typing import Tuple, Optional
from app.config import settings
from app.logger import logger


class VideoService:
    """视频处理服务"""
    
    def download_video(self, bv_number: str, task_id: str) -> Tuple[bool, str]:
        """
        下载B站视频
        
        Args:
            bv_number: B站视频BV号
            task_id: 任务ID
            
        Returns:
            (success, message): 下载结果和消息
        """
        try:
            # 创建下载目录
            download_dir = os.path.join(settings.temp_dir, task_id)
            os.makedirs(download_dir, exist_ok=True)
            
            # 配置yt-dlp选项
            ydl_opts = {
                'format': 'bestaudio/best',  # 优先下载最佳音频
                'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
                'verbose': True,
                'extractaudio': True,  # 提取音频
                'audioformat': 'wav',  # 转换为WAV格式
                'socket_timeout': 30,  # 超时设置
                'retries': 3,  # 重试次数
                'fragment_retries': 3,  # 分片重试次数
                'http_chunk_size': 10485760,  # 10MB分片
            }
            
            # 优先使用环境变量中的cookies
            if settings.bilibili_cookies:
                # 创建临时cookies文件
                temp_cookies_file = os.path.join(download_dir, 'temp_cookies.txt')
                with open(temp_cookies_file, 'w', encoding='utf-8') as f:
                    f.write(settings.bilibili_cookies)
                ydl_opts['cookies'] = temp_cookies_file
                logger.info("使用环境变量中的cookies", extra={"task_id": task_id})
            else:
                logger.warning("未找到cookies配置，将尝试直接下载（可能只能下载低分辨率视频）", extra={"task_id": task_id})
            
            # 构建URL
            video_url = f"https://www.bilibili.com/video/{bv_number}"
            
            logger.info(f"开始下载视频: {video_url}", extra={"task_id": task_id})
            logger.info(f"yt-dlp选项: {ydl_opts}", extra={"task_id": task_id})
            
            # 下载视频
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info("yt-dlp实例创建成功", extra={"task_id": task_id})
                
                try:
                    # 直接下载，不预先获取信息
                    logger.info("开始下载视频...", extra={"task_id": task_id})
                    info = ydl.extract_info(video_url, download=True)
                    video_title = info.get('title', 'unknown')
                    video_path = ydl.prepare_filename(info)
                    
                except Exception as e:
                    logger.warning(f"第一次下载尝试失败: {str(e)}", extra={"task_id": task_id})
                    
                    # 如果第一次失败，尝试更简单的配置
                    logger.info("尝试使用简化配置重新下载...", extra={"task_id": task_id})
                    simple_opts = {
                        'format': 'worst',  # 使用最差质量，通常更容易下载
                        'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
                        'socket_timeout': 60,  # 增加超时时间
                        'retries': 5,  # 增加重试次数
                    }
                    
                    # 添加cookies如果可用
                    if settings.bilibili_cookies:
                        temp_cookies_file = os.path.join(download_dir, 'temp_cookies.txt')
                        with open(temp_cookies_file, 'w', encoding='utf-8') as f:
                            f.write(settings.bilibili_cookies)
                        simple_opts['cookies'] = temp_cookies_file
                    
                    with yt_dlp.YoutubeDL(simple_opts) as ydl_simple:
                        try:
                            info = ydl_simple.extract_info(video_url, download=True)
                            video_title = info.get('title', 'unknown')
                            video_path = ydl_simple.prepare_filename(info)
                        except Exception as e2:
                            logger.error(f"简化下载也失败: {str(e2)}", extra={"task_id": task_id})
                            raise Exception(f"所有下载方法都失败: {str(e)} -> {str(e2)}")
            
            logger.info(f"视频下载完成: {video_title}", extra={"task_id": task_id})
            logger.info(f"视频文件路径: {video_path}", extra={"task_id": task_id})
            return True, f"视频下载完成: {video_title}"
            
        except Exception as e:
            error_msg = f"视频下载失败: {str(e)}"
            logger.error(error_msg, extra={"task_id": task_id})
            return False, error_msg
    
    def extract_audio(self, task_id: str, bv_number: str) -> Tuple[bool, str, Optional[str]]:
        """
        从视频中提取音频
        
        Args:
            task_id: 任务ID
            bv_number: B站视频BV号
            
        Returns:
            (success, message, audio_path): 提取结果、消息和音频文件路径
        """
        try:
            # 查找视频或音频文件
            video_dir = os.path.join(settings.temp_dir, task_id)
            media_files = [f for f in os.listdir(video_dir) if f.endswith(('.mp4', '.flv', '.webm', '.m4a', '.mp3', '.wav'))]
            
            if not media_files:
                error_msg = "未找到媒体文件"
                logger.error(error_msg, extra={"task_id": task_id})
                return False, error_msg, None
            
            media_path = os.path.join(video_dir, media_files[0])
            audio_path = os.path.join(video_dir, f"{bv_number}.wav")
            
            logger.info(f"开始处理音频: {media_path}", extra={"task_id": task_id})
            
            # 使用ffmpeg处理音频
            cmd = [
                'ffmpeg', '-i', media_path,
                '-vn',  # 不包含视频
                '-acodec', 'pcm_s16le',  # 音频编码为PCM
                '-ar', '16000',  # 采样率16kHz
                '-ac', '1',  # 单声道
                '-y',  # 覆盖输出文件
                audio_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"音频提取完成: {audio_path}", extra={"task_id": task_id})
                return True, "音频提取完成", audio_path
            else:
                error_msg = f"音频提取失败: {result.stderr}"
                logger.error(error_msg, extra={"task_id": task_id})
                return False, error_msg, None
                
        except Exception as e:
            error_msg = f"音频提取时发生错误: {str(e)}"
            logger.error(error_msg, extra={"task_id": task_id})
            return False, error_msg, None
    
    def split_audio(self, audio_path: str, task_id: str, slice_length: int = 45000) -> Tuple[bool, str, Optional[str]]:
        """
        分割音频文件
        
        Args:
            audio_path: 音频文件路径
            task_id: 任务ID
            slice_length: 切片长度（毫秒）
            
        Returns:
            (success, message, slices_dir): 分割结果、消息和切片目录
        """
        try:
            # 创建切片目录
            slices_dir = os.path.join(settings.temp_dir, task_id, "slices")
            os.makedirs(slices_dir, exist_ok=True)
            
            logger.info(f"开始分割音频: {audio_path}", extra={"task_id": task_id})
            
            # 使用ffmpeg分割音频
            cmd = [
                'ffmpeg', '-i', audio_path,
                '-f', 'segment',
                '-segment_time', str(slice_length / 1000),  # 转换为秒
                '-c:a', 'pcm_s16le',  # 保持PCM编码
                '-ar', '16000',  # 采样率16kHz
                '-ac', '1',  # 单声道
                '-y',
                os.path.join(slices_dir, '%03d.wav')
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                # 获取切片文件列表
                slice_files = sorted([f for f in os.listdir(slices_dir) if f.endswith('.wav')])
                logger.info(f"音频分割完成，共 {len(slice_files)} 个切片", extra={"task_id": task_id})
                return True, f"音频分割完成，共 {len(slice_files)} 个切片", slices_dir
            else:
                error_msg = f"音频分割失败: {result.stderr}"
                logger.error(error_msg, extra={"task_id": task_id})
                return False, error_msg, None
                
        except Exception as e:
            error_msg = f"音频分割时发生错误: {str(e)}"
            logger.error(error_msg, extra={"task_id": task_id})
            return False, error_msg, None
    

    
    def cleanup_temp_files(self, task_id: str):
        """清理临时文件"""
        try:
            temp_dir = os.path.join(settings.temp_dir, task_id)
            if os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir)
                logger.info(f"清理临时文件: {temp_dir}", extra={"task_id": task_id})
        except Exception as e:
            logger.warning(f"清理临时文件失败: {str(e)}", extra={"task_id": task_id})


# 全局服务实例
video_service = VideoService()
