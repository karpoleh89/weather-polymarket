"""main.py — Точка входа оркестратора"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def main():
    try:
        from collector import fetch_ensemble
        from processor import process
        from notifier  import send_report

        logger.info("=== Weather Polymarket Bot START ===")

        # Шаг 1: Сбор данных
        df = fetch_ensemble()

        # Шаг 2: Обработка
        results = process(df)

        # Шаг 3: Отправка
        send_report(results)

        logger.info("=== Weather Polymarket Bot DONE ===")

    except Exception as e:
        logger.exception("Critical error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

---

## `requirements.txt`
```
requests>=2.31
pandas>=2.0
numpy>=1.26
scipy>=1.12
