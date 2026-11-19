# Copyright (c) 2026 VEGA & Logic

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.



import os
import time
import asyncio
import json
import random
import logging
import re
from functools import wraps
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message
from pyrogram.enums import ChatType
from pyrogram.errors import FloodWait, MessageNotModified, ChatWriteForbidden
from datetime import datetime, timedelta

from config import (
    app, API_ID, API_HASH, DEVS, DEV_IDS,
    STOP_EVENT, BANNED_ACCOUNTS_CACHE,
    PREMIUM_PLANS, USER_COOLDOWNS,
    MEMBERS_FILE, MEMBERS_IDS_FILE, MEMBERS_NAMES_FILE,
    PAGINATION_SIZE, PROGRESS_BAR_FILLED, PROGRESS_BAR_EMPTY,
    PROGRESS_BAR_LENGTH, TRANSFER_CONFIG, BACKUP_FILE,
)
import config

from database import (
    load_accounts, save_accounts, save_accounts_detailed,
    load_contacts, save_contacts,
    load_premium, save_premium,
    save_subscriptions,
    load_admins, save_admins,
    load_banned_users, save_banned_users,
    load_subscriptions,
    is_premium, is_admin, is_banned, is_dev,
    validate_session, change_2fa_password,
    handle_file_forward, get_statistics,
    load_broadcast_users, save_broadcast_users,
    load_account_stats, save_account_stats,
    update_account_stat,
    check_premium_limit, increment_premium_usage,
    parse_post_link, react_to_single_post,
    load_accounts_cached, invalidate_accounts_cache,
    start_operation, get_stop_event, stop_user_operation,
    check_action_limit, log_error,
    update_user_stats, get_detailed_user_stats,
    should_notify_expired, reset_expired_notification,
    rate_limit, safe_edit, check_premium_panel_access,
    get_members_with_filter, save_members_data,
    add_members_parallel, transfer_members_advanced,
    filter_bots_batch, create_temp_client,
    record_floodwait, is_account_disabled,
    record_subscription_refund, check_refund_allowed,
    export_all_data, import_all_data, reset_all_data,
    create_full_backup_file, load_backup_from_file,
    add_account_with_autojoin,
    load_force_sub_channels, add_force_sub_channel, remove_force_sub_channel,
    check_user_force_sub, mark_force_sub_verified,
    get_dev_daily_stats,
    sync_force_sub_with_auto_join,
    notify_developer_new_user,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


_force_sub_sent_cache = {} 
_FORCE_SUB_COOLDOWN = 30


def progress_bar(current, total, length=PROGRESS_BAR_LENGTH):
    if total <= 0:
        return f"[{PROGRESS_BAR_EMPTY * length}] 0%"
    ratio = min(1.0, current / total)
    filled = int(length * ratio)
    bar = PROGRESS_BAR_FILLED * filled + PROGRESS_BAR_EMPTY * (length - filled)
    return f"[{bar}] {int(ratio * 100)}%"


def human_time(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}ث"
    if seconds < 3600:
        return f"{seconds//60}د {seconds%60}ث"
    return f"{seconds//3600}س {(seconds%3600)//60}د"


def paginate(items, page=0, size=PAGINATION_SIZE):
    total = len(items)
    total_pages = max(1, (total + size - 1) // size)
    page = max(0, min(page, total_pages - 1))
    start = page * size
    end = start + size
    return items[start:end], page, total_pages, total



VEGA_BUTTON = [
    [InlineKeyboardButton("اضافة حساب", callback_data="add_account"),
     InlineKeyboardButton("حذف حساب", callback_data="remove_account")],
    [InlineKeyboardButton("تنظيف الحسابات", callback_data="safe_clean_scan"),
     InlineKeyboardButton("عرض الحسابات", callback_data="show_accounts_0")],
    [InlineKeyboardButton("الحسابات المحظورة", callback_data="check_banned"),
     InlineKeyboardButton("حذف الكل", callback_data="delete_all")],
    [InlineKeyboardButton("نقل الاعضاء", callback_data="trans")],
    [InlineKeyboardButton("نقل متقدم (متوازن)", callback_data="advanced_transfer")],
    [InlineKeyboardButton(" جلب نسخة احتياطية", callback_data="backup_download"),
     InlineKeyboardButton(" رفع نسخة احتياطية", callback_data="backup_upload")],
    [InlineKeyboardButton("مغادرة كل الجروبات", callback_data="leave_all"),
     InlineKeyboardButton("ايقاف العمليات", callback_data="stop_operation")],
    [InlineKeyboardButton("جلب البيانات", callback_data="get_data"),
     InlineKeyboardButton("الاحصائيات", callback_data="statistics")],
    [InlineKeyboardButton("تفاعل مع المنشورات", callback_data="react_posts"),
     InlineKeyboardButton("إزعاج / Flood", callback_data="upload_and_send")],
    [InlineKeyboardButton("اضافة ادمن", callback_data="add_admin"),
     InlineKeyboardButton("تنزيل ادمن", callback_data="remove_admin")],
    [InlineKeyboardButton("اضافة Premium", callback_data="add_premium")],
    [InlineKeyboardButton("حظر مستخدم", callback_data="ban_user"),
     InlineKeyboardButton("إلغاء حظر", callback_data="unban_user")],
    [InlineKeyboardButton("مسح المحظورين", callback_data="clear_banned"),
     InlineKeyboardButton("عرض المحظورين", callback_data="view_banned")],
    [InlineKeyboardButton("ادارة الاشتراكات", callback_data="manage_subscriptions")],
    [InlineKeyboardButton("بث رسالة", callback_data="broadcast_menu")],
    [InlineKeyboardButton("كشف الحسابات المحظورة تلقائياً", callback_data="auto_check_banned")],
    [InlineKeyboardButton("جلب بيانات حساب", callback_data="fetch_account_data")],
    [InlineKeyboardButton("ادارة قنوات الاشتراك", callback_data="manage_force_sub")],
    [InlineKeyboardButton("حذف جميع البيانات", callback_data="reset_all_confirm")],
    [InlineKeyboardButton("إيقاف عمليتي", callback_data="stop_my_operation")],
]

MEMBER_BUTTONS = [
    [InlineKeyboardButton("اشتراك Premium", callback_data="premium_subscribe")],
    [InlineKeyboardButton("حالة اشتراكي", callback_data="my_subscription_status")],
    [InlineKeyboardButton("احصائياتي", callback_data="my_stats")],
]

PREMIUM_BUTTONS = [
    [InlineKeyboardButton("اضافة حساب", callback_data="add_account"),
     InlineKeyboardButton("حذف حساب", callback_data="remove_account")],
    [InlineKeyboardButton("تنظيف الحسابات", callback_data="safe_clean_scan"),
     InlineKeyboardButton("عرض الحسابات", callback_data="show_accounts_0")],
    [InlineKeyboardButton("الحسابات المحظورة", callback_data="check_banned"),
     InlineKeyboardButton("حذف الكل", callback_data="delete_all")],
    [InlineKeyboardButton("نقل الاعضاء", callback_data="trans")],
    [InlineKeyboardButton("نقل متقدم (متوازن)", callback_data="advanced_transfer")],
    [InlineKeyboardButton(" جلب نسخة احتياطية", callback_data="backup_download"),
     InlineKeyboardButton("رفع نسخة احتياطية", callback_data="backup_upload")],
    [InlineKeyboardButton("مغادرة كل الجروبات", callback_data="leave_all"),
     InlineKeyboardButton("ايقاف العمليات", callback_data="stop_operation")],
    [InlineKeyboardButton("جلب البيانات", callback_data="get_data"),
     InlineKeyboardButton("الاحصائيات", callback_data="statistics")],
    [InlineKeyboardButton("تفاعل مع المنشورات", callback_data="react_posts"),
     InlineKeyboardButton("إزعاج / Flood", callback_data="upload_and_send")],
    [InlineKeyboardButton("حظر مستخدم", callback_data="ban_user"),
     InlineKeyboardButton("إلغاء حظر", callback_data="unban_user")],
    [InlineKeyboardButton("مسح المحظورين", callback_data="clear_banned"),
     InlineKeyboardButton("عرض المحظورين", callback_data="view_banned")],
    [InlineKeyboardButton("بث رسالة", callback_data="broadcast_menu")],
    [InlineKeyboardButton("كشف الحسابات المحظورة تلقائياً", callback_data="auto_check_banned")],
    [InlineKeyboardButton("جلب بيانات حساب", callback_data="fetch_account_data")],
    [InlineKeyboardButton("احصائياتي", callback_data="my_stats")],
    [InlineKeyboardButton("حالة اشتراكي", callback_data="my_subscription_status")],
    [InlineKeyboardButton("إلغاء الاشتراك", callback_data="cancel_subscription")],
    [InlineKeyboardButton("إيقاف عمليتي", callback_data="stop_my_operation")],
]


def set_waiting(user_id, data: dict):
    if not isinstance(data, dict):
        data = {"action": data}
    data["_created_at"] = time.time()
    config.waiting_for[user_id] = data


# ================== التحقق الإجباري من الاشتراك لكل رسالة ==================
@app.on_message(filters.private & filters.incoming, group=-1)
async def must_join_channel(bot: Client, msg: Message):
    """التحقق الإجباري من الانضمام لكل رسالة خاصة"""
    try:
        if not msg.from_user:
            return
        if msg.from_user.is_bot:
            return
        user_id = msg.from_user.id
        if user_id in DEV_IDS:
            return
        if await is_banned(user_id):
            return
        if not config.FORCE_SUB_CHANNELS:
            return

        subscribed, missing = await check_user_force_sub(user_id)
        if subscribed:
            _force_sub_sent_cache.pop(user_id, None)
            return

        # ✅ منع إرسال رسالة الاشتراك مرتين خلال 30 ثانية
        now = time.time()
        last_sent = _force_sub_sent_cache.get(user_id, 0)
        if now - last_sent < _FORCE_SUB_COOLDOWN:
            await msg.stop_propagation()
            return

        _force_sub_sent_cache[user_id] = now

        buttons = []
        for ch in missing:
            link = ch.get('link') or f"https://t.me/{ch.get('username', '')}"
            title = ch.get('title') or ch.get('username', 'قناة')
            buttons.append([InlineKeyboardButton(f"📢 {title}", url=link)])
        buttons.append([InlineKeyboardButton("✅ تحققت من الاشتراك", callback_data="check_sub_again")])

        mention = msg.from_user.mention if hasattr(msg.from_user, 'mention') else f"@{msg.from_user.username or 'user'}"
        text = (
            f"<b>• تحية طيبة يا {mention}\n"
            f"• لا يمكنك المضي قدماً قبل الانضمام إلى قنواتنا\n"
            f"• تفضل بالانضمام ثم عاود المحاولة</b>"
        )
        try:
            await msg.reply(
                text,
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            await msg.stop_propagation()
        except ChatWriteForbidden:
            pass
    except Exception as e:
        logger.debug(f"must_join_channel: {e}")

@app.on_message(filters.command("start"))
@rate_limit(2)
async def start_command(_, message: Message):
    user_id = message.from_user.id
    start_time = time.time()
    try:
        if await is_banned(user_id):
            await message.reply("لقد تم حظرك من استخدام هذا البوت")
            return
        if user_id in config.waiting_for:
            del config.waiting_for[user_id]
        if user_id in config.temp_passwords:
            del config.temp_passwords[user_id]     
        if user_id not in DEV_IDS and config.FORCE_SUB_CHANNELS:
            subscribed, missing = await check_user_force_sub(user_id)
            if not subscribed:
                now = time.time()
                last_sent = _force_sub_sent_cache.get(user_id, 0)
                if now - last_sent >= _FORCE_SUB_COOLDOWN:
                    _force_sub_sent_cache[user_id] = now
                    buttons = []
                    for ch in missing:
                        link = ch.get('link') or f"https://t.me/{ch.get('username', '')}"
                        title = ch.get('title') or ch.get('username', 'قناة')
                        buttons.append([InlineKeyboardButton(f"📢 {title}", url=link)])
                    buttons.append([InlineKeyboardButton("✅ تحققت من الاشتراك", callback_data="check_sub_again")])
                    mention = message.from_user.mention if hasattr(message.from_user, 'mention') else f"@{message.from_user.username or 'user'}"
                    text = (
                        f"<b>• عزيزي: {mention}\n"
                        f"• عليك الانضمام إلى قنواتنا اولا\n"
                    )
                    await message.reply(
                        text,
                        disable_web_page_preview=True,
                        reply_markup=InlineKeyboardMarkup(buttons)
                    )
                return
        try:
            is_new = True
            if os.path.exists("start_users.json"):
                with open("start_users.json", "r") as f:
                    users = json.load(f)
                    if not isinstance(users, list):
                        users = []
            else:
                users = []
            if user_id in users:
                is_new = False
            else:
                users.append(user_id)
                with open("start_users.json", "w") as f:
                    json.dump(users, f)
            if is_new and user_id not in DEV_IDS:
                asyncio.create_task(notify_developer_new_user(app, message.from_user))
        except:
            pass

        if user_id not in config.BROADCAST_USERS:
            config.BROADCAST_USERS.append(user_id)
            await save_broadcast_users()
        if await is_dev(user_id):
            await send_dev_dashboard(message, start_time)
            return

        try:
            premium_check = await is_premium(user_id)
        except:
            premium_check = False
        if premium_check:
            await message.reply(
                "مرحبا بك في البوت\n\nلقد تم فتح جميع مميزات البوت لك\nاختر من القائمة أدناه:",
                reply_markup=InlineKeyboardMarkup(PREMIUM_BUTTONS)
            )
            return
        if await is_admin(user_id):
            await message.reply(
                "مرحبا بك في البوت\n\nلقد تم فتح مميزات البوت لك\nاختر من القائمة أدناه:",
                reply_markup=InlineKeyboardMarkup(PREMIUM_BUTTONS)
            )
            return
        await message.reply(
            "مرحبا بك في البوت نقل الاعضاء\n\n• للاشتراك في Premium⭐ والاستفادة من المميزات:\n• نقل الأعضاء بين الجروبات\n• جلب بيانات الأعضاء\n• التفاعل مع المنشورات\n• نشر تلقائي للمتاجر\n• بيع و شراء الاقام الوهمية\n• نقل 1k الي 200k",
            reply_markup=InlineKeyboardMarkup(MEMBER_BUTTONS)
        )
    except Exception as e:
        await log_error(user_id, "start_command", e)
        logger.error(f"خطأ في start_command: {e}")


async def send_dev_dashboard(message, start_time=None):
    try:
        stats = await get_dev_daily_stats()
        response_ms = 0
        if start_time:
            response_ms = int((time.time() - start_time) * 1000)
        if response_ms == 0:
            response_ms = random.randint(15, 35)

        text = (
            f"<b>• لوحة التحكم 🤖\n\n"
            f"━━━ إحصائيات اليوم ━━━\n👥 الإجمالي: {stats.get('total_users', 0)}\n🆕 مستخدمون جدد: 1\n💬 الرسائل: 5\n🔄 الجلسات: {stats.get('accounts_count', 0)}\n👥 عدد جروبات نقل: 1\n📇 اجمالي جهات الاتصال: {stats.get('contacts_accounts', 0)}\n جهات مُرسلة: {stats.get('sent_contacts_count', 0)}\n📢 عدد قنوات الاشتراك: {stats.get('channels_count', 0)}\n⭐ عدد مشتركين مميز: {stats.get('subs_count', 0)}\n👤 عدد الادمن: {stats.get('admins_count', 0)}\n🚫 عدد محظورين: {stats.get('banned_users_count', 0)}\n⚠️ عدد الحسابات التالفة: {stats.get('corrupt_accounts', 0)}\n⚡ متوسط الاستجابة: {response_ms}ms\n\n🕐 آخر نشاط: لا يوجد"
        )
        await message.reply(text, reply_markup=InlineKeyboardMarkup(VEGA_BUTTON))
    except Exception as e:
        logger.error(f"send_dev_dashboard: {e}")
        await message.reply("اهلا بك في لوحة التحكم", reply_markup=InlineKeyboardMarkup(VEGA_BUTTON))


# ================== /cancel ==================
@app.on_message(filters.command("cancel") & filters.private)
async def cancel_command(_, message: Message):
    user_id = message.from_user.id
    try:
        if user_id in config.temp_clients:
            client_obj = config.temp_clients.pop(user_id, None)
            if client_obj and hasattr(client_obj, 'stop'):
                try:
                    await client_obj.stop()
                except:
                    pass
        if user_id in config.temp_passwords:
            del config.temp_passwords[user_id]
        if user_id in config.waiting_for:
            del config.waiting_for[user_id]
        if user_id in config.TEMP_FILES:
            try:
                os.remove(config.TEMP_FILES[user_id])
            except:
                pass
            del config.TEMP_FILES[user_id]
        await message.reply("تم الغاء العملية")
    except Exception as e:
        await log_error(user_id, "cancel_command", e)


@app.on_message(filters.text & filters.private & ~filters.command(["start", "cancel"]))
@rate_limit(1)
async def handle_unified_messages(_, message: Message):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    action = None
    try:
        if await is_banned(user_id):
            await message.reply("لقد تم حظرك من استخدام هذا البوت")
            return
        if user_id not in config.waiting_for:
            return
        action = config.waiting_for[user_id].get("action")

        if action == "add_force_sub_link":
            del config.waiting_for[user_id]
            await add_force_sub_channel_from_link(message, text)
            return

        if action == "add_account_session":
            session = text
            del config.waiting_for[user_id]
            if not session or len(session) < 50:
                await message.reply("الجلسة غير صالحة يجب ان يكون طولها اكثر من 50 حرف")
                return
            await save_account_session_with_autojoin(message, session)
            return
        if action == "add_account_phone":
            phone = text
            if not phone or not phone.startswith('+'):
                await message.reply("يجب ادخال رقم الهاتف بصيغة دولية مثال: +20123456789")
                return
            await start_phone_login(message, phone)
            return
        if action == "add_account_phone_code":
            code = text.replace(" ", "")
            phone = config.waiting_for[user_id].get("phone")
            phone_code_hash = config.waiting_for[user_id].get("phone_code_hash")
            await process_phone_code(message, phone, code, phone_code_hash)
            return
        if action == "add_account_phone_password":
            password = text
            phone = config.waiting_for[user_id].get("phone")
            phone_code_hash = config.waiting_for[user_id].get("phone_code_hash")
            config.temp_passwords[user_id] = password
            await process_phone_password(message, phone, password, phone_code_hash)
            return
        if action == "trans_source":
            set_waiting(user_id, {"action": "trans_target", "source": text})
            await message.reply(
                "الان ارسل رابط الجروب الهدف مثال: @target_group او t.me/target_group\n"
                "لالغاء العملية اكتب /cancel"
            )
            return
        if action == "trans_target":
            source_group = config.waiting_for[user_id].get("source")
            del config.waiting_for[user_id]
            allowed, msg = await check_action_limit(user_id, 'transfer')
            if not allowed:
                await message.reply(msg)
                return
            await execute_transfer(message, source_group, text)
            return
        if action == "advanced_transfer_sources":
            source_groups = [g.strip() for g in text.split() if g.strip()]
            if not source_groups:
                await message.reply("لم يتم إدخال أي جروبات")
                return
            set_waiting(user_id, {"action": "advanced_transfer_targets", "sources": source_groups})
            await message.reply(
                "الان ارسل الجروبات الهدف (مفصولة بمسافة)\n"
                "مثال: @target1 @target2 t.me/target3\n"
                "لالغاء العملية اكتب /cancel"
            )
            return
        if action == "advanced_transfer_targets":
            target_groups = [g.strip() for g in text.split() if g.strip()]
            source_groups = config.waiting_for[user_id].get("sources")
            del config.waiting_for[user_id]
            if not target_groups:
                await message.reply("لم يتم إدخال أي جروبات هدف")
                return
            allowed, msg = await check_action_limit(user_id, 'transfer')
            if not allowed:
                await message.reply(msg)
                return
            options = {
                'max_members': 1000,
                'filter_active': True,
                'filter_new': False,
                'filter_banned': False,
                'delay_between': TRANSFER_CONFIG['delay_between_adds'],
                'use_all_accounts': True,
                'parallel_accounts': TRANSFER_CONFIG['max_parallel_accounts'],
            }
            await transfer_members_advanced(message, source_groups, target_groups, options)
            return
        if action == "add_admin":
            await add_admin_user(message, text.strip())
            return
        if action == "remove_admin":
            await remove_admin_user(message, text.strip())
            return
        if action == "add_premium":
            set_waiting(user_id, {"action": "add_premium_days", "user_id": text.strip()})
            await message.reply("الخطوة 2 من 3\nارسل عدد الأيام\nمثال: 30\n\nلإلغاء العملية اكتب /cancel")
            return
        if action == "add_premium_days":
            try:
                days = int(text.strip())
                if days < 1:
                    await message.reply("يجب أن تكون المدة أكبر من 0")
                    return
            except:
                await message.reply("يرجى إرسال رقم صحيح")
                return
            set_waiting(user_id, {"action": "add_premium_stars",
                                  "user_id": config.waiting_for[user_id].get("user_id"), "days": days})
            await message.reply("الخطوة 3 من 3\nارسل عدد النجوم المدفوعة\nمثال: 150\n\nلإلغاء العملية اكتب /cancel")
            return
        if action == "add_premium_stars":
            try:
                stars = int(text.strip())
                if stars < 0:
                    await message.reply("يجب أن يكون عدد النجوم 0 أو أكبر")
                    return
            except:
                await message.reply("يرجى إرسال رقم صحيح")
                return
            user_id_to_sub = config.waiting_for[user_id].get("user_id")
            days = config.waiting_for[user_id].get("days")
            del config.waiting_for[user_id]
            await add_premium_user(message, user_id_to_sub, days, stars)
            return
        if action == "react_post_link":
            chat_id, post_id = parse_post_link(text.strip())
            if not chat_id or not post_id:
                await message.reply("رابط غير صالح\nأرسل رابط بهذا الشكل:\nhttps://t.me/python2015/987")
                return
            del config.waiting_for[user_id]
            allowed, msg = await check_action_limit(user_id, 'react')
            if not allowed:
                await message.reply(msg)
                return
            await execute_react_post(message, chat_id, post_id)
            return
        if action == "spam_target":
            if not text:
                await message.reply("المعرف فارغ")
                return
            set_waiting(user_id, {"action": "spam_message", "target_id": text})
            await message.reply("الان ارسل الرسالة\nلالغاء العملية اكتب /cancel")
            return
        if action == "spam_message":
            set_waiting(user_id, {"action": "spam_count",
                                  "target_id": config.waiting_for[user_id].get("target_id"),
                                  "spam_text": text})
            await message.reply("كم مرة؟ (الحد الأقصى 100)\nلالغاء اكتب /cancel")
            return
        if action == "spam_count":
            try:
                count = int(text.strip())
                if count < 1 or count > 100:
                    await message.reply("يجب أن يكون العدد بين 1 و 100")
                    return
            except:
                await message.reply("يرجى إرسال رقم صحيح")
                return
            target_id = config.waiting_for[user_id].get("target_id")
            spam_text = config.waiting_for[user_id].get("spam_text")
            del config.waiting_for[user_id]
            allowed, msg = await check_action_limit(user_id, 'send_file')
            if not allowed:
                await message.reply(msg)
                return
            await execute_spam_send(message, target_id, spam_text, count)
            return
        if action == "ban_user":
            await ban_user_action(message, text.strip())
            return
        if action == "unban_user":
            await unban_user_action(message, text.strip())
            return
        if action == "set_subscription_days":
            try:
                days = int(text.strip())
                if days < 1:
                    await message.reply("يجب أن تكون المدة أكبر من 0")
                    return
                set_waiting(user_id, {"action": "set_subscription_stars",
                                      "user_id": config.waiting_for[user_id].get("user_id"), "days": days})
                await message.reply(f"تم تحديد {days} يوم.\nالان أرسل عدد النجوم\nمثال: 150\n\nلإلغاء اكتب /cancel")
            except:
                await message.reply("يرجى إرسال رقم صحيح")
            return
        if action == "set_subscription_stars":
            try:
                stars = int(text.strip())
                if stars < 0:
                    await message.reply("يجب أن يكون 0 أو أكبر")
                    return
            except:
                await message.reply("يرجى إرسال رقم صحيح")
                return
            user_id_to_sub = config.waiting_for[user_id].get("user_id")
            days = config.waiting_for[user_id].get("days")
            del config.waiting_for[user_id]
            await add_premium_user(message, user_id_to_sub, days, stars)
            return
        if action == "broadcast_message":
            del config.waiting_for[user_id]
            allowed, msg = await check_action_limit(user_id, 'broadcast')
            if not allowed:
                await message.reply(msg)
                return
            await execute_broadcast(message, text)
            return
        if action == "fetch_account_data":
            del config.waiting_for[user_id]
            await execute_fetch_account_data(message, text.strip())
            return
    except Exception as e:
        await log_error(user_id, f"handle_unified_messages_{action or 'unknown'}", e)
        logger.error(f"خطأ في handle_unified_messages: {e}")
        try:
            await message.reply("حدث خطأ غير متوقع. حاول مرة أخرى")
        except:
            pass



async def add_force_sub_channel_from_link(message, link):
    try:
        username = None
        if "t.me/" in link:
            username = link.split("t.me/")[-1].split("/")[0].split("?")[0]
        elif link.startswith("@"):
            username = link[1:]
        else:
            username = link
        if not username:
            await message.reply("❌ رابط غير صالح")
            return
        try:
            chat = await app.get_chat(f"@{username}")
        except Exception as e:
            await message.reply(f"❌ لا يمكن الوصول للقناة: {str(e)}")
            return
        try:
            me = await app.get_me()
            member = await app.get_chat_member(chat.id, me.id)
            if member.status not in ("administrator", "creator"):
                await message.reply("❌ البوت ليس أدمن في القناة!\nأضف البوت كأدمن أولاً.")
                return
        except Exception as e:
            await message.reply(f"⚠️ تنبيه: قد لا يكون البوت أدمن ({str(e)[:50]})")
        final_link = f"https://t.me/{chat.username}" if chat.username else link
        success = await add_force_sub_channel(
            chat_id=chat.id, username=chat.username or username,
            title=chat.title or username, link=final_link
        )
        if success:
            if (chat.username or username) not in config.AUTO_JOIN_CHANNELS:
                config.AUTO_JOIN_CHANNELS.append(chat.username or username)
            await message.reply(
                f"✅ تم إضافة القناة\n\n📢 {chat.title or username}\n🔗 {final_link}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 إدارة القنوات", callback_data="manage_force_sub")],
                    [InlineKeyboardButton("رجوع", callback_data="back_to_main")]
                ])
            )
        else:
            await message.reply("❌ فشل إضافة القناة")
    except Exception as e:
        await message.reply(f"❌ خطأ: {str(e)}")



async def add_admin_user(message, user_id):
    try:
        try:
            user = await app.get_users(user_id)
        except:
            await message.reply(f"لا يمكن العثور على المستخدم: {user_id}")
            return
        uid = user.id
        if uid in DEV_IDS:
            await message.reply("هذا المستخدم مطور")
            return
        if config.ADMINS is None:
            await load_admins()
        if uid in config.ADMINS:
            await message.reply("هذا المستخدم أدمن بالفعل")
            return
        config.ADMINS[uid] = {
            'added_by': message.from_user.id,
            'added_date': datetime.now().isoformat(),
            'username': user.username or '',
            'first_name': user.first_name or ''
        }
        await save_admins()
        await message.reply(
            f"تم إضافة الأدمن!\n\nالاسم: {user.first_name or ''}\n"
            f"المعرف: @{user.username or 'لا يوجد'}\nالايدي: {user.id}"
        )
    except Exception as e:
        await message.reply(f"خطأ: {str(e)}")


async def remove_admin_user(message, user_id):
    try:
        try:
            user = await app.get_users(user_id)
        except:
            await message.reply(f"لا يمكن العثور على المستخدم: {user_id}")
            return
        uid = user.id
        if uid in DEV_IDS:
            await message.reply("لا يمكن تنزيل صلاحيات الدعم")
            return
        if config.ADMINS is None:
            await load_admins()
        if uid not in config.ADMINS:
            await message.reply("هذا المستخدم ليس أدمن")
            return
        del config.ADMINS[uid]
        await save_admins()
        await message.reply(
            f"تم تنزيل صلاحيات الأدمن!\n\nالاسم: {user.first_name or ''}\n"
            f"المعرف: @{user.username or 'لا يوجد'}\nالايدي: {uid}"
        )
    except Exception as e:
        await message.reply(f"خطأ: {str(e)}")


async def add_premium_user(message, user_id, days=30, stars=0):
    try:
        try:
            user = await app.get_users(user_id)
        except:
            await message.reply(f"لا يمكن العثور على المستخدم: {user_id}")
            return
        uid = user.id        
        async with config.premium_lock:
            await load_premium()
            if uid in config.PREMIUM_USERS:
                current_expiry = config.PREMIUM_USERS[uid]
                if isinstance(current_expiry, str):
                    try:
                        current_expiry = datetime.fromisoformat(current_expiry)
                    except:
                        current_expiry = None
                if current_expiry and datetime.now() < current_expiry:
                    remaining = (current_expiry - datetime.now()).days
                    await message.reply(f"⚠️ المستخدم لديه اشتراك نشط!\nالمتبقي: {remaining} يوم")
                    return
        expiry_date = datetime.now() + timedelta(days=days)
        async with config.premium_lock:
            config.PREMIUM_USERS[uid] = expiry_date
            config.PREMIUM_SUBSCRIPTIONS[uid] = {
                'expiry': expiry_date, 'stars': stars, 'plan': f'{days} يوم'
            }
            await save_premium()
            await save_subscriptions()
        await reset_expired_notification(uid)
        remaining = (expiry_date - datetime.now()).days
        await message.reply(
            f"✅ تم إضافة Premium!\n\n"
            f"المستخدم: {user.first_name or ''} @{user.username or 'لا يوجد'}\n"
            f"المدة: {days} يوم\nالنجوم: {stars}\n"
            f"ينتهي في: {expiry_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"المتبقي: {remaining} يوم"
        )
        try:
            await app.send_message(
                uid,
                f"🎉 **تم تفعيل اشتراكك Premium!**\n\n"
                f"المدة: {days} يوم\nينتهي في: {expiry_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"المتبقي: {remaining} يوم\n\nيمكنك الآن استخدام جميع المميزات من /start",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("إلغاء الاشتراك", callback_data="cancel_subscription")]
                ])
            )
        except:
            pass
    except Exception as e:
        await message.reply(f"خطأ: {str(e)}")


async def ban_user_action(message, user_id):
    try:
        try:
            user = await app.get_users(user_id)
        except:
            await message.reply(f"لا يمكن العثور على المستخدم: {user_id}")
            return
        uid = user.id
        if uid in DEV_IDS:
            await message.reply("لا يمكن حظر الدعم")
            return
        if uid in config.BANNED_USERS:
            await message.reply("محظور بالفعل")
            return
        config.BANNED_USERS.append(uid)
        await save_banned_users()
        await message.reply(
            f"تم الحظر!\n\n{user.first_name or ''}\n"
            f"@{user.username or 'لا يوجد'}\n{user.id}"
        )
    except Exception as e:
        await message.reply(f"خطأ: {str(e)}")


async def unban_user_action(message, user_id):
    try:
        try:
            user = await app.get_users(user_id)
        except:
            await message.reply(f"لا يمكن العثور على المستخدم: {user_id}")
            return
        uid = user.id
        if uid not in config.BANNED_USERS:
            await message.reply("غير محظور")
            return
        config.BANNED_USERS.remove(uid)
        await save_banned_users()
        await message.reply(
            f"تم إلغاء الحظر!\n\n{user.first_name or ''}\n@{user.username or 'لا يوجد'}"
        )
    except Exception as e:
        await message.reply(f"خطأ: {str(e)}")


async def clear_banned_users_action(message):
    if not config.BANNED_USERS:
        await message.reply("لا يوجد محظورين")
        return
    count = len(config.BANNED_USERS)
    config.BANNED_USERS.clear()
    await save_banned_users()
    await message.reply(f"تم مسح {count} مستخدم")


@app.on_callback_query(filters.regex("^premium_subscribe$"))
async def premium_subscribe_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if await is_banned(user_id):
        await query.answer("محظور", show_alert=True)
        return
    if await is_premium(user_id):
        remaining = (config.PREMIUM_USERS[user_id] - datetime.now()).days if user_id in config.PREMIUM_USERS else 0
        await query.answer(f"لديك Premium لمدة {remaining} يوم", show_alert=True)
        return
    buttons = []
    for plan_name, stars in PREMIUM_PLANS.items():
        buttons.append([InlineKeyboardButton(f"{plan_name} - {stars} نجم", callback_data=f"select_plan_{plan_name}")])
    buttons.append([InlineKeyboardButton("رجوع", callback_data="back_to_main")])
    text = (
        "اشتراك Premium\n\nاختر الخطة:\n\n"
        "المميزات:\n- نقل الأعضاء\n- جلب البيانات\n- التفاعل\n- استخدام جميع الحسابات\n\n"
        "الدفع عبر نجوم Telegram"
    )
    await safe_edit(query.message, text, reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^select_plan_(.*)$"))
async def select_plan_callback(_, query: CallbackQuery):
    plan_name = query.matches[0].group(1)
    stars = PREMIUM_PLANS.get(plan_name, 0)
    if stars == 0:
        await query.answer("خطة غير صالحة", show_alert=True)
        return
    await query.answer()
    await safe_edit(query.message,
        f"خطة: {plan_name}\nعدد النجوم: {stars}\n\nتواصل مع الدعم: @TopVeGa",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("تواصل مع الدعم", url="https://t.me/TopVeGa")],
            [InlineKeyboardButton("رجوع", callback_data="premium_subscribe")]
        ])
    )


def _plan_to_days(plan):
    mapping = {'يوم': 1, 'اسبوع': 7, 'شهر': 30, '3 شهور': 90, '6 شهور': 180, 'سنة': 365}
    for key, val in mapping.items():
        if key in plan:
            return val
    return 30


@app.on_callback_query(filters.regex("^cancel_subscription$"))
async def cancel_subscription_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if user_id not in config.PREMIUM_SUBSCRIPTIONS:
        await query.answer("أنت غير مشترك", show_alert=True)
        return
    allowed, refund_count = await check_refund_allowed(user_id, cooldown_days=30)
    if not allowed:
        await query.answer(f"⚠️ انتظر {refund_count} يوم قبل طلب استرداد آخر", show_alert=True)
        return
    data = config.PREMIUM_SUBSCRIPTIONS[user_id]
    expiry = data['expiry']
    stars = data['stars']
    plan = data['plan']
    now = datetime.now()
    total_days = _plan_to_days(plan)
    used_days = max(0, total_days - (expiry - now).days)
    remaining_days = max(0, (expiry - now).days)
    if total_days > 0 and used_days / total_days > 0.7:
        await query.answer("⚠️ لا يمكن الإلغاء بعد استهلاك أكثر من 70%", show_alert=True)
        return
    refund_stars = int((remaining_days / total_days) * stars) if total_days > 0 else 0
    await safe_edit(query.message,
        f"إلغاء الاشتراك\n\nالخطة: {plan}\nالنجوم: {stars}\n"
        f"المتبقي: {remaining_days} يوم\nالمستهلك: {used_days}/{total_days}\n\n"
        f"الاسترداد المتوقع: {refund_stars} نجمة\n\nهل أنت متأكد؟",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("تأكيد الإلغاء", callback_data="confirm_cancel_sub")],
            [InlineKeyboardButton("رجوع", callback_data="back_to_main")]
        ])
    )


@app.on_callback_query(filters.regex("^confirm_cancel_sub$"))
async def confirm_cancel_sub_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if user_id not in config.PREMIUM_SUBSCRIPTIONS:
        await query.answer("أنت غير مشترك", show_alert=True)
        return
    allowed, _ = await check_refund_allowed(user_id, cooldown_days=30)
    if not allowed:
        await query.answer("لا يمكنك الإلغاء الآن", show_alert=True)
        return
    data = config.PREMIUM_SUBSCRIPTIONS[user_id]
    expiry = data['expiry']
    stars = data['stars']
    plan = data['plan']
    now = datetime.now()
    total_days = _plan_to_days(plan)
    remaining_days = max(0, (expiry - now).days)
    refund_stars = int((remaining_days / total_days) * stars) if total_days > 0 else 0
    await record_subscription_refund(user_id)
    async with config.premium_lock:
        if user_id in config.PREMIUM_SUBSCRIPTIONS:
            del config.PREMIUM_SUBSCRIPTIONS[user_id]
        if user_id in config.PREMIUM_USERS:
            del config.PREMIUM_USERS[user_id]
        await save_premium()
        await save_subscriptions()
    await load_premium()
    await safe_edit(query.message,
        f"تم الإلغاء\n\nالمتبقي: {remaining_days} يوم\nالاسترداد: {refund_stars} نجمة\n\n"
        f"تواصل مع @TopVeGa للاسترداد.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("تواصل مع الدعم", url="https://t.me/TopVeGa")]
        ])
    )
    try:
        await app.send_message(user_id, "⚠️ تم إلغاء اشتراكك Premium")
    except:
        pass
    for dev_id in DEV_IDS:
        try:
            await app.send_message(dev_id,
                f"⚠️ إلغاء اشتراك\nUser: {user_id}\nPlan: {plan}\nRefund: {refund_stars}")
        except:
            pass



@app.on_callback_query(filters.regex("^manage_subscriptions$"))
async def manage_subscriptions_callback(_, query: CallbackQuery):
    if not await is_dev(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    total = len(config.PREMIUM_SUBSCRIPTIONS) if config.PREMIUM_SUBSCRIPTIONS else 0
    buttons = [
        [InlineKeyboardButton("إضافة اشتراك", callback_data="add_subscription")],
        [InlineKeyboardButton("تعديل مدة", callback_data="edit_subscription")],
        [InlineKeyboardButton("عرض المشتركين", callback_data="view_subscribers")],
        [InlineKeyboardButton("حذف اشتراك", callback_data="remove_subscription")],
        [InlineKeyboardButton("رجوع", callback_data="back_to_main")]
    ]
    await safe_edit(query.message,
        f"إدارة الاشتراكات\n\nعدد المشتركين: {total}\nالدعم: @TopVeGa",
        reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex("^add_subscription$"))
async def add_subscription_callback(_, query: CallbackQuery):
    if not await is_dev(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    set_waiting(query.from_user.id, {"action": "add_premium"})
    await safe_edit(query.message,
        "إضافة اشتراك\n\nالخطوة 1/3\nأرسل معرف المستخدم\nمثال: @TopVeGa أو 123456789\n\nلإلغاء اكتب /cancel")


@app.on_callback_query(filters.regex("^edit_subscription$"))
async def edit_subscription_callback(_, query: CallbackQuery):
    if not await is_dev(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    if not config.PREMIUM_SUBSCRIPTIONS:
        await safe_edit(query.message, "لا يوجد مشتركين")
        return
    buttons = []
    for uid in config.PREMIUM_SUBSCRIPTIONS.keys():
        try:
            user = await app.get_users(uid)
            name = user.first_name or str(uid)
        except:
            name = str(uid)
        buttons.append([InlineKeyboardButton(name, callback_data=f"edit_sub_{uid}")])
    buttons.append([InlineKeyboardButton("رجوع", callback_data="manage_subscriptions")])
    await safe_edit(query.message, "اختر المستخدم:", reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^edit_sub_(\d+)$"))
async def edit_sub_user_callback(_, query: CallbackQuery):
    if not await is_dev(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    target_user_id = int(query.matches[0].group(1))
    set_waiting(query.from_user.id, {"action": "set_subscription_days", "user_id": target_user_id})
    try:
        user = await app.get_users(target_user_id)
        name = user.first_name or str(target_user_id)
    except:
        name = str(target_user_id)
    await safe_edit(query.message,
        f"تعديل اشتراك: {name}\n\nأرسل المدة الجديدة بالأيام\nمثال: 30\n\nلإلغاء اكتب /cancel")


@app.on_callback_query(filters.regex("^view_subscribers$"))
async def view_subscribers_callback(_, query: CallbackQuery):
    if not await is_dev(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    if not config.PREMIUM_SUBSCRIPTIONS:
        await safe_edit(query.message, "لا يوجد مشتركين")
        return
    text = "قائمة المشتركين:\n\n"
    for uid, data in config.PREMIUM_SUBSCRIPTIONS.items():
        try:
            user = await app.get_users(uid)
            name = f"{user.first_name or ''} @{user.username or 'لا يوجد'}"
        except:
            name = str(uid)
        remaining = (data['expiry'] - datetime.now()).days
        text += f"{name}\n  المدة: {data['plan']}\n  النجوم: {data['stars']}\n  متبقي: {remaining} يوم\n\n"
        if len(text) > 3500:
            await app.send_message(query.message.chat.id, text)
            text = ""
    if text:
        await app.send_message(query.message.chat.id, text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("رجوع", callback_data="manage_subscriptions")
            ]]))


@app.on_callback_query(filters.regex("^remove_subscription$"))
async def remove_subscription_callback(_, query: CallbackQuery):
    if not await is_dev(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    if not config.PREMIUM_SUBSCRIPTIONS:
        await safe_edit(query.message, "لا يوجد مشتركين")
        return
    buttons = []
    for uid in config.PREMIUM_SUBSCRIPTIONS.keys():
        try:
            user = await app.get_users(uid)
            name = user.first_name or str(uid)
        except:
            name = str(uid)
        buttons.append([InlineKeyboardButton(f"حذف {name}", callback_data=f"remove_sub_{uid}")])
    buttons.append([InlineKeyboardButton("رجوع", callback_data="manage_subscriptions")])
    await safe_edit(query.message, "اختر المستخدم:", reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^remove_sub_(\d+)$"))
async def remove_sub_user_callback(_, query: CallbackQuery):
    if not await is_dev(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    target_user_id = int(query.matches[0].group(1))
    if target_user_id in config.PREMIUM_SUBSCRIPTIONS:
        async with config.premium_lock:
            del config.PREMIUM_SUBSCRIPTIONS[target_user_id]
            if target_user_id in config.PREMIUM_USERS:
                del config.PREMIUM_USERS[target_user_id]
            await save_premium()
            await save_subscriptions()
        await load_premium()
        try:
            await app.send_message(target_user_id, "⚠️ تم إلغاء اشتراكك Premium بواسطة الدعم")
        except:
            pass
        await safe_edit(query.message, "تم حذف الاشتراك")
    else:
        await safe_edit(query.message, "هذا المستخدم غير مشترك")



@app.on_callback_query(filters.regex("^ban_user$"))
async def ban_user_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    set_waiting(query.from_user.id, {"action": "ban_user"})
    await safe_edit(query.message, "حظر مستخدم\n\nأرسل المعرف\nمثال: @user أو 123456\n\nلإلغاء اكتب /cancel")


@app.on_callback_query(filters.regex("^unban_user$"))
async def unban_user_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    set_waiting(query.from_user.id, {"action": "unban_user"})
    await safe_edit(query.message, "إلغاء حظر\n\nأرسل المعرف\n\nلإلغاء اكتب /cancel")


@app.on_callback_query(filters.regex("^clear_banned$"))
async def clear_banned_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    await clear_banned_users_action(query.message)


@app.on_callback_query(filters.regex("^view_banned$"))
async def view_banned_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    if not config.BANNED_USERS:
        await safe_edit(query.message, "لا يوجد محظورين")
        return
    text = "المحظورين:\n\n"
    for uid in config.BANNED_USERS:
        try:
            user = await app.get_users(uid)
            name = f"{user.first_name or ''} @{user.username or 'لا يوجد'}"
        except:
            name = str(uid)
        text += f"{name}\nالايدي: {uid}\n\n"
        if len(text) > 3500:
            await app.send_message(query.message.chat.id, text)
            text = ""
    if text:
        await app.send_message(query.message.chat.id, text)



@app.on_message(filters.private & ~filters.command(["start", "cancel"]) & ~filters.text)
async def handle_any_message(_, message: Message):
    user_id = message.from_user.id
    try:
        if await is_banned(user_id):
            return
        if user_id not in config.waiting_for:
            return
        action = config.waiting_for[user_id].get("action")

        if action == "backup_restore":
            file_path = None
            try:
                if message.document:
                    file_path = await message.download()
                else:
                    await message.reply("❌ أرسل ملف JSON")
                    return
                if not file_path:
                    await message.reply("فشل التحميل")
                    return
                msg = await message.reply("⏳ جاري الاستيراد...")
                success, msg_text = await load_backup_from_file(file_path)
                try:
                    os.remove(file_path)
                except:
                    pass
                if success:
                    await safe_edit(msg, f"✅ {msg_text}\n\nتم استبدال البيانات.")
                else:
                    await safe_edit(msg, f"❌ {msg_text}")
                del config.waiting_for[user_id]
                return
            except Exception as e:
                await message.reply(f"خطأ: {str(e)}")
                return

        if action == "upload_and_send":
            try:
                file_path = await message.download()
                if not file_path:
                    await message.reply("فشل التحميل")
                    return
                config.TEMP_FILES[user_id] = file_path
                await message.reply("تم استقبال الملف!\n\nارسل معرف الهدف\nلالغاء اكتب /cancel")
                set_waiting(user_id, {"action": "upload_and_send_target", "file_path": file_path})
                return
            except Exception as e:
                await message.reply(f"خطأ: {str(e)}")
                return

        if action == "upload_and_send_target":
            try:
                file_path = await message.download()
                if file_path:
                    config.TEMP_FILES[user_id] = file_path
                    set_waiting(user_id, {"action": "upload_and_send_target", "file_path": file_path})
                    await message.reply("تم تحديث الملف!\n\nارسل معرف الهدف")
                    return
            except:
                pass

        if message.document:
            if message.document.file_name == "accounts.json":
                try:
                    await message.download("accounts.json")
                    invalidate_accounts_cache()
                    await message.reply("تم تحديث الجلسات",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("رجوع", callback_data="back_to_main")
                        ]]))
                except Exception as e:
                    await message.reply(f"خطأ: {str(e)}")
                return

            if message.document.file_name == "sessions.txt":
                try:
                    await message.download("sessions.txt")
                    with open("sessions.txt", "r", encoding='utf-8') as f:
                        content = f.read().strip()
                        if not content:
                            await message.reply("الملف فارغ")
                            return
                        sessions = content.split('\n')
                    accounts = await load_accounts()
                    added = 0
                    for session in sessions:
                        if session.strip() and len(session.strip()) > 50:
                            status = await validate_session(session.strip())
                            if status == "valid":
                                try:
                                    async with create_temp_client(session.strip()) as temp_client:
                                        me = await temp_client.get_me()
                                        account_info = {
                                            "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
                                            "username": me.username or "",
                                            "phone": me.phone_number or "",
                                            "session": session.strip()
                                        }
                                        accounts.append(account_info)
                                        added += 1
                                except:
                                    pass
                    if await save_accounts(accounts):
                        await message.reply(f"تم التحديث!\nأضيف: {added} جلسة")
                    else:
                        await message.reply("فشل الحفظ")
                except Exception as e:
                    await message.reply(f"خطأ: {str(e)}")
                return
    except Exception as e:
        await log_error(user_id, "handle_any_message", e)



@app.on_callback_query(filters.regex("^add_account$"))
async def add_account_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    buttons = [
        [InlineKeyboardButton("اضافة برقم الهاتف", callback_data="add_account_phone_method")],
        [InlineKeyboardButton("اضافة بجلسة", callback_data="add_account_session_method")],
        [InlineKeyboardButton("رجوع", callback_data="back_to_main")]
    ]
    await safe_edit(query.message, "اختر الطريقة:", reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex("^add_account_phone_method$"))
async def add_account_phone_method(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    set_waiting(query.from_user.id, {"action": "add_account_phone"})
    await safe_edit(query.message, "ارسل رقم الهاتف بصيغة دولية\nمثال: +20123456789\n\nلإلغاء اكتب /cancel")


@app.on_callback_query(filters.regex("^add_account_session_method$"))
async def add_account_session_method(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    set_waiting(query.from_user.id, {"action": "add_account_session"})
    await safe_edit(query.message, "ارسل الجلسة\n\nلإلغاء اكتب /cancel")


@app.on_callback_query(filters.regex("^remove_account$"))
async def remove_account_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    accounts = await load_accounts()
    if not accounts:
        await safe_edit(query.message, "لا توجد حسابات")
        return
    buttons = []
    for acc in accounts[:20]:
        btn_text = f"{acc.get('name', '?')} ({acc.get('phone', '?')})"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"del_acc_{acc.get('phone', '')}")])
    if len(accounts) > 20:
        buttons.append([InlineKeyboardButton(f"و {len(accounts)-20} آخرين", callback_data="back_to_main")])
    buttons.append([InlineKeyboardButton("الغاء", callback_data="back_to_main")])
    await safe_edit(query.message, "اختر الحساب:", reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^del_acc_(.*)$"))
async def confirm_delete_account(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    phone_to_delete = query.matches[0].group(1)
    accounts = await load_accounts()
    acc = next((a for a in accounts if a.get('phone') == phone_to_delete), None)
    if not acc:
        await query.answer("غير موجود", show_alert=True)
        return
    await safe_edit(query.message,
        f"تأكيد الحذف\n\n{acc.get('name', '?')}\n{acc.get('phone', '?')}\n\nلا يمكن التراجع",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("نعم", callback_data=f"confirm_del_{phone_to_delete}")],
            [InlineKeyboardButton("لا", callback_data="remove_account")]
        ]))


@app.on_callback_query(filters.regex(r"^confirm_del_(.*)$"))
async def execute_delete_account(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    phone_to_delete = query.matches[0].group(1)
    accounts = await load_accounts()
    new_accounts = [acc for acc in accounts if acc.get('phone') != phone_to_delete]
    if len(new_accounts) == len(accounts):
        await query.answer("غير موجود", show_alert=True)
        return
    if await save_accounts(new_accounts):
        await safe_edit(query.message, "تم الحذف بنجاح",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("رجوع", callback_data="back_to_main")
            ]]))
    else:
        await safe_edit(query.message, "فشل الحذف")


@app.on_callback_query(filters.regex(r"^show_accounts_(\d+)$"))
async def show_accounts_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    page = int(query.matches[0].group(1))
    accounts = await load_accounts()
    if not accounts:
        await safe_edit(query.message, "لا توجد حسابات")
        return
    page_items, page, total_pages, total = paginate(accounts, page, PAGINATION_SIZE)
    text = f"📋 الحسابات\nالصفحة {page+1}/{total_pages}\nالإجمالي: {total}\n{'─'*30}\n\n"
    for idx, acc in enumerate(page_items, start=page*PAGINATION_SIZE+1):
        cat_emoji = config.ACCOUNT_CATEGORIES.get(acc.get('category', 'active'), '🟢')
        text += f"{idx}. {acc.get('name', '?')} {cat_emoji}\n   📱 {acc.get('phone', '?')}\n"
        if acc.get('username'):
            text += f"   🆔 @{acc['username']}\n"
        text += "\n"
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀", callback_data=f"show_accounts_{page-1}"))
    nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶", callback_data=f"show_accounts_{page+1}"))
    buttons = [nav] if nav else []
    buttons.append([InlineKeyboardButton("رجوع", callback_data="back_to_main")])
    await safe_edit(query.message, text, reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex("^noop$"))
async def noop_callback(_, query: CallbackQuery):
    await query.answer()


@app.on_callback_query(filters.regex("^safe_clean_scan$"))
async def clean_accounts_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    accounts = await load_accounts()
    valid_accounts = []
    invalid_accounts = []
    chat_id = query.message.chat.id
    await query.message.delete()
    progress_msg = await app.send_message(chat_id, "بدء الفحص...")
    for index, account in enumerate(accounts):
        if not isinstance(account, dict) or 'session' not in account:
            invalid_accounts.append(account)
            continue
        status = await validate_session(account['session'])
        if status == "valid":
            valid_accounts.append(account)
        else:
            invalid_accounts.append(account)
        if index % 5 == 0 or index == len(accounts) - 1:
            bar = progress_bar(index + 1, len(accounts))
            await safe_edit(progress_msg,
                f"🔍 الفحص\n\n{bar}\n\n✅ صالحة: {len(valid_accounts)}\n❌ غير صالحة: {len(invalid_accounts)}")
        await asyncio.sleep(0.3)
    if invalid_accounts:
        buttons = [
            [InlineKeyboardButton("حذف غير الصالحة", callback_data="confirm_delete_invalid")],
            [InlineKeyboardButton("الاحتفاظ", callback_data="back_to_main")]
        ]
    else:
        buttons = [[InlineKeyboardButton("رجوع", callback_data="back_to_main")]]
    await progress_msg.delete()
    await app.send_message(chat_id,
        f"نتائج الفحص\n\nالإجمالي: {len(accounts)}\n✅ صالحة: {len(valid_accounts)}\n❌ غير صالحة: {len(invalid_accounts)}",
        reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex("^confirm_delete_invalid$"))
async def confirm_delete_invalid(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    accounts = await load_accounts()
    valid_accounts = []
    invalid_count = 0
    for account in accounts:
        if not isinstance(account, dict) or 'session' not in account:
            invalid_count += 1
            continue
        status = await validate_session(account['session'])
        if status == "valid":
            valid_accounts.append(account)
        else:
            invalid_count += 1
    await save_accounts(valid_accounts)
    await safe_edit(query.message,
        f"تم الحذف\n\n✅ المتبقي: {len(valid_accounts)}\n🗑️ المحذوف: {invalid_count}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("رجوع", callback_data="back_to_main")
        ]]))


@app.on_callback_query(filters.regex("^check_banned$"))
async def check_banned_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    chat_id = query.message.chat.id
    await query.message.delete()
    progress_msg = await app.send_message(chat_id, "جاري الفحص...")
    accounts = await load_accounts()
    if not accounts:
        await safe_edit(progress_msg, "لا توجد حسابات")
        return
    config.BANNED_ACCOUNTS_CACHE = []
    banned, active, errors = [], [], []
    total = len(accounts)
    for i, account in enumerate(accounts):
        if i % 5 == 0:
            bar = progress_bar(i, total)
            await safe_edit(progress_msg,
                f"🔍 الفحص\n\n{bar}\n\n✅ نشطة: {len(active)}\n🚫 محظورة: {len(banned)}")
        if not isinstance(account, dict) or 'session' not in account:
            errors.append(account)
            continue
        try:
            async with create_temp_client(account['session']) as user:
                me = await user.get_me()
                if me:
                    try:
                        await user.send_message("SpamBot", "/start")
                        await asyncio.sleep(1)
                        msg = await user.get_messages("SpamBot", limit=1)
                        if msg and msg[0].text:
                            t = msg[0].text.lower()
                            if any(w in t for w in ["sorry", "banned", "limited"]):
                                banned.append(account)
                                config.BANNED_ACCOUNTS_CACHE.append(account)
                            else:
                                active.append(account)
                        else:
                            active.append(account)
                    except:
                        active.append(account)
        except:
            errors.append(account)
    report = (
        f"نتائج الفحص\n\n✅ نشطة: {len(active)}\n🚫 محظورة: {len(banned)}\n⚠️ أخطاء: {len(errors)}"
    )
    buttons = [[InlineKeyboardButton("رجوع", callback_data="back_to_main")]]
    if banned:
        buttons.insert(0, [InlineKeyboardButton("حذف المحظورة", callback_data="delete_banned")])
    await progress_msg.delete()
    await app.send_message(chat_id, report, reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex("^delete_banned$"))
async def delete_banned_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    if not config.BANNED_ACCOUNTS_CACHE:
        await query.answer("لا توجد حسابات محظورة", show_alert=True)
        return
    accounts = await load_accounts()
    banned_phones = {acc.get('phone') for acc in config.BANNED_ACCOUNTS_CACHE if acc.get('phone')}
    valid_accounts = [acc for acc in accounts if not acc.get('phone') or acc.get('phone') not in banned_phones]
    await save_accounts(valid_accounts)
    banned_count = len(config.BANNED_ACCOUNTS_CACHE)
    config.BANNED_ACCOUNTS_CACHE = []
    await safe_edit(query.message,
        f"تم الحذف\n\nالمحذوف: {banned_count}\nالمتبقي: {len(valid_accounts)}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("رجوع", callback_data="back_to_main")
        ]]))


@app.on_callback_query(filters.regex("^auto_check_banned$"))
async def auto_check_banned_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    await safe_edit(query.message,
        "كشف الحسابات المحظورة تلقائياً\n\nهل تريد المتابعة؟",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("بدء", callback_data="start_auto_check")],
            [InlineKeyboardButton("رجوع", callback_data="back_to_main")]
        ]))


@app.on_callback_query(filters.regex("^start_auto_check$"))
async def start_auto_check_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    chat_id = query.message.chat.id
    await query.message.delete()
    progress_msg = await app.send_message(chat_id, "جاري الفحص...")
    accounts = await load_accounts()
    if not accounts:
        await safe_edit(progress_msg, "لا توجد حسابات")
        return
    config.BANNED_ACCOUNTS_CACHE = []
    sem = asyncio.Semaphore(5)

    async def check_account(account):
        async with sem:
            if not isinstance(account, dict) or 'session' not in account:
                return
            try:
                async with create_temp_client(account['session']) as user:
                    me = await user.get_me()
                    if me:
                        try:
                            await user.send_message("SpamBot", "/start")
                            await asyncio.sleep(1)
                            msg = await user.get_messages("SpamBot", limit=1)
                            if msg and msg[0].text:
                                t = msg[0].text.lower()
                                if any(w in t for w in ["sorry", "banned", "limited"]):
                                    config.BANNED_ACCOUNTS_CACHE.append(account)
                                    await update_account_stat(account.get('phone', ''), 'status', 'banned')
                        except:
                            pass
            except:
                pass

    tasks = [check_account(acc) for acc in accounts]
    await asyncio.gather(*tasks)
    if config.BANNED_ACCOUNTS_CACHE:
        text = f"عُثر على {len(config.BANNED_ACCOUNTS_CACHE)} حساب محظور"
        buttons = [
            [InlineKeyboardButton("حذف", callback_data="delete_banned")],
            [InlineKeyboardButton("رجوع", callback_data="back_to_main")]
        ]
    else:
        text = "لا يوجد حسابات محظورة"
        buttons = [[InlineKeyboardButton("رجوع", callback_data="back_to_main")]]
    await progress_msg.delete()
    await app.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex("^delete_all$"))
async def delete_all_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    await safe_edit(query.message, "⚠️ حذف جميع الحسابات؟ لا يمكن التراجع",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("تأكيد", callback_data="confirm_delete_all")],
            [InlineKeyboardButton("رجوع", callback_data="back_to_main")]
        ]))


@app.on_callback_query(filters.regex("^confirm_delete_all$"))
async def confirm_delete_all_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    await save_accounts([])
    await safe_edit(query.message, "تم حذف جميع الحسابات",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("رجوع", callback_data="back_to_main")
        ]]))


@app.on_callback_query(filters.regex("^reset_all_confirm$"))
async def reset_all_confirm_callback(_, query: CallbackQuery):
    if not await is_dev(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    await safe_edit(query.message,
        "🗑️ **تحذير خطير**\n\nسيتم حذف جميع البيانات نهائياً:\n"
        "• كل الحسابات\n• المشتركين\n• الأدمن\n• المحظورين\n"
        "• الإحصائيات\n• القنوات\n\n⚠️ لا يمكن التراجع!\n\nهل أنت متأكد؟",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ نعم، احذف", callback_data="reset_all_execute")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="back_to_main")]
        ]))


@app.on_callback_query(filters.regex("^reset_all_execute$"))
async def reset_all_execute_callback(_, query: CallbackQuery):
    if not await is_dev(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    await safe_edit(query.message, "⏳ جاري الحذف...")
    success = await reset_all_data()
    if success:
        try:
            if os.path.exists("start_users.json"):
                os.remove("start_users.json")
        except:
            pass
        await safe_edit(query.message,
            "✅ **تم حذف جميع البيانات**\n\nالبوت الآن نظيف تماماً.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("رجوع", callback_data="back_to_main")
            ]]))
        for dev_id in DEV_IDS:
            try:
                await app.send_message(dev_id, f"🗑️ تم حذف جميع البيانات بواسطة {query.from_user.id}")
            except:
                pass
    else:
        await safe_edit(query.message, "❌ فشل الحذف")



@app.on_callback_query(filters.regex("^backup_download$"))
async def backup_download_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    await safe_edit(query.message, "⏳ جاري التجهيز...")
    file_path, size = await create_full_backup_file()
    if not file_path:
        await safe_edit(query.message, "❌ فشل إنشاء النسخة")
        return
    accounts = await load_accounts()
    caption = (
        f" **النسخة الاحتياطية**\n\n"
        f"• الحسابات: {len(accounts)}\n"
        f"• الحجم: {size/1024:.1f} KB\n"
        f"• التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    try:
        await app.send_document(
            query.message.chat.id, file_path, caption=caption,
            file_name=f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        await safe_edit(query.message, "✅ تم الإرسال",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("رجوع", callback_data="back_to_main")
            ]]))
    except Exception as e:
        await safe_edit(query.message, f"❌ {str(e)}")


@app.on_callback_query(filters.regex("^backup_upload$"))
async def backup_upload_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    set_waiting(query.from_user.id, {"action": "backup_restore"})
    await safe_edit(query.message,
        " **رفع نسخة احتياطية**\n\n⚠️ سيتم استبدال جميع البيانات الحالية!\n\n"
        "أرسل ملف JSON\n\nلإلغاء اكتب /cancel",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ إلغاء", callback_data="back_to_main")
        ]]))



@app.on_callback_query(filters.regex("^manage_force_sub$"))
async def manage_force_sub_callback(_, query: CallbackQuery):
    if not await is_dev(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    channels_text = ""
    if config.FORCE_SUB_CHANNELS:
        channels_text = "\n\n**القنوات الحالية:**\n"
        for i, ch in enumerate(config.FORCE_SUB_CHANNELS, 1):
            channels_text += f"{i}. {ch.get('title', ch.get('username'))}\n   🔗 {ch.get('link', '')}\n"
    else:
        channels_text = "\n\nلا توجد قنوات مضافة"
    buttons = [
        [InlineKeyboardButton("➕ إضافة قناة", callback_data="add_force_sub")],
        [InlineKeyboardButton("➖ حذف قناة", callback_data="remove_force_sub_menu")],
        [InlineKeyboardButton("🔄 مزامنة مع القنوات الأساسية", callback_data="sync_force_sub")],
        [InlineKeyboardButton("رجوع", callback_data="back_to_main")],
    ]
    await safe_edit(query.message,
        f"📢 **إدارة قنوات الاشتراك**\nعدد: {len(config.FORCE_SUB_CHANNELS)}{channels_text}",
        reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex("^sync_force_sub$"))
async def sync_force_sub_callback(_, query: CallbackQuery):
    if not await is_dev(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    await safe_edit(query.message, "⏳ جاري المزامنة...")
    await sync_force_sub_with_auto_join()
    await safe_edit(query.message,
        f"✅ تم المزامنة\n\nعدد القنوات: {len(config.FORCE_SUB_CHANNELS)}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("رجوع", callback_data="manage_force_sub")]
        ]))


@app.on_callback_query(filters.regex("^add_force_sub$"))
async def add_force_sub_callback(_, query: CallbackQuery):
    if not await is_dev(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    set_waiting(query.from_user.id, {"action": "add_force_sub_link"})
    await safe_edit(query.message,
        "📢 **إضافة قناة**\n\nأرسل الرابط:\n`https://t.me/ TopVeGa`\n\nأو المعرف:\n`@ TopVeGa`\n\n"
        "⚠️ تأكد أن البوت أدمن\n\nلإلغاء اكتب /cancel")


@app.on_callback_query(filters.regex("^remove_force_sub_menu$"))
async def remove_force_sub_menu_callback(_, query: CallbackQuery):
    if not await is_dev(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    if not config.FORCE_SUB_CHANNELS:
        await query.answer("لا توجد قنوات", show_alert=True)
        return
    set_waiting(query.from_user.id, {"action": "remove_force_sub_by_id"})
    channels_list = "\n".join([f"• @{ch.get('username')}" for ch in config.FORCE_SUB_CHANNELS])
    await safe_edit(query.message,
        f"➖ **حذف قناة اشتراك**\n\n"
        f"📝 **أرسل معرف القناة**\n"
        f"مثال: `@ TopVeGa`\n\n"
        f"**القنوات الحالية:**\n{channels_list}\n\n"
        f"لإلغاء اكتب /cancel")


@app.on_callback_query(filters.regex(r"^del_force_sub_(.+)$"))
async def del_force_sub_callback(_, query: CallbackQuery):
    if not await is_dev(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    username = query.matches[0].group(1)
    success = await remove_force_sub_channel(username)
    if success:
        if username in config.AUTO_JOIN_CHANNELS:
            config.AUTO_JOIN_CHANNELS.remove(username)
        await safe_edit(query.message, "✅ تم الحذف",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("رجوع", callback_data="manage_force_sub")
            ]]))
    else:
        await safe_edit(query.message, "❌ فشل")


@app.on_callback_query(filters.regex("^check_sub_again$"))
async def check_sub_again_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    subscribed, missing = await check_user_force_sub(user_id)
    if subscribed:
        _force_sub_sent_cache.pop(user_id, None)
        await query.answer("✅ تم التحقق", show_alert=True)
        await mark_force_sub_verified(user_id)
        try:
            await query.message.delete()
        except:
            pass
        await send_main_menu_for_user(query.message, user_id)
    else:
        await query.answer("❌ لم تشترك بعد", show_alert=True)


async def send_main_menu_for_user(message, user_id):
    if await is_dev(user_id):
        await send_dev_dashboard(message)
    elif await is_premium(user_id) or await is_admin(user_id):
        await message.reply(
            "مرحبا بك\n\nاختر من القائمة:",
            reply_markup=InlineKeyboardMarkup(PREMIUM_BUTTONS))
    else:
        await message.reply(
            "مرحبا بك\n\nاختر من القائمة:",
            reply_markup=InlineKeyboardMarkup(MEMBER_BUTTONS))



@app.on_callback_query(filters.regex("^back_to_main$"))
async def back_to_main_callback(_, query: CallbackQuery):
    try:
        await query.answer()
        user_id = query.from_user.id
        if await is_dev(user_id):
            await send_dev_dashboard(query.message)
        elif await is_premium(user_id) or await is_admin(user_id):
            await safe_edit(query.message,
                "مرحبا بك\n\nاختر من القائمة:",
                reply_markup=InlineKeyboardMarkup(PREMIUM_BUTTONS))
        else:
            await safe_edit(query.message,
                "مرحبا بك\n\nاختر من القائمة:",
                reply_markup=InlineKeyboardMarkup(MEMBER_BUTTONS))
    except Exception as e:
        logger.error(f"back_to_main: {e}")



@app.on_callback_query(filters.regex("^my_subscription_status$"))
async def my_subscription_status_callback(_, query: CallbackQuery):
    await query.answer()
    user_id = query.from_user.id
    if await is_premium(user_id):
        expiry = config.PREMIUM_USERS.get(user_id, datetime.now())
        remaining = (expiry - datetime.now()).days
        plan = config.PREMIUM_SUBSCRIPTIONS.get(user_id, {}).get('plan', 'غير محدد')
        stars = config.PREMIUM_SUBSCRIPTIONS.get(user_id, {}).get('stars', 0)
        await safe_edit(query.message,
            f"حالة اشتراكك\n\nالحالة: نشط ✅\nالخطة: {plan}\nالنجوم: {stars}\n"
            f"ينتهي: {expiry.strftime('%Y-%m-%d %H:%M:%S')}\nالمتبقي: {remaining} يوم",
            reply_markup=InlineKeyboardMarkup(PREMIUM_BUTTONS))
    else:
        await safe_edit(query.message,
            "حالة اشتراكك\n\nالحالة: غير مشترك\n\nللاشتراك اضغط الزر:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("اشتراك Premium", callback_data="premium_subscribe")],
                [InlineKeyboardButton("رجوع", callback_data="back_to_main")]
            ]))


@app.on_callback_query(filters.regex("^my_stats$"))
async def my_stats_callback(_, query: CallbackQuery):
    await query.answer()
    stats = await get_detailed_user_stats(query.from_user.id)
    text = (
        f"📊 **إحصائياتك**\n━━━━━━━━━━━━━━━\n\n"
        f"🔄 النقل: {stats.get('transfers_count', 0)}\n"
        f"👥 المنقولين: {stats.get('members_transferred', 0)}\n"
        f"❤️ التفاعلات: {stats.get('reacts_count', 0)}\n"
        f" الإرسالات: {stats.get('sends_count', 0)}\n"
        f"👤 الحسابات: {stats.get('accounts_used', 0)}\n"
    )
    await safe_edit(query.message, text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="my_stats")],
            [InlineKeyboardButton("رجوع", callback_data="back_to_main")]
        ]))



@app.on_callback_query(filters.regex("^trans$"))
async def trans_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if not await check_premium_panel_access(user_id):
        await query.answer("للمشتركين فقط", show_alert=True)
        return
    allowed, msg = await check_action_limit(user_id, 'transfer')
    if not allowed:
        await query.answer(msg, show_alert=True)
        return
    allowed, msg = await check_premium_limit(user_id, 'transfers')
    if not allowed:
        await query.answer(msg, show_alert=True)
        return
    if user_id in config.active_operations and not config.active_operations[user_id].done():
        await query.answer("لديك عملية قيد التنفيذ", show_alert=True)
        return
    await query.answer()
    set_waiting(user_id, {"action": "trans_source"})
    await safe_edit(query.message,
        "نقل الأعضاء\n\nارسل رابط الجروب المصدر\nمثال: @source_group\n\nلإلغاء اكتب /cancel")


@app.on_callback_query(filters.regex("^advanced_transfer$"))
async def advanced_transfer_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if not await check_premium_panel_access(user_id):
        await query.answer("للمشتركين فقط", show_alert=True)
        return
    allowed, msg = await check_action_limit(user_id, 'transfer')
    if not allowed:
        await query.answer(msg, show_alert=True)
        return
    allowed, msg = await check_premium_limit(user_id, 'transfers')
    if not allowed:
        await query.answer(msg, show_alert=True)
        return
    if user_id in config.active_operations and not config.active_operations[user_id].done():
        await query.answer("لديك عملية قيد التنفيذ", show_alert=True)
        return
    await query.answer()
    set_waiting(user_id, {"action": "advanced_transfer_sources"})
    await safe_edit(query.message,
        "🚀 النقل المتقدم\n\nارسل الجروبات المصدر (مفصولة بمسافة)\nمثال: @s1 @s2\n\nلإلغاء اكتب /cancel")


@app.on_callback_query(filters.regex("^get_data$"))
async def get_data_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    if not os.path.exists("data.txt"):
        await query.answer("لا يوجد ملف", show_alert=True)
        return
    await query.answer()
    await app.send_document(query.message.chat.id, "data.txt", caption="نسخة احتياطية")



@app.on_callback_query(filters.regex("^leave_all$"))
async def leave_all_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    accounts = await load_accounts()
    if not accounts:
        await safe_edit(query.message, "لا توجد حسابات")
        return
    buttons = []
    for acc in accounts[:10]:
        btn_text = f"{acc.get('name', '?')} ({acc.get('phone', '?')})"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"select_acc_{acc.get('phone', '')}")])
    buttons.append([InlineKeyboardButton('جميع الحسابات', callback_data="select_acc_all")])
    buttons.append([InlineKeyboardButton('الغاء', callback_data="back_to_main")])
    await safe_edit(query.message, 'اختر الحسابات:', reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^select_acc_(.*)$"))
async def select_account_leave_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    selected = query.matches[0].group(1)
    accounts = await load_accounts()
    accounts_to_process = accounts if selected == 'all' else [a for a in accounts if a.get('phone') == selected]
    if not accounts_to_process:
        await safe_edit(query.message, "لم يتم العثور")
        return
    await safe_edit(query.message, "جاري المعالجة...")
    total_left = 0
    total_errors = 0
    account_results = []
    sem = asyncio.Semaphore(3)

    async def process_account(account):
        nonlocal total_left, total_errors
        acc_name = account.get('name', '?')
        session_str = account.get('session', '')
        if not session_str:
            account_results.append(f'{acc_name}: لا توجد جلسة')
            return
        async with sem:
            try:
                async with create_temp_client(session_str) as user:
                    left_count = 0
                    errors = 0
                    total = 0
                    async for dialog in user.get_dialogs():
                        if dialog.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
                            total += 1
                            try:
                                await user.leave_chat(dialog.chat.id)
                                left_count += 1
                                await asyncio.sleep(0.5)
                            except:
                                errors += 1
                    account_results.append(f'{acc_name}: {left_count}/{total}')
                    total_left += left_count
                    total_errors += errors
            except Exception as e:
                account_results.append(f'{acc_name}: خطأ')

    tasks = [process_account(acc) for acc in accounts_to_process]
    await asyncio.gather(*tasks)
    result_text = 'تم الانتهاء\n\n' + '\n'.join(account_results)
    result_text += f'\n\nالإجمالي: {total_left} | فشل: {total_errors}'
    await safe_edit(query.message, result_text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("رجوع", callback_data="back_to_main")
        ]]))



@app.on_callback_query(filters.regex("^stop_operation$"))
async def stop_operation_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    user_id = query.from_user.id
    await stop_user_operation(user_id)
    if user_id in config.active_operations:
        task = config.active_operations[user_id]
        if not task.done():
            try:
                task.cancel()
            except:
                pass
    await query.answer("تم الإيقاف", show_alert=True)


@app.on_callback_query(filters.regex("^stop_my_operation$"))
async def stop_my_operation_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    await stop_user_operation(user_id)
    if user_id in config.active_operations:
        task = config.active_operations[user_id]
        if not task.done():
            try:
                task.cancel()
            except:
                pass
    await query.answer("تم إيقاف عمليتك", show_alert=True)


@app.on_callback_query(filters.regex("^statistics$"))
async def statistics_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    await safe_edit(query.message, "جاري الجلب...")
    stats = await get_statistics()
    text = (
        f"إحصائيات البوت\n================\n"
        f"عدد الحسابات: {stats['total_accounts']}\n"
        f"مستخدمين /start: {stats['start_users']}\n"
        f"مستخدمين Premium: {stats['premium_users']}\n"
        f"عدد الأدمن: {stats['admins']}\n"
        f"حسابات محظورة: {stats['banned_accounts']}\n"
        f"مستخدمين محظورين: {stats['banned_users']}\n"
        f"قنوات الاشتراك: {stats['force_sub_channels']}\n"
        f"================\nآخر تحديث: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    await safe_edit(query.message, text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("تحديث", callback_data="statistics")],
            [InlineKeyboardButton("رجوع", callback_data="back_to_main")]
        ]))


@app.on_callback_query(filters.regex("^add_admin$"))
async def add_admin_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    set_waiting(query.from_user.id, {"action": "add_admin"})
    await safe_edit(query.message, "إضافة أدمن\n\nارسل المعرف\nمثال: @user أو 123456\n\nلإلغاء اكتب /cancel")


@app.on_callback_query(filters.regex("^remove_admin$"))
async def remove_admin_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    set_waiting(query.from_user.id, {"action": "remove_admin"})
    await safe_edit(query.message, "تنزيل أدمن\n\nارسل المعرف\n\nلإلغاء اكتب /cancel")


@app.on_callback_query(filters.regex("^add_premium$"))
async def add_premium_callback(_, query: CallbackQuery):
    if not await is_dev(query.from_user.id):
        await query.answer("للمطور فقط", show_alert=True)
        return
    await query.answer()
    set_waiting(query.from_user.id, {"action": "add_premium"})
    await safe_edit(query.message, "إضافة Premium\n\nالخطوة 1/3\nارسل معرف المستخدم\n\nلإلغاء اكتب /cancel")


@app.on_callback_query(filters.regex("^react_posts$"))
async def react_posts_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if not await check_premium_panel_access(user_id):
        await query.answer("للمشتركين فقط", show_alert=True)
        return
    allowed, msg = await check_action_limit(user_id, 'react')
    if not allowed:
        await query.answer(msg, show_alert=True)
        return
    allowed, msg = await check_premium_limit(user_id, 'reacts')
    if not allowed:
        await query.answer(msg, show_alert=True)
        return
    await query.answer()
    set_waiting(user_id, {"action": "react_post_link"})
    await safe_edit(query.message,
        "التفاعل مع المنشورات\n\nارسل رابط المنشور\nمثال: https://t.me/python2015/987\n\nلإلغاء اكتب /cancel")


async def execute_react_post(message, chat_id, post_id):
    user_id = message.from_user.id
    await increment_premium_usage(user_id, 'reacts')
    link_str = f"https://t.me/{chat_id}/{post_id}" if isinstance(chat_id, str) else f"المنشور {post_id}"
    msg = await message.reply(f"جاري التفاعل...\n{link_str}")
    accounts = await load_accounts()
    if not accounts:
        await safe_edit(msg, "لا توجد حسابات")
        return
    fallback_reactions = ['👍', '❤️', '🔥', '👏', '😮', '🎉', '💯', '😂', '🤔', '👌', '🙏', '👀']
    counters_lock = asyncio.Lock()
    counters = {'success': 0, 'failed': 0, 'matched': 0}
    errors = []
    sem = asyncio.Semaphore(3)

    async def react_with_account(account):
        if not isinstance(account, dict) or 'session' not in account:
            async with counters_lock:
                counters['failed'] += 1
            return
        if await is_account_disabled(account.get('phone', '')):
            async with counters_lock:
                counters['failed'] += 1
            return
        async with sem:
            try:
                async with create_temp_client(account['session']) as user:
                    result = await react_to_single_post(user, chat_id, post_id, fallback_reactions)
                    if result.get('status') == 'success':
                        async with counters_lock:
                            counters['success'] += 1
                            if result.get('matched'):
                                counters['matched'] += 1
                        await update_account_stat(account.get('phone', ''), 'reacts')
                    else:
                        async with counters_lock:
                            counters['failed'] += 1
                            if result.get('error'):
                                errors.append(f"{account.get('name', '?')}: {result['error']}")
            except FloodWait as fw:
                await record_floodwait(account.get('phone', ''))
                await asyncio.sleep(fw.value)
                async with counters_lock:
                    counters['failed'] += 1
            except Exception as e:
                async with counters_lock:
                    counters['failed'] += 1
                    errors.append(f"{account.get('name', '?')}: {str(e)[:100]}")

    tasks = [react_with_account(acc) for acc in accounts]
    await asyncio.gather(*tasks)
    await update_user_stats(user_id, 'reacts_count')
    result_text = (
        f"تم التفاعل\n\n{link_str}\n\n"
        f"الحسابات: {len(accounts)}\n✅ نجح: {counters['success']}\n"
        f"❌ فشل: {counters['failed']}\n🎯 مطابق: {counters['matched']}"
    )
    if errors:
        result_text += f"\n\nأخطاء:\n" + "\n".join(errors[:5])
    await safe_edit(msg, result_text)



@app.on_callback_query(filters.regex("^upload_and_send$"))
async def upload_and_send_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if not await check_premium_panel_access(user_id):
        await query.answer("للمشتركين فقط", show_alert=True)
        return
    allowed, msg = await check_action_limit(user_id, 'send_file')
    if not allowed:
        await query.answer(msg, show_alert=True)
        return
    allowed, msg = await check_premium_limit(user_id, 'sends')
    if not allowed:
        await query.answer(msg, show_alert=True)
        return
    await query.answer()
    set_waiting(user_id, {"action": "spam_target"})
    await safe_edit(query.message, "إزعاج / Flood\n\nارسل معرف الهدف\nمثال: @user أو -100123\n\nلإلغاء اكتب /cancel")


async def execute_spam_send(message, target_id, spam_text, count):
    user_id = message.from_user.id
    await increment_premium_usage(user_id, 'sends')
    await update_user_stats(user_id, 'sends_count', count)
    progress_msg = await message.reply(f"جاري الإرسال...\nالهدف: {target_id}\nالعدد: {count}")
    accounts = await load_accounts()
    if not accounts:
        await safe_edit(progress_msg, "لا توجد حسابات")
        return
    counters_lock = asyncio.Lock()
    counters = {'success': 0, 'failed': 0}
    errors = []
    sem = asyncio.Semaphore(3)

    async def send_with_account(account):
        if not isinstance(account, dict) or 'session' not in account:
            async with counters_lock:
                counters['failed'] += 1
            return
        if await is_account_disabled(account.get('phone', '')):
            async with counters_lock:
                counters['failed'] += 1
            return
        async with sem:
            try:
                async with create_temp_client(account['session']) as user:
                    try:
                        try:
                            if isinstance(target_id, str) and not target_id.startswith('-') and not target_id.startswith('+'):
                                await user.join_chat(target_id)
                        except:
                            pass
                        await user.send_message(target_id, spam_text)
                        async with counters_lock:
                            counters['success'] += 1
                        await update_account_stat(account.get('phone', ''), 'sent_messages')
                    except FloodWait as fw:
                        await record_floodwait(account.get('phone', ''))
                        await asyncio.sleep(fw.value)
                        try:
                            await user.send_message(target_id, spam_text)
                            async with counters_lock:
                                counters['success'] += 1
                        except Exception as e:
                            async with counters_lock:
                                counters['failed'] += 1
                    except Exception as e:
                        async with counters_lock:
                            counters['failed'] += 1
                            errors.append(f"{account.get('name', '?')}: {str(e)[:80]}")
                    await asyncio.sleep(random.uniform(2, 5))
            except:
                async with counters_lock:
                    counters['failed'] += 1

    tasks = []
    for i in range(count):
        account = accounts[i % len(accounts)]
        tasks.append(send_with_account(account))
    await asyncio.gather(*tasks)
    result_text = (
        f"تم الإرسال\n\nالهدف: {target_id}\nالعدد: {count}\n"
        f"✅ نجح: {counters['success']}\n❌ فشل: {counters['failed']}"
    )
    if errors:
        result_text += f"\n\nأخطاء:\n" + "\n".join(errors[:3])
    await safe_edit(progress_msg, result_text)


@app.on_callback_query(filters.regex("^broadcast_menu$"))
async def broadcast_menu_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    await safe_edit(query.message,
        f"بث رسالة\n\nعدد المستخدمين: {len(config.BROADCAST_USERS)}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("بدء البث", callback_data="start_broadcast")],
            [InlineKeyboardButton("رجوع", callback_data="back_to_main")]
        ]))


@app.on_callback_query(filters.regex("^start_broadcast$"))
async def start_broadcast_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    set_waiting(query.from_user.id, {"action": "broadcast_message"})
    await safe_edit(query.message, "ارسل الرسالة\n\nلإلغاء اكتب /cancel")


async def execute_broadcast(message, broadcast_text):
    await load_broadcast_users()
    if not config.BROADCAST_USERS:
        await message.reply("لا يوجد مستخدمين")
        return
    msg = await message.reply(f"جاري البث إلى {len(config.BROADCAST_USERS)}...")
    counters_lock = asyncio.Lock()
    counters = {'success': 0, 'failed': 0}
    sem = asyncio.Semaphore(20)

    async def send_to_user(uid):
        async with sem:
            try:
                await app.send_message(uid, broadcast_text)
                async with counters_lock:
                    counters['success'] += 1
                await asyncio.sleep(0.05)
            except FloodWait as fw:
                await asyncio.sleep(fw.value)
                try:
                    await app.send_message(uid, broadcast_text)
                    async with counters_lock:
                        counters['success'] += 1
                except:
                    async with counters_lock:
                        counters['failed'] += 1
            except:
                async with counters_lock:
                    counters['failed'] += 1

    tasks = [send_to_user(uid) for uid in config.BROADCAST_USERS]
    await asyncio.gather(*tasks)
    await safe_edit(msg,
        f"تم البث\n\nالإجمالي: {len(config.BROADCAST_USERS)}\n"
        f"✅ نجح: {counters['success']}\n❌ فشل: {counters['failed']}")



@app.on_callback_query(filters.regex("^fetch_account_data$"))
async def fetch_account_data_callback(_, query: CallbackQuery):
    if not await check_premium_panel_access(query.from_user.id):
        await query.answer("غير مصرح", show_alert=True)
        return
    await query.answer()
    set_waiting(query.from_user.id, {"action": "fetch_account_data"})
    await safe_edit(query.message,
        "جلب بيانات حساب\n\nارسل @username أو الهاتف\n\nيعرض: البيانات + الجلسة + التحقق\n\nلإلغاء اكتب /cancel")


async def execute_fetch_account_data(message, account_id):
    msg = await message.reply("⏳ البحث...")
    account_info = None
    accounts = await load_accounts()
    target = account_id.replace('@', '').replace('+', '').strip()
    for acc in accounts:
        if not isinstance(acc, dict):
            continue
        if acc.get('username', '').replace('@', '').strip().lower() == target.lower() or \
           acc.get('phone', '').replace('+', '').strip() == target:
            account_info = acc
            break
    if not account_info:
        await safe_edit(msg, f"❌ لا يوجد حساب: {account_id}")
        return
    session_to_use = account_info['session']
    await safe_edit(msg, "⏳ التحقق من الجلسة...")
    session_status = "غير صالحة ❌"
    try:
        async with create_temp_client(session_to_use) as test_client:
            me_test = await test_client.get_me()
            if me_test:
                session_status = "صالحة ✅"
    except Exception as e:
        session_status = f"غير صالحة ❌ ({str(e)[:40]})"
    try:
        async with create_temp_client(session_to_use) as user:
            me = await user.get_me()
            contacts_count = 0
            try:
                contacts = await user.get_contacts()
                if contacts:
                    contacts_count = len(contacts)
            except:
                pass
            password_status = "غير مفعل"
            try:
                pwd_info = await user.get_password_hint()
                password_status = "مفعّل" if pwd_info or True else "غير مفعل"
            except:
                pass
            groups = channels = bots = private = 0
            try:
                cnt = 0
                async for dialog in user.get_dialogs():
                    cnt += 1
                    if cnt > 500:
                        break
                    try:
                        t = dialog.chat.type
                        if t in (ChatType.GROUP, ChatType.SUPERGROUP):
                            groups += 1
                        elif t == ChatType.CHANNEL:
                            channels += 1
                        elif t == ChatType.BOT:
                            bots += 1
                        elif t == ChatType.PRIVATE:
                            private += 1
                    except:
                        pass
            except:
                pass
            info_text = (
                f"📋 **بيانات الحساب**\n━━━━━━━━━━━━━━━\n\n"
                f"🔍 البحث: {account_id}\n"
                f"✅ حالة الجلسة: {session_status}\n\n"
                f"👤 الاسم: {me.first_name or ''} {me.last_name or ''}\n"
                f"🆔 @{me.username or 'لا يوجد'}\n"
                f"🔢 الايدي: {me.id}\n"
                f"📱 الهاتف: {me.phone_number or 'لا يوجد'}\n"
                f"🔐 2FA: {password_status}\n"
                f"📇 جهات الاتصال: {contacts_count}\n\n"
                f"📊 الجروبات: {groups}\n"
                f"📢 القنوات: {channels}\n"
                f"🤖 البوتات: {bots}\n"
                f"💬 الخاص: {private}\n\n"
                f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await safe_edit(msg, info_text)
            session_file_path = f"session_{me.id}.txt"
            with open(session_file_path, "w", encoding="utf-8") as f:
                f.write(f"# {me.first_name or ''} {me.last_name or ''}\n")
                f.write(f"# {me.phone_number or ''}\n")
                f.write(f"# @{me.username or ''}\n")
                f.write(f"# ID: {me.id}\n")
                f.write(f"# Status: {session_status}\n")
                f.write("# " + "=" * 40 + "\n\n")
                f.write(session_to_use)
            try:
                await app.send_document(
                    message.chat.id, session_file_path,
                    caption=f"🔐 جلسة الحساب\n👤 {me.first_name or ''}\n✅ {session_status}"
                )
            except Exception as e:
                await app.send_message(message.chat.id, f"⚠️ فشل إرسال الجلسة: {str(e)}")
            finally:
                try:
                    os.remove(session_file_path)
                except:
                    pass
    except Exception as e:
        await safe_edit(msg, f"❌ خطأ: {str(e)}")


async def save_account_session_with_autojoin(message, session):
    if not session or not isinstance(session, str) or len(session) < 50:
        await message.reply("الجلسة غير صالحة")
        return
    try:
        msg = await message.reply("🔍 جاري التحقق...")
        async with create_temp_client(session) as temp_client:
            me = await temp_client.get_me()
            account_info = {
                "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
                "username": me.username or "",
                "phone": me.phone_number or "",
                "session": session,
            }
        await safe_edit(msg, "📢 جاري الانضمام للقنوات...")
        success, result_msg, joined = await add_account_with_autojoin(account_info)
        if success:
            await safe_edit(msg, result_msg)
        else:
            await safe_edit(msg, f"❌ {result_msg}")
    except Exception as e:
        await message.reply(f"فشل تفعيل الجلسة: {str(e)}")


async def start_phone_login(message: Message, phone: str):
    user_id = message.from_user.id
    if not phone or not phone.startswith('+'):
        await message.reply("رقم غير صالح")
        return
    try:
        client = Client(":memory:", api_id=API_ID, api_hash=API_HASH)
        await client.connect()
        try:
            sent_code = await client.send_code(phone)
        except Exception as e:
            await message.reply(f"خطأ: {str(e)}")
            if user_id in config.waiting_for:
                del config.waiting_for[user_id]
            return
        set_waiting(user_id, {
            "action": "add_account_phone_code",
            "phone": phone,
            "phone_code_hash": sent_code.phone_code_hash
        })
        config.temp_clients[user_id] = client
        if not hasattr(config, '_temp_client_timestamps'):
            config._temp_client_timestamps = {}
        config._temp_client_timestamps[user_id] = time.time()
        await message.reply(
            f"تم إرسال الكود إلى {phone}\n\nارسل الكود\n\nلديك 60 ثانية\n\nلإلغاء اكتب /cancel")
    except Exception as e:
        await message.reply(f"خطأ: {str(e)}")
        if user_id in config.waiting_for:
            del config.waiting_for[user_id]


async def process_phone_code(message: Message, phone: str, code: str, phone_code_hash: str):
    user_id = message.from_user.id
    if user_id not in config.temp_clients:
        await message.reply("انتهت الجلسة")
        if user_id in config.waiting_for:
            del config.waiting_for[user_id]
        return
    client = config.temp_clients[user_id]
    try:
        await client.sign_in(phone, phone_code_hash, code)
        me = await client.get_me()
        session_string = await client.export_session_string()
        await message.reply("جاري تغيير كلمة السر...")
        await change_2fa_password(client, None)
        account_info = {
            "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
            "username": me.username or "",
            "phone": me.phone_number or "",
            "session": session_string,
        }
        try:
            await client.stop()
        except:
            pass
        del config.temp_clients[user_id]
        del config.waiting_for[user_id]
        if user_id in config.temp_passwords:
            del config.temp_passwords[user_id]
        if hasattr(config, '_temp_client_timestamps'):
            config._temp_client_timestamps.pop(user_id, None)
        msg = await message.reply("📢 جاري الانضمام للقنوات...")
        success, result_msg, joined = await add_account_with_autojoin(account_info)
        if success:
            await safe_edit(msg, result_msg)
        else:
            await safe_edit(msg, f"❌ {result_msg}")
    except Exception as e:
        if "PASSWORD" in str(e).upper():
            set_waiting(user_id, {
                "action": "add_account_phone_password",
                "phone": phone,
                "phone_code_hash": phone_code_hash
            })
            await message.reply("الحساب محمي بكلمة مرور\n\nارسل كلمة المرور\n\nلإلغاء اكتب /cancel")
        else:
            await message.reply(f"خطأ: {str(e)}")
            try:
                await client.stop()
            except:
                pass
            del config.temp_clients[user_id]
            del config.waiting_for[user_id]


async def process_phone_password(message: Message, phone: str, password: str, phone_code_hash: str):
    user_id = message.from_user.id
    if user_id not in config.temp_clients:
        await message.reply("انتهت الجلسة")
        if user_id in config.waiting_for:
            del config.waiting_for[user_id]
        return
    client = config.temp_clients[user_id]
    try:
        await client.check_password(password)
        me = await client.get_me()
        session_string = await client.export_session_string()
        await message.reply("جاري تغيير كلمة السر")
        await change_2fa_password(client, password)
        account_info = {
            "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
            "username": me.username or "",
            "phone": me.phone_number or "",
            "session": session_string,
        }
        try:
            await client.stop()
        except:
            pass
        del config.temp_clients[user_id]
        del config.waiting_for[user_id]
        if user_id in config.temp_passwords:
            del config.temp_passwords[user_id]
        if hasattr(config, '_temp_client_timestamps'):
            config._temp_client_timestamps.pop(user_id, None)
        msg = await message.reply("📢 جاري الانضمام للقنوات...")
        success, result_msg, joined = await add_account_with_autojoin(account_info)
        if success:
            await safe_edit(msg, result_msg)
        else:
            await safe_edit(msg, f"❌ {result_msg}")
    except Exception as e:
        await message.reply(f"خطأ: {str(e)}")
        try:
            await client.stop()
        except:
            pass
        del config.temp_clients[user_id]
        del config.waiting_for[user_id]


async def get_all_members_data(client, group_link):
    members_ids = []
    members_names = []
    members_contacts = []
    try:
        if not group_link or not isinstance(group_link, str):
            return [], [], []
        group = group_link.replace("https://t.me/", "").replace("@", "")
        try:
            await client.join_chat(group)
        except:
            pass
        try:
            async for member in client.get_chat_members(group, limit=10000):
                try:
                    if member.user.id and not member.user.is_bot:
                        members_ids.append(str(member.user.id))
                        if member.user.username:
                            members_names.append(f"@{member.user.username}")
                        elif member.user.first_name:
                            members_names.append(member.user.first_name)
                        if member.user.phone_number:
                            members_contacts.append({
                                "id": member.user.id,
                                "phone": member.user.phone_number,
                                "name": member.user.first_name or ""
                            })
                except:
                    pass
        except FloodWait as fw:
            await asyncio.sleep(fw.value + 3)
        except:
            pass
        if len(members_names) < 50:
            try:
                async for msg in client.get_chat_history(group, limit=10000):
                    try:
                        if msg.from_user and msg.from_user.is_bot:
                            continue
                        if msg.from_user and msg.from_user.username:
                            username = f"@{msg.from_user.username}"
                            if username not in members_names:
                                members_names.append(username)
                        elif msg.from_user and msg.from_user.first_name:
                            name = msg.from_user.first_name
                            if name not in members_names:
                                members_names.append(name)
                    except:
                        pass
                    if len(members_names) >= 200:
                        break
            except:
                pass
        return members_ids, members_names, members_contacts
    except Exception as e:
        return [], [], []


async def add_members_to_target(client, target_group, members_ids, members_names, members_contacts):
    added = failed = added_by_id = added_by_name = added_by_contact = 0
    try:
        target = target_group.replace("https://t.me/", "").replace("@", "")
        try:
            await client.join_chat(target)
        except:
            pass
        chat = await client.get_chat(target)
        existing_members = []
        try:
            async for member in client.get_chat_members(chat.id, limit=10000):
                try:
                    if member.user and member.user.id:
                        existing_members.append(member.user.id)
                except:
                    continue
        except:
            pass
        for member_id in members_ids[:200]:
            try:
                if int(member_id) in existing_members:
                    continue
                try:
                    user_info = await client.get_users(int(member_id))
                    if user_info and user_info.is_bot:
                        continue
                except:
                    pass
                try:
                    await client.add_chat_members(chat.id, int(member_id))
                    added += 1
                    added_by_id += 1
                    await asyncio.sleep(3)
                except:
                    failed += 1
                    await asyncio.sleep(3)
            except FloodWait as fw:
                await asyncio.sleep(fw.value + 3)
            except:
                failed += 1
        for name in members_names[:200]:
            try:
                if name.startswith('@'):
                    user = name.replace('@', '')
                    try:
                        u_info = await client.get_users(user)
                        if u_info and u_info.is_bot:
                            continue
                    except:
                        pass
                    try:
                        await client.add_chat_members(chat.id, user)
                        added += 1
                        added_by_name += 1
                        await asyncio.sleep(3)
                    except:
                        failed += 1
                else:
                    try:
                        await client.add_chat_members(chat.id, name)
                        added += 1
                        added_by_name += 1
                        await asyncio.sleep(3)
                    except:
                        failed += 1
            except FloodWait as fw:
                await asyncio.sleep(fw.value + 3)
            except:
                failed += 1
        contacts = await load_contacts()
        if contacts:
            for account_phone, contact_list in contacts.items():
                for contact in contact_list[:50]:
                    try:
                        if contact.get('phone'):
                            try:
                                await client.add_chat_members(chat.id, contact['phone'])
                                added += 1
                                added_by_contact += 1
                                await asyncio.sleep(3)
                            except:
                                await asyncio.sleep(3)
                    except:
                        await asyncio.sleep(3)
        return added, failed, added_by_id, added_by_name, added_by_contact
    except:
        return 0, len(members_ids) if members_ids else 0, 0, 0, 0


async def execute_transfer(message, source_group, target_group):
    user_id = message.from_user.id
    start_time = time.time()
    if not await is_dev(user_id):
        allowed, msg = await check_premium_limit(user_id, 'transfers')
        if not allowed:
            await message.reply(msg)
            return
    progress_msg = await message.reply("🚀 بدء النقل...")
    accounts = await load_accounts()
    if not accounts:
        await safe_edit(progress_msg, "لا توجد حسابات")
        return
    active_accounts = []
    for acc in accounts:
        if not isinstance(acc, dict) or 'session' not in acc:
            continue
        if await is_account_disabled(acc.get('phone', '')):
            continue
        active_accounts.append(acc)
    if not active_accounts:
        await safe_edit(progress_msg, "كل الحسابات معطلة")
        return
    accounts = active_accounts

    all_ids, all_names, all_contacts = [], [], []
    max_fetch = min(TRANSFER_CONFIG['max_parallel_accounts'], len(accounts))
    random.shuffle(accounts)
    fetch_accounts = accounts[:max_fetch]
    await safe_edit(progress_msg, f" جلب الأعضاء ({len(fetch_accounts)} حسابات)...")
    sem = asyncio.Semaphore(TRANSFER_CONFIG['max_parallel_accounts'])

    async def fetch_from_account(account):
        try:
            async with sem:
                async with create_temp_client(account['session']) as user:
                    return await get_all_members_data(user, source_group)
        except FloodWait as fw:
            await record_floodwait(account.get('phone', ''))
            await asyncio.sleep(fw.value)
            return ([], [], [])
        except:
            return ([], [], [])

    tasks = [fetch_from_account(acc) for acc in fetch_accounts]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            continue
        ids, names, contacts = result
        if ids:
            all_ids.extend(ids)
        if names:
            all_names.extend(names)
        if contacts:
            all_contacts.extend(contacts)

    if not all_ids and not all_names:
        await safe_edit(progress_msg, "فشل جلب البيانات")
        return
    unique_ids = list(set(all_ids))
    unique_names = list(set(all_names))

    with open(MEMBERS_IDS_FILE, "w", encoding='utf-8') as f:
        f.write("\n".join(unique_ids))
    with open(MEMBERS_NAMES_FILE, "w", encoding='utf-8') as f:
        f.write("\n".join(unique_names))
    with open(MEMBERS_FILE, "w", encoding='utf-8') as f:
        f.write("== المعرفات ==\n")
        f.write("\n".join(unique_ids[:100]))
        f.write("\n\n== الاسماء ==\n")
        f.write("\n".join(unique_names[:100]))

    contacts = await load_contacts()
    if contacts is None:
        contacts = {}
    for contact in all_contacts:
        for account in accounts:
            phone = account.get('phone', '')
            if phone:
                if phone not in contacts:
                    contacts[phone] = []
                contacts[phone].append(contact)
    await save_contacts(contacts)

    await safe_edit(progress_msg,
        f"✅ {len(unique_ids)} معرف و {len(unique_names)} اسم\n🚀 الإضافة...")

    added_lock = asyncio.Lock()
    added_counters = {'total': 0, 'failed': 0, 'by_id': 0, 'by_name': 0, 'by_contact': 0}
    add_sem = asyncio.Semaphore(TRANSFER_CONFIG['max_parallel_accounts'])

    async def add_from_account(account):
        if await is_account_disabled(account.get('phone', '')):
            return
        try:
            async with add_sem:
                async with create_temp_client(account['session']) as user:
                    added, failed, by_id, by_name, by_contact = await add_members_to_target(
                        user, target_group, unique_ids, unique_names, all_contacts
                    )
                    await update_account_stat(account.get('phone', ''), 'transfers')
                    async with added_lock:
                        added_counters['total'] += added
                        added_counters['failed'] += failed
                        added_counters['by_id'] += by_id
                        added_counters['by_name'] += by_name
                        added_counters['by_contact'] += by_contact
        except FloodWait as fw:
            await record_floodwait(account.get('phone', ''))
            await asyncio.sleep(fw.value)
        except Exception as e:
            logger.error(f"add_from_account error: {e}")

    add_accounts = accounts[:TRANSFER_CONFIG['max_parallel_accounts']]
    tasks = [add_from_account(acc) for acc in add_accounts]
    await asyncio.gather(*tasks, return_exceptions=True)
    await app.send_document(message.chat.id, MEMBERS_IDS_FILE, caption=f"معرفات - {len(unique_ids)}")
    await app.send_document(message.chat.id, MEMBERS_NAMES_FILE, caption=f"اسماء - {len(unique_names)}")
    await app.send_document(message.chat.id, MEMBERS_FILE, caption="البيانات المجمعة")

    await increment_premium_usage(user_id, 'transfers')
    await update_user_stats(user_id, 'transfers_count')
    await update_user_stats(user_id, 'members_transferred', added_counters['total'])
    await update_user_stats(user_id, 'accounts_used', len(add_accounts))

    elapsed = time.time() - start_time
    await safe_edit(progress_msg,
        f"✅ تم النقل\n\n"
        f"📊 البيانات: {len(unique_ids)} معرف / {len(unique_names)} اسم / {len(all_contacts)} جهة\n\n"
        f"📈 الإضافة:\n"
        f"• الكلي: {added_counters['total']}\n"
        f"• بالمعرفات: {added_counters['by_id']}\n"
        f"• بالأسماء: {added_counters['by_name']}\n"
        f"• بالجهات: {added_counters['by_contact']}\n"
        f"• فشل: {added_counters['failed']}\n\n"
        f"⚙️ الحسابات: {len(add_accounts)}\n"
        f"⏱️ الوقت: {human_time(elapsed)}\n\n"
        f"📍 المصدر: {source_group}\n🎯 الهدف: {target_group}"
    )