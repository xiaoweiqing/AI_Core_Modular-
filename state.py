# ==============================================================================
#      【【【 THIS IS THE COMPLETE, CORRECTED FILE 】】】
# ==============================================================================
# core/state.py

import asyncio
from queue import Queue
from typing import Optional # <--- THIS IS THE MISSING LINE THAT IS NOW ADDED


# ==============================================================================
#      【【【 为 AI 请求队列添加的新状态 】】】
# ==============================================================================
# 这是一个异步队列，用于存放所有待处理的 AI 请求。
# maxsize=100 意味着最多可以缓存100个请求，防止无限积压。
ai_task_queue = asyncio.Queue(maxsize=100)
# ==============================================================================
# --- AI Model and Client Placeholders ---
llm = None
gemini_model = None # <-- 【【【 新增这一行 】】】
QDRANT_CLIENT = None
EMBEDDING_MODEL = None
WHISPER_MODEL = None


# --- Status Flags ---
IS_QDRANT_DB_READY = False
IS_RECORDING = False
MEETING_MODE_ACTIVE = False
READ_ALOUD_MODE_ENABLED = False

main_loop = None # Will hold a reference to the main asyncio event loop

# --- Database Record Tracking ---
last_record_id = None
last_completed_id = None
current_meeting_session_id: Optional[str] = None # This line caused the error
# ==============================================================================
#      【【【 ADD THIS LINE HERE 】】】
# ==============================================================================
last_phrase_id = None # Tracks the ID of the last phrase added, pending full_content
# ==============================================================================
# --- Concurrency Control ---
app_controller_lock = asyncio.Lock()
db_crud_lock = asyncio.Lock() # This lock is specifically for database CRUD operations

# ---> ADD THIS NEW LINE <---
processing_complete_event = asyncio.Event()
# ---> ADDITION ENDS <---
# --- Inter-thread Communication ---
transcription_queue = Queue()

# --- Process and Thread Placeholders ---
tts_process = None
recorder_thread = None
