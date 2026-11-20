import asyncio
from datetime import datetime, timedelta
import json
import os
import re
import threading
from typing import Awaitable, Callable
import uuid

from config import SCHEDULES_FILE
from text_ui import c

try:
    import voice_out
except Exception:
    voice_out = None  # type: ignore[assignment]

__all__ = ["manage_schedule", "start_scheduler", "stop_scheduler"]

_LOCK = threading.RLock()
_TASK: asyncio.Task | None = None
_STOP_EVENT: asyncio.Event | None = None

_IS_BUSY_FN: Callable[[], bool] = lambda: False
_GET_SYS_FN: Callable[[], str] | None = None
_RUN_AGENT_FN: Callable[[list[dict]], Awaitable[str]] | None = None

_MAX_JOBS = 50
_TICK_SECONDS = 10
_MISSED_GRACE_SEC = 3600  # Speak missed one-shot reminders up to 1h late; expire older ones

_CRON_SHORTCUTS = {
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
}

_MONTH_NAMES = {
    "jan": "1", "feb": "2", "mar": "3", "apr": "4",
    "may": "5", "jun": "6", "jul": "7", "aug": "8",
    "sep": "9", "oct": "10", "nov": "11", "dec": "12",
}

_DOW_NAMES = {
    "sun": "0", "mon": "1", "tue": "2", "wed": "3",
    "thu": "4", "fri": "5", "sat": "6",
}


def _load_jobs() -> list[dict]:
    with _LOCK:
        if not os.path.exists(SCHEDULES_FILE):
            return []
        try:
            with open(SCHEDULES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []


def _save_jobs(jobs: list[dict]) -> None:
    with _LOCK:
        tmp = f"{SCHEDULES_FILE}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(jobs, f, indent=2, ensure_ascii=False)
        os.replace(tmp, SCHEDULES_FILE)


def _parse_when(raw: str, now: datetime) -> datetime:
    s = (raw or "").strip()
    if not s:
        raise ValueError("when is required (e.g. '10m', '2h', '18:30', or '2026-11-20 18:30').")

    # Pure integer seconds
    if re.fullmatch(r"\d+", s):
        secs = int(s)
        if secs <= 0:
            raise ValueError("delay must be > 0 seconds.")
        return now + timedelta(seconds=secs)

    # Human duration: 1d 2h 30m 15s
    m_dur = re.fullmatch(
        r"(?:(\d+)\s*d(?:ays?)?)?\s*(?:(\d+)\s*h(?:ours?|rs?)?)?\s*(?:(\d+)\s*m(?:ins?|inutes?)?)?\s*(?:(\d+)\s*s(?:ecs?|econds?)?)?",
        s,
        re.I,
    )
    if m_dur and any(m_dur.groups()):
        days = int(m_dur.group(1) or 0)
        hours = int(m_dur.group(2) or 0)
        mins = int(m_dur.group(3) or 0)
        secs = int(m_dur.group(4) or 0)
        delta = timedelta(days=days, hours=hours, minutes=mins, seconds=secs)
        if delta.total_seconds() <= 0:
            raise ValueError("duration must be > 0.")
        return now + delta

    # Time of day HH:MM or HH:MM:SS (today, or tomorrow if already passed)
    m_tod = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", s)
    if m_tod:
        hh, mm, ss = int(m_tod.group(1)), int(m_tod.group(2)), int(m_tod.group(3) or 0)
        if not (0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
            raise ValueError(f"invalid time '{s}'.")
        target = now.replace(hour=hh, minute=mm, second=ss, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target

    # ISO datetime
    try:
        target = datetime.fromisoformat(s.replace("Z", ""))
        if target.tzinfo is not None:
            target = target.astimezone().replace(tzinfo=None)
    except ValueError as exc:
        raise ValueError(
            f"cannot parse time '{s}'. Use '15m', '2h', '17:30', or 'YYYY-MM-DD HH:MM'."
        ) from exc

    if target <= now:
        raise ValueError(f"target time '{target.strftime('%Y-%m-%d %H:%M:%S')}' is in the past.")
    return target


def _replace_names(expr: str, mapping: dict[str, str]) -> str:
    out = expr.lower()
    for k, v in mapping.items():
        out = re.sub(rf"\b{k}\b", v, out)
    return out


def _parse_cron_field(field: str, min_v: int, max_v: int, is_dow: bool = False) -> set[int]:
    vals: set[int] = set()
    for chunk in field.split(","):
        chunk = chunk.strip()
        if not chunk:
            raise ValueError("empty cron list item")
        if "/" in chunk:
            base, step_s = chunk.split("/", 1)
            if not step_s.isdigit() or int(step_s) <= 0:
                raise ValueError(f"invalid cron step '{chunk}'")
            step = int(step_s)
        else:
            base, step = chunk, 1

        if base == "*":
            lo, hi = min_v, max_v
        elif "-" in base:
            a_s, b_s = base.split("-", 1)
            if not (a_s.isdigit() and b_s.isdigit()):
                raise ValueError(f"invalid cron range '{chunk}'")
            lo, hi = int(a_s), int(b_s)
            if is_dow and hi == 7:
                hi = 6
                vals.add(0)
            if lo < min_v or hi > max_v or lo > hi:
                raise ValueError(f"cron range out of bounds [{min_v}-{max_v}]: '{chunk}'")
        else:
            if not base.isdigit():
                raise ValueError(f"invalid cron token '{chunk}'")
            v = int(base)
            if is_dow and v == 7:
                v = 0
            if v < min_v or v > max_v:
                raise ValueError(f"cron value out of bounds [{min_v}-{max_v}]: '{chunk}'")
            lo, hi = v, v

        for x in range(lo, hi + 1, step):
            vals.add(0 if (is_dow and x == 7) else x)
    return vals


def _compile_cron(raw_cron: str) -> tuple[str, tuple[set[int], set[int], set[int], set[int], set[int], bool, bool]]:
    s = (raw_cron or "").strip()
    s = _CRON_SHORTCUTS.get(s.lower(), s)
    parts = s.split()
    if len(parts) != 5:
        raise ValueError(
            f"cron must have 5 fields 'min hour day month weekday' (got {len(parts)}). Example: '0 9 * * 1-5'."
        )
    f_min, f_hour, f_dom, f_mon, f_dow = parts
    f_mon = _replace_names(f_mon, _MONTH_NAMES)
    f_dow = _replace_names(f_dow, _DOW_NAMES)

    mins = _parse_cron_field(f_min, 0, 59)
    hours = _parse_cron_field(f_hour, 0, 23)
    doms = _parse_cron_field(f_dom, 1, 31)
    mons = _parse_cron_field(f_mon, 1, 12)
    dows = _parse_cron_field(f_dow, 0, 6, is_dow=True)

    dom_restricted = not f_dom.startswith("*")
    dow_restricted = not f_dow.startswith("*")
    return s, (mins, hours, doms, mons, dows, dom_restricted, dow_restricted)


def _cron_matches(compiled: tuple[set[int], set[int], set[int], set[int], set[int], bool, bool], dt: datetime) -> bool:
    mins, hours, doms, mons, dows, dom_res, dow_res = compiled
    if dt.minute not in mins or dt.hour not in hours or dt.month not in mons:
        return False
    # Standard cron: Sunday = 0, Monday = 1 .. Saturday = 6
    cron_dow = (dt.weekday() + 1) % 7
    dom_ok = dt.day in doms
    dow_ok = cron_dow in dows
    if dom_res and dow_res:
        return dom_ok or dow_ok
    return dom_ok and dow_ok


async def _announce(title: str, text: str, speak_it: bool = True) -> None:
    msg = text.strip()
    if not msg:
        return
    print(f"\n{c('info', f'[schedule:{title}]')} {msg}")
    if speak_it and voice_out is not None:
        try:
            await asyncio.to_thread(voice_out.speak, msg)
        except Exception:
            pass


async def _run_agent_job(job: dict) -> None:
    if _RUN_AGENT_FN is None or _GET_SYS_FN is None:
        await _announce(job["name"], f"Scheduled task '{job['name']}': {job['task']}", speak_it=True)
        return

    # Wait until foreground REPL turn finishes so Kaggle llama-server (-np 1) is idle
    waited = 0
    while _IS_BUSY_FN() and waited < 180:
        await asyncio.sleep(2)
        waited += 2

    sys_prompt = _GET_SYS_FN()
    prompt = (
        f"[PROACTIVE SCHEDULED CHECK — Job: {job['name']}]\n"
        f"Task: {job['task']}\n\n"
        "Instructions: Run only the minimal read-only tool checks needed for this task. "
        "If everything is normal and requires no user attention, reply with the exact single word: NO_ALERT\n"
        "If an issue, change, or condition requires attention, give a concise 1-2 sentence alert."
    )
    isolated_msgs = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": prompt},
    ]
    try:
        reply = await _RUN_AGENT_FN(isolated_msgs)
    except Exception as exc:
        print(f"\n{c('error', f'[schedule:{job["name"]}] check failed: {exc}')}")
        return

    clean = (reply or "").strip()
    if not clean or clean.upper().startswith("NO_ALERT"):
        return
    await _announce(job["name"], clean, speak_it=True)


async def _fire_job(job: dict) -> None:
    mode = job.get("mode", "notify")
    if mode == "agent":
        await _run_agent_job(job)
    else:
        await _announce(job["name"], job["task"], speak_it=True)


async def _scheduler_loop() -> None:
    assert _STOP_EVENT is not None
    # Startup catch-up for one-shot reminders missed while offline
    now = datetime.now()
    jobs = _load_jobs()
    dirty = False
    for job in jobs:
        if not job.get("enabled", True) or job.get("kind") != "once":
            continue
        try:
            due = datetime.fromisoformat(job["run_at"])
        except Exception:
            job["enabled"] = False
            dirty = True
            continue
        if due <= now:
            late_sec = (now - due).total_seconds()
            job["enabled"] = False
            job["last_run"] = now.isoformat(timespec="seconds")
            dirty = True
            if late_sec <= _MISSED_GRACE_SEC:
                mins_late = max(1, round(late_sec / 60))
                await _announce(
                    job["name"],
                    f"Missed reminder ({mins_late}m ago): {job['task']}",
                    speak_it=True,
                )
    if dirty:
        _save_jobs(jobs)

    while not _STOP_EVENT.is_set():
        try:
            await asyncio.wait_for(_STOP_EVENT.wait(), timeout=_TICK_SECONDS)
            break
        except asyncio.TimeoutError:
            pass

        now = datetime.now()
        minute_stamp = now.strftime("%Y-%m-%d %H:%M")
        jobs = _load_jobs()
        to_fire: list[dict] = []
        changed = False

        for job in jobs:
            if not job.get("enabled", True):
                continue

            kind = job.get("kind")
            if kind == "once":
                try:
                    due = datetime.fromisoformat(job["run_at"])
                except Exception:
                    job["enabled"] = False
                    changed = True
                    continue
                if due <= now:
                    job["enabled"] = False
                    job["last_run"] = now.isoformat(timespec="seconds")
                    changed = True
                    to_fire.append(dict(job))

            elif kind == "cron":
                if job.get("last_minute") == minute_stamp:
                    continue
                try:
                    _, compiled = _compile_cron(job["cron"])
                except Exception:
                    job["enabled"] = False
                    changed = True
                    continue
                if _cron_matches(compiled, now):
                    job["last_minute"] = minute_stamp
                    job["last_run"] = now.isoformat(timespec="seconds")
                    changed = True
                    to_fire.append(dict(job))

        if changed:
            _save_jobs(jobs)

        for job in to_fire:
            asyncio.create_task(_fire_job(job))


def start_scheduler(
    is_busy: Callable[[], bool] | None = None,
    get_system_prompt: Callable[[], str] | None = None,
    run_agent_fn: Callable[[list[dict]], Awaitable[str]] | None = None,
) -> None:
    global _TASK, _STOP_EVENT, _IS_BUSY_FN, _GET_SYS_FN, _RUN_AGENT_FN
    if is_busy is not None:
        _IS_BUSY_FN = is_busy
    if get_system_prompt is not None:
        _GET_SYS_FN = get_system_prompt
    if run_agent_fn is not None:
        _RUN_AGENT_FN = run_agent_fn

    if _TASK is not None and not _TASK.done():
        return
    _STOP_EVENT = asyncio.Event()
    _TASK = asyncio.create_task(_scheduler_loop())


def stop_scheduler() -> None:
    if _STOP_EVENT is not None:
        _STOP_EVENT.set()
    if _TASK is not None and not _TASK.done():
        _TASK.cancel()


def _find_job(jobs: list[dict], ident: str) -> dict | None:
    q = (ident or "").strip().lower()
    if not q:
        return None
    for j in jobs:
        if j["id"].lower() == q or j["name"].lower() == q:
            return j
    for j in jobs:
        if j["id"].lower().startswith(q) or q in j["name"].lower():
            return j
    return None


async def manage_schedule(
    action: str,
    name: str = "",
    when: str = "",
    cron: str = "",
    task: str = "",
    mode: str = "notify",
    job_id: str = "",
) -> str:
    act = (action or "").strip().lower()
    now = datetime.now()

    if act == "list":
        jobs = _load_jobs()
        if not jobs:
            return "No scheduled reminders or cron jobs."
        lines: list[str] = []
        for j in jobs:
            status = "ON" if j.get("enabled", True) else "OFF"
            sched = f"at {j['run_at']}" if j["kind"] == "once" else f"cron '{j['cron']}'"
            last = f" | last: {j['last_run']}" if j.get("last_run") else ""
            lines.append(
                f"[{j['id']}] {j['name']} ({status}, {j['kind']}/{j.get('mode', 'notify')}) — {sched}{last}\n"
                f"    task: {j['task']}"
            )
        return "\n".join(lines)

    if act == "add_reminder":
        if not task.strip() and name.strip():
            task = name.strip()
        if not task.strip():
            return (
                "error: missing 'task' arg. Extract the reminder text from the user's message and resend "
                'manage_schedule with action, when, and task, e.g. {"action": "add_reminder", "when": "20s", "task": "Check the oven"}.'
            )
        try:
            due = _parse_when(when, now)
        except ValueError as exc:
            return f"error: {exc}"

        jobs = _load_jobs()
        if len(jobs) >= _MAX_JOBS:
            return f"error: max {_MAX_JOBS} scheduled jobs reached. Remove old jobs first."

        clean_mode = "agent" if mode.strip().lower() == "agent" else "notify"
        job_name = name.strip() or task.strip()[:32]
        jid = uuid.uuid4().hex[:6]
        jobs.append({
            "id": jid,
            "name": job_name,
            "kind": "once",
            "mode": clean_mode,
            "run_at": due.isoformat(timespec="seconds"),
            "task": task.strip(),
            "enabled": True,
            "created_at": now.isoformat(timespec="seconds"),
            "last_run": None,
        })
        _save_jobs(jobs)
        return f"saved: reminder [{jid}] '{job_name}' set for {due.strftime('%Y-%m-%d %H:%M:%S')} ({clean_mode})."

    if act == "add_cron":
        if not task.strip() and name.strip():
            task = name.strip()
        if not task.strip():
            return (
                "error: missing 'task' arg. Resend manage_schedule with action, cron, and task, "
                'e.g. {"action": "add_cron", "cron": "0 9 * * *", "task": "Check system status"}.'
            )
        try:
            norm_cron, _ = _compile_cron(cron)
        except ValueError as exc:
            return f"error: {exc}"

        jobs = _load_jobs()
        if len(jobs) >= _MAX_JOBS:
            return f"error: max {_MAX_JOBS} scheduled jobs reached. Remove old jobs first."

        clean_mode = "agent" if mode.strip().lower() == "agent" else "notify"
        job_name = name.strip() or task.strip()[:32]
        jid = uuid.uuid4().hex[:6]
        jobs.append({
            "id": jid,
            "name": job_name,
            "kind": "cron",
            "mode": clean_mode,
            "cron": norm_cron,
            "task": task.strip(),
            "enabled": True,
            "created_at": now.isoformat(timespec="seconds"),
            "last_minute": None,
            "last_run": None,
        })
        _save_jobs(jobs)
        return f"saved: cron job [{jid}] '{job_name}' ({norm_cron}, mode={clean_mode})."

    if act == "remove":
        ident = job_id.strip() or name.strip()
        if not ident:
            return "error: remove requires 'job_id' or 'name'. Call list first."
        jobs = _load_jobs()
        target = _find_job(jobs, ident)
        if target is None:
            return f"error: no scheduled job matching '{ident}'."
        jobs = [j for j in jobs if j["id"] != target["id"]]
        _save_jobs(jobs)
        return f"deleted: scheduled job [{target['id']}] '{target['name']}'."

    if act == "toggle":
        ident = job_id.strip() or name.strip()
        if not ident:
            return "error: toggle requires 'job_id' or 'name'."
        jobs = _load_jobs()
        target = _find_job(jobs, ident)
        if target is None:
            return f"error: no scheduled job matching '{ident}'."
        target["enabled"] = not target.get("enabled", True)
        _save_jobs(jobs)
        state = "enabled" if target["enabled"] else "paused"
        return f"updated: job [{target['id']}] '{target['name']}' is now {state}."

    if act == "run_now":
        ident = job_id.strip() or name.strip()
        if not ident:
            return "error: run_now requires 'job_id' or 'name'."
        jobs = _load_jobs()
        target = _find_job(jobs, ident)
        if target is None:
            return f"error: no scheduled job matching '{ident}'."
        asyncio.create_task(_fire_job(dict(target)))
        return f"DONE. Triggered job [{target['id']}] '{target['name']}' in background."

    return f"error: invalid action '{action}'. Use: add_reminder, add_cron, list, remove, toggle, run_now."