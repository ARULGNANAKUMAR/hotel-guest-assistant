import os
from dotenv import load_dotenv

load_dotenv()

FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
BACKEND_HOST: str = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))

# LLM service configuration (optional — app works without these)
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
LLM_MODEL: str = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")
LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.anthropic.com/v1/messages")
LLM_TIMEOUT_SECONDS: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "5"))
