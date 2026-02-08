from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
import src.database as db
from src.messages import MESSAGES


class CheckRegistrationMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        state: FSMContext = data.get("state")

        if not user:
            return await handler(event, data)

        if await db.is_user_banned(user.id):
            if isinstance(event, Message):
                await event.answer(MESSAGES["ban_info"])
            elif isinstance(event, CallbackQuery):
                await event.answer(MESSAGES["ban_info"], show_alert=True)
            return

        is_start_command = isinstance(event, Message) and event.text == "/start"

        if is_start_command:
            return await handler(event, data)

        is_registered = await db.check_user_exists(user.id)
        current_state = await state.get_state() if state else None
        is_registering = current_state is not None

        if is_registered:
            return await handler(event, data)

        if is_registering:
            return await handler(event, data)

        if isinstance(event, Message):
            await event.answer("⚠️ Натисніть /start для початку!")
        elif isinstance(event, CallbackQuery):
            await event.message.answer("⚠️ Натисніть /start для початку!")

        return
