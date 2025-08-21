import sys
import json
import logging
from datetime import datetime
from app.config import settings


class JSONFormatter(logging.Formatter):
    """JSON格式日志格式化器"""
    
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # 添加额外字段
        if hasattr(record, 'task_id'):
            log_entry['task_id'] = record.task_id
        if hasattr(record, 'extra'):
            log_entry.update(record.extra)
            
        return json.dumps(log_entry, ensure_ascii=False)


class SimpleFormatter(logging.Formatter):
    """简单格式日志格式化器"""
    
    def format(self, record):
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        return f"{timestamp} | {record.levelname:8} | {record.module}:{record.funcName}:{record.lineno} - {record.getMessage()}"


def setup_logger():
    """设置日志配置"""
    
    # 创建logger
    logger = logging.getLogger('bili2text')
    logger.setLevel(getattr(logging, settings.log_level.upper()))
    
    # 清除现有处理器
    logger.handlers.clear()
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    
    # 选择格式化器
    if settings.log_format.lower() == 'json':
        formatter = JSONFormatter()
    else:
        formatter = SimpleFormatter()
    
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger


# 初始化日志
logger = setup_logger()
