"""
monitor.py — مراقبة أداء الجهاز لحظياً: المعالج، الذاكرة، الشبكة، القرص، البطارية، والعمليات.

يعتمد على مكتبة psutil. ‏run_monitor() تعمل في الخلفية وترسل عيّنة كل ثانية.
"""

from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import psutil

from .jobs import JobContext
from .shell import run

IS_MAC = sys.platform == "darwin"


@dataclass
class ProcInfo:
    pid: int
    name: str
    cpu: float
    memory: int
    user: str = ""


@dataclass
class Sample:
    time: float
    cpu: float
    per_cpu: List[float]
    mem_total: int
    mem_used: int
    mem_percent: float
    swap_used: int
    net_down: float          # بايت/ثانية
    net_up: float
    disk_read: float
    disk_write: float
    battery: Optional[float] = None
    plugged: Optional[bool] = None
    battery_secs: Optional[int] = None
    uptime: float = 0.0
    load: tuple = ()
    procs_cpu: List[ProcInfo] = field(default_factory=list)
    procs_mem: List[ProcInfo] = field(default_factory=list)


@dataclass
class BatteryHealth:
    cycle_count: Optional[int] = None
    health_percent: Optional[float] = None
    condition: str = ""


def battery_health() -> Optional[BatteryHealth]:
    """صحة البطارية وعدد دورات الشحن (من ioreg في macOS)."""
    if not IS_MAC:
        return None
    code, out = run(["ioreg", "-rn", "AppleSmartBattery"], timeout=10)
    if code != 0 or "CycleCount" not in out:
        return None

    def num(key: str) -> Optional[int]:
        m = re.search(rf'"{key}" = (\d+)', out)
        return int(m.group(1)) if m else None

    design = num("DesignCapacity")
    raw_max = num("AppleRawMaxCapacity") or num("NominalChargeCapacity")
    max_cap = num("MaxCapacity")
    if raw_max is None and max_cap and max_cap > 100:
        raw_max = max_cap
    health = round(raw_max / design * 100, 1) if design and raw_max else None
    if health is not None:
        condition = "ممتازة" if health >= 90 else "جيدة" if health >= 80 else "تحتاج صيانة"
    else:
        condition = ""
    return BatteryHealth(num("CycleCount"), health, condition)


class _ProcessSampler:
    """يحتفظ بكائنات العمليات بين العيّنات لحساب نسبة المعالج بدقة."""

    def __init__(self):
        self.procs: Dict[int, psutil.Process] = {}

    def sample(self, top: int = 12):
        alive = {}
        rows: List[ProcInfo] = []
        for p in psutil.process_iter(["pid", "name", "username"]):
            pid = p.info["pid"]
            proc = self.procs.get(pid, p)
            alive[pid] = proc
            try:
                cpu = proc.cpu_percent(None)
                mem = proc.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
                continue
            rows.append(ProcInfo(pid, p.info["name"] or "?", cpu, mem, p.info.get("username") or ""))
        self.procs = alive
        by_cpu = sorted(rows, key=lambda r: r.cpu, reverse=True)[:top]
        by_mem = sorted(rows, key=lambda r: r.memory, reverse=True)[:top]
        return by_cpu, by_mem


def run_monitor(ctx: JobContext, interval: float = 1.0, with_processes: bool = True) -> None:
    """حلقة المراقبة: ترسل ("sample", Sample) حتى يتم الإيقاف."""
    sampler = _ProcessSampler()
    psutil.cpu_percent(None, percpu=True)
    last_net = psutil.net_io_counters()
    last_disk = psutil.disk_io_counters()
    last_t = time.monotonic()
    boot = psutil.boot_time()
    tick = 0
    while not ctx.cancelled:
        time.sleep(interval)
        if ctx.cancelled:
            break
        now = time.monotonic()
        dt = max(now - last_t, 0.001)
        per_cpu = psutil.cpu_percent(None, percpu=True)
        vm = psutil.virtual_memory()
        net = psutil.net_io_counters()
        disk = psutil.disk_io_counters()
        s = Sample(
            time=time.time(),
            cpu=sum(per_cpu) / max(len(per_cpu), 1),
            per_cpu=per_cpu,
            mem_total=vm.total,
            mem_used=vm.total - vm.available,
            mem_percent=vm.percent,
            swap_used=psutil.swap_memory().used,
            net_down=(net.bytes_recv - last_net.bytes_recv) / dt if net and last_net else 0,
            net_up=(net.bytes_sent - last_net.bytes_sent) / dt if net and last_net else 0,
            disk_read=(disk.read_bytes - last_disk.read_bytes) / dt if disk and last_disk else 0,
            disk_write=(disk.write_bytes - last_disk.write_bytes) / dt if disk and last_disk else 0,
            uptime=time.time() - boot,
            load=os.getloadavg() if hasattr(os, "getloadavg") else (),
        )
        try:
            bat = psutil.sensors_battery()
        except Exception:
            bat = None
        if bat:
            s.battery = bat.percent
            s.plugged = bat.power_plugged
            s.battery_secs = bat.secsleft if isinstance(bat.secsleft, int) and bat.secsleft > 0 else None
        # العمليات كل ثانيتين (أثقل قليلاً)
        if with_processes and tick % 2 == 0:
            s.procs_cpu, s.procs_mem = sampler.sample()
        last_net, last_disk, last_t = net, disk, now
        tick += 1
        ctx.emit("sample", s)


def quick_stats() -> Dict[str, float]:
    """لقطة سريعة للصفحة الرئيسية."""
    vm = psutil.virtual_memory()
    return {"cpu": psutil.cpu_percent(0.3), "mem_percent": vm.percent,
            "mem_used": vm.total - vm.available, "mem_total": vm.total}


def end_process(pid: int, force: bool = False) -> str:
    """إنهاء عملية. يُرجع رسالة خطأ أو نصاً فارغاً عند النجاح."""
    try:
        p = psutil.Process(pid)
        p.kill() if force else p.terminate()
        return ""
    except psutil.NoSuchProcess:
        return ""
    except psutil.AccessDenied:
        return "هذه العملية تخص النظام أو مستخدماً آخر ولا يمكن إنهاؤها من هنا."
    except Exception as exc:
        return str(exc)


def format_rate(bps: float) -> str:
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if bps < 1000:
            return f"{bps:.0f} {unit}" if unit == "B/s" else f"{bps:.1f} {unit}"
        bps /= 1000
    return f"{bps:.1f} TB/s"


def format_duration(secs: float) -> str:
    secs = int(secs)
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d} يوم و {h} ساعة"
    if h:
        return f"{h} ساعة و {m} دقيقة"
    return f"{m} دقيقة"
