# syntax=docker/dockerfile:1.7

# 使用与本地开发环境一致的官方Python 3.14运行时
FROM python:3.14.6-slim

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

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖。
RUN pip install --no-cache-dir -r requirements.txt

# 安装固定版本的Ts运行时到当前Python环境
COPY scripts/ ./scripts/
RUN python scripts/install_ts.py

# 复制项目文件
COPY app.py .
COPY dashboard/ ./dashboard/
COPY data/ ./data/

# 创建必要的目录
RUN mkdir -p /app/logs /app/temp /app/config

# 暴露Streamlit默认端口
EXPOSE 8501

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# 运行Streamlit应用
CMD ["python", "scripts/run_htfa.py", "--server.headless", "true", "--server.address", "0.0.0.0", "--server.port", "8501"]
