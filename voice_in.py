"""Local mic -> Colab faster-whisper websocket.

pip install websockets sounddevice numpy
.env:  STT_WS_URL=wss://xxxx.trycloudflare.com/ws   STT_TOKEN=...
"""
from __future__ import annotations

import asyncio
import json
import os

import numpy as np
import sounddevice as sd
import websockets

from dotenv import load_dotenv

load_dotenv()

SR = 16000
BLOCK = 1600  # 100 ms per frame


class STT:
    def __init__(self, url: str | None = None, token: str | None = None):
        self.url = url or os.environ.get("STT_WS_URL")
        self.token = os.environ.get("STT_TOKEN", "") if token is None else token
        self.ws = None
        self.mute = False  # set True while TTS plays so Ultron does not hear itself
        m = os.environ.get("STT_MIC", "")
        self.device = int(m) if m.isdigit() else (m or None)

    async def connect(self):
        sep = "&" if "?" in self.url else "?"
        self.ws = await websockets.connect(
            f"{self.url}{sep}token={self.token}", max_size=None, ping_interval=20, ping_timeout=20)

    async def listen(self, on_partial=None, on_level=None, on_speech=None,
                     stop: asyncio.Event | None = None, max_s: float = 30) -> str:
        """Stream mic until server returns a non-empty final. stop.set() forces end (push-to-talk)."""
        for attempt in (0, 1):
            try:
                if self.ws is None:
                    await self.connect()
                return await self._listen(on_partial, on_level, on_speech, stop, max_s)
            except websockets.ConnectionClosed:
                self.ws = None
                if attempt:
                    raise
        return ""

    async def _listen(self, on_partial, on_level, on_speech, stop, max_s) -> str:
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()
        done = asyncio.Event()

        def cb(indata, frames, t, status):
            loop.call_soon_threadsafe(q.put_nowait, bytes(indata))

        await self.ws.send(json.dumps({"type": "reset"}))

        async def sender():
            while not done.is_set():
                raw = await q.get()
                if on_level:
                    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                    on_level(float(min(1.0, np.sqrt(np.mean(x * x)) * 8)))
                await self.ws.send(bytes(len(raw)) if self.mute else raw)

        async def ender():
            try:
                if stop is not None:
                    await asyncio.wait_for(stop.wait(), max_s)
                else:
                    await asyncio.sleep(max_s)
            except asyncio.TimeoutError:
                pass
            await self.ws.send(json.dumps({"type": "end"}))
            stop_flag["forced"] = True

        stop_flag = {"forced": False}

        async def receiver() -> str:
            while True:
                d = json.loads(await self.ws.recv())
                t = d.get("type")
                if t == "partial" and on_partial:
                    on_partial(d["text"])
                elif t == "vad" and on_speech:
                    on_speech(d["speaking"])
                elif t == "final":
                    if d["text"] or stop_flag["forced"]:
                        return d["text"]

        with sd.RawInputStream(samplerate=SR, channels=1, dtype="int16", blocksize=1600, device=self.device, callback=cb):
            tasks = [asyncio.create_task(c) for c in (sender(), ender(), receiver())]
            try:
                await asyncio.wait({tasks[2]}, return_when=asyncio.FIRST_COMPLETED)
                return tasks[2].result()
            finally:
                done.set()
                for t in tasks:
                    t.cancel()

    async def close(self):
        if self.ws:
            await self.ws.close()
            self.ws = None


async def _demo():
    stt = STT()
    print("speak. partials show live. Ctrl+C quits.")
    print("mic:", sd.query_devices(stt.device, "input")["name"])
    while True:
        text = await stt.listen(
            on_partial=lambda t: print("\r  ..", t, end="", flush=True),
            on_speech=lambda s: None)
        print("\rYOU:", text, " " * 20)


if __name__ == "__main__":
    try:
        asyncio.run(_demo())
    except KeyboardInterrupt:
        pass