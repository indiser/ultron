import os, re, sys, queue, threading, time
from pathlib import Path

import numpy as np
import sounddevice as sd
import torch
from dotenv import load_dotenv
from pocket_tts import TTSModel

load_dotenv()

STATE_PATH = os.environ.get("TTS_STATE", str(Path(__file__).parent / "first_voice.safetensors"))
MAX_CHARS = int(os.environ.get("TTS_MAX_CHARS", "600"))

torch.set_num_threads(1)  # 1 thread was fastest in your benchmark

print(" [tts] loading model...")
_model = TTSModel.load_model()
_state = _model.get_state_for_audio_prompt(STATE_PATH)
_model.generate_audio(_state, "Warmup.")  # first call slow
SR = _model.sample_rate
print(" [tts] ready")

_text_q, _aud_q = queue.Queue(), queue.Queue()
_gen = 0  # bump to cancel everything queued
_lock = threading.Lock()


def _clean(text):
    text = re.sub(r"<think>.*?</think>", " ", text, flags=re.S)
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"https?://\S+", "link", text)
    text = re.sub(r"[*_#`>|]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _synth_worker():
    while True:
        gen, text = _text_q.get()
        if gen != _gen:
            continue
        t = time.time()
        first = True
        try:
            for chunk in _model.generate_audio_stream(_state, text):
                if gen != _gen:
                    break  # cancelled mid sentence
                if first:
                    first = False
                arr = np.asarray(chunk.numpy(), dtype=np.float32).reshape(-1)
                _aud_q.put((gen, arr))
        except Exception as e:
            print(f" [tts] {type(e).__name__}: {e}")
        finally:
            _text_q.task_done()


def _play_worker():
    seen = _gen
    with sd.OutputStream(samplerate=SR, channels=1, dtype="float32") as out:
        while True:
            gen, arr = _aud_q.get()
            if gen != _gen:
                continue
            if gen != seen:  # new turn: drop old buffered audio
                out.abort()
                out.start()
                seen = gen
            out.write(arr.reshape(-1, 1))


threading.Thread(target=_synth_worker, daemon=True).start()
threading.Thread(target=_play_worker, daemon=True).start()


def _enqueue(text):
    text = _clean(text)
    if text:
        _text_q.put((_gen, text))


def speak(text, cache=False):
    """one short phrase, no splitting. cache arg kept for compat, ignored."""
    _enqueue(text)


class Stream:
    """feed LLM text deltas. speaks each sentence the moment it completes.
    first chunk may flush early at a comma so audio starts sooner."""

    def __init__(self):
        self.buf, self.first, self.spoken = "", True, 0

    def feed(self, delta: str) -> None:
        self.buf += delta
        while (chunk := self._pop()) is not None:
            self._say(chunk)

    def flush(self) -> None:
        rest, self.buf = self.buf.strip(), ""
        if rest:
            self._say(rest)

    def _pop(self):
        m = re.search(r"[.!?]+(?=\s)|\n", self.buf)
        if m:
            end = m.end()
        else:
            m = re.search(r"[,;:](?=\s)", self.buf) if self.first else None
            if m and m.end() >= 35:
                end = m.end()
            elif len(self.buf) > 220 and self.buf.rfind(", ", 60, 200) != -1:
                end = self.buf.rfind(", ", 60, 200) + 1
            else:
                return None
        chunk, self.buf = self.buf[:end], self.buf[end:]
        return chunk if chunk.strip() else self._pop()

    def _say(self, chunk: str) -> None:
        chunk = chunk.strip()
        if not chunk or self.spoken + len(chunk) > MAX_CHARS:
            return
        self.spoken += len(chunk)
        self.first = False
        _enqueue(chunk)


def stop():
    """cancel queued + current speech. call when user starts new turn."""
    global _gen
    with _lock:
        _gen += 1
    for q in (_text_q, _aud_q):
        while True:
            try:
                q.get_nowait()
                if q is _text_q:
                    _text_q.task_done()
            except queue.Empty:
                break


def ensure_voice() -> bool:
    ok = os.path.isfile(STATE_PATH)
    if not ok:
        print(f" [voice] missing: {STATE_PATH}")
    return ok


def prewarm(phrases):
    pass  # local model, no need


if __name__ == "__main__":
    text = " ".join(sys.argv[1:]) or "Hello, I am online."
    _enqueue(text)
    time.sleep(0.5)
    _text_q.join() if False else None
    while not _text_q.empty() or not _aud_q.empty():
        time.sleep(0.2)
    time.sleep(2)