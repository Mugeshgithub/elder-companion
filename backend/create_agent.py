"""Creates the ElevenLabs voice agent that uses our /v1/chat/completions as its brain.
Usage: python create_agent.py https://<public-url>
"""
import os
import sys

import httpx

import config  # noqa: F401

base = sys.argv[1].rstrip("/")
payload = {
    "name": "Elder Companion (Mugesh)",
    "conversation_config": {
        "agent": {
            "first_message": "Hi Mugesh, it's good to hear from you. How are you feeling today?",
            "language": "en",
            "prompt": {
                "llm": "custom-llm",
                "prompt": "You are a caring voice companion. Replies come from the custom LLM.",
                "custom_llm": {"url": base + "/v1", "model_id": "caregiver", "request_headers": {"x-patient-id": "1", "x-api-key": os.environ["AGENT_SHARED_SECRET"]}},
            },
        },
    },
}
r = httpx.post("https://api.elevenlabs.io/v1/convai/agents/create",
               headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}, json=payload, timeout=30)
print(r.status_code, r.text[:500])
