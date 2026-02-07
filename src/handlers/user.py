from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.filters import CommandStart, Command, or_f
from aiogram.fsm.context import FSMContext

from src.states import Registration, ProfileState
from src.messages import MESSAGES
import src.keyboards as keyboards
import src.database as db

router = Router()

# Реєстрація та старт

@router.message(F.text == "curly hair")
async def curly_hair(message: Message):
    await message.answer("кірюшка баранчик лєхєнда)0))))")

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(MESSAGES['welcome'])

    is_registered = await db.check_user_exists(message.from_user.id)

    if is_registered:
        is_admin = await db.is_user_admin(message.from_user.id)
        await message.answer(MESSAGES['menu_prompt'], reply_markup=await keyboards.reply_options(is_admin))
    else:
        await message.answer(MESSAGES['ask_course'], reply_markup=keyboards.academic_year)
        await state.set_state(Registration.academic_year)

@router.callback_query(Registration.academic_year, F.data.in_(["first_year", "second_year", "third_year", "fourth_year"]))
async def academic_year(callback: CallbackQuery, state: FSMContext):
    course_map = {
        "first_year": "1-ий",
        "second_year": "2-ий",
        "third_year": "3-ий",
        "fourth_year": "4-ий",
    }

    selected_course = course_map.get(callback.data)

    await state.update_data(course=selected_course, hobbies=[])
    await state.set_state(Registration.hobbies_selection)

    await callback.answer(f"{selected_course} курс")
    await callback.message.edit_text(
        MESSAGES['ask_hobbies'], 
        reply_markup=await keyboards.personal_hobbies(page=0, selected=[])
    )

# Вибір хобі

@router.callback_query(or_f(Registration.hobbies_selection, ProfileState.editing_hobbies), F.data.startswith("toggle_"))
async def toggle_hobby(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("hobbies", [])

    parts = callback.data.split("_")
    hobby_index = int(parts[1])
    page = int(parts[2])

    if hobby_index in selected:
        selected.remove(hobby_index)
    else:
        selected.append(hobby_index)

    await state.update_data(hobbies=selected)

    await callback.message.edit_text(
        MESSAGES['ask_hobbies'],
        reply_markup=await keyboards.personal_hobbies(page, selected)
    )

@router.callback_query(or_f(Registration.hobbies_selection, ProfileState.editing_hobbies), F.data.startswith("page_"))
async def change_page(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("hobbies", [])

    page = int(callback.data.split("_")[1])

    await callback.message.edit_text(
        MESSAGES['ask_hobbies'],
        reply_markup=await keyboards.personal_hobbies(page, selected)
    )
    await callback.answer()

@router.callback_query(or_f(Registration.hobbies_selection, ProfileState.editing_hobbies), F.data == "confirm")
async def confirm_hobbies(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("hobbies", [])
    course = data.get("course")
    is_admin = await db.is_user_admin(callback.message.from_user.id)

    current_state = await state.get_state()

    if len(selected) < 2:
        await callback.answer("Помилка!")
        await callback.message.edit_text(
            MESSAGES['hobbies_error'], 
            reply_markup=await keyboards.personal_hobbies(page=0, selected=selected)
        )
    else:
        hobbies_list = [keyboards.ALL_HOBBIES[i] for i in selected]
        await db.store_user(callback.from_user.id, hobbies_list, course)
        
        await state.clear()
        await callback.message.delete()

        if current_state == Registration.hobbies_selection:
            await callback.message.answer(MESSAGES['menu_prompt'], reply_markup=await keyboards.reply_options(is_admin))
        else:
            await callback.message.answer(MESSAGES['hobbies_saved'], reply_markup=await keyboards.reply_options(is_admin))

# Профіль та налаштування

@router.message(or_f(Command("profile"), F.text == "👤 Профіль"))
async def cmd_profile(message: Message):
    user_data = await db.get_user(message.from_user.id)

    if user_data:
        hobbies_formatted = ", ".join(user_data.get('hobbies', []))
        course = user_data.get('course', 'Не вказано')
        settings = user_data.get('settings', {'filter_course': False})

        text = MESSAGES['profile_format'].format(course, hobbies_formatted)

        await message.answer(text, reply_markup=await keyboards.profile_settings(settings['filter_course']))
    else:
        await message.answer("Профіль не знайдено. Натисніть /start для початку!")

@router.message(F.text == "🔙 Повернутися назад")
async def close_profile(message: Message):
    is_admin = await db.is_user_admin(message.from_user.id)
    await message.answer(MESSAGES['menu_prompt'], reply_markup=await keyboards.reply_options(is_admin))

@router.message(F.text == "📚 Змінити курс")
async def edit_course(message: Message, state: FSMContext):
    msg = await message.answer("*", reply_markup=ReplyKeyboardRemove())
    await msg.delete()

    await state.set_state(ProfileState.editing_course)
    await message.answer(MESSAGES['ask_course'], reply_markup=keyboards.academic_year)

@router.callback_query(ProfileState.editing_course, F.data.in_(["first_year", "second_year", "third_year", "fourth_year"]))
async def update_course(callback: CallbackQuery, state: FSMContext):
    course_map = {
        "first_year": "1-ий",
        "second_year": "2-ий",
        "third_year": "3-ий",
        "fourth_year": "4-ий",
    }

    new_course = course_map.get(callback.data)
    user_data = await db.get_user(callback.from_user.id)
    current_hobbies = user_data.get('hobbies', [])
    is_admin = await db.is_user_admin(callback.from_user.id)

    await db.store_user(callback.from_user.id, current_hobbies, new_course)
    await state.clear()

    await callback.message.delete()
    await callback.message.answer(f"✅ Курс змінено на {new_course}!", reply_markup=await keyboards.reply_options(is_admin))

@router.message(F.text == "🎨 Змінити хобі")
async def edit_hobbies(message: Message, state: FSMContext):
    msg = await message.answer("*", reply_markup=ReplyKeyboardRemove())
    await msg.delete()

    user_data = await db.get_user(message.from_user.id)
    current_hobbies_list = user_data.get('hobbies', [])

    selected_indices = []
    for h in current_hobbies_list:
        if h in keyboards.ALL_HOBBIES:
            selected_indices.append(keyboards.ALL_HOBBIES.index(h))

    await state.update_data(hobbies=selected_indices)
    await state.set_state(ProfileState.editing_hobbies)

    await message.answer(
        MESSAGES['ask_hobbies'], 
        reply_markup=await keyboards.personal_hobbies(page=0, selected=selected_indices)
    )

@router.message(F.text.startswith("⚙️"))
async def toggle_filter(message: Message):
    new_state = await db.toggle_filter_course(message.from_user.id)
    state_text = "🟢 УВІМКНЕНО" if new_state else "🔴 ВИМКНЕНО"
    
    await message.answer(
        f"Фільтр за курсом: {state_text}", 
        reply_markup=await keyboards.profile_settings(new_state)
    )