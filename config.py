"""Configuration — Weather Polymarket Bot"""
import os

# London City Airport
LONDON_LAT = 51.503164654
LONDON_LON  = 0.053166454

ENSEMBLE_BASE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"

ENSEMBLE_MODELS = [
    "ukmo_global_ensemble_20km",
    "icon_seamless_eps",
    "icon_d2_eps",
    "ncep_gefs_seamless",
    "ecmwf_ifs025_ensemble",
    "ecmwf_aifs025_ensemble",
    "ukmo_uk_ensemble_2km",
]

# Группы моделей и их суммарный вес
MODEL_GROUPS = {
    "ecmwf": {"models": ["ecmwf_ifs025_ensemble", "ecmwf_aifs025_ensemble"], "weight": 0.4},
    "gefs":  {"models": ["ncep_gefs_seamless"],                              "weight": 0.1},
    "icon":  {"models": ["icon_seamless_eps", "icon_d2_eps"],                "weight": 0.2},
    "ukmo":  {"models": ["ukmo_global_ensemble_20km", "ukmo_uk_ensemble_2km"], "weight": 0.3},
}

MODEL_SHORT_NAMES = {
    "ukmo_global_ensemble_20km": "UKMO Global",
    "icon_seamless_eps":         "ICON Seamless",
    "icon_d2_eps":               "ICON D2",
    "ncep_gefs_seamless":        "GEFS",
    "ecmwf_ifs025_ensemble":     "ECMWF IFS",
    "ecmwf_aifs025_ensemble":    "ECMWF AIFS",
    "ukmo_uk_ensemble_2km":      "UKMO UK 2km",
}

ENSEMBLE_PARAMS = {
    "latitude":         LONDON_LAT,
    "longitude":        LONDON_LON,
    "hourly":           "temperature_2m",
    "models":           ",".join(ENSEMBLE_MODELS),
    "timezone":         "GMT",
    "past_days":        1,
    "forecast_days":    3,
    "temperature_unit": "fahrenheit",
}

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID",   "")

REQUEST_TIMEOUT_SEC = 30
