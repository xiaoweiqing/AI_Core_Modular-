import os
import sys
import traceback
import asyncio
from typing import Optional
from pathlib import Path
import re
import requests # <--- 确保 requests 被导入

# --- LangChain & Model Imports ---
from langchain_core.messages import HumanMessage
from langchain_community.llms import LlamaCpp
from langchain_google_genai import ChatGoogleGenerativeAI
from sentence_transformers import SentenceTransformer

# --- Internal Imports ---
from config import settings, ACTIVE_AI_PROVIDER, CURRENT_MODEL_NAME, ACTIVE_EMBEDDING_CONFIG
from core import state
from utils.helpers import Colors

# ==============================================================================
# 【【【 1. 使用一个全新的、更简单的Prompt模板 】】】
# ==============================================================================
def apply_simple_chat_template(prompt: str) -> str:
    """
    [V5 - 终极简化版]
    使用一个极其简单和通用的模板，避免复杂的逻辑，以最大限度地提高
    与各种指令微调模型（尤其是Coder类模型）的兼容性。
    我们将完整的、未经修改的原始Prompt直接交给模型。
    """
    # 模板极其简单，只是包裹了原始的、完整的 user prompt
    # 注意：如果新模型 gpt-oss-20b 对 "User:" 有特殊识别，您也可以将模板调整为 f"User: {prompt.strip()}\nAssistant:"
    # 但目前的通用模板通常也有效。
    formatted_prompt = (
        f"<|im_start|>system\nYou are a helpful assistant that provides only the requested output without commentary.<|im_end|>\n"
        f"<|im_start|>user\n{prompt.strip()}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )
    return formatted_prompt

# ==============================================================================
# 【【【 2. 修改核心 AI 任务运行器以屏蔽日志 】】】
# ==============================================================================
async def run_ai_task(prompt: str, provider: Optional[str] = None) -> str | None:
    """
    这是整个应用中调用 AI 的唯一入口。
    [FIXED] 它现在会临时重定向 stderr 来彻底屏蔽 llama.cpp 的性能日志。
    [FIXED] 它现在使用简化的模板函数来提高模型输出质量。
    """
    target_provider = provider or ACTIVE_AI_PROVIDER

    async with state.app_controller_lock:
        try:
            if target_provider == "local":
                llm_instance = state.llm_local
                if not llm_instance: return "Error: Local LLM not ready."

                # 【关键改动】使用新的、简单的模板函数
                formatted_prompt = apply_simple_chat_template(prompt)
                print(f"\n   -> [AI Task Locked] Invoking Local LLM (Streaming)...")

                # 【关键改动】在这里强制屏蔽 C++ 层的日志输出
                original_stderr_fd = sys.stderr.fileno()
                saved_stderr_fd = os.dup(original_stderr_fd)
                try:
                    # 将 stderr 重定向到 /dev/null
                    devnull_fd = os.open(os.devnull, os.O_WRONLY)
                    os.dup2(devnull_fd, original_stderr_fd)
                    os.close(devnull_fd)
                    
                    # 在屏蔽的环境中执行模型调用
                    full_response = ""
                    async for chunk in llm_instance.astream(formatted_prompt):
                        print(chunk, end="", flush=True)
                        full_response += chunk
                    print()

                finally:
                    # 无论如何，都要恢复原始的 stderr，以便能看到真正的错误
                    os.dup2(saved_stderr_fd, original_stderr_fd)
                    os.close(saved_stderr_fd)

                cleaned_text = full_response.strip()
                if "<|im_end|>" in cleaned_text: cleaned_text = cleaned_text.replace("<|im_end|>", "").strip()
                return cleaned_text

            elif target_provider == "google":
                # Google 部分保持不变
                llm_instance = state.llm_google
                if not llm_instance: return "Error: Google LLM not ready."
                print(f"\n   -> [AI Task Locked] Invoking Google Chat Model...")
                messages = [HumanMessage(content=prompt)]
                response = await llm_instance.ainvoke(messages)
                result = response.content if hasattr(response, 'content') else str(response)
                print(result)
                return result.strip()
            
            else:
                return "Error: Invalid AI provider specified."

        except Exception as e:
            print(f"❌ {Colors.RED}[AI Task Error] {e}{Colors.ENDC}")
            traceback.print_exc()
            return f"An error occurred during the AI task: {e}"

# ==============================================================================
# 【【【 3. 修改模型加载函数以适应新模型和参数 】】】
# ==============================================================================
# ==============================================================================
# 【【【 3. 修改模型加载函数以适应新模型和参数 】】】
# ==============================================================================
# ==============================================================================
# 【【【 3. 修改模型加载函数以适应新模型和参数 】】】
# ==============================================================================
async def _setup_local_llm_direct_vulkan():
    """
    [MODIFIED] 根据您的新要求，加载 Qwen3-30B 模型并应用 llama-server 参数。
    [FIXED] verbose 设置为 False 作为第一道防线。
    """
    # 【【【 修改点 1: 更新为您的新模型路径 】】】
    MODEL_PATH = "/mnt/data/model/Qwen3-30B-A3B-Instruct-2507-UD-TQ1_0.gguf"
    
    print(f"{Colors.BLUE}>> [AI Service] Initializing TRUE LOCAL LLM via Vulkan...{Colors.ENDC}")
    print(f">> [AI Service] Model Path: {MODEL_PATH}")

    try:
        def _load_model_sync():
            print(">> [Proxy Cleaner] Local mode: removing any system proxy settings...")
            for proxy_var in ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:
                if proxy_var in os.environ: del os.environ[proxy_var]
            
            # 【【【 修改点 2: 更新 LlamaCpp 参数以匹配您的 llama-server 命令 】】】
            llm = LlamaCpp(
                model_path=MODEL_PATH,
                n_ctx=36666,            # <-- 对应 -c 56666
                n_gpu_layers=99,        # <-- 对应 -ngl 99
                
                # --- 新增和调整的参数 ---
                repeat_penalty=1.1,   # <-- 对应 --repeat-penalty 1.1
                top_k=40,             # <-- 对应 --top-k 40
                top_p=0.95,           # <-- 对应 --top-p 0.95
                
                # --- 保留的默认参数 ---
                n_batch=512,
                temperature=0.3,
                streaming=True,
                verbose=False,        # <-- 仍然保留这个作为好习惯
                
                # 注意: 您命令行中的 presence_penalty=0.5 在当前 LangChain 的 LlamaCpp 
                # 包装器中没有直接对应的参数，因此在此处被省略。
            )
            return llm

        state.llm_local = await asyncio.to_thread(_load_model_sync)
        print(f"✅ {Colors.GREEN}[AI Service] True Local LLM loaded and configured (Verbose OFF).{Colors.ENDC}")
        return True
    except Exception as e:
        # 如果还是遇到显存不足的问题，请优先尝试减小 n_ctx 的值。
        print(f"❌ {Colors.RED}[AI Error] CRITICAL - Failed to load local GGUF model: {e}{Colors.ENDC}")
        traceback.print_exc()
        return False

# ==============================================================================
#      【【【 4. 其他函数保持不变 】】】
# (下面的代码与您之前的文件版本相同，为了完整性而包含)
# ==============================================================================

async def setup_api():
    """根据配置加载相应的 AI 服务。"""
    if ACTIVE_AI_PROVIDER == "google":
        return await _setup_google_api_langchain()
    elif ACTIVE_AI_PROVIDER == "local":
        return await _setup_local_llm_direct_vulkan()
    return False

async def _setup_google_api_langchain():
    print(f"{Colors.BLUE}>> [AI Service] Initializing Google Gemini (Back-to-Basics Proxy Mode)...{Colors.ENDC}")
    if not settings.google_ai_key:
        print(f"❌ {Colors.RED}[AI Error] GOOGLE_AI_KEY not found in .env.{Colors.ENDC}")
        return False
    try:
        def _connect_sync():
            proxy_url = settings.https_proxy or settings.http_proxy
            if not proxy_url:
                raise ValueError("Proxy URL (HTTPS_PROXY) not found in .env file, which is required for Google API mode.")
            print(f">> [Proxy Force-Inject] Setting OS environment proxy to: {proxy_url}")
            os.environ['HTTPS_PROXY'] = proxy_url
            os.environ['HTTP_PROXY'] = proxy_url
            
            print(f">> [Google AI] Configuring with model '{settings.GOOGLE_MODEL_NAME}'...")
            llm = ChatGoogleGenerativeAI(
                model=settings.GOOGLE_MODEL_NAME,
                temperature=0.7,
                google_api_key=settings.google_ai_key,
                request_timeout=60
            )
            return llm

        state.llm_google = await asyncio.to_thread(_connect_sync)
        print(f"✅ {Colors.GREEN}[AI Service] Google Gemini configured successfully! (Model: {settings.GOOGLE_MODEL_NAME}){Colors.ENDC}")
        return True
    except Exception as e:
        print(f"❌ {Colors.RED}[AI Error] Failed to configure Google Gemini: {e}{Colors.ENDC}")
        traceback.print_exc()
        return False

async def setup_embedding_model():
    """[ASYNC] 根据 config.py 中的总开关，加载指定的本地模型。"""
    try:
        model_path = ACTIVE_EMBEDDING_CONFIG["path"]
        if not Path(model_path).is_dir():
            print(f"❌ {Colors.RED}[Embedding Error] Model folder not found at '{model_path}'!{Colors.ENDC}")
            return False

        print(f">> [Async Embedding] Loading model '{CURRENT_MODEL_NAME}' from: '{model_path}'...")
        state.EMBEDDING_MODEL = await asyncio.to_thread(SentenceTransformer, model_path)
        print(f"✅ {Colors.GREEN}[Async Embedding] Model '{CURRENT_MODEL_NAME}' is ready.{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"❌ {Colors.RED}[Async Embedding Error] Failed to load local model: {e}{Colors.ENDC}")
        return False

async def generate_text_vector(text: str) -> list[float] | None:
    """[ASYNC] 生成文本的向量嵌入。"""
    try:
        if not state.EMBEDDING_MODEL:
            print(f"{Colors.RED}[Async Embedding Error] Embedding model not initialized.{Colors.ENDC}")
            return None
        full_vector = await asyncio.to_thread(state.EMBEDDING_MODEL.encode, text)
        return full_vector.tolist()
    except Exception as e:
        print(f"❌ {Colors.RED}[Async Embedding Error] Failed to encode text: {e}{Colors.ENDC}")
        traceback.print_exc()
        return None

async def google_search_task(query: str) -> str:
    print("   -> [API Call] Performing Google Search...")
    api_key = settings.google_search_api_key
    cx = settings.google_search_cx
    if not api_key or not cx:
        return "Error: Google Search API Key or CX is not configured in .env file."
    url = "https://www.googleapis.com/customsearch/v1"
    params = {'key': api_key, 'cx': cx, 'q': query, 'num': 5}
    def _sync_search():
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            search_results = response.json()
            if "items" not in search_results:
                return "No search results found."
            formatted_context = ""
            for i, item in enumerate(search_results["items"]):
                title = item.get('title', 'No Title')
                snippet = item.get('snippet', 'No Snippet').replace('\n', ' ')
                formatted_context += f"Result [{i+1}]: {title}\nSnippet: {snippet}\n\n"
            return formatted_context
        except requests.exceptions.RequestException as e:
            return f"Error: Failed to connect to Google Search API. Details: {e}"
        except Exception as e:
            return f"Error: An unexpected error occurred during the search. Details: {e}"
    return await asyncio.to_thread(_sync_search)
