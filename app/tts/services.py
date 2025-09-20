from __future__ import annotations

import base64
import io
import json
import time
import uuid
from typing import Dict, List, Optional, Tuple

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings


# =========================
# Low-level AWS clients
# =========================

def _session_kwargs(region: str) -> Dict:
    """
    Build boto3 client kwargs using explicit creds from env/settings if provided.
    Falls back to default provider chain (recommended in prod via instance/task roles).
    """
    kw: Dict = {"region_name": region}
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        kw.update(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            aws_session_token=settings.AWS_SESSION_TOKEN,
        )
    return kw


def _polly():
    return boto3.client(
        "polly",
        config=Config(retries={"max_attempts": 3, "mode": "standard"}),
        **_session_kwargs(settings.AWS_REGION),
    )


def _translate():
    return boto3.client(
        "translate",
        config=Config(retries={"max_attempts": 3, "mode": "standard"}),
        **_session_kwargs(settings.AWS_REGION),
    )


def _s3():
    return boto3.client(
        "s3",
        config=Config(retries={"max_attempts": 3, "mode": "standard"}),
        **_session_kwargs(settings.AWS_REGION),
    )


def _transcribe():
    return boto3.client(
        "transcribe",
        config=Config(retries={"max_attempts": 3, "mode": "standard"}),
        **_session_kwargs(settings.AWS_REGION),
    )


# =========================
# Polly voice catalog (cached + defensive)
# =========================

_VOICE_CACHE = {"ttl": 0, "data": []}
_VOICE_TTL_SECONDS = 3600


def list_polly_voices(lang: Optional[str] = None, require_neural: bool = True) -> List[Dict]:
    """
    Safely list voices. If AWS creds are expired/unavailable,
    return the cached list (if any) or [] without raising exceptions.
    """
    now = int(time.time())
    if now >= _VOICE_CACHE["ttl"]:
        try:
            polly = _polly()
            token = None
            voices: List[Dict] = []
            while True:
                resp = polly.describe_voices(NextToken=token) if token else polly.describe_voices()
                for v in resp.get("Voices", []):
                    voices.append(
                        {
                            "id": v["Id"],                                 # e.g., "Matthew"
                            "gender": (v.get("Gender") or "").lower(),     # "male"/"female"
                            "languages": [x for x in (v.get("LanguageCodes") or [])],
                            "engines": [x for x in (v.get("SupportedEngines") or [])],
                        }
                    )
                token = resp.get("NextToken")
                if not token:
                    break
            _VOICE_CACHE["ttl"] = now + _VOICE_TTL_SECONDS
            _VOICE_CACHE["data"] = voices
        except (ClientError, BotoCoreError, Exception):
            # keep cache (if any) and do not crash
            pass

    voices = list(_VOICE_CACHE["data"]) if _VOICE_CACHE["data"] else []
    if lang:
        voices = [v for v in voices if lang in (v.get("languages") or [])]
    if require_neural:
        voices = [v for v in voices if "neural" in (v.get("engines") or [])]
    return sorted(voices, key=lambda v: (v.get("languages"), v.get("gender"), v["id"]))


def is_voice_available(voice_id: str, lang: Optional[str] = None) -> bool:
    try:
        voices = list_polly_voices(lang=lang, require_neural=False)
    except Exception:
        return False
    return any(v["id"] == voice_id for v in voices)


def supported_languages() -> List[str]:
    """
    Return a sorted list of Polly LanguageCodes available in this region,
    derived from DescribeVoices.
    Example: ["en-US","en-GB","zh-CN","yue-HK","ja-JP", ...]
    """
    voices = list_polly_voices(lang=None, require_neural=False)
    langs = set()
    for v in voices:
        for lc in v.get("languages") or []:
            langs.add(lc)
    return sorted(langs)


def language_gender_availability() -> Dict[str, Dict[str, bool]]:
    """
    For each language, indicate whether male/female voices exist.
    Returns: {"en-US":{"male":True,"female":True}, "zh-CN":{"male":False,"female":True}, ...}
    """
    info: Dict[str, Dict[str, bool]] = {}
    all_voices = list_polly_voices(lang=None, require_neural=False)
    for v in all_voices:
        g = (v.get("gender") or "").lower()
        for lc in v.get("languages") or []:
            slot = info.setdefault(lc, {"male": False, "female": False})
            if g in ("male", "female"):
                slot[g] = True
    return info


# =========================
# Language normalization for Translate
# =========================

_TRANSLATE_CODE_MAP = {
    "en": "en", "en-US": "en", "en-GB": "en",
    "ms": "ms", "ms-MY": "ms",
    "zh": "zh", "zh-CN": "zh",
    "yue": "yue", "yue-HK": "yue",   # Translate typically doesn't support Cantonese → we skip when 'yue'
    "ja": "ja", "ja-JP": "ja",
    "ko": "ko", "ko-KR": "ko",
    "es": "es", "es-ES": "es",
    "fr": "fr", "fr-FR": "fr",
    "it": "it", "it-IT": "it",
    "pt": "pt", "pt-PT": "pt",
    "ru": "ru", "ru-RU": "ru",
    "de": "de", "de-DE": "de",
    "hi": "hi", "hi-IN": "hi",
    "ta": "ta", "ta-IN": "ta",
}

# Translate’s own supported set (subset)
_TRANSLATE_SUPPORTED = {
    "en","ms","zh","ja","ko","es","fr","it","pt","ru","de","hi","ta"
}


def _to_translate(code: Optional[str]) -> Optional[str]:
    return _TRANSLATE_CODE_MAP.get(code, code) if code else None


def translate_text(text: str, source_lang: Optional[str], target_lang: str) -> str:
    """
    Translate text from source_lang -> target_lang using Amazon Translate.
    If target isn't supported by Translate (e.g., Cantonese 'yue'), return original text.
    """
    if not text:
        return text
    tl = _to_translate(target_lang)
    sl = _to_translate(source_lang) or "auto"
    if not tl or tl not in _TRANSLATE_SUPPORTED:
        # Skip translation (e.g., yue-HK) — expect caller to supply target text already.
        return text
    resp = _translate().translate_text(Text=text, SourceLanguageCode=sl, TargetLanguageCode=tl)
    return resp["TranslatedText"]


# =========================
# Voice selection (per-language, gender-aware)
# =========================

# Minimal, safe preferences (expand as you validate in your region)
PREFERRED_VOICES: Dict[str, Dict[str, str]] = {
    "en-US": {"male": "Matthew", "female": "Joanna"},
    "en-GB": {"male": "Brian",   "female": "Emma"},
    "zh-CN": {"female": "Zhiyu"},      # Mandarin often female-only per region
    "yue-HK": {"female": "Hiujin"},    # Cantonese often female-only
}

def pick_voice_for(
    target_lang: str,
    user_gender: Optional[str],
    voice_overrides: Optional[Dict[str, str]] = None,
) -> Tuple[str, str]:
    """
    Decide the best Polly VoiceId for `target_lang`.
    Order:
      1) per-language override (if available & valid)
      2) preferred per-language (gender-aware) if available
      3) any neural voice in that language (prefer matching gender)
      4) final fallback: global gender default (Matthew/Joanna)
    Returns: (voice_id, reason) where reason ∈ {"override","preferred","any","fallback"}.
    """
    g = (user_gender or "").lower()
    if g not in ("male", "female"):
        g = None

    langs = set(supported_languages())
    lang_ok = target_lang in langs

    # 1) per-language override
    if voice_overrides and target_lang in voice_overrides:
        vid = voice_overrides[target_lang]
        if lang_ok and is_voice_available(vid, lang=target_lang):
            return vid, "override"

    # 2) preferred per-language
    if lang_ok:
        pref = PREFERRED_VOICES.get(target_lang) or {}
        if g and pref.get(g) and is_voice_available(pref[g], lang=target_lang):
            return pref[g], "preferred"
        # try other gender if only one exists
        for k in ("female", "male"):
            if pref.get(k) and is_voice_available(pref[k], lang=target_lang):
                return pref[k], "preferred"

        # 3) any neural voice in that language (prefer same gender)
        avail = list_polly_voices(lang=target_lang, require_neural=True)
        if avail:
            if g:
                for v in avail:
                    if (v.get("gender") or "").lower() == g:
                        return v["id"], "any"
            return avail[0]["id"], "any"

    # 4) final fallback (language not supported or no neural voices)
    fallback = settings.POLLY_VOICE_MALE if g == "male" else settings.POLLY_VOICE_FEMALE
    return fallback, "fallback"


# =========================
# Transcribe (batch; short files)
# =========================

def transcribe_wav_bytes(
    wav_bytes: bytes,
    media_format: str,
    language_code: str,
    timeout_sec: int = 60,
) -> str:
    """
    Upload to S3, start a batch TranscriptionJob, poll for completion,
    then fetch the transcript from S3.
    """
    s3 = _s3()
    transcribe = _transcribe()

    ext = (media_format or "wav").lower()
    key = f"transcribe/{uuid.uuid4().hex}.{ext}"
    s3.put_object(
        Bucket=settings.AWS_S3_BUCKET_AUDIO,
        Key=key,
        Body=wav_bytes,
        ContentType=f"audio/{ext}",
    )

    job_name = f"job-{uuid.uuid4().hex}"
    media_uri = f"s3://{settings.AWS_S3_BUCKET_AUDIO}/{key}"

    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        LanguageCode=language_code,
        MediaFormat=ext,
        Media={"MediaFileUri": media_uri},
        OutputBucketName=settings.AWS_S3_BUCKET_AUDIO,
        OutputKey=f"transcribe/{job_name}/",
    )

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

    out_key = f"transcribe/{job_name}/{job_name}.json"
    obj = s3.get_object(Bucket=settings.AWS_S3_BUCKET_AUDIO, Key=out_key)
    data = json.loads(obj["Body"].read().decode("utf-8"))
    text = data["results"]["transcripts"][0]["transcript"].strip()
    return text


# =========================
# TTS + SpeechMarks (visemes)
# =========================

def synthesize_with_visemes(text: str, voice_id: str) -> Dict:
    """
    Synthesize `text` with Polly (neural MP3) and fetch SpeechMarks (visemes).
    Returns: { audio_b64, mime, visemes: [{t, morph}] }
    """
    polly = _polly()

    # Audio
    audio = polly.synthesize_speech(
        Text=text,
        VoiceId=voice_id,
        Engine="neural",
        OutputFormat="mp3",
    )
    audio_bytes = audio["AudioStream"].read()

    # SpeechMarks (visemes)
    marks = polly.synthesize_speech(
        Text=text,
        VoiceId=voice_id,
        Engine="neural",
        OutputFormat="json",
        SpeechMarkTypes=["viseme"],
    )

    visemes: List[Dict] = []
    for line in io.TextIOWrapper(marks["AudioStream"], encoding="utf-8"):
        try:
            obj = json.loads(line.strip())
            # "time" (ms), "value" (viseme label)
            visemes.append({"t": obj.get("time", 0) / 1000.0, "morph": obj.get("value")})
        except Exception:
            continue

    return {
        "audio_b64": base64.b64encode(audio_bytes).decode("utf-8"),
        "mime": "audio/mpeg",
        "visemes": visemes,
    }
