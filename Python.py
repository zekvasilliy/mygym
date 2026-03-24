import os
import psycopg
import logging
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))
RENDER_EXTERNAL_URL = "https://mygym-amow.onrender.com"

if not TOKEN:
    raise ValueError("Не найдена переменная BOT_TOKEN")

if not RENDER_EXTERNAL_URL:
    raise ValueError("Не найдена переменная RENDER_EXTERNAL_URL")

DATABASE_URL = os.getenv("DATABASE_URL")

MAIN_MENU, SELECT_DAY, SELECT_EXERCISE, ENTER_WEIGHT, TRACK_DAY, TRACK_EXERCISE = range(6)

WORKOUTS = {
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


def init_db():
    conn = psycopg.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS workout_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            day_name TEXT NOT NULL,
            exercise_name TEXT NOT NULL,
            weight TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def save_weight(user_id: int, username: str, day_name: str, exercise_name: str, weight: str):
    conn = psycopg.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO workout_logs (user_id, username, day_name, exercise_name, weight, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        username,
        day_name,
        exercise_name,
        weight,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()


def get_last_weights_for_day(user_id: int, day_name: str):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        SELECT exercise_name, weight, created_at
        FROM workout_logs
        WHERE user_id = ? AND day_name = ?
        ORDER BY id DESC
    """, (user_id, day_name))

    rows = cur.fetchall()
    conn.close()

    latest = {}
    for exercise_name, weight, created_at in rows:
        if exercise_name not in latest:
            latest[exercise_name] = (weight, created_at)

    return latest


def get_history_for_exercise(user_id: int, day_name: str, exercise_name: str):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        SELECT weight, created_at
        FROM workout_logs
        WHERE user_id = ? AND day_name = ? AND exercise_name = ?
        ORDER BY id DESC
    """, (user_id, day_name, exercise_name))

    rows = cur.fetchall()
    conn.close()
    return rows


def get_main_menu_keyboard():
    keyboard = [
        ["Старт тренировки", "Отслежение весов"],
        ["Помощь", "Отмена"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_days_keyboard():
    keyboard = [
        ["Грудь - Трицепс"],
        ["Спина - Бицепс"],
        ["Плечи - Ноги"],
        ["Назад", "Отмена"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_exercises_keyboard(day_name: str):
    exercises = WORKOUTS[day_name]
    keyboard = [[exercise] for exercise in exercises]
    keyboard.append(["Назад", "Отмена"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "Добро пожаловать в трекер тренировок.\n\nЧто хочешь сделать?"
    await update.message.reply_text(text, reply_markup=get_main_menu_keyboard())
    return MAIN_MENU


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Как пользоваться ботом:\n\n"
        "1. Нажми 'Старт тренировки'\n"
        "2. Выбери день тренировки\n"
        "3. Выбери упражнение\n"
        "4. Введи рабочий вес сообщением\n\n"
        "Чтобы смотреть старые веса, нажми 'Отслежение весов'."
    )
    await update.message.reply_text(text, reply_markup=get_main_menu_keyboard())
    return MAIN_MENU


async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "Старт тренировки":
        await update.message.reply_text("Выбери день тренировки:", reply_markup=get_days_keyboard())
        return SELECT_DAY

    elif text == "Отслежение весов":
        await update.message.reply_text(
            "Выбери день, по которому хочешь посмотреть веса:",
            reply_markup=get_days_keyboard()
        )
        return TRACK_DAY

    elif text == "Помощь":
        return await help_command(update, context)

    elif text == "Отмена":
        return await cancel(update, context)

    else:
        await update.message.reply_text("Выбери кнопку из меню.", reply_markup=get_main_menu_keyboard())
        return MAIN_MENU


async def select_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    day_name = update.message.text

    if day_name == "Назад":
        await update.message.reply_text("Главное меню:", reply_markup=get_main_menu_keyboard())
        return MAIN_MENU

    if day_name == "Отмена":
        return await cancel(update, context)

    if day_name not in WORKOUTS:
        await update.message.reply_text("Выбери день кнопкой.", reply_markup=get_days_keyboard())
        return SELECT_DAY

    context.user_data["selected_day"] = day_name

    await update.message.reply_text(
        f"Выбран день: {day_name}\n\nТеперь выбери упражнение:",
        reply_markup=get_exercises_keyboard(day_name)
    )
    return SELECT_EXERCISE


async def select_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    exercise_name = update.message.text
    day_name = context.user_data.get("selected_day")

    if exercise_name == "Назад":
        await update.message.reply_text("Выбери день тренировки:", reply_markup=get_days_keyboard())
        return SELECT_DAY

    if exercise_name == "Отмена":
        return await cancel(update, context)

    if not day_name or exercise_name not in WORKOUTS[day_name]:
        await update.message.reply_text("Выбери упражнение кнопкой.", reply_markup=get_exercises_keyboard(day_name))
        return SELECT_EXERCISE

    context.user_data["selected_exercise"] = exercise_name

    history = get_history_for_exercise(update.effective_user.id, day_name, exercise_name)
    last_info = ""

    if history:
        last_weight, last_date = history[0]
        last_info = f"\nПоследний записанный вес: {last_weight} ({last_date})"

    await update.message.reply_text(
        f"Упражнение: {exercise_name}{last_info}\n\n"
        "Теперь введи рабочий вес сообщением.\n"
        "Например: 60 кг или 3x10 по 50",
        reply_markup=ReplyKeyboardMarkup([["Назад", "Отмена"]], resize_keyboard=True)
    )
    return ENTER_WEIGHT


async def enter_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "Назад":
        day_name = context.user_data.get("selected_day")
        await update.message.reply_text("Выбери упражнение:", reply_markup=get_exercises_keyboard(day_name))
        return SELECT_EXERCISE

    if text == "Отмена":
        return await cancel(update, context)

    day_name = context.user_data.get("selected_day")
    exercise_name = context.user_data.get("selected_exercise")

    if not day_name or not exercise_name:
        await update.message.reply_text("Что-то сбилось. Вернись в главное меню.", reply_markup=get_main_menu_keyboard())
        return MAIN_MENU

    save_weight(
        user_id=update.effective_user.id,
        username=update.effective_user.username or "",
        day_name=day_name,
        exercise_name=exercise_name,
        weight=text
    )

    await update.message.reply_text(
        f"Сохранено:\n"
        f"День: {day_name}\n"
        f"Упражнение: {exercise_name}\n"
        f"Вес: {text}\n\n"
        f"Можешь выбрать следующее упражнение.",
        reply_markup=get_exercises_keyboard(day_name)
    )
    return SELECT_EXERCISE


async def track_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    day_name = update.message.text

    if day_name == "Назад":
        await update.message.reply_text("Главное меню:", reply_markup=get_main_menu_keyboard())
        return MAIN_MENU

    if day_name == "Отмена":
        return await cancel(update, context)

    if day_name not in WORKOUTS:
        await update.message.reply_text("Выбери день кнопкой.", reply_markup=get_days_keyboard())
        return TRACK_DAY

    context.user_data["track_day"] = day_name

    latest = get_last_weights_for_day(update.effective_user.id, day_name)

    if not latest:
        await update.message.reply_text(
            f"По дню '{day_name}' пока нет сохраненных весов.\n\n"
            "Выбери упражнение, если хочешь посмотреть историю, или вернись назад.",
            reply_markup=get_exercises_keyboard(day_name)
        )
        return TRACK_EXERCISE

    lines = [f"Последние веса по дню: {day_name}\n"]
    for exercise in WORKOUTS[day_name]:
        if exercise in latest:
            weight, created_at = latest[exercise]
            lines.append(f"• {exercise} — {weight} ({created_at})")
        else:
            lines.append(f"• {exercise} — нет записей")

    lines.append("\nТеперь выбери упражнение, чтобы посмотреть полную историю.")
    await update.message.reply_text("\n".join(lines), reply_markup=get_exercises_keyboard(day_name))
    return TRACK_EXERCISE


async def track_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    exercise_name = update.message.text
    day_name = context.user_data.get("track_day")

    if exercise_name == "Назад":
        await update.message.reply_text("Выбери день:", reply_markup=get_days_keyboard())
        return TRACK_DAY

    if exercise_name == "Отмена":
        return await cancel(update, context)

    if not day_name or exercise_name not in WORKOUTS[day_name]:
        await update.message.reply_text("Выбери упражнение кнопкой.", reply_markup=get_exercises_keyboard(day_name))
        return TRACK_EXERCISE

    history = get_history_for_exercise(update.effective_user.id, day_name, exercise_name)

    if not history:
        await update.message.reply_text(
            f"По упражнению '{exercise_name}' пока нет записей.",
            reply_markup=get_exercises_keyboard(day_name)
        )
        return TRACK_EXERCISE

    lines = [f"История по упражнению: {exercise_name}\n"]
    for weight, created_at in history[:20]:
        lines.append(f"• {weight} — {created_at}")

    await update.message.reply_text("\n".join(lines), reply_markup=get_exercises_keyboard(day_name))
    return TRACK_EXERCISE


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Действие отменено. Ты в главном меню.", reply_markup=get_main_menu_keyboard())
    return MAIN_MENU


def main():
    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_handler)],
            SELECT_DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_day)],
            SELECT_EXERCISE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_exercise)],
            ENTER_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_weight)],
            TRACK_DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, track_day)],
            TRACK_EXERCISE: [MessageHandler(filters.TEXT & ~filters.COMMAND, track_exercise)],
        },
        fallbacks=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^Отмена$"), cancel),
        ],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("help", help_command))

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
