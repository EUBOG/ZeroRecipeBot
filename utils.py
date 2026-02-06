# utils.py
import time
import logging
from functools import wraps
from requests.exceptions import ConnectionError, Timeout
from urllib3.exceptions import ProtocolError

logger = logging.getLogger(__name__)

def safe_send(bot_method):
    """Декоратор для безопасной отправки сообщений с повторными попытками"""
    @wraps(bot_method)
    def wrapper(*args, **kwargs):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return bot_method(*args, **kwargs)
            except (ConnectionError, ProtocolError, Timeout) as e:
                wait = 2 ** attempt  # экспоненциальная задержка: 1, 2, 4 сек
                logger.warning(f"Попытка {attempt + 1}/{max_retries} не удалась: {e}. Повтор через {wait} сек...")
                if attempt < max_retries - 1:
                    time.sleep(wait)
                else:
                    logger.error(f"Не удалось отправить сообщение после {max_retries} попыток")
                    # Отправляем минимальное уведомление через лог
                    print("⚠️ Не удалось отправить сообщение пользователю (сетевая ошибка)")
    return wrapper