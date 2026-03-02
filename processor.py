"""processor.py — Шаг 2: Обработка данных"""

import logging
from collections import defaultdict
from datetime import date, timedelta, datetime, timezone
from typing import TypedDict

import numpy as np
import pandas as pd
from scipy import stats

import config

logger = logging.getLogger(__name__)


class DayStats(TypedDict):
    date:      date
    probs_c:   dict
    mean_f:    float
    mode_f:    float
    median_f:  float
    sd_f:      float
    skew_f:    float
    sigma1_lo: float
    sigma1_hi: float
    sigma2_lo: float
    sigma2_hi: float


def process(df: pd.DataFrame) -> list:
    today    = datetime.now(timezone.utc).date()
    tomorrow = today + timedelta(days=1)
    weights  = _build_weights(df.columns.tolist())
    results  = []
    for target_date in (today, tomorrow):
        day_df = df[df.index.date == target_date]
        if day_df.empty:
            logger.warning("No data for %s", target_date)
            continue
        results.append(_compute_day(day_df, target_date, weights))
    return results


def _build_weights(columns: list) -> dict:
    """
    Колонки имеют формат:
      temperature_2m_<model>                    (детерминированный член)
      temperature_2m_member01_<model>           (член ансамбля)
    
    Определяем модель по тому, какой из ENSEMBLE_MODELS
    содержится в имени колонки.
    """
    # Сопоставляем каждую колонку с моделью
    col_to_model: dict[str, str] = {}
    for col in columns:
        for model in config.ENSEMBLE_MODELS:
            if model in col:
                col_to_model[col] = model
                break

    # Считаем кол-во колонок на модель
    model_col_count: dict[str, int] = defaultdict(int)
    for model in col_to_model.values():
        model_col_count[model] += 1

    # Вес каждой колонки = вес_группы / (
