import boto3
import os

# Load from env
region = os.getenv("AWS_REGION", "ap-southeast-5")
access_key = os.getenv("AWS_ACCESS_KEY_ID")
secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
session_token = os.getenv("AWS_SESSION_TOKEN")

# Initialize Polly client
polly = boto3.client(
    "polly",
    region_name=region,
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
    aws_session_token=session_token
)

# Call Polly
response = polly.synthesize_speech(
    Text="Hello, this is a test of Amazon Polly in our multilingual AI avatar project.",
    OutputFormat="mp3",
    VoiceId="Matthew"  # Or Joanna
)

# Save to file
with open("polly_test.mp3", "wb") as f:
    f.write(response["AudioStream"].read())

print("✅ Polly test complete. Check polly_test.mp3")
