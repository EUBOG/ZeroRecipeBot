import telebot
from telebot import types
from config import BOT_TOKEN
from database import Database
from enum import Enum
from utils import safe_send
import logging

# Подавляем ложные "ошибки" от telebot при остановке
logging.getLogger('telebot').setLevel(logging.WARNING)
# Дополнительно: подавляем логи от urllib3
logging.getLogger('urllib3').setLevel(logging.WARNING)

# Инициализация
bot = telebot.TeleBot(BOT_TOKEN)
db = Database()

# Состояния пользователя
user_states = {}
user_data = {}


class State(Enum):
    AWAITING_TITLE = 1
    AWAITING_CATEGORY = 2
    AWAITING_INGREDIENTS = 3
    AWAITING_INSTRUCTIONS = 4
    AWAITING_RECIPE_ID_FOR_EDIT = 5
    AWAITING_RECIPE_ID_FOR_DELETE = 6
    AWAITING_SEARCH_QUERY = 7
    AWAITING_RECIPE_ID_FOR_REVIEW = 8
    AWAITING_RATING = 9
    AWAITING_COMMENT = 10
    AWAITING_CONSENT = 11


CATEGORIES = ["завтрак", "обед", "ужин"]


# Клавиатуры
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📝 Добавить рецепт", "📚 Мои рецепты")
    markup.add("🔍 Поиск", "🛡️ Отозвать согласие")
    return markup


def category_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add(*[types.KeyboardButton(cat) for cat in CATEGORIES])
    markup.add("🔙 Отмена")
    return markup


# Команды
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    user = message.from_user

    # Сохраняем/обновляем данные пользователя в БД
    db.add_user(
        user_id=user_id,
        username=user.username
    )

    # Проверяем согласие
    if not db.user_has_consent(user_id):
        user_states[user_id] = State.AWAITING_CONSENT

        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("✅ Принимаю условия", callback_data="consent_accept"),
            types.InlineKeyboardButton("❌ Отказываюсь", callback_data="consent_decline")
        )

        send_safe_message(bot, message.chat.id,
            "🔐 <b>Защита персональных данных</b>\n\n"
            "Для работы бота мы сохраняем:\n"
            "• Ваш ID в Telegram — для привязки рецептов\n"
            "• Ваши рецепты (названия, ингредиенты, инструкции)\n\n"
            "Мы <b>не запрашиваем и не храним</b>:\n"
            "• ФИО, телефон, email, адрес\n\n"
            "Данные используются только для работы бота и не передаются третьим лицам.\n"
            "Политика конфиденциальности: https://eubog.ru/privacy\n\n"
            "<i>Нажимая «Принимаю», вы даёте согласие на обработку указанных данных.</i>",
            reply_markup=markup,
            parse_mode="HTML"
        )
        return

    # Если согласие есть — показываем главное меню
    send_safe_message(bot, message.chat.id,
        "👋 Добро пожаловать в Блокнот рецептов!\n"
        "Сохраняйте, редактируйте и делитесь своими любимыми блюдами.",
        reply_markup=main_menu()
    )


# Обработчик кнопок согласия
@bot.callback_query_handler(func=lambda call: call.data in ["consent_accept", "consent_decline"])
def handle_consent(call):
    bot.answer_callback_query(call.id)
    user_id = call.message.chat.id
    chat_id = call.message.chat.id

    if call.data == "consent_accept":
        # Записываем согласие
        db.give_consent(user_id)

        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text="✅ Спасибо! Согласие получено.\nТеперь вы можете пользоваться ботом.",
            reply_markup=None
        )

        # Показываем меню через 2 секунды
        send_safe_message(bot, call.message.chat.id, "Выберите действие:", reply_markup=main_menu())

    else:  # consent_decline
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text="❌ Вы отказались от использования бота.\n"
                 "Если передумаете — напишите /start",
            reply_markup=None
        )

    # Удаляем состояние
    if user_id in user_states:
        del user_states[user_id]


# Добавление рецепта
@bot.message_handler(func=lambda m: m.text == "📝 Добавить рецепт")
def add_recipe_start(message):
    # 🔒 Проверка согласия
    if not db.user_has_consent(message.chat.id):
        bot.send_message(message.chat.id, "⚠️ Сначала примите условия (/start)")
        return
    user_states[message.chat.id] = State.AWAITING_TITLE
    send_safe_message(bot, message.chat.id, "🍽 Введите название блюда:", reply_markup=types.ReplyKeyboardRemove())


@bot.message_handler(func=lambda m: user_states.get(m.chat.id) == State.AWAITING_TITLE)
def get_title(message):
    user_data[message.chat.id] = {"title": message.text}
    user_states[message.chat.id] = State.AWAITING_CATEGORY
    send_safe_message(bot, message.chat.id, "🕗 Выберите категорию:", reply_markup=category_keyboard())


@bot.message_handler(func=lambda m: user_states.get(m.chat.id) == State.AWAITING_CATEGORY and m.text in CATEGORIES)
def get_category(message):
    user_data[message.chat.id]["category"] = message.text
    user_states[message.chat.id] = State.AWAITING_INGREDIENTS
    send_safe_message(bot, message.chat.id, "🥕 Перечислите ингредиенты (через запятую):",
                     reply_markup=types.ReplyKeyboardRemove())


@bot.message_handler(func=lambda m: user_states.get(m.chat.id) == State.AWAITING_INGREDIENTS)
def get_ingredients(message):
    user_data[message.chat.id]["ingredients"] = message.text
    user_states[message.chat.id] = State.AWAITING_INSTRUCTIONS
    send_safe_message(bot, message.chat.id, "👩‍🍳 Опишите способ приготовления:")


@bot.message_handler(func=lambda m: user_states.get(m.chat.id) == State.AWAITING_INSTRUCTIONS)
def get_instructions(message):
    user_data[message.chat.id]["instructions"] = message.text
    data = user_data[message.chat.id]

    recipe_id = db.add_recipe(
        message.chat.id,
        data["title"],
        data["category"],
        data["ingredients"],
        data["instructions"]
    )

    send_safe_message(bot, message.chat.id,
        f"✅ Рецепт «{data['title']}» успешно сохранён!\nКатегория: {data['category']}",
        reply_markup=main_menu()
    )
    del user_states[message.chat.id]
    del user_data[message.chat.id]


# Мои рецепты
@bot.message_handler(func=lambda m: m.text == "📚 Мои рецепты")
def show_my_recipes(message):
    # 🔒 Проверка согласия
    if not db.user_has_consent(message.chat.id):
        bot.send_message(message.chat.id, "⚠️ Сначала примите условия (/start)")
        return
    recipes = db.get_user_recipes(message.chat.id)
    if not recipes:
        send_safe_message(bot, message.chat.id, "У вас пока нет сохранённых рецептов.", reply_markup=main_menu())
        return

    text = "📋 Ваши рецепты:\n\n"
    for rid, title, category in recipes:
        text += f"• {title} ({category}) — /view_{rid}\n"

    send_safe_message(bot, message.chat.id, text, reply_markup=main_menu(), parse_mode="HTML")


# Просмотр рецепта (через callback из /view_X)
@bot.message_handler(regexp=r"^/view_\d+$")
def view_recipe(message):
    recipe_id = int(message.text.split('_')[1])
    recipe = db.get_recipe(recipe_id)

    if not recipe or recipe[1] != message.chat.id:
        send_safe_message(bot, message.chat.id, "Рецепт не найден или недоступен.")
        return

    _, _, title, category, ingredients, instructions, _ = recipe
    reviews = db.get_reviews(recipe_id)

    text = f"🍽 *{title}*\n🕗 Категория: {category}\n\n*Ингредиенты:*\n{ingredients}\n\n*Приготовление:*\n{instructions}"

    if reviews:
        text += "\n\n⭐ Отзывы:\n"
        for rating, comment, _ in reviews:
            text += f"• {rating}★ — {comment}\n"

    # Кнопки действий
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_{recipe_id}"))
    markup.add(types.InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_{recipe_id}"))
    markup.add(types.InlineKeyboardButton("⭐ Оставить отзыв", callback_data=f"review_{recipe_id}"))

    send_safe_message(bot, message.chat.id, text, reply_markup=markup, parse_mode="HTML")


# Поиск
@bot.message_handler(func=lambda m: m.text == "🔍 Поиск")
def search_start(message):
    # 🔒 Проверка согласия
    if not db.user_has_consent(message.chat.id):
        bot.send_message(message.chat.id, "⚠️ Сначала примите условия (/start)")
        return
    user_states[message.chat.id] = State.AWAITING_SEARCH_QUERY
    send_safe_message(bot, message.chat.id, "🔍 Введите название блюда или ингредиент:",
                     reply_markup=types.ReplyKeyboardRemove())


@bot.message_handler(func=lambda m: user_states.get(m.chat.id) == State.AWAITING_SEARCH_QUERY)
def perform_search(message):
    results = db.search_recipes(message.text)
    if not results:
        send_safe_message(bot, message.chat.id, "Ничего не найдено 😕", reply_markup=main_menu())
        del user_states[message.chat.id]
        return

    text = "🔍 Результаты поиска:\n\n"
    for rid, title, category in results:
        text += f"• {title} ({category}) — /view_{rid}\n"

    send_safe_message(bot, message.chat.id, text, reply_markup=main_menu(), parse_mode="HTML")
    del user_states[message.chat.id]

# Отзыв согласия
@bot.message_handler(func=lambda m: m.text == "🛡️ Отозвать согласие")
def revoke_consent_start(message):
    chat_id = message.chat.id

    # Проверка: пользователь уже давал согласие?
    if not db.user_has_consent(chat_id):
        bot.send_message(
            chat_id,
            "ℹ️ Вы ещё не давали согласия на обработку данных.\n"
            "Напишите /start для начала работы с ботом.",
            reply_markup=main_menu()
        )
        return

    # Подтверждение действия (защита от случайного нажатия)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Да, отозвать", callback_data="revoke_confirm"),
        types.InlineKeyboardButton("❌ Отмена", callback_data="revoke_cancel")
    )

    bot.send_message(
        chat_id,
        "⚠️ <b>Внимание!</b>\n\n"
        "При отзыве согласия будут <b>безвозвратно удалены</b>:\n"
        "• Все ваши рецепты\n"
        "• Все оставленные отзывы\n"
        "• Вся информация о вас из базы бота\n\n"
        "Это действие нельзя отменить. Вы уверены?",
        reply_markup=markup,
        parse_mode="HTML"
    )


# Обработка инлайн-кнопок
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    # 🔒 Проверка согласия (для всех действий кроме отзыва согласия)
    if call.data not in ["revoke_confirm", "revoke_cancel"] and not db.user_has_consent(chat_id):
        bot.send_message(
            chat_id,
            "⚠️ Сначала примите условия использования бота.\nНапишите /start"
        )
        return

    try:
        # === 1. Отзыв согласия ===
        if call.data == "revoke_confirm":
            # Удаляем ВСЕ данные пользователя
            db.revoke_user_data(chat_id)

            # Очищаем состояния
            user_states.pop(chat_id, None)
            user_data.pop(chat_id, None)

            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text="✅ Согласие отозвано.\nВсе ваши данные удалены из базы бота.\n\n"
                     "Чтобы начать заново, напишите /start",
                reply_markup=None
            )
            return

        elif call.data == "revoke_cancel":
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text="ℹ️ Отзыв согласия отменён.\nВаши данные сохранены.",
                reply_markup=None
            )
            bot.send_message(chat_id, "Выберите действие:", reply_markup=main_menu())
            return

        # === 2. Действия с рецептами (требуют парсинга данных вида "action_id") ===
        data_parts = call.data.split('_')
        if len(data_parts) < 2:
            bot.send_message(chat_id, "❌ Некорректные данные действия.")
            return

        action = data_parts[0]
        recipe_id = int(data_parts[1])

        # 🔐 Проверка прав доступа к рецепту
        recipe = db.get_recipe(recipe_id)
        if not recipe or recipe[1] != chat_id:  # recipe[1] = user_id из БД
            bot.send_message(chat_id, "❌ У вас нет прав на это действие.")
            return

        # === 3. Редактирование ===
        if action == "edit":
            user_states[chat_id] = State.AWAITING_TITLE
            user_data[chat_id] = {"recipe_id": recipe_id}
            bot.send_message(chat_id, "✏️ Введите новое название:", reply_markup=types.ReplyKeyboardRemove())

        # === 4. Удаление ===
        elif action == "delete":
            db.delete_recipe(recipe_id)
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text="✅ Рецепт успешно удалён."
            )

        # === 5. Отзыв на рецепт ===
        elif action == "review":
            user_states[chat_id] = State.AWAITING_RATING
            user_data[chat_id] = {"recipe_id": recipe_id}
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=5)
            markup.add(*[types.KeyboardButton(str(i)) for i in range(1, 6)])
            markup.add("🔙 Отмена")
            bot.send_message(chat_id, "⭐ Оцените рецепт (1–5):", reply_markup=markup)

    except (IndexError, ValueError) as e:
        bot.send_message(chat_id, "❌ Ошибка обработки действия. Попробуйте снова.")
        print(f"Callback error: {e}")


# Обработка отзыва (оценка → комментарий)
@bot.message_handler(
    func=lambda m: user_states.get(m.chat.id) == State.AWAITING_RATING and m.text.isdigit() and 1 <= int(m.text) <= 5)
def get_rating(message):
    # 🔒 Проверка согласия
    if not db.user_has_consent(message.chat.id):
        bot.send_message(message.chat.id, "⚠️ Сначала примите условия (/start)")
        return
    user_data[message.chat.id]["rating"] = int(message.text)
    user_states[message.chat.id] = State.AWAITING_COMMENT
    send_safe_message(bot, message.chat.id, "💬 Напишите комментарий (или «-» для пропуска):",
                     reply_markup=types.ReplyKeyboardRemove())


@bot.message_handler(func=lambda m: user_states.get(m.chat.id) == State.AWAITING_COMMENT)
def get_comment(message):
    comment = message.text if message.text != "-" else ""
    data = user_data[message.chat.id]

    db.add_review(data["recipe_id"], message.chat.id, data["rating"], comment)

    send_safe_message(bot, message.chat.id,
        "✅ Отзыв сохранён!",
        reply_markup=main_menu()
    )
    del user_states[message.chat.id]
    del user_data[message.chat.id]


# Отмена
@bot.message_handler(func=lambda m: m.text == "🔙 Отмена")
def cancel(message):
    if message.chat.id in user_states:
        del user_states[message.chat.id]
    if message.chat.id in user_data:
        del user_data[message.chat.id]
    send_safe_message(bot, message.chat.id, "❌ Действие отменено", reply_markup=main_menu())


@safe_send
def send_safe_message(bot, chat_id, text, **kwargs):
    return bot.send_message(chat_id, text, **kwargs)
# Пояснение: Вместо прямого вызова:
# bot.send_message(...)
# Используем: send_safe_message(bot, message.chat.id, "✅ Рецепт сохранён!", reply_markup=main_menu())

def require_consent(handler):
    """Декоратор: блокирует действия без согласия"""
    def wrapper(message):
        if not db.user_has_consent(message.chat.id):
            send_safe_message(bot, message.chat.id,
                "⚠️ Сначала примите условия использования бота (/start)"
            )
            return
        return handler(message)
    return wrapper

# Запуск и остановка
if __name__ == "__main__":
    import sys
    import time
    from urllib3.exceptions import ProtocolError

    # Настройка логгирования (после подавления уровней)
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO,
        handlers=[
            logging.FileHandler("bot.log", encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

    print("🤖 Бот «Блокнот рецептов» запускается...")
    print("Нажмите Ctrl+C для остановки")

    try:
        while True:
            try:
                bot.infinity_polling(
                    timeout=20,
                    long_polling_timeout=20,
                    logger_level=logging.INFO,
                    skip_pending=True
                )
            except (ConnectionError, ProtocolError) as e:
                logging.warning(f"⚠️ Сетевая ошибка: {e}. Переподключение через 5 сек...")
                time.sleep(5)
            except KeyboardInterrupt:
                logging.info("🛑 Получен сигнал остановки (Ctrl+C). Завершаем работу...")
                raise
            except Exception as e:
                logging.exception(f"❌ Критическая ошибка: {e}")
                time.sleep(15)
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен пользователем")
    finally:
        if 'db' in globals():
            db.close()
            print("✅ Соединение с базой данных закрыто")
        print("Бот завершил работу корректно")