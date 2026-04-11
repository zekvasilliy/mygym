import os
import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Optional

import psycopg
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))
DATABASE_URL = os.getenv("DATABASE_URL")
RENDER_EXTERNAL_URL = "https://mygym-amow.onrender.com"

if not TOKEN:
    raise ValueError("Не найдена переменная BOT_TOKEN")

if not DATABASE_URL:
    raise ValueError("Не найдена переменная DATABASE_URL")

MAIN_PROGRAM = "main"
ZEYNAL_PROGRAM = "zeynal"
ZEYNAL_DAY_NAME = "Зейнал"

STATE_MAIN_MENU = "main_menu"
STATE_SELECT_DAY = "select_day"
STATE_SELECT_EXERCISE = "select_exercise"
STATE_ENTER_WEIGHT = "enter_weight"
STATE_EDIT_WEIGHT = "edit_weight"
STATE_TRACK_DAY = "track_day"
STATE_TRACK_EXERCISE = "track_exercise"
STATE_ZEYNAL_EXERCISE = "zeynal_exercise"
STATE_ZEYNAL_ENTER_WEIGHT = "zeynal_enter_weight"

WORKOUTS: Dict[str, List[str]] = {
    "Грудь - Трицепс": [
        "Жим лежа",
        "Бабочка",
        "Жим лежа на верх груди",
        "Сведение в кроссовере",
        "Французский жим",
        "Жим для трицепса",
        "Жим гантели из-за головы",
        "Канат / палка / и тд",
        "Пресс лежа",
        "Пресс на турнике",
    ],
    "Спина - Бицепс": [
        "Тяга на 1 руке",
        "Вертикальная тяга",
        "Горизонтальная тяга",
        "С блином в руках",
        "Сгибание рук со штангой",
        "Тренажер Скотта",
        "Сгибание на наклонной скамье",
        "Молоток",
        "Пресс лежа",
        "Пресс на турнике",
    ],
    "Плечи - Ноги": [
        "Приседание со штангой",
        "Шайтан машина - жим ног",
        "Шагать с гантелями",
        "Разгибание ног",
        "Поднятие грифа",
        "Мах гантелей",
        "Жим от Арнольда",
        "Обратная бабочка",
        "Пресс лежа",
        "Пресс на турнике",
    ],
}

ZEYNAL_WORKOUTS = [
    "Подтягивания",
    "Отжимания",
    "Бицепс",
    "Трицепс",
    "Средняя дельта",
    "Пресс",
]

ALL_MAIN_EXERCISES = sorted({exercise for exercises in WORKOUTS.values() for exercise in exercises})

WELCOME_TEXT = (
    "Добро пожаловать в трекер тренировок.\n\n"
    "Start больше не нужен — просто нажимай нужную кнопку.\n"
    "Кнопка 'Выйти' полностью закрывает клавиатуру бота.\n"
    "Раздел 'Зейнал' хранится отдельно от обычных тренировок.\n\n"
    "Выбери нужную функцию."
)

HELP_TEXT = (
    "Как пользоваться ботом:\n\n"
    "1. Нажимай нужную кнопку сразу.\n"
    "2. Для обычной тренировки выбери день и упражнение.\n"
    "3. Для блока 'Зейнал' жми кнопку 'Зейнал'.\n"
    "4. Если ошибся в цифре, нажми 'Изменить последнее'.\n"
    "5. Чтобы полностью выйти из бота и убрать клавиатуру — нажми 'Выйти'."
)


def get_connection():
    return psycopg.connect(DATABASE_URL, connect_timeout=5)


def init_db():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS workout_logs (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    username TEXT,
                    day_name TEXT NOT NULL,
                    exercise_name TEXT NOT NULL,
                    weight TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )
            cur.execute(
                """
                ALTER TABLE workout_logs
                ADD COLUMN IF NOT EXISTS program_name TEXT NOT NULL DEFAULT 'main'
                """
            )
        conn.commit()


def save_weight_sync(
    user_id: int,
    username: str,
    program_name: str,
    day_name: str,
    exercise_name: str,
    weight: str,
):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO workout_logs (
                    user_id,
                    username,
                    program_name,
                    day_name,
                    exercise_name,
                    weight,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    username,
                    program_name,
                    day_name,
                    exercise_name,
                    weight,
                    datetime.now(),
                ),
            )
        conn.commit()


def get_last_weights_for_day_sync(user_id: int, program_name: str, day_name: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT exercise_name, weight, created_at
                FROM workout_logs
                WHERE user_id = %s AND program_name = %s AND day_name = %s
                ORDER BY id DESC
                """,
                (user_id, program_name, day_name),
            )
            rows = cur.fetchall()

    latest = {}
    for exercise_name, weight, created_at in rows:
        if exercise_name not in latest:
            latest[exercise_name] = (weight, created_at.strftime("%Y-%m-%d %H:%M:%S"))
    return latest


def get_history_for_exercise_sync(user_id: int, program_name: str, day_name: str, exercise_name: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT weight, created_at
                FROM workout_logs
                WHERE user_id = %s AND program_name = %s AND day_name = %s AND exercise_name = %s
                ORDER BY id DESC
                """,
                (user_id, program_name, day_name, exercise_name),
            )
            rows = cur.fetchall()

    return [(weight, created_at.strftime("%Y-%m-%d %H:%M:%S")) for weight, created_at in rows]


def get_last_record_for_exercise_sync(
    user_id: int,
    program_name: str,
    day_name: str,
    exercise_name: str,
):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, weight, created_at
                FROM workout_logs
                WHERE user_id = %s AND program_name = %s AND day_name = %s AND exercise_name = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id, program_name, day_name, exercise_name),
            )
            row = cur.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "weight": row[1],
        "created_at": row[2].strftime("%Y-%m-%d %H:%M:%S"),
    }


def update_weight_record_sync(record_id: int, new_weight: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE workout_logs
                SET weight = %s
                WHERE id = %s
                """,
                (new_weight, record_id),
            )
        conn.commit()


def build_keyboard(keyboard: List[List[str]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=False,
    )


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        ["Старт тренировки", "Отслежение весов"],
        ["Зейнал", "Выйти"],
    ]
    return build_keyboard(keyboard)


def get_days_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        ["Грудь - Трицепс"],
        ["Спина - Бицепс"],
        ["Плечи - Ноги"],
        ["Назад", "Выйти"],
    ]
    return build_keyboard(keyboard)


def get_exercises_keyboard(day_name: str) -> ReplyKeyboardMarkup:
    keyboard = [[exercise] for exercise in WORKOUTS[day_name]]
    keyboard.append(["Назад", "Выйти"])
    return build_keyboard(keyboard)


def get_zeynal_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        ["Подтягивания", "Отжимания"],
        ["Бицепс", "Трицепс"],
        ["Средняя дельта", "Пресс"],
        ["Назад", "Выйти"],
    ]
    return build_keyboard(keyboard)


def get_weight_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        ["Изменить последнее"],
        ["Назад", "Выйти"],
    ]
    return build_keyboard(keyboard)


def default_session() -> Dict[str, Optional[str]]:
    return {
        "state": STATE_MAIN_MENU,
        "program_name": None,
        "selected_day": None,
        "selected_exercise": None,
        "track_day": None,
    }


def get_session(context: ContextTypes.DEFAULT_TYPE) -> Dict[str, Optional[str]]:
    session = context.user_data.get("session")
    if not session:
        session = default_session()
        context.user_data["session"] = session
    return session


def save_session(context: ContextTypes.DEFAULT_TYPE, **updates) -> Dict[str, Optional[str]]:
    session = get_session(context)
    session.update(updates)
    return session


def reset_session(context: ContextTypes.DEFAULT_TYPE):
    context.user_data["session"] = default_session()


def find_days_for_exercise(exercise_name: str) -> List[str]:
    return [day for day, exercises in WORKOUTS.items() if exercise_name in exercises]


async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    reset_session(context)
    await update.message.reply_text(text, reply_markup=get_main_menu_keyboard())


async def exit_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_session(context)
    await update.message.reply_text(
        "Ты вышел из бота.\n\nЧтобы открыть меню снова, нажми /start.",
        reply_markup=ReplyKeyboardRemove(),
    )


async def send_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_session(context)
    await update.message.reply_text(HELP_TEXT, reply_markup=get_main_menu_keyboard())


async def send_day_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_session(
        context,
        state=STATE_SELECT_DAY,
        program_name=MAIN_PROGRAM,
        selected_day=None,
        selected_exercise=None,
        track_day=None,
    )
    await update.message.reply_text("Выбери день тренировки:", reply_markup=get_days_keyboard())


async def send_zeynal_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_session(
        context,
        state=STATE_ZEYNAL_EXERCISE,
        program_name=ZEYNAL_PROGRAM,
        selected_day=ZEYNAL_DAY_NAME,
        selected_exercise=None,
        track_day=None,
    )
    await update.message.reply_text(
        "Раздел 'Зейнал'. Эти записи хранятся отдельно от основного отслеживания.\n\n"
        "Выбери упражнение:",
        reply_markup=get_zeynal_keyboard(),
    )


async def send_main_day_exercises(update: Update, context: ContextTypes.DEFAULT_TYPE, day_name: str):
    save_session(
        context,
        state=STATE_SELECT_EXERCISE,
        program_name=MAIN_PROGRAM,
        selected_day=day_name,
        selected_exercise=None,
        track_day=None,
    )
    await update.message.reply_text(
        f"Выбран день: {day_name}\n\nТеперь выбери упражнение:",
        reply_markup=get_exercises_keyboard(day_name),
    )


async def prompt_for_weight(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    program_name: str,
    day_name: str,
    exercise_name: str,
    state: str,
):
    last_record = await asyncio.to_thread(
        get_last_record_for_exercise_sync,
        user_id,
        program_name,
        day_name,
        exercise_name,
    )
    last_info = ""

    if last_record:
        last_info = (
            f"\nПоследний записанный вес: {last_record['weight']} "
            f"({last_record['created_at']})"
        )

    save_session(
        context,
        state=state,
        program_name=program_name,
        selected_day=day_name,
        selected_exercise=exercise_name,
        track_day=None,
    )

    await update.message.reply_text(
        f"Упражнение: {exercise_name}{last_info}\n\n"
        "Теперь введи рабочий вес сообщением.\n"
        "Например: 60 кг или 3x10 по 50\n\n"
        "Если ошибся в прошлой записи — нажми 'Изменить последнее'.",
        reply_markup=get_weight_keyboard(),
    )


async def send_track_day_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_session(
        context,
        state=STATE_TRACK_DAY,
        program_name=MAIN_PROGRAM,
        selected_day=None,
        selected_exercise=None,
        track_day=None,
    )
    await update.message.reply_text(
        "Выбери день, по которому хочешь посмотреть веса:",
        reply_markup=get_days_keyboard(),
    )


async def send_track_day_result(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, day_name: str):
    latest = await asyncio.to_thread(get_last_weights_for_day_sync, user_id, MAIN_PROGRAM, day_name)

    save_session(
        context,
        state=STATE_TRACK_EXERCISE,
        program_name=MAIN_PROGRAM,
        selected_day=None,
        selected_exercise=None,
        track_day=day_name,
    )

    if not latest:
        await update.message.reply_text(
            f"По дню '{day_name}' пока нет сохраненных весов.\n\n"
            "Выбери упражнение, если хочешь посмотреть историю, или вернись назад.",
            reply_markup=get_exercises_keyboard(day_name),
        )
        return

    lines = [f"Последние веса по дню: {day_name}\n"]
    for exercise in WORKOUTS[day_name]:
        if exercise in latest:
            weight, created_at = latest[exercise]
            lines.append(f"• {exercise} — {weight} ({created_at})")
        else:
            lines.append(f"• {exercise} — нет записей")

    lines.append("\nТеперь выбери упражнение, чтобы посмотреть полную историю.")
    await update.message.reply_text("\n".join(lines), reply_markup=get_exercises_keyboard(day_name))


async def send_track_exercise_history(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    day_name: str,
    exercise_name: str,
):
    history = await asyncio.to_thread(
        get_history_for_exercise_sync,
        user_id,
        MAIN_PROGRAM,
        day_name,
        exercise_name,
    )

    save_session(
        context,
        state=STATE_TRACK_EXERCISE,
        program_name=MAIN_PROGRAM,
        selected_day=None,
        selected_exercise=None,
        track_day=day_name,
    )

    if not history:
        await update.message.reply_text(
            f"По упражнению '{exercise_name}' пока нет записей.",
            reply_markup=get_exercises_keyboard(day_name),
        )
        return

    lines = [f"История по упражнению: {exercise_name}\n"]
    for weight, created_at in history[:20]:
        lines.append(f"• {weight} — {created_at}")

    await update.message.reply_text("\n".join(lines), reply_markup=get_exercises_keyboard(day_name))


async def start_edit_last_weight(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    session: Dict[str, Optional[str]],
):
    program_name = session.get("program_name")
    day_name = session.get("selected_day")
    exercise_name = session.get("selected_exercise")

    if not program_name or not day_name or not exercise_name:
        await update.message.reply_text(
            "Сначала выбери упражнение, потом можно изменить последнее значение.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    last_record = await asyncio.to_thread(
        get_last_record_for_exercise_sync,
        user_id,
        program_name,
        day_name,
        exercise_name,
    )
    if not last_record:
        await update.message.reply_text(
            "По этому упражнению пока нечего менять.",
            reply_markup=get_weight_keyboard(),
        )
        return

    save_session(
        context,
        state=STATE_EDIT_WEIGHT,
        program_name=program_name,
        selected_day=day_name,
        selected_exercise=exercise_name,
        track_day=None,
    )

    await update.message.reply_text(
        f"Сейчас последнее значение по упражнению '{exercise_name}': "
        f"{last_record['weight']} ({last_record['created_at']})\n\n"
        "Пришли новый вес сообщением.",
        reply_markup=get_weight_keyboard(),
    )


async def apply_weight_edit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    session: Dict[str, Optional[str]],
    new_weight: str,
):
    program_name = session.get("program_name")
    day_name = session.get("selected_day")
    exercise_name = session.get("selected_exercise")

    if not program_name or not day_name or not exercise_name:
        await send_main_menu(update, context, "Что-то сбилось. Открыл главное меню.")
        return

    last_record = await asyncio.to_thread(
        get_last_record_for_exercise_sync,
        user_id,
        program_name,
        day_name,
        exercise_name,
    )
    if not last_record:
        await update.message.reply_text(
            "Не нашел запись для изменения. Выбери упражнение заново.",
            reply_markup=get_main_menu_keyboard(),
        )
        reset_session(context)
        return

    await asyncio.to_thread(update_weight_record_sync, last_record["id"], new_weight)

    if program_name == ZEYNAL_PROGRAM:
        save_session(
            context,
            state=STATE_ZEYNAL_EXERCISE,
            program_name=ZEYNAL_PROGRAM,
            selected_day=ZEYNAL_DAY_NAME,
            selected_exercise=None,
            track_day=None,
        )
        reply_markup = get_zeynal_keyboard()
        location_text = "Блок: Зейнал"
    else:
        save_session(
            context,
            state=STATE_SELECT_EXERCISE,
            program_name=MAIN_PROGRAM,
            selected_day=day_name,
            selected_exercise=None,
            track_day=None,
        )
        reply_markup = get_exercises_keyboard(day_name)
        location_text = f"День: {day_name}"

    await update.message.reply_text(
        "Последнее значение изменено.\n"
        f"{location_text}\n"
        f"Упражнение: {exercise_name}\n"
        f"Новый вес: {new_weight}\n\n"
        "Можешь выбрать следующее упражнение.",
        reply_markup=reply_markup,
    )


async def save_new_weight(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    session: Dict[str, Optional[str]],
    weight_text: str,
):
    program_name = session.get("program_name") or MAIN_PROGRAM
    day_name = session.get("selected_day")
    exercise_name = session.get("selected_exercise")

    if not day_name or not exercise_name:
        await send_main_menu(update, context, "Что-то сбилось. Открыл главное меню.")
        return

    await asyncio.to_thread(
        save_weight_sync,
        user_id,
        update.effective_user.username or "",
        program_name,
        day_name,
        exercise_name,
        weight_text,
    )

    if program_name == ZEYNAL_PROGRAM:
        save_session(
            context,
            state=STATE_ZEYNAL_EXERCISE,
            program_name=ZEYNAL_PROGRAM,
            selected_day=ZEYNAL_DAY_NAME,
            selected_exercise=None,
            track_day=None,
        )
        reply_markup = get_zeynal_keyboard()
        block_text = "Блок: Зейнал"
    else:
        save_session(
            context,
            state=STATE_SELECT_EXERCISE,
            program_name=MAIN_PROGRAM,
            selected_day=day_name,
            selected_exercise=None,
            track_day=None,
        )
        reply_markup = get_exercises_keyboard(day_name)
        block_text = f"День: {day_name}"

    await update.message.reply_text(
        "Сохранено:\n"
        f"{block_text}\n"
        f"Упражнение: {exercise_name}\n"
        f"Вес: {weight_text}\n\n"
        "Можешь выбрать следующее упражнение.",
        reply_markup=reply_markup,
    )


async def handle_back(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Dict[str, Optional[str]]):
    state = session.get("state")
    program_name = session.get("program_name")
    selected_day = session.get("selected_day")

    if state in {STATE_MAIN_MENU, None}:
        await send_main_menu(update, context, "Ты уже в главном меню.")
        return

    if state == STATE_SELECT_DAY:
        await send_main_menu(update, context, "Главное меню:")
        return

    if state == STATE_SELECT_EXERCISE:
        await send_day_selection(update, context)
        return

    if state == STATE_TRACK_DAY:
        await send_main_menu(update, context, "Главное меню:")
        return

    if state == STATE_TRACK_EXERCISE:
        await send_track_day_selection(update, context)
        return

    if state == STATE_ZEYNAL_EXERCISE:
        await send_main_menu(update, context, "Главное меню:")
        return

    if state in {STATE_ENTER_WEIGHT, STATE_EDIT_WEIGHT}:
        if program_name == ZEYNAL_PROGRAM:
            await send_zeynal_menu(update, context)
            return
        if selected_day and selected_day in WORKOUTS:
            await send_main_day_exercises(update, context, selected_day)
            return
        await send_day_selection(update, context)
        return

    if state == STATE_ZEYNAL_ENTER_WEIGHT:
        await send_zeynal_menu(update, context)
        return

    await send_main_menu(update, context, "Главное меню:")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_main_menu(update, context, WELCOME_TEXT)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_help(update, context)


async def route_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    user_id = update.effective_user.id
    session = get_session(context)
    state = session.get("state")

    if text == "Start":
        await send_main_menu(update, context, "Start больше не нужен. Просто нажимай кнопки.")
        return

    if text == "Помощь":
        await send_help(update, context)
        return

    if text in {"Выйти", "Отмена"}:
        await exit_bot(update, context)
        return

    if text == "Назад":
        await handle_back(update, context, session)
        return

    if text in {"/start", "Меню"}:
        await send_main_menu(update, context, WELCOME_TEXT)
        return

    if text == "Старт тренировки":
        await send_day_selection(update, context)
        return

    if text == "Отслежение весов":
        await send_track_day_selection(update, context)
        return

    if text == "Зейнал":
        await send_zeynal_menu(update, context)
        return

    if text in WORKOUTS:
        if state in {STATE_TRACK_DAY, STATE_TRACK_EXERCISE}:
            await send_track_day_result(update, context, user_id, text)
        else:
            await send_main_day_exercises(update, context, text)
        return

    if text in ZEYNAL_WORKOUTS:
        await prompt_for_weight(
            update,
            context,
            user_id,
            ZEYNAL_PROGRAM,
            ZEYNAL_DAY_NAME,
            text,
            STATE_ZEYNAL_ENTER_WEIGHT,
        )
        return

    if text == "Изменить последнее":
        await start_edit_last_weight(update, context, user_id, session)
        return

    if state == STATE_TRACK_EXERCISE:
        track_day = session.get("track_day")
        if track_day and text in WORKOUTS.get(track_day, []):
            await send_track_exercise_history(update, context, user_id, track_day, text)
            return

    if state in {STATE_SELECT_EXERCISE, STATE_ENTER_WEIGHT, STATE_EDIT_WEIGHT}:
        selected_day = session.get("selected_day")
        if selected_day and text in WORKOUTS.get(selected_day, []):
            await prompt_for_weight(
                update,
                context,
                user_id,
                MAIN_PROGRAM,
                selected_day,
                text,
                STATE_ENTER_WEIGHT,
            )
            return

    if text in ALL_MAIN_EXERCISES:
        matched_days = find_days_for_exercise(text)
        if len(matched_days) == 1:
            day_name = matched_days[0]
            if state in {STATE_TRACK_DAY, STATE_TRACK_EXERCISE}:
                await send_track_exercise_history(update, context, user_id, day_name, text)
            else:
                await prompt_for_weight(
                    update,
                    context,
                    user_id,
                    MAIN_PROGRAM,
                    day_name,
                    text,
                    STATE_ENTER_WEIGHT,
                )
            return

        if state in {STATE_TRACK_DAY, STATE_TRACK_EXERCISE}:
            save_session(
                context,
                state=STATE_TRACK_DAY,
                program_name=MAIN_PROGRAM,
                selected_day=None,
                selected_exercise=None,
                track_day=None,
            )
        else:
            save_session(
                context,
                state=STATE_SELECT_DAY,
                program_name=MAIN_PROGRAM,
                selected_day=None,
                selected_exercise=None,
                track_day=None,
            )

        await update.message.reply_text(
            "Это упражнение есть в нескольких днях. Сначала выбери день кнопкой.",
            reply_markup=get_days_keyboard(),
        )
        return

    if state == STATE_EDIT_WEIGHT:
        await apply_weight_edit(update, context, user_id, session, text)
        return

    if state in {STATE_ENTER_WEIGHT, STATE_ZEYNAL_ENTER_WEIGHT}:
        await save_new_weight(update, context, user_id, session, text)
        return

    if state == STATE_SELECT_DAY:
        await update.message.reply_text("Выбери день кнопкой.", reply_markup=get_days_keyboard())
        return

    if state == STATE_TRACK_DAY:
        await update.message.reply_text("Выбери день кнопкой.", reply_markup=get_days_keyboard())
        return

    if state == STATE_ZEYNAL_EXERCISE:
        await update.message.reply_text("Выбери упражнение кнопкой.", reply_markup=get_zeynal_keyboard())
        return

    await update.message.reply_text("Выбери нужную кнопку.", reply_markup=get_main_menu_keyboard())


def main():
    init_db()

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route_text))

    webhook_path = TOKEN
    webhook_url = f"{RENDER_EXTERNAL_URL}/{TOKEN}"

    logger.info(f"Webhook URL: {webhook_url}")

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=webhook_path,
        webhook_url=webhook_url,
    )


if __name__ == "__main__":
    main()
