import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

VALKEY_URI = os.environ["VALKEY_URI"]
POSTGRES_URI = os.environ["POSTGRES_URI"]
INACTIVITY_SECONDS = int(os.getenv("INACTIVITY_SECONDS", 4 * 3600))
AGENT_SHARED_SECRET = os.environ["AGENT_SHARED_SECRET"]
PATIENT_TZ = os.getenv("PATIENT_TZ", "Europe/Paris")
