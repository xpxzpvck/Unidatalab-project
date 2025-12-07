import json
import os
import logging
from typing import Optional
from dataclasses import dataclass
from pydantic import BaseModel, Field, ValidationError
from cerebras.cloud.sdk import Cerebras

from app.schemas import Menu, OrderItem
from app.config import settings

logger = logging.getLogger(__name__)


class LLMOrderIntent(BaseModel):
    ordered_items: list[OrderItem] = Field(
        default_factory=list,
        description="List of items the user wants to order. Use exact menu names.",
    )
    end_order: bool = Field(
        default=False, description="True if the user explicitly finishes the order."
    )


@dataclass
class LLMResult:
    intent: Optional[LLMOrderIntent]
    raw: str
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and self.intent is not None


class LLMService:
    def __init__(self, model_name: str = settings.LLM_MODEL):
        api_key = settings.CEREBRAS_API_KEY
        if not api_key:
            logger.warning("CEREBRAS_API_KEY is not set. LLM calls will fail.")
            self.client = None
        else:
            try:
                self.client = Cerebras(api_key=api_key)
            except Exception as e:
                logger.error(f"Failed to init Cerebras client: {e}")
                self.client = None
        self.model_name = model_name

    def _menu_to_prompt_format(self, menu: Menu) -> str:
        payload = {
            "items": [
                {
                    "name": item.name,
                    "category": item.category,
                    "price": item.price,
                    "properties": item.properties or None,
                }
                for item in menu.items.values()
            ],
            "ingredients": list(menu.ingredients.keys()),
        }
        return json.dumps(payload, indent=2)

    def parse_intent(
        self, user_message: str, menu: Menu, prior_summary: str = ""
    ) -> LLMResult:
        if not self.client:
            return LLMResult(
                intent=None,
                raw="",
                error="LLM Client not initialized (missing API key?)",
            )

        menu_json = self._menu_to_prompt_format(menu)

        system_content = (
            "You are an ordering intent extractor for a McDonald's text chat. "
            "Analyze the user's message and extract the ordering intent according to the provided schema.\n"
            "RULES:\n"
            "- Use ONLY item names from the provided menu data.\n"
            "- For generic requests like 'burger' or 'drink', use the generic name (e.g. 'burger') so the system can ask for clarification.\n"
            "- Default quantity is 1.\n\n"
            f"Current order summary: {prior_summary or 'empty'}\n"
            f"Menu Data:\n{menu_json}"
        )

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_message},
        ]

        try:
            json_schema = LLMOrderIntent.model_json_schema()

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "order_intent_schema",
                        "strict": False,
                        "schema": json_schema,
                    },
                },
                temperature=0,
            )

            raw_text = response.choices[0].message.content or ""

            intent = LLMOrderIntent.model_validate_json(raw_text)
            return LLMResult(intent=intent, raw=raw_text)

        except Exception as exc:
            logger.error(f"LLM Error in parse_intent: {exc}")
            return LLMResult(intent=None, raw=str(exc), error=str(exc))

    def generate_reply(
        self, user_message: str, menu: Menu, order_summary: str = ""
    ) -> str:
        if not self.client:
            return "Sorry, the LLM service is currently unavailable."

        menu_dump = self._menu_to_prompt_format(menu)

        system_prompt = (
            "You are a friendly McDonald's ordering assistant. "
            "Keep replies concise and natural. "
            "Do NOT claim to add/remove items yourself in this text reply; just acknowledge or ask clarifying questions.\n"
            f"Menu context: {menu_dump}\n"
            f"Current order: {order_summary or 'empty'}\n"
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.7,
                max_completion_tokens=300,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            logger.error(f"LLM Error in generate_reply: {exc}")
            return "One moment, I'm checking the menu..."
