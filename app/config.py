from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path: MCP hosts such as Claude Desktop launch the server from another directory.
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """Application settings, read from environment variables or `.env`."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    app_name: str = "Support Triage API"
    # pg8000 is a pure-Python driver: no native DLLs to install or get blocked.
    database_url: str = "postgresql+pg8000://tickets:tickets@localhost:5433/tickets"

    # "provider:model", e.g. "google:gemini-3.5-flash-lite" or "anthropic:claude-haiku-5-5".
    ai_model: str = "google:gemini-3.5-flash-lite"
    # Optional so the app and the test suite can run without an API key.
    google_api_key: str | None = None
    # Judge for LLM-graded evals: a different model than the agent avoids self-grading bias.
    eval_judge_model: str = "google:gemini-3.1-flash-lite"


settings = Settings()
