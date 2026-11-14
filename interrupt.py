import asyncio
import os
import threading

if os.name == "nt":
    import msvcrt

# set while a tool waits for a y/N answer, so the Esc watcher stays off the keyboard
_asking = threading.Event()


def ask(prompt: str) -> str:
    _asking.set()
    try:
        return input(prompt)
    finally:
        _asking.clear()


def _flush_keys() -> None:
    while msvcrt.kbhit():
        msvcrt.getwch()


async def run_cancellable(coro):
    """Run coro. Esc cancels it. Returns (result, cancelled)."""
    task = asyncio.ensure_future(coro)
    if os.name != "nt":  # Esc watcher is Windows only
        return await task, False

    done = threading.Event()
    loop = asyncio.get_running_loop()

    def watch():
        while not done.is_set():
            if not _asking.is_set() and msvcrt.kbhit():
                if msvcrt.getwch() == "\x1b":
                    loop.call_soon_threadsafe(task.cancel)
                    return
            done.wait(0.05)

    threading.Thread(target=watch, daemon=True).start()
    try:
        return await task, False
    except asyncio.CancelledError:
        if task.cancelled():
            return None, True
        raise
    finally:
        done.set()
        if os.name == "nt":
            _flush_keys()