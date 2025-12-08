import json
import os
import logging
from typing import Optional
from dataclasses import dataclass
from pydantic import BaseModel, Field, ValidationError
from cerebras.cloud.sdk import Cerebras

from app.schemas import Menu, OrderItem, LLMOrderIntent, LLMResult
from app.config import settings

logger = logging.getLogger(__name__)


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

    def parse_intent(
        self, user_message: str, menu: Menu, prior_summary: str = ""
    ) -> LLMResult:
        if not self.client:
            return LLMResult(
                intent=None,
                raw="",
                error="LLM Client not initialized (missing API key?)",
            )

        menu_json = str(menu)

        system_content = (
            "You are an ordering intent extractor for a McDonald's text chat. "
            "Analyze the user's message and extract the ordering intent according to the provided schema.\n"
            "RULES:\n"
            "- Use ONLY item names from the provided menu data.\n"
            "- Map user synonyms to the exact menu item name (e.g. if user says 'Coke' or 'Cola', use 'Coca-Cola').\n"
            "- For generic requests like 'burger' or 'drink', use the generic name (e.g. 'burger') so the system can ask for clarification.\n"
            "- If the user indicates they want to cancel the current pending item (e.g. 'no', 'cancel', 'changed mind', 'forget it'), set 'cancel_pending' to true.\n"
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
        self, user_message: str, menu: Menu, order_summary: str = "", has_upsell: bool = False
    ) -> str:
        if not self.client:
            return "Sorry, the LLM service is currently unavailable."

        menu_dump = str(menu)

        system_prompt = (
            "You are a friendly McDonald's ordering assistant. "
            "Keep replies concise and natural. "
            "Do NOT claim to add/remove items yourself in this text reply; ask clarifying questions.\n"
            f"Menu context: {menu_dump}\n"
            f"Current order: {order_summary or 'empty'}\n"
        )

        if has_upsell:
            system_prompt += (
                "NOTE: Do NOT ask 'anything else?', 'what else?', or 'is that all?' at the end. "
                "The system will append a specific question immediately after your response."
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
