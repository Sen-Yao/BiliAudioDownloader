import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置"""
    
    # 应用基础配置
    app_name: str = "BiliAudioDownloader"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # 服务器配置
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    
    # B站cookies配置
    bilibili_cookies: Optional[str] = None
    
    # 文件存储配置
    temp_dir: str = "./temp"
    
    # 处理配置
    max_file_size: int = 500 * 1024 * 1024  # 500MB
    max_concurrent_tasks: int = 3
    task_timeout: int = 3600  # 1小时
    
    # 日志配置
    log_level: str = "INFO"
    log_format: str = "json"
    
    # 安全配置
    api_key_header: str = "X-API-Key"
    enable_auth: bool = False
    cors_origins: list = ["*"]
    
    # Redis配置
    redis_url: Optional[str] = None
    celery_broker_url: Optional[str] = None
    celery_result_backend: Optional[str] = None
    
    # Whisper配置
    whisper_model: str = "small"
    whisper_language: str = "zh"
    whisper_service_url: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        env_prefix = "BILI2TEXT_"
        
        # 环境变量映射
        fields = {
            "bilibili_cookies": {"env": "BILIBILI_COOKIES"},
            "debug": {"env": "DEBUG"},
            "log_level": {"env": "LOG_LEVEL"},
            "host": {"env": "HOST"},
            "port": {"env": "PORT"},
            "workers": {"env": "WORKERS"},
        }


# 全局配置实例
settings = Settings()
