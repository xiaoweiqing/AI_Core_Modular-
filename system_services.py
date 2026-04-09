# core/system_services.py (CORRECTED)

import asyncio
import aiosqlite
import traceback
import sqlite3  # <--- 【【【 在这里添加这一行 】】】
from pathlib import Path  # <--- 【【【 在这里添加这一行 】】】
# Import our custom modules
from config import settings # <-- FIX #1: Import 'settings' instead of the whole module
from core import state
from core.hotkey_handlers import process_metadata_and_vectorize
from utils.helpers import Colors

async def run_startup_maintenance():
    """[ASYNC MASTER] Runs all startup checks and cleanup routines concurrently."""
    print("\n--- Running Async System Maintenance ---")
    
    cleanup_tasks = [
        cleanup_old_orphans(),
        cleanup_duplicates()
    ]
    await asyncio.gather(*cleanup_tasks, return_exceptions=True)
    
    await process_pending_tasks_on_startup()
    
    print("--------------------------------------\n")


async def cleanup_duplicates():
    """[ASYNC] Performs startup deduplication on the main corpus database non-blockingly."""
    print(">> [Async System] Checking for duplicate records...")
    try:
        async with state.db_crud_lock:
            # FIX #2: Use 'settings' object to get paths and table names
            async with aiosqlite.connect(str(settings.CORPUS_DB)) as conn:
                query = f"""
                    DELETE FROM {settings.CORPUS_TABLE_NAME}
                    WHERE id IN (
                        SELECT id FROM (
                            SELECT id,
                                   ROW_NUMBER() OVER (PARTITION BY input_text ORDER BY id) as rn
                            FROM {settings.CORPUS_TABLE_NAME}
                        ) t WHERE t.rn > 1
                    )"""
                cursor = await conn.execute(query)
                deleted_count = cursor.rowcount
                await conn.commit()

        if deleted_count > 0:
            print(f"   ✅ [Cleanup] Found and deleted {deleted_count} duplicate record(s).")
        else:
            print("   -> No duplicates found. Database is clean.")
    except Exception as e:
        print(f"   ❌ {Colors.RED}[Deduplication Error] An error occurred: {e}{Colors.ENDC}")
        traceback.print_exc()


async def cleanup_old_orphans():
    """[ASYNC] Cleans up old, unfinished records non-blockingly."""
    print(">> [Async System] Checking for old, incomplete records...")
    try:
        async with state.db_crud_lock:
            # FIX #2: Use 'settings' object
            async with aiosqlite.connect(str(settings.CORPUS_DB)) as conn:
                cursor = await conn.execute(
                    f"DELETE FROM {settings.CORPUS_TABLE_NAME} WHERE status = 'pending_output' AND id < (SELECT MAX(id) - 10 FROM {settings.CORPUS_TABLE_NAME})"
                )
                deleted_count = cursor.rowcount
                await conn.commit()
        
        if deleted_count > 0:
            print(f"   ✅ [Cleanup] Deleted {deleted_count} old orphaned record(s).")
        else:
            print("   -> No old orphaned records found.")
    except Exception as e:
        print(f"   ❌ {Colors.RED}[Cleanup Error] An error occurred: {e}{Colors.ENDC}")
        traceback.print_exc()


async def process_pending_tasks_on_startup():
    """[ASYNC] Finds and queues pending vectorization tasks using asyncio."""
    print(">> [Async System] Checking for pending background tasks from the last session...")
    try:
        async with state.db_crud_lock:
            # FIX #2: Use 'settings' object
            async with aiosqlite.connect(str(settings.CORPUS_DB)) as conn:
                cursor = await conn.execute(f"SELECT id FROM {settings.CORPUS_TABLE_NAME} WHERE status = 'pending_summaries'")
                pending_records = await cursor.fetchall()

        if pending_records:
            print(f"   -> {Colors.YELLOW}Found {len(pending_records)} pending task(s). Creating async tasks...{Colors.ENDC}")
            for record in pending_records:
                record_id = record[0]
                print(f"      - Creating background task for Record ID: {record_id}")
                asyncio.create_task(process_metadata_and_vectorize(record_id, "output"))
        else:
            print("   -> No pending tasks found. All records are fully processed.")
    except Exception as e:
        print(f"   ❌ {Colors.RED}[Pending Task Error] Failed to create async tasks: {e}{Colors.ENDC}")
        traceback.print_exc()

# core/system_services.py (请替换文件中的这两个函数)

import re
import json
import sqlite3
from pathlib import Path
import traceback
from config import settings
from utils.helpers import Colors

def _sanitize_filename(name: str) -> str:
    """
    [HELPER V4] 强制将输入文本截断到安全长度(60字符)，然后再进行净化。
    """
    if not isinstance(name, str) or not name.strip():
        name = "Untitled"
    safe_length_name = name[:60]
    sanitized = re.sub(r'[\\/*?:"<>|\n\r]', '_', safe_length_name)
    sanitized = re.sub(r'[\s_]+', '_', sanitized).strip('_')
    return sanitized if sanitized else "Untitled"

def export_all_databases_to_markdown():
    """
    [SYNC] [V10 - 最终返璞归真版] 严格按照要求，将每一行完整数据导出为独立的、按时间倒序排列的MD文件。
    - 忠于原文：完整导出每一列数据，不优化格式。
    - 绝对稳健：单行错误绝不中断整个流程。
    - 正确排序：文件名保证最新笔记在最顶端。
    """
    base_export_dir = Path("/home/weiyubin/MuseBox_Storage/总笔记")
    base_export_dir.mkdir(parents=True, exist_ok=True)
    
    print("\n" + "="*70)
    print(f"--- [MD Exporter V10 - Final] Starting direct export to: {base_export_dir} ---")

    TABLES_FOR_ROW_EXPORT = {
        settings.CORPUS_TABLE_NAME, settings.DAILY_RECORDS_TABLE_NAME,
        settings.SEARCH_ARCHIVE_TABLE_NAME, settings.RISK_ASSESSMENT_TABLE_NAME,
        settings.CONCISE_QA_TABLE_NAME, settings.VOICE_TRANSCRIPTS_TABLE_NAME
    }

    db_paths = [getattr(settings, attr) for attr in dir(settings) if isinstance(getattr(settings, attr, None), Path) and str(getattr(settings, attr)).endswith(".sqlite")]

    for db_path in db_paths:
        if not db_path.exists():
            print(f"{Colors.YELLOW}   -> Skipping non-existent DB: {db_path.name}{Colors.ENDC}")
            continue

        try:
            export_subfolder = base_export_dir / db_path.stem
            export_subfolder.mkdir(parents=True, exist_ok=True)
            print(f"{Colors.BLUE}>> Processing DB: {db_path.name} -> Folder: {db_path.stem}{Colors.ENDC}")

            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            
            for table_name_tuple in cursor.fetchall():
                table_name = table_name_tuple[0]

                if table_name in TABLES_FOR_ROW_EXPORT:
                    print(f"   -> Table '{table_name}'. Applying direct row-by-row export...")
                    
                    try:
                        row_cursor = conn.cursor()
                        row_cursor.execute(f"SELECT * FROM {table_name}")
                        rows = row_cursor.fetchall()
                        if not rows: continue

                        headers = [desc[0] for desc in row_cursor.description]
                        header_map = {h: i for i, h in enumerate(headers)}
                        id_idx = header_map.get('id')
                        
                        if id_idx is None:
                            print(f"   -> {Colors.YELLOW}[Warning] Table '{table_name}' has no 'id' column. Skipping.{Colors.ENDC}")
                            continue

                        exported_count = 0
                        for row in rows:
                            try:
                                row_id = row[id_idx]
                                timestamp_str = None
                                summary_text = f"Record_{row_id}"

                                # --- 步骤 1: 优先从 'timestamp' 字段获取时间 (最可靠) ---
                                if 'timestamp' in header_map and row[header_map['timestamp']]:
                                    timestamp_str = str(row[header_map['timestamp']])

                                # --- 步骤 2: 如果是 training_data 且上面没获取到时间，才尝试从 metadata 获取 ---
                                if table_name == settings.CORPUS_TABLE_NAME and not timestamp_str:
                                    try:
                                        # 只解析，不因失败而中断
                                        metadata_content = row[header_map.get('metadata', '')]
                                        if metadata_content:
                                            metadata = json.loads(metadata_content)
                                            timestamp_str = metadata.get("created_at")
                                    except Exception:
                                        pass # 解析失败就失败，不影响

                                # --- 步骤 3: 确定用于文件名的摘要 ---
                                summary_cols = ['input_text', 'user_query', 'ai_summary', 'input_situation']
                                for col in summary_cols:
                                    if col in header_map and row[header_map[col]]:
                                        summary_text = str(row[header_map[col]]).split('\n')[0]
                                        break
                                
                                # --- 步骤 4: 构建保证排序正确的文件名 ---
                                if timestamp_str:
                                    filename_prefix = str(timestamp_str).replace(" ", "_").replace(":", "-")
                                else:
                                    # 备用方案：确保即使没有时间，文件也能被创建
                                    filename_prefix = f"0000-00-00_00-00-00_ID_{row_id}"

                                filename_summary_part = _sanitize_filename(summary_text)
                                filename = f"{filename_prefix}_{filename_summary_part}.md"
                                md_file_path = export_subfolder / filename
                                
                                if md_file_path.exists(): continue

                                # --- 步骤 5: 生成文件内容 (忠于原文，逐列导出) ---
                                md_content = []
                                for header, cell_data in zip(headers, row):
                                    # 列名作为二级标题
                                    md_content.append(f"## {header}")
                                    # 内容原封不动放入代码块
                                    md_content.append(f"```\n{str(cell_data)}\n```\n")
                                
                                with open(md_file_path, 'w', encoding='utf-8') as f:
                                    f.write('\n'.join(md_content))
                                exported_count += 1

                            except Exception as e:
                                # 这是“金钟罩”：如果单行出错，打印警告并继续处理下一行
                                row_id_for_error = row[id_idx] if id_idx is not None and len(row) > id_idx else "Unknown"
                                print(f"   -> {Colors.YELLOW}[Warning] Skipping row ID {row_id_for_error} in table '{table_name}' due to processing error: {e}{Colors.ENDC}")
                                continue

                        if exported_count > 0: print(f"   ✅ Exported {exported_count} new individual records from '{table_name}'.")
                        else: print(f"   -> No new records to export from '{table_name}'. All notes are up to date.")

                    except Exception as table_error:
                         print(f"   ❌ {Colors.RED}[Error] Failed to process table '{table_name}': {table_error}{Colors.ENDC}")
                
                elif 'sqlite_sequence' not in table_name:
                    md_file_path = export_subfolder / f"{table_name}_full_export.md"
                    if md_file_path.exists() and md_file_path.stat().st_mtime > db_path.stat().st_mtime: continue
                    cursor.execute(f"SELECT * FROM {table_name}")
                    rows, headers = cursor.fetchall(), [d[0] for d in cursor.description]
                    if not rows: continue
                    md_content = [f"# Full Export of `{table_name}`\n", f"| {' | '.join(headers)} |", f"|{'|'.join(['---'] * len(headers))}|"]
                    for row in rows: md_content.append(f"| {' | '.join([str(c).replace('|', '\|') for c in row])} |")
                    with open(md_file_path, 'w', encoding='utf-8') as f: f.write('\n'.join(md_content))
                    print(f"   ✅ Exported config table '{table_name}' to a single overview file.")

            conn.close()
        except Exception as e:
            print(f"❌ {Colors.RED}[MD Exporter Error] A critical error occurred while processing {db_path.name}: {e}{Colors.ENDC}")
            traceback.print_exc()

    print("--- [MD Exporter V10] Export process complete. ---")
    print("="*70 + "\n")
