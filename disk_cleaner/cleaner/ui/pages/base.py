"""base.py — الصفحة الأساسية التي ترث منها كل صفحات البرنامج."""

from __future__ import annotations

from tkinter import messagebox
from typing import Optional

import customtkinter as ctk

from ...core.jobs import Job


class Page(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.job: Optional[Job] = None

    # ------------------------------------------------------------ دورة الحياة
    def on_show(self) -> None:
        """تُستدعى عند فتح الصفحة."""

    def on_hide(self) -> None:
        """تُستدعى عند مغادرة الصفحة."""

    def on_smart_result(self, result) -> None:
        """تُستدعى عند انتهاء الفحص الذكي من الصفحة الرئيسية."""

    # ------------------------------------------------------------ المهام
    @property
    def busy(self) -> bool:
        return bool(self.job and self.job.is_alive())

    def start_job(self, fn, *args, **kwargs) -> Job:
        if self.busy:
            self.job.cancel()
        self.job = self.app.run_job(self, fn, *args, **kwargs)
        return self.job

    def cancel_job(self) -> None:
        if self.busy:
            self.job.cancel()

    def on_job_event(self, job: Job, kind: str, payload: tuple) -> None:
        if job is not self.job:
            return  # رسالة من مهمة قديمة أُلغيت
        if kind == "progress":
            self.on_progress(*payload)
        elif kind == "finished":
            self.job = None
            result, error = payload
            if error:
                messagebox.showerror("حدث خطأ غير متوقع", error.strip().splitlines()[-1])
            self.on_finished(result, job)
        else:
            self.on_custom(kind, payload)

    def on_progress(self, fraction, text) -> None:
        pass

    def on_finished(self, result, job: Job) -> None:
        pass

    def on_custom(self, kind: str, payload: tuple) -> None:
        pass

    @staticmethod
    def summary_text(job: Job, extra: str = "") -> str:
        text = f"{'تم الإيقاف' if job.cancelled else 'اكتمل'} خلال {job.elapsed:.1f} ثانية"
        if extra:
            text += f" — {extra}"
        if job.errors:
            text += f" — تم تخطي {job.errors:,} عنصر محمي"
        return text


class CallbackListener:
    """مستمع بسيط لمهمة جانبية (عندما تحتاج الصفحة أكثر من مهمة في نفس الوقت)."""

    def __init__(self, on_progress=None, on_finished=None, on_custom=None, parent=None):
        self.on_progress = on_progress
        self.on_finished = on_finished
        self.on_custom = on_custom
        self.parent = parent

    def on_job_event(self, job, kind, payload):
        if kind == "progress":
            if self.on_progress:
                self.on_progress(*payload)
        elif kind == "finished":
            result, error = payload
            if error:
                messagebox.showerror("حدث خطأ غير متوقع", error.strip().splitlines()[-1],
                                     parent=self.parent)
            if self.on_finished:
                self.on_finished(result, job)
        elif self.on_custom:
            self.on_custom(kind, payload)
