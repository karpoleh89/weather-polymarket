"""
processor.py — Шаг 2: Обработка данных

Для каждого дня (сегодня / завтра GMT) вычисляет:
  - Взвешенные вероятности Tmax в Wunder °C
  - Mean, Mode, Median, SD, Skew Tmax в °F
  - Правило 3 сигм
"""

import logging
from collections import defaultdict
from datetime import date, timedelta, datetime, timezone
from typing import TypedDict

import numpy as np
import pandas as pd
from scipy import stats

import config

logger = logging.getLogger(__name__)


# ── Типы ─────────────────────────────────────────────────────────────────────

class DayStats(TypedDict):
    date:           date
    probs_c:        dict[int, float]   # {celsius: probability 0..1}
    mean_f:         float
    mode_f:         float
    median_f:       float
    sd_f:           float
    skew_f:         float
    sigma1_lo:      float              # mean - 1sd
    sigma1_hi:      float              # mean + 1sd
    sigma2_lo:      float              # mean - 2sd
    sigma2_hi:      float              # mean + 2sd


# ── Публичный интерфейс ───────────────────────────────────────────────────────

def process(df: pd.DataFrame) -> list[DayStats]:
    """
    Parameters
    ----------
    df : DataFrame из collector.fetch_ensemble()

    Returns
    -------
    list of DayStats — [сегодня, завтра]
    """
    today    = datetime.now(timezone.utc).date()
    tomorrow = today + timedelta(days=1)
    results  = []

    weights = _build_weights(df.columns.tolist())

    for target_date in (today, tomorrow):
        day_df = _filter_day(df, target_date)
        if day_df.empty:
            logger.warning("No data for %s", target_date)
            continue
        stats_obj = _compute_day(day_df, target_date, weights)
        results.append(stats_obj)

    return results


# ── Вспомогательные функции ───────────────────────────────────────────────────

def _build_weights(columns: list[str]) -> dict[str, float]:
    """
    Вычисляет вес каждой колонки-члена.

    Алгоритм:
      1. Определяем, к какой группе принадлежит колонка (по префиксу модели).
      2. Вес группы делим на (кол-во моделей в группе × кол-во членов каждой модели).
    """
    # Шаг 1: считаем членов для каждой модели
    model_members: dict[str, list[str]] = defaultdict(list)
    for col in columns:
        for model in config.ENSEMBLE_MODELS:
            if col.startswith(model):
                model_members[model].append(col)
                break

    weights: dict[str, float] = {}

    for group_info in config.MODEL_GROUPS.values():
        group_models = group_info["models"]
        group_weight = group_info["weight"]
        n_models     = len(group_models)

        for model in group_models:
            members = model_members.get(model, [])
            if not members:
                logger.warning("No members found for model '%s'", model)
                continue
            per_member_weight = group_weight / (n_models * len(members))
            for col in members:
                weights[col] = per_member_weight

    # Нормализуем (на случай если какая-то модель недоступна)
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}

    logger.debug("Weights built for %d members, total=%.4f", len(weights), sum(weights.values()))
    return weights


def _filter_day(df: pd.DataFrame, target: date) -> pd.DataFrame:
    """Оставляет только строки за нужный день (GMT)."""
    mask = df.index.date == target
    return df.loc[mask]


def _f_to_wunder_c(f_val: float) -> int:
    """Перевод °F → Wunder °C: ROUND((F-32)/1.8, 0)."""
    return int(round((f_val - 32) / 1.8, 0))


def _sd_label(sd: float) -> str:
    if sd < 0.8:
        return "БЕТОН"
    elif sd <= 1.5:
        return "Консолидация"
    elif sd <= 2.5:
        return "Умеренный спред"
    elif sd <= 4.0:
        return "Широкий спред"
    else:
        return "Спагетти!!!"


def _skew_label(skew: float) -> str:
    if -0.5 <= skew <= 0.5:
        return "Симметричное"
    elif 0.5 < skew <= 1.0:
        return "Умеренное справа"
    elif skew > 1.0:
        return "Сильное справа"
    elif -1.0 <= skew < -0.5:
        return "Умеренное слева"
    else:
        return "Сильное слева"


def _market_label(c: int) -> str:
    """Узко если кратно 5, иначе Широко."""
    return "Узко" if c % 5 == 0 else "Широко"


def _compute_day(day_df: pd.DataFrame, target: date, weights: dict[str, float]) -> DayStats:
    """Вычисляет все статистики за один день."""

    # ── 1. Tmax каждого члена (°F integer) ───────────────────────────────────
    tmax_f_raw: dict[str, float] = {}
    for col in day_df.columns:
        series = day_df[col].dropna()
        if not series.empty:
            tmax_f_raw[col] = series.max()

    if not tmax_f_raw:
        raise RuntimeError(f"No valid Tmax values for {target}")

    # ── 2. Round Tmax °F → int ────────────────────────────────────────────────
    tmax_f_int: dict[str, int] = {col: round(v) for col, v in tmax_f_raw.items()}

    # ── 3. Конвертируем в Wunder °C ───────────────────────────────────────────
    tmax_c: dict[str, int] = {col: _f_to_wunder_c(v) for col, v in tmax_f_int.items()}

    # ── 4. Взвешенные вероятности по °C ──────────────────────────────────────
    probs_raw: dict[int, float] = defaultdict(float)
    for col, c_val in tmax_c.items():
        w = weights.get(col, 0.0)
        probs_raw[c_val] += w

    total_w = sum(probs_raw.values())
    probs_c: dict[int, float] = {
        c: (w / total_w) if total_w > 0 else 0.0
        for c, w in sorted(probs_raw.items())
    }

    # ── 5-8. Статистики по °F (используем weighted values) ───────────────────
    # Строим взвешенный список значений °F для scipy-вычислений
    cols_with_w = [(col, weights.get(col, 0.0)) for col in tmax_f_raw if col in weights]

    f_values = np.array([tmax_f_raw[col] for col, _ in cols_with_w])
    w_values = np.array([w for _, w in cols_with_w])
    w_values = w_values / w_values.sum()  # normalize

    mean_f   = float(np.average(f_values, weights=w_values))
    median_f = float(_weighted_median(f_values, w_values))
    sd_f     = float(np.sqrt(np.average((f_values - mean_f) ** 2, weights=w_values)))
    skew_f   = float(_weighted_skew(f_values, w_values, mean_f, sd_f))

    # Mode — наиболее частое целое °F (невзвешенный, по целым)
    f_int_arr = np.array([tmax_f_int[col] for col in tmax_f_raw])
    mode_f   = float(stats.mode(f_int_arr, keepdims=True).mode[0])

    return DayStats(
        date       = target,
        probs_c    = probs_c,
        mean_f     = round(mean_f, 1),
        mode_f     = mode_f,
        median_f   = round(median_f, 1),
        sd_f       = round(sd_f, 1),
        skew_f     = round(skew_f, 2),
        sigma1_lo  = round(mean_f - sd_f, 1),
        sigma1_hi  = round(mean_f + sd_f, 1),
        sigma2_lo  = round(mean_f - 2 * sd_f, 1),
        sigma2_hi  = round(mean_f + 2 * sd_f, 1),
    )


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    """Взвешенная медиана."""
    sorted_idx = np.argsort(values)
    sv = values[sorted_idx]
    sw = weights[sorted_idx]
    cumw = np.cumsum(sw)
    midpoint = 0.5
    return float(sv[np.searchsorted(cumw, midpoint)])


def _weighted_skew(values: np.ndarray, weights: np.ndarray, mean: float, sd: float) -> float:
    """Взвешенная асимметрия (skewness)."""
    if sd == 0:
        return 0.0
    return float(np.average(((values - mean) / sd) ** 3, weights=weights))


# ── Метки (экспортируем для notifier) ────────────────────────────────────────
sd_label      = _sd_label
skew_label    = _skew_label
market_label  = _market_label


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")
    sys.path.insert(0, ".")
    from collector import fetch_ensemble

    df      = fetch_ensemble()
    results = process(df)

    for r in results:
        print(f"\n=== {r['date']} ===")
        print("Вероятности Tmax:")
        for c, p in r["probs_c"].items():
            print(f"  {c}°C — {p*100:.1f}% ({market_label(c)})")
        print(f"Mean={r['mean_f']}°F  Mode={r['mode_f']}°F  Median={r['median_f']}°F")
        print(f"SD={r['sd_f']}°F ({sd_label(r['sd_f'])})")
        print(f"68%: {r['sigma1_lo']}-{r['sigma1_hi']}°F")
        print(f"95%: {r['sigma2_lo']}-{r['sigma2_hi']}°F")
        print(f"Skew={r['skew_f']} ({skew_label(r['skew_f'])})")
