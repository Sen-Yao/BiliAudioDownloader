import time
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import os

from app.config import settings
from app.logger import logger
from app.models import HealthResponse, ErrorResponse
from app.tasks import router as tasks_router


# 应用启动时间
startup_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info(f"应用启动: {settings.app_name} v{settings.app_version}")
    logger.info(f"日志级别: {settings.log_level}")
    logger.info(f"运行模式: HTTP API + MCP (双模式)")
    
    yield
    
    # 关闭时
    logger.info("应用关闭")


# 创建FastAPI应用
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="B站视频转文字API服务 (支持HTTP API和MCP协议)",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(tasks_router, prefix="/api/v1")

# 自动添加MCP路由（始终启用）
from app.mcp_routes import router as mcp_router
app.include_router(mcp_router, prefix="/mcp")


@app.get("/", summary="根路径")
async def root():
    """API根路径"""
    return {
        "message": "B站视频转文字API服务",
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
        "modes": {
            "http_api": "RESTful API接口",
            "mcp": "Model Context Protocol接口"
        }
    }


@app.get("/health", response_model=HealthResponse, summary="健康检查")
async def health_check():
    """健康检查接口"""
    uptime = time.time() - startup_time
    
    return HealthResponse(
        status="healthy",
        version=settings.app_version,
        timestamp=datetime.now(),
        uptime=uptime
    )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理器"""
    logger.error(f"未处理的异常: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="InternalServerError",
            message="服务器内部错误",
            detail=str(exc),
            timestamp=datetime.now()
        ).model_dump()
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """HTTP异常处理器"""
    logger.warning(f"HTTP异常: {exc.status_code} - {exc.detail}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error="HTTPException",
            message=exc.detail,
            timestamp=datetime.now()
        ).model_dump()
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=settings.workers
    )
