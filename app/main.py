from __future__ import annotations

import asyncio
import os

import httpx
import typer


cli = typer.Typer(help="McDonald's text ordering simulator (client/server).")


async def _run_client(server_url: str) -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        session_resp = await client.post(f"{server_url}/sessions")
        session_resp.raise_for_status()
        data = session_resp.json()
        session_id = data["session_id"]
        print(f"System: {data['message']}")

        while True:
            user_input = input("You: ").strip()
            if not user_input:
                continue
            try:
                resp = await client.post(
                    f"{server_url}/chat",
                    json={"session_id": session_id, "message": user_input},
                )
                resp.raise_for_status()
                payload = resp.json()
                prefix = "[LLM] " if payload.get("used_llm_fallback") else ""
                print(f"System: {prefix}{payload['message']}")
                if payload.get("order_complete"):
                    break
            except httpx.HTTPStatusError as exc:
                print(
                    f"System: request failed ({exc.response.status_code}): {exc.response.text}"
                )
            except Exception as exc:  # pragma: no cover - runtime IO
                print(f"System: request failed ({exc})")
                break


@cli.command()
def chat(
    server: str = typer.Option(
        "http://localhost:8000", "--server", "-s", help="Server base URL"
    )
) -> None:
    """
    Start the asynchronous CLI chat client.
    """
    asyncio.run(_run_client(server))


@cli.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port"),
) -> None:
    """
    Run the FastAPI server with uvicorn.
    """
    import uvicorn

    reload = os.getenv("RELOAD", "false").lower() == "true"
    uvicorn.run("app.server:app", host=host, port=port, reload=reload)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
