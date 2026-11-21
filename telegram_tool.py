import asyncio
from collections import deque
from datetime import datetime
import os
import httpx
from text_ui import c
import time

__all__ = ["send_telegram", "read_telegram", "start_telegram", "stop_telegram", "TELEGRAM_ACTIVE", "AGENT_LOCK"]

TELEGRAM_ACTIVE = False
AGENT_LOCK = asyncio.Lock()
_TASK: asyncio.Task | None = None
MAX_CHUNK = 4000
INBOX: deque[dict] = deque(maxlen=20)
MAX_AGE = 600

def read_telegram(limit: int = 5) -> str:
    n = max(1, min(int(limit or 5), 20))
    if not INBOX:
        return "No incoming Telegram messages received in this session."
    items = list(INBOX)[-n:]
    lines = [f"{i}. [{m['time']}] {m['text']}" for i, m in enumerate(items, 1)]
    return "Recent incoming Telegram messages:\n" + "\n".join(lines)


def _creds() -> tuple[str, str]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    return token, chat_id


def _chunks(text: str, size: int = MAX_CHUNK) -> list[str]:
    text = (text or "").strip() or "(empty)"
    return [text[i : i + size] for i in range(0, len(text), size)]


async def send_telegram(text: str) -> str:
    token, chat_id = _creds()
    if not token or not chat_id:
        return "error: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing in .env"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            for part in _chunks(text):
                r = await client.post(url, json={"chat_id": chat_id, "text": part})
                if r.status_code >= 400:
                    return f"error: Telegram HTTP {r.status_code}: {r.text[:250]}"
    except Exception as e:
        return f"error: Telegram send failed: {e}"
    return "sent: Telegram message delivered."


def tg_print(msg: str) -> None:
    print("\r" + " " * 100 + "\r" + msg)
    print(c("info", "you: "), end="", flush=True)

async def _handle_incoming(user_text: str, tg_messages: list[dict]) -> None:
    global TELEGRAM_ACTIVE
    from text_ui import SOURCE
    SOURCE.set("tg")
    from agent import run_agent

    if user_text.strip().lower() in ("/clear", "/reset"):
        del tg_messages[1:]
        await send_telegram("Telegram chat history cleared.")
        return

    async with AGENT_LOCK:
        TELEGRAM_ACTIVE = True
        try:
            tg_messages.append({
                "role": "user",
                "content": "[system: message came from Telegram. Your final reply is sent to Telegram "
                           "automatically. Do NOT call send_telegram for it.]\n" + user_text,
            })
            try:
                reply = await run_agent(tg_messages)
            except Exception as e:
                reply = f"error: {e}"
            tg_messages.append({"role": "assistant", "content": reply})
            # keep system prompt + last 40 msgs
            if len(tg_messages) > 41:
                del tg_messages[1:-40]
        finally:
            TELEGRAM_ACTIVE = False

    try:
        from recall_tool import log_turn
        log_turn("user", user_text)
        log_turn("assistant", reply)
    except Exception:
        pass

    res = await send_telegram(reply)
    if res.startswith("error:"):
        print(c("error", f"[telegram] {res}"))
    else:
        tg_print(c("info", f"[telegram] replied: {reply[:200]}"))


async def _poll_loop(system_prompt: str) -> None:
    token, allowed_chat = _creds()
    if not token or not allowed_chat:
        print(c("info", "[telegram] disabled (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)"))
        return

    base = f"https://api.telegram.org/bot{token}"
    tg_messages = [{"role": "system", "content": system_prompt}]
    offset = 0
    print(c("info", "[telegram] polling started"))

    async with httpx.AsyncClient(timeout=httpx.Timeout(35.0, connect=10.0)) as client:
        # Clear any stale webhook so getUpdates does not hit 409 Conflict
        try:
            await client.post(f"{base}/deleteWebhook", json={"drop_pending_updates": False})
        except Exception:
            pass

        while True:
            try:
                r = await client.post(
                    f"{base}/getUpdates",
                    json={"offset": offset, "timeout": 25, "allowed_updates": ["message"]},
                )
                if r.status_code == 409:
                    print(c("error", "[telegram] 409 Conflict: another bot poller or webhook is active"))
                    await asyncio.sleep(10)
                    continue
                if r.status_code >= 400:
                    await asyncio.sleep(5)
                    continue

                data = r.json()
                for upd in data.get("result", []):
                    offset = max(offset, upd["update_id"] + 1)
                    msg = upd.get("message") or {}
                    chat_id = str((msg.get("chat") or {}).get("id", ""))
                    text = (msg.get("text") or "").strip()
                    if not text or chat_id != allowed_chat:
                        continue
                    if time.time() - msg.get("date", 0) > MAX_AGE:
                        await send_telegram(f"Skipped old message (bot was offline): {text[:80]}")
                        continue
                    INBOX.append({"time": datetime.now().strftime("%H:%M:%S"), "text": text})
                    tg_print(c("info", f"[telegram] incoming: {text[:80]}"))
                    await _handle_incoming(text, tg_messages)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(c("error", f"[telegram] poll error: {e}"))
                await asyncio.sleep(5)


def start_telegram(system_prompt: str) -> None:
    global _TASK
    if _TASK is None or _TASK.done():
        _TASK = asyncio.create_task(_poll_loop(system_prompt))


async def stop_telegram() -> None:
    global _TASK
    if _TASK and not _TASK.done():
        _TASK.cancel()
        try:
            await _TASK
        except asyncio.CancelledError:
            pass
    _TASK = None