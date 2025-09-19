from typing import List, Union
from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Multimodal AI Avatar"
    APP_ENV: str = "dev"
    APP_PORT: int = 8000

    # Allow list of origins (JSON list or comma-separated string in .env)
    ALLOW_ORIGINS: List[Union[AnyHttpUrl, str]] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    # JWT
    JWT_SECRET: str
    JWT_EXPIRES_MINUTES: int = 60

    # Mongo (self-hosted)
    MONGO_CONNECTION: str = "mongodb"
    MONGO_HOST: str = "127.0.0.1"
    MONGO_PORT: int = 27017
    MONGO_DATABASE: str = "ai_avatar"
    MONGO_USERNAME: str
    MONGO_PASSWORD: str
    MONGO_AUTH_SOURCE: str = "admin"

    # AWS
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_SESSION_TOKEN: str | None = None
    AWS_REGION: str = "ap-southeast-5"
    AWS_S3_BUCKET_AUDIO: str = "avatar-audio-cache"
    POLLY_VOICE_MALE: str = "Matthew"
    POLLY_VOICE_FEMALE: str = "Joanna"

    # Load from .env file
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Security / Limits
    MAX_TTS_TEXT_LEN: int = 500         # prevent abuse & big bills
    RATE_TTS_PER_MIN: int = 12          # per-user per-minute
    RATE_AUTH_PER_MIN: int = 20         # signup/login bursts
    TRUSTED_HOSTS: list[str] = ["127.0.0.1", "localhost"]  # add your EC2 DNS later


settings = Settings()
