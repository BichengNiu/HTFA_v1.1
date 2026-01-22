# 使用官方Python 3.11运行时作为基础镜像
FROM python:3.11.5-slim

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
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
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
CMD ["streamlit", "run", "dashboard/app.py", "--server.headless", "true", "--server.address", "0.0.0.0", "--server.port", "8501"]
