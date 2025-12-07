from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import List, Optional

from cerebras.cloud.sdk import Cerebras
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

from app.models.menu import Menu
from app.models.order import OrderItem

load_dotenv()
logger = logging.getLogger(__name__)


class LLMOrderIntent(BaseModel):
    ordered_items: List[OrderItem] = Field(
        default_factory=list,
        description="List of items the user wants to order. Use exact menu names.",
    )
    end_order: bool = Field(
        default=False,
        description="True if the user explicitly finishes the order (e.g., 'that is all', 'done'). False if they reject an offer but continue.",
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
    def __init__(self, model_name: str = "gpt-oss-120b"):
        api_key = os.getenv("CEREBRAS_API_KEY")
        if not api_key:
            raise RuntimeError(
                "CEREBRAS_API_KEY is not set. Please export it or provide via .env."
            )
        self.client = Cerebras(api_key=api_key)
        self.model_name = model_name

    def _build_system_instruction(self, menu: Menu, prior_summary: str) -> str:

        menu_json = json.dumps(menu.as_prompt_payload(), indent=2)
        instructions = (
            "You are an ordering intent extractor for a McDonald's text chat. "
            "Analyze the user's message and extract the ordering intent according to the provided schema.\n"
            "RULES:\n"
            "- Use ONLY item names from the provided menu data.\n"
            "- For generic requests like 'burger' or 'drink', keep the generic name so the system can ask for clarification.\n"
            "- For double deals, create a 'double_deal' item with components 'item1' and 'item2'.\n"
            "- If the user specifies modifications (e.g. 'no pickles'), put them in 'remove_ingredients'.\n"
            "- Default quantity is 1."
        )
        return (
            f"{instructions}\n\n"
            f"Current order summary: {prior_summary or 'empty'}\n"
            f"Menu Data:\n{menu_json}"
        )

    def parse_intent(
        self,
        user_message: str,
        menu: Menu,
        prior_summary: str = "",
        last_system_message: str = "",
    ) -> LLMResult:
        system_content = self._build_system_instruction(menu, prior_summary)

        messages = [{"role": "system", "content": system_content}]
        if last_system_message:
            messages.append({"role": "assistant", "content": last_system_message})
        messages.append({"role": "user", "content": user_message})

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
        except Exception as exc:
            logger.error("Cerebras call failed: %s", exc)
            return LLMResult(intent=None, raw="", error=f"Cerebras call failed: {exc}")

        raw_text = response.choices[0].message.content or ""

        try:

            intent = LLMOrderIntent.model_validate_json(raw_text)
            return LLMResult(intent=intent, raw=raw_text)
        except ValidationError as exc:
            logger.error("Pydantic validation error: %s | raw: %s", exc, raw_text)
            return LLMResult(
                intent=None, raw=raw_text, error=f"Validation error: {exc}"
            )

    def generate_reply(
        self, user_message: str, menu: Menu, order_summary: str = ""
    ) -> str:

        system_prompt = (
            "You are a friendly McDonald's ordering assistant. Craft a concise, helpful reply. "
            "Do NOT claim to add/remove items; only ask clarifying questions or acknowledge.\n"
            f"Menu snapshot: {json.dumps(menu.as_prompt_payload())}\n"
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
                max_completion_tokens=500,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            logger.error("Cerebras generate_reply failed: %s", exc)
            return "I'm having trouble connecting to Cerebras right now."
