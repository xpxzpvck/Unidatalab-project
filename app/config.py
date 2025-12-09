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

    REPLY_PROMPT: str = (
        "You are a friendly McDonald's ordering assistant. "
        "Keep replies concise and natural. "
        "Do NOT claim to add/remove items yourself in this text reply; ask clarifying questions.\n"
    )
    INTENT_PROMPT: str = (
        "You are an ordering intent extractor for a McDonald's text chat. "
        "Analyze the user's message and extract the ordering intent according to the provided schema.\n"
        "RULES:\n"
        "- Use ONLY item names from the provided menu data.\n"
        "- Map user synonyms to the exact menu item name (e.g. if user says 'Coke' or 'Cola', use 'Coca-Cola').\n"
        "- For generic requests like 'burger' or 'drink', use the generic name (e.g. 'burger') so the system can ask for clarification.\n"
        "- If the user indicates they want to cancel the current pending item (e.g. 'no', 'cancel', 'changed mind', 'forget it'), set 'cancel_pending' to true.\n"
        "- Default quantity is 1.\n\n"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore"
    )

settings = Settings()