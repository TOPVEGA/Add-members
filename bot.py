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



import asyncio
import commands
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

from config import app, DEV_IDS
from database import (
    load_premium, load_admins,
    load_banned_users, load_subscriptions,
    load_account_stats, load_broadcast_users,
    check_expiring_subscriptions,
    auto_backup,
    load_expired_notified,
    cleanup_waiting_for,
    load_accounts,
    load_force_sub_channels,
    sync_force_sub_with_auto_join,
    daily_contacts_collector,
    notify_developer_periodic,
)


logging.basicConfig(
    format="[%(asctime)s - %(levelname)s] - %(name)s: %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
    handlers=[
        RotatingFileHandler("log.txt", maxBytes=10485760, backupCount=5, encoding="utf-8"),
        logging.StreamHandler(),
    ],
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("pytgcalls").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


async def load_all_data():
    logger.info("بدء تحميل البيانات...")
    loaders = [
        ("Accounts", load_accounts),
        ("Premium", load_premium),
        ("Admins", load_admins),
        ("Banned Users", load_banned_users),
        ("Subscriptions", load_subscriptions),
        ("Account Stats", load_account_stats),
        ("Broadcast Users", load_broadcast_users),
        ("Expired Notified", load_expired_notified),
        ("Force Sub Channels", load_force_sub_channels),
    ]
    loaded = 0
    for name, func in loaders:
        try:
            await func()
            loaded += 1
            logger.info("✅ تم تحميل %s", name)
        except Exception as e:
            logger.error("❌ فشل تحميل %s: %s", name, e)
    logger.info("📦 تم تحميل %s/%s من البيانات", loaded, len(loaders))


async def notify_devs(me):
    text = (
        f"<b>• تم تشغيل البوت بنجاح\n\n"
        f"• الاسم: {me.first_name or ''}\n"
        f"• اليوزر: @{me.username or 'لا يوجد'}\n"
        f"• الايدي: {me.id}\n"
        f"• الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</b>"
    )
    for dev_id in DEV_IDS:
        try:
            await app.send_message(dev_id, text)
        except Exception as e:
            logger.error("فشل إخطار المطور %s: %s", dev_id, e)


async def start_background_tasks():
    asyncio.create_task(check_expiring_subscriptions())
    asyncio.create_task(auto_backup())
    asyncio.create_task(cleanup_waiting_for())
    asyncio.create_task(daily_contacts_collector())     
    asyncio.create_task(notify_developer_periodic())    
    logger.info(
        "✅ تم بدء المهام الخلفية:\n"
        "   • فحص الاشتراكات\n"
        "   • النسخ الاحتياطي\n"
        "   • تنظيف waiting_for\n"
        "   • 📇 جمع جهات الاتصال اليومية (كل 24 ساعة)\n"
        "   • 🔔 إشعار المطور الدوري (كل 12 ساعة)"
    )


def main():
    logger.info("=" * 50)
    logger.info("🤖 البوت يعمل...")
    logger.info("👨‍💻 المطور: @TopVeGa")
    logger.info("=" * 50)
    try:
        with app:
            me = app.get_me()
            logger.info("✅ تم الاتصال بـ @%s (ID: %s)", me.username, me.id)
            try:
                app.loop.run_until_complete(sync_force_sub_with_auto_join())
                logger.info("✅ تمت مزامنة قنوات الاشتراك الإجباري")
            except Exception as e:
                logger.error("❌ فشل مزامنة قنوات الاشتراك: %s", e)

            try:
                app.loop.run_until_complete(notify_devs(me))
            except Exception as e:
                logger.error("فشل إرسال رسالة التشغيل: %s", e)

            try:
                app.loop.create_task(start_background_tasks())
            except Exception as e:
                logger.error("فشل بدء المهام الخلفية: %s", e)

            from pyrogram import idle
            idle()
            logger.info("تم إيقاف البوت")
    except KeyboardInterrupt:
        logger.warning("تم إيقاف البوت يدوياً (Ctrl+C)")
    except Exception as e:
        logger.critical("خطأ فادح: %s", e, exc_info=True)
        raise


if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(load_all_data())
    except Exception as e:
        print(f"خطأ في تحميل البيانات: {e}")
    main()