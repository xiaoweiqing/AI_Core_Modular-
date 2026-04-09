#!/bin/bash

# ==============================================================================
#      AI Core - 智能启动器 (Config 联动版)
# ==============================================================================
# 功能：
# 1. 自动激活 'aic-final' Conda 环境
# 2. 读取 config.py 判断 AI 模式 (Local vs Google)
# 3. 如果是 Local 模式，自动启动/检查 llama-server
# 4. 如果是 Google 模式，直接启动主程序 (不浪费资源)
# ==============================================================================

# --- 1. 项目与环境配置 ---
CONDA_ENV_NAME="aic-final"      # Conda 环境名称
PYTHON_SCRIPT_NAME="main.py"    # 主程序文件名
CONFIG_FILE_NAME="config.py"    # 配置文件名

# --- 2. 本地模型配置 (仅在 local 模式下使用) ---
# 请确保这些路径与您之前的设置一致
MODEL_SERVER_DIR="$HOME/llama.cpp/build-vulkan-new"
MODEL_PATH="/mnt/data/model/Qwen3-30B-A3B-Instruct-2507-UD-TQ1_0.gguf"
MODEL_SERVER_EXEC="./bin/llama-server"
# 端口必须与 config.py 中的 local_api_url 一致 (8087)
MODEL_SERVER_ARGS="-c 56666 -ngl 99 --repeat-penalty 1.1 --presence-penalty 0.5 --top-k 40 --top-p 0.95 --host 0.0.0.0 --port 8087"

# --- 颜色定义 ---
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
BLUE="\033[34m"
RESET="\033[0m"

# --- 脚本开始 ---
clear
echo -e "${BLUE}========================================================${RESET}"
echo -e "${BLUE}      AI Core - 智能启动器 (Conda: ${CONDA_ENV_NAME})${RESET}"
echo -e "${BLUE}========================================================${RESET}"
echo ""

# ==============================================================================
# [步骤 1] 激活 Conda 环境
# ==============================================================================
echo -e "[1/4] 正在激活 Conda 环境: ${YELLOW}${CONDA_ENV_NAME}${RESET}..."

# 自动寻找 conda.sh
CONDA_PATH=""
if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    CONDA_PATH="$HOME/miniconda3/etc/profile.d/conda.sh"
elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
    CONDA_PATH="$HOME/anaconda3/etc/profile.d/conda.sh"
elif [ -f "/opt/conda/etc/profile.d/conda.sh" ]; then
    CONDA_PATH="/opt/conda/etc/profile.d/conda.sh"
fi

if [ -n "$CONDA_PATH" ]; then
    source "$CONDA_PATH"
else
    echo -e "   ${YELLOW}⚠️  未找到 conda.sh，尝试直接调用系统 conda...${RESET}"
fi

# 执行激活
conda activate "${CONDA_ENV_NAME}" 2>/dev/null

if [ $? -eq 0 ]; then
    echo -e "   ${GREEN}✅ 环境已激活。${RESET}"
else
    echo -e "   ${RED}❌ 激活失败！请检查环境 '${CONDA_ENV_NAME}' 是否存在。${RESET}"
    read -p "按任意键退出..."
    exit 1
fi
echo ""

# ==============================================================================
# [步骤 2] 智能解析 config.py 并决定策略
# ==============================================================================
echo -e "[2/4] 读取配置文件 (${CONFIG_FILE_NAME})..."

if [ ! -f "${CONFIG_FILE_NAME}" ]; then
    echo -e "   ${RED}❌ 错误：找不到配置文件 ${CONFIG_FILE_NAME}${RESET}"
    exit 1
fi

# 使用 grep 查找配置行。这里会匹配 'ACTIVE_AI_PROVIDER = "local"' (忽略空格)
if grep -q 'ACTIVE_AI_PROVIDER[[:space:]]*=[[:space:]]*"local"' "${CONFIG_FILE_NAME}"; then
    # --- 分支 A: 本地模式 ---
    echo -e "   ${YELLOW}>> 检测到 AI 模式为 'LOCAL'${RESET}"
    echo -e "   >> 正在检查本地模型服务器状态..."

    # 检查 llama-server 是否已经在运行
    if pgrep -f "llama-server -m ${MODEL_PATH}" > /dev/null; then
        echo -e "   ${GREEN}✅ 本地模型服务器已经在运行中。${RESET}"
    else
        echo -e "   ${YELLOW}>> 服务器未运行，正在后台启动...${RESET}"
        echo -e "   >> 模型: $(basename ${MODEL_PATH})"
        
        # 进入目录并后台启动
        (
          cd "${MODEL_SERVER_DIR}" && \
          nohup ${MODEL_SERVER_EXEC} -m "${MODEL_PATH}" ${MODEL_SERVER_ARGS} > llama-server.log 2>&1 &
        )
        
        echo -e "   >> 等待 5 秒让服务器初始化..."
        sleep 5
        
        # 再次检查
        if pgrep -f "llama-server -m ${MODEL_PATH}" > /dev/null; then
            echo -e "   ${GREEN}✅ 服务器启动成功 (PID: $(pgrep -f "llama-server -m ${MODEL_PATH}"))${RESET}"
        else
            echo -e "   ${RED}❌ 严重错误：无法启动本地模型服务器！${RESET}"
            echo "   请检查路径是否正确: ${MODEL_SERVER_DIR}"
            read -p "按任意键退出..."
            exit 1
        fi
    fi

elif grep -q 'ACTIVE_AI_PROVIDER[[:space:]]*=[[:space:]]*"google"' "${CONFIG_FILE_NAME}"; then
    # --- 分支 B: Google 模式 ---
    echo -e "   ${GREEN}>> 检测到 AI 模式为 'GOOGLE'${RESET}"
    echo -e "   ${GREEN}✅ 跳过本地模型启动 (节省显存/内存资源)。${RESET}"
    
else
    # --- 分支 C: 其他/未知 ---
    echo -e "   ${YELLOW}>> 未检测到明确的 'local' 或 'google' 配置，默认跳过本地服务器启动。${RESET}"
fi
echo ""

# ==============================================================================
# [步骤 3] 检查依赖 (可选，为了稳健)
# ==============================================================================
echo -e "[3/4] 快速检查核心依赖..."
# 这里只做一个简单的检查，避免每次都跑 pip install 浪费时间
python -c "import langchain_google_genai; import langchain_community" 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "   ${GREEN}✅ 核心库检查通过。${RESET}"
else
    echo -e "   ${YELLOW}⚠️  警告：似乎缺少部分依赖，正在尝试安装...${RESET}"
    pip install -r requirements.txt
fi
echo ""

# ==============================================================================
# [步骤 4] 启动主程序
# ==============================================================================
echo -e "[4/4] 启动 Python 主程序: ${PYTHON_SCRIPT_NAME}"
echo -e "${BLUE}--------------------------------------------------------${RESET}"
echo ""

python "${PYTHON_SCRIPT_NAME}"

# ==============================================================================
# 脚本结束
# ==============================================================================
echo ""
echo -e "${BLUE}--------------------------------------------------------${RESET}"
echo "程序已退出。"
read -p "按任意键关闭窗口..."
