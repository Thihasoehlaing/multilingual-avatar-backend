# app/tts/routes.py
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from starlette.concurrency import run_in_threadpool

from app.utils.response import success
from app.tts import services  # provides pipeline_text / pipeline_voice

router = APIRouter(prefix="/tts", tags=["tts"])


# ==== Schemas ====

class SpeakTextRequest(BaseModel):
    text: str = Field(..., min_length=1)
    current_lang: str
    target_lang: str
    style: Optional[str] = None
    neural_only: Optional[bool] = None
    sample_rate_hz: Optional[int] = None
    return_transcript: bool = False


class SpeakVoiceS3Request(BaseModel):
    bucket: str
    key: str
    current_lang: str
    target_lang: str
    return_transcript: bool = True


class VisemeMapped(BaseModel):
    time_ms: int
    shape: str


class SpeakResponse(BaseModel):
    s3_url: Optional[str] = None
    visemes_mapped: List[VisemeMapped] = []
    visemes_raw: Optional[List[Dict[str, Any]]] = None
    transcript: Optional[str] = None
    audio_b64: Optional[str] = None
    audio_mime: Optional[str] = None
    sample_rate_hz: Optional[int] = None
    engine: Optional[str] = None
    debug: Optional[Dict[str, Any]] = None
    duration_ms: Optional[int] = None
    source_text: Optional[str] = None
    translated_text: Optional[str] = None


# ==== Routes ====

@router.post("/speak/text", response_model=Dict[str, Any])
async def speak_text(payload: SpeakTextRequest):
    try:
        # run sync pipeline in a worker thread (no 'await' on the function itself)
        result = await run_in_threadpool(
            services.pipeline_text,
            text=payload.text,
            current_lang=payload.current_lang,
            target_lang=payload.target_lang,
            style=payload.style,
            neural_only=payload.neural_only,
            sample_rate_hz=payload.sample_rate_hz,
            return_transcript=payload.return_transcript,
        )
        return success(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"text pipeline failed: {e}")


@router.post("/speak/voice-s3", response_model=Dict[str, Any])
async def speak_voice_from_s3(payload: SpeakVoiceS3Request):
    try:
        result = await run_in_threadpool(
            services.pipeline_voice,
            bucket=payload.bucket,
            key=payload.key,
            current_lang=payload.current_lang,
            target_lang=payload.target_lang,
            return_transcript=payload.return_transcript,
        )
        return success(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"voice-s3 pipeline failed: {e}")


# ---- (Optional) Deprecated legacy endpoint: multipart file upload) ----
@router.post("/speak/voice", response_model=Dict[str, Any], deprecated=True)
async def speak_voice_legacy(
    voice_file: UploadFile = File(..., description="Deprecated: use /tts/speak/voice-s3"),
    current_language: str = Form(...),
    target_language: str = Form(...),
    return_transcript: bool = Form(True),
):
    try:
        # If you still want this to work, you can stream the file to S3 here,
        # then call the same services.pipeline_voice(bucket, key, ...)
        # Or just raise to force migration:
        raise HTTPException(status_code=410, detail="Use /tts/speak/voice-s3 with S3 bucket/key.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"legacy voice pipeline failed: {e}")
