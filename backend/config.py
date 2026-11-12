"""Application configuration loaded from environment variables."""

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
load_dotenv(PROJECT_DIR / ".env")


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


class Settings:
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agentpay.db")
    PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "").strip()
    PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
    PAYPAL_BASE_URL = os.getenv(
        "PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com"
    ).rstrip("/")
    PAYPAL_RETURN_URL = os.getenv(
        "PAYPAL_RETURN_URL", "http://localhost:5173/payment/return"
    )
    PAYPAL_CANCEL_URL = os.getenv(
        "PAYPAL_CANCEL_URL", "http://localhost:5173/contract"
    )
    BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")
    BACKEND_PORT = _positive_int("BACKEND_PORT", 8000)
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]
    MAX_BUDGET = 5.00
    MAX_CSV_SIZE_MB = _positive_int("MAX_CSV_SIZE_MB", 5)
    UPLOAD_DIR = BACKEND_DIR / "uploads"

    @property
    def paypal_mock_mode(self) -> bool:
        return not (self.PAYPAL_CLIENT_ID and self.PAYPAL_CLIENT_SECRET)


settings = Settings()
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
