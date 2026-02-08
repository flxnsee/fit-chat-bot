import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, or_f
from aiogram.fsm.context import FSMContext

from src.states import AdminState
from src.messages import MESSAGES
import src.keyboards as keyboards
import src.database as db

router = Router()


@router.message(or_f(Command("admin"), F.text == "🔐 Адмін-панель"))
async def cmd_admin(message: Message, state: FSMContext):
    if not await db.is_user_admin(message.from_user.id):
        return
    await state.set_state(AdminState.main)
    await message.answer(
        MESSAGES["admin_welcome"], reply_markup=await keyboards.admin_menu()
    )


@router.message(AdminState.main, F.text == "🔙 Вийти з адмін-панелі")
async def exit_admin(message: Message, state: FSMContext):
    is_admin = await db.is_user_admin(message.from_user.id)
    await state.clear()
    await message.answer(
        MESSAGES["admin_exit"], reply_markup=await keyboards.reply_options(is_admin)
    )


@router.message(AdminState.main, F.text == "📊 Статистика")
async def admin_stats(message: Message):
    stats = await db.get_bot_stats()
    await message.answer(
        MESSAGES["admin_stats"].format(
            user_count=stats.get("total_users", 0),
            active_user_count=stats.get("active_users", 0),
            banned_user_count=stats.get("banned_users", 0),
            letter_count=stats.get("total_letters", 0),
            delivered_letter_count=stats.get("delivered_letters", 0),
        )
    )


@router.message(AdminState.main, F.text == "📢 Розсилка")
async def admin_broadcast(message: Message, state: FSMContext):
    await state.set_state(AdminState.waiting_for_broadcast)
    await message.answer(
        MESSAGES["admin_broadcast"], reply_markup=await keyboards.cancel_admin()
    )


@router.message(AdminState.waiting_for_broadcast)
async def admin_broadcast_send(message: Message, state: FSMContext, bot: Bot):
    if message.text == "❌ Скасувати":
        await state.set_state(AdminState.main)
        await message.answer(
            MESSAGES["admin_broadcast_exit"], reply_markup=await keyboards.admin_menu()
        )

        return

    users_cursor = await db.get_all_users_cursor()
    count = 0
    blocked = 0

    status_msg = await message.answer("⏳ Розсилка почалася...")

    if users_cursor:
        async for user in users_cursor:
            current_state = await state.get_state()

            if current_state != AdminState.waiting_for_broadcast:
                await status_msg.edit_text("🛑 Розсилку було примусово зупинено.")

                return

            try:
                await bot.send_message(user["user_id"], message.text)

                count += 1

                await asyncio.sleep(0.05)

            except Exception:
                blocked += 1

    await status_msg.delete()
    await message.answer(
        MESSAGES["admin_broadcast_info"].format(count=count, blocked=blocked),
        reply_markup=await keyboards.admin_menu(),
    )
    await state.set_state(AdminState.main)


@router.message(AdminState.main, F.text == "🔨 Бан")
async def admin_ban_start(message: Message, state: FSMContext):
    await state.set_state(AdminState.waiting_for_ban)
    await message.answer(
        MESSAGES["admin_ban_prompt"], reply_markup=await keyboards.cancel_admin()
    )


@router.message(AdminState.waiting_for_ban)
async def admin_ban_process(message: Message, state: FSMContext):
    if message.text == "❌ Скасувати":
        await state.set_state(AdminState.main)
        await message.answer(
            MESSAGES["admin_ban_exit"], reply_markup=await keyboards.admin_menu()
        )
        return

    try:
        target_id = int(message.text)
        if await db.is_user_admin(target_id):
            await state.set_state(AdminState.main)
            return await message.answer(
                MESSAGES["admin_ban_admin_error"].format(user_id=target_id),
                reply_markup=await keyboards.admin_menu(),
            )

        await db.deactivate_user(target_id)
        await message.answer(
            MESSAGES["admin_ban_success"].format(user_id=target_id),
            reply_markup=await keyboards.admin_menu(),
        )
        await state.set_state(AdminState.main)
    except ValueError:
        await message.answer(
            MESSAGES["admin_error"].format(user_id=message.text),
            reply_markup=await keyboards.admin_menu(),
        )


@router.message(AdminState.main, F.text == "🕊️ Розбан")
async def admin_unban_start(message: Message, state: FSMContext):
    await state.set_state(AdminState.waiting_for_unban)
    await message.answer(
        MESSAGES["admin_unban_prompt"], reply_markup=await keyboards.cancel_admin()
    )


@router.message(AdminState.waiting_for_unban)
async def admin_unban_process(message: Message, state: FSMContext):
    if message.text == "❌ Скасувати":
        await state.set_state(AdminState.main)
        await message.answer(
            MESSAGES["admin_unban_exit"], reply_markup=await keyboards.admin_menu()
        )
        return

    try:
        target_id = int(message.text)
        await db.activate_user(target_id)
        await message.answer(
            MESSAGES["admin_unban_success"].format(user_id=target_id),
            reply_markup=await keyboards.admin_menu(),
        )
        await state.set_state(AdminState.main)
    except ValueError:
        await message.answer(
            MESSAGES["admin_error"].format(user_id=message.text),
            reply_markup=await keyboards.admin_menu(),
        )


@router.callback_query(F.data.startswith("ban_user_"))
async def admin_quick_ban(callback: CallbackQuery):
    if not await db.is_user_admin(callback.from_user.id):
        return

    try:
        target_id = int(callback.data.split("_")[2])
        if await db.is_user_admin(target_id):
            await callback.answer(
                MESSAGES["admin_ban_admin_error"].format(user_id=target_id),
                show_alert=True,
            )
            return

        await db.deactivate_user(target_id)
        await callback.message.edit_text(
            MESSAGES["admin_ban_success"].format(user_id=target_id)
        )
    except Exception as e:
        await callback.answer("Error processing ban")


@router.message(Command("setadmin"))
async def cmd_set_admin(message: Message):
    if not await db.is_user_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(MESSAGES["setadmin_info"], parse_mode="Markdown")
        return
    if not parts[1].isdigit():
        await message.answer(MESSAGES["setadmin_error"])
        return

    target_id = int(parts[1])
    if await db.check_user_exists(target_id):
        await db.set_admin(target_id)
        await message.answer(
            MESSAGES["setadmin_success"].format(user_id=target_id),
            parse_mode="Markdown",
        )
    else:
        await message.answer(MESSAGES["admin_error"].format(user_id=target_id))


async def show_next_report(message: Message, state: FSMContext):
    reports = await db.get_active_reports()

    if not reports:
        await message.answer(
            "✅ Активних скарг немає! Все чисто.",
            reply_markup=await keyboards.admin_menu(),
        )
        await state.set_state(AdminState.main)
        return

    report = reports[0]

    text = (
        f"🚨 <b>Розгляд скарги</b> ({len(reports)} в черзі)\n\n"
        f"✉️ <b>Лист від:</b> <code>{report['sender_id']}</code>\n"
        f"👤 <b>Поскаржився:</b> <code>{report.get('reported_by', 'Н/Д')}</code>\n\n"
        f"📝 <b>Текст листа:</b>\n<blockquote>{report['content']}</blockquote>"
    )

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=await keyboards.admin_report_actions(
            report["sender_id"], str(report["_id"])
        ),
    )


@router.message(AdminState.main, F.text == "🚨 Скарги")
async def admin_check_reports(message: Message, state: FSMContext):
    await show_next_report(message, state)


@router.callback_query(F.data.startswith("adm_"))
async def admin_report_decision(callback: CallbackQuery, state: FSMContext, bot: Bot):
    parts = callback.data.split("_")
    action = parts[1]
    target_id = int(parts[2])
    letter_id = parts[3]

    if action == "dismiss":
        await db.close_report(letter_id, callback.from_user.id, "dismissed")
        await callback.answer("Скаргу відхилено")

    elif action == "ban":
        if await db.is_user_admin(target_id):
            await callback.answer("Це адмін! Не можу забанити", show_alert=True)
            return

        await db.deactivate_user(target_id)
        await db.close_report(letter_id, callback.from_user.id, "banned")
        await callback.answer("Користувача заблоковано")

    elif action == "warn":
        warnings = await db.warn_user(target_id)
        if warnings >= 3:
            await db.deactivate_user(target_id)
            await db.close_report(letter_id, callback.from_user.id, "banned_by_warns")
            try:
                await bot.send_message(
                    target_id, "🚫 Ви отримали 3-тє попередження і були заблоковані."
                )
            except:
                pass
            await callback.answer(f"3-й варн. Забанено.")
        else:
            await db.close_report(letter_id, callback.from_user.id, "warned")
            try:
                await bot.send_message(
                    target_id,
                    f"⚠️ Ви отримали попередження ({warnings}/3). Дотримуйтесь правил!",
                )
            except:
                pass
            await callback.answer(f"Варн видано ({warnings}/3)")

    await callback.message.delete()

    await show_next_report(callback.message, state)
