import base64
import json
from typing import Dict, Any, List, Optional

import boto3
from botocore.config import Config

from app.config import settings
from app.tts.viseme_map import to_morph


# One-time clients
_boto_cfg = Config(region_name=settings.AWS_REGION)
_polly = boto3.client("polly", config=_boto_cfg)
_translate = boto3.client("translate", config=_boto_cfg)


def translate_text(text: str, source_lang: Optional[str], target_lang: str) -> str:
    """
    Use Amazon Translate to get target text when source_lang is provided
    and differs from target. If source_lang is None, treat as same-language.
    """
    if not text:
        return text
    if source_lang and source_lang != target_lang:
        resp = _translate.translate_text(
            Text=text,
            SourceLanguageCode=source_lang,
            TargetLanguageCode=target_lang,
        )
        return resp["TranslatedText"]
    # No translation needed
    return text


def synthesize_with_visemes(text: str, voice_id: str = "Joanna") -> Dict[str, Any]:
    """
    Call Polly Neural TTS for audio and Speech Marks for visemes+words.
    Returns: { "audioBase64": str, "visemes": List[Dict], "sampleRate": int }
    """
    # Audio
    audio_resp = _polly.synthesize_speech(
        Text=text,
        VoiceId=voice_id,
        Engine="neural",
        OutputFormat="mp3",
    )
    audio_bytes = audio_resp["AudioStream"].read()
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

    # Speech marks (viseme + word)
    marks_resp = _polly.synthesize_speech(
        Text=text,
        VoiceId=voice_id,
        Engine="neural",
        OutputFormat="json",
        SpeechMarkTypes=["viseme", "word"],
    )
    marks_lines = marks_resp["AudioStream"].read().decode("utf-8").splitlines()

    visemes: List[Dict[str, Any]] = []
    for line in marks_lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = item.get("type")
        if t == "viseme":
            # Polly fields: {"time":123,"type":"viseme","value":"p"}
            visemes.append({
                "type": "viseme",
                "time": item.get("time", 0),            # ms
                "value": item.get("value"),
                "morph": to_morph(item.get("value", ""))  # normalized for avatar
            })
        elif t == "word":
            # useful for captions / karaoke
            # {"time":456,"type":"word","value":"hello","start":456,"end":600}
            visemes.append({
                "type": "word",
                "time": item.get("time", 0),
                "value": item.get("value")
            })

    # Polly MP3 default sample rate is usually 22050 or 24000 depending on voice; expose a common value
    return {
        "audioBase64": audio_b64,
        "visemes": visemes,
        "sampleRate": 22050
    }


def tts_pipeline(
    text: str,
    user_voice_pref: Optional[str],
    target_lang: str,
    source_lang: Optional[str] = None,
    override_voice: Optional[str] = None,
) -> Dict[str, Any]:
    """
    High-level: translate (if needed) → synthesize with selected voice.
    Voice priority: override_voice > user_voice_pref > defaults by gender (handled at route level).
    """
    # 1) Translate if source_lang provided and different
    final_text = translate_text(text, source_lang=source_lang, target_lang=target_lang)

    # 2) Voice choice
    voice = override_voice or user_voice_pref or settings.POLLY_VOICE_FEMALE

    # 3) Synthesize + visemes
    return synthesize_with_visemes(final_text, voice_id=voice)
