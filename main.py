# main.py (最终正确版)

import os
import sys
import asyncio
import threading
import subprocess
import pyperclip
from pathlib import Path
import traceback
from core import hotkey_handlers

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    print("❌ Critical Error: 'watchdog' library not found. Please run 'pip install watchdog'.")

from config import settings, TRIGGER_FILES
from core import state
from core import ai_services
from core import audio_services
from core import database_manager
from core import system_services
from utils.helpers import Colors, safe_notification


class AsyncFileTriggerHandler(FileSystemEventHandler):
    """
    [ASYNC] Watches for trigger files and calls the corresponding async function.
    """
    def __init__(self, loop):
        self.loop = loop
        self.function_map = {
            # --- AI Power Tools ---
            str(TRIGGER_FILES["translate_to_en"]): create_async_hotkey_handler(
                hotkey_handlers.translate_to_en
            ),
            str(TRIGGER_FILES["translate_to_zh"]): create_async_hotkey_handler(
                hotkey_handlers.translate_to_zh
            ),
            str(TRIGGER_FILES["optimize_prompt"]): create_async_hotkey_handler(
                hotkey_handlers.optimize_prompt
            ),
            str(TRIGGER_FILES["get_concise_answer"]): create_async_hotkey_handler(
                hotkey_handlers.get_concise_answer
            ),
            # --- Personal Security & Context ---
            str(TRIGGER_FILES["personal_risk_analysis"]): create_async_hotkey_handler(
                hotkey_handlers.personal_risk_analysis
            ),
            str(TRIGGER_FILES["export_range_context"]): create_async_hotkey_handler(
                hotkey_handlers.export_context_by_range
            ),
            # --- Data Mappings ---
            str(TRIGGER_FILES["save_input"]): create_async_hotkey_handler(
                hotkey_handlers.save_input
            ),
            str(TRIGGER_FILES["save_output"]): create_async_hotkey_handler(
                hotkey_handlers.save_output
            ),
            str(TRIGGER_FILES["save_thought_process"]): create_async_hotkey_handler(
                hotkey_handlers.save_thought_process
            ),
            str(TRIGGER_FILES["cancel_turn"]): hotkey_handlers.cancel_last_turn,
            str(TRIGGER_FILES["mark_high_quality"]): hotkey_handlers.mark_as_high_quality,
            # --- Audio Mappings ---
            str(TRIGGER_FILES["read_aloud"]): create_async_hotkey_handler(
                hotkey_handlers.read_text_aloud
            ),
            str(TRIGGER_FILES["toggle_read_aloud"]): hotkey_handlers.toggle_read_aloud_mode,
            str(TRIGGER_FILES["voice_to_text"]): hotkey_handlers.voice_to_text_workflow,
            str(TRIGGER_FILES["meeting_mode"]): hotkey_handlers.toggle_meeting_mode,
            # --- Advanced Search Mappings ---
            str(TRIGGER_FILES["codebase_search"]): create_async_hotkey_handler(
                hotkey_handlers.search_codebase
            ),
            str(TRIGGER_FILES["personal_memory_advisor"]): create_async_hotkey_handler(
                hotkey_handlers.analyze_personal_history
            ),
            str(TRIGGER_FILES["talent_pool_search"]): create_async_hotkey_handler(
                hotkey_handlers.find_and_search_talent_pools
            ),
            str(TRIGGER_FILES["import_constitution_principle"]): create_async_hotkey_handler(
                hotkey_handlers.import_constitution_principle
            ),
            str(TRIGGER_FILES["phrase_expander"]): create_async_hotkey_handler(
                hotkey_handlers.expand_phrase
            ),
            str(TRIGGER_FILES["power_search_and_answer"]): create_async_hotkey_handler(
                hotkey_handlers.power_search_and_answer
            ),
            str(TRIGGER_FILES["add_phrase"]): create_async_hotkey_handler(
                hotkey_handlers.add_phrase
            ),
            str(TRIGGER_FILES["add_full_content"]): create_async_hotkey_handler(
                hotkey_handlers.add_full_content
            ),
            str(TRIGGER_FILES["delete_phrase_mapping"]): create_async_hotkey_handler(
                hotkey_handlers.delete_phrase_mapping
            ),
            str(TRIGGER_FILES["free_conversation"]): create_async_hotkey_handler(
                hotkey_handlers.free_conversation
            ),

        }
        print(">> [Async System] Hotkey file watcher initialized.")

    def on_created(self, event):
        if not event.is_directory and event.src_path in self.function_map:
            print(f"\n>> [Async Signal] Received task: {Path(event.src_path).name}")
            asyncio.run_coroutine_threadsafe(
                self._handle_event(event.src_path), self.loop
            )

    async def _handle_event(self, src_path):
        try:
            handler = self.function_map.get(src_path)
            if not handler: return
            if asyncio.iscoroutinefunction(handler):
                await handler()
            elif callable(handler):
                await asyncio.to_thread(handler)
            if os.path.exists(src_path):
                os.unlink(src_path)
        except Exception as e:
            print(f"❌ {Colors.RED}[Handler Error] An error occurred while processing task for {Path(src_path).name}:{Colors.ENDC}")
            traceback.print_exc()

def create_async_hotkey_handler(target_func, *args):
    """
    A wrapper that retrieves selected text and then calls the async target function.
    """
    async def handler():
        def _get_text():
            text = ""
            try:
                text = subprocess.run(["xclip", "-o", "-selection", "primary"], capture_output=True, text=True, check=True).stdout
            except Exception:
                try:
                    text = subprocess.run(["wl-paste", "-p"], capture_output=True, text=True, check=True).stdout
                except Exception:
                    text = pyperclip.paste()
            return text.strip()

        text_to_process = await asyncio.to_thread(_get_text)

        if text_to_process:
            if asyncio.iscoroutinefunction(target_func):
                await target_func(text_to_process, *args)
            else:
                await asyncio.to_thread(target_func, text_to_process, *args)
        else:
            await safe_notification("No Text Found", "Please select or copy text first.")
    return handler


async def main():
    """The main asynchronous entry point for the entire application."""
    os.system("cls" if os.name == "nt" else "clear")
    print("=" * 70)
    print("      AI Core v8.0 - High-Performance Asynchronous Edition")
    print("=" * 70)

    if not WATCHDOG_AVAILABLE:
        sys.exit(1)
        
    system_services.export_all_databases_to_markdown()
    
    # --- 【【【 启动逻辑最终修复版：顺序启动，确保依赖关系 】】】 ---
    print(">> [Async Main] Initializing services sequentially for stability...")

    # 1. 优先初始化所有数据库，包括向量数据库
    if not await database_manager.setup_all_databases():
        print(f"❌ {Colors.RED}Critical Error: Database initialization failed. Exiting.{Colors.ENDC}")
        sys.exit(1)

    # 2. 然后再初始化依赖数据库的 AI 服务和模型
    if not await ai_services.setup_embedding_model():
        print(f"❌ {Colors.RED}Critical Error: Embedding model failed to load. Exiting.{Colors.ENDC}")
        sys.exit(1)
        
    if not await audio_services.setup_whisper_model():
        print(f"❌ {Colors.RED}Critical Error: Whisper model failed to load. Exiting.{Colors.ENDC}")
        sys.exit(1)

    # 3. 最后加载最耗资源的大语言模型
    if not await ai_services.setup_api():
        print(f"❌ {Colors.RED}Critical Error: Main AI service (LLM) failed to load. Exiting.{Colors.ENDC}")
        sys.exit(1)
    
    # --- 【【【 修复结束 】】】 ---

    await system_services.run_startup_maintenance()

    print(">> [Async Main] Starting background transcription processor thread...")
    threading.Thread(target=audio_services.processor_task, daemon=True).start()

    print("✅ [System] Background processor is running.")

    settings.IPC_DIR.mkdir(exist_ok=True)
    for file_path in TRIGGER_FILES.values():
        if file_path.exists():
            file_path.unlink()

    loop = asyncio.get_running_loop()
    state.main_loop = loop
    observer = Observer()
    observer.schedule(AsyncFileTriggerHandler(loop), str(settings.IPC_DIR), recursive=False)
    observer.start()

    async def chat_server_task():
        """
        [ASYNC BACKGROUND TASK]
        一个纯本地的、基于命名管道的聊天服务器，用于响应 chat_client.py 的请求。
        """
        print(f"✅ {Colors.GREEN}[System] Local IPC Chat Server is running.{Colors.ENDC}")
        
        if not settings.CHAT_INPUT_PIPE.exists():
            os.mkfifo(str(settings.CHAT_INPUT_PIPE))
        if not settings.CHAT_OUTPUT_PIPE.exists():
            os.mkfifo(str(settings.CHAT_OUTPUT_PIPE))

        while True:
            try:
                def _read_from_pipe():
                    with open(str(settings.CHAT_INPUT_PIPE), 'r') as fifo:
                        line = fifo.readline()
                        return line.strip()

                question = await asyncio.to_thread(_read_from_pipe)
                
                if question:
                    print(f"\n>> {Colors.CYAN}[IPC Chat Request] Received: {question}{Colors.ENDC}")
                    
                    answer = await ai_services.run_ai_task(question)
                    if not answer:
                        answer = "Sorry, I could not generate a response."

                    def _write_to_pipe(response):
                        with open(str(settings.CHAT_OUTPUT_PIPE), 'w') as fifo:
                            fifo.write(response + '\n')
                    
                    await asyncio.to_thread(_write_to_pipe, answer)
                    print(f">> {Colors.GREEN}[IPC Chat Response] Sent answer back to client.{Colors.ENDC}")

            except Exception as e:
                print(f"❌ {Colors.RED}[IPC Chat Server Error] {e}{Colors.ENDC}")
                await asyncio.sleep(1)

    asyncio.create_task(chat_server_task())
    
    print("✅ [System] Core services are running. Listening for hotkey signals...")
    
    print("\n" + "=" * 70)
    print(f"  {Colors.GREEN}--- Language Learning & Tools ---{Colors.ENDC}")
    print(f"  - [Alt+R] -> {Colors.GREEN}Reads selected text aloud (EN/ZH Auto-Detect){Colors.ENDC}")
    print(f"  - [Alt+T] -> {Colors.YELLOW}Toggle [Translate & Read] Mode{Colors.ENDC}")
    print(f"  - [Alt+G] -> {Colors.CYAN}Record SHORT Voice to Text (Start/Stop){Colors.ENDC}")
    print(f"  - [Alt+B] -> {Colors.RED}TOGGLE Long-Form Meeting Recorder{Colors.ENDC}")
    print(f"\n  {Colors.GREEN}--- AI Power Tools ---{Colors.ENDC}")
    print(f"  - [Alt+Q] -> Translates selected text to {Colors.CYAN}English{Colors.ENDC}")
    print(f"  - [Alt+W] -> Translates selected text to {Colors.GREEN}Chinese{Colors.ENDC}")
    print(f"  - [Alt+E] -> {Colors.BLUE}Optimizes{Colors.ENDC} selected text into a high-quality prompt")
    print(f"  - [Alt+N] -> Gets a hyper-concise {Colors.YELLOW}answer{Colors.ENDC} for selected text")
    print(f"\n  {Colors.MAGENTA}--- Personal Security & Context ---{Colors.ENDC}")
    print(f"  - [Win+Q] -> Imports selected text as a {Colors.BLUE}new Core Principle{Colors.ENDC}")
    print(f"  - [Alt+Z] -> Analyzes text for personal {Colors.MAGENTA}risks & opportunities{Colors.ENDC}")
    print(f"\n  {Colors.MAGENTA}--- AI Training Data Center ---{Colors.ENDC}")
    print(f"  - [Alt+S] -> {Colors.MAGENTA}Saves Input{Colors.ENDC} to corpus.")
    print(f"  - [Win+D] -> {Colors.CYAN}Saves Thought Process{Colors.ENDC} for the last pair.")
    print(f"  - [Alt+D] -> {Colors.MAGENTA}Saves Output{Colors.ENDC}, completes the pair.")
    print(f"  - [Alt+C] -> {Colors.YELLOW}Cancels{Colors.ENDC} the pending input.")
    print(f"  - [Alt+F] -> Marks the last pair as {Colors.BLUE}High-Quality{Colors.ENDC}.")
    print(f"\n  {Colors.BLUE}--- Advanced Search & Export ---{Colors.ENDC}")
    print(f"  - [Alt+J] -> {Colors.BLUE}Memory Advisor:{Colors.ENDC} Analyzes topic against your history")
    print(f"  - [Alt+K] -> {Colors.BLUE}Codebase Search:{Colors.ENDC} High-speed code search")
    print(f"  - [Alt+M] -> {Colors.BLUE}Talent Search:{Colors.ENDC} Scans all vector DBs for candidates")
    print(f"  - [Alt+V] -> {Colors.BLUE}Export History:{Colors.ENDC} Exports dialogue in a selected range")
    print(f"  - [Win+E] -> {Colors.MAGENTA}Power Search:{Colors.ENDC} Solves a problem using Google Search + LLM")
    print(f"  - [Win+Z] -> {Colors.CYAN}Saves new Phrase Shortcut{Colors.ENDC}")
    print(f"  - [Win+X] -> {Colors.CYAN}Adds Full Content to the pending shortcut{Colors.ENDC}")
    print(f"  - [Win+C] -> {Colors.YELLOW}Deletes{Colors.ENDC} an existing phrase mapping by its shortcut")
    print(f"  - [Win+R] -> {Colors.GREEN}自由对话:{Colors.ENDC} 与本地LLM直接对话并存档")
    
    print("\n  Press Ctrl+C to safely exit the program.")
    print("=" * 70 + "\n")

    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        print("\n>> [Async Main] Main task cancelled, shutting down.")
    finally:
        observer.stop()
        observer.join()
        print(">> [System] Exited safely.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n>> [System] Shutdown signal (Ctrl+C) received. Exiting gracefully.")
    finally:
        print(">> [System] Performing final database export to Markdown before closing...")
        system_services.export_all_databases_to_markdown()
        print(">> [System] Exited safely.")
