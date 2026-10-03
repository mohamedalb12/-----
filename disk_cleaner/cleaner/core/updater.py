"""
updater.py — البحث عن تحديثات التطبيقات (مثل Updater في CleanMyMac).

- تطبيقات App Store: نسأل خدمة Apple الرسمية (iTunes Lookup) عن آخر إصدار.
- تطبيقات تستخدم إطار Sparkle (أغلب التطبيقات خارج المتجر): نقرأ رابط التحديثات
  (SUFeedURL) من التطبيق نفسه ونقارن الإصدارات.
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .apps import AppInfo, list_apps
from .jobs import JobContext, NULL_CONTEXT

SPARKLE_NS = "http://www.andymatuschak.org/xml-namespaces/sparkle"
UA = "Disk Cleaner Pro (macOS app update check)"


@dataclass
class UpdateInfo:
    app: AppInfo
    current: str
    latest: str
    source: str          # "App Store" أو "Sparkle"
    url: str             # صفحة التحديث أو رابط التنزيل
    notes: str = ""


def _ssl_context():
    try:
        import certifi  # متوفر غالباً مع pip
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _fetch(url: str, timeout: float = 10) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r:
        return r.read(5_000_000)


def version_key(v: str) -> Tuple:
    """تحويل '2.10.3 (456)' إلى مفتاح مقارنة رقمي."""
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:6]) or (0,)


def is_newer(latest: str, current: str) -> bool:
    if not latest or not current:
        return False
    a, b = version_key(latest), version_key(current)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def _info_plist(app: AppInfo) -> dict:
    try:
        with open(os.path.join(app.path, "Contents", "Info.plist"), "rb") as f:
            return plistlib.load(f)
    except Exception:
        return {}


def _check_app_store(app: AppInfo) -> Optional[UpdateInfo]:
    url = "https://itunes.apple.com/lookup?" + urllib.parse.urlencode(
        {"bundleId": app.bundle_id, "entity": "macSoftware"})
    data = json.loads(_fetch(url))
    if not data.get("resultCount"):
        return None
    r = data["results"][0]
    latest = str(r.get("version", ""))
    if is_newer(latest, app.version):
        track = r.get("trackId")
        link = f"macappstore://apps.apple.com/app/id{track}" if track else "macappstore://showUpdatesPage"
        return UpdateInfo(app, app.version, latest, "App Store", link,
                          str(r.get("releaseNotes", ""))[:400])
    return None


def _check_sparkle(app: AppInfo, feed: str, build: str) -> Optional[UpdateInfo]:
    root = ET.fromstring(_fetch(feed))
    best: Optional[Tuple[Tuple, str, str, str, str]] = None
    for item in root.iter("item"):
        enc = item.find("enclosure")
        short = (item.findtext(f"{{{SPARKLE_NS}}}shortVersionString")
                 or (enc.get(f"{{{SPARKLE_NS}}}shortVersionString") if enc is not None else None) or "")
        ver = (item.findtext(f"{{{SPARKLE_NS}}}version")
               or (enc.get(f"{{{SPARKLE_NS}}}version") if enc is not None else None) or short)
        if not ver:
            continue
        link = (enc.get("url") if enc is not None else None) or item.findtext("link") or ""
        notes = re.sub(r"<[^>]+>", " ", item.findtext("description") or "").strip()[:400]
        key = version_key(ver)
        if best is None or key > best[0]:
            best = (key, short or ver, ver, link, notes)
    if not best:
        return None
    _key, short, ver, link, notes = best
    # نقارن الإصدار الظاهر للمستخدم أولاً (الأدق)، وإلا رقم البناء CFBundleVersion
    if short and app.version:
        newer = is_newer(short, app.version)
    else:
        newer = is_newer(ver, build)
    if newer:
        return UpdateInfo(app, app.version, short, "Sparkle", link, notes)
    return None


def check_app(app: AppInfo) -> Tuple[str, Optional[UpdateInfo], str]:
    """(حالة: store/sparkle/none/error، معلومات التحديث، رسالة)."""
    if app.is_system or not app.bundle_id:
        return "none", None, ""
    info = _info_plist(app)
    try:
        if os.path.exists(os.path.join(app.path, "Contents", "_MASReceipt")):
            return "store", _check_app_store(app), ""
        feed = info.get("SUFeedURL")
        if feed and str(feed).startswith("https://"):
            return "sparkle", _check_sparkle(app, str(feed), str(info.get("CFBundleVersion", ""))), ""
    except Exception as exc:
        return "error", None, str(exc)[:120]
    return "none", None, ""


def check_updates(ctx: JobContext = NULL_CONTEXT, apps: Optional[List[AppInfo]] = None):
    """يُرجع (التحديثات المتاحة، عدد التطبيقات التي أمكن فحصها، عدد التطبيقات الكلي)."""
    apps = apps if apps is not None else list_apps()
    updates: List[UpdateInfo] = []
    checked = 0
    done = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(check_app, a): a for a in apps}
        for fut in as_completed(futures):
            done += 1
            app = futures[fut]
            status, update, _msg = fut.result()
            if status in ("store", "sparkle"):
                checked += 1
            if update:
                updates.append(update)
                ctx.emit("update_found", update)
            ctx.progress(done / max(len(apps), 1), f"فحص {app.name}... ({done} من {len(apps)})")
            if ctx.cancelled:
                pool.shutdown(wait=False, cancel_futures=True)
                break
    updates.sort(key=lambda u: u.app.name.lower())
    return updates, checked, len(apps)
