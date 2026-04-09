# test_connection.py
# 这是一个独立的诊断脚本，用于测试最核心的 Google API 连接问题

import os
import traceback
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

print("="*50)
print(">>> [DIAGNOSTIC SCRIPT] Starting Google API Connection Test...")
print("="*50)

# 1. 加载 .env 文件中的配置
print("\n[Step 1] Loading configuration from .env file...")
load_dotenv()

# 从环境中获取 API 密钥和代理地址
api_key = os.getenv("GOOGLE_AI_KEY")
proxy_url = os.getenv("HTTPS_PROXY")

if not api_key:
    print("❌ FATAL: 'GOOGLE_AI_KEY' not found in .env file. Please check your .env file.")
    exit()
else:
    print("✅ Found GOOGLE_AI_KEY.")

if not proxy_url:
    print("❌ FATAL: 'HTTPS_PROXY' not found in .env file. This is required for Google API mode.")
    exit()
else:
    print(f"✅ Found HTTPS_PROXY: {proxy_url}")

# 2. 强制在程序运行环境中设置代理 (最可靠的方式)
print("\n[Step 2] Forcibly setting proxy in the current environment...")
os.environ['HTTPS_PROXY'] = proxy_url
os.environ['HTTP_PROXY'] = proxy_url
print("✅ Proxy has been set in the environment.")

# 3. 尝试初始化并调用 Google AI 模型
print("\n[Step 3] Initializing ChatGoogleGenerativeAI model...")
try:
    # 使用和主程序完全一致的配置
    llm = ChatGoogleGenerativeAI(
        model="models/gemini-flash-lite-latest",
        google_api_key=api_key,
        request_timeout=60, # 60秒超时
        temperature=0.7
    )
    print("✅ Model initialized successfully.")
    
    print("\n[Step 4] Sending a test message ('Hello, world!')...")
    print("(This step might take a moment, please wait for the result or an error)")

    # 使用最新的 v1.0 消息格式
    messages = [HumanMessage(content="Hello, world!")]
    
    # 执行调用
    response = llm.invoke(messages)
    
    print("\n" + "="*25 + "  ✅ SUCCESS!  " + "="*25)
    print(">>> Received response from Google API:")
    print(f">>> Response Type: {type(response)}")
    print(f">>> Response Content: {response.content}")
    print("="*64)
    print("\n>>> This means your environment, API key, proxy, and installed libraries are all working correctly!")

except Exception as e:
    print("\n" + "="*25 + "  ❌ FAILURE!  " + "="*25)
    print(">>> An error occurred during the API call:")
    print(f">>> Error Type: {type(e)}")
    print(f">>> Error Details: {e}")
    print("\n>>> Full Error Traceback:")
    traceback.print_exc()
    print("="*64)
