"""Hosts the FastAPI server on Modal at a stable URL, replacing the cloudflared tunnel.

Deploy:  .venv/bin/modal deploy backend/modal_app.py
Secrets: a Modal secret named `elder-companion` holding the .env values (see README).

One container stays alive on purpose. The silence trigger is a Valkey subscription that runs
inside the server, so a second copy would raise every inactivity alert twice and scaling to
zero would stop it listening.
"""
from pathlib import Path

import modal

APP_DIR = "/root/app"
BACKEND_DIR = Path(__file__).resolve().parent  # not "." so the folder never depends on where the command is run

image = (
    modal.Image.debian_slim(python_version="3.13")
    .pip_install(
        "fastapi==0.158.1",
        "uvicorn==0.54.0",
        "anthropic==2.0.0",
        "httpx==0.28.1",
        "psycopg[binary,pool]==3.3.6",
        "pgvector==0.5.1",
        "redis==8.1.0",
        "pydantic==2.14.1",
        "python-dotenv==1.2.4",
        "pypdf==6.21.2",
    )
    .env({"PYTHONPATH": APP_DIR})
    .add_local_dir(
        BACKEND_DIR,
        remote_path=APP_DIR,
        ignore=["__pycache__", "*.pyc", "modal_app.py", "create_agent.py", ".env*"],
    )
)

app = modal.App("elder-companion", image=image)


@app.function(
    secrets=[modal.Secret.from_name("elder-companion")],
    cpu=2.0,  # the default is a fraction of a core, which queued requests for seconds under the live demo's polling
    memory=1024,
    region="eu",  # next to the Aiven databases in Frankfurt: every query is a short hop instead of an ocean
    min_containers=1,  # keep the Valkey silence listener alive
    max_containers=1,  # and never run two listeners
    timeout=3600,
)
@modal.concurrent(max_inputs=50)
@modal.asgi_app()
def web():
    from main import app as fastapi_app

    return fastapi_app
