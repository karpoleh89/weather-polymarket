# -*- coding: utf-8 -*-
import logging
from datetime import datetime, timedelta, timezone
import pandas as pd
import requests
import config

logger = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def get_actual_tmax_yesterday() -> dict | None:
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    params = {
        "latitude":         config.LONDON_LAT,
        "longitude":        config.LONDON_LON,
        "hourly":           "temperature_2m,cloud_cover",
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
        logger.error("Failed to fetch observations: %s", e)
        return None

    hourly = data.get("hourly", {})
    times  = hourly.get("time")
    temps  = hourly.get("temperature_2m")
    clouds = hourly.get("cloud_cover")

    if not times or not temps:
        return None

    idx     = pd.to_datetime(times, utc=True)
    temp_s  = pd.Series(temps, index=idx, dtype=float)
    cloud_s = pd.Series(clouds, index=idx, dtype=float) if clouds else None

    mask    = temp_s.index.date == yesterday
    daytime = temp_s[mask].between_time("06:00", "21:00")

    if daytime.empty:
        return None

    tmax_f = float(daytime.max())
    tmax_c = int(round((tmax_f - 32) / 1.8, 0))

    # Облачность только 10:00-17:00 (пик прогрева)
    cloud_label = "unknown"
    if cloud_s is not None:
        cloud_peak = cloud_s[mask].between_time("10:00", "17:00").dropna()
        if not cloud_peak.empty:
            mean_cloud  = float(cloud_peak.mean())
            cloud_label = _cloud_category(mean_cloud)
            logger.info("Yesterday cloud 10-17h: %.0f%% -> %s", mean_cloud, cloud_label)

    logger.info("Actual Tmax yesterday (%s): %.1f°F = %d°C [%s]",
                yesterday, tmax_f, tmax_c, cloud_label)

    return dict(
        date        = yesterday,
        tmax_f      = round(tmax_f, 1),
        tmax_c      = tmax_c,
        cloud_label = cloud_label,
    )


def get_current_conditions() -> dict:
    params = {
        "latitude":  config.LONDON_LAT,
        "longitude": config.LONDON_LON,
        "current":   "wind_direction_10m,cloud_cover",
        "timezone":  "GMT",
    }
    result = {"wind_deg": None, "cloud_label": "mixed", "cloud_pct": None}

    try:
        r = requests.get(FORECAST_URL, params=params, timeout=config.REQUEST_TIMEOUT_SEC)
        r.raise_for_status()
        current = r.json().get("current", {})

        wind_deg  = current.get("wind_direction_10m")
        cloud_pct = current.get("cloud_cover")

        if wind_deg is not None:
            result["wind_deg"] = float(wind_deg)
            logger.info("Wind: %.0f deg", wind_deg)

        if cloud_pct is not None:
            result["cloud_pct"] = float(cloud_pct)
            current_hour = datetime.now(timezone.utc).hour
            if 10 <= current_hour <= 17:
                result["cloud_label"] = _cloud_category(float(cloud_pct))
                logger.info("Cloud cover: %.0f%% -> %s", cloud_pct, result["cloud_label"])
            else:
                result["cloud_label"] = "mixed"
                logger.info("Outside peak hours (10-17 GMT) -> neutral 'mixed'")

    except Exception as e:
        logger.warning("Could not fetch current conditions: %s", e)

    return result


def _cloud_category(cloud_pct: float) -> str:
    if cloud_pct <= 30:
        return "clear"
    elif cloud_pct <= 70:
        return "mixed"
    else:
        return "overcast"
