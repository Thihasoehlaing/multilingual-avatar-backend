import os
import uuid
import boto3
from fastapi import APIRouter, UploadFile, HTTPException
from botocore.exceptions import BotoCoreError, ClientError

router = APIRouter(prefix="/voice", tags=["voice"])

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_BUCKET = os.getenv("AWS_S3_BUCKET_AUDIO", "avatar-ai-cache")

# Allowed prefix to prevent deleting arbitrary keys
ALLOWED_PREFIXES = ("voice/in/", "transcribe/in/")

s3 = boto3.client("s3", region_name=AWS_REGION)


@router.post("/upload")
async def upload_voice(voice_file: UploadFile):
    """
    Upload a recorded voice file to S3 and return its key + URI.
    Does not run STT/TTS — only storage.
    """
    if not voice_file:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    try:
        # choose an extension based on the incoming file (fallback .webm)
        orig = voice_file.filename or ""
        ext = os.path.splitext(orig)[1] or ".webm"
        key = f"voice/in/{uuid.uuid4().hex}{ext}"

        body = await voice_file.read()
        if not body:
            raise HTTPException(status_code=400, detail="Empty file.")

        s3.put_object(
            Bucket=AWS_BUCKET,
            Key=key,
            Body=body,
            ContentType=voice_file.content_type or "application/octet-stream",
        )

        return {
            "bucket": AWS_BUCKET,
            "key": key,
            "uri": f"s3://{AWS_BUCKET}/{key}",
        }

    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=500, detail=f"S3 upload failed: {e}")


@router.delete("/{key:path}")
async def delete_voice_object(key: str):
    """
    Delete a previously uploaded object. Only allows keys in ALLOWED_PREFIXES.
    Example: DELETE /voice/voice/in/4f3d...e9.webm
    """
    if not key or not any(key.startswith(p) for p in ALLOWED_PREFIXES):
        raise HTTPException(
            status_code=400,
            detail=f"Key must start with one of: {', '.join(ALLOWED_PREFIXES)}"
        )

    try:
        # Optional: ensure it exists first
        s3.head_object(Bucket=AWS_BUCKET, Key=key)
    except ClientError as e:
        # NotFound or forbidden → surface a clear 404
        code = e.response.get("Error", {}).get("Code")
        if code in ("404", "NoSuchKey", "NotFound"):
            raise HTTPException(status_code=404, detail="Object not found.")
        # other errors fall through to delete attempt or 500
    try:
        s3.delete_object(Bucket=AWS_BUCKET, Key=key)
        return {"deleted": True, "bucket": AWS_BUCKET, "key": key}
    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=500, detail=f"S3 delete failed: {e}")
