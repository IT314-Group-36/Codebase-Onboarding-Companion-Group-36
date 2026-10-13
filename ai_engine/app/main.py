from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from . import engine
from .config import settings

app = FastAPI(
    title="Onboarding AI Engine",
    version="0.1.0",
    description=("Turns code context into plain-English explanations/answers.\n\n"
                 "Uses Google Gemini if `GEMINI_API_KEY` is set, otherwise offline heuristics."),
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def check_auth(authorization: str | None = Header(None)):
    if settings.engine_api_key and authorization != f"Bearer {settings.engine_api_key}":
        raise HTTPException(401, "Invalid or missing engine API key")


class GenerateRequest(BaseModel):
    task: str = Field(..., description="explain_file | answer_question",
                      examples=["explain_file"])
    input: dict = Field(..., description="Task-specific payload (see README)")


class GenerateResponse(BaseModel):
    output: str
    provider: str


@app.post("/v1/generate", response_model=GenerateResponse, dependencies=[Depends(check_auth)])
def generate(req: GenerateRequest):
    if req.task == "explain_file":
        out, provider = engine.explain_file(req.input)
    elif req.task == "answer_question":
        out, provider = engine.answer_question(req.input)
    else:
        raise HTTPException(400, f"Unknown task '{req.task}'. Use explain_file or answer_question.")
    return GenerateResponse(output=out, provider=provider)


@app.get("/health")
def health():
    return {"status": "ok", "provider": "gemini" if settings.gemini_api_key else "offline",
            "auth_required": bool(settings.engine_api_key)}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")
