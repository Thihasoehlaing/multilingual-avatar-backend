from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, Any

from app.deps import get_current_user
from app.tts.services import tts_pipeline

from app.utils.rate_limit import limiter
from app.utils.response import success
from app.utils.errors import BadRequestError
from app.utils.origin_guard import enforce_origin
from app.config import settings

# Keep target/source codes consistent with your sessions model
SourceLang = Literal["en-US", "ms-MY", "zh-CN"]
TargetLang = Literal[
    "en-US", "cmn-CN", "ja-JP", "ko-KR", "es-ES", "fr-FR",
    "it-IT", "pt-PT", "ru-RU", "de-DE", "hi-IN", "ta-IN"
]

router = APIRouter()

class TtsRequest(BaseModel):
    text: str = Field(min_length=1)
    target_lang: TargetLang
    source_lang: Optional[SourceLang] = None
    voice: Optional[str] = None  # e.g. Polly voice id like "Matthew", "Joanna"

@router.post("", summary="Text → Speech with visemes")
@limiter.limit(f"{settings.RATE_TTS_PER_MIN}/minute")
async def tts(
    request: Request,
    req: TtsRequest,
    current_user = Depends(get_current_user),
    _=Depends(enforce_origin),   # simple origin guard
) -> Dict[str, Any]:
    """
    Returns base64 MP3 + viseme/word timeline for client-side lip-sync & captions.
    """
    text = req.text.strip()
    if not text:
        raise BadRequestError("Empty text")
    if len(text) > settings.MAX_TTS_TEXT_LEN:
        raise BadRequestError(f"Text too long (>{settings.MAX_TTS_TEXT_LEN} chars)")

    user_voice_pref = current_user.get("voice_pref")

    try:
        result = tts_pipeline(
            text=text,
            user_voice_pref=user_voice_pref,
            target_lang=req.target_lang,
            source_lang=req.source_lang,
            override_voice=req.voice,
        )
    except Exception as e:
        # Clean fail instead of leaking internals
        raise BadRequestError(f"TTS failed: {type(e).__name__}")

    return success(result)
