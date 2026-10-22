"""Reply generation: Claude first, OpenAI as fallback if the Anthropic call fails."""
import logging
import os

import anthropic
import httpx

import config  # noqa: F401  (loads .env)

log = logging.getLogger("llm")

CLAUDE_MODEL = "claude-haiku-5-5"  # fast: this sits on the voice path
OPENAI_MODEL = "gpt-4o-mini"
claude = anthropic.AsyncAnthropic()


async def _openai(system: str, messages: list[dict], max_tokens: int) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['EMBEDDINGS_API_KEY']}"},
            json={
                "model": OPENAI_MODEL,
                "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}, *messages],
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


async def generate(system: str, messages: list[dict], max_tokens: int = 200) -> tuple[str, str]:
    """Returns (reply, model_used)."""
    try:
        resp = await claude.messages.create(
            model=CLAUDE_MODEL, max_tokens=max_tokens, system=system, messages=messages,
            thinking={"type": "disabled"},  # voice path: no hidden reasoning tokens, lower latency
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if not text:
            raise ValueError("Claude returned no text block")
        return text, CLAUDE_MODEL
    except (anthropic.APIError, ValueError) as e:
        log.warning("Claude failed (%s), falling back to OpenAI", type(e).__name__)
        return await _openai(system, messages, max_tokens), OPENAI_MODEL
