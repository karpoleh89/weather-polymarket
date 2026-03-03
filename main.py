# -*- coding: utf-8 -*-
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def main():
    try:
        from collector import fetch_ensemble
        from processor import process
        from notifier  import send_report
        from observer  import get_actual_tmax_yesterday, get_current_conditions

        logger.info("=== Weather Polymarket Bot START ===")

        df         = fetch_ensemble()
        conditions = get_current_conditions()
        results    = process(
            df,
            wind_deg    = conditions["wind_deg"],
            cloud_label = conditions["cloud_label"],
        )
        actual_yesterday = get_actual_tmax_yesterday()
        send_report(results, actual_yesterday, conditions)

        logger.info("=== Weather Polymarket Bot DONE ===")

    except Exception as e:
        logger.exception("Critical error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
