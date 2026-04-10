import subprocess
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

while True:
    logger.info("ボット起動中...")
    try:
        subprocess.run(["python3", "telegram_ai_bot_full.py"], check=True)
    except Exception as e:
        logger.error(f"クラッシュ: {e}")
    logger.info("5秒後に再起動...")
    time.sleep(5)
