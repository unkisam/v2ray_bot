#!/usr/bin/env python3
"""
Production-Grade V2Ray Config Telegram Bot
با سیستم فاکتور، ارسال رسید و تایید دستی توسط ادمین
"""

import os
import json
import sqlite3
import logging
import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
from enum import Enum
import base64

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, User
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ChatAction
from flask import Flask
from threading import Thread

app = Flask(__name__)


@app.get("/")
def home():
    return "ok", 200


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


Thread(target=run_web, daemon=True).start()
# ==================== LOGGING SETUP ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.getenv('BOT_TOKEN', '8520873297:AAH6WANR20WXYMOaRrMaztKjTipzoojG028')
ADMIN_IDS = [int(x) for x in os.getenv('ADMIN_IDS', '8552949710').split(',')]
DATABASE_PATH = 'bot_database.db'

# ==================== شماره کارت برای واریز ====================
CARD_NUMBER = os.getenv('CARD_NUMBER', '6037-9917-6124-5137')
CARD_HOLDER = os.getenv('CARD_HOLDER', '.')
CARD_BANK = os.getenv('CARD_BANK', 'بانک ملی')

# ==================== ENUMS ====================
class UserState(Enum):
    WAITING_FOR_SUPPORT_MESSAGE = 3
    ADMIN_WAITING_FOR_BROADCAST = 4
    ADMIN_WAITING_FOR_PLAN_NAME = 5
    ADMIN_WAITING_FOR_PLAN_PRICE = 6
    ADMIN_WAITING_FOR_PLAN_TRAFFIC = 7
    ADMIN_WAITING_FOR_PLAN_DURATION = 8
    ADMIN_SEARCH_USER = 10
    WAITING_FOR_RECEIPT_PHOTO = 11       # انتظار برای عکس رسید
    ADMIN_WAITING_FOR_CONFIG = 12        # ادمین داره کانفیگ تایپ می‌کنه
    ADMIN_WAITING_FOR_WALLET_AMOUNT = 13 # ادمین داره مبلغ کیف پول می‌فرسته


# ==================== DATA CLASSES ====================
@dataclass
class Plan:
    id: int
    name: str
    price: float
    traffic: str
    duration: int

    def __str__(self):
        return f"📦 {self.name}\n💵 قیمت: {self.price:,.0f} تومان\n📊 ترافیک: {self.traffic}\n⏱️ مدت: {self.duration} روز"


@dataclass
class Service:
    id: int
    user_id: int
    plan_id: int
    plan_name: str
    config: str
    traffic: str
    expiry_date: str
    purchase_date: str
    status: str


@dataclass
class Payment:
    id: int
    user_id: int
    username: str
    amount: float
    status: str
    date: str
    payment_type: str


# ==================== DATABASE MANAGER ====================
class DatabaseManager:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self.init_database()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_database(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    wallet REAL DEFAULT 0,
                    join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    last_activity TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    price REAL NOT NULL,
                    traffic TEXT NOT NULL,
                    duration INTEGER NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS services (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    plan_id INTEGER NOT NULL,
                    config TEXT DEFAULT '',
                    expiry_date TIMESTAMP,
                    purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (plan_id) REFERENCES plans(id)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    status TEXT DEFAULT 'pending',
                    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    payment_type TEXT DEFAULT 'wallet_charge',
                    receipt_file_id TEXT,
                    plan_id INTEGER,
                    admin_notes TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS support_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    reply TEXT,
                    status TEXT DEFAULT 'open',
                    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')

            conn.commit()

            # ========== MIGRATION: ستون‌های جدید به جداول قدیمی اضافه میشن ==========
            self._run_migrations(conn)

            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            conn.rollback()
        finally:
            conn.close()

    def _run_migrations(self, conn):
        """اضافه کردن ستون‌های جدید به دیتابیس قدیمی"""
        cursor = conn.cursor()
        migrations = [
            # payments جدول
            ("payments", "receipt_file_id", "ALTER TABLE payments ADD COLUMN receipt_file_id TEXT"),
            ("payments", "plan_id",         "ALTER TABLE payments ADD COLUMN plan_id INTEGER"),
            ("payments", "admin_notes",     "ALTER TABLE payments ADD COLUMN admin_notes TEXT"),
            # services جدول
            ("services", "status",          "ALTER TABLE services ADD COLUMN status TEXT DEFAULT 'pending'"),
            ("services", "config",          "ALTER TABLE services ADD COLUMN config TEXT DEFAULT ''"),
            ("services", "expiry_date",     "ALTER TABLE services ADD COLUMN expiry_date TIMESTAMP"),
        ]
        for table, column, sql in migrations:
            try:
                cursor.execute(f"SELECT {column} FROM {table} LIMIT 1")
            except sqlite3.OperationalError:
                # ستون وجود نداره — اضافه کن
                try:
                    cursor.execute(sql)
                    conn.commit()
                    logger.info(f"Migration: added column '{column}' to '{table}'")
                except Exception as e:
                    logger.error(f"Migration error ({table}.{column}): {e}")

    # ========== USER OPERATIONS ==========
    def user_exists(self, telegram_id: int) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE telegram_id = ?', (telegram_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def create_user(self, telegram_id: int, username: str = None, first_name: str = None) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO users (telegram_id, username, first_name) VALUES (?, ?, ?)',
                           (telegram_id, username, first_name))
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return None
        finally:
            conn.close()

    def get_user_id(self, telegram_id: int) -> Optional[int]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE telegram_id = ?', (telegram_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None

    def get_user_wallet(self, user_id: int) -> float:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT wallet FROM users WHERE id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0.0

    def update_user_activity(self, telegram_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE users SET last_activity = CURRENT_TIMESTAMP WHERE telegram_id = ?', (telegram_id,))
            conn.commit()
        except Exception as e:
            logger.error(f"Error updating activity: {e}")
        finally:
            conn.close()

    def add_wallet(self, user_id: int, amount: float) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE users SET wallet = wallet + ? WHERE id = ?', (amount, user_id))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding to wallet: {e}")
            return False
        finally:
            conn.close()

    def deduct_wallet(self, user_id: int, amount: float) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE users SET wallet = wallet - ? WHERE id = ? AND wallet >= ?',
                           (amount, user_id, amount))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deducting wallet: {e}")
            return False
        finally:
            conn.close()

    # ========== PLAN OPERATIONS ==========
    def get_all_plans(self) -> List[Plan]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, price, traffic, duration FROM plans WHERE is_active = 1 ORDER BY price ASC')
        plans = [Plan(*row) for row in cursor.fetchall()]
        conn.close()
        return plans

    def get_plan(self, plan_id: int) -> Optional[Plan]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, price, traffic, duration FROM plans WHERE id = ?', (plan_id,))
        result = cursor.fetchone()
        conn.close()
        return Plan(*result) if result else None

    def add_plan(self, name: str, price: float, traffic: str, duration: int) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO plans (name, price, traffic, duration) VALUES (?, ?, ?, ?)',
                           (name, price, traffic, duration))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            logger.error(f"Error adding plan: {e}")
            return False
        finally:
            conn.close()

    def delete_plan(self, plan_id: int) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE plans SET is_active = 0 WHERE id = ?', (plan_id,))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error deleting plan: {e}")
            return False
        finally:
            conn.close()

    # ========== SERVICE OPERATIONS ==========
    def create_pending_service(self, user_id: int, plan_id: int) -> int:
        """یه سرویس pending بساز - قبل از تایید ادمین"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO services (user_id, plan_id, config, status)
                VALUES (?, ?, '', 'pending')
            ''', (user_id, plan_id))
            conn.commit()
            service_id = cursor.lastrowid
            if not service_id:
                raise Exception("lastrowid is None after insert")
            logger.info(f"Pending service created: {service_id} for user {user_id}")
            return service_id
        except Exception as e:
            logger.error(f"Error creating pending service: {e}")
            raise
        finally:
            conn.close()

    def activate_service(self, service_id: int, config: str, duration_days: int) -> bool:
        """سرویس رو فعال کن با کانفیگ و تاریخ انقضا"""
        expiry_date = (datetime.now() + timedelta(days=duration_days)).isoformat()
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                UPDATE services SET config = ?, expiry_date = ?, status = 'active'
                WHERE id = ?
            ''', (config, expiry_date, service_id))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error activating service: {e}")
            return False
        finally:
            conn.close()

    def get_user_services(self, user_id: int) -> List[Service]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.id, s.user_id, s.plan_id, p.name, s.config, p.traffic,
                   COALESCE(s.expiry_date, ''), s.purchase_date, s.status
            FROM services s
            JOIN plans p ON s.plan_id = p.id
            WHERE s.user_id = ?
            ORDER BY s.purchase_date DESC
        ''', (user_id,))
        services = [Service(*row) for row in cursor.fetchall()]
        conn.close()
        return services

    # ========== PAYMENT OPERATIONS ==========
    def add_payment(self, user_id: int, amount: float, payment_type: str = 'wallet_charge',
                    receipt_file_id: str = None, plan_id: int = None) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO payments (user_id, amount, status, payment_type, receipt_file_id, plan_id)
                VALUES (?, ?, 'pending', ?, ?, ?)
            ''', (user_id, amount, payment_type, receipt_file_id, plan_id))
            conn.commit()
            payment_id = cursor.lastrowid
            if not payment_id:
                raise Exception("lastrowid is None after insert")
            logger.info(f"Payment created: {payment_id} for user {user_id}")
            return payment_id
        except Exception as e:
            logger.error(f"Error adding payment: {e}")
            raise  # بجای None برگردوندن، خطا رو throw کن
        finally:
            conn.close()

    def update_payment_receipt(self, payment_id: int, receipt_file_id: str) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE payments SET receipt_file_id = ? WHERE id = ?',
                           (receipt_file_id, payment_id))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating receipt: {e}")
            return False
        finally:
            conn.close()

    def get_payment(self, payment_id: int) -> Optional[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT p.id, p.user_id, u.telegram_id, u.username, u.first_name,
                       p.amount, p.status, p.date, p.payment_type,
                       p.receipt_file_id, p.plan_id
                FROM payments p
                JOIN users u ON p.user_id = u.id
                WHERE p.id = ?
            ''', (payment_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'id': row[0], 'user_id': row[1], 'telegram_id': row[2],
                    'username': row[3], 'first_name': row[4], 'amount': row[5],
                    'status': row[6], 'date': row[7], 'payment_type': row[8],
                    'receipt_file_id': row[9], 'plan_id': row[10]
                }
            return None
        except Exception as e:
            logger.error(f"Error getting payment: {e}")
            return None
        finally:
            conn.close()

    def approve_payment(self, payment_id: int) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE payments SET status = 'approved' WHERE id = ?", (payment_id,))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error approving payment: {e}")
            return False
        finally:
            conn.close()

    def reject_payment(self, payment_id: int) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE payments SET status = 'rejected' WHERE id = ?", (payment_id,))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error rejecting payment: {e}")
            return False
        finally:
            conn.close()

    def get_pending_payments(self) -> List[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT p.id, p.user_id, u.telegram_id, u.username, u.first_name,
                   p.amount, p.status, p.date, p.payment_type,
                   p.receipt_file_id, p.plan_id
            FROM payments p
            JOIN users u ON p.user_id = u.id
            WHERE p.status = 'pending'
            ORDER BY p.date DESC
        ''')
        rows = cursor.fetchall()
        conn.close()
        return [{
            'id': r[0], 'user_id': r[1], 'telegram_id': r[2],
            'username': r[3], 'first_name': r[4], 'amount': r[5],
            'status': r[6], 'date': r[7], 'payment_type': r[8],
            'receipt_file_id': r[9], 'plan_id': r[10]
        } for r in rows]

    # ========== SUPPORT OPERATIONS ==========
    def add_support_message(self, user_id: int, message: str) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO support_messages (user_id, message) VALUES (?, ?)', (user_id, message))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding support message: {e}")
            return False
        finally:
            conn.close()

    # ========== STATISTICS ==========
    def get_statistics(self) -> Dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT COUNT(*) FROM users')
            total_users = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM users WHERE last_activity >= datetime('now', '-7 days')")
            active_users = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM services WHERE status = 'active'")
            total_services = cursor.fetchone()[0]
            cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'approved'")
            total_revenue = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM payments WHERE status = 'pending'")
            pending_payments = cursor.fetchone()[0]
            return {
                'total_users': total_users, 'active_users': active_users,
                'total_services': total_services, 'total_revenue': total_revenue,
                'pending_payments': pending_payments
            }
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {'total_users': 0, 'active_users': 0, 'total_services': 0, 'total_revenue': 0, 'pending_payments': 0}
        finally:
            conn.close()

    def get_all_users(self) -> List[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT u.id, u.telegram_id, u.username, u.first_name, u.join_date,
                       u.wallet, u.last_activity,
                       COUNT(DISTINCT s.id) as service_count,
                       COALESCE(SUM(p.amount), 0) as total_spent
                FROM users u
                LEFT JOIN services s ON u.id = s.user_id AND s.status = 'active'
                LEFT JOIN payments p ON u.id = p.user_id AND p.status = 'approved'
                GROUP BY u.id
                ORDER BY u.join_date DESC
            ''')
            users = []
            for row in cursor.fetchall():
                users.append({
                    'id': row[0], 'telegram_id': row[1], 'username': row[2],
                    'first_name': row[3], 'join_date': row[4], 'wallet': row[5],
                    'last_activity': row[6], 'service_count': row[7], 'total_spent': row[8]
                })
            return users
        except Exception as e:
            logger.error(f"Error getting users: {e}")
            return []
        finally:
            conn.close()

    def search_user_by_telegram_id(self, telegram_id: int) -> Optional[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT u.id, u.telegram_id, u.username, u.first_name, u.join_date,
                       u.wallet, u.is_active,
                       COUNT(DISTINCT s.id) as service_count,
                       COALESCE(SUM(p.amount), 0) as total_spent
                FROM users u
                LEFT JOIN services s ON u.id = s.user_id AND s.status = 'active'
                LEFT JOIN payments p ON u.id = p.user_id AND p.status = 'approved'
                WHERE u.telegram_id = ?
                GROUP BY u.id
            ''', (telegram_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'id': row[0], 'telegram_id': row[1], 'username': row[2],
                    'first_name': row[3], 'join_date': row[4], 'wallet': row[5],
                    'is_active': row[6], 'service_count': row[7], 'total_spent': row[8]
                }
            return None
        except Exception as e:
            logger.error(f"Error searching user: {e}")
            return None
        finally:
            conn.close()


# ==================== BOT HANDLERS ====================
class BotHandlers:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def is_admin(self, user_id: int) -> bool:
        return user_id in ADMIN_IDS

    # ==================== HELPER ====================
    async def _notify_admins(self, context, text: str, parse_mode: str = 'HTML'):
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(admin_id, text, parse_mode=parse_mode)
            except Exception as e:
                logger.error(f"Error notifying admin {admin_id}: {e}")

    # ==================== START ====================
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not self.db.user_exists(user.id):
            self.db.create_user(user.id, user.username, user.first_name)
        self.db.update_user_activity(user.id)
        # پاک کردن state قبلی
        context.user_data.clear()

        if self.is_admin(user.id):
            await self.show_admin_menu(update, context)
        else:
            await self.show_user_menu(update, context)

    # ==================== MENUS ====================
    async def show_user_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            ['🛒 خرید سرویس', '📦 سرویس های من'],
            ['👛 کیف پول', '💬 پشتیبانی']
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        text = '👋 خوش آمدید به ربات فروش سرویس V2Ray\n\nلطفا گزینه مورد نظر را انتخاب کنید:'
        msg = update.message or (update.callback_query.message if update.callback_query else None)
        if msg:
            await msg.reply_text(text, reply_markup=reply_markup)

    async def show_admin_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            ['📊 آمار', '👤 کاربران'],
            ['💰 تراکنش‌ها', '📦 پلن‌ها'],
            ['📨 پیام همگانی', '⚙️ تنظیمات']
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        text = '🛡️ پنل مدیریت\nگزینه مورد نظر را انتخاب کنید:'
        msg = update.message or (update.callback_query.message if update.callback_query else None)
        if msg:
            await msg.reply_text(text, reply_markup=reply_markup)

    # ==================== MESSAGE ROUTER ====================
    async def handle_user_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        self.db.update_user_activity(user.id)
        user_id = self.db.get_user_id(user.id)
        text = update.message.text

        if self.is_admin(user.id):
            await self.handle_admin_message(update, context)
            return

        state = context.user_data.get('state')

        if state == UserState.WAITING_FOR_SUPPORT_MESSAGE.value:
            await self.receive_support_message(update, context, user_id)
        else:
            if text == '🛒 خرید سرویس':
                await self.show_plans(update, context)
            elif text == '📦 سرویس های من':
                await self.show_user_services(update, context, user_id)
            elif text == '👛 کیف پول':
                await self.show_wallet(update, context, user_id)
            elif text == '💬 پشتیبانی':
                await self.start_support_chat(update, context)
            else:
                await update.message.reply_text('❌ لطفا از منو استفاده کنید.')

    async def handle_photo_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """هندل عکس رسید از کاربر"""
        user = update.effective_user
        state = context.user_data.get('state')

        logger.info(f"Photo received from {user.id}, state={state}, user_data={context.user_data}")

        if state == UserState.WAITING_FOR_RECEIPT_PHOTO.value:
            await self.receive_receipt_photo(update, context)
        else:
            # اگه state نداره، راهنمایی بده
            await update.message.reply_text(
                '⚠️ برای ارسال رسید، ابتدا روی دکمه *"📤 ارسال رسید پرداخت کارت"* کلیک کنید.\n\n'
                'سپس عکس رسید را بفرستید.',
                parse_mode='Markdown'
            )

    # ==================== USER: خرید سرویس ====================
    async def show_plans(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        plans = self.db.get_all_plans()
        if not plans:
            await update.message.reply_text('❌ هیچ پلن فعالی موجود نیست.')
            return

        text = '📦 *پلن‌های موجود:*\n\n'
        keyboard = []
        for plan in plans:
            text += f'• *{plan.name}*\n'
            text += f'  💵 {plan.price:,.0f} تومان\n'
            text += f'  📊 {plan.traffic} | ⏱️ {plan.duration} روز\n\n'
            keyboard.append([InlineKeyboardButton(
                f"🛒 {plan.name} — {plan.price:,.0f}t",
                callback_data=f"buy_plan_{plan.id}"
            )])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def handle_plan_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش فاکتور + گزینه‌های پرداخت"""
        query = update.callback_query
        await query.answer()

        plan_id = int(query.data.split('_')[2])
        plan = self.db.get_plan(plan_id)
        if not plan:
            await query.edit_message_text('❌ پلن یافت نشد.')
            return

        telegram_id = query.from_user.id
        user_id = self.db.get_user_id(telegram_id)
        wallet = self.db.get_user_wallet(user_id)

        # ذخیره پلن انتخابی
        context.user_data['selected_plan_id'] = plan_id

        invoice_text = f"""
🧾 *فاکتور سفارش*
━━━━━━━━━━━━━━━━━━━━━━━
📦 پلن: *{plan.name}*
📊 ترافیک: {plan.traffic}
⏱️ مدت: {plan.duration} روز
━━━━━━━━━━━━━━━━━━━━━━━
💵 مبلغ قابل پرداخت: *{plan.price:,.0f} تومان*
━━━━━━━━━━━━━━━━━━━━━━━
💳 *شماره کارت:*
`{CARD_NUMBER}`
👤 به نام: {CARD_HOLDER}
🏦 بانک: {CARD_BANK}
━━━━━━━━━━━━━━━━━━━━━━━
"""

        keyboard = []

        # اگه موجودی کافی داره، گزینه پرداخت از کیف پول هم بده
        if wallet >= plan.price:
            invoice_text += f'\n👛 موجودی کیف پول شما: *{wallet:,.0f} تومان* ✅\n'
            keyboard.append([InlineKeyboardButton(
                f'👛 پرداخت از کیف پول ({plan.price:,.0f}t)',
                callback_data=f'pay_wallet_{plan_id}'
            )])

        keyboard.append([InlineKeyboardButton('📤 ارسال رسید پرداخت کارت', callback_data=f'send_receipt_plan_{plan_id}')])
        keyboard.append([InlineKeyboardButton('❌ انصراف', callback_data='back_to_menu')])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(invoice_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def pay_from_wallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پرداخت مستقیم از کیف پول"""
        query = update.callback_query
        await query.answer()

        plan_id = int(query.data.split('_')[2])
        plan = self.db.get_plan(plan_id)
        telegram_id = query.from_user.id
        user_id = self.db.get_user_id(telegram_id)
        wallet = self.db.get_user_wallet(user_id)

        if wallet < plan.price:
            await query.edit_message_text('❌ موجودی کافی نیست.')
            return

        if not self.db.deduct_wallet(user_id, plan.price):
            await query.edit_message_text('❌ خطا در پردازش پرداخت.')
            return

        # ثبت سرویس pending
        service_id = self.db.create_pending_service(user_id, plan_id)
        # ثبت پرداخت approved (چون از کیف پول بوده)
        payment_id = self.db.add_payment(user_id, plan.price, 'wallet_purchase', None, plan_id)
        self.db.approve_payment(payment_id)

        await query.edit_message_text(
            '✅ *پرداخت از کیف پول موفق!*\n\n'
            f'📦 پلن: {plan.name}\n'
            f'💵 مبلغ: {plan.price:,.0f} تومان\n\n'
            '⏳ ادمین به زودی کانفیگ شما را ارسال می‌کند.',
            parse_mode='Markdown'
        )

        # اطلاع به ادمین
        admin_text = (
            f'💰 <b>خرید از کیف پول جدید!</b>\n\n'
            f'👤 کاربر: {query.from_user.mention_html()}\n'
            f'🆔 Telegram ID: <code>{telegram_id}</code>\n'
            f'📦 پلن: {plan.name}\n'
            f'💵 مبلغ: {plan.price:,.0f} تومان\n'
            f'🔢 Service ID: {service_id}\n\n'
            f'برای ارسال کانفیگ:\n'
            f'/send_config_{service_id}_{telegram_id}'
        )
        await self._notify_admins(context, admin_text)

    async def request_receipt_for_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """درخواست ارسال رسید برای خرید کارتی"""
        query = update.callback_query
        await query.answer()

        plan_id = int(query.data.split('_')[3])
        plan = self.db.get_plan(plan_id)

        context.user_data['state'] = UserState.WAITING_FOR_RECEIPT_PHOTO.value
        context.user_data['receipt_type'] = 'plan_purchase'
        context.user_data['receipt_plan_id'] = plan_id

        await query.edit_message_text(
            f'📤 *ارسال رسید پرداخت*\n\n'
            f'📦 پلن: {plan.name}\n'
            f'💵 مبلغ: {plan.price:,.0f} تومان\n\n'
            f'لطفا *عکس رسید* واریز را ارسال کنید:',
            parse_mode='Markdown'
        )

    # ==================== USER: کیف پول ====================
    async def show_wallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
        wallet = self.db.get_user_wallet(user_id)
        text = (
            f'👛 *کیف پول*\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━\n'
            f'موجودی: *{wallet:,.0f} تومان*\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━'
        )
        keyboard = [
            [InlineKeyboardButton('💳 شارژ کیف پول', callback_data='charge_wallet')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def charge_wallet_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش اطلاعات واریز برای شارژ کیف پول"""
        query = update.callback_query
        await query.answer()

        invoice_text = (
            f'💳 *شارژ کیف پول*\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━\n'
            f'شماره کارت:\n`{CARD_NUMBER}`\n'
            f'به نام: {CARD_HOLDER}\n'
            f'بانک: {CARD_BANK}\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━\n'
            f'مبلغ دلخواه واریز کنید و سپس *عکس رسید* ارسال کنید.\n'
            f'پس از تایید ادمین، کیف پول شما شارژ می‌شود.'
        )

        keyboard = [
            [InlineKeyboardButton('📤 ارسال رسید', callback_data='send_receipt_wallet')],
            [InlineKeyboardButton('❌ انصراف', callback_data='back_to_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(invoice_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def request_receipt_for_wallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """درخواست رسید برای شارژ کیف پول"""
        query = update.callback_query
        await query.answer()

        context.user_data['state'] = UserState.WAITING_FOR_RECEIPT_PHOTO.value
        context.user_data['receipt_type'] = 'wallet_charge'

        await query.edit_message_text(
            '📤 *ارسال رسید شارژ کیف پول*\n\n'
            'لطفا *عکس رسید* واریز را ارسال کنید:',
            parse_mode='Markdown'
        )

    # ==================== RECEIPT HANDLER ====================
    async def receive_receipt_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت عکس رسید از کاربر"""
        user = update.effective_user
        user_id = self.db.get_user_id(user.id)
        receipt_type = context.user_data.get('receipt_type', '')

        logger.info(f"Processing receipt from user {user.id}, type={receipt_type}, user_id={user_id}")

        if not user_id:
            await update.message.reply_text('❌ خطا: کاربر یافت نشد. /start را بزنید.')
            return

        if not update.message.photo:
            await update.message.reply_text('❌ لطفا عکس ارسال کنید.')
            return

        # گرفتن بهترین کیفیت عکس
        photo = update.message.photo[-1]
        file_id = photo.file_id
        logger.info(f"Photo file_id: {file_id}")

        try:
            if receipt_type == 'plan_purchase':
                plan_id = context.user_data.get('receipt_plan_id')
                if not plan_id:
                    await update.message.reply_text('❌ خطا: پلن انتخاب نشده. دوباره از منو خرید کنید.')
                    context.user_data.clear()
                    return

                plan = self.db.get_plan(plan_id)
                if not plan:
                    await update.message.reply_text('❌ خطا: پلن یافت نشد.')
                    context.user_data.clear()
                    return

                # ثبت پرداخت و سرویس pending
                payment_id = self.db.add_payment(user_id, plan.price, 'card_purchase', file_id, plan_id)
                service_id = self.db.create_pending_service(user_id, plan_id)

                logger.info(f"Created payment_id={payment_id}, service_id={service_id}")

                await update.message.reply_text(
                    '✅ *رسید دریافت شد!*\n\n'
                    f'📦 پلن: {plan.name}\n'
                    f'🔢 شناسه پرداخت: #{payment_id}\n\n'
                    '⏳ پس از تایید ادمین، کانفیگ برای شما ارسال می‌شود.',
                    parse_mode='Markdown'
                )

                caption = (
                    f'📥 <b>رسید خرید سرویس جدید!</b>\n\n'
                    f'👤 کاربر: {user.mention_html()}\n'
                    f'🆔 Telegram ID: <code>{user.id}</code>\n'
                    f'📦 پلن: {plan.name}\n'
                    f'💵 مبلغ: {plan.price:,.0f} تومان\n'
                    f'🔢 Payment ID: #{payment_id}\n'
                    f'🔢 Service ID: #{service_id}\n'
                    f'⏰ {datetime.now().strftime("%Y-%m-%d %H:%M")}'
                )
                approve_data = f'aap|{payment_id}|{service_id}|{user.id}|{plan_id}'
                reject_data = f'arj|{payment_id}|{user.id}'
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton('✅ تایید و ارسال کانفیگ', callback_data=approve_data),
                    InlineKeyboardButton('❌ رد رسید', callback_data=reject_data)
                ]])

                sent_count = 0
                for admin_id in ADMIN_IDS:
                    try:
                        await context.bot.send_photo(
                            admin_id, file_id,
                            caption=caption,
                            parse_mode='HTML',
                            reply_markup=keyboard
                        )
                        sent_count += 1
                        logger.info(f"Receipt sent to admin {admin_id}")
                    except Exception as e:
                        logger.error(f"Error sending receipt to admin {admin_id}: {e}")

                if sent_count == 0:
                    logger.error("Receipt not sent to ANY admin!")

            elif receipt_type == 'wallet_charge':
                payment_id = self.db.add_payment(user_id, 0, 'wallet_charge', file_id, None)

                logger.info(f"Wallet charge payment_id={payment_id}")

                await update.message.reply_text(
                    '✅ *رسید دریافت شد!*\n\n'
                    f'🔢 شناسه درخواست: #{payment_id}\n\n'
                    '⏳ پس از بررسی ادمین، کیف پول شما شارژ می‌شود.',
                    parse_mode='Markdown'
                )

                caption = (
                    f'💳 <b>رسید شارژ کیف پول جدید!</b>\n\n'
                    f'👤 کاربر: {user.mention_html()}\n'
                    f'🆔 Telegram ID: <code>{user.id}</code>\n'
                    f'🔢 Payment ID: #{payment_id}\n'
                    f'⏰ {datetime.now().strftime("%Y-%m-%d %H:%M")}\n\n'
                    f'مبلغ واریزی را وارد کنید و تایید کنید:'
                )
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton('✅ تایید و شارژ کیف پول', callback_data=f'aaw|{payment_id}|{user.id}'),
                    InlineKeyboardButton('❌ رد رسید', callback_data=f'arj|{payment_id}|{user.id}')
                ]])

                sent_count = 0
                for admin_id in ADMIN_IDS:
                    try:
                        await context.bot.send_photo(
                            admin_id, file_id,
                            caption=caption,
                            parse_mode='HTML',
                            reply_markup=keyboard
                        )
                        sent_count += 1
                        logger.info(f"Wallet receipt sent to admin {admin_id}")
                    except Exception as e:
                        logger.error(f"Error sending wallet receipt to admin {admin_id}: {e}")

            else:
                logger.error(f"Unknown receipt_type: '{receipt_type}'")
                await update.message.reply_text('❌ خطا: نوع رسید نامشخص. دوباره از منو شروع کنید.')

        except Exception as e:
            logger.error(f"receive_receipt_photo error: {e}", exc_info=True)
            await update.message.reply_text('❌ خطا در پردازش رسید. لطفا دوباره تلاش کنید.')

        finally:
            # همیشه state پاک میشه
            context.user_data.clear()

    # ==================== USER: سرویس‌ها ====================
    async def show_user_services(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
        services = self.db.get_user_services(user_id)
        if not services:
            await update.message.reply_text('❌ شما هنوز سرویسی ندارید.')
            return

        text = '📦 *سرویس‌های شما:*\n\n'
        for i, s in enumerate(services, 1):
            status_emoji = {'active': '🟢', 'pending': '🟡', 'expired': '🔴'}.get(s.status, '⚪')
            text += f'{i}. {status_emoji} *{s.plan_name}*\n'
            text += f'   📊 ترافیک: {s.traffic}\n'
            if s.status == 'pending':
                text += f'   ⏳ در انتظار تایید ادمین\n'
            elif s.expiry_date:
                try:
                    expiry = datetime.fromisoformat(s.expiry_date)
                    days_left = (expiry - datetime.now()).days
                    text += f'   ⏰ انقضا: {s.expiry_date[:10]} ({days_left} روز)\n'
                except:
                    pass
            if s.config and s.status == 'active':
                text += f'   🔗 کانفیگ:\n`{s.config}`\n'
            text += '\n'

        await update.message.reply_text(text, parse_mode='Markdown')

    # ==================== USER: پشتیبانی ====================
    async def start_support_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['state'] = UserState.WAITING_FOR_SUPPORT_MESSAGE.value
        keyboard = [[InlineKeyboardButton('❌ انصراف', callback_data='back_to_menu')]]
        await update.message.reply_text(
            '💬 پیام خود را بنویسید:',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def receive_support_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
        msg = update.message.text
        user = update.effective_user
        self.db.add_support_message(user_id, msg)
        context.user_data.clear()
        await update.message.reply_text('✅ پیام شما ثبت شد. به زودی پاسخ داده می‌شود.')
        admin_text = (
            f'💬 <b>پیام پشتیبانی جدید!</b>\n\n'
            f'👤 {user.mention_html()}\n'
            f'🆔 <code>{user.id}</code>\n\n'
            f'📝 {msg}'
        )
        await self._notify_admins(context, admin_text)

    # ==================== ADMIN: callbacks ====================
    async def admin_approve_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ادمین تایید کرد - باید کانفیگ بفرسته"""
        query = update.callback_query
        await query.answer()

        # فرمت: aap|payment_id|service_id|user_telegram_id|plan_id
        parts = query.data.split('|')
        try:
            payment_id = int(parts[1])
            service_id = int(parts[2])
            user_telegram_id = int(parts[3])
            plan_id = int(parts[4])
        except (IndexError, ValueError) as e:
            logger.error(f"admin_approve_plan parse error: {e}, data={query.data}")
            await query.answer('❌ خطا در پردازش داده', show_alert=True)
            return

        plan = self.db.get_plan(plan_id)

        context.user_data['admin_state'] = UserState.ADMIN_WAITING_FOR_CONFIG.value
        context.user_data['pending_payment_id'] = payment_id
        context.user_data['pending_service_id'] = service_id
        context.user_data['pending_user_telegram_id'] = user_telegram_id
        context.user_data['pending_plan'] = {'name': plan.name, 'duration': plan.duration}

        try:
            await query.edit_message_caption(
                caption=query.message.caption + '\n\n✅ تایید شد - در انتظار کانفیگ...',
                parse_mode='HTML'
            )
        except Exception:
            pass

        await context.bot.send_message(
            query.from_user.id,
            f'📤 کانفیگ برای پلن *{plan.name}* را ارسال کنید:\n\n'
            f'(متن کانفیگ را تایپ یا paste کنید)',
            parse_mode='Markdown'
        )

    async def admin_approve_wallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ادمین شارژ کیف پول رو تایید کرد - باید مبلغ بده"""
        query = update.callback_query
        await query.answer()

        # فرمت: aaw|payment_id|user_telegram_id
        parts = query.data.split('|')
        try:
            payment_id = int(parts[1])
            user_telegram_id = int(parts[2])
        except (IndexError, ValueError) as e:
            logger.error(f"admin_approve_wallet parse error: {e}, data={query.data}")
            await query.answer('❌ خطا در پردازش داده', show_alert=True)
            return

        context.user_data['admin_state'] = UserState.ADMIN_WAITING_FOR_WALLET_AMOUNT.value
        context.user_data['pending_payment_id'] = payment_id
        context.user_data['pending_user_telegram_id'] = user_telegram_id

        try:
            await query.edit_message_caption(
                caption=query.message.caption + '\n\n✅ تایید شد - در انتظار مبلغ...',
                parse_mode='HTML'
            )
        except Exception:
            pass

        await context.bot.send_message(
            query.from_user.id,
            '💰 مبلغ شارژ کیف پول را وارد کنید (تومان):',
        )

    async def admin_reject_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ادمین رسید رو رد کرد"""
        query = update.callback_query
        await query.answer()

        # فرمت: arj|payment_id|user_telegram_id
        parts = query.data.split('|')
        try:
            payment_id = int(parts[1])
            user_telegram_id = int(parts[2])
        except (IndexError, ValueError) as e:
            logger.error(f"admin_reject parse error: {e}, data={query.data}")
            await query.answer('خطا در پردازش داده', show_alert=True)
            return

        self.db.reject_payment(payment_id)

        await query.edit_message_caption(
            caption=query.message.caption + '\n\n❌ رد شد.',
            parse_mode='HTML'
        )

        try:
            await context.bot.send_message(
                user_telegram_id,
                '❌ *رسید پرداخت شما تایید نشد.*\n\n'
                'در صورت نیاز با پشتیبانی تماس بگیرید.',
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error notifying user: {e}")

    # ==================== ADMIN: message handler ====================
    async def handle_admin_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        admin_state = context.user_data.get('admin_state')

        if admin_state == UserState.ADMIN_WAITING_FOR_CONFIG.value:
            await self.receive_admin_config(update, context)
            return

        if admin_state == UserState.ADMIN_WAITING_FOR_WALLET_AMOUNT.value:
            await self.receive_admin_wallet_amount(update, context)
            return

        if admin_state == UserState.ADMIN_WAITING_FOR_BROADCAST.value:
            await self.send_broadcast(update, context)
            return

        if admin_state == UserState.ADMIN_WAITING_FOR_PLAN_NAME.value:
            await self.receive_plan_name(update, context)
            return
        if admin_state == UserState.ADMIN_WAITING_FOR_PLAN_PRICE.value:
            await self.receive_plan_price(update, context)
            return
        if admin_state == UserState.ADMIN_WAITING_FOR_PLAN_TRAFFIC.value:
            await self.receive_plan_traffic(update, context)
            return
        if admin_state == UserState.ADMIN_WAITING_FOR_PLAN_DURATION.value:
            await self.receive_plan_duration(update, context)
            return

        # دکمه‌های منو اول چک میشن — هر state ای که باشه کنسل میشه
        MENU_BUTTONS = {'📊 آمار', '👤 کاربران', '💰 تراکنش‌ها', '📦 پلن‌ها', '📨 پیام همگانی', '⚙️ تنظیمات'}
        if text in MENU_BUTTONS:
            # کنسل کردن هر state قبلی
            context.user_data.pop('admin_state', None)
            if text == '📊 آمار':
                await self.show_statistics(update, context)
            elif text == '👤 کاربران':
                await self.show_users_list(update, context)
            elif text == '💰 تراکنش‌ها':
                await self.show_pending_payments(update, context)
            elif text == '📦 پلن‌ها':
                await self.show_plans_management(update, context)
            elif text == '📨 پیام همگانی':
                await self.start_broadcast(update, context)
            elif text == '⚙️ تنظیمات':
                await self.show_settings(update, context)
            return

        if admin_state == UserState.ADMIN_SEARCH_USER.value:
            await self.search_and_show_user(update, context)
            return

        await update.message.reply_text('❌ دستور نامشخص.')

    async def receive_admin_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت کانفیگ از ادمین و ارسال به کاربر"""
        config_text = update.message.text.strip()
        payment_id = context.user_data.get('pending_payment_id')
        service_id = context.user_data.get('pending_service_id')
        user_telegram_id = context.user_data.get('pending_user_telegram_id')
        plan_info = context.user_data.get('pending_plan', {})

        # فعال‌سازی سرویس در دیتابیس
        self.db.activate_service(service_id, config_text, plan_info.get('duration', 30))
        self.db.approve_payment(payment_id)

        context.user_data.pop('admin_state', None)
        context.user_data.pop('pending_payment_id', None)
        context.user_data.pop('pending_service_id', None)
        context.user_data.pop('pending_user_telegram_id', None)
        context.user_data.pop('pending_plan', None)

        # ارسال کانفیگ به کاربر
        try:
            await context.bot.send_message(
                user_telegram_id,
                f'🎉 *سرویس شما فعال شد!*\n\n'
                f'📦 پلن: {plan_info.get("name", "")}\n'
                f'⏱️ مدت: {plan_info.get("duration", 30)} روز\n\n'
                f'🔗 *کانفیگ V2Ray:*\n`{config_text}`\n\n'
                f'⚠️ این کانفیگ شخصی است، با کسی به اشتراک نگذارید.',
                parse_mode='Markdown'
            )
            await update.message.reply_text('✅ کانفیگ با موفقیت به کاربر ارسال شد!')
        except Exception as e:
            logger.error(f"Error sending config to user: {e}")
            await update.message.reply_text(f'❌ خطا در ارسال به کاربر: {e}')

    async def receive_admin_wallet_amount(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت مبلغ از ادمین برای شارژ کیف پول"""
        try:
            amount = float(update.message.text.replace(',', '').strip())
            if amount <= 0:
                await update.message.reply_text('❌ مبلغ باید بیشتر از 0 باشد.')
                return

            payment_id = context.user_data.get('pending_payment_id')
            user_telegram_id = context.user_data.get('pending_user_telegram_id')
            user_id = self.db.get_user_id(user_telegram_id)

            # آپدیت مبلغ و تایید پرداخت
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute('UPDATE payments SET amount = ? WHERE id = ?', (amount, payment_id))
            conn.commit()
            conn.close()

            self.db.approve_payment(payment_id)
            self.db.add_wallet(user_id, amount)

            context.user_data.pop('admin_state', None)
            context.user_data.pop('pending_payment_id', None)
            context.user_data.pop('pending_user_telegram_id', None)

            await update.message.reply_text(f'✅ کیف پول کاربر به مقدار {amount:,.0f} تومان شارژ شد!')

            try:
                await context.bot.send_message(
                    user_telegram_id,
                    f'✅ *کیف پول شما شارژ شد!*\n\n'
                    f'💰 مبلغ: *{amount:,.0f} تومان*\n\n'
                    'برای مشاهده موجودی: 👛 کیف پول',
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error notifying user: {e}")

        except ValueError:
            await update.message.reply_text('❌ مبلغ معتبر وارد کنید (فقط عدد).')

    # ==================== ADMIN: سایر ====================
    async def show_statistics(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        stats = self.db.get_statistics()
        text = (
            f'📊 *آمار ربات*\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━\n'
            f'👥 کل کاربران: {stats["total_users"]}\n'
            f'🟢 فعال (۷ روز): {stats["active_users"]}\n'
            f'📦 سرویس‌های فعال: {stats["total_services"]}\n'
            f'💰 درآمد کل: {stats["total_revenue"]:,.0f} تومان\n'
            f'⏳ تراکنش در انتظار: {stats["pending_payments"]}\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━'
        )
        await update.message.reply_text(text, parse_mode='Markdown')

    async def show_users_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        users = self.db.get_all_users()
        text = f'👥 کاربران ({len(users)})\n\n'
        for u in users[:10]:
            text += f'• `{u["telegram_id"]}` — {u.get("username") or u.get("first_name") or "بدون نام"}\n'
        if len(users) > 10:
            text += f'\n... و {len(users) - 10} نفر دیگر'
        text += '\n\n🔍 برای جستجو، Telegram ID را وارد کنید:'
        context.user_data['admin_state'] = UserState.ADMIN_SEARCH_USER.value
        await update.message.reply_text(text, parse_mode='Markdown')

    async def search_and_show_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            telegram_id = int(update.message.text.strip())
            user = self.db.search_user_by_telegram_id(telegram_id)
            context.user_data.pop('admin_state', None)
            if not user:
                await update.message.reply_text(f'❌ کاربر {telegram_id} یافت نشد.')
                return
            text = (
                f'👤 *جزئیات کاربر*\n'
                f'━━━━━━━━━━━━━━━━━━━━━━━\n'
                f'🆔 Telegram ID: `{user["telegram_id"]}`\n'
                f'👤 یوزرنیم: {user["username"] or "ندارد"}\n'
                f'📝 نام: {user["first_name"] or "ندارد"}\n'
                f'📅 عضویت: {str(user["join_date"])[:10]}\n'
                f'👛 کیف پول: {user["wallet"]:,.0f} تومان\n'
                f'📦 سرویس فعال: {user["service_count"]}\n'
                f'💸 کل خرید: {user["total_spent"]:,.0f} تومان\n'
                f'🟢 وضعیت: {"فعال" if user["is_active"] else "غیرفعال"}\n'
                f'━━━━━━━━━━━━━━━━━━━━━━━'
            )
            await update.message.reply_text(text, parse_mode='Markdown')
        except ValueError:
            await update.message.reply_text('❌ Telegram ID معتبر نیست.')

    async def show_pending_payments(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        payments = self.db.get_pending_payments()
        if not payments:
            await update.message.reply_text('✅ تراکنش در انتظاری وجود ندارد.')
            return
        text = f'⏳ *تراکنش‌های در انتظار ({len(payments)})*\n\n'
        for p in payments:
            text += (
                f'🔢 #{p["id"]} | {p["payment_type"]}\n'
                f'👤 {p["username"] or p["first_name"] or "نامشخص"}\n'
                f'💵 {p["amount"]:,.0f} تومان\n'
                f'⏰ {str(p["date"])[:16]}\n'
                f'رسید: {"دارد ✅" if p["receipt_file_id"] else "ندارد ❌"}\n\n'
            )
        await update.message.reply_text(text, parse_mode='Markdown')

    async def show_plans_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        plans = self.db.get_all_plans()
        text = f'📦 *پلن‌ها ({len(plans)})*\n\n'
        for p in plans:
            text += f'#{p.id} *{p.name}* — {p.price:,.0f}t | {p.traffic} | {p.duration}روز\n'
        keyboard = [
            [InlineKeyboardButton('➕ پلن جدید', callback_data='add_new_plan')],
        ]
        if plans:
            keyboard.append([InlineKeyboardButton('🗑️ حذف پلن', callback_data='show_delete_plans')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def add_new_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        context.user_data['admin_state'] = UserState.ADMIN_WAITING_FOR_PLAN_NAME.value
        context.user_data['new_plan'] = {}
        await query.edit_message_text('📝 نام پلن را وارد کنید:')

    async def receive_plan_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['new_plan']['name'] = update.message.text.strip()
        context.user_data['admin_state'] = UserState.ADMIN_WAITING_FOR_PLAN_PRICE.value
        await update.message.reply_text('💵 قیمت پلن را وارد کنید (تومان، فقط عدد):')

    async def receive_plan_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            price = float(update.message.text.replace(',', ''))
            context.user_data['new_plan']['price'] = price
            context.user_data['admin_state'] = UserState.ADMIN_WAITING_FOR_PLAN_TRAFFIC.value
            await update.message.reply_text('📊 ترافیک را وارد کنید (مثال: 100 GB):')
        except ValueError:
            await update.message.reply_text('❌ عدد معتبر وارد کنید.')

    async def receive_plan_traffic(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['new_plan']['traffic'] = update.message.text.strip()
        context.user_data['admin_state'] = UserState.ADMIN_WAITING_FOR_PLAN_DURATION.value
        await update.message.reply_text('⏱️ مدت را وارد کنید (روز، فقط عدد):')

    async def receive_plan_duration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            duration = int(update.message.text)
            plan = context.user_data.get('new_plan', {})
            if self.db.add_plan(plan['name'], plan['price'], plan['traffic'], duration):
                context.user_data.pop('admin_state', None)
                context.user_data.pop('new_plan', None)
                await update.message.reply_text(
                    f'✅ پلن اضافه شد!\n\n'
                    f'📦 {plan["name"]}\n'
                    f'💵 {plan["price"]:,.0f} تومان\n'
                    f'📊 {plan["traffic"]} | ⏱️ {duration} روز'
                )
            else:
                await update.message.reply_text('❌ خطا (احتمالاً نام تکراری).')
        except ValueError:
            await update.message.reply_text('❌ عدد معتبر وارد کنید.')

    async def show_delete_plans(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        plans = self.db.get_all_plans()
        keyboard = [[InlineKeyboardButton(f'🗑️ {p.name}', callback_data=f'delete_plan_{p.id}')] for p in plans]
        keyboard.append([InlineKeyboardButton('❌ انصراف', callback_data='admin_back')])
        await query.edit_message_text('کدام پلن حذف شود؟', reply_markup=InlineKeyboardMarkup(keyboard))

    async def delete_plan_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        plan_id = int(query.data.split('_')[2])
        plan = self.db.get_plan(plan_id)
        self.db.delete_plan(plan_id)
        await query.edit_message_text(f'✅ پلن "{plan.name}" حذف شد.')

    async def start_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['admin_state'] = UserState.ADMIN_WAITING_FOR_BROADCAST.value
        await update.message.reply_text('📨 پیام همگانی را بنویسید:')

    async def send_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.message.text
        users = self.db.get_all_users()
        context.user_data.pop('admin_state', None)
        success, failed = 0, 0
        await update.message.reply_text(f'📨 در حال ارسال به {len(users)} کاربر...')
        for u in users:
            try:
                await context.bot.send_message(u['telegram_id'], f'📨 پیام از مدیر:\n\n{msg}')
                success += 1
            except:
                failed += 1
        await update.message.reply_text(f'✅ ارسال شد!\n✅ موفق: {success}\n❌ ناموفق: {failed}')

    async def show_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = (
            f'⚙️ *تنظیمات*\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━\n'
            f'💳 شماره کارت: `{CARD_NUMBER}`\n'
            f'👤 صاحب کارت: {CARD_HOLDER}\n'
            f'🏦 بانک: {CARD_BANK}\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━\n'
            f'برای تغییر، متغیرهای محیطی را ویرایش کنید:\n'
            f'`CARD_NUMBER`, `CARD_HOLDER`, `CARD_BANK`'
        )
        await update.message.reply_text(text, parse_mode='Markdown')

    # ==================== CALLBACK ROUTER ====================
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        telegram_id = query.from_user.id

        try:
            if data == 'back_to_menu':
                if self.is_admin(telegram_id):
                    await self.show_admin_menu(update, context)
                else:
                    await self.show_user_menu(update, context)
            elif data == 'admin_back':
                await self.show_admin_menu(update, context)
            elif data.startswith('buy_plan_'):
                await self.handle_plan_selection(update, context)
            elif data.startswith('pay_wallet_'):
                await self.pay_from_wallet(update, context)
            elif data.startswith('send_receipt_plan_'):
                await self.request_receipt_for_plan(update, context)
            elif data == 'charge_wallet':
                await self.charge_wallet_start(update, context)
            elif data == 'send_receipt_wallet':
                await self.request_receipt_for_wallet(update, context)
            elif data.startswith('aap|'):
                await self.admin_approve_plan(update, context)
            elif data.startswith('aaw|'):
                await self.admin_approve_wallet(update, context)
            elif data.startswith('arj|'):
                await self.admin_reject_payment(update, context)
            elif data == 'add_new_plan':
                await self.add_new_plan(update, context)
            elif data == 'show_delete_plans':
                await self.show_delete_plans(update, context)
            elif data.startswith('delete_plan_'):
                await self.delete_plan_confirm(update, context)
        except Exception as e:
            logger.error(f"Callback error: {e}", exc_info=True)
            try:
                await query.edit_message_text('❌ خطا در پردازش. دوباره امتحان کنید.')
            except:
                pass


# ==================== MAIN ====================
def main():
    logger.info("Starting V2Ray Config Bot...")

    db = DatabaseManager(DATABASE_PATH)

    if not db.get_all_plans():
        logger.info("Adding default plans...")
        db.add_plan('90 روزه', 390000, '1 GB', 90)
        db.add_plan('90 روزه', 780000, '2 GB', 90)
        db.add_plan('90 روزه', 1170000, '3 GB', 90)
        db.add_plan('90 روزه',1490000, '5 GB', 90)
        db.add_plan('90 روزه',2490000, '10 GB', 90)
        db.add_plan('90 روزه',3575000, '15 GB', 90)
        db.add_plan('90 روزه',4950000, '20 GB', 90)
        
    app = Application.builder().token(BOT_TOKEN).build()
    handlers = BotHandlers(db)

    app.add_handler(CommandHandler('start', handlers.start))
    app.add_handler(MessageHandler(filters.PHOTO, handlers.handle_photo_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_user_message))
    app.add_handler(CallbackQueryHandler(handlers.handle_callback))

    logger.info("Bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
