from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    BASE_DIR: Path = ROOT
    DATA_DIR: Path = ROOT / "data"
    MENU_FILES: List[str] = [
        "menu_deals.yaml",
        "menu_ingredients.yaml",
        "menu_upsells.yaml",
        "menu_virtual_items.yaml",
    ]

    LLM_MODEL: str = "gpt-oss-120b"
    CEREBRAS_API_KEY: str = ""

    MEDIUM_SIZE_DISCOUNT: float = 0.2
    SMALL_SIZE_DISCOUNT: float = 0.4
    DOUBLE_DEAL_DISCOUNT: float = 0.2

    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore"
    )

settings = Settings()