import os

import httpx

import config  # noqa: F401  (loads .env)

OPENAI_URL = "https://api.openai.com/v1/embeddings"
MODEL = "text-embedding-3-small"
DIMENSIONS = 1024  # matches memories.embedding


async def embed(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            OPENAI_URL,
            headers={"Authorization": f"Bearer {os.environ['EMBEDDINGS_API_KEY']}"},
            json={"input": text, "model": MODEL, "dimensions": DIMENSIONS},
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]
