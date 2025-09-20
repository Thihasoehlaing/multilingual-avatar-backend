import base64
from fastapi import APIRouter, UploadFile, File, Depends
from typing import Literal
from app.deps import get_current_user
from app.voice.services import s2s_nova_sonic, clone_enroll, clone_speak
from app.tts.services import translate_text, synthesize_with_visemes
from app.users.crud import update_profile
from app.utils.response import success

router = APIRouter(prefix="/voice", tags=["voice"])

SourceLang = Literal["auto","en-US","ms-MY","zh-CN"]
TargetLang = Literal["en-US","ms-MY","zh-CN"]

@router.post("/s2s")
async def speech_to_speech(
    file: UploadFile = File(...),
    target_lang: TargetLang = "en-US",
    source_lang: SourceLang = "auto",
    current_user = Depends(get_current_user)
):
    wav_bytes = await file.read()
    audio = s2s_nova_sonic(wav_bytes, source_lang=source_lang, target_lang=target_lang)

    return success({
        "audio_b64": base64.b64encode(audio).decode(),
        "mime": "audio/mpeg",
        "visemes": []  # optionally add from Polly or Rhubarb
    })

@router.post("/enroll")
async def enroll_voice(file: UploadFile = File(...), current_user = Depends(get_current_user)):
    b = await file.read()
    voice_id = await clone_enroll(b, display_name=current_user.get("full_name") or current_user["email"])
    await update_profile(current_user["_db"], current_user["_id"], {"voice_profile_id": voice_id})
    return success({"voice_profile_id": voice_id})

@router.post("/speak")
async def speak_with_cloned(
    text: str,
    target_lang: str = "en-US",
    current_user = Depends(get_current_user)
):
    t = translate_text(text, source_lang=None, target_lang=target_lang)
    vid = current_user.get("voice_profile_id")
    if not vid:
        voice = (current_user.get("gender") == "male" and "Matthew") or "Joanna"
        return success(synthesize_with_visemes(t, voice_id=voice))
    audio = await clone_speak(vid, t, target_lang)
    v = synthesize_with_visemes(t, voice_id="Danielle")["visemes"]
    return success({"audio_b64": base64.b64encode(audio).decode(), "mime": "audio/mpeg", "visemes": v})
