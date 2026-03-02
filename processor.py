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
                if m == model:
                    weights[col] = per_col_weight

    total = sum(weights.values())
    if total == 0:
        raise RuntimeError("Weights sum to zero")
    weights = {k: v / total for k, v in weights.items()}
    logger.info("Weights built: %d columns", len(weights))
    return weights


def _f_to_wunder_c(f_val: float) -> int:
    return int(round((f_val - 32) / 1.8, 0))


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    idx = np.argsort(values)
    sv, sw = values[idx], weights[idx]
    cumw = np.cumsum(sw)
    return float(sv[np.searchsorted(cumw, 0.5)])


def _weighted_skew(values: np.ndarray, weights: np.ndarray, mean: float, sd: float) -> float:
    if sd == 0:
        return 0.0
    return float(np.average(((values - mean) / sd) ** 3, weights=weights))


def _compute_day(day_df: pd.DataFrame, target: date, weights: dict) -> dict:
    tmax_raw = {}
    for col in day_df.columns:
        s = day_df[col].dropna()
        if not s.empty:
            tmax_raw[col] = s.max()

    if not tmax_raw:
        raise RuntimeError(f"No valid Tmax for {target}")

    tmax_int = {col: round(v) for col, v in tmax_raw.items()}
    tmax_c   = {col: _f_to_wunder_c(v) for col, v in tmax_int.items()}

    probs_raw = defaultdict(float)
    for col, c_val in tmax_c.items():
        probs_raw[c_val] += weights.get(col, 0.0)
    total_w = sum(probs_raw.values())
    probs_c = {c: w / total_w for c, w in sorted(probs_raw.items())} if total_w > 0 else {}

    cols_w = [(col, weights.get(col, 0.0)) for col in tmax_raw if col in weights]
    if not cols_w:
        raise RuntimeError(f"No weighted columns for {target}")

    f_vals = np.array([tmax_raw[col] for col, _ in cols_w])
    w_vals = np.array([w for _, w in cols_w])
    w_vals = w_vals / w_vals.sum()

    mean_f   = float(np.average(f_vals, weights=w_vals))
    sd_f     = float(np.sqrt(np.average((f_vals - mean_f) ** 2, weights=w_vals)))
    median_f = float(_weighted_median(f_vals, w_vals))
    skew_f   = float(_weighted_skew(f_vals, w_vals, mean_f, sd_f))
    mode_f   = float(stats.mode(np.array([tmax_int[col] for col in tmax_raw]), keepdims=True).mode[0])

    return dict(
        date      = target,
        probs_c   = probs_c,
        mean_f    = round(mean_f, 1),
        mode_f    = mode_f,
        median_f  = round(median_f, 1),
        sd_f      = round(sd_f, 1),
        skew_f    = round(skew_f, 2),
        sigma1_lo = round(mean_f - sd_f, 1),
        sigma1_hi = round(mean_f + sd_f, 1),
        sigma2_lo = round(mean_f - 2 * sd_f, 1),
        sigma2_hi = round(mean_f + 2 * sd_f, 1),
    )


def sd_label(sd: float) -> str:
    if sd < 0.8:      return "БЕТОН"
    elif sd <= 1.5:   return "Консолидация"
    elif sd <= 2.5:   return "Умеренный спред"
    elif sd <= 4.0:   return "Широкий спред"
    else:             return "Спагетти!!!"


def skew_label(skew: float) -> str:
    if -0.5 <= skew <= 0.5:    return "Симметричное"
    elif 0.5 < skew <= 1.0:    return "Умеренное справа"
    elif skew > 1.0:            return "Сильное справа"
    elif -1.0 <= skew < -0.5:  return "Умеренное слева"
    else:                       return "Сильное слева"


def market_label(c: int) -> str:
    return "Узко" if c % 5 == 0 else "Широко"

def confidence_score(sd: float, skew: float, mean_f: float) -> int:
    """
    Индекс уверенности 0-10.
    Старт: 10 баллов, вычитаем штрафы, добавляем бонусы.
    """
    score = 10

    # Штраф за разброс
    if sd > 2.5:
        score -= 6
    elif sd > 1.5:
        score -= 3

    # Штраф за асимметрию
    if abs(skew) > 1.0:
        score -= 2

    # Штраф за «узкое окно» — если mean в °C кратно 5
    mean_c = _f_to_wunder_c(mean_f)
    if mean_c % 5 == 0:
        score -= 2

    return max(0, min(10, score))


def confidence_score_with_bonus(sd: float, skew: float, mean_f: float, mode_f: float) -> int:
    """
    То же что confidence_score, но с бонусом за консенсус Mean==Mode.
    """
    score = confidence_score(sd, skew, mean_f)

    # Бонус за консенсус: ROUND(mean) °C == ROUND(mode) °C
    mean_c = _f_to_wunder_c(mean_f)
    mode_c = _f_to_wunder_c(mode_f)
    if mean_c == mode_c:
        score += 2

    return max(0, min(10, score))


def verdict_label(sd: float, skew: float) -> str:
    """
    Вердикт по логике IFS из Google Sheets.
    Приоритет сверху вниз.
    """
    if sd < 1.1:
        return "💎 БЕТОН (Входи крупно)"
    elif sd < 1.8 and abs(skew) < 0.7:
        return "✅ СИГНАЛ (Стандартный риск)"
    elif sd > 2.5 or abs(skew) > 1.5:
        return "⚠️ ЛОТЕРЕЯ (Только копейки)"
    elif sd >= 1.8:
        return "🟡 РИСК (Нужен хедж)"
    else:
        return "🔍 АНАЛИЗИРУЙ РУКАМИ"
