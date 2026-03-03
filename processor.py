# -*- coding: utf-8 -*-
import logging
from collections import defaultdict
from datetime import date, timedelta, datetime, timezone
import numpy as np
import pandas as pd
from scipy import stats
import config

logger = logging.getLogger(__name__)


def process(df: pd.DataFrame, wind_deg: float = None) -> list:
    today    = datetime.now(timezone.utc).date()
    tomorrow = today + timedelta(days=1)
    now_utc  = datetime.now(timezone.utc)
    results  = []

    for target_date in (today, tomorrow):
        # Lead time в часах до конца дня
        target_end = datetime(target_date.year, target_date.month, target_date.day,
                              21, 0, 0, tzinfo=timezone.utc)
        lead_hours = max(0, (target_end - now_utc).total_seconds() / 3600)

        weights = _build_weights(df.columns.tolist(), lead_hours, wind_deg, df)

        day_df = df[df.index.date == target_date]
        if day_df.empty:
            logger.warning("No data for %s", target_date)
            continue
        results.append(_compute_day(day_df, target_date, weights, lead_hours))

    return results


def _build_weights(columns: list, lead_hours: float,
                   wind_deg: float = None, df: pd.DataFrame = None) -> dict:
    """
    Веса с тремя уровнями корректировки:
    1. Базовые веса из config
    2. Lead-time корректировка (чем ближе событие — тем важнее локальные модели)
    3. Ветровая корректировка (восточный ветер → UKMO важнее, GFS слабее)
    4. Spread-Skill корректировка (уверенная модель получает бонус)
    """
    # Сопоставляем колонки с моделями
    col_to_model = {}
    for col in columns:
        for model in config.ENSEMBLE_MODELS:
            if model in col:
                col_to_model[col] = model
                break

    model_col_count = defaultdict(int)
    for model in col_to_model.values():
        model_col_count[model] += 1

    # Базовые групповые веса
    group_weights = {g: info["weight"] for g, info in config.MODEL_GROUPS.items()}

    # ── 1. Lead-time корректировка ────────────────────────────────────────────
    # За 48ч+: глобальные (ECMWF, GFS) важнее
    # За 12ч-: локальные (UKMO, ICON) важнее
    if lead_hours <= 12:
        # Финальная стадия — доверяем локальным
        lead_multipliers = {"ecmwf": 0.8, "gefs": 0.6, "icon": 1.3, "ukmo": 1.5}
    elif lead_hours <= 24:
        # Переходная зона
        lead_multipliers = {"ecmwf": 0.9, "gefs": 0.8, "icon": 1.2, "ukmo": 1.2}
    else:
        # Далёкий горизонт — глобальные надёжнее
        lead_multipliers = {"ecmwf": 1.1, "gefs": 1.0, "icon": 0.9, "ukmo": 0.9}

    for g in group_weights:
        group_weights[g] *= lead_multipliers.get(g, 1.0)

    # ── 2. Ветровая корректировка ─────────────────────────────────────────────
    # Восточный ветер (45°-135°): UKMO лучше видит морской бриз с Темзы
    if wind_deg is not None:
        if 45 <= wind_deg <= 135:
            logger.info("Eastern wind (%.0f deg) — boosting UKMO, reducing GFS", wind_deg)
            group_weights["ukmo"] *= 1.5
            group_weights["gefs"] *= 0.5
        elif 225 <= wind_deg <= 315:
            logger.info("Western wind (%.0f deg) — standard weights", wind_deg)

    # Нормализуем групповые веса до суммы 1.0
    total_gw = sum(group_weights.values())
    group_weights = {g: w / total_gw for g, w in group_weights.items()}
    logger.info("Group weights after adjustments: %s",
                {g: round(w, 3) for g, w in group_weights.items()})

    # Базовый вес каждой колонки
    weights = {}
    for group, info in config.MODEL_GROUPS.items():
        gw = group_weights[group]
        n_models = len(info["models"])
        for model in info["models"]:
            n_cols = model_col_count.get(model, 0)
            if n_cols == 0:
                continue
            per_col = gw / (n_models * n_cols)
            for col, m in col_to_model.items():
                if m == model:
                    weights[col] = per_col

    # ── 3. Spread-Skill корректировка ─────────────────────────────────────────
    # Модель с меньшим внутренним разбросом получает бонус
    if df is not None:
        weights = _apply_spread_skill(weights, col_to_model, df)

    # Финальная нормализация
    total = sum(weights.values())
    if total == 0:
        raise RuntimeError("Weights sum to zero")
    weights = {k: v / total for k, v in weights.items()}
    return weights


def _apply_spread_skill(weights: dict, col_to_model: dict,
                        df: pd.DataFrame) -> dict:
    """
    Spread-Skill: модель у которой члены ансамбля более согласны между собой
    (меньше внутренний SD) получает мультипликатор > 1.
    Логика: уверенная модель → заслуживает больше доверия прямо сейчас.
    """
    # Считаем внутренний SD каждой модели по последним 24ч
    cutoff = df.index.max() - pd.Timedelta(hours=24)
    recent = df[df.index >= cutoff]
    if recent.empty:
        return weights

    # Группируем колонки по модели
    model_cols = defaultdict(list)
    for col, model in col_to_model.items():
        if col in weights:
            model_cols[model].append(col)

    model_sd = {}
    for model, cols in model_cols.items():
        subset = recent[cols].dropna(how="all")
        if subset.empty or len(cols) < 2:
            continue
        # Средний SD по всем временным точкам
        model_sd[model] = float(subset.std(axis=1).mean())

    if not model_sd:
        return weights

    # Инвертируем: меньше SD → больше мультипликатор
    max_sd = max(model_sd.values())
    min_sd = min(model_sd.values())
    spread = max_sd - min_sd

    multipliers = {}
    for model, sd in model_sd.items():
        if spread > 0.1:
            # Нормализуем: от 0.7 (макс SD) до 1.3 (мин SD)
            norm = (max_sd - sd) / spread
            multipliers[model] = 0.7 + norm * 0.6
        else:
            multipliers[model] = 1.0

    logger.info("Spread-Skill multipliers: %s",
                {m: round(v, 3) for m, v in multipliers.items()})

    # Применяем
    adjusted = {}
    for col, w in weights.items():
        model = col_to_model.get(col)
        mult  = multipliers.get(model, 1.0)
        adjusted[col] = w * mult

    return adjusted


def _f_to_wunder_c(f_val: float) -> int:
    return int(round((f_val - 32) / 1.8, 0))


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    idx = np.argsort(values)
    sv, sw = values[idx], weights[idx]
    cumw = np.cumsum(sw)
    return float(sv[np.searchsorted(cumw, 0.5)])


def _weighted_skew(values: np.ndarray, weights: np.ndarray,
                   mean: float, sd: float) -> float:
    if sd == 0:
        return 0.0
    return float(np.average(((values - mean) / sd) ** 3, weights=weights))


def _compute_day(day_df: pd.DataFrame, target: date,
                 weights: dict, lead_hours: float) -> dict:
    daytime = day_df.between_time("06:00", "21:00")
    if daytime.empty:
        logger.warning("No daytime hours for %s, using full day", target)
        daytime = day_df

    tmax_raw = {}
    for col in daytime.columns:
        s = daytime[col].dropna()
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
    mode_f   = float(stats.mode(np.array([tmax_int[col] for col in tmax_raw]),
                                keepdims=True).mode[0])

    # Tmax по группам моделей (для Bias Collection)
    group_tmax = {}
    group_map = {model: group for group, info in config.MODEL_GROUPS.items()
                 for model in info["models"]}
    col_to_model_local = {}
    for col in tmax_raw:
        for model in config.ENSEMBLE_MODELS:
            if model in col:
                col_to_model_local[col] = model
                break

    group_vals = defaultdict(list)
    for col, tmax_val in tmax_raw.items():
        model = col_to_model_local.get(col)
        if model:
            group = group_map.get(model)
            if group:
                group_vals[group].append(tmax_val)

    GROUP_LABELS = {
        "ecmwf": "ECMWF",
        "gefs":  "GFS",
        "icon":  "ICON",
        "ukmo":  "UKMO",
    }
    for group, vals in group_vals.items():
        if vals:
            group_tmax[GROUP_LABELS.get(group, group)] = round(float(np.mean(vals)), 1)

                     
    cs = confidence_score_with_bonus(sd_f, skew_f, mean_f, mode_f)
    vd = verdict_label(sd_f, skew_f)

    return dict(
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
        confidence = cs,
        verdict    = vd,
        lead_hours = round(lead_hours, 1),
        group_tmax = group_tmax,
    )


def confidence_score(sd: float, skew: float, mean_f: float) -> int:
    score = 10
    if sd > 2.5:
        score -= 6
    elif sd > 1.5:
        score -= 3
    if abs(skew) > 1.0:
        score -= 2
    if _f_to_wunder_c(mean_f) % 5 == 0:
        score -= 2
    return max(0, min(10, score))


def confidence_score_with_bonus(sd: float, skew: float,
                                mean_f: float, mode_f: float) -> int:
    score = confidence_score(sd, skew, mean_f)
    if _f_to_wunder_c(mean_f) == _f_to_wunder_c(mode_f):
        score += 2
    return max(0, min(10, score))


def verdict_label(sd: float, skew: float) -> str:
    if sd < 1.1:
        return "\U0001f48e БЕТОН (Входи крупно)"
    elif sd < 1.8 and abs(skew) < 0.7:
        return "\u2705 СИГНАЛ (Стандартный риск)"
    elif sd > 2.5 or abs(skew) > 1.5:
        return "\u26a0\ufe0f ЛОТЕРЕЯ (Только копейки)"
    elif sd >= 1.8:
        return "\U0001f7e1 РИСК (Нужен хедж)"
    else:
        return "\U0001f50d АНАЛИЗИРУЙ РУКАМИ"


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
