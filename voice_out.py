import hashlib, io, os, re, sys, queue, threading, time
from pathlib import Path
import requests, sounddevice as sd, soundfile as sf
from dotenv import load_dotenv

load_dotenv()

TTS_URL = os.environ.get("TTS_URL", "").rstrip("/")
TTS_KEY = os.environ.get("TTS_KEY", "")
VOICE = os.environ.get("TTS_VOICE", "me")
LANG = os.environ.get("TTS_LANG", "en")
TTS_REF = os.environ.get("TTS_REF", "")                       # path to your reference clip
MAX_CHARS = int(os.environ.get("TTS_MAX_CHARS", "600"))       # speak at most this much per turn
HDR = {"Authorization": f"Bearer {TTS_KEY}"} if TTS_KEY else {}
CACHE_DIR = Path(__file__).parent / "voice_cache"
CACHE_DIR.mkdir(exist_ok=True)

S = requests.Session()                                        # keep-alive: no new TLS handshake per sentence
_text_q, _aud_q = queue.Queue(), queue.Queue()
_gen = 0                                                      # bump to cancel everything queued
_lock = threading.Lock()


def _clean(text):
    text = re.sub(r"<think>.*?</think>", " ", text, flags=re.S)
    text = re.sub(r"```.*?```", " ", text, flags=re.S)        # skip code blocks
    text = re.sub(r"https?://\S+", "link", text)
    text = re.sub(r"[*_#`>|]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _synth(text, cache=False):
    path = None
    if cache:
        key = hashlib.sha1(f"{VOICE}|{LANG}|{text}".encode()).hexdigest()[:16]
        path = CACHE_DIR / f"{key}.wav"
        if path.is_file():
            return sf.read(path)
    t = time.time()
    try:
        r = S.post(f"{TTS_URL}/v1/audio/speech", headers=HDR, timeout=180, json={
            "input": text, "voice": VOICE, "response_format": "wav",
            "extra_params": {"lang": LANG}})
        if r.status_code != 200:
            print(f" [tts] {r.status_code} {r.text[:150]}")
            return None
        print(f" [tts] {time.time() - t:.1f}s for {len(text)} chars")
        if path:
            path.write_bytes(r.content)
        return sf.read(io.BytesIO(r.content))
    except Exception as e:
        print(f" [tts] {type(e).__name__}: {e}")
        return None


def _synth_worker():
    while True:
        gen, text, cache = _text_q.get()
        if gen != _gen:
            continue
        a = _synth(text, cache)
        if a is not None:
            _aud_q.put((gen, a))


def _play_worker():
    while True:
        gen, (data, sr) = _aud_q.get()
        if gen != _gen:
            continue
        sd.play(data, sr)
        sd.wait()


if TTS_URL:
    threading.Thread(target=_synth_worker, daemon=True).start()
    threading.Thread(target=_play_worker, daemon=True).start()


def _enqueue(text, cache=False):
    text = _clean(text)
    if TTS_URL and text:
        _text_q.put((_gen, text, cache))


def speak(text, cache=False):
    """one short phrase, no splitting. cache=True for fixed lines."""
    _enqueue(text, cache)


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
    try:
        sd.stop()
    except Exception:
        pass


# ---------- voice cloning: upload + auto re-upload ----------
def upload_voice(path: str) -> bool:
    if not os.path.isfile(path):
        print(f" [voice] file not found: {path}")
        return False
    with open(path, "rb") as f:
        r = S.post(f"{TTS_URL}/v1/audio/voices", headers=HDR, timeout=120,
                   files={"audio_sample": f},
                   data={"name": VOICE, "consent": "my-own-voice", "speaker_description": "ultron"})
    print(f" [voice] upload {r.status_code} {r.text[:200]}")
    return r.status_code == 200


def ensure_voice() -> bool:
    """Colab restarts wipe voices. call at startup: re-uploads TTS_REF if voice is missing."""
    if not TTS_URL:
        return False
    try:
        r = S.get(f"{TTS_URL}/v1/audio/voices", headers=HDR, timeout=30)
        have = r.json().get("voices", []) if r.ok else []
    except Exception as e:
        print(f" [voice] TTS server unreachable: {type(e).__name__}")
        return False
    if VOICE in have:
        return True
    if TTS_REF and os.path.isfile(TTS_REF):
        return upload_voice(TTS_REF)
    print(f" [voice] '{VOICE}' not on server. Set TTS_REF in .env or run: uv run voice_out.py upload clip.mp3")
    return False


def prewarm(phrases):
    """synthesize fixed narration lines once. cached on disk, instant afterwards."""
    def run():
        for p in phrases:
            _synth(p, cache=True)
    threading.Thread(target=run, daemon=True).start()


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "upload":
        upload_voice(a[1])
    elif len(a) >= 2 and a[0] == "say":
        t = time.time()
        audio = _synth(" ".join(a[1:]))
        print(f"total {time.time() - t:.1f}s")
        if audio:
            sd.play(*audio); sd.wait()
    else:
        print("usage: uv run voice_out.py upload clip.mp3 | say \"hello there\"")