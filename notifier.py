"""notifier.py — Шаг 3: Форматирование и отправка в Telegram"""

import logging
import requests

import config
import processor

logger = logging.getLogger(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"


def send_report(results: list[processor.DayStats]) -> None:
    """Форматирует и отправляет сообщение в Telegram."""
    text = _format_message(results)
    logger.info("Sending message to Telegram...")
    _send(text)


def _format_message(results: list[processor.DayStats]) -> str:
    parts = []
    for r in results:
        d = r["date"].strftime("%d.%m.%Y")
        block = [f"📅 *{d}*"]

        # Вероятности °C (только где > 0%)
        block.append("*Вероятность:*")
        for c, p in r["probs_c"].items():
            pct  = p * 100
            if pct < 0.5:
                continue  # отсекаем шум
            label = processor.market_label(c)
            block.append(f"{c}°C — вероятность {pct:.0f}% ({label})")

        # Mean / Mode / Median
        block.append("")
        block.append(f"Mean(Tmax)={_fmt(r['mean_f'])}°F")
        block.append(f"Mode(Tmax)={_fmt(r['mode_f'])}°F")
        block.append(f"Median(Tmax)={_fmt(r['median_f'])}°F")

        # SD
        sd_lbl = processor.sd_label(r["sd_f"])
        block.append("")
        block.append(f"SD(Tmax) = {_fmt(r['sd_f'])}°F ({sd_lbl})")
        block.append(f"68% вероятность = {_fmt(r['sigma1_lo'])}-{_fmt(r['sigma1_hi'])}°F")
        block.append(f"95% вероятность = {_fmt(r['sigma2_lo'])}-{_fmt(r['sigma2_hi'])}°F")

        # Skew
        sk_lbl = processor.skew_label(r["skew_f"])
        block.append(f"SKEW(Tmax) = {_fmt(r['skew_f'])} ({sk_lbl})")

        parts.append("\n".join(block))

    return "\n\n".join(parts)


def _fmt(val: float) -> str:
    """Форматирует число: целое если .0, иначе одна десятичная."""
    return str(int(val)) if val == int(val) else f"{val:.1f}"


def _send(text: str) -> None:
    payload = {
        "chat_id":    config.TELEGRAM_CHAT_ID,
        "text":       text,
        "parse_mode": "Markdown",
    }
    try:
        r = requests.post(TELEGRAM_API, json=payload, timeout=10)
        r.raise_for_status()
        logger.info("Message sent. Response: %s", r.json().get("ok"))
    except requests.RequestException as e:
        logger.error("Failed to send Telegram message: %s", e)
        raise
