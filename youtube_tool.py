import asyncio
import re
from urllib.parse import parse_qs, urlparse
from config import safe_path

__all__ = ["youtube_transcript", "find_yt_link"]

YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
YT_URL_RE = re.compile(
    r"https?://(?:www\.|m\.|music\.)?(?:youtube\.com/(?:watch\?[^\s]+|shorts/[A-Za-z0-9_-]{11}|live/[A-Za-z0-9_-]{11}|embed/[A-Za-z0-9_-]{11})|youtu\.be/[A-Za-z0-9_-]{11}[^\s]*)",
    re.I,
)
PREVIEW_CHARS = 1800


def find_yt_link(text: str) -> str | None:
    m = YT_URL_RE.search(text or "")
    return m.group(0).rstrip(".,)>]\"'") if m else None


def _extract_video_id(url_or_id: str) -> str | None:
    s = (url_or_id or "").strip().strip("<>\"'")
    if YT_ID_RE.match(s):
        return s
    if "youtu" in s and not s.startswith(("http://", "https://")):
        s = "https://" + s
    p = urlparse(s)
    host = (p.hostname or "").lower()
    parts = [x for x in p.path.split("/") if x]
    cand = None
    if host == "youtu.be" and parts:
        cand = parts[0]
    elif host.endswith("youtube.com"):
        if p.path == "/watch":
            cand = parse_qs(p.query).get("v", [None])[0]
        elif len(parts) >= 2 and parts[0] in ("shorts", "live", "embed", "v"):
            cand = parts[1]
    return cand if cand and YT_ID_RE.match(cand) else None


def _fetch_sync(video_id: str, languages: list[str]) -> str:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return "error: youtube-transcript-api not installed. Run: uv add youtube-transcript-api"

    try:
        api = YouTubeTranscriptApi()
        if hasattr(api, "fetch"):
            fetched = api.fetch(video_id, languages=languages)
            rows = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else list(fetched)
        else:
            rows = YouTubeTranscriptApi.get_transcript(video_id, languages=languages)
    except Exception as e:
        name = type(e).__name__
        if name in ("TranscriptsDisabled", "NoTranscriptFound"):
            return f"error: no transcript available for video {video_id}."
        if name == "VideoUnavailable":
            return f"error: video {video_id} is unavailable or private."
        if name in ("RequestBlocked", "IpBlocked") or "429" in str(e):
            return "error: YouTube blocked transcript request (rate limit or IP block). Do not retry immediately."
        return f"error: YouTube transcript failed: {name}: {e}"

    lines = []
    for r in rows:
        raw_text = r["text"] if isinstance(r, dict) else getattr(r, "text", "")
        raw_start = r["start"] if isinstance(r, dict) else getattr(r, "start", 0.0)
        text = str(raw_text).replace("\n", " ").strip()
        if not text:
            continue
        mins, secs = divmod(int(float(raw_start)), 60)
        hrs, mins = divmod(mins, 60)
        ts = f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs else f"{mins:02d}:{secs:02d}"
        lines.append(f"[{ts}] {text}")
    return "\n".join(lines)


async def youtube_transcript(url: str, lang: str = "en") -> str:
    vid = _extract_video_id(url)
    if not vid:
        return "error: invalid YouTube URL. Resend with full link like https://www.youtube.com/watch?v=..."

    out_name = f"yt_{vid}.md"
    out_path = safe_path(out_name)

    if out_path.exists() and out_path.stat().st_size > 0:
        saved = out_path.read_text(encoding="utf-8")
        body = saved.split("\n\n", 1)[1].strip() if "\n\n" in saved else saved
    else:
        primary = (lang or "en").strip() or "en"
        langs = [primary] if primary == "en" else [primary, "en"]
        body = await asyncio.to_thread(_fetch_sync, vid, langs)
        if body.startswith("error:"):
            return body
        if not body.strip():
            return f"error: empty transcript returned for {vid}."
        out_path.write_text(
            f"# YouTube Transcript: https://youtu.be/{vid}\n\n{body}\n",
            encoding="utf-8",
        )

    from rag import ingest_doc
    idx_msg = await asyncio.to_thread(ingest_doc, out_name)

    preview = body[:PREVIEW_CHARS]
    if len(body) > PREVIEW_CHARS:
        next_step = (
            f" Transcript truncated in preview; call read_doc(source='{out_name}', part=2) "
            f"or search_docs before summarizing."
        )
    else:
        next_step = " Full transcript fits below; summarize directly."

    return (
        f"DONE. Transcript saved to {out_name}, {len(body)} chars. {idx_msg}.{next_step}\n\n"
        f"Preview:\n{preview}"
    )