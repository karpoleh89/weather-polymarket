# -*- coding: utf-8 -*-
"""
observer.py — Фактические наблюдения Tmax с Open-Meteo
Используем forecast API (не ensemble) — он содержит реальные данные за прошлое
"""

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

import config

logger = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def get_actual_tmax_yesterday() -> dict | None:
    """
    Возвращает фактический Tmax за вчера в °F и °C.

    Returns
    -------
    dict с ключами:
        date      : date вчерашнего дня
        tmax_f    : float — Tmax °F (06:00-21:00 GMT)
        tmax_c    : int   — Tmax Wunder °C
    None если данные недоступны.
    """
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    params = {
        "latitude":         config.LONDON_LAT,
        "longitude":        config.LONDON_LON,
        "hourly":           "temperature_2m",
        "timezone":         "GMT",
        "past_days":        2,
        "forecast_days":    1,
        "temperature_unit": "fahrenheit",
    }

    try:
        r = requests.get(FORECAST_URL, params=params, timeout=config.REQUEST_TIMEOUT_SEC)
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        logger.error("Failed to fetch actual observations: %s", e)
        return None

    hourly = data.get("hourly", {})
    times  = hourly.get("time")
    temps  = hourly.get("temperature_2m")

    if not times or not temps:
        logger.warning("No observation data in response")
        return None

    # Строим Series с временным индексом
    idx = pd.to_datetime(times, utc=True)
    series = pd.Series(temps, index=idx, dtype=float)

    # Фильтруем вчерашний день + дневные часы 06:00-21:00
    yesterday_series = series[series.index.date == yesterday]
    daytime = yesterday_series.between_time("06:00", "21:00")

    if daytime.empty:
        logger.warning("No daytime observations for %s", yesterday)
        return None

    tmax_f = float(daytime.max())
    tmax_c = int(round((tmax_f - 32) / 1.8, 0))

    logger.info("Actual Tmax yesterday (%s): %.1f°F = %d°C", yesterday, tmax_f, tmax_c)

    return dict(
        date   = yesterday,
        tmax_f = round(tmax_f, 1),
        tmax_c = tmax_c,
    )
