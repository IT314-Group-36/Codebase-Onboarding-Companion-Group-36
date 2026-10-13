"""Client for the AI API team's engine.

Contract (agree on this with the AI team):
  POST {AI_API_URL}
  Headers: Authorization: Bearer <AI_API_KEY>   (optional)
  Body:    {"task": "explain_file" | "answer_question", "input": {...}}
  Reply:   {"output": "<plain-english text>", "provider": "<optional label>"}

If AI_API_URL is not set, or the call fails, methods return None and the caller
falls back to its built-in heuristic answer, so the backend always works.
"""
import logging

import httpx

from ..config import settings

log = logging.getLogger("ai_client")


class AIClient:
    @property
    def enabled(self) -> bool:
        return bool(settings.ai_api_url)

    def _call(self, task: str, payload: dict) -> tuple[str, str] | None:
        if not self.enabled:
            return None
        headers = {"Authorization": f"Bearer {settings.ai_api_key}"} if settings.ai_api_key else {}
        try:
            r = httpx.post(settings.ai_api_url, json={"task": task, "input": payload},
                           headers=headers, timeout=settings.ai_timeout)
            r.raise_for_status()
            body = r.json()
            out = body.get("output")
            return (out, body.get("provider") or "ai-engine") if out else None
        except Exception as exc:  # network, timeout, bad JSON...
            log.warning("AI API call failed (%s): %s", task, exc)
            return None

    def explain_file(self, path: str, language: str, code: str, symbols: list[dict]) -> tuple[str, str] | None:
        return self._call("explain_file", {"path": path, "language": language,
                                           "code": code[:8000], "symbols": symbols})

    def answer_question(self, question: str, contexts: list[dict]) -> tuple[str, str] | None:
        return self._call("answer_question", {"question": question, "contexts": contexts})


ai_client = AIClient()
