import logging
import os
from dotenv import load_dotenv

from src.gateway import init_telegram_application

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=getattr(logging, LOG_LEVEL, logging.INFO),
)
logger = logging.getLogger("career_pilot.main")

def main() -> None:
    logger.info("=========================================================")
    logger.info("Starting CareerPilot Auditing and Job-Hunting Daemon")
    logger.info("=========================================================")

    try:
        app = init_telegram_application()
        logger.info("Telegram Bot long polling starting. Waiting for incoming resumes...")
        app.run_polling(close_loop=True)
    except Exception as exc:
        logger.critical(f"Daemon terminated due to unexpected error in bot runtime: {exc}", exc_info=True)
    finally:
        logger.info("CareerPilot daemon shut down.")

if __name__ == "__main__":
    main()
