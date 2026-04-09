#!/bin/bash
# ==============================================================================
#      AI Core - Intelligent Launcher for Conda (v2.0)
# ==============================================================================
#
#   作者: Gemini (根据用户反馈和日志进行最终优化)
#   用途: 自动激活环境，并智能检查、启动、等待所有外部服务准备就绪。
#
# ==============================================================================

# --- [可配置项] ---
CONDA_ENV_NAME="aic-final"
DB_CONTAINER_NAME="ai_database_hub"
PYTHON_SCRIPT_NAME="main.py"
QDRANT_HEALTH_URL="http://localhost:6333"


# --- [脚本主逻辑] ---
clear
echo "================================================================="
echo "   AI Core - Intelligent Conda Launcher v2.0"
echo "================================================================="
echo ""

# --- 步骤 1: 激活 Conda 环境 (保持不变) ---
echo "[1/4] Activating Conda environment: '${CONDA_ENV_NAME}'..."
if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
else
    echo "❌ CRITICAL: Miniconda not found. Please reinstall."
    read -p "Press any key to exit..."; exit 1
fi
conda activate "${CONDA_ENV_NAME}"
if [ $? -ne 0 ]; then
    echo "❌ CRITICAL: Failed to activate Conda environment '${CONDA_ENV_NAME}'."
    read -p "Press any key to exit..."; exit 1
fi
echo "✅ Conda environment activated."
echo ""

# --- 步骤 2: 检查并启动 Qdrant 容器 (保持不变) ---
echo "[2/4] Checking database container '${DB_CONTAINER_NAME}'..."
if ! command -v docker &> /dev/null; then
    echo "❌ CRITICAL: Docker not found. Please install and run Docker."; read -p "Press any key..."; exit 1
fi
if [ -n "$(docker ps -q -f name=^/${DB_CONTAINER_NAME}$)" ]; then
    echo "✅ Database is already running."
elif [ -n "$(docker ps -aq -f name=^/${DB_CONTAINER_NAME}$)" ]; then
    echo ">> Found stopped database, restarting..."
    docker start "${DB_CONTAINER_NAME}"; echo "✅ Database started."
else
    echo ">> Container not found. Starting a new one from 'qdrant/qdrant'..."
    docker run -d --name "${DB_CONTAINER_NAME}" -p 6333:6333 qdrant/qdrant
fi
echo ""

# --- 【【【 全新步骤 3: 数据库健康检查 】】】 ---
echo "[3/4] Waiting for database to become ready..."
ATTEMPTS=0
MAX_ATTEMPTS=15 # 最多等待15秒
while [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
    # 使用 curl 静默模式检查 Qdrant 的健康状态端点
    if curl --silent --fail ${QDRANT_HEALTH_URL} > /dev/null; then
        echo "✅ Database is responsive and ready for connections!"
        break
    fi
    ATTEMPTS=$((ATTEMPTS+1))
    echo "   -> Waiting for database... (${ATTEMPTS}/${MAX_ATTEMPTS})"
    sleep 1
done

if [ $ATTEMPTS -eq $MAX_ATTEMPTS ]; then
    echo "❌ CRITICAL: Database did not become ready in time."
    echo "   Please check Docker and the container logs with: docker logs ${DB_CONTAINER_NAME}"
    read -p "Press any key to exit..."; exit 1
fi
echo ""

# --- 步骤 4: 启动主程序 ---
echo "[4/4] Launching Python application..."
echo "    (The Large Language Model will be loaded internally, please wait...)"
echo "-------------------------- [ Program Log Start ] --------------------------"
echo ""

python "${PYTHON_SCRIPT_NAME}"

# --- 脚本结束 ---
echo ""
echo "-------------------------- [  Program Log End  ] ---------------------------"
read -p "Program has finished. Press any key to exit..."
