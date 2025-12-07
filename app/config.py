from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    BASE_DIR: Path = ROOT

    DATA_DIR: Path = ROOT / "data"
    LLM_MODEL: str = "gpt-oss-120b"
    CEREBRAS_API_KEY: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore"
    )

settings = Settings()