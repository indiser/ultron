import ctypes
import os
import platform
import re
import shutil
import socket
import subprocess
import time
from typing import Any

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore[assignment]

__all__ = ["system_status", "get_system_metrics"]

_LAST_CPU_SAMPLE = 0.0
_SKIP_FSTYPES = frozenset({
    "squashfs", "tmpfs", "devtmpfs", "overlay", "proc", "sysfs",
    "cgroup", "cgroup2", "debugfs", "tracefs", "securityfs", "pstore",
    "autofs", "mqueue", "hugetlbfs", "fusectl", "configfs", "nsfs",
})


def _fmt_bytes(num_bytes: int | float) -> str:
    val = float(max(0.0, num_bytes))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if val < 1024.0 or unit == "TB":
            return f"{val:.1f} {unit}" if unit != "B" else f"{int(val)} B"
        val /= 1024.0
    return f"{val:.1f} TB"


def _fmt_uptime(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "unknown"
    total = int(seconds)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{mins}m")
    return " ".join(parts)


def _get_uptime_sec() -> float | None:
    if psutil is not None:
        try:
            return max(0.0, time.time() - psutil.boot_time())
        except Exception:
            pass

    sys_name = platform.system()
    try:
        if sys_name == "Windows":
            ms = ctypes.windll.kernel32.GetTickCount64()  # type: ignore[attr-defined]
            return ms / 1000.0
        if sys_name == "Linux" and os.path.exists("/proc/uptime"):
            with open("/proc/uptime", "r", encoding="utf-8") as f:
                return float(f.read().split()[0])
        if sys_name == "Darwin":
            out = subprocess.check_output(
                ["sysctl", "-n", "kern.boottime"], text=True, timeout=1.5
            )
            m = re.search(r"sec\s*=\s*(\d+)", out)
            if m:
                return max(0.0, time.time() - float(m.group(1)))
    except Exception:
        pass
    return None


def _get_cpu() -> dict[str, Any]:
    global _LAST_CPU_SAMPLE
    info: dict[str, Any] = {
        "percent": None,
        "logical_cores": os.cpu_count(),
        "physical_cores": None,
        "freq_mhz": None,
        "load_avg": None,
    }

    if hasattr(os, "getloadavg"):
        try:
            l1, l5, l15 = os.getloadavg()
            info["load_avg"] = [round(l1, 2), round(l5, 2), round(l15, 2)]
        except OSError:
            pass

    if psutil is None:
        return info

    try:
        now = time.monotonic()
        interval = 0.15 if (now - _LAST_CPU_SAMPLE) > 2.0 else None
        info["percent"] = round(float(psutil.cpu_percent(interval=interval)), 1)
        _LAST_CPU_SAMPLE = time.monotonic()
    except Exception:
        pass

    try:
        info["logical_cores"] = psutil.cpu_count(logical=True) or info["logical_cores"]
        info["physical_cores"] = psutil.cpu_count(logical=False)
    except Exception:
        pass

    try:
        freq = psutil.cpu_freq()
        if freq and freq.current:
            info["freq_mhz"] = round(float(freq.current))
    except Exception:
        pass

    return info


def _fallback_memory() -> tuple[dict[str, Any], dict[str, Any]]:
    mem: dict[str, Any] = {"total": None, "used": None, "available": None, "percent": None}
    swap: dict[str, Any] = {"total": None, "used": None, "percent": None}
    sys_name = platform.system()

    try:
        if sys_name == "Windows":
            class _MEMSTAT(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = _MEMSTAT()
            stat.dwLength = ctypes.sizeof(_MEMSTAT)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):  # type: ignore[attr-defined]
                total = int(stat.ullTotalPhys)
                avail = int(stat.ullAvailPhys)
                used = max(0, total - avail)
                mem = {
                    "total": total,
                    "used": used,
                    "available": avail,
                    "percent": round((used / total) * 100, 1) if total else 0.0,
                }
        elif sys_name == "Linux" and os.path.exists("/proc/meminfo"):
            kv: dict[str, int] = {}
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        kv[parts[0].rstrip(":")] = int(parts[1]) * 1024
            total = kv.get("MemTotal", 0)
            avail = kv.get("MemAvailable", kv.get("MemFree", 0))
            if total > 0:
                used = max(0, total - avail)
                mem = {
                    "total": total,
                    "used": used,
                    "available": avail,
                    "percent": round((used / total) * 100, 1),
                }
            stotal = kv.get("SwapTotal", 0)
            sfree = kv.get("SwapFree", 0)
            if stotal > 0:
                sused = max(0, stotal - sfree)
                swap = {
                    "total": stotal,
                    "used": sused,
                    "percent": round((sused / stotal) * 100, 1),
                }
        elif sys_name == "Darwin":
            total_s = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=1.5)
            vm_s = subprocess.check_output(["vm_stat"], text=True, timeout=1.5)
            total = int(total_s.strip())
            pm = re.search(r"page size of (\d+) bytes", vm_s)
            page_size = int(pm.group(1)) if pm else 4096
            pages: dict[str, int] = {}
            for line in vm_s.splitlines():
                m = re.match(r"^Pages\s+([^:]+):\s+(\d+)\.", line.strip())
                if m:
                    pages[m.group(1).lower()] = int(m.group(2))
            avail_pages = pages.get("free", 0) + pages.get("inactive", 0) + pages.get("speculative", 0)
            avail = min(total, avail_pages * page_size)
            used = max(0, total - avail)
            mem = {
                "total": total,
                "used": used,
                "available": avail,
                "percent": round((used / total) * 100, 1) if total else 0.0,
            }
    except Exception:
        pass

    return mem, swap


def _get_memory() -> tuple[dict[str, Any], dict[str, Any]]:
    if psutil is None:
        return _fallback_memory()

    mem: dict[str, Any] = {"total": None, "used": None, "available": None, "percent": None}
    swap: dict[str, Any] = {"total": None, "used": None, "percent": None}

    try:
        vm = psutil.virtual_memory()
        mem = {
            "total": int(vm.total),
            "used": int(vm.used),
            "available": int(vm.available),
            "percent": round(float(vm.percent), 1),
        }
    except Exception:
        mem, _ = _fallback_memory()

    try:
        sw = psutil.swap_memory()
        swap = {
            "total": int(sw.total),
            "used": int(sw.used),
            "percent": round(float(sw.percent), 1),
        }
    except Exception:
        pass

    return mem, swap


def _get_disks() -> list[dict[str, Any]]:
    disks: list[dict[str, Any]] = []
    seen_mounts: set[str] = set()
    sys_name = platform.system()

    if psutil is not None:
        try:
            parts = psutil.disk_partitions(all=False)
            for p in parts:
                fstype = (p.fstype or "").lower()
                opts = (p.opts or "").lower()
                if fstype in _SKIP_FSTYPES or "cdrom" in opts:
                    continue
                if sys_name == "Linux" and p.mountpoint.startswith(("/snap/", "/var/snap/", "/run/")):
                    continue
                if sys_name == "Darwin" and p.mountpoint.startswith("/System/Volumes/") and p.mountpoint != "/System/Volumes/Data":
                    continue
                if p.mountpoint in seen_mounts:
                    continue
                try:
                    usage = psutil.disk_usage(p.mountpoint)
                    if usage.total <= 0:
                        continue
                    seen_mounts.add(p.mountpoint)
                    disks.append({
                        "mount": p.mountpoint,
                        "fstype": p.fstype or "unknown",
                        "total": int(usage.total),
                        "used": int(usage.used),
                        "free": int(usage.free),
                        "percent": round(float(usage.percent), 1),
                    })
                except (PermissionError, OSError):
                    continue
        except Exception:
            pass

    if not disks:
        fallback_path = os.path.abspath(os.sep)
        try:
            du = shutil.disk_usage(fallback_path)
            if du.total > 0:
                disks.append({
                    "mount": fallback_path,
                    "fstype": "unknown",
                    "total": int(du.total),
                    "used": int(du.used),
                    "free": int(du.free),
                    "percent": round((du.used / du.total) * 100, 1),
                })
        except Exception:
            pass

    return disks


def _get_battery() -> dict[str, Any] | None:
    if psutil is None or not hasattr(psutil, "sensors_battery"):
        return None
    try:
        batt = psutil.sensors_battery()
        if batt is None:
            return None
        secs = getattr(batt, "secsleft", None)
        time_left: str | None = None
        if isinstance(secs, (int, float)) and secs >= 0:
            hrs, rem = divmod(int(secs), 3600)
            mins, _ = divmod(rem, 60)
            time_left = f"{hrs}h {mins}m"
        return {
            "percent": round(float(batt.percent), 1),
            "plugged": bool(batt.power_plugged),
            "time_left": time_left,
        }
    except Exception:
        return None


def _get_temp_c() -> float | None:
    if psutil is None or not hasattr(psutil, "sensors_temperatures"):
        return None
    try:
        temps = psutil.sensors_temperatures()  # type: ignore[attr-defined]
        if not temps:
            return None
        readings: list[float] = []
        for entries in temps.values():
            for e in entries:
                cur = getattr(e, "current", None)
                if isinstance(cur, (int, float)) and 0 < cur < 150:
                    readings.append(float(cur))
        return round(max(readings), 1) if readings else None
    except Exception:
        return None


def _get_gpu() -> list[dict[str, Any]]:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return []
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.check_output(
            [
                smi,
                "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=1.5,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        gpus: list[dict[str, Any]] = []
        for line in out.strip().splitlines():
            cols = [c.strip() for c in line.split(",")]
            if len(cols) >= 5:
                gpus.append({
                    "name": cols[0],
                    "util_percent": float(cols[1]) if cols[1].replace(".", "", 1).isdigit() else None,
                    "mem_used_mb": int(float(cols[2])) if cols[2].replace(".", "", 1).isdigit() else None,
                    "mem_total_mb": int(float(cols[3])) if cols[3].replace(".", "", 1).isdigit() else None,
                    "temp_c": int(float(cols[4])) if cols[4].replace(".", "", 1).isdigit() else None,
                })
        return gpus
    except Exception:
        return []


def _get_self_rss() -> int | None:
    if psutil is None:
        return None
    try:
        return int(psutil.Process().memory_info().rss)
    except Exception:
        return None


def get_system_metrics() -> dict[str, Any]:
    """Structured snapshot for both system_status() tool and Web UI SYSTEM panel."""
    mem, swap = _get_memory()
    uptime_sec = _get_uptime_sec()
    return {
        "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "hostname": socket.gethostname(),
        "uptime_sec": round(uptime_sec) if uptime_sec is not None else None,
        "uptime_human": _fmt_uptime(uptime_sec),
        "cpu": _get_cpu(),
        "memory": mem,
        "swap": swap,
        "disks": _get_disks(),
        "battery": _get_battery(),
        "temp_c": _get_temp_c(),
        "gpus": _get_gpu(),
        "ultron_rss": _get_self_rss(),
        "psutil_installed": psutil is not None,
    }


def system_status() -> str:
    try:
        m = get_system_metrics()
    except Exception as exc:
        return f"error: failed to read system status: {exc}"

    lines: list[str] = [
        f"Host: {m['hostname']} | OS: {m['os']} | Uptime: {m['uptime_human']}"
    ]

    cpu = m["cpu"]
    cpu_parts: list[str] = []
    if cpu["percent"] is not None:
        cpu_parts.append(f"{cpu['percent']}%")
    cores = []
    if cpu["physical_cores"]:
        cores.append(f"{cpu['physical_cores']}P")
    if cpu["logical_cores"]:
        cores.append(f"{cpu['logical_cores']}L")
    if cores:
        cpu_parts.append(f"({'/'.join(cores)} cores)")
    if cpu["freq_mhz"]:
        cpu_parts.append(f"@ {cpu['freq_mhz']} MHz")
    if cpu["load_avg"]:
        cpu_parts.append(f"load {cpu['load_avg'][0]}/{cpu['load_avg'][1]}/{cpu['load_avg'][2]}")
    if m["temp_c"] is not None:
        cpu_parts.append(f"max temp {m['temp_c']}C")
    lines.append(f"CPU: {' '.join(cpu_parts) if cpu_parts else 'unavailable'}")

    mem = m["memory"]
    if mem["total"]:
        mem_line = (
            f"RAM: {_fmt_bytes(mem['used'])} / {_fmt_bytes(mem['total'])} "
            f"({mem['percent']}%, avail {_fmt_bytes(mem['available'])})"
        )
    else:
        mem_line = "RAM: unavailable"
    swap = m["swap"]
    if swap["total"] and swap["total"] > 0:
        mem_line += f" | Swap: {_fmt_bytes(swap['used'])} / {_fmt_bytes(swap['total'])} ({swap['percent']}%)"
    lines.append(mem_line)

    if m["disks"]:
        d_strs = [
            f"{d['mount']} {_fmt_bytes(d['used'])}/{_fmt_bytes(d['total'])} ({d['percent']}%, free {_fmt_bytes(d['free'])})"
            for d in m["disks"]
        ]
        lines.append("Disk: " + " | ".join(d_strs))
    else:
        lines.append("Disk: unavailable")

    batt = m["battery"]
    if batt is not None:
        state = "plugged in" if batt["plugged"] else "on battery"
        extra = f", {batt['time_left']} left" if (not batt["plugged"] and batt["time_left"]) else ""
        lines.append(f"Battery: {batt['percent']}% ({state}{extra})")
    else:
        lines.append("Battery: none (desktop/AC)")

    for i, g in enumerate(m["gpus"]):
        g_parts = [g["name"]]
        if g["util_percent"] is not None:
            g_parts.append(f"{g['util_percent']}%")
        if g["mem_used_mb"] is not None and g["mem_total_mb"] is not None:
            g_parts.append(f"VRAM {g['mem_used_mb']}/{g['mem_total_mb']} MB")
        if g["temp_c"] is not None:
            g_parts.append(f"{g['temp_c']}C")
        lines.append(f"GPU{i}: {' | '.join(g_parts)}")

    if m["ultron_rss"]:
        lines.append(f"Ultron process RAM: {_fmt_bytes(m['ultron_rss'])}")

    if not m["psutil_installed"]:
        lines.append("Note: psutil not installed; running OS fallback (install psutil for full sensors).")

    return "\n".join(lines)