import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import src.database as db
from config import TOKEN
from src.handlers import router as main_router
from src.middlewares import CheckRegistrationMiddleware
from src.messages import MESSAGES

logging.basicConfig(level=logging.INFO, stream = sys.stdout)
logger = logging.getLogger(__name__)

bot = Bot(token = TOKEN, default = DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler()

sending_lock = False

async def send_due_letters(bot: Bot):
    global sending_lock

    if sending_lock:
        logger.warning("Mailman: previous sending task still running, skipping this run")
        return
    
    sending_lock = True

    try:    
        due_letters = await db.get_letters(limit = 50)

        if not due_letters:
            return
        
        logger.info(f"Mailman: found {len(due_letters)} due letters to send")

        for letter in due_letters:
            try:
                text = MESSAGES['new_letter_notification'].format(content = letter['content'])

                await bot.send_message(letter['recipient_id'], text)
                await db.mark_letter_delivered(letter['_id'])
                await asyncio.sleep(0.05)

            except TelegramForbiddenError:
                logger.warning(f"Mailman: cannot send letter to user {letter['recipient_id']}, bot was blocked")
                
                await db.mark_letter_failed(letter['_id'], reason="user_blocked")
                await db.deactivate_user(letter['recipient_id'])

            except TelegramRetryAfter as e:
                logger.warning(f"Mailman: hit rate limit, sleeping for {e.retry_after} seconds")

                await asyncio.sleep(e.retry_after)

            except Exception as e:
                logger.error(f"Mailman: failed to send letter {letter['_id']} due to {e}")

                await db.mark_letter_failed(letter['_id'], reason = str(e))

    except Exception as e:
        logger.error(f"Mailman: unexpected error: {e}")

    finally:
        sending_lock = False

async def main():
    await db.init_indexes()

    dp.message.middleware(CheckRegistrationMiddleware())
    dp.callback_query.middleware(CheckRegistrationMiddleware())
    dp.include_router(main_router)

    scheduler.add_job(send_due_letters, 'interval', minutes=1, args=[bot])
    scheduler.start()

    logger.info("Bot started")

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")