# B站视频音频切分服务
# 支持HTTP API和MCP协议
# 用于下载B站视频并切分为30秒音频片段

# 多阶段构建 - 构建阶段
FROM python:3.10-alpine as builder

# 设置工作目录
WORKDIR /app

# 安装构建依赖
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    && rm -rf /var/cache/apk/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖到虚拟环境
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 生产阶段 - 使用Alpine基础镜像
FROM python:3.10-alpine

# 添加元数据标签
LABEL maintainer="BiliAudioDownloader Team"
LABEL description="BiliAudioDownloader - B站视频音频切分服务"
LABEL version="1.0.0"

# 创建非root用户
RUN addgroup -g 1000 appuser && \
    adduser -D -s /bin/sh -u 1000 -G appuser appuser

# 设置工作目录
WORKDIR /app

# 安装运行时依赖（使用Alpine包管理器）
RUN apk add --no-cache \
    ffmpeg \
    && rm -rf /var/cache/apk/*

# 从构建阶段复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 复制应用代码
COPY app/ ./app/

# 创建临时文件目录（任务完成后自动清理，无需持久化）
RUN mkdir -p /app/temp && \
    chown -R appuser:appuser /app

# 切换到非root用户
USER appuser

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
