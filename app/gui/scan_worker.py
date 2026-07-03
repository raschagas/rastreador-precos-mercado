"""Background scan worker — runs the async scan + notification dispatch off the
Qt UI thread and reports back via signals."""
from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import QThread, Signal

from engine import notify
from engine.scanner import run_scan

log = logging.getLogger(__name__)


class ScanWorker(QThread):
    finished_ok = Signal(object, int)   # (ScanResult, notifications_sent)
    failed = Signal(str)

    def run(self) -> None:  # noqa: D401 - QThread entrypoint
        try:
            async def _job():
                result = await run_scan()
                sent = await notify.dispatch(result)
                return result, sent
            result, sent = asyncio.run(_job())
            self.finished_ok.emit(result, sent)
        except Exception as e:  # never let the thread die silently
            log.exception("Scan worker failed")
            self.failed.emit(str(e))
