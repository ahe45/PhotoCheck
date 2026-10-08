"""Explicit local diagnostic for sample folders; never invoked by normal startup."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path


def process_memory():
    if os.name != "nt":
        return {}
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD),
                    ("peak", ctypes.c_size_t), ("working", ctypes.c_size_t),
                    ("peak_paged", ctypes.c_size_t), ("paged", ctypes.c_size_t),
                    ("peak_nonpaged", ctypes.c_size_t), ("nonpaged", ctypes.c_size_t),
                    ("pagefile", ctypes.c_size_t), ("peak_pagefile", ctypes.c_size_t)]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    memory_info = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
    memory_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    memory_info.restype = wintypes.BOOL
    if memory_info(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        return {"working_mb": round(counters.working / 1048576, 1), "peak_mb": round(counters.peak / 1048576, 1)}
    return {}


def run(folder, report_path, limit=0):
    from PIL import Image
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    from .domain import Status
    from .export import export_excel
    from .files import collect
    from .ui import MainWindow
    from .theme import apply_light_theme

    root, output = Path(folder).resolve(), Path(report_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    progress_path = output.with_suffix(".progress.json")
    start = time.perf_counter()
    paths = collect(root, True).paths
    if limit:
        paths = paths[:limit]
    hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    app = QApplication.instance() or QApplication([])
    apply_light_theme(app)
    window = MainWindow()
    window.folder.setText(str(root))
    window.show()
    if limit:
        # Restrict discovery in this diagnostic process only, preserving the UI pipeline.
        import photocheck.workers as workers
        original_collect = workers.collect
        def limited_collect(*args):
            result = original_collect(*args)
            result.paths = result.paths[:limit]
            return result
        workers.collect = limited_collect
    window.start_scan()
    loop = QEventLoop()
    ticks = []
    last_tick = time.perf_counter()
    last_progress = 0

    def tick():
        nonlocal last_tick, last_progress
        now = time.perf_counter()
        ticks.append(now - last_tick)
        last_tick = now
        if now - last_progress >= 5:
            info = {"total": window.total, "processed": len(window.results),
                    "elapsed_seconds": round(now - start, 1),
                    "counts": dict(window.counts), "memory": process_memory()}
            progress_path.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
            last_progress = now

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(250)
    window.worker.finished.connect(loop.quit)
    loop.exec()
    timer.stop()
    seconds = time.perf_counter() - start
    report = {"ok": len(window.results) == len(paths), "frozen": bool(getattr(sys, "frozen", False)),
              "total": window.total, "processed": len(window.results), "elapsed_seconds": round(seconds, 2),
              "counts": dict(window.counts), "excluded": window.excluded,
              "discovery_issues": window.discovery_issues, "memory": process_memory(),
              "gui_timer_max_delay_seconds": round(max(ticks, default=0), 3),
              "gui_timer_median_delay_seconds": round(statistics.median(ticks), 3) if ticks else None,
              "model_versions": sorted({r.model_version for r in window.results}),
              "criteria_versions": sorted({r.criteria_version for r in window.results})}
    reasons = Counter(reason for r in window.results for reason in r.reasons)
    report["reason_counts"] = dict(reasons.most_common())
    report["tag_counts"] = dict(Counter(tag for r in window.results for tag in r.tags))
    report["analysis_exceptions"] = [r.relative_path for r in window.results if any("분석 실패" in reason for reason in r.reasons)]
    report["normal_files"] = [r.relative_path for r in window.results if r.status == Status.NORMAL]
    report["originals_unchanged"] = all(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest for name, digest in hashes.items())
    report["ui_checks"] = {}
    if window.proxy.rowCount():
        window.table.selectRow(0)
        window.pool.waitForDone()
        app.processEvents()
        report["ui_checks"]["preview"] = window.view.photo is not None
        window.move(1)
        report["ui_checks"]["navigation"] = window.table.currentIndex().row() == min(1, window.proxy.rowCount() - 1)
        first = window.model.rows[0].path.name
        window.search.setText(first)
        report["ui_checks"]["filename_search"] = window.proxy.rowCount() >= 1
        window.reason_filter.setCurrentText("파일")
        report["ui_checks"]["empty_filter_clears_preview"] = window.proxy.rowCount() != 0 or window.current is None
        window.search.clear()
        window.reason_filter.setCurrentIndex(0)
    report["ok"] = report["ok"] and report["originals_unchanged"] and not report["analysis_exceptions"]
    report['exported_review_count'] = export_excel(output.with_suffix(".xlsx"), window.results)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    window.close()
    if sys.stdout:
        print(json.dumps({k: report[k] for k in ("ok", "total", "processed", "counts", "elapsed_seconds", "memory", "originals_unchanged", "ui_checks")}, ensure_ascii=False))
    return 0 if report["ok"] else 1
