# syntax=docker/dockerfile:1.7

# Docker 与 Windows 运行时统一使用 Python 3.13.4 和同一精确依赖锁。
FROM python:3.13.4-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    HTFA_DEBUG_MODE=false

# 健康检查使用 curl；Python 依赖只使用二进制或官方镜像可安装产物。
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制唯一精确依赖锁
COPY tooling/requirements/requirements-py313.lock .

# 开发、Windows 发布和 Docker 安装相同的精确版本。
RUN pip install --no-cache-dir -r requirements-py313.lock

# 安装固定版本的Ts运行时到当前Python环境
COPY scripts/ ./scripts/
RUN python scripts/htfa.py install-ts

# 复制项目文件
COPY app.py .
COPY htfa/ ./htfa/
COPY components/ ./components/
COPY data/ ./data/

# 创建必要的目录
RUN mkdir -p /app/logs /app/temp /app/config

# 暴露Streamlit默认端口
EXPOSE 8501

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# 运行Streamlit应用
CMD ["python", "scripts/htfa.py", "start", "--server.headless", "true", "--server.address", "0.0.0.0", "--server.port", "8501"]
