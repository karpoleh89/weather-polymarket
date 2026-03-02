"""collector.py — Шаг 1: Сбор данных с Open-Meteo Ensemble API"""

import logging
import pandas as pd
import requests
import config

logger = logging.getLogger(__name__)


def fetch_ensemble() -> pd.DataFrame:
    """
    Returns
    -------
    pd.DataFrame
        index   : DatetimeIndex (UTC/GMT)
        columns : <model>_member<NN>  — температура °F
    """
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
    frames = []
    for model in config.ENSEMBLE_MODELS:
        if model not in data:
            logger.warning("Model '%s' missing — skip", model)
            continue
        hourly = data[model].get("hourly", {})
        times  = hourly.get("time")
        if not times:
            continue
        members = {k: v for k, v in hourly.items() if k != "time"}
        if not members:
            continue
        idx = pd.to_datetime(times, utc=True)
        renamed = {}
        for col, vals in members.items():
            suffix = col.replace("temperature_2m", "").lstrip("_")
            renamed[f"{model}_{suffix}" if suffix else model] = vals
        frames.append(pd.DataFrame(renamed, index=idx))
        logger.debug("'%s': %d members", model, len(renamed))

    if not frames:
        raise RuntimeError("No model data returned from API")

    df = pd.concat(frames, axis=1).sort_index()
    df.index.name = "datetime_gmt"
    df = df.apply(pd.to_numeric, errors="coerce")
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")
    df = fetch_ensemble()
    print(df.head(3).to_string())
    print(f"\n{df.shape[0]} rows x {df.shape[1]} columns")
    print(f"Period: {df.index[0]} -> {df.index[-1]}")
