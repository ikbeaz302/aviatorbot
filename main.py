import logging
import sqlite3
import random
import asyncio
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация бота
BOT_TOKEN = "7134890568:AAHv1ca-evbQYry-5MH3E5Y5FwEY8LpcV1M"
ADMIN_ID = 5781330460
BOT_USERNAME = "aviator_signalybot"

# Глобальные настройки (управляются через админ-панель)
CASINO_LINK = "https://1win.com"
VALID_ID_PREFIX = "123"  # По умолчанию ID должны начинаться с 123

class AviatorBot:
    def __init__(self):
        self.init_database()

    def init_database(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect('aviator_bot.db')
        cursor = conn.cursor()

        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                win_id TEXT,
                attempts_left INTEGER DEFAULT 3,
                last_reset TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_attempts INTEGER DEFAULT 0,
                invited_by INTEGER,
                registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Таблица настроек
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        # Инициализация настроек по умолчанию
        cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('casino_link', CASINO_LINK))
        cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('valid_id_prefix', VALID_ID_PREFIX))

        conn.commit()
        conn.close()

    def get_setting(self, key):
        """Получить настройку из базы данных"""
        conn = sqlite3.connect('aviator_bot.db')
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None

    def set_setting(self, key, value):
        """Установить настройку в базе данных"""
        conn = sqlite3.connect('aviator_bot.db')
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
        conn.commit()
        conn.close()

    def get_user(self, user_id):
        """Получить пользователя из базы данных"""
        conn = sqlite3.connect('aviator_bot.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result

    def create_user(self, user_id, username, first_name, invited_by=None):
        """Создать нового пользователя"""
        conn = sqlite3.connect('aviator_bot.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, username, first_name, invited_by) 
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, first_name, invited_by))
        conn.commit()
        conn.close()

    def update_user_attempts(self, user_id, attempts_left):
        """Обновить количество попыток пользователя"""
        conn = sqlite3.connect('aviator_bot.db')
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET attempts_left = ?, last_reset = CURRENT_TIMESTAMP 
            WHERE user_id = ?
        ''', (attempts_left, user_id))
        conn.commit()
        conn.close()

    def set_user_win_id(self, user_id, win_id):
        """Установить 1win ID пользователя"""
        conn = sqlite3.connect('aviator_bot.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET win_id = ? WHERE user_id = ?', (win_id, user_id))
        conn.commit()
        conn.close()

    def reset_all_attempts(self):
        """Сбросить попытки всех пользователей"""
        conn = sqlite3.connect('aviator_bot.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET attempts_left = 3, last_reset = CURRENT_TIMESTAMP')
        conn.commit()
        conn.close()

    def get_all_users(self):
        """Получить всех пользователей"""
        conn = sqlite3.connect('aviator_bot.db')
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, username, first_name, win_id, attempts_left FROM users')
        result = cursor.fetchall()
        conn.close()
        return result

    def check_and_reset_attempts(self, user_id):
        """Проверить и сбросить попытки если прошло 12 часов"""
        user = self.get_user(user_id)
        if not user:
            return 3

        last_reset = datetime.fromisoformat(user[5])  # last_reset столбец
        current_time = datetime.now()

        if current_time - last_reset >= timedelta(hours=12):
            self.update_user_attempts(user_id, 3)
            return 3

        return user[4]  # attempts_left столбец

    def generate_coefficient_image(self, coefficient):
        """Генерация изображения с коэффициентом в стиле Aviator"""
        # Создаем изображение с темным фоном
        width, height = 400, 300
        img = Image.new('RGB', (width, height), color='#1a1a2e')
        draw = ImageDraw.Draw(img)

        # Попытка загрузить шрифт, если не получается - используем стандартный
        try:
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        except:
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()

        # Рисуем градиентный фон
        for y in range(height):
            r = int(26 + (30 * y / height))
            g = int(26 + (40 * y / height))
            b = int(46 + (60 * y / height))
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # Добавляем декоративные элементы
        draw.ellipse([width-100, 20, width-20, 100], outline='#16213e', width=2)
        draw.ellipse([20, height-100, 100, height-20], outline='#16213e', width=2)

        # Основной текст с коэффициентом
        text = f"{coefficient}x"
        bbox = draw.textbbox((0, 0), text, font=font_large)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        x = (width - text_width) // 2
        y = (height - text_height) // 2 - 20

        # Добавляем тень
        draw.text((x+3, y+3), text, font=font_large, fill='#000000')
        # Основной текст
        draw.text((x, y), text, font=font_large, fill='#00ff88')

        # Добавляем заголовок
        title = "🛩️ AVIATOR SIGNAL"
        title_bbox = draw.textbbox((0, 0), title, font=font_small)
        title_width = title_bbox[2] - title_bbox[0]
        title_x = (width - title_width) // 2
        draw.text((title_x, 30), title, font=font_small, fill='#ffffff')

        # Сохраняем в BytesIO
        bio = BytesIO()
        img.save(bio, 'PNG')
        bio.seek(0)
        return bio

bot_instance = AviatorBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    user = update.effective_user

    # Проверяем реферальную ссылку
    invited_by = None
    if context.args and context.args[0].startswith('ref='):
        try:
            invited_by = int(context.args[0][4:])
        except ValueError:
            pass

    # Создаем или обновляем пользователя
    bot_instance.create_user(user.id, user.username, user.first_name, invited_by)

    # Если пользователь пришел по реферальной ссылке
    if invited_by:
        inviter = bot_instance.get_user(invited_by)
        if inviter:
            # Добавляем попытку пригласившему
            current_attempts = bot_instance.check_and_reset_attempts(invited_by)
            bot_instance.update_user_attempts(invited_by, current_attempts + 1)

            # Уведомляем пригласившего
            try:
                keyboard = [[InlineKeyboardButton("🎯 Получить сигнал Aviator", callback_data="get_signal")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.send_message(
                    invited_by,
                    f"🎉 Вы пригласили {user.first_name}, у вас появилась ещё одна попытка!",
                    reply_markup=reply_markup
                )
            except:
                pass

    # Получаем данные пользователя для проверки регистрации
    user_data = bot_instance.get_user(user.id)

    # Если это администратор - показываем админ-панель сразу
    if user.id == ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton("🔧 Админ-панель", callback_data="show_admin_panel")],
            [InlineKeyboardButton("🎯 Получить сигнал Aviator", callback_data="get_signal")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"👑 Добро пожаловать, администратор!\n\n"
            f"🎯 Вы можете использовать бота как обычный пользователь или управлять им через админ-панель.",
            reply_markup=reply_markup
        )
        return

    # Проверяем, есть ли уже зарегистрированный ID
    if user_data and user_data[3]:  # win_id существует - пользователь уже зарегистрирован
        attempts_left = bot_instance.check_and_reset_attempts(user.id)

        if attempts_left > 0:
            keyboard = [
                [InlineKeyboardButton("🎯 Получить сигнал Aviator", callback_data="get_signal")],
                [InlineKeyboardButton("🔗 Моя реферальная ссылка", callback_data="my_referral_link")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"✅ Вы уже зарегистрированы!\n\n"
                f"🆔 Ваш ID: {user_data[3]}\n\n"
                f"🎯 У вас осталось попыток: {attempts_left}/3\n\n"
                f"Нажмите кнопку ниже, чтобы получить сигнал! 🚀",
                reply_markup=reply_markup
            )
        else:
            share_text = "🎯 Бот, который дает сигналы на Aviator! 🚀\nЗапускай и зарабатывай! 💰"
            import urllib.parse
            encoded_text = urllib.parse.quote(share_text)
            keyboard = [
                [InlineKeyboardButton("👥 Пригласить друга", url=f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME}?start=ref={user.id}&text={encoded_text}")],
                [InlineKeyboardButton("🔗 Моя реферальная ссылка", callback_data="my_referral_link")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"✅ Вы уже зарегистрированы!\n\n"
                f"🆔 Ваш ID: {user_data[3]}\n\n"
                f"😔 У вас закончились попытки! Ждите 12 часов, чтобы получить еще 3 попытки, или пригласите друга, чтобы получить еще 1 попытку! 👥",
                reply_markup=reply_markup
            )
        return  # Важно! Выходим из функции, чтобы не показывать форму регистрации
    else:
        # Новый пользователь - показываем стартовое сообщение для регистрации
        casino_link = bot_instance.get_setting('casino_link')
        keyboard = [[InlineKeyboardButton("✅ Я зарегистрировался", callback_data="registered")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"🎯 Добро пожаловать в бота \"Сигнал от Aviator\"! ✈️\n\n"
            f"📋 Для получения сигнала сначала зарегистрируйтесь по этой ссылке:\n"
            f"🔗 {casino_link}\n\n"
            f"⚠️ Важно! Чтобы бот дал вам сигнал, у вас должен быть новый аккаунт, "
            f"зарегистрированный через эту ссылку. Иначе бот не примет ваш ID!\n\n"
            f"🎰 Работает только с казино 1win.",
            reply_markup=reply_markup
        )

async def get_my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Получить свой Telegram ID"""
    user_id = update.effective_user.id
    await update.message.reply_text(f"🆔 Ваш Telegram ID: {user_id}")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ-панель"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет доступа к админ-панели.")
        return

    keyboard = [
        [InlineKeyboardButton("🔗 Изменить ссылку 1win", callback_data="admin_change_link")],
        [InlineKeyboardButton("🆔 Изменить валидность ID", callback_data="admin_change_id_prefix")],
        [InlineKeyboardButton("📢 Отправить сообщение", callback_data="admin_broadcast")],
        [InlineKeyboardButton("👥 Список пользователей", callback_data="admin_users_list")],
        [InlineKeyboardButton("🔄 Сбросить попытки", callback_data="admin_reset_attempts")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🔧 Админ-панель бота \"Сигнал от Aviator\"\n\nВыберите действие:",
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data == "registered":
        # Проверяем, есть ли уже зарегистрированный ID
        user_data = bot_instance.get_user(user_id)
        if user_data and user_data[3]:  # win_id уже существует
            keyboard = [[InlineKeyboardButton("🔙 Вернуться в меню", callback_data="back_to_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "❌ Вы уже зарегистрированы!\n\n"
                f"🆔 Ваш ID: {user_data[3]}\n\n"
                "Для получения новых попыток дождитесь обновления (каждые 12 часов) или пригласите друзей.",
                reply_markup=reply_markup
            )
            return

        await query.edit_message_text(
            "🆔 Введите ваш ID от 1win:",
            reply_markup=None
        )
        context.user_data['waiting_for_id'] = True

    elif data == "enter_id":
        # Проверяем, есть ли уже зарегистрированный ID
        user_data = bot_instance.get_user(user_id)
        if user_data and user_data[3]:  # win_id уже существует
            keyboard = [[InlineKeyboardButton("🔙 Вернуться в меню", callback_data="back_to_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "❌ Вы уже зарегистрированы!\n\n"
                f"🆔 Ваш ID: {user_data[3]}\n\n"
                "Для получения новых попыток дождитесь обновления (каждые 12 часов) или пригласите друзей.",
                reply_markup=reply_markup
            )
            return

        await query.edit_message_text(
            "🆔 Введите ваш ID от 1win:",
            reply_markup=None
        )
        context.user_data['waiting_for_id'] = True

    elif data == "get_signal":
        attempts_left = bot_instance.check_and_reset_attempts(user_id)

        if attempts_left <= 0:
            share_text = "🎯 Бот, который дает сигналы на Aviator! 🚀\nЗапускай и зарабатывай! 💰"
            import urllib.parse
            encoded_text = urllib.parse.quote(share_text)
            keyboard = [[InlineKeyboardButton("👥 Пригласить друга", url=f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME}?start=ref={user_id}&text={encoded_text}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "😔 У вас закончились попытки! Ждите 12 часов, чтобы получить еще 3 попытки, или пригласите друга, чтобы получить еще 1 попытку! 👥",
                reply_markup=reply_markup
            )
            return

        # Генерируем коэффициент
        user_data = bot_instance.get_user(user_id)
        total_attempts = user_data[6] if user_data else 0

        if total_attempts < 3:
            # Первые 3 попытки: от 1.10x до 2.3x
            coefficient = round(random.uniform(1.10, 2.30), 2)
        else:
            # После 3 попыток: от 1x до 10x
            coefficient = round(random.uniform(1.0, 10.0), 2)

        # Уменьшаем количество попыток
        bot_instance.update_user_attempts(user_id, attempts_left - 1)

        # Обновляем общее количество попыток
        conn = sqlite3.connect('aviator_bot.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET total_attempts = total_attempts + 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()

        # Генерируем изображение
        image = bot_instance.generate_coefficient_image(coefficient)

        new_attempts_left = attempts_left - 1

        if new_attempts_left > 0:
            keyboard = [[InlineKeyboardButton("🎯 Получить сигнал Aviator", callback_data="get_signal")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            caption = f"🎯 Ваш сигнал: {coefficient}x\n\n📊 Попыток осталось: {new_attempts_left}/3"
        else:
            share_text = "🎯 Бот, который дает сигналы на Aviator! 🚀\nЗапускай и зарабатывай! 💰"
            import urllib.parse
            encoded_text = urllib.parse.quote(share_text)
            keyboard = [[InlineKeyboardButton("👥 Пригласить друга", url=f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME}?start=ref={user_id}&text={encoded_text}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            caption = f"🎯 Ваш сигнал: {coefficient}x\n\n😔 У вас закончились попытки! Ждите 12 часов, чтобы получить еще 3 попытки, или пригласите друга, чтобы получить еще 1 попытку! 👥"

        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=image,
            caption=caption,
            reply_markup=reply_markup
        )

    elif data == "show_admin_panel" and user_id == ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton("🔗 Изменить ссылку 1win", callback_data="admin_change_link")],
            [InlineKeyboardButton("🆔 Изменить валидность ID", callback_data="admin_change_id_prefix")],
            [InlineKeyboardButton("📢 Отправить сообщение", callback_data="admin_broadcast")],
            [InlineKeyboardButton("👥 Список пользователей", callback_data="admin_users_list")],
            [InlineKeyboardButton("🔄 Сбросить попытки", callback_data="admin_reset_attempts")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🔧 Админ-панель бота \"Сигнал от Aviator\"\n\nВыберите действие:",
            reply_markup=reply_markup
        )

    elif data == "my_referral_link":
        referral_link = f"https://t.me/{BOT_USERNAME}?start=ref={user_id}"
        share_link = f"https://t.me/share/url?url={referral_link}&text=🎯 Бот, который дает сигналы на Aviator! 🚀%0AЗапускай и зарабатывай! 💰"

        keyboard = [
            [InlineKeyboardButton("📤 Поделиться ссылкой", url=share_link)],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"🔗 Ваша реферальная ссылка:\n\n"
            f"`{referral_link}`\n\n"
            f"💡 Отправьте эту ссылку друзьям!\n"
            f"За каждого приглашенного друга вы получите +1 попытку!",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    elif data == "back_to_main":
        user_data = bot_instance.get_user(user_id)
        if user_data and user_data[3]:  # win_id существует
            attempts_left = bot_instance.check_and_reset_attempts(user_id)

            if attempts_left > 0:
                keyboard = [
                    [InlineKeyboardButton("🎯 Получить сигнал Aviator", callback_data="get_signal")],
                    [InlineKeyboardButton("🔗 Моя реферальная ссылка", callback_data="my_referral_link")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    f"🎯 Добро пожаловать в бота \"Сигнал от Aviator\"! ✈️\n\n"
                    f"У вас осталось попыток: {attempts_left}/3\n\n"
                    f"Нажмите кнопку ниже, чтобы получить сигнал! 🚀",
                    reply_markup=reply_markup
                )
            else:
                share_text = "🎯 Бот, который дает сигналы на Aviator! 🚀\nЗапускай и зарабатывай! 💰"
                import urllib.parse
                encoded_text = urllib.parse.quote(share_text)
                keyboard = [
                    [InlineKeyboardButton("👥 Пригласить друга", url=f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME}?start=ref={user_id}&text={encoded_text}")],
                    [InlineKeyboardButton("🔗 Моя реферальная ссылка", callback_data="my_referral_link")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    "😔 У вас закончились попытки! Ждите 12 часов, чтобы получить еще 3 попытки, или пригласите друга, чтобы получить еще 1 попытку! 👥",
                    reply_markup=reply_markup
                )

    # Админ панель
    elif data.startswith("admin_") and user_id == ADMIN_ID:
        if data == "admin_change_link":
            keyboard = [[InlineKeyboardButton("◀️ Назад в панель", callback_data="show_admin_panel")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "🔗 Отправьте новую ссылку на казино 1win:",
                reply_markup=reply_markup
            )
            context.user_data['admin_waiting_for'] = 'casino_link'

        elif data == "admin_change_id_prefix":
            keyboard = [[InlineKeyboardButton("◀️ Назад в панель", callback_data="show_admin_panel")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "🆔 Отправьте новый префикс для валидных ID (цифры, с которых должны начинаться новые ID):",
                reply_markup=reply_markup
            )
            context.user_data['admin_waiting_for'] = 'id_prefix'

        elif data == "admin_broadcast":
            keyboard = [[InlineKeyboardButton("◀️ Назад в панель", callback_data="show_admin_panel")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "📢 Отправьте сообщение, которое будет разослано всем пользователям:",
                reply_markup=reply_markup
            )
            context.user_data['admin_waiting_for'] = 'broadcast_message'

        elif data == "admin_users_list":
            users = bot_instance.get_all_users()
            keyboard = [[InlineKeyboardButton("◀️ Назад в панель", callback_data="show_admin_panel")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if not users:
                await query.edit_message_text("👥 Пользователей пока нет.", reply_markup=reply_markup)
                return

            text = "👥 Список пользователей:\n\n"
            for user in users[:20]:  # Показываем первых 20
                user_id_str, username, first_name, win_id, attempts_left = user
                username_str = f"@{username}" if username else "Нет username"
                win_id_str = win_id if win_id else "Не указан"
                text += f"🆔 {user_id_str}\n👤 {first_name} ({username_str})\n🎰 1win ID: {win_id_str}\n📊 Попытки: {attempts_left}/3\n\n"

            if len(users) > 20:
                text += f"... и еще {len(users) - 20} пользователей"

            await query.edit_message_text(text[:4000], reply_markup=reply_markup)  # Telegram ограничение

        elif data == "admin_reset_attempts":
            keyboard = [[InlineKeyboardButton("◀️ Назад в панель", callback_data="show_admin_panel")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            bot_instance.reset_all_attempts()
            await query.edit_message_text("✅ Попытки всех пользователей сброшены!", reply_markup=reply_markup)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик текстовых сообщений"""
    user_id = update.effective_user.id
    text = update.message.text

    # Обработка ввода ID от пользователя
    if context.user_data.get('waiting_for_id'):
        context.user_data['waiting_for_id'] = False

        valid_prefixes = bot_instance.get_setting('valid_id_prefix')
        # Поддержка нескольких префиксов через запятую
        prefix_list = [prefix.strip() for prefix in valid_prefixes.split(',')]

        # Проверяем, начинается ли ID с любого из валидных префиксов
        is_valid = any(text.startswith(prefix) for prefix in prefix_list)

        if not is_valid:
            casino_link = bot_instance.get_setting('casino_link')
            keyboard = [
                [InlineKeyboardButton("🎰 Зарегистрируйтесь тут", url=casino_link)],
                [InlineKeyboardButton("🆔 Введите ID от 1win", callback_data="enter_id")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "❌ Вы ввели старый ID. Вы должны зарегистрироваться через эту ссылку и написать новый ID от 1win.",
                reply_markup=reply_markup
            )
        else:
            # Сохраняем валидный ID
            bot_instance.set_user_win_id(user_id, text)

            attempts_left = bot_instance.check_and_reset_attempts(user_id)
            keyboard = [[InlineKeyboardButton("🎯 Получить сигнал Aviator", callback_data="get_signal")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"✅ ID успешно сохранен!\n\n🎯 Теперь вы можете получать сигналы Aviator.\n📊 У вас {attempts_left}/3 попыток.",
                reply_markup=reply_markup
            )

    # Обработка админских команд
    elif context.user_data.get('admin_waiting_for') and user_id == ADMIN_ID:
        waiting_for = context.user_data['admin_waiting_for']
        context.user_data['admin_waiting_for'] = None

        if waiting_for == 'casino_link':
            bot_instance.set_setting('casino_link', text)
            await update.message.reply_text(f"✅ Ссылка на казино обновлена: {text}")

        elif waiting_for == 'id_prefix':
            bot_instance.set_setting('valid_id_prefix', text)
            await update.message.reply_text(f"✅ Префикс для валидных ID обновлен: {text}")

        elif waiting_for == 'broadcast_message':
            users = bot_instance.get_all_users()
            success_count = 0
            fail_count = 0
            for user in users:
                try:
                    await context.bot.send_message(user[0], text)  # user[0] is user_id
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to send message to user {user[0]}: {e}")
                    fail_count += 1
            await update.message.reply_text(f"✅ Сообщение отправлено {success_count} пользователям.\n❌ Не удалось отправить {fail_count} пользователям.")

def main() -> None:
    """Запуск бота"""
    application = Application.builder().token(BOT_TOKEN).build()

    # Обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("myid", get_my_id))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # Запуск
    print("🚀 Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()