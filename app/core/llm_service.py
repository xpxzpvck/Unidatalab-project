from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import List, Optional

from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, Field, ValidationError

from app.models.menu import Menu
from app.models.order import OrderItem


load_dotenv()
logger = logging.getLogger(__name__)


class LLMOrderIntent(BaseModel):
    ordered_items: List[OrderItem] = Field(default_factory=list)
    end_order: bool = False


@dataclass
class LLMResult:
    intent: Optional[LLMOrderIntent]
    raw: str
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and self.intent is not None


class LLMService:
    def __init__(self, model_name: str = "gemini-2.5-flash"):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY is not set. Please export it or provide via .env."
            )
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name
        self.response_model = model_name

    def _build_system_instruction(self, menu: Menu, prior_summary: str) -> str:
        menu_json = json.dumps(menu.as_prompt_payload(), indent=2)
        instructions = (
            "You are an ordering intent extractor for a McDonald's text chat. "
            "Read the latest user message and emit strictly JSON (no markdown) "
            "that matches this shape:\n"
            "{\n"
            '  "ordered_items": [\n'
            "    {\n"
            '      "name": "Big Mac Meal",\n'
            '      "kind": "combo | item | double_deal",\n'
            '      "quantity": 1,\n'
            '      "properties": {"size": "medium"},\n'
            '      "components": [\n'
            '         {"slot": "drink", "name": "Coca-Cola", "properties": {"size": "medium"}},\n'
            '         {"slot": "fries", "name": "French Fries", "properties": {"size": "medium"}}\n'
            "      ],\n"
            '      "add_ingredients": ["Bacon"],\n'
            '      "remove_ingredients": ["Onion"]\n'
            "    }\n"
            "  ],\n"
            '  "end_order": false\n'
            "}\n"
            "- Use only item names from the provided menu JSON.\n"
            "- Preserve user virtual requests like 'burger', 'drink', 'dessert', 'combo', or 'ice cream' as the name "
            "if they were not clarified.\n"
            "- For double deals, include kind='double_deal' and put the two burgers inside components with slot names "
            "like 'item1' and 'item2'.\n"
            "- If the user signals the order is finished (e.g., 'that is all', 'done', 'no thanks' to 'anything else?'), set end_order=true.\n"
            "- If the user rejects an upsell or specific offer (e.g., 'no' to 'want a combo?'), set end_order=false.\n"
            "- Default quantity is 1. Do not return any text outside of the JSON object."
        )
        return (
            f"{instructions}\n\n"
            f"Current order summary: {prior_summary or 'empty'}\n"
            f"Menu data:\n{menu_json}\n"
            "Return only the JSON."
        )

    def _extract_json(self, text: str) -> str:
        # Strip code block markdown if present
        text = re.sub(r"^```json", "", text, flags=re.MULTILINE)
        text = re.sub(r"^```", "", text, flags=re.MULTILINE)
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            return match.group(0)
        return text

    def _response_text(self, response) -> str:
        raw_text = getattr(response, "text", "") or ""
        if raw_text:
            return raw_text
        parts: List[str] = []
        for candidate in getattr(response, "candidates", []) or []:
            content = getattr(candidate, "content", None)
            if content and getattr(content, "parts", None):
                for part in content.parts:
                    if hasattr(part, "text"):
                        parts.append(part.text)
        return "\n".join(parts)

    def parse_intent(
        self,
        user_message: str,
        menu: Menu,
        prior_summary: str = "",
        last_system_message: str = "",
    ) -> LLMResult:
        prompt = (
            f"{self._build_system_instruction(menu, prior_summary)}\n\n"
            f"Previous system message: {last_system_message or 'none'}\n"
            f"User: {user_message}"
        )
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
            )
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            return LLMResult(intent=None, raw="", error=f"LLM call failed: {exc}")

        raw_text = self._response_text(response)
        try:
            json_payload = self._extract_json(raw_text)
            parsed_dict, _ = json.JSONDecoder().raw_decode(json_payload)
            intent = LLMOrderIntent(**parsed_dict)
            return LLMResult(intent=intent, raw=raw_text)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.error("LLM parse error: %s | raw: %s", exc, raw_text)
            return LLMResult(intent=None, raw=raw_text, error=f"Parse error: {exc}")

    def generate_reply(
        self, user_message: str, menu: Menu, order_summary: str = ""
    ) -> str:
        prompt = (
            "You are a friendly McDonald's ordering assistant. Craft a concise, helpful reply "
            "for the user message below. Do NOT claim to add/remove items or change the order; "
            "only ask clarifying questions or acknowledge. Stay on the menu and avoid unavailable items.\n"
            "If the user declines an offer or seems finished with a thought, ask if they want anything else.\n"
            f"Menu snapshot: {json.dumps(menu.as_prompt_payload())}\n"
            f"Current order: {order_summary or 'empty'}\n"
            f"User: {user_message}\n"
            "Respond in one or two sentences."
        )
        response = self.client.models.generate_content(
            model=self.response_model,
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
        )
        return self._response_text(response).strip()
