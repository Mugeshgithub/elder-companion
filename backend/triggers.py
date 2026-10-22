"""Proactive triggers: Valkey key-expiry events fire when a patient has been silent too long."""
import asyncio
import logging
import re

import redis.asyncio as redis

from config import VALKEY_URI

log = logging.getLogger("triggers")

EXPIRED_CHANNEL = "__keyevent@0__:expired"
ALIVE_KEY = re.compile(r"^patient:(\d+):alive$")


async def listen_for_inactivity(on_inactive):
    """Calls `await on_inactive(patient_id)` whenever a patient's `alive` key expires.
    Reconnects if the connection drops, so the silence trigger never dies quietly."""
    while True:
        r = redis.from_url(VALKEY_URI, decode_responses=True, health_check_interval=20)
        try:
            pubsub = r.pubsub()
            await pubsub.subscribe(EXPIRED_CHANNEL)
            async for msg in pubsub.listen():
                if msg["type"] != "message":
                    continue
                m = ALIVE_KEY.match(msg["data"])
                if m:
                    try:
                        await on_inactive(int(m.group(1)))
                    except Exception:
                        log.exception("inactivity handler failed")
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("silence-trigger connection lost, reconnecting in 2s", exc_info=True)
            await asyncio.sleep(2)
        finally:
            try:
                await r.aclose()
            except Exception:
                pass
