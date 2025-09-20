from __future__ import annotations
import base64, json, time, io, uuid
from typing import Optional, List, Dict

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings

# ---------- boto3 clients ----------
def _session_kwargs(region: str):
    kw = {"region_name": region}
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        kw.update(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            aws_session_token=settings.AWS_SESSION_TOKEN,
        )
    return kw

def _polly():
    return boto3.client("polly", config=Config(retries={"max_attempts": 3}), **_session_kwargs(settings.AWS_REGION))

def _translate():
    return boto3.client("translate", config=Config(retries={"max_attempts": 3}), **_session_kwargs(settings.AWS_REGION))

def _s3():
    return boto3.client("s3", config=Config(retries={"max_attempts": 3}), **_session_kwargs(settings.AWS_REGION))

def _transcribe():
    return boto3.client("transcribe", config=Config(retries={"max_attempts": 3}), **_session_kwargs(settings.AWS_REGION))

# ---------- Voice catalog ----------
_VOICE_CACHE = {"ttl": 0, "data": []}
_VOICE_TTL_SECONDS = 3600

def list_polly_voices(lang: Optional[str] = None, require_neural: bool = True) -> List[Dict]:
    now = int(time.time())
    if now >= _VOICE_CACHE["ttl"]:
        polly = _polly()
        token = None
        voices: List[Dict] = []
        while True:
            resp = polly.describe_voices(NextToken=token) if token else polly.describe_voices()
            for v in resp.get("Voices", []):
                voices.append({
                    "id": v["Id"],
                    "gender": v.get("Gender"),
                    "languages": v.get("LanguageCodes", []),
                    "engines": v.get("SupportedEngines", []),
                })
            token = resp.get("NextToken")
            if not token:
                break
        _VOICE_CACHE["ttl"] = now + _VOICE_TTL_SECONDS
        _VOICE_CACHE["data"] = voices

    out = _VOICE_CACHE["data"]
    if lang:
        out = [v for v in out if lang in (v.get("languages") or [])]
    if require_neural:
        out = [v for v in out if "neural" in (v.get("engines") or [])]
    return sorted(out, key=lambda x: (x["languages"], x["gender"], x["id"]))

def is_voice_available(voice_id: str, lang: Optional[str] = None) -> bool:
    voices = list_polly_voices(lang=lang, require_neural=False)
    return any(v["id"] == voice_id for v in voices)

# ---------- Translate lang map ----------
_TRANSLATE_CODE_MAP = {
    "en":"en","en-US":"en","en-GB":"en",
    "ms":"ms","ms-MY":"ms",
    "zh":"zh","zh-CN":"zh",
    "ja":"ja","ja-JP":"ja",
    "ko":"ko","ko-KR":"ko",
    "es":"es","es-ES":"es",
    "fr":"fr","fr-FR":"fr",
    "it":"it","it-IT":"it",
    "pt":"pt","pt-PT":"pt",
    "ru":"ru","ru-RU":"ru",
    "de":"de","de-DE":"de",
    "hi":"hi","hi-IN":"hi",
    "ta":"ta","ta-IN":"ta",
}
def _to_translate(code: Optional[str]) -> Optional[str]:
    return _TRANSLATE_CODE_MAP.get(code, code) if code else None

def translate_text(text: str, source_lang: Optional[str], target_lang: str) -> str:
    if not text:
        return text
    tl = _to_translate(target_lang)
    sl = _to_translate(source_lang) or "auto"
    if not tl:
        return text
    resp = _translate().translate_text(Text=text, SourceLanguageCode=sl, TargetLanguageCode=tl)
    return resp["TranslatedText"]

# ---------- Transcribe (upload to S3 + batch job + poll) ----------
# NOTE: This is simple and reliable for <60s clips. For live use, you'd do streaming Transcribe.
def transcribe_wav_bytes(wav_bytes: bytes, media_format: str, language_code: str, timeout_sec: int = 60) -> str:
    """
    Upload the audio to S3, start a batch TranscriptionJob, poll for completion,
    download the transcript JSON and return the transcript string.
    """
    s3 = _s3()
    transcribe = _transcribe()

    key = f"transcribe/{uuid.uuid4().hex}.{media_format or 'wav'}"
    s3.put_object(Bucket=settings.AWS_S3_BUCKET_AUDIO, Key=key, Body=wav_bytes, ContentType=f"audio/{media_format or 'wav'}")

    job_name = f"job-{uuid.uuid4().hex}"
    media_uri = f"s3://{settings.AWS_S3_BUCKET_AUDIO}/{key}"
    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        LanguageCode=language_code,
        MediaFormat=media_format or "wav",
        Media={"MediaFileUri": media_uri},
        OutputBucketName=settings.AWS_S3_BUCKET_AUDIO,
        OutputKey=f"transcribe/{job_name}/"
    )

    # Poll
    start = time.time()
    while True:
        st = transcribe.get_transcription_job(TranscriptionJobName=job_name)
        status = st["TranscriptionJob"]["TranscriptionJobStatus"]
        if status == "COMPLETED":
            break
        if status == "FAILED":
            raise RuntimeError(f"Transcription failed: {st}")
        if time.time() - start > timeout_sec:
            raise TimeoutError("Transcription timed out")
        time.sleep(2.0)

    # Download transcript JSON from S3
    out_key = f"transcribe/{job_name}/{job_name}.json"
    obj = s3.get_object(Bucket=settings.AWS_S3_BUCKET_AUDIO, Key=out_key)
    data = json.loads(obj["Body"].read().decode("utf-8"))
    text = data["results"]["transcripts"][0]["transcript"].strip()
    return text

# ---------- Polly synth + visemes ----------
def synthesize_with_visemes(text: str, voice_id: str):
    polly = _polly()

    # 1) Audio
    audio = polly.synthesize_speech(
        Text=text,
        VoiceId=voice_id,
        Engine="neural",
        OutputFormat="mp3",
    )
    audio_bytes = audio["AudioStream"].read()

    # 2) SpeechMarks (visemes)
    marks = polly.synthesize_speech(
        Text=text,
        VoiceId=voice_id,
        Engine="neural",
        OutputFormat="json",
        SpeechMarkTypes=["viseme"],
    )

    visemes = []
    for line in io.TextIOWrapper(marks["AudioStream"], encoding="utf-8"):
        try:
            obj = json.loads(line.strip())
            # "time" in ms, "value" is coarse viseme symbol (map this in your frontend/mapper)
            visemes.append({"t": obj.get("time", 0)/1000.0, "morph": obj.get("value")})
        except Exception:
            continue

    return {
        "audio_b64": base64.b64encode(audio_bytes).decode("utf-8"),
        "mime": "audio/mpeg",
        "visemes": visemes,
    }
