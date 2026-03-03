# -*- coding: utf-8 -*-
import logging
import requests
import config
import processor

logger = logging.getLogger(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"


def send_report(results: list, actual_yesterday=None) -> None:
    text = _format_message(results, actual_yesterday)
    logger.info("Sending message to Telegram...")
    _send(text)


def _format_message(results: list, actual_yesterday=None) -> str:
    parts = []

    if actual_yesterday:
        d = actual_yesterday["date"].strftime("%d.%m.%Y")
        c = actual_yesterday["tmax_c"]
        f = actual_yesterday["tmax_f"]
        marker = " (Узко)" if c % 5 == 0 else ""
        parts.append(
            "\U0001f4cc *Факт вчера (" + d + "):*\n"
            "Tmax = " + str(c) + "\u00b0C / " + _fmt(f) + "\u00b0F" + marker
        )

    for r in results:
        d = r["date"].strftime("%d.%m.%Y")
        block = [
            "\U0001f4c5 *" + d + "*",
            "*Вероятность:*"
        ]

        for c, p in r["probs_c"].items():
            pct = p * 100
            if pct < 0.5:
                continue
            label = processor.market_label(c)
            block.append(str(c) + "\u00b0C \u2014 вероятность " + str(round(pct)) + "% (" + label + ")")

        block.append("")
        block.append("Mean(Tmax)=" + _fmt(r["mean_f"]) + "\u00b0F")
        block.append("Mode(Tmax)=" + _fmt(r["mode_f"]) + "\u00b0F")
        block.append("Median(Tmax)=" + _fmt(r["median_f"]) + "\u00b0F")

# Tmax по моделям для Bias Collection
        if r.get("group_tmax"):
            block.append("")
            block.append("*Tmax по моделям:*")
            for model_name, tmax_val in sorted(r["group_tmax"].items()):
                block.append(model_name + ": " + _fmt(tmax_val) + "\u00b0F")
```

---

Сообщение будет выглядеть так:
```
📅 03.03.2026
Вероятность:
11°C — вероятность 63% (Широко)
...

Mean(Tmax)=53°F
Mode(Tmax)=52°F
Median(Tmax)=52°F

Tmax по моделям:
ECMWF: 52.4°F
GFS: 55.1°F
ICON: 53.8°F
UKMO: 51.2°F

SD(Tmax) = 1.8°F ...
        
        sd_lbl = processor.sd_label(r["sd_f"])
        block.append("")
        block.append("SD(Tmax) = " + _fmt(r["sd_f"]) + "\u00b0F (" + sd_lbl + ")")
        block.append("68% вероятность = " + _fmt(r["sigma1_lo"]) + "-" + _fmt(r["sigma1_hi"]) + "\u00b0F")
        block.append("95% вероятность = " + _fmt(r["sigma2_lo"]) + "-" + _fmt(r["sigma2_hi"]) + "\u00b0F")

        sk_lbl = processor.skew_label(r["skew_f"])
        block.append("SKEW(Tmax) = " + _fmt(r["skew_f"]) + " (" + sk_lbl + ")")

        block.append("")
        block.append("*Confidence Score: " + str(r["confidence"]) + "/10*")
        block.append("Вердикт: " + r["verdict"])

        parts.append("\n".join(block))

    return "\n\n".join(parts)


def _fmt(val: float) -> str:
    return str(int(val)) if val == int(val) else str(round(val, 1))


def _send(text: str) -> None:
    payload = {
        "chat_id":    config.TELEGRAM_CHAT_ID,
        "text":       text,
        "parse_mode": "Markdown",
    }
    try:
        r = requests.post(TELEGRAM_API, json=payload, timeout=10)
        r.raise_for_status()
        logger.info("Message sent OK: %s", r.json().get("ok"))
    except requests.RequestException as e:
        logger.error("Failed to send Telegram message: %s", e)
        raise
