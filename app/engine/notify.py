"""Notifications — Telegram (raw httpx to the Bot API) + native Windows toast
(winotify). Both channels are gated by persistent settings:
``notifications_enabled`` master switch, then ``telegram_enabled`` /
``toast_enabled`` per channel, and ``notify_new_lows`` / ``notify_drops`` per
event type. Ported from the homelab notifier's R$/kg branch."""
from __future__ import annotations

import logging

import httpx

from . import config

log = logging.getLogger(__name__)

SITE_NAMES = {"samsclub": "Sam's Club", "swift": "Swift", "superadega": "Superadega"}


def _format_brl2(value: float) -> str:
    """39.9 -> 'R$ 39,90'."""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _listing_lines(listing: dict, kind: str) -> tuple[str, str]:
    """Return (telegram_html, toast_plain) for a listing notification."""
    site = SITE_NAMES.get(listing["site"], listing["site"])
    family = listing.get("model_family") or listing.get("title", "")[:40]
    title = (listing.get("title") or "")[:80]
    ppk = listing.get("price_per_kg") or 0
    kg = f"{_format_brl2(ppk)}/kg"
    pkg = _format_brl2(listing.get("price") or 0)

    if kind == "new_low":
        head_tg = f"🥩 <b>{family}</b> — 🔥 nova mínima!\n  {kg}"
        head_toast = f"🔥 Nova mínima: {family} — {kg}"
    elif kind == "new":
        head_tg = f"🥩 <b>{family}</b> — 🆕 novo\n  {kg}"
        head_toast = f"🆕 {family} — {kg}"
    else:  # drop
        old_price = listing.get("old_price")
        price = listing.get("price") or 0
        old_ppk = old_price * ppk / price if old_price and price else None
        if old_ppk:
            pct = ((old_ppk - ppk) / old_ppk * 100) if old_ppk > 0 else 0
            head_tg = (f"🥩 <b>{family}</b> — 📉 caiu!\n"
                       f"  {_format_brl2(old_ppk)}/kg → {kg} (-{pct:.0f}%)")
            head_toast = f"📉 {family}: {_format_brl2(old_ppk)}/kg → {kg}"
        else:
            head_tg = f"🥩 <b>{family}</b> — 📉 caiu!\n  {kg}"
            head_toast = f"📉 {family} — {kg}"

    tg = (f"{head_tg}\n📦 {pkg} (pacote) · 🏪 {site}\n📝 {title}")
    url = listing.get("url")
    if url:
        tg += f'\n\n<a href="{url}">Ver produto</a>'
    toast = f"{head_toast}\n{site} · {pkg} (pacote)"
    return tg, toast


async def _send_telegram(text: str, settings: dict) -> None:
    token = (settings.get("telegram_token") or "").strip()
    chat_id = str(settings.get("telegram_chat_id") or "").strip()
    if not token or not chat_id:
        log.info("Telegram not configured; skipping send")
        return
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": True},
            )
            if resp.status_code != 200:
                log.warning("Telegram send failed %d: %s", resp.status_code, resp.text[:200])
    except Exception as e:
        log.error("Telegram send error: %s", e)


def _send_toast(title: str, message: str) -> None:
    try:
        from winotify import Notification  # Windows only
    except Exception:
        log.debug("winotify unavailable (non-Windows or not installed)")
        return
    try:
        Notification(app_id="Rastreador de Preços", title=title,
                     msg=message, duration="short").show()
    except Exception as e:
        log.error("Toast error: %s", e)


async def dispatch(result, settings: dict | None = None) -> int:
    """Send notifications for a ScanResult, honouring all toggles. Returns the
    number of notifications sent (0 if notifications are disabled)."""
    settings = settings or config.load_settings()
    if not settings.get("notifications_enabled", True):
        return 0

    tg_on = settings.get("telegram_enabled", True)
    toast_on = settings.get("toast_enabled", True)
    cap = int(settings.get("max_notif_per_scan", 20))

    events: list[tuple[dict, str]] = []
    if settings.get("notify_new_lows", True):
        events += [(r, "new_low") for r in result.new_lows]
    if settings.get("notify_drops", True):
        events += [(r, "drop") for r in result.drops]
    events = events[:cap]

    sent = 0
    for listing, kind in events:
        tg, toast = _listing_lines(listing, kind)
        if tg_on:
            await _send_telegram(tg, settings)
        if toast_on:
            title, _, body = toast.partition("\n")
            _send_toast(title, body or title)
        sent += 1
    return sent


async def send_test(settings: dict) -> str:
    """Fire a test notification through the enabled channels. Returns a status."""
    msgs = []
    if settings.get("telegram_enabled", True):
        await _send_telegram("✅ <b>Rastreador de Preços</b>\nTeste de notificação Telegram.",
                             settings)
        msgs.append("Telegram")
    if settings.get("toast_enabled", True):
        _send_toast("Rastreador de Preços", "Teste de notificação (toast).")
        msgs.append("Toast")
    return "Enviado: " + ", ".join(msgs) if msgs else "Nenhum canal habilitado"
