import asyncio
import os
import uuid
from typing import Dict

import httpx
import typer
import uvicorn
from fastapi import FastAPI, HTTPException

from app.schemas import ChatRequest, ChatReply, SessionState
from app.services.menu_service import MenuService
from app.services.cart_service import CartService
from app.services.chat_service import ChatService
from app.services.llm_service import LLMService

app = FastAPI(title="McDonald's Ordering Simulator")

menu_service = MenuService()

llm_service = LLMService()
cart_service = CartService(menu_service)
chat_service = ChatService(menu_service, llm_service, cart_service)

sessions: Dict[str, SessionState] = {}


@app.post("/sessions")
async def create_session():
    sid = uuid.uuid4().hex
    sessions[sid] = SessionState()
    return {
        "session_id": sid,
        "message": "Welcome to McDonald's! What would you like to order?",
    }


@app.post("/chat", response_model=ChatReply)
async def chat_endpoint(req: ChatRequest):
    if req.session_id not in sessions:
        raise HTTPException(404, "Session not found")

    state = sessions[req.session_id]

    response_text = chat_service.process_message(state, req.message)

    summary = [str(i) for i in state.order.items]
    total = cart_service.calculate_total(state.order)

    return ChatReply(
        message=response_text,
        order_complete="Order completed" in response_text,
        used_llm_fallback=False,
        order_summary=summary,
        total=total,
    )


cli = typer.Typer(help="McDonald's text ordering simulator (client/server).")


async def _run_client(server_url: str) -> None:
    """Client part"""
    print(f"Connecting to {server_url}...")
    try:
        async with httpx.AsyncClient(timeout=30) as client:

            session_resp = await client.post(f"{server_url}/sessions")
            session_resp.raise_for_status()
            data = session_resp.json()
            session_id = data["session_id"]
            print(f"System: {data.get('message', 'Connected')}")

            while True:
                user_input = input("You: ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ["quit", "exit"]:
                    break

                resp = await client.post(
                    f"{server_url}/chat",
                    json={"session_id": session_id, "message": user_input},
                )
                resp.raise_for_status()
                payload = resp.json()

                print(f"System: {payload['message']}")
                if payload.get("order_complete"):
                    break
    except httpx.ConnectError:
        print(
            "Error: Could not connect to server. Is it running? (Try 'mcd-cli serve')"
        )
    except Exception as exc:
        print(f"Error: {exc}")


@cli.command()
def chat(
    server: str = typer.Option(
        "http://localhost:8000", "--server", "-s", help="Server base URL"
    )
) -> None:
    """Start the chat client."""
    asyncio.run(_run_client(server))


@cli.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
) -> None:
    """Run the FastAPI server."""

    uvicorn.run("app.main:app", host=host, port=port, reload=reload)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
