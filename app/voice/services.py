from __future__ import annotations
import base64
import json
from typing import Optional

import boto3
from botocore.config import Config
import httpx

from app.config import settings


# ---------- boto3 Session helpers ----------

def _get_boto3_session(region: Optional[str] = None) -> boto3.session.Session:
    """
    Create a boto3 Session using explicit credentials from settings when provided.
    Falls back to the default provider chain (EC2/Task role, env, shared config) otherwise.
    """
    kwargs: dict = {"region_name": region or settings.BEDROCK_REGION}

    # Prefer explicit creds from settings if present; allow role-based auth otherwise.
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        kwargs.update(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            aws_session_token=settings.AWS_SESSION_TOKEN,  # may be None
        )

    return boto3.session.Session(**kwargs)


def _bedrock_client():
    """
    Bedrock Runtime client bound to the Bedrock region in settings.
    Uses the session built above so it honors settings creds + session token.
    """
    session = _get_boto3_session(region=settings.BEDROCK_REGION)
    return session.client(
        "bedrock-runtime",
        config=Config(read_timeout=60, retries={"max_attempts": 3, "mode": "standard"}),
    )


# Lazily initialized singleton (so import time stays cheap)
_BEDROCK = None
def _get_bedrock():
    global _BEDROCK
    if _BEDROCK is None:
        _BEDROCK = _bedrock_client()
    return _BEDROCK


# ---------- Bedrock S2S (Nova Sonic) ----------

def s2s_nova_sonic(wav_bytes: bytes, source_lang: str, target_lang: str) -> bytes:
    """
    Send input speech to Amazon Nova Sonic (Bedrock) and receive generated speech
    in the target language.

    Returns raw audio bytes (decode base64 from response). Caller decides MIME.
    """
    body = {
        "input_audio": base64.b64encode(wav_bytes).decode("utf-8"),
        "source_language": source_lang,
        "target_language": target_lang,
        # You can expose these as params if you want to tweak latency/quality
        "latency_mode": "real_time",
    }

    client = _get_bedrock()
    resp = client.invoke_model(
        modelId=settings.BEDROCK_MODEL_ID,
        body=json.dumps(body).encode("utf-8"),
        accept="application/json",
        contentType="application/json",
    )
    payload = json.loads(resp["body"].read())

    # Expecting {"audio": "<base64>"}; adapt if your account/model returns a different schema.
    return base64.b64decode(payload["audio"])


# ---------- Optional: third-party voice cloning vendor ----------

async def clone_enroll(wav_bytes: bytes, display_name: str) -> str:
    """
    Enroll a user voice with a managed cloning vendor.
    Requires CLONE_API_BASE / CLONE_API_KEY in settings.
    """
    if not settings.CLONE_API_BASE or not settings.CLONE_API_KEY:
        raise ValueError("Voice cloning is not configured (CLONE_API_BASE / CLONE_API_KEY).")

    async with httpx.AsyncClient(timeout=60) as cx:
        r = await cx.post(
            f"{settings.CLONE_API_BASE}/voices",
            headers={"Authorization": f"Bearer {settings.CLONE_API_KEY}"},
            files={"audio": ("sample.wav", wav_bytes, "audio/wav")},
            data={"name": display_name},
        )
        r.raise_for_status()
        data = r.json()
        return data["voice_id"]

async def clone_speak(voice_id: str, text: str, lang: str) -> bytes:
    """
    Synthesize speech with a cloned voice.
    """
    if not settings.CLONE_API_BASE or not settings.CLONE_API_KEY:
        raise ValueError("Voice cloning is not configured (CLONE_API_BASE / CLONE_API_KEY).")

    async with httpx.AsyncClient(timeout=60) as cx:
        r = await cx.post(
            f"{settings.CLONE_API_BASE}/tts",
            headers={"Authorization": f"Bearer {settings.CLONE_API_KEY}"},
            json={"voice_id": voice_id, "text": text, "language": lang},
        )
        r.raise_for_status()
        data = r.json()

        # Expecting {"audio":"<base64>"}; adapt if your vendor differs.
        return base64.b64decode(data["audio"])
