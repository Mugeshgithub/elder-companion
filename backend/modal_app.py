"""Hosts the FastAPI server on Modal at a stable URL, replacing the cloudflared tunnel.

Deploy:  .venv/bin/modal deploy backend/modal_app.py
Secrets: a Modal secret named `elder-companion` holding the .env values (see README).

One container stays alive on purpose. The silence trigger is a Valkey subscription that runs
inside the server, so a second copy would raise every inactivity alert twice and scaling to
zero would stop it listening.
"""
import modal

APP_DIR = "/root/app"

image = (
    modal.Image.debian_slim(python_version="3.13")
    .pip_install(
        "fastapi==0.158.1",
        "uvicorn==0.54.0",
        "anthropic==2.0.0",
        "httpx==0.28.1",
        "psycopg[binary]==3.3.6",
        "pgvector==0.5.1",
        "redis==8.1.0",
        "pydantic==2.14.1",
        "python-dotenv==1.2.4",
    )
    .env({"PYTHONPATH": APP_DIR})
    .add_local_dir(
        ".",
        remote_path=APP_DIR,
        ignore=["__pycache__", "*.pyc", "modal_app.py", "create_agent.py"],
    )
)

app = modal.App("elder-companion", image=image)


@app.function(
    secrets=[modal.Secret.from_name("elder-companion")],
    min_containers=1,  # keep the Valkey silence listener alive
    max_containers=1,  # and never run two listeners
    timeout=3600,
)
@modal.concurrent(max_inputs=50)
@modal.asgi_app()
def web():
    from main import app as fastapi_app

    return fastapi_app
