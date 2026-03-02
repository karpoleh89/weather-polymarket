"""collector.py — Шаг 1: Сбор данных с Open-Meteo Ensemble API"""

import logging
import pandas as pd
import requests
import config

logger = logging.getLogger(__name__)


def fetch_ensemble() -> pd.DataFrame:
    logger.info("Fetching ensemble data...")
    raw = _request_api()
    df  = _parse_response(raw)
    logger.info("Got %d rows x %d member columns", len(df), len(df.columns))
    return df


def _request_api() -> dict:
    try:
        r = requests.get(
            config.ENSEMBLE_BASE_URL,
            params=config.ENSEMBLE_PARAMS,
            timeout=config.REQUEST_TIMEOUT_SEC,
        )
        r.raise_for_status()
    except requests.RequestException as e:
        logger.error("API error: %s", e)
        raise
    return r.json()


def _parse_response(data: dict) -> pd.DataFrame:
    """
    API возвращает единый объект hourly со всеми моделями внутри.
    Ключи выглядят так:
      temperature_2m_ecmwf_ifs025_ensemble_member01
      temperature_2m_ncep_gefs_seamless_member00
      ...
    Берём все колонки кроме 'time', называем их как есть.
    """
    hourly = data.get("hourly", {})
    times  = hourly.get("time")

    if not times:
        raise RuntimeError("No 'time' field in API response")

    idx = pd.to_datetime(times, utc=True)

    # Логируем первые колонки для диагностики
    all_cols = [k for k in hourly.keys() if k != "time"]
    logger.info("Hourly columns count: %d", len(all_cols))
    logger.info("First 5 columns: %s", all_cols[:5])

    if not all_cols:
        raise RuntimeError("No temperature columns in API response")

    df = pd.DataFrame(
        {col: hourly[col] for col in all_cols},
        index=idx
    )
    df.index.name = "datetime_gmt"
    df = df.apply(pd.to_numeric, errors="coerce")
    return df


if __name__ == "__main__":
    logging.b
