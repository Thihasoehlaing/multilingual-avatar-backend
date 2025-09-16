from pydantic import BaseModel, Field
from typing import Optional, Literal

# Input (ASR) languages (Transcribe Streaming)
SourceLang = Literal["en-US", "ms-MY", "zh-CN"]

# Output (Polly) languages — pick your demo set
TargetLang = Literal[
    "en-US", "cmn-CN", "ja-JP", "ko-KR", "es-ES", "fr-FR",
    "it-IT", "pt-PT", "ru-RU", "de-DE", "hi-IN", "ta-IN"
]

class Prosody(BaseModel):
    rate: Literal["x-slow", "slow", "medium", "fast", "x-fast"] = "medium"
    pitch: Literal["x-low", "low", "default", "medium", "high", "x-high"] = "default"

class SessionCreate(BaseModel):
    source_lang: SourceLang
    target_lang: TargetLang
    prosody: Optional[Prosody] = Field(default_factory=Prosody)

class SessionPublic(BaseModel):
    session_id: str = Field(alias="_id")
    user_id: str
    source_lang: SourceLang
    target_lang: TargetLang
    created_at: str
    ended_at: Optional[str] = None
