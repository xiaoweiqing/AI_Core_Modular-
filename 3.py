# core/audio_services.py (FINAL CORRECTED VERSION)

import os
import asyncio
import aiosqlite
import sqlite3 # Keep sync sqlite3 for the sync processor_task
import subprocess
import tempfile
import traceback
from pathlib import Path
from typing import Optional # <--- 添加这行缺失的代码
import pyperclip
from faster_whisper import WhisperModel

from config import settings
from core import state
from utils.helpers import Colors, is_primarily_chinese, get_local_time_str, safe_notification

async def setup_whisper_model():
    """[ASYNC] Loads the faster-whisper model from a local folder without blocking."""
    try:
        local_model_path = "./faster-whisper-large-v3-local"
        if not os.path.isdir(local_model_path):
            print(f"❌ {Colors.RED}[Whisper Error] Model folder not found at '{local_model_path}'!{Colors.ENDC}")
            return False

        print(f">> [Async Audio Service] Loading Whisper model in background thread...")
        state.WHISPER_MODEL = await asyncio.to_thread(
            WhisperModel, local_model_path, device="cpu", compute_type="int8"
        )
        print(f"✅ {Colors.GREEN}[Async Audio Service] Whisper model loaded successfully.{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"❌ {Colors.RED}[Whisper Error] Failed to load local model: {e}{Colors.ENDC}")
        return False

# 找到 piper_tts_task 函数，然后用下面这个最终修复版完整替换它

async def piper_tts_task(text: str):
    """
    [最终修复版 - 适配文件播放逻辑]
    使用 Piper TTS 生成音频文件并播放。
    - 它现在会将播放进程正确地存储在 state.tts_process 中。
    - 它不再等待播放完成，而是立即返回，让 hotkey_handlers 可以随时中断。
    """
    # 【核心修复】检查是否已有进程正在播放，如果有，则不执行任何操作。
    # 停止逻辑完全由 hotkey_handlers.py 处理。
    if state.tts_process and state.tts_process.poll() is None:
        print(f"{Colors.YELLOW}[TTS] Playback is already in progress. Ignoring new request.{Colors.ENDC}")
        return

    temp_audio_file = None
    try:
        # 这个同步函数只负责生成音频文件，不负责播放
        def _generate_audio_sync():
            print(f"\n{Colors.BLUE}[Audio Service] Generating TTS audio file...{Colors.ENDC}")
            script_dir = Path("./") # 假设脚本在项目根目录运行
            piper_exe = script_dir / "piper" / "piper"
            
            # 动态选择中英文模型
            if is_primarily_chinese(text):
                model_file = script_dir / "zh_CN-huayan-medium.onnx"
                config_file = script_dir / "zh_CN-huayan-medium.onnx.json"
            else:
                model_file = script_dir / "en_US-lessac-medium.onnx"
                config_file = script_dir / "en_US-lessac-medium.onnx.json"

            # 创建一个临时的 .wav 文件来保存音频
            nonlocal temp_audio_file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fp_audio:
                temp_audio_file = fp_audio.name

            # 构建并执行 Piper 命令
            piper_command = [
                str(piper_exe), "--model", str(model_file),
                "--config", str(config_file), "--output_file", temp_audio_file,
            ]
            
            subprocess.run(
                piper_command, check=True, capture_output=True,
                input=text.encode("utf-8"), timeout=180,
            )
            print(f"   -> [Thread] Audio generated and saved to: {temp_audio_file}")
            # 返回生成好的文件名
            return temp_audio_file

        # 在后台线程中生成音频文件，避免阻塞主线程
        audio_file_path = await asyncio.to_thread(_generate_audio_sync)

        if audio_file_path:
            print("   -> [Async] Starting playback in a new process...")
            # 【核心修复】启动 aplay 进程，并将其存储到全局状态中
            state.tts_process = subprocess.Popen(
                ["aplay", audio_file_path], 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )

            # 【核心修复】启动一个后台任务来监控播放是否结束，并自动清理
            async def _playback_monitor():
                try:
                    # 等待播放进程结束
                    await asyncio.to_thread(state.tts_process.wait)
                    print(f"   -> {Colors.GREEN}[Monitor] Playback finished naturally.{Colors.ENDC}")
                except Exception as e:
                    print(f"   -> {Colors.YELLOW}[Monitor] Playback was likely terminated. Error: {e}{Colors.ENDC}")
                finally:
                    # 无论播放是自然结束还是被中断，都清理文件和状态
                    if os.path.exists(audio_file_path):
                        os.remove(audio_file_path)
                    # 只有当进程是当前这个进程时才清理state，防止覆盖新的播放请求
                    if state.tts_process and state.tts_process.pid == aplay_proc.pid:
                         state.tts_process = None
            
            # 使用 aplay_proc 的局部变量来启动监控器
            aplay_proc = state.tts_process
            asyncio.create_task(_playback_monitor())
        
    except Exception as e:
        print(f"   -> {Colors.RED}An unexpected error occurred during TTS: {e}{Colors.ENDC}")
        if state.main_loop:
            asyncio.run_coroutine_threadsafe(safe_notification("TTS Error", "Failed to generate or play audio."), state.main_loop)
        # 确保即使在生成失败时也清理状态和文件
        if temp_audio_file and os.path.exists(temp_audio_file):
            os.remove(temp_audio_file)
        state.tts_process = None

# ==============================================================================
#      【【【 THIS IS THE MAIN FIX BLOCK 】】】
# ==============================================================================
async def _process_single_file(audio_path_str: str, session_id: Optional[str]):
    """
    [ASYNC WORKER] Handles one audio file.
    It now receives the session_id directly to avoid race conditions.
    """
    try:
        audio_path = Path(audio_path_str)
        print(f"\n{Colors.BLUE}>> [Async Processor] Picked up task: {audio_path.name}{Colors.ENDC}")
        await safe_notification("New Transcription", "Processing audio chunk...")

        segments, info = await asyncio.to_thread(state.WHISPER_MODEL.transcribe, audio_path_str)
        full_text = " ".join(segment.text for segment in segments).strip()

        if full_text:
            is_meeting_chunk = audio_path.name.startswith("rec_")
            prefix = "[Meeting] " if is_meeting_chunk else ""
            final_text = f"{prefix}{full_text}"

            print(f"   -> [Processor] Transcription complete (Lang: {info.language}). Saving to DB.")
            
            # Use the session_id that was passed directly with the file.
            async with aiosqlite.connect(str(settings.VOICE_TRANSCRIPTS_DB)) as conn:
                await conn.execute(
                    f"""INSERT INTO {settings.VOICE_TRANSCRIPTS_TABLE_NAME}
                        (timestamp, language_detected, transcribed_text, session_id)
                        VALUES (?, ?, ?, ?)""",
                    (get_local_time_str(), info.language, final_text, session_id),
                )
                await conn.commit()
            print(f"   -> [Processor] ✅ Transcript saved to database with session ID: {str(session_id)[:8]}...")
            
            if not is_meeting_chunk:
                 await asyncio.to_thread(pyperclip.copy, full_text)
                 await safe_notification("Transcription Complete", "Text copied to clipboard.")
                 print(f"   -> {Colors.GREEN}[Clipboard] ✅ Transcribed text copied!{Colors.ENDC}")
            
            # If this was the final chunk of a meeting, signal completion.
            if audio_path.name.startswith("rec_final"):
                # CRITICAL FIX: event.set() is NOT a coroutine. It's a thread-safe sync method.
                # We can and should call it directly.
                state.processing_complete_event.set()
                print(f"   -> {Colors.CYAN}[Processor] Signaled completion for meeting session.{Colors.ENDC}")
        else:
            print(f"   -> [Processor] {Colors.YELLOW}No speech detected.{Colors.ENDC}")

        if not settings.KEEP_AUDIO_FILES and os.path.exists(audio_path_str):
            os.unlink(audio_path_str)

    except Exception as e:
        print(f"❌ {Colors.RED}[Async Processor Error] Failed to process {Path(audio_path_str).name}: {e}{Colors.ENDC}")
        traceback.print_exc()

def processor_task():
    """
    [STEP 2 - ROBUST WORKER FIX]
    Runs in a dedicated background thread. It is now robust enough to handle
    the unified tuple format (filepath, session_id) from the queue, which is
    essential for both short voice notes and meeting mode to function correctly.
    """
    while True:
        try:
            # 从队列中获取我们统一格式的元组
            item = state.transcription_queue.get()
            
            # 【核心逻辑】安全地解包元组
            # 无论这是来自 Alt+G (session_id=None) 还是 Alt+B (session_id="xxx")
            # 这里的代码都能正确处理，不会再崩溃
            audio_path_str, session_id = item

            # 检查主事件循环是否仍在运行
            if state.main_loop and state.main_loop.is_running():
                # 将两个参数都安全地传递给异步处理函数
                future = asyncio.run_coroutine_threadsafe(
                    _process_single_file(audio_path_str, session_id), state.main_loop
                )
                # 等待异步任务完成，以确保文件被逐个处理
                future.result()
            
            # 标记队列中的这个任务已完成
            state.transcription_queue.task_done()
            
        except Exception as e:
            # 捕获任何潜在的严重错误，打印日志但保持线程存活
            print(f"❌ {Colors.RED}[Audio Processor Thread Error] A critical error occurred: {e}{Colors.ENDC}")
            traceback.print_exc()
# ==============================================================================
#      【【【 END OF FIX BLOCK 】】】
# ==============================================================================
