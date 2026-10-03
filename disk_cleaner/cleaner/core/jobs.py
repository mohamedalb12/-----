"""
jobs.py — تشغيل المهام الطويلة في الخلفية.

كل مهمة (فحص، حذف، ...) تعمل في خيط مستقل وترسل رسائلها إلى طابور واحد
تقرأه الواجهة من الخيط الرئيسي (لأن Tkinter لا يسمح بتعديل الواجهة من خيط آخر).

صيغة الرسالة:  (job, kind, payload)
    kind = "progress"  payload = (fraction | None, text)   ‏None = تقدّم غير محدّد
    kind = "finished"  payload = (result, error_traceback | None)
    أو أي نوع مخصص ترسله المهمة عبر ctx.emit(...)
"""

from __future__ import annotations

import queue
import threading
import time
import traceback
from typing import Any, Callable, Optional


class Job(threading.Thread):
    def __init__(self, sink: "queue.Queue", listener: Any, fn: Callable, *args, name: str = "",
                 **kwargs):
        super().__init__(daemon=True, name=name or getattr(fn, "__name__", "job"))
        self.sink = sink
        self.listener = listener
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.errors = 0
        self.started_at = 0.0
        self.elapsed = 0.0
        self._cancel = threading.Event()
        self._last_progress = 0.0

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def emit(self, kind: str, *payload) -> None:
        self.sink.put((self, kind, payload))

    def run(self) -> None:
        self.started_at = time.monotonic()
        result, error = None, None
        try:
            result = self.fn(JobContext(self), *self.args, **self.kwargs)
        except Exception:  # لا نسمح لأي خطأ غير متوقع بإسقاط البرنامج
            error = traceback.format_exc()
        self.elapsed = time.monotonic() - self.started_at
        self.emit("finished", result, error)


class JobContext:
    """
    يُمرَّر لدوال الفحص في core: يتيح لها معرفة طلب الإيقاف، وإرسال التقدم،
    وعدّ الأخطاء. ‏sub(lo, hi) يحجز جزءاً من شريط التقدم لمرحلة فرعية.
    """

    THROTTLE = 0.08

    def __init__(self, job: Optional[Job] = None, lo: float = 0.0, hi: float = 1.0):
        self.job = job
        self.lo = lo
        self.hi = hi

    @property
    def cancelled(self) -> bool:
        return bool(self.job and self.job.cancelled)

    def progress(self, fraction: Optional[float], text: str = "", force: bool = False) -> None:
        if not self.job:
            return
        now = time.monotonic()
        if not force and now - self.job._last_progress < self.THROTTLE:
            return
        self.job._last_progress = now
        if fraction is not None:
            fraction = self.lo + (self.hi - self.lo) * max(0.0, min(1.0, fraction))
        self.job.emit("progress", fraction, text)

    def sub(self, lo: float, hi: float) -> "JobContext":
        span = self.hi - self.lo
        return JobContext(self.job, self.lo + span * lo, self.lo + span * hi)

    def error(self, n: int = 1) -> None:
        if self.job:
            self.job.errors += n

    def emit(self, kind: str, *payload) -> None:
        if self.job:
            self.job.emit(kind, *payload)


# سياق فارغ لاستدعاء دوال الفحص مباشرة (مثلاً في الاختبارات)
NULL_CONTEXT = JobContext(None)
