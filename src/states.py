from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    academic_year = State()
    hobbies_selection = State()


class LetterState(StatesGroup):
    writing_letter = State()


class ProfileState(StatesGroup):
    editing_course = State()
    editing_hobbies = State()


class InboxState(StatesGroup):
    replying = State()
    current_letter_id = State()
    reply_to_id = State()
    renaming_letter = State()


class AdminState(StatesGroup):
    main = State()
    waiting_for_broadcast = State()
    waiting_for_ban = State()
    waiting_for_unban = State()
