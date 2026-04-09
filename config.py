# config.py (修改版 - 第1步)

import os
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ==============================================================================
#      【【【 1. 所有的“总开关”，都集中在这里 】】】
# ==============================================================================

# ---  ⚠️  AI 服务提供商 “总开关”  ⚠️ ---
# ---  可选值: "local" 或 "google" ---
ACTIVE_AI_PROVIDER = "local"

# ---  ⚠️  Google Gemini 模型 “总开关” (如果上面选了 "google")  ⚠️ ---
# ---  可选值: "gemini-1.5-flash", "gemini-1.5-pro" ---
ACTIVE_GOOGLE_MODEL_NAME = "models/gemini-2.5-flash-lite "

# ---  ⚠️  Embedding 向量模型 “总开关”  ⚠️ ---
# ---  可选值: "gemma" 或 "minilm" ---
EMBEDDING_MODEL_CONFIGS = {
    "minilm": { "path": "./all-MiniLM-L6-v2", "dimension": 384 },
    "gemma": { "path": "./embeddinggemma-300m", "dimension": 768 }
}
CURRENT_MODEL_NAME = "gemma"
ACTIVE_EMBEDDING_CONFIG = EMBEDDING_MODEL_CONFIGS[CURRENT_MODEL_NAME]


# ==============================================================================
#      【【【 2. 统一的 AppSettings 类 】】】
# ==============================================================================
# ==============================================================================
#      【【【 2. 统一的 AppSettings 类 - 格式修正版 】】】
# ==============================================================================
class AppSettings(BaseSettings):
    """
    定义并验证所有应用设置。
    """
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', case_sensitive=False)

    # --- .env 文件中的所有变量 ---
    google_ai_key: Optional[str] = None
    local_api_url: Optional[str] = "http://127.0.0.1:8087/v1"
    http_proxy: Optional[str] = None
    https_proxy: Optional[str] = None
    notion_token: Optional[str] = None
    google_search_api_key: Optional[str] = None
    google_search_cx: Optional[str] = None
    core_brain_database_id: Optional[str] = None
    toolbox_log_database_id: Optional[str] = None
    daily_review_database_id: Optional[str] = None
    training_hub_database_id: Optional[str] = None
    inbox_database_id: Optional[str] = None
    jd_hub_database_id: Optional[str] = None
    candidate_db_id: Optional[str] = None
    candidate_profile_hub_db_id: Optional[str] = None

    # --- 固定配置 ---
    HOME_DIR: Path = Path.home()
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    KEEP_AUDIO_FILES: bool = True
    RECORD_CHUNK_SECONDS: int = Field(60, gt=0, le=3600)
    CORPUS_TABLE_NAME: str = "training_data"
    DAILY_RECORDS_TABLE_NAME: str = "records"
    RISK_ASSESSMENT_TABLE_NAME: str = "assessments"
    VOICE_TRANSCRIPTS_TABLE_NAME: str = "transcripts"
    CONCISE_QA_TABLE_NAME: str = "qa_records"
    CONSTITUTION_TABLE_NAME: str = "principles"
    SIMILARITY_THRESHOLD: float = 0.995
    PHRASE_EXPANDER_TABLE_NAME: str = "phrase_mappings"
    SEARCH_ARCHIVE_TABLE_NAME: str = "search_records"
    WEB_ARCHIVE_TABLE_NAME: str = "web_articles"
    FREE_CONVERSATION_TABLE_NAME: str = "conversations"

    # --- 所有动态属性 (@property) ---
    @property
    def WEB_ARCHIVE_DB(self) -> Path:
        return self.HOME_DIR / "web_archive.sqlite"
    
    @property
    def WEB_CAPTURES_DIR(self) -> Path:
        return self.HOME_DIR / "web_captures"

    @property
    def SEARCH_ARCHIVE_DB(self) -> Path: 
        return self.HOME_DIR / "ai_search_archive.sqlite"
        
    @property
    def FREE_CONVERSATION_DB(self) -> Path:
        return self.HOME_DIR / "free_conversation.sqlite"
    
    @property
    def FREE_CONVERSATION_DIR(self) -> Path:
        return Path("/home/weiyubin/MuseBox_Storage/个人笔记/自由对话")

    @property
    def GOOGLE_MODEL_NAME(self) -> str:
        return ACTIVE_GOOGLE_MODEL_NAME
    
    @property
    def PHRASE_EXPANDER_DB(self) -> Path: 
        return self.HOME_DIR / "phrase_expander.sqlite"
    
    @property
    def VECTOR_DIMENSION(self) -> int:
        return ACTIVE_EMBEDDING_CONFIG["dimension"]

    @property
    def QDRANT_COLLECTION_NAME(self) -> str:
        return f"{CURRENT_MODEL_NAME}_dialogue_pairs_{self.VECTOR_DIMENSION}d_v1"

    @property
    def QDRANT_RISK_ANALYSIS_COLLECTION(self) -> str:
        return f"{CURRENT_MODEL_NAME}_risk_analysis_{self.VECTOR_DIMENSION}d_v1"

    @property
    def QDRANT_CONSTITUTION_COLLECTION(self) -> str:
        return f"{CURRENT_MODEL_NAME}_constitution_{self.VECTOR_DIMENSION}d_v1"

    @property
    def IPC_DIR(self) -> Path:
        return self.HOME_DIR / ".ai_ecosystem_ipc"

    @property
    def CHAT_INPUT_PIPE(self) -> Path:
        return self.IPC_DIR / "chat_input.pipe"
    
    @property
    def CHAT_OUTPUT_PIPE(self) -> Path:
        return self.IPC_DIR / "chat_output.pipe"

    @property
    def AUDIO_ARCHIVE_DIR(self) -> Path:
        return self.HOME_DIR / "audio_archives"
    
    @property
    def CORPUS_DB(self) -> Path:
        return self.HOME_DIR / "ai_training_corpus.sqlite"
    
    @property
    def DAILY_RECORDS_DB(self) -> Path:
        return self.HOME_DIR / "gemini_daily_records.sqlite"
    
    @property
    def RISK_ASSESSMENT_DB(self) -> Path:
        return self.HOME_DIR / "personal_risk_assessments.sqlite"
    
    @property
    def VOICE_TRANSCRIPTS_DB(self) -> Path:
        return self.HOME_DIR / "voice_transcripts.sqlite"
    
    @property
    def CONCISE_QA_DB(self) -> Path:
        return self.HOME_DIR / "concise_qa_archive.sqlite"
    
    @property
    def CONSTITUTION_DB(self) -> Path:
        return self.HOME_DIR / "personal_constitution.sqlite"


# ==============================================================================
#      【【【 3. 创建全局实例和触发文件 】】】
# ==============================================================================
try:
    settings = AppSettings()
    # 启动时打印所有开关的状态，一目了然
    print(f"✅ [Config] AI Provider set to: '{ACTIVE_AI_PROVIDER.upper()}'")
    if ACTIVE_AI_PROVIDER == "google":
        print(f"✅ [Config] Google Model set to: '{ACTIVE_GOOGLE_MODEL_NAME.upper()}'")
    print(f"✅ [Config] Embedding Model set to: '{CURRENT_MODEL_NAME.upper()}'")
except Exception as e:
    print(f"FATAL: Configuration error - {e}")
    exit(1)

# TRIGGER_FILES 字典保持不变
TRIGGER_FILES = {
    "translate_to_en": settings.IPC_DIR / "trigger_translate_to_en",
    "translate_to_zh": settings.IPC_DIR / "trigger_translate_to_zh",
    "optimize_prompt": settings.IPC_DIR / "trigger_optimize_prompt",
    "read_aloud": settings.IPC_DIR / "trigger_read_aloud",
    "toggle_read_aloud": settings.IPC_DIR / "trigger_toggle_read_aloud_mode",
    "get_concise_answer": settings.IPC_DIR / "trigger_get_concise_answer",
    "personal_risk_analysis": settings.IPC_DIR / "trigger_personal_risk_analysis",
    "export_range_context": settings.IPC_DIR / "trigger_export_range_context",
    "save_input": settings.IPC_DIR / "trigger_save_input",
    "save_output": settings.IPC_DIR / "trigger_save_output",
    "cancel_turn": settings.IPC_DIR / "trigger_cancel_last_turn", # <--- 在这里加上 "_last"
    "mark_high_quality": settings.IPC_DIR / "trigger_mark_high_quality",
    "save_thought_process": settings.IPC_DIR / "trigger_save_thought_process",
    "voice_to_text": settings.IPC_DIR / "trigger_voice_to_text",
    "meeting_mode": settings.IPC_DIR / "trigger_meeting_mode",
    "codebase_search": settings.IPC_DIR / "trigger_codebase_search",
    "personal_memory_advisor": settings.IPC_DIR / "trigger_memory_advisor",
    "talent_pool_search": settings.IPC_DIR / "trigger_talent_pool_search",
    "import_constitution_principle": settings.IPC_DIR / "trigger_import_constitution_principle",
    "phrase_expander": settings.IPC_DIR / "trigger_phrase_expander",
    "power_search_and_answer": settings.IPC_DIR / "trigger_power_search_and_answer",
    "add_phrase": settings.IPC_DIR / "trigger_add_phrase",
    "add_full_content": settings.IPC_DIR / "trigger_add_full_content",
    "delete_phrase_mapping": settings.IPC_DIR / "trigger_delete_phrase_mapping",
    # ==============================================================================
    #      【【【 添加新的“自由对话”触发文件 (用于 Win+R) 】】】
    # ==============================================================================
    "free_conversation": settings.IPC_DIR / "trigger_free_conversation",
}
