#!/bin/bash

# ==============================================================================
#      AI Core Modular - Launcher v2.2 (最终修正版)
# ==============================================================================
# v2.2 修正:
# - 【核心修复】: 修复了因参数处理不当导致文件名包含多余引号的严重错误。
#   采用 Bash 数组来定义和传递服务器参数，这是最健壮和正确的做法，
#   确保脚本执行与手动执行命令的效果完全一致。
# ==============================================================================

# --- 1. 项目配置 ---
PYTHON_SCRIPT_NAME="main.py"
DB_CONTAINER_NAME="ai_database_hub"
MODEL_DIR="all-MiniLM-L6-v2"
PIP_MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"

# ##############################################################################
# ### --- 本地视觉模型服务器配置 (已修正) --- ###
# ##############################################################################
MODEL_SERVER_DIR="$HOME/llama.cpp/build-vulkan-new"
MODEL_PATH="/mnt/data/models/Qwen3-VL-30B-A3B-Instruct-1M/Qwen3-VL-30B-A3B-Instruct-1M-UD-TQ1_0.gguf"
MMPROJ_PATH="/mnt/data/models/Qwen3-VL-30B-A3B-Instruct-1M/Qwen3-VL-30B-A3B-Instruct-1M-UD-mmproj-BF16.gguf"
MODEL_SERVER_EXEC="./bin/llama-server"

# 【重大修正】: 使用数组来定义参数，避免引号问题
SERVER_ARGS=(
    --mmproj "${MMPROJ_PATH}"
    -c 16384
    -ngl 60
    --host 0.0.0.0
    --port 8087
    --repeat-penalty 1.1
    --presence-penalty 0.5
    --top-k 40
    --top-p 0.95
    --jinja
)


# --- 脚本主逻辑 ---
clear
echo "========================================================"
echo "    AI Core Modular - Launcher v2.2 (最终修正版)"
echo "========================================================"
echo ""

# --- 步骤 1: 检查、创建并激活虚拟环境 ---
echo "[1/6] 正在设置并激活虚拟环境..."
if [ ! -d "venv" ]; then
    echo ">> 未找到虚拟环境 'venv'，正在创建..."
    python3 -m venv venv || { echo "❌ 严重错误: 创建虚拟环境失败！"; read -p "按任意键退出..."; exit 1; }
fi
source venv/bin/activate
echo "✅ 虚拟环境已激活。"
echo ""

# --- 步骤 2: 安装/更新 Python 依赖 ---
echo "[2/6] 正在安装/更新依赖..."
pip install -r requirements.txt -i ${PIP_MIRROR} || { echo "❌ 严重错误: Python 依赖安装失败！"; read -p "按任意键退出..."; exit 1; }
echo "✅ Python 依赖已是最新。"
echo ""

# --- 步骤 3: 检查数据库容器 ---
echo "[3/6] 正在检查数据库容器 (${DB_CONTAINER_NAME})..."
if [ -n "$(docker ps -q -f name=^/${DB_CONTAINER_NAME}$)" ]; then
    echo "✅ 数据库正在运行。"
elif [ -n "$(docker ps -aq -f name=^/${DB_CONTAINER_NAME}$)" ]; then
    echo ">> 检测到已停止的数据库，正在重启..."
    docker start ${DB_CONTAINER_NAME}
    echo "✅ 数据库已启动。"
else
    echo "❌ 严重错误: 未找到 Docker 容器 '${DB_CONTAINER_NAME}'！"
    read -p "按任意键退出..."
    exit 1
fi
echo ""

# --- 步骤 4: 检查 Embedding 模型 ---
echo "[4/6] 正在检查本地 Embedding 模型..."
if [ -d "$MODEL_DIR" ]; then
    echo "✅ Embedding 模型文件夹 '${MODEL_DIR}' 已找到。"
else
    echo "❌ 错误: Embedding 模型文件夹 '${MODEL_DIR}' 丢失！"
    read -p "按任意键退出..."
    exit 1
fi
echo ""

# --- 步骤 5: 检查并启动 LLM (视觉模型) 服务器 ---
echo "[5/6] 正在检查本地视觉模型服务器 (llama-server)..."
if pgrep -f "llama-server -m ${MODEL_PATH}" > /dev/null; then
    echo "✅ 本地视觉模型服务器已在运行。"
else
    echo ">> 服务器未运行，正在后台启动..."
    (
      # 【重大修正】: 使用 "${SERVER_ARGS[@]}" 来正确传递所有参数
      cd "${MODEL_SERVER_DIR}" && nohup ${MODEL_SERVER_EXEC} -m "${MODEL_PATH}" "${SERVER_ARGS[@]}" > llama-server.log 2>&1 &
    )
    echo ">> 正在等待服务器初始化 (等待15秒)..."
    sleep 15 # 视觉模型加载可能更慢，增加等待时间
    if pgrep -f "llama-server -m ${MODEL_PATH}" > /dev/null; then
        echo "✅ 服务器成功启动！日志: ${MODEL_SERVER_DIR}/llama-server.log"
    else
        echo "❌ 严重错误: 启动本地视觉模型服务器失败！"
        echo "   请检查日志: ${MODEL_SERVER_DIR}/llama-server.log"
        tail -n 20 "${MODEL_SERVER_DIR}/llama-server.log"
        read -p "按任意键退出..."
        exit 1
    fi
fi
echo ""

# --- 步骤 6: 启动主程序 ---
echo "[6/6] 正在启动 Python 主程序: ${PYTHON_SCRIPT_NAME}..."
echo "-------------------------- [ 程序日志开始 ] --------------------------"
echo ""
python "${PYTHON_SCRIPT_NAME}"

# --- 脚本结束 ---
echo ""
echo "-------------------------- [  程序日志结束  ] --------------------------"
read -p "程序已执行完毕。按任意键退出..."
