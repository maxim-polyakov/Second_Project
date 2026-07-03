from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.agent import ask_agent

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(
    title="Smart Subscription Registry",
    description="Backend core and ReAct AI agent for personal subscriptions.",
    version="0.1.0",
)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, description="Natural-language user question.")


@app.get("/")
def root() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask")
def ask(request: AskRequest) -> dict:
    try:
        return ask_agent(request.question)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
