import math
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext

from src.states import LetterState, InboxState
from src.messages import MESSAGES
import src.utils as utils
import src.keyboards as keyboards
import src.database as db

router = Router()

# Написання листів

@router.message(F.text == "✍️ Написати листа")
async def write_letter(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    if not await db.can_send_letter(user_id):
        await message.answer(MESSAGES['already_sent'])
        return
    
    remaining = await db.get_remaining_limit(user_id)
    
    text = MESSAGES['letter_limit_info'].format(count=remaining) + "\n\n" + MESSAGES['letter_rules']
    
    await message.answer(text, reply_markup=await keyboards.cancel_menu())
    await state.set_state(LetterState.writing_letter)

@router.message(LetterState.writing_letter, F.text == "🔙 Повернутися назад")
async def cancel_letter(message: Message, state: FSMContext):
    await state.clear()

    is_admin = await db.is_user_admin(message.from_user.id)
    
    await message.answer(MESSAGES['letter_cancelled'], reply_markup=await keyboards.reply_options(is_admin))

@router.message(LetterState.writing_letter, F.text == "📬 Вхідні листи")
async def open_inbox_from_writing(message: Message, state: FSMContext):
    await state.clear()
    await open_inbox(message)

@router.message(LetterState.writing_letter, F.text)
async def send_letter(message: Message, state: FSMContext):
    sender_id = message.from_user.id
    content = message.text
    is_admin = await db.is_user_admin(sender_id)

    if utils.contains_bad_words(content):
        await message.answer(MESSAGES['bad_words_warning'])
        return

    if len(content) < 10:
        await message.answer(MESSAGES['letter_too_short_error'])
        return
    
    if len(content) > 1000:
        await message.answer(MESSAGES['letter_too_long_error'].format(max_length=1000))
        return

    sender = await db.get_user(sender_id)
    sender_hobbies = sender.get('hobbies', [])
    sender_course = sender.get('course')

    recipient = await db.find_recipient(sender_id, sender_hobbies, sender_course)

    if not recipient:
        settings = await db.get_user_settings(sender_id)
        msg_key = 'no_recipient2' if settings.get('filter_course') else 'no_recipient'
        await message.answer(MESSAGES[msg_key], reply_markup=await keyboards.reply_options(is_admin))
        await state.clear()
        return
    
    delay = 0
    delivery_time = await db.create_letter(sender_id, recipient['user_id'], content, delay_hours=delay, consume_quota=True)

    remaining = await db.get_remaining_limit(sender_id)

    await message.answer(
        MESSAGES['letter_sent_confirm'].format(time=delivery_time.strftime('%H:%M')) + 
        f"\n\n📉 Залишилось листів: <b>{remaining}/3</b>",
        reply_markup=await keyboards.reply_options(is_admin)
    )
    await state.clear()

# Вхідні листи

@router.message(F.text == "📬 Вхідні листи")
async def open_inbox(message: Message):
    user_id = message.from_user.id
    is_admin = await db.is_user_admin(user_id)
    
    letters, total_count = await db.get_inbox(user_id, page=0, page_size=keyboards.INBOX_PAGE_SIZE)
    
    if not letters:
        await message.answer(MESSAGES['inbox_empty'], reply_markup=await keyboards.reply_options(is_admin))
        return
    
    total_pages = math.ceil(total_count / keyboards.INBOX_PAGE_SIZE)
    
    await message.answer(
        MESSAGES['inbox_prompt'].format(count=total_count, page=1, total_pages=total_pages), 
        reply_markup=await keyboards.inbox_list(letters, page=0, total_pages=total_pages)
    )

@router.callback_query(F.data.startswith("inbox_page_"))
async def change_inbox_page(callback: CallbackQuery):
    page = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    letters, total_count = await db.get_inbox(user_id, page=page, page_size=keyboards.INBOX_PAGE_SIZE)
    total_pages = math.ceil(total_count / keyboards.INBOX_PAGE_SIZE)

    if not letters and page > 0:
        await callback.answer("Сторінка більше недоступна")
        return

    await callback.message.edit_text(
        MESSAGES['inbox_prompt'].format(count=total_count, page=page + 1, total_pages=total_pages),
        reply_markup=await keyboards.inbox_list(letters, page=page, total_pages=total_pages)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("read_letter_"))
async def read_letter(callback: CallbackQuery, state: FSMContext):
    letter_id = callback.data.split("_")[2]
    letter = await db.get_letter(letter_id)

    if not letter:
        await callback.answer(MESSAGES['letter_not_found'], show_alert=True)

        letters, total_count = await db.get_inbox(callback.from_user.id)
        total_pages = math.ceil(total_count / keyboards.INBOX_PAGE_SIZE)

        await callback.message.edit_reply_markup(reply_markup=await keyboards.inbox_list(letters, total_pages=total_pages))
        return
    
    if not letter.get('is_read'):
        await db.mark_letter_read(letter_id)
    
    await state.update_data(current_letter_id=letter_id)
    await callback.message.delete()
    
    content = letter.get('content', '')
    date_sent = letter.get('created_at').strftime('%d.%m.%Y %H:%M')
    text = MESSAGES["inbox_letter_format"].format(date=date_sent, content=content)
    
    await callback.message.answer(text, reply_markup=await keyboards.letter_options(letter_id))

@router.message(F.text == "📜 Історія листування")
async def view_history(message: Message, state: FSMContext):
    """Показати історію листування з користувачем"""
    data = await state.get_data()
    current_letter_id = data.get("current_letter_id")

    if not current_letter_id:
        await message.answer("Спочатку відкрийте лист!")
        return

    letter = await db.get_letter(current_letter_id)
    if not letter:
        await message.answer("Лист не знайдено.")
        return

    me_id = message.from_user.id
    other_id = letter['sender_id']
    page = 0

    page_letters, total_pages, current_page, total_letters = await db.get_dialogue_history_with_pagination(
        me_id, other_id, page=page, letters_per_page=2
    )

    if not page_letters:
        await message.answer(MESSAGES['thread_empty'])
        return

    await state.update_data(
        history_other_id=other_id, 
        history_page=page,
        history_me_id=me_id
    )

    start_letter_num = page * 2 + 1
    end_letter_num = start_letter_num + len(page_letters) - 1
    text_lines = [f"📜 <b>Історія листування</b> (листи {start_letter_num}-{end_letter_num} з {total_letters})\n〰️〰️〰️〰️〰️〰️\n"]
    end_letter_num = start_letter_num + len(page_letters) - 1
    text_lines = [f"📜 <b>Історія листування</b> (листи {start_letter_num}-{end_letter_num} з {total_letters})\n〰️〰️〰️〰️〰️〰️\n"]

    for msg in page_letters:
        is_me = msg.get('sender_id') == me_id
        role = "🫵 <b>Ви</b>" if is_me else "🦉 <b>Незнайомець</b>"
        
        created_at = msg.get('created_at')
        if created_at:
            date = created_at.strftime('%d.%m %H:%M')
        else:
            date = "??.??"

        content = msg.get('content', '[Текст відсутній]')
        
        text_lines.append(f"{role} [{date}]:\n{content}\n")

    full_text = "\n".join(text_lines)
    
    await message.answer(full_text, parse_mode="HTML", reply_markup=await keyboards.history_nav_v2(current_page, total_pages))

# Відповіді на листи

@router.message(F.text == "✍️ Відповісти")
async def reply_letter(message: Message, state: FSMContext):
    data = await state.get_data()
    letter_id = data.get("current_letter_id")

    if not letter_id:
        await message.answer(MESSAGES['letter_not_found'])
        return
    
    letter = await db.get_letter(letter_id)
    if not letter:
        await message.answer(MESSAGES['letter_not_found'])
        return

    original_sender_id = letter.get('sender_id')
    await state.update_data(reply_to_id=original_sender_id)

    msg = await message.answer("*", reply_markup=ReplyKeyboardRemove())
    await msg.delete()
    
    await message.answer(MESSAGES['reply_prompt'], reply_markup=await keyboards.cancel_menu())
    await state.set_state(InboxState.replying)

@router.message(InboxState.replying, F.text)
async def send_reply(message: Message, state: FSMContext, bot: Bot):
    is_admin = await db.is_user_admin(message.from_user.id)

    if message.text == "🔙 Повернутися назад":
        await state.clear()
        await message.answer(MESSAGES['reply_cancelled'], reply_markup=await keyboards.reply_options(is_admin))
        return
    
    data = await state.get_data()
    recipient_id = data.get("reply_to_id")
    content = message.text
    sender_id = message.from_user.id
    original_letter_id = data.get("current_letter_id")

    if utils.contains_bad_words(content):
        await message.answer(MESSAGES['bad_words_warning'])
        return
    
    if len(content) < 2:
        await message.answer(MESSAGES['letter_too_short_error'])
        return
    
    if len(content) > 1000:
        await message.answer(MESSAGES['letter_too_long_error'].format(max_length=1000))
        return

    delay = 1 
    delivery_time = await db.create_letter(sender_id, recipient_id, content, delay_hours=delay, parent_id=original_letter_id, consume_quota=False)

    if original_letter_id:
        await db.archive_letter(original_letter_id)

    await message.answer(MESSAGES['letter_reply_sent'].format(time=delivery_time.strftime('%H:%M')), 
                         reply_markup=await keyboards.reply_options(is_admin))
    await state.clear()

# Скарги

@router.message(F.text == "⚠️ Поскаржитись")
async def report_letter(message: Message, state: FSMContext, bot: Bot):
    is_admin = await db.is_user_admin(message.from_user.id)
    data = await state.get_data()
    letter_id = data.get('current_letter_id')

    if not letter_id:
        await message.answer(MESSAGES['report_error'], reply_markup=await keyboards.reply_options(is_admin))
        return
    
    letter = await db.report_user_letter(letter_id, message.from_user.id)

    if letter:
        await message.answer(MESSAGES['report_received'], reply_markup=await keyboards.reply_options(is_admin))

        admin_ids = await db.get_admins()
        for admin_id in admin_ids:
            try:
                await bot.send_message(admin_id, MESSAGES['new_report_notification'])
            except Exception:
                pass
    else:
        await message.answer(MESSAGES['report_error'])

@router.message(F.text == "� Цей діалог")
async def view_thread_dialog(message: Message, state: FSMContext):
    """Показати тільки лист цієї нитки (thread)"""
    data = await state.get_data()
    current_letter_id = data.get("current_letter_id")

    if not current_letter_id:
        await message.answer("Спочатку відкрийте лист!")
        return

    letter = await db.get_letter(current_letter_id)
    if not letter:
        await message.answer("Лист не знайдено.")
        return

    me_id = message.from_user.id

    page_size = 10
    page = 0
    thread, total_count = await db.get_thread_page(current_letter_id, page=page, page_size=page_size)

    if not thread:
        await message.answer(MESSAGES['thread_empty'])
        return

    total_pages = max(1, math.ceil(total_count / page_size))
    await state.update_data(
        history_type="thread", 
        history_letter_id=current_letter_id,
        history_page=page, 
        history_page_size=page_size
    )

    text_lines = [MESSAGES['thread_dialog_header'].format(page=page + 1, total_pages=total_pages)]

    for msg in thread:
        is_me = msg.get('sender_id') == me_id
        role = "🫵 Ви" if is_me else "🦉 Незнайомець"
        
        created_at = msg.get('created_at')
        if created_at:
            date = created_at.strftime('%d.%m %H:%M')
        else:
            date = "??.??"

        content = msg.get('content')
        if content is None:
            content = "[Текст відсутній]"

        line = f"<b>{role}</b> [{date}]:\n{str(content)}\n"
        text_lines.append(line)

    full_text = "\n".join(text_lines)
    if len(full_text) > 4000:
        full_text = full_text[-4000:]
        full_text = "...\n" + full_text

    await message.answer(full_text, parse_mode="HTML", reply_markup=await keyboards.history_nav(page, total_pages))

@router.message(F.text == "📚 Всі листи")
async def view_all_letters(message: Message, state: FSMContext):
    """Показати всю історію з цим користувачем"""
    data = await state.get_data()
    current_letter_id = data.get("current_letter_id")

    if not current_letter_id:
        await message.answer("Спочатку відкрийте лист!")
        return

    letter = await db.get_letter(current_letter_id)
    if not letter:
        await message.answer("Лист не знайдено.")
        return

    me_id = message.from_user.id
    other_id = letter['sender_id']

    page_size = 10
    page = 0
    history, total_count = await db.get_dialogue_history_page(me_id, other_id, page=page, page_size=page_size)

    if not history:
        await message.answer(MESSAGES['thread_empty'])
        return

    total_pages = max(1, math.ceil(total_count / page_size))
    await state.update_data(
        history_type="all",
        history_other_id=other_id, 
        history_page=page, 
        history_page_size=page_size
    )

    text_lines = [MESSAGES['thread_all_header'].format(page=page + 1, total_pages=total_pages)]

    for msg in history:
        is_me = msg.get('sender_id') == me_id
        role = "🫵 Ви" if is_me else "🦉 Незнайомець"
        
        created_at = msg.get('created_at')
        if created_at:
            date = created_at.strftime('%d.%m %H:%M')
        else:
            date = "??.??"

        content = msg.get('content')
        if content is None:
            content = "[Текст відсутній]"

        line = f"<b>{role}</b> [{date}]:\n{str(content)}\n"
        text_lines.append(line)

    full_text = "\n".join(text_lines)
    if len(full_text) > 4000:
        full_text = full_text[-4000:]
        full_text = "...\n" + full_text

    await message.answer(full_text, parse_mode="HTML", reply_markup=await keyboards.history_nav(page, total_pages))

@router.callback_query(F.data.startswith("history_page_"))
async def change_history_page(callback: CallbackQuery, state: FSMContext):
    """Навігація по сторінках історії листування"""
    page = int(callback.data.split("_")[2])
    data = await state.get_data()

    other_id = data.get("history_other_id")
    me_id = data.get("history_me_id")

    if not other_id or not me_id:
        await callback.answer(MESSAGES['session_lost'], show_alert=True)
        return

    page_letters, total_pages, current_page, total_letters = await db.get_dialogue_history_with_pagination(
        me_id, other_id, page=page, letters_per_page=2
    )

    if not page_letters:
        await callback.answer("Сторінка більше недоступна")
        return

    await state.update_data(history_page=page)

    start_letter_num = page * 2 + 1
    end_letter_num = start_letter_num + len(page_letters) - 1
    text_lines = [f"📜 <b>Історія листування</b> (листи {start_letter_num}-{end_letter_num} з {total_letters})\n〰️〰️〰️〰️〰️〰️\n"]

    for msg in page_letters:
        is_me = msg.get('sender_id') == me_id
        role = "🫵 <b>Ви</b>" if is_me else "🦉 <b>Незнайомець</b>"

        created_at = msg.get('created_at')
        if created_at:
            date = created_at.strftime('%d.%m %H:%M')
        else:
            date = "??.??"

        content = msg.get('content', '[Текст відсутній]')
        text_lines.append(f"{role} [{date}]:\n{content}\n")

    full_text = "\n".join(text_lines)
    await callback.message.edit_text(full_text, parse_mode="HTML", reply_markup=await keyboards.history_nav_v2(current_page, total_pages))
    await callback.answer()

@router.callback_query(F.data == "close_history")
async def close_history(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()

    data = await state.get_data()
    letter_id = data.get("current_letter_id")

    if not letter_id:
        await callback.answer(MESSAGES['session_lost'], show_alert=True)
        return

    letter = await db.get_letter(letter_id)

    if not letter:
        await callback.answer(MESSAGES['letter_not_found'], show_alert=True)
        return

    content = letter.get('content', '')
    created_at = letter.get('created_at')
    date_str = created_at.strftime('%d.%m %H:%M') if created_at else "Невідомо"
    
    await state.update_data(history_other_id=None, history_page=None, history_me_id=None)
    
    await callback.message.answer(MESSAGES['inbox_letter_format'].format(date=date_str, content=content), parse_mode="HTML", reply_markup=await keyboards.letter_options(letter_id))

# Архівування листів

@router.message(F.text == "🗃 Архівувати")
async def archive_letter(message: Message, state: FSMContext):
    data = await state.get_data()
    letter_id = data.get('current_letter_id')
    is_admin = await db.is_user_admin(message.from_user.id)

    if letter_id:
        await db.archive_letter(letter_id)
        await message.answer(MESSAGES['letter_archived'], reply_markup=await keyboards.reply_options(is_admin))
    else:
        await message.answer(MESSAGES['letter_not_found'], reply_markup=await keyboards.reply_options(is_admin))

    await state.clear()

@router.message(F.text == "🔙 Назад до вхідних")
async def back_to_inbox(message: Message, state: FSMContext):
    msg = await message.answer("*", reply_markup=ReplyKeyboardRemove())
    await msg.delete()
    
    await state.update_data(current_letter_id=None, reply_to_id=None)
    user_id = message.from_user.id
    
    letters, total_count = await db.get_inbox(user_id, page=0, page_size=keyboards.INBOX_PAGE_SIZE)
    is_admin = await db.is_user_admin(user_id)

    if not letters:
        await message.answer(MESSAGES['inbox_empty'], reply_markup=await keyboards.reply_options(is_admin))
    else:
        total_pages = math.ceil(total_count / keyboards.INBOX_PAGE_SIZE)
        await message.answer(MESSAGES['inbox_prompt'].format(count=total_count, page=1, total_pages=total_pages), 
                             reply_markup=await keyboards.inbox_list(letters, page=0, total_pages=total_pages))

# Callback handlers

@router.callback_query(F.data == "close_inbox")
async def close_inbox(callback: CallbackQuery):
    is_admin = await db.is_user_admin(callback.from_user.id)

    await callback.message.delete()
    await callback.message.answer(MESSAGES['menu_prompt'], reply_markup=await keyboards.reply_options(is_admin))

@router.callback_query(F.data == "archive_all_letters")
async def archive_all_inbox_letters(callback: CallbackQuery):
    user_id = callback.from_user.id
    archived_count = await db.archive_all_letters(user_id)
    
    if archived_count > 0:
        await callback.message.answer(f"✅ Заархівовано {archived_count} лист(а/ів)")
        
        letters, total_count = await db.get_inbox(user_id, page=0, page_size=keyboards.INBOX_PAGE_SIZE)
        is_admin = await db.is_user_admin(user_id)
        
        if not letters:
            await callback.message.edit_text(MESSAGES['inbox_empty'])
            await callback.message.delete()
            await callback.message.answer(MESSAGES['menu_prompt'], reply_markup=await keyboards.reply_options(is_admin))
        else:
            total_pages = math.ceil(total_count / keyboards.INBOX_PAGE_SIZE)
            await callback.message.edit_text(
                MESSAGES['inbox_prompt'].format(count=total_count, page=1, total_pages=total_pages),
                reply_markup=await keyboards.inbox_list(letters, page=0, total_pages=total_pages)
            )
    else:
        await callback.answer("📭 Немає листів для архівації", show_alert=True)

@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery):
    await callback.answer()