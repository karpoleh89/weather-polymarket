import logging
from collections import defaultdict
from datetime import date, timedelta, datetime, timezone
import numpy as np
import pandas as pd
from scipy import stats
import config

logger = logging.getLogger(__name__)


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
    col_to_model = {}
    for col in columns:
        for model in config.ENSEMBLE_MODELS:
            if model in col:
                col_to_model[col] = model
                break

    model_col_count = defaultdict(int)
    for model in col_to_model.values():
        model_col_count[model] += 1

    weights = {}
    for group_info in config.MODEL_GROUPS.values():
        group_models = group_info["models"]
        group_weight = group_info["weight"]
        n_models     = len(group_models)
        for model in group_models:
            n_cols = model_col_count.get(model, 0)
            if n_cols == 0:
                logger.warning("No members found for model '%s'", model)
                continue
            per_col_weight = group_weight / (n_models * n_cols)
            for col, m in col_to_model.items():
