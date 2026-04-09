# 文件: chat_client.py (锁文件机制最终版)

import os
import sys
import threading
import time
from pathlib import Path
import atexit

# --- 配置 ---
IPC_DIR = Path(os.path.expanduser("~/.ai_ecosystem_ipc"))
CHAT_INPUT_PIPE = IPC_DIR / "chat_input.pipe"
CHAT_OUTPUT_PIPE = IPC_DIR / "chat_output.pipe"
# 【新】定义锁文件路径
LOCK_FILE = IPC_DIR / "chat_client.lock"

# --- ANSI 颜色代码 ---
class Colors:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"

# 【新】全局锁文件句柄
lock_file_handle = None

def cleanup_lock_file():
    """【新】确保在程序退出时释放锁文件。"""
    global lock_file_handle
    if lock_file_handle:
        try:
            lock_file_handle.close()
            if os.path.exists(LOCK_FILE):
                os.remove(LOCK_FILE)
            # print(f"\n{Colors.YELLOW}[System] Lock file released.{Colors.ENDC}") # 退出时无需打印
        except Exception:
            pass

def is_process_running(pid: int) -> bool:
    """【新】检查给定PID的进程是否仍在运行 (仅限Linux/macOS)。"""
    if pid <= 0: return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True

def acquire_lock() -> bool:
    """【新】尝试获取锁文件，确保只有一个实例运行。"""
    global lock_file_handle
    IPC_DIR.mkdir(exist_ok=True)

    try:
        # 这是一个原子操作：如果文件不存在，则创建并打开它；如果存在，则失败。
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        lock_file_handle = os.fdopen(fd, 'w')
        # 将当前进程ID写入锁文件
        lock_file_handle.write(str(os.getpid()))
        lock_file_handle.flush()
        # 注册退出处理函数，确保锁被释放
        atexit.register(cleanup_lock_file)
        return True
    except FileExistsError:
        # 文件已存在，说明可能有另一个实例在运行。
        try:
            with open(LOCK_FILE, 'r') as f:
                pid_str = f.read().strip()
                pid = int(pid_str)

            if is_process_running(pid):
                # 进程确实在运行，本实例需要退出
                print(f"{Colors.YELLOW}[System] Chat window is already running (PID: {pid}). Aborting.{Colors.ENDC}")
                # 无需停留，直接退出
                return False
            else:
                # 进程已死，但锁文件残留（例如上次崩溃了）
                print(f"{Colors.YELLOW}[System] Found stale lock file for dead process {pid}. Cleaning up...{Colors.ENDC}")
                os.remove(LOCK_FILE)
                # 清理后重试一次
                return acquire_lock()
        except (ValueError, FileNotFoundError, TypeError):
            # 锁文件损坏或为空，直接清理并重试
            try:
                os.remove(LOCK_FILE)
            except OSError:
                pass
            return acquire_lock()
    except Exception as e:
        print(f"{Colors.RED}[Fatal Error] Could not acquire lock: {e}{Colors.ENDC}")
        return False


def listen_for_responses(stop_event):
    if not os.path.exists(CHAT_OUTPUT_PIPE):
        try:
            os.mkfifo(CHAT_OUTPUT_PIPE)
        except FileExistsError:
            pass # Pipe already exists, which is fine

    while not stop_event.is_set():
        try:
            with open(CHAT_OUTPUT_PIPE, 'r') as fifo:
                while not stop_event.is_set():
                    response_lines = []
                    # 循环读取直到遇到结束标记
                    while True:
                        line = fifo.readline()
                        if not line: # 如果管道另一端关闭，会立即读到空字符串
                            time.sleep(0.1)
                            break
                        
                        clean_line = line.strip()
                        if clean_line == "__AI_RESPONSE_END__":
                            break # 遇到结束标记，停止读取本次回复
                        else:
                            response_lines.append(line)
                    
                    if response_lines:
                        full_response = "".join(response_lines).strip()
                        # \r 清除当前行, 打印AI回复, 然后重新打印用户提示符
                        print(f"\r{Colors.GREEN}AI:{Colors.ENDC}\n{full_response}\n")
                        print(f"{Colors.CYAN}You:{Colors.ENDC} ", end="", flush=True)

        except Exception:
            if not stop_event.is_set():
                time.sleep(1) # 发生错误时等待一下再重试

def main(initial_question=""):
    # 【核心改动】程序启动的第一件事就是尝试获取锁
    if not acquire_lock():
        # 如果获取失败，说明已有实例在运行，直接退出
        sys.exit(0)

    # 只有成功获取锁的实例才会继续执行下面的代码
    os.system('cls' if os.name == 'nt' else 'clear')
    print("=" * 50)
    print(f"{Colors.GREEN}   AI 临时对话窗口 (AI Interactive Chat){Colors.ENDC}")
    print("=" * 50)
    print("  - 直接输入您的问题，按 Enter 发送。")
    print("  - 输入 'exit' 或 'quit' 或按 Ctrl+C 来关闭。")
    print("-" * 50)

    if not os.path.exists(CHAT_INPUT_PIPE):
        try:
            os.mkfifo(CHAT_INPUT_PIPE)
        except FileExistsError:
            pass

    stop_event = threading.Event()
    listener_thread = threading.Thread(target=listen_for_responses, args=(stop_event,))
    listener_thread.daemon = True
    listener_thread.start()

    try:
        if initial_question:
            print(f"{Colors.CYAN}You (Initial):{Colors.ENDC} {initial_question}")
            with open(CHAT_INPUT_PIPE, 'w') as fifo:
                fifo.write(initial_question + '\n')

        while True:
            # 在输入前先打印提示符
            print(f"{Colors.CYAN}You:{Colors.ENDC} ", end="", flush=True)
            user_input = input()
            if user_input.lower() in ['exit', 'quit']:
                break
            
            try:
                with open(CHAT_INPUT_PIPE, 'w') as fifo:
                    fifo.write(user_input + '\n')
            except BrokenPipeError:
                print(f"\n{Colors.RED}错误: 无法连接到主AI程序。{Colors.ENDC}")
                break

    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        print(f"\n{Colors.YELLOW}正在关闭对话窗口...{Colors.ENDC}")
        stop_event.set()
        # 尝试向输出管道写入一个空字符来唤醒监听线程，使其能检查到stop_event
        try:
            with os.fdopen(os.open(CHAT_OUTPUT_PIPE, os.O_WRONLY | os.O_NONBLOCK), 'w') as f:
                f.write('\n')
        except Exception:
            pass
        listener_thread.join(timeout=1)
        # atexit 会在这里自动调用 cleanup_lock_file()

if __name__ == "__main__":
    initial_prompt = ' '.join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    main(initial_prompt)
