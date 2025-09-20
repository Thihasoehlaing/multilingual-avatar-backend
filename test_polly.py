#!/usr/bin/env python3
"""
aws_ai_services_smoketest.py

One-file smoke test for AWS AI services used in your backend:
- Amazon Translate (text -> text)
- Amazon Polly (text -> mp3 + speechmarks/visemes)
- Amazon Transcribe (audio file -> transcript) [batch via S3]
- Amazon Bedrock Nova Sonic S2S (speech -> speech)

Usage examples:
  python aws_ai_services_smoketest.py --text "Hello from demo" --src en-US --tgt ja-JP --voice Matthew
  python aws_ai_services_smoketest.py --audio sample.wav --src en-US --tgt ms-MY
  python aws_ai_services_smoketest.py --text "早上好" --src zh-CN --tgt en-US --voice Joanna --audio sample.wav

Environment variables used (fallbacks shown):
  AWS_REGION=ap-southeast-5             Region for Translate/Polly/Transcribe/S3
  AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN
  AWS_S3_BUCKET_AUDIO=your-audio-bucket
  BEDROCK_REGION=ap-southeast-5         Region for Bedrock Runtime
  BEDROCK_MODEL_ID=amazon.nova-s2s-v1:0 Model ID for Nova Sonic S2S (adjust if your account differs)

Outputs are saved under ./out/
"""

import argparse
import base64
import io
import json
import os
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError


# -------------------------
# Env & helpers
# -------------------------

def env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    return v if v is not None and v != "" else default


AWS_REGION = env("AWS_REGION", "us-east-1")
AWS_S3_BUCKET_AUDIO = env("AWS_S3_BUCKET_AUDIO", "avatar-ai-cache")

BEDROCK_REGION = env("BEDROCK_REGION", "us-east-1")
BEDROCK_MODEL_ID = env("BEDROCK_MODEL_ID", "amazon.nova-s2s-v1:0")


def _session_kwargs(region: str) -> Dict[str, Any]:
    kw: Dict[str, Any] = {"region_name": region}
    ak = env("AWS_ACCESS_KEY_ID")
    sk = env("AWS_SECRET_ACCESS_KEY")
    tk = env("AWS_SESSION_TOKEN")
    if ak and sk:
        kw["aws_access_key_id"] = ak
        kw["aws_secret_access_key"] = sk
        if tk:
            kw["aws_session_token"] = tk
    return kw


def _translate():
    return boto3.client(
        "translate",
        config=Config(retries={"max_attempts": 3, "mode": "standard"}),
        **_session_kwargs(AWS_REGION),
    )


def _polly():
    return boto3.client(
        "polly",
        config=Config(retries={"max_attempts": 3, "mode": "standard"}),
        **_session_kwargs(AWS_REGION),
    )


def _s3():
    return boto3.client(
        "s3",
        config=Config(retries={"max_attempts": 3, "mode": "standard"}),
        **_session_kwargs(AWS_REGION),
    )


def _transcribe():
    return boto3.client(
        "transcribe",
        config=Config(retries={"max_attempts": 3, "mode": "standard"}),
        **_session_kwargs(AWS_REGION),
    )


def _bedrock():
    return boto3.client(
        "bedrock-runtime",
        config=Config(read_timeout=60, retries={"max_attempts": 3, "mode": "standard"}),
        **_session_kwargs(BEDROCK_REGION),
    )


def ensure_outdir() -> Path:
    p = Path("out")
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


# -------------------------
# Translate
# -------------------------

def test_translate(text: str, source_lang: Optional[str], target_lang: str) -> str:
    if not text:
        return text
    sl = source_lang or "auto"
    print(f"[Translate] {sl} -> {target_lang}: {text!r}")
    resp = _translate().translate_text(Text=text, SourceLanguageCode=sl, TargetLanguageCode=target_lang)
    out = resp["TranslatedText"]
    print(f"[Translate] Output: {out!r}")
    return out


# -------------------------
# Polly (audio + visemes)
# -------------------------

def _polly_synthesize(text: str, voice_id: str) -> bytes:
    try:
        resp = _polly().synthesize_speech(Text=text, VoiceId=voice_id, Engine="neural", OutputFormat="mp3")
    except (ClientError, BotoCoreError) as e:
        print(f"[Polly] Neural failed ({e}); falling back to standard engine.")
        resp = _polly().synthesize_speech(Text=text, VoiceId=voice_id, Engine="standard", OutputFormat="mp3")
    return resp["AudioStream"].read()


def _polly_visemes(text: str, voice_id: str) -> List[Dict[str, Any]]:
    try:
        resp = _polly().synthesize_speech(
            Text=text,
            VoiceId=voice_id,
            Engine="neural",
            OutputFormat="json",
            SpeechMarkTypes=["viseme"],
        )
    except (ClientError, BotoCoreError) as e:
        print(f"[Polly] SpeechMarks(neural) failed ({e}); trying standard.")
        resp = _polly().synthesize_speech(
            Text=text,
            VoiceId=voice_id,
            Engine="standard",
            OutputFormat="json",
            SpeechMarkTypes=["viseme"],
        )
    marks: List[Dict[str, Any]] = []
    for line in io.TextIOWrapper(resp["AudioStream"], encoding="utf-8"):
        try:
            obj = json.loads(line.strip())
            # "time" in ms, "value" = viseme label
            marks.append({"t": round(obj.get("time", 0) / 1000.0, 4), "morph": obj.get("value")})
        except Exception:
            continue
    return marks


def test_polly(text: str, voice_id: str) -> Dict[str, Any]:
    print(f"[Polly] Synthesizing with voice '{voice_id}' ...")
    audio_bytes = _polly_synthesize(text, voice_id)
    visemes = _polly_visemes(text, voice_id)

    outdir = ensure_outdir()
    mp3_path = outdir / "polly_tts.mp3"
    json_path = outdir / "polly_visemes.json"
    write_file(mp3_path, audio_bytes)
    write_file(json_path, json.dumps(visemes, ensure_ascii=False, indent=2).encode("utf-8"))
    print(f"[Polly] Saved MP3 -> {mp3_path}")
    print(f"[Polly] Saved visemes -> {json_path}")

    return {"audio_path": str(mp3_path), "visemes_path": str(json_path), "viseme_count": len(visemes)}


# -------------------------
# Transcribe (batch via S3)
# -------------------------

def test_transcribe(local_audio_path: Optional[str], language_code: str, timeout_sec: int = 300) -> Optional[str]:
    if not local_audio_path:
        print("[Transcribe] Skipped (no --audio provided).")
        return None
    if not AWS_S3_BUCKET_AUDIO:
        raise RuntimeError("AWS_S3_BUCKET_AUDIO env var is required for Transcribe test.")

    p = Path(local_audio_path)
    if not p.exists():
        raise FileNotFoundError(f"Audio file not found: {local_audio_path}")

    ext = p.suffix.lower().lstrip(".") or "wav"
    if ext == "m4a":
        ext = "mp4"  # Transcribe expects 'mp4' format label

    s3 = _s3()
    transcribe = _transcribe()
    key = f"transcribe/{uuid.uuid4().hex}.{ext}"

    print(f"[Transcribe] Uploading {p} to s3://{AWS_S3_BUCKET_AUDIO}/{key}")
    s3.upload_file(str(p), AWS_S3_BUCKET_AUDIO, key, ExtraArgs={"ContentType": f"audio/{ext}"})

    job_name = f"job-{uuid.uuid4().hex}"
    media_uri = f"s3://{AWS_S3_BUCKET_AUDIO}/{key}"
    print(f"[Transcribe] Starting job={job_name}, media={media_uri}, lang={language_code}, format={ext}")
    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        LanguageCode=language_code,
        MediaFormat=ext,
        Media={"MediaFileUri": media_uri},
        OutputBucketName=AWS_S3_BUCKET_AUDIO,
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
    print(f"[Transcribe] Fetching transcript at s3://{AWS_S3_BUCKET_AUDIO}/{out_key}")
    obj = s3.get_object(Bucket=AWS_S3_BUCKET_AUDIO, Key=out_key)
    data = json.loads(obj["Body"].read().decode("utf-8"))
    text = data["results"]["transcripts"][0]["transcript"].strip()

    outdir = ensure_outdir()
    path = outdir / "transcribe_transcript.txt"
    write_file(path, (text + "\n").encode("utf-8"))
    print(f"[Transcribe] Saved transcript -> {path}")
    return text


# -------------------------
# Bedrock Nova Sonic S2S
# -------------------------

def test_bedrock_s2s(local_audio_path: Optional[str], source_lang: str, target_lang: str) -> Optional[str]:
    if not local_audio_path:
        print("[Bedrock] Skipped (no --audio provided).")
        return None

    p = Path(local_audio_path)
    if not p.exists():
        raise FileNotFoundError(f"Audio file not found: {local_audio_path}")

    audio_bytes = p.read_bytes()
    body = {
        "input_audio": base64.b64encode(audio_bytes).decode("utf-8"),
        "source_language": source_lang,
        "target_language": target_lang,
        "latency_mode": "real_time",
    }

    print(f"[Bedrock] Invoking model {BEDROCK_MODEL_ID} in {BEDROCK_REGION} ...")
    resp = _bedrock().invoke_model(
        modelId=BEDROCK_MODEL_ID,
        body=json.dumps(body).encode("utf-8"),
        accept="application/json",
        contentType="application/json",
    )
    payload = json.loads(resp["body"].read())
    b64audio = payload.get("audio")
    if not b64audio:
        raise RuntimeError(f"Bedrock response missing 'audio' key: {payload}")

    out_audio = base64.b64decode(b64audio)
    outdir = ensure_outdir()
    path = outdir / "bedrock_s2s.mp3"
    write_file(path, out_audio)
    print(f"[Bedrock] Saved MP3 -> {path}")
    return str(path)


# -------------------------
# Main
# -------------------------

def main():
    parser = argparse.ArgumentParser(description="AWS AI Services Smoke Test")
    parser.add_argument("--text", default="Hello, this is a multilingual avatar demo.")
    parser.add_argument("--src", "--source-lang", dest="src", default="en-US")
    parser.add_argument("--tgt", "--target-lang", dest="tgt", default="ja-JP")
    parser.add_argument("--voice", default="Matthew", help="Polly VoiceId (e.g., Matthew, Joanna, Zhiyu)")
    parser.add_argument("--audio", help="Path to input audio file for Transcribe & Bedrock S2S (e.g., sample.wav)")
    args = parser.parse_args()

    print(f"== Regions ==")
    print(f"AWS_REGION={AWS_REGION}")
    print(f"BEDROCK_REGION={BEDROCK_REGION}, BEDROCK_MODEL_ID={BEDROCK_MODEL_ID}")
    if AWS_S3_BUCKET_AUDIO:
        print(f"AWS_S3_BUCKET_AUDIO={AWS_S3_BUCKET_AUDIO}")
    else:
        print("AWS_S3_BUCKET_AUDIO is not set (Transcribe test will fail if --audio is provided).")

    # Translate
    try:
        translated = test_translate(args.text, args.src, args.tgt)
    except Exception as e:
        print(f"[Translate] ERROR: {e}")
        translated = args.text

    # Polly
    try:
        test_polly(translated, args.voice)
    except Exception as e:
        print(f"[Polly] ERROR: {e}")

    # Transcribe (requires --audio and S3 bucket)
    try:
        tr_text = test_transcribe(args.audio, language_code=args.src)
        if tr_text:
            print(f"[Transcribe] Transcript: {tr_text[:80]}{'...' if len(tr_text)>80 else ''}")
    except Exception as e:
        print(f"[Transcribe] ERROR: {e}")

    # Bedrock S2S (requires --audio)
    try:
        bedrock_path = test_bedrock_s2s(args.audio, source_lang=args.src, target_lang=args.tgt)
        if bedrock_path:
            print(f"[Bedrock] Output at: {bedrock_path}")
    except Exception as e:
        print(f"[Bedrock] ERROR: {e}")

    print("\nDone. Check the ./out/ folder for artifacts.")


if __name__ == "__main__":
    main()
