"""collector.py — Шаг 1: Сбор данных с Open-Meteo Ensemble API"""

import logging
import pandas as pd
import requests
import config

logger = logging.getLogger(__name__)


def fetch_ensemble() -> pd.DataFrame:
    logger.info("Fetching ensemble data...")
    raw = _request_api()
    
    # Диагностика — логируем реальную структуру ответа
    logger.info("Top-level keys in response: %s", list(raw.keys()))
    for key in list(raw.keys())[:3]:
        val = raw[key]
        if isinstance(val, dict):
            logger.info("Key '%s' -> dict with keys: %s", key, list(val.keys())[:5])
        else:
            logger.info("Key '%s' -> type: %s, value: %s", key, type(val).__name__, str(val)[:100])
    
    df = _parse_response(raw)
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


def fetch_ensemble() -> pd.DataFrame:
    logger.info("Fetching ensemble data...")
    raw = _request_api()
    
    # Диагностика — логируем реальную структуру ответа
    logger.info("Top-level keys in response: %s", list(raw.keys()))
    for key in list(raw.keys())[:3]:
        val = raw[key]
        if isinstance(val, dict):
            logger.info("Key '%s' -> dict with keys: %s", key, list(val.keys())[:5])
        else:
            logger.info("Key '%s' -> type: %s, value: %s", key, type(val).__name__, str(val)[:100])
    
    df = _parse_response(raw)
    logger.info("Got %d rows x %d member columns", len(df), len(df.columns))
    return df
