# -*- coding: utf-8 -*-
import logging
import requests
import config
import processor

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot" + config.TELEGRAM_BOT_TOKEN + "/sendMessage"


def send_report(results: list, actual_yesterday=None, conditions=None) -> None:
    text = _format_message(results, actual_yesterday, conditions)
    logger.info("Sending message to Telegram...")
    _send(text)


def _format_message(results: list, actual_yesterday=None, conditions=None) -> str:
    parts = []

    # Текущие условия
    if conditions:
        cloud_labels = {
            "clear":    "\u2600\ufe0f Ясно",
            "mixed":    "\u26c5 Переменная облачность",
            "overcast": "\u2601\ufe0f Пасмурно",
            "unknown":  "Облачность неизвестна",
        }
        wind_deg   = conditions.get("wind_deg")
        cloud_pct  = conditions.get("cloud_pct")
        cloud_lbl  = cloud_labels.get(conditions.get("cloud_label", "unknown"), "")
        cloud_pct_str = (" (" + str(round(cloud_pct)) + "%)") if cloud_pct is not None else ""
        wind_str   = _wind_direction(wind_deg) if wind_deg is not None else "н/д"
        bias_active = _bias_active_str(conditions.get("cloud_label", "unknown"))

        parts.append(
            "\U0001f321 *Текущие условия:*\n"
            + cloud_lbl + cloud_pct_str + "\n"
            + "Ветер: " + wind_str + "\n"
            + bias_active
        )

    # Факт вчера
    if actual_yesterday:
        d      = actual_yesterday["date"].strftime("%d.%m.%Y")
        c      = actual_yesterday["tmax_c"]
        f      = actual_yesterday["tmax_f"]
        marker = " (Узко)" if c % 5 == 0 else ""
        cl     = actual_yesterday.get("cloud_label", "unknown")
        cl_ru  = {"clear": "ясно", "mixed": "переменно", "overcast": "пасмурно"}.get(cl, "")
        cl_str = (" [" + cl_ru + "]") if cl_ru else ""
        parts.append(
            "\U0001f4cc *Факт вчера (" + d + "):*\n"
            "Tmax = " + str(c) + "\u00b0C / " + _fmt(f) + "\u00b0F" + marker + cl_str
        )

    # Прогноз по дням
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
            block.append(
                str(c) + "\u00b0C \u2014 вероятность "
                + str(round(pct)) + "% (" + label + ")"
            )

        block.append("")
        block.append("Mean(Tmax)=" + _fmt(r["mean_f"]) + "\u00b0F")
        block.append("Mode(Tmax)=" + _fmt(r["mode_f"]) + "\u00b0F")
        block.append("Median(Tmax)=" + _fmt(r["median_f"]) + "\u00b0F")

        if r.get("group_tmax"):
            block.append("")
            block.append("*Tmax по моделям:*")
            for model_name, tmax_val in sorted(r["group_tmax"].items()):
                block.append(model_name + ": " + _fmt(tmax_val) + "\u00b0F")

        sd_lbl = processor.sd_label(r["sd_f"])
        block.append("")
        block.append("SD(Tmax) = " + _fmt(r["sd_f"]) + "\u00b0F (" + sd_lbl + ")")
        block.append("68% \u2014 " + _fmt(r["sigma1_lo"]) + "-" + _fmt(r["sigma1_hi"]) + "\u00b0F")
        block.append("95% \u2014 " + _fmt(r["sigma2_lo"]) + "-" + _fmt(r["sigma2_hi"]) + "\u00b0F")

        sk_lbl = processor.skew_label(r["skew_f"])
        block.append("SKEW(Tmax) = " + _fmt(r["skew_f"]) + " (" + sk_lbl + ")")

        block.append("")
        block.append("*Confidence Score: " + str(r["confidence"]) + "/10*")
        block.append("Вердикт: " + r["verdict"])

        parts.append("\n".join(block))

    return "\n\n".join(parts)


def _wind_direction(deg: float) -> str:
    directions = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"]
    idx = round(deg / 45) % 8
    return directions[idx] + " (" + str(round(deg)) + "\u00b0)"


def _bias_active_str(cloud_label: str) -> str:
    import config
    bias = config.BIAS_CORRECTION.get(cloud_label, {})
    if any(v != 0.0 for v in bias.values()):
        return "Bias коррекция: \u2705 активна [" + cloud_label + "]"
    return "Bias коррекция: \u23f3 накапливаем данные"


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
