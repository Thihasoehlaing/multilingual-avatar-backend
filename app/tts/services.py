import json
import os
import time
import uuid
from typing import Dict, List, Optional, Tuple

import boto3
from botocore.config import Config
from fastapi import HTTPException, UploadFile

from app.tts.viseme_map import VISEME_MAP

# ========= ENV / SETTINGS =========

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_S3_BUCKET_AUDIO = os.getenv("AWS_S3_BUCKET_AUDIO", "avatar-ai-cache")
S3_URL_EXPIRES_SECONDS = int(os.getenv("S3_URL_EXPIRES_SECONDS", "3600"))  # 1h link

def _normalize_bedrock_model_id(raw: Optional[str]) -> str:
    model = (raw or "amazon.nova-pro-v1:0").strip()
    if model.startswith("amazon.nova") and ":" not in model:
        model += ":0"
    return model

BEDROCK_MODEL_ID = _normalize_bedrock_model_id(os.getenv("BEDROCK_MODEL_ID"))

MAX_TTS_TEXT_LEN = int(os.getenv("MAX_TTS_TEXT_LEN", "500"))
TRANSCRIBE_WAIT_TIMEOUT = int(os.getenv("TRANSCRIBE_WAIT_TIMEOUT", "45"))   # seconds
TRANSCRIBE_POLL_INTERVAL = float(os.getenv("TRANSCRIBE_POLL_INTERVAL", "2.0"))
NEURAL_ONLY_DEFAULT = os.getenv("NEURAL_ONLY_DEFAULT", "true").lower() == "true"

_boto_cfg = Config(retries={"max_attempts": 6, "mode": "standard"})
s3 = boto3.client("s3", region_name=AWS_REGION, config=_boto_cfg)
polly = boto3.client("polly", region_name=AWS_REGION, config=_boto_cfg)
transcribe = boto3.client("transcribe", region_name=AWS_REGION, config=_boto_cfg)
bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION, config=_boto_cfg)

# ========= VOICE SELECTION =========

# near-locale fallback map for voices
_NEAR_LOCALE = {
    "zh-CN": ["zh-TW"], "zh-TW": ["zh-CN"],
    "es-ES": ["es-MX"], "es-MX": ["es-ES"],
    "en-GB": ["en-US"], "en-US": ["en-GB"],
    "pt-BR": ["pt-PT"], "pt-PT": ["pt-BR"],
}

_DEFAULT_PRIORITY = [
    "Matthew", "Joanna", "Takumi", "Mizuki", "Seoyeon", "Zhiyu",
    "Amy", "Brian", "Emma", "Raveena", "Aditi", "Lupe", "Mia",
]

# Add this helper near your Polly section
def _supports_neural(voice_id: str) -> bool:
    """
    Probe a Polly voice for Neural support (cheap 1-char synth).
    Returns True if Neural works, else False.
    """
    try:
        resp = polly.synthesize_speech(Text=".", VoiceId=voice_id, OutputFormat="mp3", Engine="neural")
        # Drain/close stream to avoid leaking the socket
        _ = resp["AudioStream"].read()
        return True
    except Exception:
        return False


def _list_polly_voices_by_lang(lang: str) -> List[Dict]:
    out: List[Dict] = []
    next_token: Optional[str] = None
    try_specific = bool(lang)
    while True:
        try:
            kwargs: Dict[str, str] = {"LanguageCode": lang} if try_specific else {}
            if next_token:
                kwargs["NextToken"] = next_token
            resp = polly.describe_voices(**kwargs)
        except Exception:
            if not try_specific:
                break
            try_specific = False
            continue
        for v in resp.get("Voices", []):
            out.append({
                "id": v["Id"],
                "gender": v.get("Gender", "Female").capitalize(),
                "language_code": v.get("LanguageCode", lang),
            })
        next_token = resp.get("NextToken")
        if not next_token:
            break
    return out

def _pick_voice(target_lang: str, user_gender: Optional[str], neural_only: bool) -> Tuple[str, str]:
    """
    Choose a Polly voice with preferences:
      1) Match target_lang (with near-locale fallbacks)
      2) Match user_gender if provided
      3) Follow _DEFAULT_PRIORITY order
      4) If neural_only: pick the first *neural-capable* voice from the pool.
         If none are neural-capable, gracefully fall back to Standard using the top candidate.
      5) If neural_only is False: prefer Neural if available (first that supports it),
         else use Standard with the top candidate.
    Returns: (voice_id, engine) where engine is "neural" or "standard".
    """
    # Build candidate pool
    locales = [target_lang] + _NEAR_LOCALE.get(target_lang, [])
    candidates: List[Dict] = []
    for lc in locales:
        cand = _list_polly_voices_by_lang(lc)
        if cand:
            candidates = cand
            break
    if not candidates:
        candidates = _list_polly_voices_by_lang("")

    # Filter by gender (if provided), then sort by priority
    pool = [c for c in candidates if user_gender and c["gender"].lower() == (user_gender or "").lower()] or candidates
    pool.sort(key=lambda c: (_DEFAULT_PRIORITY.index(c["id"]) if c["id"] in _DEFAULT_PRIORITY else 999, c["id"]))

    if not pool:
        raise HTTPException(status_code=422, detail="No Polly voices available.")

    # Try to find a neural-capable voice in order
    for c in pool:
        if _supports_neural(c["id"]):
            return c["id"], "neural"

    # No neural-capable voice found
    top = pool[0]["id"]
    if neural_only:
        # User demanded neural, but none available → choose next available (Standard) instead of erroring
        return top, "standard"

    # Prefer Neural by default; fallback to Standard if none supported
    return top, "standard"

    return voice_id, "neural"  # will auto-fallback to standard in _synthesize_audio if needed

# ========= BEDROCK TRANSLATION =========

def translate_text_bedrock(text: str, src_lang: str, tgt_lang: str, style: Optional[str] = None) -> str:
    if not text or not text.strip():
        return ""
    system = (
        "You are a precise translation engine. Translate the user text exactly from the source language "
        "to the target language, preserving meaning and tone. Return only the translated text."
    )
    if style:
        system += f" Style: {style}."
    messages = [{
        "role": "user",
        "content": [{"text": f"Source language: {src_lang}\nTarget language: {tgt_lang}\nText:\n{text}"}]
    }]
    try:
        resp = bedrock.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=messages,
            system=[{"text": system}],
            inferenceConfig={"maxTokens": 1024, "temperature": 0.2, "topP": 0.9},
        )
        return resp["output"]["message"]["content"][0]["text"].strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed via Bedrock: {e}")

# ========= S3 HELPERS =========

def _s3_put(key: str, data: bytes, content_type: str, cache_control: Optional[str] = None) -> str:
    kwargs = {"Bucket": AWS_S3_BUCKET_AUDIO, "Key": key, "Body": data, "ContentType": content_type}
    if cache_control:
        kwargs["CacheControl"] = cache_control
    s3.put_object(**kwargs)
    return f"s3://{AWS_S3_BUCKET_AUDIO}/{key}"

def _s3_presigned_get(key: str, expires: int = S3_URL_EXPIRES_SECONDS) -> str:
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": AWS_S3_BUCKET_AUDIO, "Key": key},
        ExpiresIn=expires,
    )

def _s3_delete(key: str) -> None:
    try:
        s3.delete_object(Bucket=AWS_S3_BUCKET_AUDIO, Key=key)
    except Exception:
        pass

def _s3_save_tts_audio(audio_bytes: bytes, lang: str, ext: str = "mp3") -> Tuple[str, str, str]:
    key = f"tts/out/{lang}/{uuid.uuid4().hex}.{ext}"
    s3_uri = _s3_put(key, audio_bytes, content_type="audio/mpeg", cache_control="public, max-age=86400")
    url = _s3_presigned_get(key)
    return key, s3_uri, url

# ========= TRANSCRIBE (LEGACY: FILE) =========

def transcribe_audio(file: UploadFile, lang_code_hint: Optional[str] = None) -> str:
    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty audio file.")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio file too large (>10MB).")

    ext = os.path.splitext(file.filename or "")[1].lower() or ".bin"
    mime = file.content_type or "application/octet-stream"
    in_key = f"transcribe/in/{uuid.uuid4().hex}{ext}"

    _s3_put(in_key, content, mime)
    s3_uri = f"s3://{AWS_S3_BUCKET_AUDIO}/{in_key}".replace(" ", "")

    job_name = f"job-{uuid.uuid4().hex}"
    kwargs: Dict = {
        "TranscriptionJobName": job_name,
        "Media": {"MediaFileUri": s3_uri},
        "OutputBucketName": AWS_S3_BUCKET_AUDIO,
    }
    kwargs["LanguageCode"] = (lang_code_hint or "en-US")

    try:
        transcribe.start_transcription_job(**kwargs)
    except Exception as e:
        _s3_delete(in_key)
        raise HTTPException(status_code=500, detail=f"Transcribe start failed: {e}")

    t0 = time.time()
    out_key: Optional[str] = None
    while time.time() - t0 < TRANSCRIBE_WAIT_TIMEOUT:
        job = transcribe.get_transcription_job(TranscriptionJobName=job_name)["TranscriptionJob"]
        status = job["TranscriptionJobStatus"]
        if status == "COMPLETED":
            resp = s3.list_objects_v2(Bucket=AWS_S3_BUCKET_AUDIO, Prefix=job_name)
            for obj in resp.get("Contents", []):
                if obj["Key"].endswith(".json"):
                    out_key = obj["Key"]; break
            break
        if status == "FAILED":
            _s3_delete(in_key)
            raise HTTPException(status_code=422, detail=f"Transcription failed: {job.get('FailureReason')}")
        time.sleep(TRANSCRIBE_POLL_INTERVAL)

    _s3_delete(in_key)
    if not out_key:
        raise HTTPException(status_code=504, detail="Transcription timed out.")

    obj = s3.get_object(Bucket=AWS_S3_BUCKET_AUDIO, Key=out_key)
    data = json.loads(obj["Body"].read().decode("utf-8"))
    _s3_delete(out_key)
    try:
        return data["results"]["transcripts"][0]["transcript"].strip()
    except Exception:
        return ""

# ========= TRANSCRIBE (S3 INPUT) =========

def transcribe_s3(bucket: str, key: str, lang_code_hint: Optional[str] = None) -> str:
    if not bucket or not key:
        raise HTTPException(status_code=400, detail="S3 bucket/key are required for transcription.")

    s3_uri = f"s3://{bucket}/{key}".replace(" ", "")
    job_name = f"job-{uuid.uuid4().hex}"

    kwargs: Dict = {
        "TranscriptionJobName": job_name,
        "Media": {"MediaFileUri": s3_uri},
        "OutputBucketName": AWS_S3_BUCKET_AUDIO,
    }
    kwargs["LanguageCode"] = (lang_code_hint or "en-US")

    try:
        transcribe.start_transcription_job(**kwargs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcribe start failed (S3): {e}")

    t0 = time.time()
    out_key: Optional[str] = None
    while time.time() - t0 < TRANSCRIBE_WAIT_TIMEOUT:
        job = transcribe.get_transcription_job(TranscriptionJobName=job_name)["TranscriptionJob"]
        status = job["TranscriptionJobStatus"]
        if status == "COMPLETED":
            resp = s3.list_objects_v2(Bucket=AWS_S3_BUCKET_AUDIO, Prefix=job_name)
            for obj in resp.get("Contents", []):
                if obj["Key"].endswith(".json"):
                    out_key = obj["Key"]; break
            break
        if status == "FAILED":
            raise HTTPException(status_code=422, detail=f"Transcription failed: {job.get('FailureReason')}")
        time.sleep(TRANSCRIBE_POLL_INTERVAL)

    if not out_key:
        raise HTTPException(status_code=504, detail="Transcription timed out (S3).")

    obj = s3.get_object(Bucket=AWS_S3_BUCKET_AUDIO, Key=out_key)
    data = json.loads(obj["Body"].read().decode("utf-8"))
    _s3_delete(out_key)

    try:
        return data["results"]["transcripts"][0]["transcript"].strip()
    except Exception:
        return ""

# ========= VISEMES =========

def _map_visemes_to_shapes(visemes_raw: List[Dict]) -> List[Dict]:
    return [{"time_ms": evt.get("time_ms", 0), "shape": VISEME_MAP.get(evt.get("viseme", ""), "AX")}
            for evt in visemes_raw]

# ========= POLLY =========

def _synthesize_marks(text: str, voice_id: str, engine: str) -> List[Dict]:
    resp = polly.synthesize_speech(
        Text=text, VoiceId=voice_id, OutputFormat="json",
        SpeechMarkTypes=["viseme"], Engine=engine,
    )
    out: List[Dict] = []
    for line in resp["AudioStream"].read().decode("utf-8").splitlines():
        try:
            evt = json.loads(line)
            if evt.get("type") == "viseme":
                out.append({"time_ms": evt.get("time", 0), "viseme": evt.get("value", "")})
        except Exception:
            continue
    return out

def _synthesize_audio(text: str, voice_id: str, engine: str, sample_rate_hz: int) -> bytes:
    try:
        resp = polly.synthesize_speech(
            Text=text, VoiceId=voice_id, OutputFormat="mp3",
            Engine=engine, SampleRate=str(sample_rate_hz),
        )
        return resp["AudioStream"].read()
    except Exception:
        if engine == "neural":
            resp = polly.synthesize_speech(
                Text=text, VoiceId=voice_id, OutputFormat="mp3",
                Engine="standard", SampleRate=str(sample_rate_hz),
            )
            return resp["AudioStream"].read()
        raise

def synthesize_with_visemes(
    text: str,
    target_lang: str,
    user_gender: Optional[str],
    neural_only: bool,
    sample_rate_hz: int = 22050,
) -> Tuple[bytes, List[Dict]]:
    voice_id, engine = _pick_voice(target_lang, user_gender, neural_only)
    audio_bytes = _synthesize_audio(text, voice_id, engine, sample_rate_hz)
    visemes_raw = _synthesize_marks(text, voice_id, engine)
    return audio_bytes, visemes_raw

# ========= PIPELINES =========

def pipeline_text(
    text: str,
    current_lang: str,
    target_lang: str,
    user_gender: Optional[str] = None,
    style: Optional[str] = None,
    neural_only: Optional[bool] = None,
    sample_rate_hz: Optional[int] = None,
    include_visemes_raw: bool = False,
    return_transcript: bool = False,
) -> Dict:
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Text is required.")
    if len(text) > MAX_TTS_TEXT_LEN:
        raise HTTPException(status_code=400, detail=f"Text too long (>{MAX_TTS_TEXT_LEN} chars).")

    translated = translate_text_bedrock(text, current_lang, target_lang, style=style)

    audio_bytes, visemes_raw = synthesize_with_visemes(
        translated,
        target_lang,
        user_gender,
        neural_only if neural_only is not None else NEURAL_ONLY_DEFAULT,
        sample_rate_hz or 22050,
    )

    _, _, audio_s3_url = _s3_save_tts_audio(audio_bytes, target_lang)

    resp: Dict = {
        "s3_url": audio_s3_url,
        "visemes_mapped": _map_visemes_to_shapes(visemes_raw),
        "source_text": text,               # original input text
        "translated_text": translated,     # translated text (used for TTS)
    }
    if include_visemes_raw:
        resp["visemes_raw"] = visemes_raw
    if return_transcript:
        resp["transcript"] = text  # for text pipeline, transcript == source_text
    return resp

def pipeline_voice(
    bucket: str,
    key: str,
    current_lang: str,
    target_lang: str,
    user_gender: Optional[str] = None,
    style: Optional[str] = None,
    neural_only: Optional[bool] = None,
    sample_rate_hz: Optional[int] = None,
    include_visemes_raw: bool = False,
    return_transcript: bool = True,
) -> Dict:
    """
    Voice pipeline (S3):
    1) Transcribe from S3
    2) Translate via Bedrock
    3) Synthesize with Polly (+ visemes)
    4) Save to S3 and return presigned URL + visemes
    """
    transcript = transcribe_s3(bucket, key, lang_code_hint=current_lang)
    if not transcript:
        raise HTTPException(status_code=422, detail="Transcribe returned empty transcript (S3).")

    translated = translate_text_bedrock(transcript, current_lang, target_lang, style=style)

    audio_bytes, visemes_raw = synthesize_with_visemes(
        translated,
        target_lang,
        user_gender,
        neural_only if neural_only is not None else NEURAL_ONLY_DEFAULT,
        sample_rate_hz or 22050,
    )

    _, _, audio_s3_url = _s3_save_tts_audio(audio_bytes, target_lang)

    resp: Dict = {
        "s3_url": audio_s3_url,
        "visemes_mapped": _map_visemes_to_shapes(visemes_raw),
        "source_text": transcript,   # original speech transcript
        "translated_text": translated,     # translated text (used for TTS)
    }
    if include_visemes_raw:
        resp["visemes_raw"] = visemes_raw
    if return_transcript:
        resp["transcript"] = transcript
    return resp
