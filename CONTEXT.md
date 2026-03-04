# POLYMARKET WEATHER TRADING AGENT — PROJECT CONTEXT

> Вставь этот файл первым сообщением в любой новый чат.
> Язык общения: русский. Код: английский.

---

## СТАТУС ПРОЕКТА

Этап 0 (текущий) — ГОТОВО:
- Ансамблевая модель прогноза погоды (Python)
- Telegram бот с уведомлениями
- Веб-дашборд (vanilla JS, Chart.js)
- Cloudflare Worker (METAR прокси + Blackbox.ai прокси)

Следующий этап — инфраструктура + Polymarket read-only + SEMI-AUTO торговля

---

## ГЕО

**Основное гео:** EGLC — London City Airport
- LAT: 51.503164654, LON: 0.053166454
- ICAO: EGLC
- Ключевой локальный эффект: Thames Estuary Breeze (восточный ветер 45°–135° = холодный воздух с эстуария, резкое торможение прогрева)

**Мультигео:** архитектура должна поддерживать несколько гео с первого дня. Каждое гео — строка в таблице `geos` в БД. Новое гео = новая строка, не новый код.

---

## АНСАМБЛЕВАЯ МОДЕЛЬ (processor.py)

### Модели и веса (config.py)
```python
MODEL_GROUPS = {
    "ecmwf": {"models": ["ecmwf_ifs025_ensemble", "ecmwf_aifs025_ensemble"], "weight": 0.4},
    "gefs":  {"models": ["ncep_gefs_seamless"],                              "weight": 0.1},
    "icon":  {"models": ["icon_seamless_eps", "icon_d2_eps"],                "weight": 0.2},
    "ukmo":  {"models": ["ukmo_global_ensemble_20km", "ukmo_uk_ensemble_2km"],"weight": 0.3},
}
# Итого: 214 членов ансамбля
```

### Динамические веса (_build_weights)
Три уровня корректировки поверх базовых весов:

**1. Lead-time мультипликаторы:**
```python
if lead_hours <= 12:   # финальная стадия — доверяем локальным
    {ecmwf: 0.8, gefs: 0.6, icon: 1.3, ukmo: 1.5}
elif lead_hours <= 24:  # переходная зона
    {ecmwf: 0.9, gefs: 0.8, icon: 1.2, ukmo: 1.2}
else:                   # далёкий горизонт — глобальные надёжнее
    {ecmwf: 1.1, gefs: 1.0, icon: 0.9, ukmo: 0.9}
```

**2. Ветровая коррекция:**
```python
if 45 <= wind_deg <= 135:  # восточный ветер → Thames breeze
    ukmo *= 1.5
    gefs *= 0.5
```

**3. Spread-Skill коррекция:**
- Считает внутренний SD каждой модели за последние 24ч (cutoff = df.index.max() - 24h)
- Инвертирует: меньше SD → мультипликатор 0.7..1.3
- Уверенная модель получает бонус

### Расчёт вероятностей (_compute_day) — ТОЧНЫЙ АЛГОРИТМ
```python
# КРИТИЧНО: именно такой порядок операций
tmax_raw[col] = daytime_series.max()           # raw °F, 06:00–21:00 UTC
tmax_int[col] = round(tmax_raw[col])           # Python banker's rounding!
tmax_c[col]   = int(round((tmax_int - 32) / 1.8))  # _f_to_wunder_c
probs_c[c]   += weights[col]                   # накапливаем по °C бакетам
```

**ВАЖНО — банковское округление Python:**
- Python `round(60.5) = 60` (round half to even)
- JS `Math.round(60.5) = 61` — НЕ СОВПАДАЕТ
- В JS нужна функция `bankersRound(x)`

### Данные приходят в °F
API Open-Meteo вызывается с `temperature_unit: "fahrenheit"`.
Ансамбль → конвертация в °C только для вероятностей (через _f_to_wunder_c).
Дашборд отображает в °F (пользователь так захотел).

### Структура вывода process()
```python
{
    date, probs_c,           # {°C: probability}
    mean_f, mode_f, median_f, sd_f, skew_f,
    sigma1_lo, sigma1_hi, sigma2_lo, sigma2_hi,
    confidence,              # 0–10
    verdict,                 # "💎 БЕТОН" / "✅ СИГНАЛ" / "⚠️ ЛОТЕРЕЯ" / "🟡 РИСК"
    lead_hours,
    group_tmax,              # {"ECMWF": X, "GFS": X, "ICON": X, "UKMO": X}
}
```

### Bias correction
Структура есть в config.py, но пока нули — коррекция не применяется.
После 10+ дней наблюдений — заполнить и включить.

---

## ФАЙЛЫ ПРОЕКТА (текущие)

```
backend/
├── config.py       — MODEL_GROUPS, BIAS_CORRECTION, ENSEMBLE_MODELS, LAT/LON
├── processor.py    — _build_weights, _compute_day, process()
├── observer.py     — сбор данных METAR для bias tracking
├── notifier.py     — Telegram бот
└── main.py         — точка входа, scheduler

frontend/
└── dashboard.html  — vanilla JS, Chart.js 4.4.1, один файл

cloudflare/
└── worker.js       — два endpoint:
    GET /           → METAR proxy (aviationweather.gov)
    POST /ai        → Blackbox.ai proxy (OpenAI-compatible API)
    POST /models    → список доступных моделей Blackbox
```

---

## CLOUDFLARE WORKER

URL: `https://metar-proxy.karpoleh89.workers.dev`

```javascript
// METAR
GET /?ids=EGLC&hours=12

// AI (Blackbox.ai)
POST /ai
Body: { model: "auto", messages: [...], max_tokens: 1000 }
// Worker сам вызывает /models и берёт первую доступную модель

// Список моделей
GET /models
```

Blackbox.ai API: OpenAI-compatible формат.
- Endpoint: `https://api.blackbox.ai/v1/chat/completions`
- Auth: `Bearer sk-...`
- Response: `choices[0].message.content`

---

## ДАШБОРД (dashboard.html)

Текущие возможности:
- Ансамблевый график (p10/p50/p90 + модели + METAR overlay)
- Вероятности Tmax (°C, Polymarket формат)
- Таблица ветра (Open-Meteo, м/с, на день)
- METAR таблица (последние 8 наблюдений)
- Карточки текущих условий (ТЕМП из последнего METAR)
- Nowcast hints (dT/dt, delta от модели, бриз Темзы, QNH)
- AI-аналитик (кнопка → Blackbox.ai → анализ на русском)
- Карта imweather (satellite nowcast, с кнопкой обновления)
- Auto-refresh 30 мин

Ключевые функции JS:
- `bankersRound(x)` — банковское округление (≡ Python round)
- `fWunderC(f)` — °F → °C (≡ _f_to_wunder_c)
- `buildWeights()` — полный порт _build_weights включая Spread-Skill
- `rProbs()` — вероятности, точно совпадают с ботом
- `metarParsed()` — парсинг METAR с защитой от всех форматов времени

---

## POLYMARKET ТОРГОВЛЯ

### Бюджет и риск-менеджмент
- Бюджет: $10–20 на рынок (например, все температуры Лондона на день)
- Kelly: stake = (edge × bankroll) / odds
- Edge = model_prob - market_prob
- Max Kelly fraction: 15% от бюджета рынка (~$2.25 макс за ставку)
- Min edge threshold: 5%
- Stop-loss: -$5 на рынок (треть бюджета)
- Dutching: при нескольких исходах с edge — распределяем ставку для единого target profit

### Пример решения Brain
```
EGLC · 04 Mar · Tmax прогноз

Модель:  14°C = 52%  |  13°C = 31%  |  15°C = 17%
Рынок:   14°C = 38¢  |  13°C = 45¢  |  15°C = 22¢
Edge:    14°C +14%   |  13°C -14%   |  15°C -5%

Сигнал: BUY 14°C @ 0.38
Размер: $3.20 (Kelly 21% → cap 15% → $2.25)
```

### Режимы торговли
- **SEMI-AUTO (текущий план):** каждое решение → Telegram кнопки ✅/❌/✏️
- **FULL AUTO:** Brain торгует самостоятельно в пределах лимитов
- **MONITOR:** только анализ, сделки вручную

---

## ТЕХНИЧЕСКИЙ СТЕК (план)

```
Backend:   Python 3.11 + FastAPI + Celery + Redis
Database:  PostgreSQL 16 + TimescaleDB + pgvector
Frontend:  Next.js 14 + shadcn/ui + TradingView Lightweight Charts
Infra:     Hetzner CX32 (€5.5/мес) + Cloudflare Workers (бесплатно)
LLM:       Claude Sonnet (Brain) + Claude Haiku/Blackbox (Nowcast)
Trading:   py-clob-client + web3.py (Polygon)
Monitoring: Grafana + Prometheus + Loki
```

Итого: ~€20–45/мес

---

## СТРУКТУРА БД (план, мультигео)

```sql
-- Конфиг гео (новое гео = новая строка)
CREATE TABLE geos (
    id TEXT PRIMARY KEY,          -- "EGLC", "EGLL", etc.
    name TEXT,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    icao TEXT,
    polymarket_slug TEXT,
    ensemble_config JSONB,        -- weights, models
    bias_correction JSONB,
    budget_usd DECIMAL,
    active BOOLEAN DEFAULT true
);

-- Ансамблевые прогоны (TimescaleDB hypertable)
CREATE TABLE ensemble_runs (
    time TIMESTAMPTZ NOT NULL,
    geo_id TEXT REFERENCES geos(id),
    target_date DATE,
    probs_c JSONB,                -- {14: 0.52, 13: 0.31, ...}
    mean_f DECIMAL, sd_f DECIMAL,
    lead_hours DECIMAL,
    group_tmax JSONB,
    confidence INT,
    verdict TEXT
);

-- METAR наблюдения
CREATE TABLE metar_obs (
    time TIMESTAMPTZ NOT NULL,
    geo_id TEXT,
    temp_c DECIMAL, dewpoint_c DECIMAL,
    wind_dir INT, wind_spd_ms DECIMAL,
    altimeter_hpa DECIMAL,
    raw TEXT
);

-- Polymarket цены
CREATE TABLE market_prices (
    time TIMESTAMPTZ NOT NULL,
    geo_id TEXT,
    market_id TEXT,
    outcome TEXT,                  -- "14C", "13C", etc.
    best_bid DECIMAL,
    best_ask DECIMAL
);

-- Сделки
CREATE TABLE trades (
    id UUID PRIMARY KEY,
    geo_id TEXT,
    market_id TEXT,
    outcome TEXT,
    side TEXT,                    -- BUY/SELL
    size_usd DECIMAL,
    price DECIMAL,
    kelly_fraction DECIMAL,
    edge_at_entry DECIMAL,
    brain_reasoning TEXT,         -- полный текст reasoning LLM
    status TEXT,                  -- pending/filled/cancelled
    created_at TIMESTAMPTZ,
    filled_at TIMESTAMPTZ
);

-- База знаний (RAG)
CREATE TABLE knowledge (
    id UUID PRIMARY KEY,
    geo_id TEXT,
    category TEXT,                -- "geo_factor", "trade_log", "llm_lesson"
    content TEXT,
    embedding vector(1536),       -- pgvector
    created_at TIMESTAMPTZ
);
```

---

## NOWCAST СИГНАЛЫ

| Сигнал | Порог | Действие |
|--------|-------|----------|
| dT/dt быстрый прогрев | >2.7°F/ч | Tmax выше прогноза |
| dT/dt охлаждение | <-0.9°F/ч | Пик дня позади |
| Факт vs модель | >1.5°F выше | Бычий сигнал |
| Факт vs модель | <-1.5°F ниже | Медвежий сигнал |
| Ветер восточный | 45°–135° | Thames breeze риск |
| T–Td дефицит | >14°F и растёт | Риск пробоя вверх |
| QNH падение | ≥2 hPa/3ч | Нестабильность |

---

## ЗНАНИЯ О EGLC (база)

- Thames Estuary Breeze: восточный ветер с эстуария Темзы резко тормозит прогрев. Может понизить Tmax на 2–4°C за 15–20 минут.
- UKMO лучше видит локальные морские эффекты для EGLC → boost при восточном ветре
- GFS хуже → penalty при восточном ветре
- Urban heat island: EGLC находится в East London, Canary Wharf рядом — небольшое повышение ночных минимумов
- Runway orientation E-W: влияет на приземный слой ветра
- Рекомендация: при облачности >80% — занижать модельный прогноз на 0.5–1°C (радиационный прогрев заблокирован)

---

## ПЛАН РАЗРАБОТКИ (спринты)

| # | Название | Статус |
|---|----------|--------|
| 0 | Ensemble + METAR + Telegram + Dashboard | ✅ ГОТОВО |
| 1 | Docker + PostgreSQL мультигео schema + Redis | 🔜 |
| 2 | Polymarket read-only (цены, orderbook, edge расчёт) | 🔜 |
| 3 | Knowledge Base (pgvector + RAG) | 🔜 |
| 4 | Brain v1 + Kelly + Telegram SEMI-AUTO | 🔜 |
| 5 | Первые реальные сделки ($1–3) + Trade Log | 🔜 |
| 6 | Dashboard v2 (Next.js, PnL, позиции) | 🔜 |
| 7 | FULL AUTO (после ≥30 прибыльных сделок) | 🔜 |

---

## ВАЖНЫЕ РЕШЕНИЯ И ПОЧЕМУ

1. **Fahrenheit в API, Celsius в вероятностях** — API Open-Meteo вызывается с `temperature_unit=fahrenheit`. Для вероятностей конвертация через `_f_to_wunder_c` с банковским округлением. Дашборд показывает °F.

2. **Банковское округление** — Python `round()` использует round-half-to-even. В JS нужна кастомная `bankersRound()`. Без этого вероятности не совпадают.

3. **Spread-Skill cutoff** — `df.index.max() - 24h`, не `now - 24h`. Важно для точного воспроизведения логики Python.

4. **Cloudflare Worker** — решает CORS для METAR и хранит API ключи серверно (не в браузере).

5. **Мультигео с первого дня** — все таблицы имеют `geo_id`. Добавить новое гео = одна строка в `geos`, без изменения кода.

6. **Hetzner вместо AWS** — в 10–15 раз дешевле при аналогичном качестве для Европы.

7. **SEMI-AUTO перед FULL-AUTO** — минимум 30 сделок с положительным EV прежде чем доверить автоматике реальные деньги.

---

## КОНТАКТЫ И СЕРВИСЫ

- Cloudflare Worker: `https://metar-proxy.karpoleh89.workers.dev`
- Dashboard: задеплоен на Netlify
- Telegram бот: работает
- Open-Meteo Ensemble API: `https://ensemble-api.open-meteo.com/v1/ensemble`
- AviationWeather METAR: `https://aviationweather.gov/api/data/metar`
- Blackbox.ai API: `https://api.blackbox.ai/v1/chat/completions`
- Polymarket CLOB: `https://clob.polymarket.com`
- py-clob-client: `pip install py-clob-client`
