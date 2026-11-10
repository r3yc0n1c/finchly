"""Finchly API configuration settings."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Application runtime settings loaded from environment."""

    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql://finchly:finchly_dev@localhost:5432/finchly"
    )
    nats_url: str = os.getenv("NATS_URL", "nats://localhost:4222")
    s3_endpoint_url: str = os.getenv("S3_ENDPOINT_URL", "http://localhost:9000")
    s3_access_key_id: str = os.getenv("S3_ACCESS_KEY_ID", "finchly")
    s3_secret_access_key: str = os.getenv("S3_SECRET_ACCESS_KEY", "finchly_dev_secret")
    s3_bucket_name: str = os.getenv("S3_BUCKET_NAME", "finchly-documents")
    environment: str = os.getenv("ENVIRONMENT", "development")
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))


settings = Settings()
