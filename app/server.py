from __future__ import annotations

import uuid
from typing import Dict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.core.llm_service import LLMService
from app.core.menu_loader import load_menu
from app.core.order_manager import ChatResponse, OrderManager, SessionState


class SessionResponse(BaseModel):
    session_id: str
    message: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatReply(BaseModel):
    message: str
    order_complete: bool
    used_llm_fallback: bool
    order_summary: list[str]
    total: float


app = FastAPI(title="McDonald's Ordering Simulator")

menu = load_menu()
_llm_service = None
_order_manager: OrderManager | None = None
sessions: Dict[str, SessionState] = {}


def get_manager() -> OrderManager:
    global _order_manager, _llm_service
    if _order_manager is None:
        try:
            _llm_service = LLMService()
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        _order_manager = OrderManager(menu, _llm_service)
    return _order_manager


@app.post("/sessions", response_model=SessionResponse)
async def create_session() -> SessionResponse:
    manager = get_manager()
    session_id = uuid.uuid4().hex
    sessions[session_id] = SessionState()
    greeting = manager.greeting()
    return SessionResponse(session_id=session_id, message=greeting)


@app.post("/chat", response_model=ChatReply)
async def chat(req: ChatRequest) -> ChatReply:
    manager = get_manager()
    state = sessions.get(req.session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    response: ChatResponse = manager.process_message(state, req.message)
    summary = state.order.summary_lines(menu)
    total = state.order.total(menu)
    return ChatReply(
        message=response.message,
        order_complete=response.order_complete,
        used_llm_fallback=response.used_llm_fallback,
        order_summary=summary,
        total=total,
    )
