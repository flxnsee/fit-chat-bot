import math
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

# Реєстрація: вибір курсу
academic_year = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🐣 1-ий курс", callback_data="first_year"),
            InlineKeyboardButton(text="🎓 2-ий курс", callback_data="second_year")
        ],
        [
            InlineKeyboardButton(text="🧠 3-ий курс", callback_data="third_year"),
            InlineKeyboardButton(text="🦁 4-ий курс", callback_data="fourth_year")
        ],
        [
            InlineKeyboardButton(text="👨‍🎓 5-ий курс", callback_data="fifth_year"),
            InlineKeyboardButton(text="👨‍🏫 6-ий курс", callback_data="sixth_year")
        ]
    ]
)

# Вибір хобі
ALL_HOBBIES = [
    "🎵 Музика", "🎮 Ігри", "📖 Читання", "⚽ Спорт",
    "✈️ Подорожі", "📸 Фото", "🎨 Малювання", "🎬 Кіно",
    "💻 IT/Код", "🌱 Природа", "🍳 Кулінарія", "🎤 Спів"
]

PAGE_SIZE = 6 

async def personal_hobbies(page: int, selected: list[int]):
    builder = InlineKeyboardBuilder()
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    hobbies_on_page = ALL_HOBBIES[start:end]

    for i, hobby in enumerate(hobbies_on_page, start=start):
        status = "✅" if i in selected else "⬜️"
        text = f"{status} {hobby}"
        builder.add(InlineKeyboardButton(text=text, callback_data=f"toggle_{i}_{page}"))

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Туди", callback_data=f"page_{page - 1}"))
    total_pages = math.ceil(len(ALL_HOBBIES) / PAGE_SIZE)
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="Сюди ➡️", callback_data=f"page_{page + 1}"))
    
    if nav_row:
        builder.row(*nav_row)

    builder.row(InlineKeyboardButton(text="💾 Зберегти вибір", callback_data="confirm"))

    return builder.adjust(2).as_markup()

# Головне меню
async def reply_options(is_admin: bool = False):
    builder = ReplyKeyboardBuilder()
    
    builder.row(KeyboardButton(text="✍️ Написати листа"))
    builder.row(KeyboardButton(text="📬 Вхідні листи"), KeyboardButton(text="👤 Профіль"))

    if is_admin:
        builder.row(KeyboardButton(text="🔐 Адмін-панель"))

    return builder.as_markup(resize_keyboard=True)

# Кнопки скасування
async def cancel_menu():
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="🔙 Повернутися назад"))
    return builder.as_markup(resize_keyboard=True)

async def cancel_admin():
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="❌ Скасувати"))
    return builder.as_markup(resize_keyboard=True)

# Налаштування профілю
async def profile_settings(filter_enabled: bool):
    builder = ReplyKeyboardBuilder()

    filter_status = "🟢" if filter_enabled else "🔴"
    filter_text = f"⚙️ Тільки мій курс {filter_status}"

    builder.row(KeyboardButton(text="📚 Змінити курс"), KeyboardButton(text="🎨 Змінити хобі"))
    builder.row(KeyboardButton(text=filter_text))
    builder.row(KeyboardButton(text="🔙 Повернутися назад"))

    return builder.as_markup(resize_keyboard=True)

# Вхідні листи
INBOX_PAGE_SIZE = 5

async def inbox_list(letters, total_pages: int, page: int = 0):
    builder = InlineKeyboardBuilder()

    if not letters:
        builder.row(InlineKeyboardButton(text="🔙 Згорнути скриньку", callback_data="close_inbox"))
        return builder.as_markup()

    for letter in letters:
        is_read = letter.get('is_read', False)
        icon = "📨" if is_read else "🎁"
        
        created_at = letter.get('created_at')
        time_str = created_at.strftime('%H:%M') if created_at else ""
        
        content = letter.get('content', '')
        preview = content[:20] + "..." if len(content) > 20 else content
        btn_text = f"{icon} {time_str} | {preview}"

        builder.add(InlineKeyboardButton(text=btn_text, callback_data=f"read_letter_{letter['_id']}"))

    builder.adjust(1)

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"inbox_page_{page - 1}"))
    
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="Далі ➡️", callback_data=f"inbox_page_{page + 1}"))

    if nav_row:
        builder.row(*nav_row)

    builder.row(InlineKeyboardButton(text="🗂 Архівувати всі", callback_data="archive_all_letters"))
    builder.row(InlineKeyboardButton(text="🔙 Згорнути скриньку", callback_data="close_inbox"))

    return builder.as_markup()

# Дії з листом
async def letter_options(letter_id):
    builder = ReplyKeyboardBuilder()
    
    builder.row(KeyboardButton(text="✍️ Відповісти"))
    builder.row(KeyboardButton(text="� Перейменувати"), KeyboardButton(text="📜 Історія листування"))
    builder.row(KeyboardButton(text="🗃 Архівувати"), KeyboardButton(text="⚠️ Поскаржитись"))
    builder.row(KeyboardButton(text="🔙 Назад до вхідних"))

    return builder.as_markup(resize_keyboard=True)

# Історія листування
async def history_nav_v2(page: int, total_pages: int):
    builder = InlineKeyboardBuilder()

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"history_page_{page - 1}"))
    
    nav_row.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="Далі ➡️", callback_data=f"history_page_{page + 1}"))
    
    builder.row(*nav_row)
    builder.row(InlineKeyboardButton(text="🔙 Повернутися до листа", callback_data="close_history"))

    return builder.as_markup()

# Адмін-панель
async def admin_menu():
    builder = ReplyKeyboardBuilder()

    builder.row(KeyboardButton(text="🚨 Скарги"), KeyboardButton(text="📊 Статистика"))
    builder.row(KeyboardButton(text="📢 Розсилка"))
    builder.row(KeyboardButton(text="🔨 Бан"), KeyboardButton(text="🕊️ Розбан"))
    builder.row(KeyboardButton(text="🔙 Вийти з адмін-панелі"))

    return builder.as_markup(resize_keyboard=True)

async def admin_report_actions(sender_id: int, letter_id: str):
    builder = InlineKeyboardBuilder()
    
    builder.add(InlineKeyboardButton(text="🔨 Бан", callback_data=f"adm_ban_{sender_id}_{letter_id}"))
    builder.add(InlineKeyboardButton(text="⚠️ Варн", callback_data=f"adm_warn_{sender_id}_{letter_id}"))
    builder.add(InlineKeyboardButton(text="🗑 Відхилити", callback_data=f"adm_dismiss_{sender_id}_{letter_id}"))
    
    return builder.adjust(2).as_markup()

async def letter_ban(user_id):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🚫 Заблокувати користувача", callback_data=f"ban_user_{user_id}"))
    return builder.as_markup()