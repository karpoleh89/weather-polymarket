import logging
import requests
import config
import processor

logger = logging.getLogger(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"


def send_report(results: list) -> None:
    text = _format_message(results)
    logger.info("Sending message to Telegram...")
    _send(text)


def _format_message(results: list) -> str:
    parts = []
    for r in results:
        d = r["date"].strftime("%d.%m.%Y")
        block = [f"📅 *{d}*", "*Вероятность:*"]

        for c, p in r["probs_c"].items():
            pct = p * 100
            if pct < 0.5:
                continue
            label = processor.market_label(c)
            block.append(f"{c}°C — вероятность {pct:.0f}% ({label})")

        block.append("")
        block.append(f"Mean(Tmax)={_fmt(r['mean_f'])}°F")
        block.append(f"Mode(Tmax)={_fmt(r['mode_f'])}°F")
        block.append(f"Median(Tmax)={_fmt(r['median_f'])}°F")

        sd_lbl = processor.sd_label(r["sd_f"])
        block.append("")
        block.append(f"SD(Tmax) = {_fmt(r['sd_f'])}°F ({sd_lbl})")
        block.append(f"68% вероятность = {_fmt(r['sigma1_lo'])}-{_fmt(r['sigma1_hi'])}°F")
        block.append(f"95% вероятность = {_fmt(r['sigma2_lo'])}-{_fmt(r['sigma2_hi'])}°F")

        sk_lbl = processor.skew_label(r["skew_f"])
        block.append(f"SKEW(Tmax) = {_fmt(r['skew_f'])} ({sk_lbl})")

        # Confidence Score
        block.append("")
        block.append(f"*Confidence Score: {r['confidence']}/10*")
        block.append(f"Вердикт: {r['verdict']}")

        parts.append("\n".join(block))

    return "\n\n".join(parts)
```

---

## Как будет выглядеть сообщение
```
📅 03.03.2026
Вероятность:
11°C — вероятность 63% (Широко)
12°C — вероятность 24% (Широко)
...

Mean(Tmax)=53°F
Mode(Tmax)=53°F
Median(Tmax)=52°F

SD(Tmax) = 1.8°F (Умеренный спред)
68% вероятность = 51.2-54.8°F
95% вероятность = 49.4-56.6°F
SKEW(Tmax) = 0.8 (Умеренное справа)

Confidence Score: 7/10
Вердикт: 🟡 РИСК (Нужен хедж)


def _fmt(val: float) -> str:
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
        logger.info("Message sent OK: %s", r.json().get("ok"))
    except requests.RequestException as e:
        logger.error("Failed to send Telegram message: %s", e)
        raise
