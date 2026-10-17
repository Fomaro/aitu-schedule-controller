import asyncio
import logging
from typing import Callable, Awaitable
from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramBadRequest

logger = logging.getLogger(__name__)


async def safe_broadcast_message(
    bot: Bot,
    chat_ids: list[int],
    text: str,
    on_progress: Callable[[int, int, int], Awaitable[None]] | None = None
) -> tuple[int, int]:
    """
    Безопасная массовая рассылка с защитой от FloodWait и подробной статистикой.
    Возвращает (успешно_отправлено, ошибок).
    """
    sent = 0
    failed = 0
    total = len(chat_ids)

    for i, cid in enumerate(chat_ids, 1):
        try:
            await bot.send_message(
                chat_id=cid,
                text=text,
                disable_web_page_preview=True
            )
            sent += 1
        except TelegramRetryAfter as e:
            logger.warning(f"FloodWait: спим {e.retry_after} сек...")
            await asyncio.sleep(e.retry_after + 1)
            try:
                await bot.send_message(chat_id=cid, text=text, disable_web_page_preview=True)
                sent += 1
            except Exception:
                failed += 1
        except TelegramForbiddenError:
            # Пользователь заблокировал бота
            failed += 1
        except TelegramBadRequest as e:
            logger.debug(f"BadRequest при отправке пользователю {cid}: {e}")
            failed += 1
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при отправке пользователю {cid}: {e}")
            failed += 1

        # Троттлинг 20 сообщений в секунду
        await asyncio.sleep(0.05)

        # Периодическое обновление прогресса (каждые 15 сообщений)
        if on_progress and (i % 15 == 0 or i == total):
            try:
                await on_progress(i, sent, failed)
            except Exception:
                pass

    return sent, failed
