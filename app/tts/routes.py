from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps import get_current_user
from app.utils.response import success, fail
from app.users.crud import update_profile
from app.config import settings
from .services import (
    list_polly_voices,
    is_voice_available,
    translate_text,
    synthesize_with_visemes,
)

router = APIRouter(prefix="/tts", tags=["tts"])

class SayIn(BaseModel):
    text: str = Field(..., max_length=settings.MAX_TTS_TEXT_LEN)
    current_lang: Optional[str] = None
    target_lang: str

@router.get("/voices")
async def get_voices(lang: Optional[str] = None, neural_only: bool = True, current_user=Depends(get_current_user)):
    return success({"voices": list_polly_voices(lang=lang, require_neural=neural_only)})

@router.post("/choose")
async def choose_voice(voice_id: str, lang: Optional[str] = None, current_user=Depends(get_current_user)):
    if not is_voice_available(voice_id, lang=lang):
        return fail("VOICE_NOT_AVAILABLE", f"Voice '{voice_id}' not available in this region.")
    await update_profile(current_user["_db"], current_user["_id"], {"voice_pref": voice_id})
    return success({"voice_pref": voice_id})

@router.post("/say")
async def say(body: SayIn, current_user=Depends(get_current_user)):
    # Translate (if needed) from current_lang to target_lang
    text_t = translate_text(body.text.strip(), source_lang=body.current_lang, target_lang=body.target_lang)

    # pick voice: user preference → gender default
    voice = current_user.get("voice_pref")
    if not voice:
        voice = settings.POLLY_VOICE_MALE if current_user.get("gender") == "male" else settings.POLLY_VOICE_FEMALE
    if not is_voice_available(voice, lang=body.target_lang):
        voice = settings.POLLY_VOICE_FEMALE

    out = synthesize_with_visemes(text_t, voice_id=voice)
    return success(out)
