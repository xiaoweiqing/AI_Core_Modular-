# ==============================================================================
#      【【【 1. REPLACE your entire import block with this one 】】】
# ==============================================================================
# --- Add these new imports for the web scraper ---
import subprocess # <--- 确保在文件顶部导入 subprocess 模块
import sys  # <--- 添加这一行
import aiosqlite
import uuid
import pyperclip
import asyncio      # The core async library
import aiosqlite    # The async replacement for sqlite3
import json
import uuid
import traceback
import re
import time
from pathlib import Path
from typing import Optional
import numpy as np
import sounddevice as sd
import soundfile as sf
from qdrant_client import models
# At the top of core/hotkey_handlers.py
from core import database_manager # Import the entire module
# Import our custom modules
from config import settings, CURRENT_MODEL_NAME
from core import state
from core import ai_services
from core import audio_services
from utils.helpers import Colors, safe_notification, clean_text, get_local_time_str

try:
    import fast_grep_engine
except ImportError:
    print(f"{Colors.RED}Warning: 'fast_grep_engine' not found. Codebase search (Alt+K) will be disabled.{Colors.ENDC}")
    fast_grep_engine = None


# ==============================================================================
#      【【【 所有函数都已移除外层的 app_controller_lock 】】】
# ==============================================================================

# --- AI-Powered Translation & Prompting Workflows ---

async def translate_to_en(text: str):
    """
    [ASYNC] Handles Alt+Q.
    【已移除顶层业务锁，允许并发提交AI任务】
    """
    print(f"\n{Colors.BLUE}[Async 流水线] 正在执行翻译和分段...{Colors.ENDC}")

    # --- 第一步：专注翻译 ---
    print("   -> [工位 1] 正在获取核心翻译...")
    prompt_for_translation = f"""
Translate the following Chinese text into a single, fluent, natural-sounding English sentence. Output ONLY the translated sentence.
<USER_TEXT_TO_TRANSLATE>
{clean_text(text)}
</USER_TEXT_TO_TRANSLATE>
"""
    full_translation = await ai_services.run_ai_task(prompt_for_translation)

    if not full_translation:
        await safe_notification("Translation Failed", "AI model did not return a translation.")
        return

    await asyncio.to_thread(pyperclip.copy, full_translation)
    print(f"{Colors.YELLOW}--- [ 英文全文 | 已复制到剪贴板 ] ---{Colors.ENDC}")
    print(f"{Colors.CYAN}{full_translation}{Colors.ENDC}\n")
    
    # 自由地创建后台任务，它会被底层的锁安全地排队
    asyncio.create_task(database_manager.log_daily_record("TRANSLATE_EN_PIPELINE", text, full_translation))

    # --- 第二步：专注分段 ---
    try:
        print("   -> [工位 2] 正在为翻译结果生成分段提示...")
        prompt_for_segmentation = f"""
Your ONLY task is to break down the English sentence below into a series of logical phrases for typing.
For each English phrase, also provide its corresponding Chinese meaning.
The entire output MUST be a list of lines. Each line MUST follow this exact format:
English Phrase ||| Chinese Meaning
<ENGLISH_SENTENCE_TO_SEGMENT>
{full_translation}
</ENGLISH_SENTENCE_TO_SEGMENT>
"""
        segment_response = await ai_services.run_ai_task(prompt_for_segmentation)
        
        lines = segment_response.strip().split('\n')
        formatted_chunks_for_print = []
        for line in lines:
            if '|||' in line:
                parts = line.split('|||', 1)
                en_phrase = parts[0].strip()
                zh_meaning = parts[1].strip()
                if en_phrase:
                    # 这是美化的关键：ljust(40)
                    formatted_line = (
                        f"{Colors.RED}{en_phrase.ljust(40)}{Colors.YELLOW}"
                        f"- ({zh_meaning}){Colors.ENDC}"
                    )
                    formatted_chunks_for_print.append(formatted_line)

        if formatted_chunks_for_print:
            await safe_notification("翻译完成", "完整英文已复制，分段提示已生成。")
            print(f"{Colors.YELLOW}--- [ ⌨️ 分段输入提示 ] ---{Colors.ENDC}")
            for line in formatted_chunks_for_print:
                print(line)
        else:
            await safe_notification("翻译完成", "英文已复制，但本次未能生成分段提示。")
    except Exception as e:
        print(f"❌ {Colors.RED}[分段工位错误] {e}{Colors.ENDC}")
        traceback.print_exc()


    if state.READ_ALOUD_MODE_ENABLED:
        asyncio.create_task(read_text_aloud(full_translation))


# ==============================================================================
#      【【【 这是关键修复：增加输入长度安全检查 】】】
# ==============================================================================
# ==============================================================================
#      【【【 最终解决方案：智能分块翻译超长文本 】】】
# ==============================================================================
# ==============================================================================
#      【【【 最终修复：两段式“绝对可靠”分割法 】】】
# ==============================================================================
# ==============================================================================
#      【【【 最终诊断步骤：检查传入的原始文本及长度 】】】
# ==============================================================================
async def translate_to_zh(text: str):
    """
    [ASYNC] Handles Alt+W.
    [FINAL-CLEANED VERSION] 已移除所有诊断代码。
    它现在依赖于 main.py 中修复后的热键处理器来提供完整的文本。
    健壮的分块逻辑被保留，以处理真正超长的输入。
    """
    original_text = clean_text(text)
    SAFE_CHAR_LIMIT = 500  # 为每个AI请求设置一个安全的字符数上限

    # --- 如果文本长度在安全范围内，直接翻译 ---
    if len(original_text) <= SAFE_CHAR_LIMIT:
        print(f"\n{Colors.BLUE}[Async 流水线] 正在执行英译汉 (标准模式)...{Colors.ENDC}")
        prompt = f"""<|system|>
你是一位专业的翻译家。你的任务是将用户的英文消息翻译成流畅、地道的中文。你必须只输出翻译后的文本，不包含任何额外的评论或解释。<|user|>
{original_text}<|assistant|>"""
        final_text = await ai_services.run_ai_task(prompt)

    # --- 如果文本超长，启动两段式分块翻译 ---
    else:
        print(f"\n{Colors.YELLOW}[!] 检测到超长文本 ({len(original_text)} 字符)，启动两段式可靠分块翻译...{Colors.ENDC}")
        await safe_notification("正在处理长文本...", "可靠分块翻译已启动。")

        # 【第一阶段：尝试按句子优雅分割，以保留上下文】
        sentences = re.split(r'(?<=[.?!])\s+', original_text)
        
        # 【第二阶段：处理顽固长块（例如没有标点的长句），进行强制分割】
        text_chunks = []
        for sentence in sentences:
            if len(sentence) > SAFE_CHAR_LIMIT:
                print(f"   -> 检测到顽固长块 (长度 {len(sentence)})，正在进行强制分割...")
                for i in range(0, len(sentence), SAFE_CHAR_LIMIT):
                    text_chunks.append(sentence[i:i+SAFE_CHAR_LIMIT])
            else:
                text_chunks.append(sentence)
        
        # 【优化步骤：重新组合成不超长的、更大的块，以减少API调用次数】
        final_chunks = []
        current_chunk = ""
        for chunk in text_chunks:
            if len(current_chunk) + len(chunk) + 1 > SAFE_CHAR_LIMIT:
                final_chunks.append(current_chunk)
                current_chunk = chunk
            else:
                current_chunk += (" " + chunk) if current_chunk else chunk
        if current_chunk:
            final_chunks.append(current_chunk)

        print(f"   -> 文本已可靠地分割成 {len(final_chunks)} 个块进行处理。")

        # --- 循环翻译所有最终确定的块 ---
        translated_chunks = []
        for i, chunk in enumerate(final_chunks):
            print(f"   -> 正在翻译块 {i+1}/{len(final_chunks)}...")
            prompt = f"""<|system|>
你是一位专业的翻译家。你的任务是将用户的英文消息翻译成流畅、地道的中文。你必须只输出翻译后的文本，不包含任何额外的评论或解释。<|user|>
{chunk}<|assistant|>"""
            translated_chunk = await ai_services.run_ai_task(prompt)
            if translated_chunk:
                translated_chunks.append(translated_chunk)
            else:
                # 即使某个块翻译失败，也不让整个流程中断
                translated_chunks.append(f"[块 {i+1} 翻译失败]")
        
        # 将所有翻译好的块拼接成最终的完整文本
        final_text = "\n".join(translated_chunks)
        print(f"✅ {Colors.GREEN}所有块翻译完成，已合并。{Colors.ENDC}")

    # --- 统一处理最终结果（无论是直接翻译还是分块翻译） ---
    if not final_text:
        await safe_notification("翻译失败", "AI 模型未能返回任何有效结果。")
        return

    await asyncio.to_thread(pyperclip.copy, final_text)
    await safe_notification("翻译完成", "完整的中文翻译已复制到剪贴板。")
    print(f"{Colors.YELLOW}--- [ 中文翻译 | 已复制到剪贴板 ] ---{Colors.ENDC}")
    print(f"{Colors.GREEN}{final_text}{Colors.ENDC}\n")
    
    # 在后台记录这次翻译
    asyncio.create_task(database_manager.log_daily_record("TRANSLATE_ZH_PIPELINE", original_text, final_text))

    # 如果开启了朗读模式，则朗读翻译结果
    if state.READ_ALOUD_MODE_ENABLED:
        asyncio.create_task(read_text_aloud(final_text))

async def optimize_prompt(text: str):
    """
    [ASYNC] Handles Alt+E.
    【已移除顶层业务锁】
    """
    print(f"\n{Colors.BLUE}[Async Handler] Formalizing text into bilingual AI instructions...{Colors.ENDC}")

    meta_prompt = f"""
# ROLE
You are an AI Instruction Formalization Engine, fluent in both English and Chinese.
# TASK
Your sole purpose is to convert the user-provided text into two versions of a highly formal, objective, and explicit AI instruction: one in English and one in Chinese. You must adhere to the following rules with absolute strictness for BOTH language outputs:
1.  ABSOLUTE FIDELITY: The original meaning, intent, and all specific details of the source text must be preserved exactly. You are forbidden from adding, removing, or altering any factual content or core concepts.
2.  FORMAL STRUCTURE: Rephrase the text as a direct, unambiguous command. The output must be structured as a clear, actionable directive.
3.  OBJECTIVE LANGUAGE: Eliminate all colloquialisms, conversational filler, and ambiguity. Replace them with precise, formal, and objective language.
4.  SELF-CONTAINMENT: Your transformation must be based *only* on the provided source text.
# OUTPUT FORMAT
You MUST output a single, valid JSON object and nothing else. The JSON object must contain two keys:
- "en_instruction": The formalized instruction in English.
- "zh_instruction": The formalized instruction in Chinese.
Example format: {{"en_instruction": "...", "zh_instruction": "..."}}
# SOURCE TEXT
---
{text}
---
# OUTPUT
Generate only the JSON object containing the two formalized instructions.
"""
    ai_response_json = await ai_services.run_ai_task(meta_prompt)
    if not ai_response_json:
        await safe_notification("Formalization Failed", "AI model did not return a response.")
        return

    try:
        instructions = json.loads(ai_response_json)
        en_instruction = instructions.get("en_instruction", "Error: English version not found.")
        zh_instruction = instructions.get("zh_instruction", "错误：未找到中文版本。")

        await asyncio.to_thread(pyperclip.copy, en_instruction)
        await safe_notification("Instruction Formalized", "English version copied to clipboard.")

        print(f"{Colors.YELLOW}--- [ AI Instruction (EN) | Copied to Clipboard ] ---{Colors.ENDC}")
        print(f"{Colors.GREEN}{en_instruction}{Colors.ENDC}")
        print(f"{Colors.YELLOW}--- [ AI 指令 (ZH) | Display Only ] ---{Colors.ENDC}")
        print(f"{Colors.CYAN}{zh_instruction}{Colors.ENDC}")

        print("   -> [Async Task] Submitting optimization to daily log DB...")
        asyncio.create_task(database_manager.log_daily_record("OPTIMIZE_PROMPT", text, en_instruction, meta_prompt))

    except json.JSONDecodeError:
        await safe_notification("Formalization Failed", "AI returned an invalid format. See console.")
        print(f"❌ {Colors.RED}[Error] Failed to parse AI response. The model did not return valid JSON.{Colors.ENDC}")
        print(f"   Raw AI Response: {ai_response_json}")


async def get_concise_answer(text: str):
    """
    [ASYNC] Handles Alt+N.
    【已移除顶层业务锁】
    """
    print(f"\n{Colors.BLUE}[Async Handler] Requesting concise answer for: '{text[:50]}...'{Colors.ENDC}")
    
    prompt = f"""
# ROLE
You are an expert fact-checker and summarizer AI. Your goal is to provide a direct, hyper-concise, and accurate answer to the user's implicit question based on the text they have selected.

# TASK
1.  Analyze the user's selected text below.
2.  Determine the core question or topic.
3.  Provide a single, definitive, and very short answer.
4.  Do not be conversational. Do not say "The answer is...". Just provide the answer.

# USER'S SELECTED TEXT
---
{clean_text(text)}
---

# YOUR OUTPUT
(Your direct and concise answer here)
"""
    ai_response = await ai_services.run_ai_task(prompt)
    
    if not ai_response:
        await safe_notification("AI Error", "The model did not return a response.")
        return

    await asyncio.to_thread(pyperclip.copy, ai_response)
    await safe_notification("Answer Ready", "Concise answer copied to clipboard.")
    
    print(f"{Colors.YELLOW}--- [ Concise Answer | Copied ] ---{Colors.ENDC}")
    print(f"{Colors.GREEN}{ai_response}{Colors.ENDC}")

    print("   -> [Async Task] Submitting concise Q&A to daily log DB...")
    asyncio.create_task(database_manager.log_daily_record("CONCISE_QA", text, ai_response))


# --- Personal Security & Context ---

async def _save_risk_analysis_to_sqlite_async(situation: str, ai_response: str):
    """[ASYNC BG TASK] Saves a completed risk analysis to the SQLite database."""
    print("   -> [Async BG Task] Saving risk analysis to SQLite...")
    try:
        async with aiosqlite.connect(str(settings.RISK_ASSESSMENT_DB)) as conn:
            await conn.execute(
                f"INSERT INTO {settings.RISK_ASSESSMENT_TABLE_NAME} (timestamp, input_situation, ai_full_response) VALUES (?, ?, ?)",
                (get_local_time_str(), situation, ai_response),
            )
            await conn.commit()
        print(f"✅ {Colors.GREEN}[Async SQLite] Risk analysis record saved successfully.{Colors.ENDC}")
    except Exception as e:
        print(f"❌ {Colors.RED}[Async SQLite Error] Failed to save risk analysis: {e}{Colors.ENDC}")
        traceback.print_exc()


async def _save_risk_analysis_to_vector_db_async(situation: str, ai_response: str):
    """[ASYNC BG TASK] Vectorizes and saves a risk analysis to the Qdrant history collection."""
    print("   -> [Async BG Task] Saving risk analysis to Vector DB...")
    try:
        full_text = f"### Situation Analyzed:\n{situation}\n\n### AI-Generated Analysis:\n{ai_response}"
        
        vector = await ai_services.generate_text_vector(full_text)
        if not vector:
            print(f"❌ {Colors.RED}[Async Vector Error] Vectorization failed for risk analysis.{Colors.ENDC}")
            return

        point_id = str(uuid.uuid4())
        payload = {
            "timestamp": get_local_time_str(),
            "original_situation": situation,
            "full_analysis_text": full_text,
        }
        
        await asyncio.to_thread(
            state.QDRANT_CLIENT.upsert,
            collection_name=settings.QDRANT_RISK_ANALYSIS_COLLECTION,
            points=[models.PointStruct(id=point_id, vector=vector, payload=payload)],
            wait=True,
        )
        print(f"✅ {Colors.GREEN}[Async Vector DB] Risk analysis vectorized and indexed successfully.{Colors.ENDC}")
    except Exception as e:
        print(f"❌ {Colors.RED}[Async Vector Error] Failed to index risk analysis: {e}{Colors.ENDC}")
        traceback.print_exc()


async def personal_risk_analysis(text: str):
    """
    [ASYNC] Handles Alt+Z.
    【已移除顶层业务锁】
    """
    if not state.IS_QDRANT_DB_READY:
        await safe_notification("Error", "Vector Database is not ready.")
        return
        
    print(f"\n{Colors.MAGENTA}[Async Handler] Initiating Closed-Loop Risk Analysis...{Colors.ENDC}")
    
    query_vector = await ai_services.generate_text_vector(text)
    if not query_vector:
        await safe_notification("Vectorization Failed", "Could not generate vector.")
        return

    # 并发执行数据库查询
    constitution_search_task = asyncio.to_thread(
        state.QDRANT_CLIENT.query_points,
        collection_name=settings.QDRANT_CONSTITUTION_COLLECTION,
        query=query_vector, limit=3
    )
    history_search_task = asyncio.to_thread(
        state.QDRANT_CLIENT.query_points,
        collection_name=settings.QDRANT_RISK_ANALYSIS_COLLECTION,
        query=query_vector, limit=2
    )
    search_results, history_search_results = await asyncio.gather(constitution_search_task, history_search_task)

    retrieved_principles = ""
    for result in search_results.points:
        retrieved_principles += f"--- [Relevant Core Principle] ---\n{result.payload.get('text_chunk', '')}\n\n"

    if not retrieved_principles:
         await safe_notification("Analysis Error", "Could not find any relevant principles in the active constitution DB.")
         return

    retrieved_history = ""
    if history_search_results.points:
        for result in history_search_results.points:
            retrieved_history += f"--- [Relevant Past Analysis] ---\n{result.payload.get('full_analysis_text', '')}\n\n"

    prompt = f"""
# Your Role
You are my AI strategic advisor. Your primary function is to provide a holistic and practical analysis that integrates my core principles with general knowledge and common sense.

# My Personal Constitution (The Primary Strategic Filter)
This is the most important context. Your analysis must be fundamentally aligned with these principles, but not blindly constrained by them.
---
{retrieved_principles}
---

# Relevant Past Analyses (If any)
Use these for context and to ensure consistency in your reasoning.
---
{retrieved_history}
---

# New Situation to Analyze
"{text}"

# Your Core Task
Provide a "Strategic Briefing" on the new situation. Do not be a simple rule-checker. **Synthesize** my principles with your own broad knowledge of the world, business, and human psychology to provide the most insightful and actionable advice possible. Your response must be both principled and practical.

# Required Output Structure:
1.  **Executive Summary:** A brief, top-level verdict. Does this align or conflict with my mission?
2.  **Principled Risk Assessment:** Analyze the risks through the lens of my constitution.
3.  **Common Sense Risk Assessment:** What are the obvious, real-world risks that anyone should consider, even without my constitution?
4.  **Opportunity Analysis:** Identify principle-aligned opportunities for growth.
5.  **Final Actionable Advice:** Provide a clear, synthesized recommendation that balances my principles with practical reality.
"""
    analysis_response = await ai_services.run_ai_task(prompt)
    if not analysis_response:
        await safe_notification("Analysis Failed", "AI model did not return a response.")
        return

    await asyncio.to_thread(pyperclip.copy, analysis_response)
    await safe_notification("Analysis Complete", "Results copied. Saving to DBs in background.")
    print(f"{Colors.YELLOW}--- [ Personal Constitution Analysis | Copied ] ---{Colors.ENDC}")
    print(f"{Colors.CYAN}{analysis_response}{Colors.ENDC}")

    print(f"{Colors.BLUE}--- [Async Tasks] Dispatching save operations to background... ---{Colors.ENDC}")
    asyncio.create_task(_save_risk_analysis_to_sqlite_async(text, analysis_response))
    asyncio.create_task(_save_risk_analysis_to_vector_db_async(text, analysis_response))


# --- Data Recording Workflows ---

async def save_input(text: str):
    """
    [ASYNC] Handles Alt+S.
    【已移除锁】
    """
    if state.last_record_id is not None:
        await safe_notification("Action Blocked", f"Input (ID: {state.last_record_id}) is pending.")
        return

    try:
        async with aiosqlite.connect(str(settings.CORPUS_DB)) as conn:
            cursor = await conn.execute(
                f"SELECT id FROM {settings.CORPUS_TABLE_NAME} WHERE input_text = ?", (text,)
            )
            existing_record = await cursor.fetchone()

            if existing_record:
                msg = f"This input already exists as Record ID: {existing_record[0]}."
                print(f"\n{Colors.YELLOW}[!] DUPLICATE FOUND: {msg}{Colors.ENDC}")
                await safe_notification("Duplicate Found", "Save operation cancelled.")
                return

            print(f"\n{Colors.MAGENTA}[Async Handler] Capturing new input record...{Colors.ENDC}")
            metadata_json = json.dumps({"created_at": get_local_time_str()})
            
            cursor = await conn.execute(
                f"INSERT INTO {settings.CORPUS_TABLE_NAME} (input_text, metadata, status) VALUES (?, ?, ?)",
                (text, metadata_json, "pending_output"),
            )
            await conn.commit()
            state.last_record_id = cursor.lastrowid
        
        print(f"✅ {Colors.GREEN}[Async SQLite] Input saved as ID: {state.last_record_id}.{Colors.ENDC}")
        await safe_notification("Input Saved", f"Record ID: {state.last_record_id} is pending.")
        
        print(f"   -> [Async Task] Submitting metadata task for record {state.last_record_id}.")
        asyncio.create_task(process_metadata_and_vectorize(state.last_record_id, "input"))

    except Exception as e:
        print(f"❌ {Colors.RED}[Save Input Error] A database error occurred: {e}{Colors.ENDC}")
        traceback.print_exc()
        await safe_notification("Database Error", "Failed to save the input record.")


async def save_output(text: str):
    """
    [ASYNC] Handles Alt+D.
    【已移除锁】
    """
    if state.last_record_id is None:
        await safe_notification("Action Blocked", "No input pending. Use Alt+S first.")
        return

    record_id_to_process = state.last_record_id
    print(f"\n{Colors.MAGENTA}[Async Handler] Pairing output with record ID: {record_id_to_process}...{Colors.ENDC}")
    
    async with aiosqlite.connect(str(settings.CORPUS_DB)) as conn:
        await conn.execute(
            f"UPDATE {settings.CORPUS_TABLE_NAME} SET output_text = ?, status = ? WHERE id = ?",
            (text, "pending_summaries", record_id_to_process),
        )
        await conn.commit()

    state.last_completed_id = record_id_to_process
    state.last_record_id = None

    print(f"✅ {Colors.GREEN}[Async SQLite] Record {record_id_to_process} is complete.{Colors.ENDC}")
    await safe_notification("Output Saved", f"Record {record_id_to_process} completed!")
    
    print(f"   -> [Async Task] Submitting full processing task for record {record_id_to_process}.")
    asyncio.create_task(process_metadata_and_vectorize(record_id_to_process, "output"))


async def cancel_last_turn():
    """
    [ASYNC] Handles Alt+C.
    【已移除锁】
    """
    if state.last_record_id is None:
        await safe_notification("Cancel Failed", "No pending input to cancel.")
        return

    record_id_to_delete = state.last_record_id
    state.last_record_id = None
    
    print(f"\n{Colors.YELLOW}[Async Handler] Deleting pending record ID: {record_id_to_delete}...{Colors.ENDC}")
    async with aiosqlite.connect(str(settings.CORPUS_DB)) as conn:
        await conn.execute(f"DELETE FROM {settings.CORPUS_TABLE_NAME} WHERE id = ?", (record_id_to_delete,))
        await conn.commit()
    
    print(f"✅ {Colors.GREEN}[Async SQLite] Deleted pending record ID: {record_id_to_delete}.{Colors.ENDC}")
    await safe_notification("Action Canceled", f"Deleted pending record ID: {record_id_to_delete}.")


async def mark_as_high_quality():
    """
    [ASYNC] Handles Alt+F.
    【已移除锁】
    """
    if state.last_completed_id is None:
        await safe_notification("Annotation Failed", "No recently completed record to mark.")
        return

    record_id_to_mark = state.last_completed_id
    state.last_completed_id = None
    
    print(f"\n{Colors.BLUE}[Async Handler] Marking record ID: {record_id_to_mark} as 'high-quality'...{Colors.ENDC}")
    async with aiosqlite.connect(str(settings.CORPUS_DB)) as conn:
        await conn.execute(
            f"UPDATE {settings.CORPUS_TABLE_NAME} SET quality_label = ? WHERE id = ?",
            ("high-quality", record_id_to_mark),
        )
        await conn.commit()

    print(f"✅ {Colors.GREEN}[Async SQLite] Record {record_id_to_mark} marked as high-quality.{Colors.ENDC}")
    await safe_notification("Annotation Successful", f"Record {record_id_to_mark} marked.")


# --- Asynchronous Backend Processing ---

async def process_metadata_and_vectorize(record_id: int, stage: str):
    """
    [ASYNC BG TASK] Fetches a record, generates summaries, and indexes it in Qdrant.
    [MODIFIED] Now handles texts longer than the AI's context window.
    """
    print(f">> [Async BG] Starting job for record {record_id} (Stage: {stage})")
    try:
        # (这部分代码保持不变)
        async with aiosqlite.connect(str(settings.CORPUS_DB)) as conn:
            cursor = await conn.execute(
                f"SELECT input_text, output_text, metadata FROM {settings.CORPUS_TABLE_NAME} WHERE id = ?", (record_id,)
            )
            record = await cursor.fetchone()
        
        if not record: return
        input_text, output_text, metadata_json = record
        metadata = json.loads(metadata_json)

        text_to_summarize = ""
        if stage == "input":
            print(f"   -> Record {record_id}: Summarizing input...")
            text_to_summarize = input_text
        elif stage == "output" and output_text:
            print(f"   -> Record {record_id}: Summarizing output...")
            text_to_summarize = output_text

        # ==============================================================================
        #      【【【 这是关键的修复和优化 】】】
        # ==============================================================================
        if text_to_summarize:
            try:
                # 1. 为了安全，我们只截取前 16000 个字符来生成摘要
                #    这远远小于 32768 的令牌限制，通常是安全的
                safe_text_chunk = text_to_summarize[:16000]
                
                summary_prompt = f"Summarize the following in one short sentence:\n\n{clean_text(safe_text_chunk)}"
                summary = await ai_services.run_ai_task(summary_prompt)
                
                if summary:
                    metadata[f"{stage}_summary"] = summary
            
            except ValueError as e:
                # 2. 如果即使截断后文本仍然太长或发生其他值错误，我们捕获它
                if "exceed context window" in str(e):
                    print(f"   -> {Colors.YELLOW}[Warning] Text for record {record_id} is too long to summarize. Skipping summary.{Colors.ENDC}")
                    # 我们不生成摘要，但流程继续，这比崩溃要好得多
                    metadata[f"{stage}_summary"] = "[Content too long to summarize]"
                else:
                    # 对于其他未知的值错误，我们还是打印出来
                    print(f"❌ {Colors.RED}[Async BG Error] An unexpected ValueError occurred during summarization for record {record_id}: {e}{Colors.ENDC}")
            except Exception as e:
                print(f"❌ {Colors.RED}[Async BG Error] A general error occurred during summarization for record {record_id}: {e}{Colors.ENDC}")
        # ==============================================================================
        #      【【【 修复结束 】】】
        # ==============================================================================
        
        # (这部分代码保持不变)
        async with aiosqlite.connect(str(settings.CORPUS_DB)) as conn:
            await conn.execute(
                f"UPDATE {settings.CORPUS_TABLE_NAME} SET metadata = ? WHERE id = ?",
                (json.dumps(metadata, ensure_ascii=False), record_id),
            )
            await conn.commit()

        # (后续的向量化等代码保持不变)
        if output_text and state.IS_QDRANT_DB_READY:
            # ... (rest of the function is the same)
            print(f"   -> Record {record_id}: Vectorizing complete record...")
            full_text = f"User Input: {input_text}\n\nAI Response: {output_text}"
            vector = await ai_services.generate_text_vector(full_text)
            if not vector:
                print(f"❌ {Colors.RED}[Async BG Error] Vectorization failed for record {record_id}.{Colors.ENDC}")
                return
            payload = {"source_id": record_id, "full_turn": full_text, **metadata}
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(record_id)))
            await asyncio.to_thread(
                state.QDRANT_CLIENT.upsert,
                collection_name=settings.QDRANT_COLLECTION_NAME,
                points=[models.PointStruct(id=point_id, vector=vector, payload=payload)],
                wait=True,
            )
            async with aiosqlite.connect(str(settings.CORPUS_DB)) as conn:
                await conn.execute(
                    f"UPDATE {settings.CORPUS_TABLE_NAME} SET status = ? WHERE id = ?", ("complete", record_id)
                )
                await conn.commit()
            print(f"✅ {Colors.GREEN}[Async BG Complete] Successfully indexed record ID: {record_id}!{Colors.ENDC}")

    except Exception as e:
        print(f"❌ {Colors.RED}[Async BG Error] Processing failed for record {record_id}: {e}{Colors.ENDC}")
        traceback.print_exc()

# --- Text-to-Speech (TTS) Workflows ---

async def read_text_aloud(text: str):
    """
    [已修复]
    处理 Alt+R 快捷键：异步启动或停止TTS播放。
    - 如果没有在播放，则调用 audio_services.piper_tts_task 开始播放。
    - 如果正在播放，则终止 state.tts_process 中存储的进程。
    """
    # 检查 state.tts_process 是否存在并且仍在运行
    # process.poll() is None 意味着进程仍在运行
    if state.tts_process and state.tts_process.poll() is None:
        print(f"\n{Colors.YELLOW}[TTS Stop] Terminating active playback...{Colors.ENDC}")
        
        # 终止存储在全局状态中的播放进程
        state.tts_process.terminate()
        # 我们不需要在这里等待，后台的监控任务会处理善后
        state.tts_process = None # 立即清理状态，允许快速再次播放
        return

    # 如果没有进程在运行，则启动一个新的播放任务
    # 新版的 audio_services.piper_tts_task 会负责将新进程存入 state.tts_process
    await audio_services.piper_tts_task(text)

def toggle_read_aloud_mode():
    """[SYNC] Handles Alt+T: Toggles the global read-aloud mode ON or OFF."""
    state.READ_ALOUD_MODE_ENABLED = not state.READ_ALOUD_MODE_ENABLED
    if state.READ_ALOUD_MODE_ENABLED:
        msg, color = "ON. Translations will be read aloud.", Colors.GREEN
    else:
        msg, color = "OFF. Translations will be silent.", Colors.YELLOW
    print(f"\n{color}>> [System] Read Aloud Mode is now {msg.split('.')[0]}.{Colors.ENDC}")
    
    if state.main_loop:
        asyncio.run_coroutine_threadsafe(safe_notification("Read Aloud Mode", msg), state.main_loop)

# [SYNC-THREAD] 为同步音频录制流设置的全局变量
short_rec_stream = None
short_rec_frames = []

def voice_to_text_workflow():
    """
    [CRITICAL FIX APPLIED]
    Handles Alt+G. This version ensures the data sent to the queue is always
    a tuple (filepath, None) to prevent the background processor from crashing.
    """
    global short_rec_stream, short_rec_frames

    # --- 停止录音逻辑 ---
    if state.IS_RECORDING:
        if not short_rec_stream:
            state.IS_RECORDING = False
            return
        try:
            short_rec_stream.stop()
            short_rec_stream.close()
        except Exception as e:
            print(f"Error stopping recording stream: {e}")

        state.IS_RECORDING = False
        print(f"\n{Colors.GREEN}>> Short recording stopped. Processing in background...{Colors.ENDC}")
        if state.main_loop:
            asyncio.run_coroutine_threadsafe(safe_notification("Recording Stopped", "Processing audio..."), state.main_loop)

        if not short_rec_frames:
            print(f"   -> {Colors.YELLOW}[Warning] No audio was recorded.{Colors.ENDC}")
            return

        try:
            settings.AUDIO_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = get_local_time_str().replace(":", "-").replace(" ", "_")
            filename = f"short_rec_{timestamp}.wav"
            filepath = settings.AUDIO_ARCHIVE_DIR / filename
            sf.write(filepath, np.concatenate(short_rec_frames, axis=0), 16000)
            print(f"   -> {Colors.GREEN}[File Saved] Audio saved to: {filepath}{Colors.ENDC}")
            
            # 
            # --- 【【【 THIS IS THE FIX 】】】 ---
            #
            # The correct format is a tuple: (file_path, None)
            state.transcription_queue.put((str(filepath), None))
            
        except Exception as e:
            print(f"❌ {Colors.RED}[File Error] Could not save audio file: {e}{Colors.ENDC}")
        return

    # --- 开始录音逻辑 (这部分保持不变) ---
    try:
        if state.IS_RECORDING: return
            
        state.IS_RECORDING = True
        short_rec_frames = []
        print(f"\n{Colors.YELLOW}>> Short recording started... Press Alt+G again to stop.{Colors.ENDC}")
        if state.main_loop:
            asyncio.run_coroutine_threadsafe(safe_notification("Recording Started", "Press Alt+G again to stop."), state.main_loop)
        
        def callback(indata, frames, time, status):
            short_rec_frames.append(indata.copy())
        
        short_rec_stream = sd.InputStream(samplerate=16000, channels=1, callback=callback)
        short_rec_stream.start()
    except Exception as e:
        print(f"❌ {Colors.RED}[Audio Error] Could not start recording: {e}{Colors.ENDC}")
        state.IS_RECORDING = False

# --- Meeting Mode Workflows ---

meeting_rec_stream = None
meeting_rec_frames = []

def toggle_meeting_mode():
    """
    [SYNC DISPATCHER] Handles Alt+B.
    - Start: Generates a new session ID and launches the non-locking recorder task.
    - Stop: Signals the stop and dispatches the locking summary task.
    """
    if state.MEETING_MODE_ACTIVE:
        session_id_to_process = state.current_meeting_session_id
        state.MEETING_MODE_ACTIVE = False # Signal to the async task to stop
        
        print(f"\n{Colors.RED}>> [Meeting Mode] Stop signal received. Generating summary for session {str(session_id_to_process)[:8]}...{Colors.ENDC}")
        if state.main_loop and session_id_to_process:
            asyncio.run_coroutine_threadsafe(summarize_meeting_session(session_id_to_process), state.main_loop)
            asyncio.run_coroutine_threadsafe(safe_notification("Meeting Mode", "Stopping... Summary will be generated."), state.main_loop)
        return

    if state.MEETING_MODE_ACTIVE: return
    
    try:
        state.current_meeting_session_id = str(uuid.uuid4())
        state.MEETING_MODE_ACTIVE = True
        print(f"\n{Colors.GREEN}>> [Meeting Mode] Started. New Session ID: {state.current_meeting_session_id[:8]}...{Colors.ENDC}")
        if state.main_loop:
            asyncio.run_coroutine_threadsafe(recorder_task(), state.main_loop)
            asyncio.run_coroutine_threadsafe(safe_notification("Meeting Mode Active", "Recording in the background..."), state.main_loop)
    except Exception as e:
        print(f"❌ {Colors.RED}[Meeting Mode Error] Could not dispatch task: {e}{Colors.ENDC}")
        state.MEETING_MODE_ACTIVE = False

async def summarize_meeting_session(session_id: str):
    """
    [ASYNC WORKER] Waits for the transcription signal, queries the DB,
    generates a summary, and displays the results. This part uses a lock.
    """
    async with state.app_controller_lock:
        try:
            print(f"{Colors.BLUE}>> [Meeting Summary] Waiting for final transcriptions for session {session_id[:8]}...{Colors.ENDC}")
            await state.processing_complete_event.wait()

            print(f">> [Meeting Summary] Signal received. Querying database...{Colors.ENDC}")
            async with aiosqlite.connect(str(settings.VOICE_TRANSCRIPTS_DB)) as conn:
                cursor = await conn.execute(
                    f"SELECT transcribed_text FROM {settings.VOICE_TRANSCRIPTS_TABLE_NAME} WHERE session_id = ? ORDER BY id ASC",
                    (session_id,)
                )
                rows = await cursor.fetchall()

            if not rows:
                print(f"{Colors.YELLOW}>> [Meeting Summary] No speech was detected during this session.{Colors.ENDC}")
                await safe_notification("Meeting Summary", "No speech was detected.")
                return

            full_transcript = "\n".join(row[0].replace("[Meeting] ", "") for row in rows)
            
            summary_prompt = f"""
# ROLE
You are a professional meeting assistant. Your task is to analyze a raw meeting transcript and generate a clear, structured summary.

# RAW MEETING TRANSCRIPT
---
{full_transcript}
---

# YOUR TASK
Based on the transcript, generate a summary that includes the following sections:
1.  **Discussion Points:** Briefly outline the core topics discussed.
2.  **Key Decisions:** List any clear decisions that were made.
3.  **Action Items:** List any to-do items assigned to specific people.

If a section has no relevant information, state "None".
"""
            summary = await ai_services.run_ai_task(summary_prompt)
            if not summary:
                summary = "AI summary generation failed."

            final_output = (
                f"--- [ Meeting Transcript (Session: {session_id[:8]}) ] ---\n"
                f"{full_transcript}\n\n"
                f"--- [ AI-Generated Meeting Summary ] ---\n"
                f"{summary}"
            )

            await asyncio.to_thread(pyperclip.copy, final_output)
            await safe_notification("Meeting Summary Ready", "Full transcript and summary copied.")
            
            print(f"\n{Colors.YELLOW}{'=' * 25} [ Meeting Minutes: {session_id[:8]} ] {'=' * 24}{Colors.ENDC}")
            print(f"{Colors.GREEN}{final_output}{Colors.ENDC}")
            print(f"{Colors.YELLOW}{'=' * 70}{Colors.ENDC}\n")

        except Exception as e:
            print(f"❌ {Colors.RED}[Meeting Summary Error] An unexpected error occurred: {e}{Colors.ENDC}")
            traceback.print_exc()
        finally:
            state.processing_complete_event.clear()
            if state.current_meeting_session_id == session_id:
                 state.current_meeting_session_id = None

async def recorder_task():
    """
    [ASYNC BACKGROUND TASK] This task runs without a lock, allowing other
    app functions to run concurrently.
    """
    global meeting_rec_stream, meeting_rec_frames
    session_id = state.current_meeting_session_id
    
    if not session_id:
        print(f"❌ {Colors.RED}[Recorder Error] Cannot start, session ID is missing.{Colors.ENDC}")
        return

    settings.AUDIO_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    meeting_rec_frames = []

    def meeting_callback(indata, frames, time, status):
        meeting_rec_frames.append(indata.copy())
    try:
        meeting_rec_stream = sd.InputStream(samplerate=16000, channels=1, callback=meeting_callback)
        meeting_rec_stream.start()
        print(f"{Colors.YELLOW}   -> [Background Recorder] Audio stream opened, recording...{Colors.ENDC}")

        while state.MEETING_MODE_ACTIVE:
            await asyncio.sleep(settings.RECORD_CHUNK_SECONDS)
            current_frames = meeting_rec_frames
            meeting_rec_frames = []
            if current_frames:
                await write_audio_chunk(current_frames, "rec_chunk", session_id)
    finally:
        if meeting_rec_stream:
            meeting_rec_stream.stop(); meeting_rec_stream.close()
        if meeting_rec_frames:
            await write_audio_chunk(meeting_rec_frames, "rec_final", session_id)
        print(f"{Colors.GREEN}>> [Background Recorder] Recording task stopped and cleaned up.{Colors.ENDC}")

async def write_audio_chunk(frames: list, prefix: str, session_id: Optional[str]):
    """
    [STABILITY FIX APPLIED]
    This version ensures that the numpy concatenation and soundfile writing,
    which are potential sources of C-level errors, are executed within a
    thread-safe, synchronous function.
    """
    def _write_file_thread_safe():
        try:
            # Isolate numpy and soundfile operations for thread safety
            audio_data = np.concatenate(frames, axis=0)
            
            timestamp = get_local_time_str().replace(":", "-").replace(" ", "_")
            filename = f"{prefix}_{timestamp}.wav"
            filepath = settings.AUDIO_ARCHIVE_DIR / filename
            
            sf.write(filepath, audio_data, 16000)
            
            print(f"   -> {Colors.GREEN}[File Saved] Audio saved to: {filepath}{Colors.ENDC}")
            
            # This data format is now consistent for both Alt+G and Alt+B
            state.transcription_queue.put((str(filepath), session_id))
            
        except Exception as e:
            print(f"   -> {Colors.RED}[File Write Error] Could not save audio chunk: {e}{Colors.ENDC}")
            traceback.print_exc()

    # Use asyncio.to_thread to run the thread-safe function in the background
    await asyncio.to_thread(_write_file_thread_safe)

# --- Advanced Search & Export Workflows ---

async def export_context_by_range(range_text: str):
    """
    [ASYNC] Handles Alt+V.
    【已移除锁】
    """
    print(f"\n{Colors.BLUE}[Async Handler] Received export range: '{range_text}'...{Colors.ENDC}")
    match = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", range_text)
    if not match:
        await safe_notification("Export Failed", "Invalid format. Use 'startID-endID'.")
        return

    start_id, end_id = sorted([int(match.group(1)), int(match.group(2))])
    async with aiosqlite.connect(str(settings.CORPUS_DB)) as conn:
        cursor = await conn.execute(
            f"SELECT id, input_text, output_text FROM {settings.CORPUS_TABLE_NAME} WHERE id BETWEEN ? AND ?",
            (start_id, end_id),
        )
        records = await cursor.fetchall()

    if not records:
        await safe_notification("Export Failed", f"No records found in range {start_id}-{end_id}.")
        return

    context_data = [{"id": r[0], "user_input": r[1], "ai_output": r[2]} for r in records]
    export_path = Path(f"./context/session_range_{start_id}_to_{end_id}.json")
    
    def _write_file():
        export_path.parent.mkdir(exist_ok=True)
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(context_data, f, ensure_ascii=False, indent=4)
    
    await asyncio.to_thread(_write_file)
    
    await safe_notification("Export Complete", f"Saved {len(records)} items to {export_path}")
    print(f"✅ {Colors.GREEN}[Export Complete] Saved {len(records)} interactions.{Colors.ENDC}")

async def search_codebase(search_term: str):
    """
    [ASYNC DISPATCHER] Handles Alt+K.
    【已移除锁】
    """
    if not fast_grep_engine:
        await safe_notification("Search Failed", "fast_grep_engine is not available.")
        return
    
    print(f"\n{Colors.BLUE}[Async Handler] Codebase search task started in background...{Colors.ENDC}")
    await safe_notification("Search Started", "Searching codebase in the background...")
    # This now creates a task that runs independently of any high-level lock.
    asyncio.create_task(search_codebase_task(search_term))

async def search_codebase_task(search_term: str):
    """
    [ASYNC WORKER] Performs the C++ engine search.
    This worker function will acquire a lock only for its duration.
    """
    async with state.app_controller_lock:
        try:
            search_path = str(settings.HOME_DIR)
            results = await asyncio.to_thread(fast_grep_engine.search_content, path=search_path, term=search_term)
            if not results:
                await safe_notification("Search Complete", f"No results found for '{search_term}'.")
                return

            summary = f"Found {len(results)} results."
            await safe_notification("Codebase Search Complete", summary)
            print(f"✅ {Colors.GREEN}[BG Search Complete] {summary}{Colors.ENDC}")
            for line in results[:10]:
                print(f"{Colors.CYAN}{line}{Colors.ENDC}")
        except Exception as e:
            print(f"❌ {Colors.RED}[Code Search Error] An unexpected error occurred: {e}{Colors.ENDC}")
            traceback.print_exc()
            await safe_notification("Code Search Error", "An error occurred in the background task.")

async def analyze_personal_history(current_topic: str):
    """
    [ASYNC DISPATCHER] Handles Alt+J.
    【已移除锁】
    """
    if not state.IS_QDRANT_DB_READY:
        await safe_notification("Error", "Vector Database is not ready.")
        return

    print(f"\n{Colors.MAGENTA}[Async Handler] Memory Advisor task started...{Colors.ENDC}")
    await safe_notification("Analysis Started", "The AI is thinking...")
    asyncio.create_task(advisor_task(current_topic))

async def advisor_task(current_topic: str):
    """
    [ASYNC WORKER] The background worker for the Memory Advisor.
    Acquires a lock for its duration.
    """
    async with state.app_controller_lock:
        try:
            query_vector = await ai_services.generate_text_vector(current_topic)
            if not query_vector:
                await safe_notification("Vectorization Failed", "Could not generate vector.")
                return

            search_results = await asyncio.to_thread(
                state.QDRANT_CLIENT.query_points,
                collection_name=settings.QDRANT_COLLECTION_NAME, query=query_vector, limit=3
            )
            
            if not search_results.points:
                await safe_notification("No Related History", "Could not find similar interactions.")
                return

            retrieved_history = "\n\n".join([f"--- [Past Interaction] ---\n{res.payload.get('full_turn', '')}" for res in search_results.points])
            master_prompt = f"""
# Your Role
You are my AI Strategic Advisor and Personal Knowledge Curator. Help me learn from my past actions.
# My Current Topic
"{current_topic}"
# Relevant Past Interactions
{retrieved_history}
# Your Task
Provide a concise, strategic analysis with these sections:
1.  **Past Achievements Summary:** What have I already accomplished?
2.  **Untapped Knowledge & Gaps:** What ideas did I never follow up on?
3.  **Strategic Next Steps:** Provide a clear, prioritized list of 2-3 actionable next steps.
"""
            final_analysis = await ai_services.run_ai_task(master_prompt)
            if not final_analysis:
                await safe_notification("Analysis Failed", "AI model did not return a response.")
                return

            await asyncio.to_thread(pyperclip.copy, final_analysis)
            await safe_notification("Personal Analysis Complete", "Results copied.")
            print(f"{Colors.YELLOW}--- [ Personal Memory Advisor | Complete ] ---{Colors.ENDC}")
            print(f"{Colors.GREEN}{final_analysis}{Colors.ENDC}")
        except Exception as e:
            print(f"❌ {Colors.RED}[Advisor Task Error] An unexpected error occurred: {e}{Colors.ENDC}")
            traceback.print_exc()
            await safe_notification("Advisor Error", "An unexpected error occurred in the background task.")

async def find_and_search_talent_pools(job_description: str):
    """
    [ASYNC DISPATCHER] Handles Alt+M.
    【已移除锁】
    """
    if not state.IS_QDRANT_DB_READY:
        await safe_notification("Error", "Vector Database is not ready.")
        return
    
    print(f"\n{Colors.BLUE}[Async Handler] Talent pool search task started...{Colors.ENDC}")
    await safe_notification("Search Started", "Scanning all talent pools in the background.")
    asyncio.create_task(find_and_search_talent_pools_task(job_description))

async def find_and_search_talent_pools_task(job_description: str):
    """
    [ASYNC WORKER] Dynamically scans and searches all collections on Qdrant.
    Acquires a lock for its duration.
    """
    async with state.app_controller_lock:
        try:
            print(f"{Colors.BLUE}>> [Smart Scan] Dynamically discovering all vector databases...{Colors.ENDC}")
            
            collections_res = await asyncio.to_thread(state.QDRANT_CLIENT.get_collections)
            all_collection_names = [c.name for c in collections_res.collections]
            
            if not all_collection_names:
                await safe_notification("Search Aborted", "No vector collections found.")
                return

            print(f"   -> Found {len(all_collection_names)} databases, beginning smart-match search...")
            
            main_query_vector = await ai_services.generate_text_vector(job_description)
            if not main_query_vector:
                await safe_notification("Vectorization Failed", "Could not generate primary search vector.")
                return

            all_results = []

            async def search_one_collection_smartly(collection_name):
                try:
                    collection_info = await asyncio.to_thread(
                        state.QDRANT_CLIENT.get_collection,
                        collection_name=collection_name
                    )
                    
                    collection_dimension = collection_info.config.params.vectors.size
                    
                    if len(main_query_vector) != collection_dimension:
                        print(f"   -> {Colors.YELLOW}[Skipping] DB '{collection_name}' (dim: {collection_dimension}) is incompatible with current search (dim: {len(main_query_vector)}).{Colors.ENDC}")
                        return None, None

                    search_result = await asyncio.to_thread(
                        state.QDRANT_CLIENT.query_points,
                        collection_name=collection_name, query=main_query_vector, limit=10, with_payload=True
                    )
                    return collection_name, search_result
                    
                except Exception as e:
                    print(f"❌ {Colors.RED}   -> Unexpected error while searching collection '{collection_name}': {e}{Colors.ENDC}")
                    return None, None

            tasks = [search_one_collection_smartly(name) for name in all_collection_names]
            all_search_results_with_source = await asyncio.gather(*tasks)

            for collection_name, search_result in all_search_results_with_source:
                if collection_name and search_result and search_result.points:
                    for point in search_result.points:
                        all_results.append({"point": point, "source": collection_name})
            
            if not all_results:
                await safe_notification("Search Complete", "No matching candidates found in any compatible databases.")
                print(f"{Colors.YELLOW}>> [Smart Scan] No matches found across all compatible databases.{Colors.ENDC}")
                return
                
            all_results.sort(key=lambda r: r["point"].score, reverse=True)
            
            total_compatible_collections = len([res for res in all_search_results_with_source if res[0] is not None])
            top_results_text = f"--- [ Cross-DB Talent Scan Report ({len(all_results)} found in {total_compatible_collections} compatible DBs) ] ---\n\n"
            for i, result_data in enumerate(all_results[:10]):
                point = result_data["point"]
                source_db = result_data["source"]
                payload = point.payload or {}
                snippet = (payload.get("full_turn") or payload.get("text_snippet") or payload.get("text", "N/A")).split("\n")[0]
                candidate_name = payload.get("candidate_name", "Unknown")

                top_results_text += (
                    f"#{i+1}: {candidate_name} | Relevance: {point.score*100:.2f}%\n"
                    f"   -> From DB: {Colors.CYAN}{source_db}{Colors.ENDC}\n"
                    f"   -> Snippet: {snippet}...\n\n"
                )
            
            await asyncio.to_thread(pyperclip.copy, top_results_text)
            await safe_notification("Talent Scan Complete", f"Found {len(all_results)} in {total_compatible_collections} DBs. Top 10 copied.")
            print(f"{Colors.YELLOW}{top_results_text}{Colors.ENDC}")
            
        except Exception as e:
            print(f"❌ {Colors.RED}[Talent Search Error] An unexpected error occurred: {e}{Colors.ENDC}")
            traceback.print_exc()
            await safe_notification("Talent Search Error", "An error occurred in the background.")

# --- Constitution Management ---

async def import_constitution_principle(text: str):
    """
    [ASYNC] Handles Win+Q with AI-First deduplication.
    【已移除锁】
    """
    if not state.IS_QDRANT_DB_READY:
        await safe_notification("Error", "Vector Database is not ready.")
        return
        
    print(f"\n{Colors.BLUE}[AI-First Import] Analyzing new principle for conceptual similarity...{Colors.ENDC}")
    
    try:
        vector = await ai_services.generate_text_vector(text)
        if not vector:
            await safe_notification("Vectorization Failed", "Could not generate vector for analysis.")
            return

        search_results = await asyncio.to_thread(
            state.QDRANT_CLIENT.search,
            collection_name=settings.QDRANT_CONSTITUTION_COLLECTION,
            query_vector=vector,
            limit=1,
            score_threshold=settings.SIMILARITY_THRESHOLD,
        )
        
        if search_results:
            most_similar_principle = search_results[0].payload.get('text_chunk', 'N/A')
            similarity_score = search_results[0].score
            
            error_message = f"This principle is {similarity_score:.2%} similar to an existing one."
            print(f"{Colors.YELLOW}[Conceptual Duplicate Found] {error_message}{Colors.ENDC}")
            print(f"   - Your Input: '{text}'")
            print(f"   - Existing:   '{most_similar_principle}'")
            await safe_notification("Duplicate Concept", error_message)
            return

    except Exception as e:
        await safe_notification("Vector Search Error", "An error occurred during similarity check.")
        print(f"❌ {Colors.RED}[Vector Search Error] {e}{Colors.ENDC}")
        traceback.print_exc()
        return
        
    print(f"✅ {Colors.GREEN}[AI Check Passed] The principle is conceptually unique.{Colors.ENDC}")

    try:
        async with aiosqlite.connect(str(settings.CONSTITUTION_DB)) as conn:
            cursor = await conn.execute(
                f"INSERT OR IGNORE INTO {settings.CONSTITUTION_TABLE_NAME} (timestamp, principle_text) VALUES (?, ?)",
                (get_local_time_str(), text)
            )
            await conn.commit()
            if cursor.rowcount == 0:
                print(f"{Colors.YELLOW}[Exact Duplicate Found] The exact text exists in SQLite. Halting.{Colors.ENDC}")
                await safe_notification("Duplicate Entry", "This exact principle text already exists.")
                return
    except Exception as e:
        await safe_notification("Database Error", "Failed to save principle to SQLite.")
        print(f"❌ {Colors.RED}[SQLite Error] {e}{Colors.ENDC}")
        return
        
    print(f"✅ {Colors.GREEN}[SQLite Save] New principle archived successfully.{Colors.ENDC}")

    try:
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, text))
        payload = {"timestamp": get_local_time_str(), "text_chunk": text}
        
        await asyncio.to_thread(
            state.QDRANT_CLIENT.upsert,
            collection_name=settings.QDRANT_CONSTITUTION_COLLECTION,
            points=[models.PointStruct(id=point_id, vector=vector, payload=payload)],
            wait=True,
        )
        print(f"✅ {Colors.GREEN}[Vector DB Commit] Principle vectorized and indexed successfully.{Colors.ENDC}")
        await safe_notification("Principle Added", "Successfully added to your constitution.")

    except Exception as e:
        await safe_notification("Vector DB Error", "Failed to commit the principle vector.")
        print(f"❌ {Colors.RED}[Vector Commit Error] {e}{Colors.ENDC}")

# --- Phrase Expander Workflows ---

async def expand_phrase(phrase: str):
    """
    [ASYNC] Handles Win+W.
    【已移除锁】
    """
    clean_phrase = phrase.strip()
    if not clean_phrase:
        await safe_notification("No Text", "The selection was empty after trimming whitespace.")
        return

    print(f"\n{Colors.BLUE}[Phrase Expander] Looking up cleaned phrase: '{clean_phrase}'...{Colors.ENDC}")
    try:
        async with aiosqlite.connect(str(settings.PHRASE_EXPANDER_DB)) as conn:
            cursor = await conn.execute(
                f"SELECT full_content FROM {settings.PHRASE_EXPANDER_TABLE_NAME} WHERE phrase = ?",
                (clean_phrase,)
            )
            result = await cursor.fetchone()

        if result:
            full_content = result[0]
            await asyncio.to_thread(pyperclip.copy, full_content)
            print(f"✅ {Colors.GREEN}[Copied] Found and copied content to clipboard.{Colors.ENDC}")
            await safe_notification("Phrase Expanded", f"Copied content for '{clean_phrase}' to clipboard.")
        else:
            print(f"   -> {Colors.YELLOW}[Not Found] No phrase mapping found for '{clean_phrase}'.{Colors.ENDC}")
            await safe_notification("Phrase Not Found", f"There is no entry defined for '{clean_phrase}'.")

    except Exception as e:
        print(f"❌ {Colors.RED}[Phrase Expander Error] A database error occurred: {e}{Colors.ENDC}")
        traceback.print_exc()
        await safe_notification("Database Error", "Failed to query the phrase expander database.")

async def add_phrase(text: str):
    """
    [ASYNC] Handles Win+S.
    【已移除锁】
    """
    clean_phrase = text.strip()
    if not clean_phrase:
        await safe_notification("No Text", "The selection was empty after trimming.")
        return

    if state.last_phrase_id is not None:
        await safe_notification("Action Blocked", f"Phrase (ID: {state.last_phrase_id}) is pending content.")
        return

    try:
        async with aiosqlite.connect(str(settings.PHRASE_EXPANDER_DB)) as conn:
            cursor = await conn.execute(
                f"SELECT id FROM {settings.PHRASE_EXPANDER_TABLE_NAME} WHERE phrase = ?", (clean_phrase,)
            )
            existing_record = await cursor.fetchone()

            if existing_record:
                msg = f"This phrase shortcut already exists as Record ID: {existing_record[0]}."
                print(f"\n{Colors.YELLOW}[!] DUPLICATE PHRASE: {msg}{Colors.ENDC}")
                await safe_notification("Duplicate Phrase", "This shortcut is already in use.")
                return

            print(f"\n{Colors.MAGENTA}[Phrase Expander] Capturing new phrase: '{clean_phrase}'...{Colors.ENDC}")
            
            cursor = await conn.execute(
                f"INSERT INTO {settings.PHRASE_EXPANDER_TABLE_NAME} (phrase, full_content) VALUES (?, ?)",
                (clean_phrase, "[PENDING CONTENT]"),
            )
            await conn.commit()
            state.last_phrase_id = cursor.lastrowid
        
        print(f"✅ {Colors.GREEN}[SQLite] Phrase saved as ID: {state.last_phrase_id}. Awaiting full content.{Colors.ENDC}")
        await safe_notification("Phrase Saved", f"'{clean_phrase}' is waiting for content (Win+D).")

    except Exception as e:
        print(f"❌ {Colors.RED}[Add Phrase Error] A database error occurred: {e}{Colors.ENDC}")
        traceback.print_exc()
        await safe_notification("Database Error", "Failed to save the new phrase.")

async def add_full_content(text: str):
    """
    [ASYNC] Handles Win+D.
    【已移除锁】
    """
    if state.last_phrase_id is None:
        await safe_notification("Action Blocked", "No phrase is pending. Use Win+S first.")
        return

    record_id_to_update = state.last_phrase_id
    print(f"\n{Colors.MAGENTA}[Phrase Expander] Pairing content with phrase ID: {record_id_to_update}...{Colors.ENDC}")
    
    try:
        async with aiosqlite.connect(str(settings.PHRASE_EXPANDER_DB)) as conn:
            await conn.execute(
                f"UPDATE {settings.PHRASE_EXPANDER_TABLE_NAME} SET full_content = ? WHERE id = ?",
                (text, record_id_to_update),
            )
            await conn.commit()

        state.last_phrase_id = None

        print(f"✅ {Colors.GREEN}[SQLite] Record {record_id_to_update} is now complete.{Colors.ENDC}")
        await safe_notification("Content Saved", f"Phrase mapping {record_id_to_update} completed!")

    except Exception as e:
        print(f"❌ {Colors.RED}[Add Content Error] A database error occurred: {e}{Colors.ENDC}")
        traceback.print_exc()
        await safe_notification("Database Error", "Failed to save the full content.")

async def delete_phrase_mapping(text: str):
    """
    [ASYNC] Handles Win+C.
    【已移除锁】
    """
    clean_phrase = text.strip()
    if not clean_phrase:
        await safe_notification("No Text", "Please select the phrase you want to delete.")
        return
        
    print(f"\n{Colors.YELLOW}[Phrase Expander] Attempting to delete mapping for phrase: '{clean_phrase}'...{Colors.ENDC}")
    
    try:
        async with aiosqlite.connect(str(settings.PHRASE_EXPANDER_DB)) as conn:
            cursor = await conn.execute(
                f"DELETE FROM {settings.PHRASE_EXPANDER_TABLE_NAME} WHERE phrase = ?",
                (clean_phrase,)
            )
            await conn.commit()

            if cursor.rowcount > 0:
                print(f"✅ {Colors.GREEN}[SQLite] Successfully deleted {cursor.rowcount} record(s).{Colors.ENDC}")
                await safe_notification("Deletion Successful", f"Removed the mapping for '{clean_phrase}'.")
            else:
                print(f"   -> {Colors.YELLOW}[Not Found] No phrase mapping found for '{clean_phrase}' to delete.{Colors.ENDC}")
                await safe_notification("Phrase Not Found", f"Could not find '{clean_phrase}' to delete.")

    except Exception as e:
        print(f"❌ {Colors.RED}[Delete Phrase Error] A database error occurred: {e}{Colors.ENDC}")
        traceback.print_exc()
        await safe_notification("Database Error", "Failed to delete the phrase mapping.")

# --- Power Search Workflow ---

async def _save_search_record_async(query: str, context: str, answer: str):
    """[ASYNC BG TASK] Saves a complete search interaction to the SQLite database."""
    print("   -> [Async BG Task] Archiving search and answer to SQLite...")
    try:
        async with aiosqlite.connect(str(settings.SEARCH_ARCHIVE_DB)) as conn:
            await conn.execute(
                f"""INSERT INTO {settings.SEARCH_ARCHIVE_TABLE_NAME} 
                    (timestamp, user_query, search_context, ai_answer) 
                    VALUES (?, ?, ?, ?)""",
                (get_local_time_str(), query, context, answer),
            )
            await conn.commit()
        print(f"✅ {Colors.GREEN}[Async SQLite] Search record for '{query[:30]}...' saved successfully.{Colors.ENDC}")
    except Exception as e:
        print(f"❌ {Colors.RED}[Async SQLite Error] Failed to save search record: {e}{Colors.ENDC}")
        traceback.print_exc()

async def power_search_and_answer(query: str):
    """
    [ASYNC] Handles Win+E.
    【已移除锁】
    """
    print(f"\n{Colors.MAGENTA}[Power Search] Initiating for query: '{query}'...{Colors.ENDC}")
    await safe_notification("Power Search...", f"Searching the web for your query...")
    
    search_context = await ai_services.google_search_task(query)
    if not search_context or "error" in search_context.lower():
        await safe_notification("Search Failed", "Could not retrieve search results.")
        print(f"❌ {Colors.RED}[Power Search] Aborted due to search failure. Details: {search_context}{Colors.ENDC}")
        return

    final_prompt = f"""
# ROLE
You are an expert researcher and analyst. Your goal is to provide a definitive, well-reasoned, and comprehensive answer to the user's question.

# INSTRUCTIONS
1.  Carefully analyze the user's question to understand their core intent.
2.  Review the "Real-Time Search Results" below. This is your primary source of the most current information.
3.  **Synthesize a final answer by intelligently integrating the key information from the search results with your own broad general knowledge and reasoning abilities.**
4.  Do not merely list what the search results say. Provide a direct and confident answer to the user's question, using the search results as evidence and context.
5.  If the search results are sparse, use your expertise to provide the most logical answer, while noting that the real-time information was limited.

# REAL-TIME SEARCH RESULTS
---
{search_context}
---

# USER'S QUESTION
{query}

# YOUR EXPERT ANSWER:
"""
    print(">> [Power Search] Sending enhanced prompt to Google's top LLM...")
    final_answer = await ai_services.run_ai_task(final_prompt, provider="google")
    
    if final_answer:
        await asyncio.to_thread(pyperclip.copy, final_answer)
        await safe_notification("Power Answer Ready", "Result from Google copied and archived.")
        
        print(f"{Colors.YELLOW}--- [ Power Search Result | Copied & Archived ] ---\n{Colors.ENDC}")
        print(f"{Colors.CYAN}{final_answer}{Colors.ENDC}")
        
        asyncio.create_task(_save_search_record_async(query, search_context, final_answer))
    else:
        await safe_notification("AI Error", "The Google model did not return a response.")

# ==============================================================================
#      【【【 新功能: 自由对话 (Free Conversation) 】】】
# ==============================================================================

async def _export_conversation_turn_to_md(user_input: str, model_response: str, conversation_id: str):
    """
    [后台辅助任务] 将单次对话保存为独立的 Markdown 文件。
    """
    try:
        # 确保目标文件夹存在
        export_dir = settings.FREE_CONVERSATION_DIR
        export_dir.mkdir(parents=True, exist_ok=True)

        # 构建文件名，使用时间戳确保排序和唯一性
        timestamp_str = get_local_time_str().replace(" ", "_").replace(":", "-")
        # 从用户输入中提取一个简短、安全的部分作为文件名的一部分
        sanitized_input_summary = re.sub(r'[\\/*?:"<>|\n\r]', '_', user_input[:40].strip())
        
        # 如果净化后为空，则使用备用名
        if not sanitized_input_summary:
            sanitized_input_summary = "conversation"
            
        filename = f"{timestamp_str}_{sanitized_input_summary}.md"
        file_path = export_dir / filename

        # 准备 Markdown 内容
        md_content = f"""# 自由对话记录

**对话ID:** `{conversation_id}`
**时间:** `{get_local_time_str()}`

---

## 你的输入

---

## 模型的回复

"""
        # 异步写入文件
        def _write_file():
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(md_content)
        
        await asyncio.to_thread(_write_file)
        print(f"✅ {Colors.GREEN}[MD Export] 自由对话记录已导出到: {file_path}{Colors.ENDC}")

    except Exception as e:
        print(f"❌ {Colors.RED}[MD Export Error] 导出自由对话记录失败: {e}{Colors.ENDC}")
        traceback.print_exc()

async def free_conversation(text: str):
    """
    [ASYNC] [已修复死锁问题] 处理 Win+R 快捷键。
    此版本只负责启动聊天客户端并发送初始问题，不执行任何AI调用或存档操作。
    """
    clean_input = text.strip()
    
    # 【核心】给我们的聊天窗口起一个独一-无二的名字
    unique_window_title = "AI_Core_Chat_Window"

    # --- 辅助函数：检查并启动唯一的聊天窗口 ---
    def _ensure_chat_window_is_running():
        try:
            # 检查窗口是否存在
            check_command = f"wmctrl -l | grep -q '{unique_window_title}'"
            subprocess.run(check_command, shell=True, check=True)
            # 如果上面代码没报错，说明窗口已存在，我们什么都不用做

        except (subprocess.CalledProcessError, FileNotFoundError):
            # 异常意味着窗口不存在，我们才启动一个新窗口
            print(f"✅ [Chat Client] Window not found, launching a new one...")
            try:
                python_executable = sys.executable
                script_path = Path(__file__).parent.parent / "chat_client.py"
                command = [
                    "gnome-terminal",
                    f"--title={unique_window_title}",
                    "--", "bash", "-c",
                    f'"{python_executable}" "{script_path}"; exec bash'
                ]
                subprocess.Popen(command)
            except Exception as launch_e:
                print(f"❌ {Colors.RED}[Launch Error] Failed to launch new chat client: {launch_e}{Colors.ENDC}")

    # --- 主要逻辑 ---

    # 1. 在后台线程中确保窗口存在（如果不存在就启动一个）
    await asyncio.to_thread(_ensure_chat_window_is_running)

    # 2. 如果用户选中了文本，就将其作为初始问题发送给聊天服务器
    if clean_input:
        print(f"\n{Colors.CYAN}[自由对话] Received input, sending to chat window...{Colors.ENDC}")
        try:
            # 这个操作是非阻塞的，所以很快
            with open(str(settings.CHAT_INPUT_PIPE), 'w') as fifo:
                fifo.write(clean_input + '\n')
        except Exception as e:
            print(f"❌ {Colors.RED}[IPC Error] Could not send text to pipe: {e}{Colors.ENDC}")

# ==============================================================================
#      【【【 新功能: 保存思考过程 (Alt+M) 】】】
# ==============================================================================
async def save_thought_process(text: str):
    """
    [ASYNC] Handles Alt+M: Saves the selected text as the 'thought_process'
    for the most recently completed input/output pair.
    """
    # 检查是否有最近完成的记录可供附加。
    # 我们使用 state.last_completed_id，这是在按下 Alt+D 时设置的。
    if state.last_completed_id is None:
        await safe_notification("Action Blocked", "No recently completed record. Use Alt+S -> Alt+D first.")
        return

    record_id_to_update = state.last_completed_id
    print(f"\n{Colors.CYAN}[Async Handler] Attaching thought process to record ID: {record_id_to_update}...{Colors.ENDC}")
    
    try:
        async with aiosqlite.connect(str(settings.CORPUS_DB)) as conn:
            # 执行一个 UPDATE 查询，只更新 thought_process 这一列
            await conn.execute(
                f"""UPDATE {settings.CORPUS_TABLE_NAME} 
                    SET thought_process = ? 
                    WHERE id = ?""",
                (text, record_id_to_update),
            )
            await conn.commit()

        print(f"✅ {Colors.GREEN}[Async SQLite] Thought process saved for record {record_id_to_update}.{Colors.ENDC}")
        await safe_notification("Thought Process Saved", f"Attached to Record ID: {record_id_to_update}")

        # 注意：我们不在这里清除 state.last_completed_id
        # 因为用户可能还想对同一个记录按 Alt+F 标记为高质量
        # Alt+F 函数会负责清除它

    except Exception as e:
        print(f"❌ {Colors.RED}[Save Thought Process Error] A database error occurred: {e}{Colors.ENDC}")
        traceback.print_exc()
        await safe_notification("Database Error", "Failed to save the thought process.")
