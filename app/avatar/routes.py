from __future__ import annotations
import base64
from typing import Optional, Literal
from fastapi import APIRouter, Depends, UploadFile, File, Form
from pydantic import BaseModel, Field

from app.deps import get_current_user
from app.utils.response import success, fail
from app.utils.avatar import avatar_for_gender
from app.config import settings
from app.tts.services import (
    translate_text,
    synthesize_with_visemes,
    transcribe_wav_bytes,
    is_voice_available,
)

router = APIRouter(prefix="/avatar", tags=["avatar"])

@router.get("/config")
async def get_avatar_config(current_user=Depends(get_current_user)):
    return success({"avatar": avatar_for_gender(current_user.get("gender"))})

# ----- Text path -----
class SpeakTextIn(BaseModel):
    text: str = Field(..., max_length=settings.MAX_TTS_TEXT_LEN)
    current_lang: Optional[str] = None
    target_lang: str

@router.post("/speak/text")
async def avatar_speak_text(body: SpeakTextIn, current_user=Depends(get_current_user)):
    text_t = translate_text(body.text.strip(), source_lang=body.current_lang, target_lang=body.target_lang)
    voice = current_user.get("voice_pref") or (settings.POLLY_VOICE_MALE if current_user.get("gender") == "male" else settings.POLLY_VOICE_FEMALE)
    if not is_voice_available(voice, lang=body.target_lang):
        voice = settings.POLLY_VOICE_FEMALE
    out = synthesize_with_visemes(text_t, voice_id=voice)
    return success(out)

# ----- Voice path (upload small WAV/MP3) -----
@router.post("/speak/voice")
async def avatar_speak_voice(
    file: UploadFile = File(...),
    current_lang: str = Form(..., description="e.g., en-US, ms-MY, zh-CN"),
    target_lang: str = Form(..., description="e.g., en-US, ms-MY, zh-CN"),
    media_format: Optional[str] = Form(None, description="wav|mp3|mp4|flac|ogg|amr")
    ,
    current_user=Depends(get_current_user),
):
    data = await file.read()
    mf = (media_format or (file.filename.split(".")[-1].lower() if file.filename else "wav")).replace("m4a","mp4")
    # Transcribe current_lang -> text
    text_src = transcribe_wav_bytes(data, media_format=mf, language_code=current_lang)
    # Translate -> target_lang
    text_t = translate_text(text_src, source_lang=current_lang, target_lang=target_lang)
    # TTS in chosen/default voice
    voice = current_user.get("voice_pref") or (settings.POLLY_VOICE_MALE if current_user.get("gender") == "male" else settings.POLLY_VOICE_FEMALE)
    if not is_voice_available(voice, lang=target_lang):
        voice = settings.POLLY_VOICE_FEMALE
    out = synthesize_with_visemes(text_t, voice_id=voice)
    # Optionally include transcript for captions
    out["transcript"] = text_src
    return success(out)
