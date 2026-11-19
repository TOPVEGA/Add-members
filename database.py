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
import json
import re
import time
import uuid
import asyncio
import shutil
import sqlite3
import logging
from functools import wraps
from datetime import datetime, timedelta
from pyrogram import Client
from pyrogram.errors import FloodWait, MessageNotModified

from config import (
    ACCOUNTS_FILE, CONTACTS_FILE, ACCOUNT_STATS_FILE, BROADCAST_FILE,
    API_ID, API_HASH, DEV_VEGA,
    PREMIUM_DAILY_LIMITS, USER_STATS_FILE, ERROR_LOG_FILE,
    MEMBERS_FILE, MEMBERS_IDS_FILE, MEMBERS_NAMES_FILE,
    DEFAULT_2FA_PASSWORD, ENABLE_AUTO_2FA_CHANGE,
    BACKUP_FILE,
)
import config

logger = logging.getLogger(__name__)

DB_FILE = "bot_data.db"
_db_lock = asyncio.Lock()


def _get_conn():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_db_sync():
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                username TEXT,
                phone TEXT,
                session TEXT UNIQUE NOT NULL,
                category TEXT DEFAULT 'active',
                added_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_phone TEXT,
                contact_id TEXT,
                contact_phone TEXT,
                contact_name TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sent_contacts (
                contact_id TEXT PRIMARY KEY,
                contact_phone TEXT,
                contact_name TEXT,
                sent_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS premium_users (
                user_id INTEGER PRIMARY KEY,
                expiry TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER PRIMARY KEY,
                expiry TEXT NOT NULL,
                stars INTEGER DEFAULT 0,
                plan TEXT DEFAULT 'غير محدد'
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER,
                added_date TEXT,
                username TEXT,
                first_name TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS banned_users (
                user_id INTEGER PRIMARY KEY
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS broadcast_users (
                user_id INTEGER PRIMARY KEY
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS account_stats (
                phone TEXT PRIMARY KEY,
                added_members INTEGER DEFAULT 0,
                sent_messages INTEGER DEFAULT 0,
                reacts INTEGER DEFAULT 0,
                transfers INTEGER DEFAULT 0,
                last_used TEXT,
                status TEXT DEFAULT 'active',
                category TEXT DEFAULT 'active'
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS expired_notified (
                user_id INTEGER PRIMARY KEY
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id INTEGER PRIMARY KEY,
                transfers_count INTEGER DEFAULT 0,
                reacts_count INTEGER DEFAULT 0,
                sends_count INTEGER DEFAULT 0,
                members_transferred INTEGER DEFAULT 0,
                accounts_used INTEGER DEFAULT 0,
                last_activity TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS error_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TEXT,
                user_id INTEGER,
                action TEXT,
                error TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS start_users (
                user_id INTEGER PRIMARY KEY
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS subscription_refunds (
                user_id INTEGER PRIMARY KEY,
                last_refund TEXT,
                refund_count INTEGER DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS floodwait_tracker (
                phone TEXT PRIMARY KEY,
                count INTEGER DEFAULT 0,
                last_wait TEXT,
                disabled_until TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS force_sub_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                username TEXT UNIQUE,
                title TEXT,
                link TEXT,
                added_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_force_sub_verified (
                user_id INTEGER PRIMARY KEY,
                verified_at TEXT
            )
        """)

        # الفهارس
        cur.execute("CREATE INDEX IF NOT EXISTS idx_premium_expiry ON premium_users(expiry)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_expiry ON subscriptions(expiry)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_accounts_phone ON accounts(phone)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_accounts_category ON accounts(category)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_banned_user ON banned_users(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_error_time ON error_logs(time)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sent_contacts ON sent_contacts(contact_id)")

        conn.commit()
        logger.info("تم تهيئة قاعدة البيانات بنجاح")
    finally:
        conn.close()


def _run_sync(func, *args, **kwargs):
    return asyncio.to_thread(func, *args, **kwargs)


_init_db_sync()


def create_temp_client(session_string):
    if not session_string or not isinstance(session_string, str):
        raise ValueError("session_string غير صالح")
    return Client(
        f"temp_{uuid.uuid4().hex[:12]}",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_string,
        in_memory=True,
        no_updates=True,
        lang_code="ar"
    )


def rate_limit(seconds=3):
    def decorator(func):
        @wraps(func)
        async def wrapper(client, message, *args, **kwargs):
            try:
                user_id = message.from_user.id
            except:
                return await func(client, message, *args, **kwargs)
            if user_id in DEV_VEGA:
                return await func(client, message, *args, **kwargs)
            now = time.time()
            if user_id in config.USER_COOLDOWNS:
                diff = now - config.USER_COOLDOWNS[user_id]
                if diff < seconds:
                    await message.reply(f"⏳ انتظر {int(seconds - diff) + 1} ثانية قبل المحاولة مجدداً")
                    return
            config.USER_COOLDOWNS[user_id] = now
            return await func(client, message, *args, **kwargs)
        return wrapper
    return decorator


async def safe_edit(message, text, reply_markup=None):
    if not message:
        return
    try:
        await message.edit(text, reply_markup=reply_markup)
    except MessageNotModified:
        pass
    except FloodWait as fw:
        await asyncio.sleep(fw.value)
        try:
            await message.edit(text, reply_markup=reply_markup)
        except:
            pass
    except Exception as e:
        logger.error(f"خطأ في تعديل الرسالة: {e}")


async def check_premium_panel_access(user_id):
    if not user_id:
        return False
    if user_id in DEV_VEGA:
        return True
    if await is_premium(user_id):
        return True
    if await is_admin(user_id):
        return True
    return False


async def get_members_with_filter(client, group_link, filters=None):
    if not filters:
        filters = {'active': True, 'new': False, 'banned': False}
    members_data = {}
    try:
        if not group_link or not isinstance(group_link, str):
            return {}
        group = group_link.replace("https://t.me/", "").replace("@", "")
        try:
            await client.join_chat(group)
        except:
            pass
        async for member in client.get_chat_members(group, limit=10000):
            try:
                user_id = member.user.id
                if not user_id:
                    continue
                username = member.user.username or ""
                first_name = member.user.first_name or ""
                last_name = member.user.last_name or ""
                phone = member.user.phone_number or ""
                joined_date = member.joined_date or datetime.now()
                if filters.get('banned', False):
                    if member.user.is_bot or member.user.is_deleted:
                        continue
                if filters.get('active', False):
                    if not username and not phone:
                        continue
                if filters.get('new', False):
                    if joined_date < datetime.now() - timedelta(days=7):
                        continue
                if member.user.is_bot:
                    continue
                members_data[user_id] = {
                    'id': user_id,
                    'username': username,
                    'first_name': first_name,
                    'last_name': last_name,
                    'phone': phone,
                    'joined_date': joined_date.isoformat()
                }
            except:
                continue
        return members_data
    except Exception as e:
        logger.error(f"get_members_with_filter error: {e}")
        return {}


async def filter_bots_batch(client, member_ids, batch_size=100):
    if not member_ids or not isinstance(member_ids, list):
        return []
    non_bots = []
    for i in range(0, len(member_ids), batch_size):
        batch = member_ids[i:i+batch_size]
        try:
            users = await client.get_users(batch)
            if not isinstance(users, list):
                users = [users]
            for u in users:
                if u and not u.is_bot:
                    non_bots.append(u.id)
        except:
            for uid in batch:
                try:
                    u = await client.get_users(uid)
                    if u and not u.is_bot:
                        non_bots.append(uid)
                except:
                    pass
        await asyncio.sleep(0.5)
    return non_bots


async def transfer_members_advanced(message, source_groups, target_groups, options=None):
    if not options:
        options = {
            'max_members': 1000,
            'filter_active': True,
            'filter_new': False,
            'filter_banned': False,
            'delay_between': 3,
            'use_all_accounts': True,
            'parallel_accounts': 3,
        }
    user_id = message.from_user.id
    stop_event = get_stop_event(user_id)
    stop_event.clear()
    progress_msg = await message.reply("بدء عملية نقل الأعضاء المتطورة...")
    accounts = await load_accounts_cached()
    if not accounts:
        await safe_edit(progress_msg, "لا توجد حسابات مسجلة")
        return
    accounts_to_use = accounts if options['use_all_accounts'] else accounts[:options['parallel_accounts']]
    accounts_to_use = accounts_to_use[:options['parallel_accounts']]
    all_members = {}
    await safe_edit(progress_msg, f"جلب الأعضاء من {len(source_groups)} جروب...")
    for source_group in source_groups:
        if stop_event.is_set():
            await safe_edit(progress_msg, "تم إيقاف العملية")
            return
        for account in accounts_to_use[:2]:
            if stop_event.is_set():
                await safe_edit(progress_msg, "تم إيقاف العملية")
                return
            try:
                async with create_temp_client(account['session']) as user:
                    members = await get_members_with_filter(user, source_group, {
                        'active': options['filter_active'],
                        'new': options['filter_new'],
                        'banned': options['filter_banned']
                    })
                    for member_id, data in members.items():
                        if member_id not in all_members:
                            all_members[member_id] = data
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"خطأ في جلب الأعضاء: {e}")
                continue
        await safe_edit(progress_msg, f"تم جلب {len(all_members)} عضو حتى الآن...")
    if options['max_members']:
        all_members = dict(list(all_members.items())[:options['max_members']])
    await safe_edit(progress_msg, f"تم جلب {len(all_members)} عضو بنجاح")
    total_added = 0
    total_failed = 0
    total_bots_skipped = 0
    for target_group in target_groups:
        if stop_event.is_set():
            await safe_edit(progress_msg, "تم إيقاف العملية")
            return
        await safe_edit(progress_msg, f"إضافة الأعضاء إلى {target_group}...")
        member_list = list(all_members.items())
        chunk_size = len(member_list) // len(accounts_to_use) + 1 if accounts_to_use else 0
        tasks = []
        for idx, account in enumerate(accounts_to_use):
            start_idx = idx * chunk_size
            end_idx = min((idx + 1) * chunk_size, len(member_list))
            chunk = member_list[start_idx:end_idx]
            if chunk:
                task = add_members_parallel(account, target_group, chunk, options['delay_between'])
                tasks.append(task)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, dict):
                total_added += result.get('added', 0)
                total_failed += result.get('failed', 0)
    await save_members_data(all_members)
    await update_user_stats(user_id, 'transfers_count')
    await update_user_stats(user_id, 'members_transferred', total_added)
    await safe_edit(progress_msg,
        f"تمت عملية النقل بنجاح!\n\n"
        f"- إجمالي الأعضاء المجلوبين: {len(all_members)}\n"
        f"- تمت الإضافة: {total_added}\n"
        f"- فشل: {total_failed}\n"
        f"- بوتات تم تخطيها: {total_bots_skipped}\n"
        f"- المصادر: {len(source_groups)}\n"
        f"- الأهداف: {len(target_groups)}\n"
        f"- الحسابات: {len(accounts_to_use)}"
    )


async def add_members_parallel(account, target_group, members_chunk, delay=3):
    added = 0
    failed = 0
    bots_skipped = 0
    if not account or not isinstance(account, dict) or 'session' not in account:
        return {'added': 0, 'failed': len(members_chunk) if members_chunk else 0, 'bots_skipped': 0}
    try:
        async with create_temp_client(account['session']) as user:
            target = target_group.replace("https://t.me/", "").replace("@", "")
            try:
                await user.join_chat(target)
            except:
                pass
            chat = await user.get_chat(target)
            for member_id, member_data in members_chunk:
                added_success = False
                for attempt in range(3):
                    try:
                        try:
                            user_info = await user.get_users(int(member_id))
                            if user_info and user_info.is_bot:
                                bots_skipped += 1
                                added_success = True
                                break
                        except:
                            pass
                        try:
                            await user.add_chat_members(chat.id, int(member_id))
                            added += 1
                            await update_account_stat(account.get('phone', ''), 'added_members')
                            added_success = True
                            break
                        except Exception as inner_e:
                            if member_data.get('username'):
                                try:
                                    u_info = await user.get_users(member_data['username'])
                                    if u_info and u_info.is_bot:
                                        bots_skipped += 1
                                        added_success = True
                                        break
                                except:
                                    pass
                                await user.add_chat_members(chat.id, member_data['username'])
                                added += 1
                                await update_account_stat(account.get('phone', ''), 'added_members')
                                added_success = True
                                break
                            else:
                                raise inner_e
                    except FloodWait as fw:
                        await asyncio.sleep(fw.value + 3)
                        continue
                    except Exception:
                        if attempt == 2:
                            failed += 1
                        else:
                            await asyncio.sleep(2)
                            continue
                if not added_success and attempt == 2:
                    failed += 1
                await asyncio.sleep(delay)
    except Exception as e:
        logger.error(f"add_members_parallel error: {e}")
        failed = len(members_chunk) if members_chunk else 0
    return {'added': added, 'failed': failed, 'bots_skipped': bots_skipped}


async def save_members_data(members):
    if not members or not isinstance(members, dict):
        return
    ids = []
    names = []
    contacts = []
    for member_id, data in members.items():
        ids.append(str(member_id))
        if data.get('username'):
            names.append(f"@{data['username']}")
        elif data.get('first_name'):
            names.append(data['first_name'])
        if data.get('phone'):
            contacts.append({
                'id': member_id,
                'phone': data['phone'],
                'name': data.get('first_name', '')
            })
    try:
        with open(MEMBERS_IDS_FILE, "w", encoding='utf-8') as f:
            f.write("\n".join(ids))
        with open(MEMBERS_NAMES_FILE, "w", encoding='utf-8') as f:
            f.write("\n".join(names))
        with open(MEMBERS_FILE, "w", encoding='utf-8') as f:
            f.write("== المعرفات ==\n")
            f.write("\n".join(ids[:100]))
            f.write("\n\n== الاسماء ==\n")
            f.write("\n".join(names[:100]))
    except Exception as e:
        logger.error(f"save_members_data error: {e}")


def _load_accounts_sync():
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT name, username, phone, session, category, added_at FROM accounts")
        rows = cur.fetchall()
        return [
            {
                "name": row["name"] or "",
                "username": row["username"] or "",
                "phone": row["phone"] or "",
                "session": row["session"],
                "category": row["category"] or "active",
                "added_at": row["added_at"] or datetime.now().isoformat(),
            }
            for row in rows
        ]
    finally:
        conn.close()


def _save_accounts_sync(accounts):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        cur.execute("DELETE FROM accounts")
        seen_sessions = set()
        inserted = 0
        skipped = 0
        for acc in accounts:
            session = acc.get("session", "")
            if not session or session in seen_sessions:
                skipped += 1
                continue
            seen_sessions.add(session)
            cur.execute(
                "INSERT OR IGNORE INTO accounts (name, username, phone, session, category, added_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    acc.get("name", ""),
                    acc.get("username", ""),
                    acc.get("phone", ""),
                    session,
                    acc.get("category", "active"),
                    acc.get("added_at", datetime.now().isoformat()),
                ),
            )
            inserted += 1
        conn.commit()
        return {"success": True, "inserted": inserted, "skipped": skipped}
    except Exception as e:
        conn.rollback()
        logger.error(f"فشل حفظ accounts: {e}")
        return {"success": False, "inserted": 0, "skipped": 0, "error": str(e)}
    finally:
        conn.close()


async def load_accounts():
    try:
        async with _db_lock:
            return await _run_sync(_load_accounts_sync)
    except Exception as e:
        logger.error(f"خطأ في تحميل accounts: {e}")
        return []


async def save_accounts(accounts):
    if not isinstance(accounts, list):
        return False
    valid_accounts = []
    for acc in accounts:
        if not isinstance(acc, dict):
            continue
        if 'session' not in acc or not isinstance(acc['session'], str):
            continue
        valid_accounts.append(acc)
    try:
        async with _db_lock:
            result = await _run_sync(_save_accounts_sync, valid_accounts)
            if result.get("success"):
                invalidate_accounts_cache()
            return result.get("success", False)
    except Exception as e:
        logger.error(f"فشل حفظ accounts: {e}")
        return False


async def save_accounts_detailed(accounts):
    if not isinstance(accounts, list):
        return {"success": False, "inserted": 0, "skipped": 0}
    valid_accounts = [a for a in accounts if isinstance(a, dict) and 'session' in a]
    try:
        async with _db_lock:
            result = await _run_sync(_save_accounts_sync, valid_accounts)
            if result.get("success"):
                invalidate_accounts_cache()
            return result
    except Exception as e:
        return {"success": False, "inserted": 0, "skipped": 0, "error": str(e)}


async def add_account_with_autojoin(account_info):
    try:
        joined = 0
        failed_channels = []
        try:
            async with create_temp_client(account_info['session']) as user:
                for channel in config.AUTO_JOIN_CHANNELS:
                    try:
                        await user.join_chat(channel)
                        joined += 1
                        await asyncio.sleep(1.5)
                    except FloodWait as fw:
                        await asyncio.sleep(fw.value + 2)
                        try:
                            await user.join_chat(channel)
                            joined += 1
                        except:
                            failed_channels.append(channel)
                    except Exception as e:
                        err = str(e).lower()
                        if "already" in err or "participant" in err:
                            joined += 1
                        else:
                            failed_channels.append(channel)
        except Exception as e:
            logger.error(f"auto_join error: {e}")

        accounts = await load_accounts()
        if accounts is None:
            accounts = []

        if len(accounts) >= config.MAX_TOTAL_ACCOUNTS:
            return False, f"تم الوصول للحد الأقصى ({config.MAX_TOTAL_ACCOUNTS})", joined
        if any(a.get('session') == account_info['session'] for a in accounts):
            return False, "هذه الجلسة مضافة مسبقاً", joined
        if account_info.get('phone') and any(a.get('phone') == account_info['phone'] for a in accounts):
            return False, "هذا الحساب مضاف مسبقاً (نفس الرقم)", joined

        account_info['category'] = 'active'
        account_info['added_at'] = datetime.now().isoformat()
        accounts.append(account_info)

        result = await save_accounts_detailed(accounts)
        if result.get("success"):
            msg = f"✅ تمت إضافة الحساب بنجاح\n"
            msg += f"👤 {account_info['name']}\n"
            msg += f"📱 {account_info['phone']}\n"
            msg += f"🆔 @{account_info['username'] or 'لا يوجد'}\n"
            msg += f"📢 انضم لـ {joined} قناة"
            if failed_channels:
                msg += f"\n⚠️ فشل: {', '.join(failed_channels[:3])}"
            return True, msg, joined
        else:
            return False, "فشل حفظ الحساب", joined
    except Exception as e:
        logger.error(f"add_account_with_autojoin: {e}")
        return False, f"خطأ: {str(e)}", 0



def _load_contacts_sync():
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT account_phone, contact_id, contact_phone, contact_name FROM contacts")
        rows = cur.fetchall()
        result = {}
        for row in rows:
            phone = row["account_phone"]
            if phone not in result:
                result[phone] = []
            result[phone].append({
                "id": row["contact_id"],
                "phone": row["contact_phone"],
                "name": row["contact_name"] or "",
            })
        return result
    finally:
        conn.close()


def _save_contacts_sync(contacts):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        cur.execute("DELETE FROM contacts")
        for account_phone, contact_list in contacts.items():
            for contact in contact_list:
                cur.execute(
                    "INSERT INTO contacts (account_phone, contact_id, contact_phone, contact_name) VALUES (?, ?, ?, ?)",
                    (account_phone, str(contact.get("id", "")), contact.get("phone", ""), contact.get("name", "")),
                )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        return False
    finally:
        conn.close()


async def load_contacts():
    try:
        async with _db_lock:
            return await _run_sync(_load_contacts_sync)
    except:
        return {}


async def save_contacts(contacts):
    if not isinstance(contacts, dict):
        return False
    try:
        async with _db_lock:
            return await _run_sync(_save_contacts_sync, contacts)
    except:
        return False



def _load_sent_contacts_sync():
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT contact_id, contact_phone, contact_name FROM sent_contacts")
        return {row["contact_id"]: {"phone": row["contact_phone"], "name": row["contact_name"]} for row in cur.fetchall()}
    finally:
        conn.close()


def _add_sent_contacts_batch_sync(contacts_list):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        added = 0
        skipped = 0
        for c in contacts_list:
            cid = str(c.get("id", c.get("contact_id", "")))
            if not cid:
                skipped += 1
                continue
            try:
                cur.execute(
                    "INSERT OR IGNORE INTO sent_contacts (contact_id, contact_phone, contact_name, sent_at) VALUES (?, ?, ?, ?)",
                    (cid, c.get("phone", c.get("contact_phone", "")), c.get("name", c.get("contact_name", "")), datetime.now().isoformat()),
                )
                if cur.rowcount > 0:
                    added += 1
                else:
                    skipped += 1
            except:
                skipped += 1
        conn.commit()
        return {"added": added, "skipped": skipped}
    except:
        conn.rollback()
        return {"added": 0, "skipped": len(contacts_list)}
    finally:
        conn.close()


async def load_sent_contacts():
    try:
        async with _db_lock:
            return await _run_sync(_load_sent_contacts_sync)
    except:
        return {}


async def add_sent_contacts_batch(contacts_list):
    if not contacts_list:
        return {"added": 0, "skipped": 0}
    try:
        async with _db_lock:
            return await _run_sync(_add_sent_contacts_batch_sync, contacts_list)
    except:
        return {"added": 0, "skipped": 0}


def _get_sent_contact_ids_sync():
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT contact_id FROM sent_contacts")
        return {row["contact_id"] for row in cur.fetchall()}
    finally:
        conn.close()


async def get_sent_contact_ids():
    try:
        async with _db_lock:
            return await _run_sync(_get_sent_contact_ids_sync)
    except:
        return set()



def _load_account_stats_sync():
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM account_stats")
        return {row["phone"]: dict(row) for row in cur.fetchall()}
    finally:
        conn.close()


def _save_account_stats_sync(stats):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        cur.execute("DELETE FROM account_stats")
        for phone, data in stats.items():
            cur.execute(
                "INSERT INTO account_stats (phone, added_members, sent_messages, reacts, transfers, last_used, status, category) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (phone, data.get("added_members", 0), data.get("sent_messages", 0),
                 data.get("reacts", 0), data.get("transfers", 0), data.get("last_used"),
                 data.get("status", "active"), data.get("category", "active")),
            )
        conn.commit()
        return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()


async def load_account_stats():
    try:
        async with _db_lock:
            data = await _run_sync(_load_account_stats_sync)
        config.ACCOUNT_STATS.clear()
        if data and isinstance(data, dict):
            config.ACCOUNT_STATS.update(data)
    except:
        pass


async def save_account_stats():
    try:
        async with _db_lock:
            return await _run_sync(_save_account_stats_sync, dict(config.ACCOUNT_STATS))
    except:
        return False


async def update_account_stat(phone, key, increment=1):
    if not phone or not isinstance(phone, str):
        return
    if phone not in config.ACCOUNT_STATS:
        config.ACCOUNT_STATS[phone] = {
            'added_members': 0, 'sent_messages': 0, 'reacts': 0, 'transfers': 0,
            'last_used': None, 'status': 'active', 'category': 'active',
        }
    try:
        if key in ('status', 'category'):
            config.ACCOUNT_STATS[phone][key] = increment
        else:
            config.ACCOUNT_STATS[phone][key] = config.ACCOUNT_STATS[phone].get(key, 0) + increment
    except (TypeError, ValueError):
        config.ACCOUNT_STATS[phone][key] = increment
    config.ACCOUNT_STATS[phone]['last_used'] = datetime.now().isoformat()
    await save_account_stats()


def classify_account(account, stats):
    phone = account.get('phone', '')
    if not phone or phone not in stats:
        return 'active'
    s = stats[phone]
    if s.get('status') == 'banned':
        return 'banned'
    disabled_until = s.get('disabled_until')
    if disabled_until:
        try:
            if datetime.now() < datetime.fromisoformat(disabled_until):
                return 'disabled'
        except:
            pass
    if s.get('transfers', 0) >= config.ACCOUNT_PREMIUM_MIN_TRANSFERS and s.get('added_members', 0) > 100:
        return 'premium'
    last_used = s.get('last_used')
    if last_used:
        try:
            last_dt = datetime.fromisoformat(last_used)
            if (datetime.now() - last_dt).total_seconds() / 3600 > config.ACCOUNT_IDLE_HOURS:
                return 'idle'
        except:
            pass
    return 'active'


async def refresh_account_categories():
    accounts = await load_accounts()
    stats = config.ACCOUNT_STATS
    updated = 0
    for acc in accounts:
        new_cat = classify_account(acc, stats)
        if acc.get('category') != new_cat:
            acc['category'] = new_cat
            updated += 1
    if updated > 0:
        await save_accounts(accounts)
    return updated



def _load_broadcast_users_sync():
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM broadcast_users")
        return [row["user_id"] for row in cur.fetchall()]
    finally:
        conn.close()


def _save_broadcast_users_sync(users):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        cur.execute("DELETE FROM broadcast_users")
        for uid in users:
            cur.execute("INSERT OR IGNORE INTO broadcast_users (user_id) VALUES (?)", (uid,))
        conn.commit()
        return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()


async def load_broadcast_users():
    try:
        async with _db_lock:
            data = await _run_sync(_load_broadcast_users_sync)
        config.BROADCAST_USERS.clear()
        if data and isinstance(data, list):
            config.BROADCAST_USERS.extend(data)
    except:
        pass


async def save_broadcast_users():
    try:
        async with _db_lock:
            return await _run_sync(_save_broadcast_users_sync, list(config.BROADCAST_USERS))
    except:
        return False



def _parse_datetime(v):
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v)
        except:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(v, fmt)
            except:
                continue
    if isinstance(v, (int, float)):
        try:
            return datetime.fromtimestamp(v)
        except:
            pass
    return None


def _load_premium_sync():
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id, expiry FROM premium_users")
        return {row["user_id"]: row["expiry"] for row in cur.fetchall()}
    finally:
        conn.close()


def _load_subscriptions_sync():
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id, expiry, stars, plan FROM subscriptions")
        return {
            row["user_id"]: {"expiry": row["expiry"], "stars": row["stars"], "plan": row["plan"]}
            for row in cur.fetchall()
        }
    finally:
        conn.close()


async def load_premium():
    try:
        async with _db_lock:
            premium_data = await _run_sync(_load_premium_sync)
            subs_data = await _run_sync(_load_subscriptions_sync)
        config.PREMIUM_USERS.clear()
        if premium_data and isinstance(premium_data, dict):
            for k, v in premium_data.items():
                try:
                    expiry = _parse_datetime(v)
                    if expiry:
                        config.PREMIUM_USERS[int(k)] = expiry
                except:
                    continue
        config.PREMIUM_SUBSCRIPTIONS.clear()
        if subs_data and isinstance(subs_data, dict):
            for k, v in subs_data.items():
                try:
                    if not isinstance(v, dict) or 'expiry' not in v:
                        continue
                    expiry = _parse_datetime(v['expiry'])
                    if not expiry:
                        continue
                    config.PREMIUM_SUBSCRIPTIONS[int(k)] = {
                        'expiry': expiry,
                        'stars': v.get('stars', 0),
                        'plan': v.get('plan', 'غير محدد')
                    }
                except:
                    continue
    except Exception as e:
        logger.error(f"خطأ في تحميل premium: {e}")


def _save_premium_sync(data):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        cur.execute("DELETE FROM premium_users")
        for uid, expiry in data.items():
            cur.execute("INSERT INTO premium_users (user_id, expiry) VALUES (?, ?)", (uid, expiry))
        conn.commit()
        return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()


def _save_subscriptions_sync(data):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        cur.execute("DELETE FROM subscriptions")
        for uid, v in data.items():
            cur.execute(
                "INSERT INTO subscriptions (user_id, expiry, stars, plan) VALUES (?, ?, ?, ?)",
                (uid, v["expiry"], v.get("stars", 0), v.get("plan", "غير محدد")),
            )
        conn.commit()
        return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()


async def save_premium():
    try:
        data = {}
        for k, v in config.PREMIUM_USERS.items():
            if isinstance(v, datetime):
                data[k] = v.isoformat()
            elif isinstance(v, str):
                data[k] = v
        async with _db_lock:
            return await _run_sync(_save_premium_sync, data)
    except:
        return False


async def save_subscriptions():
    try:
        data = {}
        for k, v in config.PREMIUM_SUBSCRIPTIONS.items():
            if not isinstance(v, dict) or 'expiry' not in v:
                continue
            expiry = v['expiry']
            if isinstance(expiry, datetime):
                expiry_str = expiry.isoformat()
            elif isinstance(expiry, str):
                expiry_str = expiry
            else:
                continue
            data[k] = {'expiry': expiry_str, 'stars': v.get('stars', 0), 'plan': v.get('plan', 'غير محدد')}
        async with _db_lock:
            return await _run_sync(_save_subscriptions_sync, data)
    except:
        return False


async def load_subscriptions():
    await load_premium()



def _load_expired_notified_sync():
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM expired_notified")
        return [row["user_id"] for row in cur.fetchall()]
    finally:
        conn.close()


def _save_expired_notified_sync(users):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        cur.execute("DELETE FROM expired_notified")
        for uid in users:
            cur.execute("INSERT OR IGNORE INTO expired_notified (user_id) VALUES (?)", (uid,))
        conn.commit()
        return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()


async def load_expired_notified():
    try:
        async with _db_lock:
            data = await _run_sync(_load_expired_notified_sync)
        config.EXPIRED_NOTIFIED_USERS.clear()
        if data and isinstance(data, list):
            for u in data:
                try:
                    config.EXPIRED_NOTIFIED_USERS.add(int(u))
                except:
                    continue
    except:
        pass


async def save_expired_notified():
    try:
        data = list(config.EXPIRED_NOTIFIED_USERS)
        async with _db_lock:
            return await _run_sync(_save_expired_notified_sync, data)
    except:
        return False


async def should_notify_expired(user_id):
    if not user_id:
        return False
    if user_id in config.EXPIRED_NOTIFIED_USERS:
        return False
    config.EXPIRED_NOTIFIED_USERS.add(user_id)
    await save_expired_notified()
    return True


async def reset_expired_notification(user_id):
    if user_id in config.EXPIRED_NOTIFIED_USERS:
        config.EXPIRED_NOTIFIED_USERS.discard(user_id)
        await save_expired_notified()



def _load_admins_sync():
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id, added_by, added_date, username, first_name FROM admins")
        return {
            row["user_id"]: {
                "added_by": row["added_by"], "added_date": row["added_date"],
                "username": row["username"] or "", "first_name": row["first_name"] or "",
            } for row in cur.fetchall()
        }
    finally:
        conn.close()


def _save_admins_sync(data):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        cur.execute("DELETE FROM admins")
        for uid, v in data.items():
            cur.execute(
                "INSERT INTO admins (user_id, added_by, added_date, username, first_name) VALUES (?, ?, ?, ?, ?)",
                (uid, v.get("added_by"), v.get("added_date"), v.get("username", ""), v.get("first_name", "")),
            )
        conn.commit()
        return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()


async def load_admins():
    try:
        async with _db_lock:
            data = await _run_sync(_load_admins_sync)
        config.ADMINS.clear()
        if data and isinstance(data, dict):
            for k, v in data.items():
                try:
                    config.ADMINS[int(k)] = v
                except:
                    continue
    except:
        pass


async def save_admins():
    try:
        data = {str(k): v for k, v in config.ADMINS.items()}
        async with _db_lock:
            return await _run_sync(_save_admins_sync, data)
    except:
        return False



def _load_banned_users_sync():
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM banned_users")
        return [row["user_id"] for row in cur.fetchall()]
    finally:
        conn.close()


def _save_banned_users_sync(data):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        cur.execute("DELETE FROM banned_users")
        for uid in data:
            cur.execute("INSERT OR IGNORE INTO banned_users (user_id) VALUES (?)", (uid,))
        conn.commit()
        return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()


async def load_banned_users():
    try:
        async with _db_lock:
            data = await _run_sync(_load_banned_users_sync)
        config.BANNED_USERS.clear()
        if data and isinstance(data, list):
            config.BANNED_USERS.extend(data)
    except:
        pass


async def save_banned_users():
    try:
        async with _db_lock:
            return await _run_sync(_save_banned_users_sync, list(config.BANNED_USERS))
    except:
        return False



async def is_premium(user_id):
    if not user_id:
        return False
    if user_id in DEV_VEGA:
        return True
    if user_id in config.PREMIUM_USERS:
        expiry = config.PREMIUM_USERS[user_id]
        if isinstance(expiry, str):
            expiry = _parse_datetime(expiry)
            if expiry:
                config.PREMIUM_USERS[user_id] = expiry
        if expiry and datetime.now() < expiry:
            return True
        else:
            async with config.premium_lock:
                if user_id in config.PREMIUM_USERS:
                    del config.PREMIUM_USERS[user_id]
                if user_id in config.PREMIUM_SUBSCRIPTIONS:
                    del config.PREMIUM_SUBSCRIPTIONS[user_id]
                await save_premium()
                await save_subscriptions()
            return False
    try:
        async with config.premium_lock:
            await load_premium()
            if user_id in config.PREMIUM_USERS:
                expiry = config.PREMIUM_USERS[user_id]
                if expiry and datetime.now() < expiry:
                    return True
                else:
                    del config.PREMIUM_USERS[user_id]
                    if user_id in config.PREMIUM_SUBSCRIPTIONS:
                        del config.PREMIUM_SUBSCRIPTIONS[user_id]
                    await save_premium()
                    await save_subscriptions()
    except:
        pass
    return False


async def is_admin(user_id):
    if not user_id:
        return False
    if user_id in DEV_VEGA:
        return True
    return user_id in config.ADMINS


async def is_banned(user_id):
    if not user_id:
        return False
    return user_id in config.BANNED_USERS


async def is_dev(user_id):
    if not user_id:
        return False
    return user_id in DEV_VEGA



async def check_premium_limit(user_id, action):
    if user_id in DEV_VEGA:
        return True, None
    today = datetime.now().strftime("%Y-%m-%d")
    if user_id not in config.PREMIUM_DAILY_USAGE:
        config.PREMIUM_DAILY_USAGE[user_id] = {'date': today, 'usage': {}}
    if config.PREMIUM_DAILY_USAGE[user_id]['date'] != today:
        config.PREMIUM_DAILY_USAGE[user_id] = {'date': today, 'usage': {}}
    used = config.PREMIUM_DAILY_USAGE[user_id]['usage'].get(action, 0)
    limit = PREMIUM_DAILY_LIMITS.get(action, 999)
    if used >= limit:
        return False, f"تجاوزت الحد اليومي ({limit}) لهذا الإجراء. حاول غداً"
    return True, None


async def increment_premium_usage(user_id, action):
    if user_id in DEV_VEGA:
        return
    today = datetime.now().strftime("%Y-%m-%d")
    if user_id not in config.PREMIUM_DAILY_USAGE:
        config.PREMIUM_DAILY_USAGE[user_id] = {'date': today, 'usage': {}}
    if config.PREMIUM_DAILY_USAGE[user_id]['date'] != today:
        config.PREMIUM_DAILY_USAGE[user_id] = {'date': today, 'usage': {}}
    config.PREMIUM_DAILY_USAGE[user_id]['usage'][action] = config.PREMIUM_DAILY_USAGE[user_id]['usage'].get(action, 0) + 1



async def validate_session(session_str):
    if not session_str or not isinstance(session_str, str) or len(session_str) < 50:
        return "invalid"
    try:
        async with create_temp_client(session_str) as temp_client:
            me = await temp_client.get_me()
            return "valid" if me else "invalid"
    except:
        return "invalid"


async def change_2fa_password(client, current_password=None, new_password=None):
    if not client:
        return False, "Client غير صالح"
    if new_password is None:
        new_password = DEFAULT_2FA_PASSWORD
    if not ENABLE_AUTO_2FA_CHANGE:
        return False, "تغيير كلمة المرور معطّل"
    try:
        try:
            await client.enable_cloud_password(password=new_password, hint=f"2FA ({new_password})")
            return True, f"تم تفعيل 2FA بكلمة {new_password}"
        except Exception as e:
            error_msg = str(e)
            if "already" in error_msg.lower() or "password" in error_msg.lower():
                if current_password:
                    try:
                        await client.change_cloud_password(
                            current_password=current_password, new_password=new_password,
                            new_hint=f"2FA ({new_password})"
                        )
                        return True, f"تم تغيير كلمة السر إلى {new_password}"
                    except:
                        try:
                            await client.remove_cloud_password()
                            await client.enable_cloud_password(password=new_password, hint=f"2FA ({new_password})")
                            return True, f"تم إعادة تفعيل 2FA"
                        except:
                            return False, "فشل تغيير كلمة السر"
                else:
                    try:
                        await client.remove_cloud_password()
                        await client.enable_cloud_password(password=new_password, hint=f"2FA ({new_password})")
                        return True, f"تم تغيير كلمة السر إلى {new_password}"
                    except:
                        return False, "الحساب مفعل بخطوتين ولا يمكن التغيير بدون القديمة"
            else:
                return False, f"فشل: {error_msg}"
    except Exception as e:
        return False, f"فشل: {str(e)}"



async def handle_file_forward(client, target_id, file_path, count=1, accounts=None):
    if not target_id:
        return {'total': count, 'success': 0, 'failed': count, 'details': []}
    if not accounts:
        accounts = await load_accounts()
        accounts = accounts[:3]
    results = []
    success_count = 0
    fail_count = 0
    if not accounts or not os.path.exists(file_path):
        return {'total': count, 'success': 0, 'failed': count, 'details': []}
    for i in range(count):
        account = accounts[i % len(accounts)]
        if not isinstance(account, dict) or 'session' not in account:
            fail_count += 1
            continue
        try:
            async with create_temp_client(account['session']) as user:
                try:
                    if file_path.endswith(('.mp4', '.mkv', '.avi')):
                        await user.send_video(target_id, file_path)
                    elif file_path.endswith(('.mp3', '.wav', '.m4a')):
                        await user.send_audio(target_id, file_path)
                    elif file_path.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                        await user.send_photo(target_id, file_path)
                    else:
                        await user.send_document(target_id, file_path)
                    success_count += 1
                    results.append({'account': account.get('name', 'Unknown'), 'status': 'success', 'try': i+1})
                    await update_account_stat(account.get('phone', ''), 'sent_messages')
                except Exception as e:
                    fail_count += 1
                    results.append({'account': account.get('name', 'Unknown'), 'status': 'failed', 'error': str(e), 'try': i+1})
            await asyncio.sleep(2)
        except Exception as e:
            fail_count += 1
            results.append({'account': account.get('name', 'Unknown'), 'status': 'error', 'error': str(e), 'try': i+1})
    return {'total': count, 'success': success_count, 'failed': fail_count, 'details': results}



def _load_start_users_count_sync():
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM start_users")
        return cur.fetchone()["cnt"]
    finally:
        conn.close()


async def get_statistics():
    accounts = await load_accounts()
    try:
        async with _db_lock:
            start_users = await _run_sync(_load_start_users_count_sync)
    except:
        start_users = 0
    banned_accounts = []
    for account in accounts[:10]:
        if not isinstance(account, dict) or 'session' not in account:
            continue
        status = await validate_session(account['session'])
        if status == "invalid":
            banned_accounts.append(account)
    stats = {
        'total_accounts': len(accounts) if accounts else 0,
        'start_users': start_users,
        'premium_users': len(config.PREMIUM_USERS) if config.PREMIUM_USERS else 0,
        'admins': len(config.ADMINS) if config.ADMINS else 0,
        'banned_accounts': len(banned_accounts) if banned_accounts else 0,
        'banned_users': len(config.BANNED_USERS) if config.BANNED_USERS else 0,
        'force_sub_channels': len(config.AUTO_JOIN_CHANNELS),
    }
    return stats


def _get_dev_daily_stats_sync():
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM start_users")
        total_users = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM accounts")
        accounts_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(DISTINCT account_phone) FROM contacts")
        contacts_accounts = cur.fetchone()[0] or 0
        cur.execute("SELECT COUNT(*) FROM force_sub_channels")
        channels_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM subscriptions")
        subs_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM admins")
        admins_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM banned_users")
        banned_users_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM accounts WHERE session IS NULL OR length(session) < 50")
        corrupt_accounts = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM sent_contacts")
        sent_contacts_count = cur.fetchone()[0]
        return {
            'total_users': total_users,
            'accounts_count': accounts_count,
            'contacts_accounts': contacts_accounts,
            'channels_count': channels_count,
            'subs_count': subs_count,
            'admins_count': admins_count,
            'banned_users_count': banned_users_count,
            'corrupt_accounts': corrupt_accounts,
            'sent_contacts_count': sent_contacts_count,
        }
    finally:
        conn.close()


async def get_dev_daily_stats():
    try:
        async with _db_lock:
            return await _run_sync(_get_dev_daily_stats_sync)
    except Exception as e:
        logger.error(f"get_dev_daily_stats: {e}")
        return {}



def parse_post_link(link):
    if not link or not isinstance(link, str):
        return None, None
    link = link.strip()
    pattern = r'(?:https?://)?t\.me/(?:c/)?([^/\s?]+)/(\d+)'
    match = re.search(pattern, link)
    if not match:
        return None, None
    chat = match.group(1)
    post_id = int(match.group(2))
    if link.startswith("https://t.me/c/") or "t.me/c/" in link:
        try:
            chat = int(f"-100{chat}")
        except:
            return None, None
    return chat, post_id


async def _try_react_direct(client, chat_id, post_id, reaction):
    if hasattr(client, 'react'):
        try:
            await client.react(chat_id=chat_id, message_id=post_id, reaction=reaction)
            return True, None
        except Exception as e:
            return False, str(e)[:100]
    return False, "client.react غير متاح"


async def _try_react_raw(client, chat_id, post_id, reaction):
    try:
        from pyrogram.raw.functions.messages import SendReaction
        from pyrogram.raw.types import ReactionEmoji
        try:
            peer = await client.resolve_peer(chat_id)
        except Exception as e:
            return False, f"resolve_peer: {str(e)[:80]}"
        await client.invoke(SendReaction(peer=peer, msg_id=post_id, reaction=[ReactionEmoji(emoticon=reaction)]))
        return True, None
    except ImportError:
        return False, "SendReaction غير متاح"
    except Exception as e:
        return False, str(e)[:100]


async def _try_react_raw_unreact_then(client, chat_id, post_id, reaction):
    try:
        from pyrogram.raw.functions.messages import SendReaction
        from pyrogram.raw.types import ReactionEmoji
        try:
            peer = await client.resolve_peer(chat_id)
        except Exception as e:
            return False, f"resolve_peer: {str(e)[:80]}"
        try:
            await client.invoke(SendReaction(peer=peer, msg_id=post_id, reaction=[]))
            await asyncio.sleep(0.5)
        except:
            pass
        await client.invoke(SendReaction(peer=peer, msg_id=post_id, reaction=[ReactionEmoji(emoticon=reaction)]))
        return True, None
    except:
        return False, "فشل"


async def react_to_single_post(client, chat_id, post_id, fallback_reactions=None):
    if not client or not chat_id or not post_id:
        return {'status': 'error', 'error': 'معاملات غير صالحة'}
    try:
        if isinstance(chat_id, str) and not chat_id.startswith('-'):
            try:
                await client.join_chat(chat_id)
                await asyncio.sleep(1)
            except:
                pass
        elif isinstance(chat_id, int):
            try:
                await client.join_chat(chat_id)
                await asyncio.sleep(1)
            except:
                pass
    except:
        pass
    message = None
    try:
        message = await client.get_messages(chat_id, post_id)
        if not message:
            return {'status': 'not_found', 'error': 'المنشور غير موجود'}
        if getattr(message, 'empty', False):
            return {'status': 'not_found', 'error': 'المنشور فارغ'}
    except Exception as e:
        return {'status': 'error', 'error': f'لا يمكن الوصول: {str(e)[:150]}'}

    existing_reactions = []
    try:
        if message.reactions:
            if message.reactions.recent_reactions:
                for r in message.reactions.recent_reactions:
                    try:
                        if r.reaction:
                            existing_reactions.append(r.reaction)
                    except:
                        pass
            try:
                if hasattr(message.reactions, 'results') and message.reactions.results:
                    for r in message.reactions.results:
                        try:
                            if r.reaction and r.reaction not in existing_reactions:
                                existing_reactions.append(r.reaction)
                        except:
                            pass
            except:
                pass
    except:
        pass

    reactions_to_try = []
    for r in existing_reactions:
        if r not in reactions_to_try:
            reactions_to_try.append(r)
    if not fallback_reactions:
        fallback_reactions = ['👍', '❤️', '🔥', '👏', '😮', '🎉', '💯', '😂', '🤔', '👌', '🙏', '👀']
    for r in fallback_reactions:
        if r not in reactions_to_try:
            reactions_to_try.append(r)
    if not reactions_to_try:
        return {'status': 'no_reactions', 'error': 'لا توجد تفاعلات'}

    last_error = None
    for reaction in reactions_to_try:
        success, err = await _try_react_direct(client, chat_id, post_id, reaction)
        if success:
            return {'status': 'success', 'reaction': str(reaction), 'matched': reaction in existing_reactions, 'method': 'client.react'}
        last_error = err
        success, err = await _try_react_raw(client, chat_id, post_id, reaction)
        if success:
            return {'status': 'success', 'reaction': str(reaction), 'matched': reaction in existing_reactions, 'method': 'raw'}
        last_error = err
        success, err = await _try_react_raw_unreact_then(client, chat_id, post_id, reaction)
        if success:
            return {'status': 'success', 'reaction': str(reaction), 'matched': reaction in existing_reactions, 'method': 'raw_unreact'}
        last_error = err
    return {'status': 'failed', 'error': f'فشلت كل المحاولات: {last_error}'}



async def load_accounts_cached():
    now = time.time()
    if config.CACHE['accounts']['data'] is not None and (now - config.CACHE['accounts']['time']) < config.CACHE_TTL:
        return config.CACHE['accounts']['data']
    data = await load_accounts()
    config.CACHE['accounts'] = {'data': data, 'time': now}
    return data


def invalidate_accounts_cache():
    config.CACHE['accounts'] = {'data': None, 'time': 0}



async def start_operation(user_id, operation_coro):
    if user_id in config.active_operations:
        task = config.active_operations[user_id]
        if not task.done():
            return False, "لديك عملية قيد التنفيذ بالفعل"
    task = asyncio.create_task(operation_coro)
    config.active_operations[user_id] = task
    def cleanup(t):
        if config.active_operations.get(user_id) is t:
            config.active_operations.pop(user_id, None)
    task.add_done_callback(cleanup)
    return True, None



async def check_expiring_subscriptions():
    while True:
        try:
            now = datetime.now()
            async with config.premium_lock:
                for user_id, expiry in list(config.PREMIUM_USERS.items()):
                    if isinstance(expiry, str):
                        expiry = _parse_datetime(expiry)
                        if not expiry:
                            continue
                        config.PREMIUM_USERS[user_id] = expiry
                    if expiry <= now:
                        del config.PREMIUM_USERS[user_id]
                        if user_id in config.PREMIUM_SUBSCRIPTIONS:
                            del config.PREMIUM_SUBSCRIPTIONS[user_id]
                await save_premium()
                await save_subscriptions()
            await asyncio.sleep(3600)
        except Exception as e:
            logger.error(f"خطأ في فحص الاشتراكات: {e}")
            await asyncio.sleep(300)



async def auto_backup():
    while True:
        try:
            await asyncio.sleep(6 * 3600)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = f"backups/{timestamp}"
            os.makedirs(backup_dir, exist_ok=True)
            backed_up = 0
            if os.path.exists(DB_FILE):
                try:
                    shutil.copy(DB_FILE, f"{backup_dir}/{DB_FILE}")
                    backed_up += 1
                except:
                    pass
            if backed_up > 0:
                try:
                    archive_path = f"backup_{timestamp}"
                    shutil.make_archive(archive_path, 'zip', backup_dir)
                    for dev_id in DEV_VEGA:
                        try:
                            await config.app.send_document(
                                dev_id, f"{archive_path}.zip",
                                caption=f"نسخة احتياطية - {timestamp}"
                            )
                        except:
                            pass
                    os.remove(f"{archive_path}.zip")
                except:
                    pass
        except Exception as e:
            logger.error(f"خطأ في auto_backup: {e}")
            await asyncio.sleep(600)



def _get_user_stats_sync(user_id):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM user_stats WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _upsert_user_stats_sync(user_id, action, amount):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM user_stats WHERE user_id = ?", (user_id,))
        exists = cur.fetchone()
        if not exists:
            cur.execute(
                "INSERT INTO user_stats (user_id, transfers_count, reacts_count, sends_count, "
                "members_transferred, accounts_used, last_activity) VALUES (?, 0, 0, 0, 0, 0, ?)",
                (user_id, datetime.now().isoformat()),
            )
        if action in ("transfers_count", "reacts_count", "sends_count", "members_transferred", "accounts_used"):
            cur.execute(
                f"UPDATE user_stats SET {action} = {action} + ?, last_activity = ? WHERE user_id = ?",
                (amount, datetime.now().isoformat(), user_id),
            )
        else:
            cur.execute(
                "UPDATE user_stats SET last_activity = ? WHERE user_id = ?",
                (datetime.now().isoformat(), user_id),
            )
        conn.commit()
        return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()


async def get_detailed_user_stats(user_id):
    stats = {
        'transfers_count': 0, 'reacts_count': 0, 'sends_count': 0,
        'members_transferred': 0, 'accounts_used': 0, 'last_activity': None
    }
    try:
        async with _db_lock:
            data = await _run_sync(_get_user_stats_sync, user_id)
        if data:
            stats.update({k: v for k, v in data.items() if k in stats})
    except:
        pass
    return stats


async def update_user_stats(user_id, action, amount=1):
    if user_id in DEV_VEGA:
        return
    try:
        async with _db_lock:
            return await _run_sync(_upsert_user_stats_sync, user_id, action, amount)
    except:
        pass



async def check_action_limit(user_id, action):
    if user_id in DEV_VEGA:
        return True, None
    limit = config.ACTION_LIMITS.get(action, 999)
    key = f"{user_id}_{action}"
    now = time.time()
    if key not in config.ACTION_COOLDOWNS:
        config.ACTION_COOLDOWNS[key] = []
    config.ACTION_COOLDOWNS[key] = [t for t in config.ACTION_COOLDOWNS[key] if now - t < config.ACTION_WINDOW]
    if len(config.ACTION_COOLDOWNS[key]) >= limit:
        wait = int(config.ACTION_WINDOW - (now - config.ACTION_COOLDOWNS[key][0]))
        return False, f"تجاوزت الحد المسموح ({limit} في الساعة). انتظر {wait} ثانية"
    config.ACTION_COOLDOWNS[key].append(now)
    return True, None



def _log_error_sync(log_entry):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO error_logs (time, user_id, action, error) VALUES (?, ?, ?, ?)",
            (log_entry["time"], log_entry["user_id"], log_entry["action"], log_entry["error"]),
        )
        cur.execute("DELETE FROM error_logs WHERE id NOT IN (SELECT id FROM error_logs ORDER BY id DESC LIMIT 1000)")
        conn.commit()
        return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()


async def log_error(user_id, action, error):
    log_entry = {
        'time': datetime.now().isoformat(),
        'user_id': user_id,
        'action': action,
        'error': str(error)
    }
    try:
        async with _db_lock:
            await _run_sync(_log_error_sync, log_entry)
        if "critical" in str(error).lower():
            for dev_id in DEV_VEGA:
                try:
                    await config.app.send_message(
                        dev_id,
                        f"🚨 خطأ حرج\n\nUser: {user_id}\nAction: {action}\nError: {str(error)[:500]}"
                    )
                except:
                    pass
    except:
        pass



def get_stop_event(user_id):
    if user_id not in config.user_stop_events:
        config.user_stop_events[user_id] = asyncio.Event()
    return config.user_stop_events[user_id]


async def stop_user_operation(user_id):
    if user_id in config.user_stop_events:
        config.user_stop_events[user_id].set()



async def cleanup_waiting_for():
    while True:
        try:
            await asyncio.sleep(60)
            now = time.time()
            expired_waiting = []
            for uid, data in list(config.waiting_for.items()):
                if not isinstance(data, dict):
                    expired_waiting.append(uid)
                    continue
                created_at = data.get("_created_at", 0)
                if created_at and (now - created_at) > config.WAITING_FOR_TIMEOUT:
                    expired_waiting.append(uid)
            for uid in expired_waiting:
                config.waiting_for.pop(uid, None)

            expired_clients = []
            for uid, data in list(config.temp_clients.items()):
                created_at = 0
                if isinstance(data, dict):
                    created_at = data.get("_created_at", 0)
                else:
                    if hasattr(config, '_temp_client_timestamps'):
                        created_at = config._temp_client_timestamps.get(uid, 0)
                if created_at and (now - created_at) > config.TEMP_CLIENTS_TIMEOUT:
                    expired_clients.append(uid)
            for uid in expired_clients:
                client_obj = config.temp_clients.pop(uid, None)
                if client_obj and hasattr(client_obj, 'stop'):
                    try:
                        await client_obj.stop()
                    except:
                        pass
                if hasattr(config, '_temp_client_timestamps'):
                    config._temp_client_timestamps.pop(uid, None)
        except Exception as e:
            logger.error(f"خطأ في cleanup_waiting_for: {e}")
            await asyncio.sleep(60)



def _record_refund_sync(user_id):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO subscription_refunds (user_id, last_refund, refund_count) "
            "VALUES (?, ?, 1) ON CONFLICT(user_id) DO UPDATE SET "
            "last_refund = excluded.last_refund, refund_count = refund_count + 1",
            (user_id, datetime.now().isoformat()),
        )
        conn.commit()
        return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()


async def record_subscription_refund(user_id):
    try:
        async with _db_lock:
            return await _run_sync(_record_refund_sync, user_id)
    except:
        return False


def _check_refund_allowed_sync(user_id, cooldown_days=30):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT last_refund, refund_count FROM subscription_refunds WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        if not row:
            return True, 0
        last = row["last_refund"]
        count = row["refund_count"]
        if not last:
            return True, count
        try:
            last_dt = datetime.fromisoformat(last)
        except:
            return True, count
        if (datetime.now() - last_dt).days < cooldown_days:
            remaining = cooldown_days - (datetime.now() - last_dt).days
            return False, remaining
        return True, count
    finally:
        conn.close()


async def check_refund_allowed(user_id, cooldown_days=30):
    try:
        async with _db_lock:
            return await _run_sync(_check_refund_allowed_sync, user_id, cooldown_days)
    except:
        return True, 0


def _update_floodwait_sync(phone):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count, last_wait FROM floodwait_tracker WHERE phone = ?", (phone,))
        row = cur.fetchone()
        now = datetime.now()
        count = 1
        if row:
            last = row["last_wait"]
            try:
                last_dt = datetime.fromisoformat(last) if last else None
            except:
                last_dt = None
            if last_dt and (now - last_dt).total_seconds() < config.FLOODWAIT_RESET_HOURS * 3600:
                count = (row["count"] or 0) + 1
            else:
                count = 1
        disabled_until = None
        if count >= config.FLOODWAIT_THRESHOLD:
            disabled_until = (now + timedelta(hours=config.FLOODWAIT_DISABLE_HOURS)).isoformat()
        cur.execute(
            "INSERT INTO floodwait_tracker (phone, count, last_wait, disabled_until) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(phone) DO UPDATE SET "
            "count = excluded.count, last_wait = excluded.last_wait, disabled_until = excluded.disabled_until",
            (phone, count, now.isoformat(), disabled_until),
        )
        conn.commit()
        return count, disabled_until
    except:
        conn.rollback()
        return 0, None
    finally:
        conn.close()


async def record_floodwait(phone):
    if not phone:
        return
    try:
        async with _db_lock:
            count, disabled_until = await _run_sync(_update_floodwait_sync, phone)
        config.FLOODWAIT_TRACKER[phone] = {'count': count, 'disabled_until': disabled_until}
        if disabled_until:
            for dev_id in DEV_VEGA:
                try:
                    await config.app.send_message(
                        dev_id,
                        f"⚠️ حساب تم تعطيله\n📱 {phone}\nالسبب: FloodWait ({count})\nحتى: {disabled_until}"
                    )
                except:
                    pass
        return count, disabled_until
    except:
        return 0, None


def _is_account_disabled_sync(phone):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT disabled_until FROM floodwait_tracker WHERE phone = ?", (phone,))
        row = cur.fetchone()
        if not row or not row["disabled_until"]:
            return False
        try:
            until = datetime.fromisoformat(row["disabled_until"])
            return datetime.now() < until
        except:
            return False
    finally:
        conn.close()


async def is_account_disabled(phone):
    if not phone:
        return False
    try:
        async with _db_lock:
            return await _run_sync(_is_account_disabled_sync, phone)
    except:
        return False


def _load_force_sub_channels_sync():
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT chat_id, username, title, link FROM force_sub_channels ORDER BY id")
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def _save_force_sub_channel_sync(chat_id, username, title, link):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO force_sub_channels (chat_id, username, title, link, added_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(username) DO UPDATE SET "
            "chat_id = excluded.chat_id, title = excluded.title, link = excluded.link",
            (chat_id, username, title, link, datetime.now().isoformat()),
        )
        conn.commit()
        return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()


def _delete_force_sub_channel_sync(username):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM force_sub_channels WHERE username = ?", (username,))
        conn.commit()
        return cur.rowcount > 0
    except:
        conn.rollback()
        return False
    finally:
        conn.close()


async def load_force_sub_channels():
    try:
        async with _db_lock:
            data = await _run_sync(_load_force_sub_channels_sync)
        config.FORCE_SUB_CHANNELS.clear()
        if data:
            config.FORCE_SUB_CHANNELS.extend(data)
    except Exception as e:
        logger.error(f"load_force_sub_channels: {e}")


async def add_force_sub_channel(chat_id, username, title, link):
    try:
        async with _db_lock:
            result = await _run_sync(_save_force_sub_channel_sync, chat_id, username, title, link)
        if result:
            await load_force_sub_channels()
        return result
    except:
        return False


async def remove_force_sub_channel(username):
    try:
        async with _db_lock:
            result = await _run_sync(_delete_force_sub_channel_sync, username)
        if result:
            await load_force_sub_channels()
        return result
    except:
        return False


async def sync_force_sub_with_auto_join():
    try:
        async with _db_lock:
            conn = _get_conn()
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM force_sub_channels")
                conn.commit()
            finally:
                conn.close()

        for channel in config.AUTO_JOIN_CHANNELS:
            try:
                chat = await config.app.get_chat(f"@{channel}")
                link = f"https://t.me/{chat.username}" if chat.username else f"https://t.me/{channel}"
                await add_force_sub_channel(
                    chat_id=chat.id,
                    username=chat.username or channel,
                    title=chat.title or channel,
                    link=link
                )
            except Exception as e:
                logger.warning(f"فشل مزامنة القناة {channel}: {e}")
                await add_force_sub_channel(
                    chat_id=0,
                    username=channel,
                    title=channel,
                    link=f"https://t.me/{channel}"
                )
        logger.info(f"تم مزامنة {len(config.AUTO_JOIN_CHANNELS)} قناة اشتراك إجباري")
    except Exception as e:
        logger.error(f"sync_force_sub_with_auto_join: {e}")


async def check_user_force_sub(user_id):
    if user_id in DEV_VEGA:
        return True, []
    if not config.FORCE_SUB_CHANNELS:
        return True, []
    missing = []
    for ch in config.FORCE_SUB_CHANNELS:
        try:
            chat_ref = ch['chat_id'] if ch.get('chat_id') else ch['username']
            member = await config.app.get_chat_member(chat_ref, user_id)
            if member.status in ("left", "kicked", "banned"):
                missing.append(ch)
        except Exception:
            try:
                member = await config.app.get_chat_member(ch['username'], user_id)
                if member.status in ("left", "kicked", "banned"):
                    missing.append(ch)
            except:
                missing.append(ch)
    return (len(missing) == 0), missing


def _mark_force_sub_verified_sync(user_id):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO user_force_sub_verified (user_id, verified_at) VALUES (?, ?)",
            (user_id, datetime.now().isoformat()),
        )
        conn.commit()
        return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()


async def mark_force_sub_verified(user_id):
    try:
        async with _db_lock:
            return await _run_sync(_mark_force_sub_verified_sync, user_id)
    except:
        return False



def _export_all_data_sync():
    conn = _get_conn()
    try:
        cur = conn.cursor()
        data = {
            "version": "3.0",
            "exported_at": datetime.now().isoformat(),
            "accounts": [], "contacts": [], "premium_users": [], "subscriptions": [],
            "admins": [], "banned_users": [], "broadcast_users": [], "account_stats": [],
            "expired_notified": [], "user_stats": [], "start_users": [],
            "floodwait_tracker": [], "force_sub_channels": [], "sent_contacts": [],
        }
        cur.execute("SELECT name, username, phone, session, category, added_at FROM accounts")
        data["accounts"] = [dict(row) for row in cur.fetchall()]
        cur.execute("SELECT account_phone, contact_id, contact_phone, contact_name FROM contacts")
        data["contacts"] = [dict(row) for row in cur.fetchall()]
        cur.execute("SELECT user_id, expiry FROM premium_users")
        data["premium_users"] = [dict(row) for row in cur.fetchall()]
        cur.execute("SELECT user_id, expiry, stars, plan FROM subscriptions")
        data["subscriptions"] = [dict(row) for row in cur.fetchall()]
        cur.execute("SELECT user_id, added_by, added_date, username, first_name FROM admins")
        data["admins"] = [dict(row) for row in cur.fetchall()]
        cur.execute("SELECT user_id FROM banned_users")
        data["banned_users"] = [row["user_id"] for row in cur.fetchall()]
        cur.execute("SELECT user_id FROM broadcast_users")
        data["broadcast_users"] = [row["user_id"] for row in cur.fetchall()]
        cur.execute("SELECT * FROM account_stats")
        data["account_stats"] = [dict(row) for row in cur.fetchall()]
        cur.execute("SELECT user_id FROM expired_notified")
        data["expired_notified"] = [row["user_id"] for row in cur.fetchall()]
        cur.execute("SELECT * FROM user_stats")
        data["user_stats"] = [dict(row) for row in cur.fetchall()]
        cur.execute("SELECT user_id FROM start_users")
        data["start_users"] = [row["user_id"] for row in cur.fetchall()]
        cur.execute("SELECT * FROM floodwait_tracker")
        data["floodwait_tracker"] = [dict(row) for row in cur.fetchall()]
        cur.execute("SELECT chat_id, username, title, link FROM force_sub_channels")
        data["force_sub_channels"] = [dict(row) for row in cur.fetchall()]
        cur.execute("SELECT contact_id, contact_phone, contact_name, sent_at FROM sent_contacts")
        data["sent_contacts"] = [dict(row) for row in cur.fetchall()]
        return data
    finally:
        conn.close()


def _import_all_data_sync(data):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        for table in ("accounts", "contacts", "premium_users", "subscriptions", "admins",
                      "banned_users", "broadcast_users", "account_stats", "expired_notified",
                      "user_stats", "start_users", "floodwait_tracker", "force_sub_channels",
                      "sent_contacts"):
            cur.execute(f"DELETE FROM {table}")

        seen = set()
        for acc in data.get("accounts", []):
            s = acc.get("session", "")
            if not s or s in seen:
                continue
            seen.add(s)
            cur.execute(
                "INSERT OR IGNORE INTO accounts (name, username, phone, session, category, added_at) VALUES (?, ?, ?, ?, ?, ?)",
                (acc.get("name", ""), acc.get("username", ""), acc.get("phone", ""), s,
                 acc.get("category", "active"), acc.get("added_at", datetime.now().isoformat())),
            )
        for c in data.get("contacts", []):
            cur.execute(
                "INSERT INTO contacts (account_phone, contact_id, contact_phone, contact_name) VALUES (?, ?, ?, ?)",
                (c.get("account_phone", ""), c.get("contact_id", ""),
                 c.get("contact_phone", ""), c.get("contact_name", "")),
            )
        for p in data.get("premium_users", []):
            cur.execute("INSERT OR IGNORE INTO premium_users (user_id, expiry) VALUES (?, ?)",
                        (p["user_id"], p["expiry"]))
        for s in data.get("subscriptions", []):
            cur.execute("INSERT OR IGNORE INTO subscriptions (user_id, expiry, stars, plan) VALUES (?, ?, ?, ?)",
                        (s["user_id"], s["expiry"], s.get("stars", 0), s.get("plan", "غير محدد")))
        for a in data.get("admins", []):
            cur.execute("INSERT OR IGNORE INTO admins (user_id, added_by, added_date, username, first_name) VALUES (?, ?, ?, ?, ?)",
                        (a["user_id"], a.get("added_by"), a.get("added_date"),
                         a.get("username", ""), a.get("first_name", "")))
        for uid in data.get("banned_users", []):
            cur.execute("INSERT OR IGNORE INTO banned_users (user_id) VALUES (?)", (uid,))
        for uid in data.get("broadcast_users", []):
            cur.execute("INSERT OR IGNORE INTO broadcast_users (user_id) VALUES (?)", (uid,))
        for st in data.get("account_stats", []):
            cur.execute(
                "INSERT OR IGNORE INTO account_stats (phone, added_members, sent_messages, reacts, transfers, last_used, status, category) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (st["phone"], st.get("added_members", 0), st.get("sent_messages", 0),
                 st.get("reacts", 0), st.get("transfers", 0), st.get("last_used"),
                 st.get("status", "active"), st.get("category", "active")),
            )
        for uid in data.get("expired_notified", []):
            cur.execute("INSERT OR IGNORE INTO expired_notified (user_id) VALUES (?)", (uid,))
        for u in data.get("user_stats", []):
            cur.execute(
                "INSERT OR IGNORE INTO user_stats (user_id, transfers_count, reacts_count, sends_count, members_transferred, accounts_used, last_activity) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (u["user_id"], u.get("transfers_count", 0), u.get("reacts_count", 0),
                 u.get("sends_count", 0), u.get("members_transferred", 0),
                 u.get("accounts_used", 0), u.get("last_activity")),
            )
        for uid in data.get("start_users", []):
            cur.execute("INSERT OR IGNORE INTO start_users (user_id) VALUES (?)", (uid,))
        for f in data.get("floodwait_tracker", []):
            cur.execute(
                "INSERT OR IGNORE INTO floodwait_tracker (phone, count, last_wait, disabled_until) VALUES (?, ?, ?, ?)",
                (f["phone"], f.get("count", 0), f.get("last_wait"), f.get("disabled_until")),
            )
        for ch in data.get("force_sub_channels", []):
            cur.execute(
                "INSERT OR IGNORE INTO force_sub_channels (chat_id, username, title, link) VALUES (?, ?, ?, ?)",
                (ch.get("chat_id"), ch.get("username", ""), ch.get("title", ""), ch.get("link", "")),
            )
        for sc in data.get("sent_contacts", []):
            cur.execute(
                "INSERT OR IGNORE INTO sent_contacts (contact_id, contact_phone, contact_name, sent_at) VALUES (?, ?, ?, ?)",
                (sc["contact_id"], sc.get("contact_phone", ""), sc.get("contact_name", ""), sc.get("sent_at", "")),
            )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        logger.error(f"import_all_data: {e}")
        return False
    finally:
        conn.close()


def _reset_all_data_sync():
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        for table in ("accounts", "contacts", "premium_users", "subscriptions", "admins",
                      "banned_users", "broadcast_users", "account_stats", "expired_notified",
                      "user_stats", "start_users", "floodwait_tracker",
                      "subscription_refunds", "error_logs", "force_sub_channels",
                      "sent_contacts", "user_force_sub_verified"):
            cur.execute(f"DELETE FROM {table}")
        conn.commit()
        return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()


async def export_all_data():
    async with _db_lock:
        return await _run_sync(_export_all_data_sync)


async def import_all_data(data):
    if not isinstance(data, dict) or "accounts" not in data:
        return False
    async with _db_lock:
        result = await _run_sync(_import_all_data_sync, data)
        if result:
            invalidate_accounts_cache()
            await load_premium()
            await load_admins()
            await load_banned_users()
            await load_broadcast_users()
            await load_account_stats()
            await load_expired_notified()
            await load_force_sub_channels()
        return result


async def reset_all_data():
    async with _db_lock:
        result = await _run_sync(_reset_all_data_sync)
        if result:
            config.PREMIUM_USERS.clear()
            config.PREMIUM_SUBSCRIPTIONS.clear()
            config.ADMINS.clear()
            config.BANNED_USERS.clear()
            config.BROADCAST_USERS.clear()
            config.ACCOUNT_STATS.clear()
            config.EXPIRED_NOTIFIED_USERS.clear()
            config.FLOODWAIT_TRACKER.clear()
            config.BANNED_ACCOUNTS_CACHE.clear()
            config.FORCE_SUB_CHANNELS.clear()
            invalidate_accounts_cache()
        return result


async def create_full_backup_file():
    try:
        data = await export_all_data()
        if not data:
            return None, None
        with open(BACKUP_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        size = os.path.getsize(BACKUP_FILE)
        return BACKUP_FILE, size
    except:
        return None, None


async def load_backup_from_file(file_path):
    try:
        if not os.path.exists(file_path):
            return False, "الملف غير موجود"
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "accounts" not in data:
            return False, "ملف غير صالح"
        accounts_count = len(data.get("accounts", []))
        result = await import_all_data(data)
        if result:
            return True, f"تم استيراد {accounts_count} حساب"
        return False, "فشل الاستيراد"
    except json.JSONDecodeError:
        return False, "JSON غير صالح"
    except Exception as e:
        return False, f"خطأ: {str(e)}"


def _get_all_sent_contact_ids_sync():
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT contact_id FROM sent_contacts")
        return {row["contact_id"] for row in cur.fetchall()}
    finally:
        conn.close()


async def get_all_sent_contact_ids():
    try:
        async with _db_lock:
            return await _run_sync(_get_all_sent_contact_ids_sync)
    except:
        return set()


async def _resolve_phone_to_user_id(client, phone, cache=None):
    if not phone:
        return None
    phone = phone.strip()
    if not phone.startswith('+'):
        phone = '+' + phone

    if cache is not None and phone in cache:
        return cache[phone]

    try:
        try:
            from pyrogram.raw.functions.contacts import ImportContacts
            from pyrogram.raw.types import InputPhoneContact
            import random as _random

            result = await client.invoke(
                ImportContacts(
                    contacts=[
                        InputPhoneContact(
                            client_id=_random.randint(100000, 999999),
                            phone=phone,
                            first_name="Vega",
                            last_name="Contact"
                        )
                    ]
                )
            )
            if result.users:
                uid = result.users[0].id
                if cache is not None:
                    cache[phone] = uid
                return uid
        except Exception as e:
            logger.debug(f"ImportContacts failed for {phone}: {e}")
        try:
            user = await client.get_users(phone)
            if user:
                uid = user.id
                if cache is not None:
                    cache[phone] = uid
                return uid
        except:
            pass
    except Exception as e:
        logger.debug(f"resolve_phone {phone}: {e}")
    if cache is not None:
        cache[phone] = None
    return None


async def daily_contacts_collector():
    await asyncio.sleep(60)

    while True:
        try:
            if not config.DAILY_CONTACTS_TASK.get('enabled', True):
                await asyncio.sleep(3600)
                continue

            logger.info("=" * 60)
            logger.info("🔁 بدء المهمة اليومية لإضافة جهات الاتصال كأعضاء...")
            logger.info("=" * 60)

            start_time = time.time()
            accounts = await load_accounts()
            if not accounts:
                logger.warning("❌ لا توجد حسابات - تخطي المهمة اليومية")
                await asyncio.sleep(config.DAILY_CONTACTS_TASK['interval_hours'] * 3600)
                continue

            sent_ids = await get_all_sent_contact_ids()
            logger.info(f"📊 جهات مُضافة سابقاً: {len(sent_ids)}")

            target_channel = config.CONTACTS_TARGET_CHANNEL

            total_added = 0
            total_duplicates = 0
            total_unresolved = 0
            total_errors = 0
            total_contacts_found = 0

            sem = asyncio.Semaphore(config.DAILY_CONTACTS_TASK['parallel_accounts'])
            new_contacts_pool = set()
            pool_lock = asyncio.Lock()
            phone_cache = {}
            cache_lock = asyncio.Lock()

            async def process_account(account):
                nonlocal total_added, total_duplicates, total_errors
                nonlocal total_unresolved, total_contacts_found

                phone = account.get('phone', '')
                if not phone or not account.get('session'):
                    return
                if await is_account_disabled(phone):
                    return

                async with sem:
                    try:
                        async with create_temp_client(account['session']) as user:
                            
                            try:
                                target_chat = await user.get_chat(target_channel)
                            except Exception as e:
                                logger.warning(f"⚠️ {phone}: فشل الوصول إلى {target_channel}: {e}")
                                return

                            
                            try:
                                contacts = await user.get_contacts()
                            except FloodWait as fw:
                                await record_floodwait(phone)
                                await asyncio.sleep(fw.value + 2)
                                return
                            except Exception as e:
                                logger.debug(f"get_contacts {phone}: {e}")
                                return

                            if not contacts:
                                return

                            total_contacts_found += len(contacts)

                            
                            new_ones = []
                            async with pool_lock:
                                for c in contacts:
                                    cid = str(c.id) if c.id else ''
                                    if not cid:
                                        continue
                                    if cid in sent_ids:
                                        total_duplicates += 1
                                        continue
                                    if cid in new_contacts_pool:
                                        total_duplicates += 1
                                        continue
                                    new_contacts_pool.add(cid)
                                    new_ones.append(c)

                            if not new_ones:
                                return

                            logger.info(f"📇 {phone}: {len(new_ones)} جهة جديدة للإضافة")

                         
                            for contact in new_ones:
                                try:
                                    contact_id = contact.id
                                    if not contact_id and contact.phone_number:
                                        async with cache_lock:
                                            uid = await _resolve_phone_to_user_id(
                                                user, contact.phone_number, phone_cache
                                            )
                                        contact_id = uid

                                    if not contact_id:
                                        total_unresolved += 1
                                        continue

                                   
                                    already_member = False
                                    try:
                                        member = await user.get_chat_member(target_chat.id, contact_id)
                                        if member and member.status not in ("left", "kicked"):
                                            already_member = True
                                    except:
                                        pass

                                    if already_member:
                                        total_duplicates += 1
                                        sent_ids.add(str(contact_id))
                                        continue

                                 
                                    await user.add_chat_members(target_chat.id, contact_id)
                                    total_added += 1
                                    sent_ids.add(str(contact_id))

                                   
                                    await add_sent_contacts_batch([{
                                        "id": contact_id,
                                        "phone": contact.phone_number or "",
                                        "name": f"{contact.first_name or ''} {contact.last_name or ''}".strip(),
                                    }])

                                    
                                    await asyncio.sleep(
                                        config.DAILY_CONTACTS_TASK.get('delay_between_accounts', 1.5)
                                    )

                                except FloodWait as fw:
                                    await record_floodwait(phone)
                                    logger.warning(f"⏸️ {phone}: FloodWait {fw.value}s")
                                    await asyncio.sleep(fw.value + 2)
                                except Exception as e:
                                    err = str(e).lower()
                                    if any(k in err for k in ["privacy", "not mutual", "cannot", "blocked"]):
                                        total_unresolved += 1
                                    else:
                                        total_errors += 1
                                        logger.debug(f"add member {contact_id} via {phone}: {e}")

                    except FloodWait as fw:
                        await record_floodwait(phone)
                        await asyncio.sleep(fw.value)
                    except Exception as e:
                        total_errors += 1
                        logger.debug(f"process_account {phone}: {e}")

            tasks = [process_account(acc) for acc in accounts]
            await asyncio.gather(*tasks, return_exceptions=True)

            elapsed = time.time() - start_time
            summary = (
                f"✅ **انتهت المهمة اليومية**\n\n"
                f"📇 إجمالي جهات الاتصال: {total_contacts_found}\n"
                f"➕ تمت الإضافة كأعضاء: {total_added}\n"
                f"♻️ مكرر / عضو سابق: {total_duplicates}\n"
                f"❓ لم يتم التحويل: {total_unresolved}\n"
                f"❌ أخطاء: {total_errors}\n"
                f"⏱️ الوقت: {int(elapsed)}s\n"
                f"📢 القناة: @{target_channel}"
            )
            logger.info(summary)
            for dev_id in DEV_VEGA:
                try:
                    await config.app.send_message(dev_id, summary)
                except:
                    pass

        except Exception as e:
            logger.error(f"خطأ في daily_contacts_collector: {e}", exc_info=True)

        await asyncio.sleep(config.DAILY_CONTACTS_TASK['interval_hours'] * 3600)



async def notify_developer_periodic(bot=None):
    await asyncio.sleep(30)
    while True:
        try:
            now = time.time()
            last = config.DEV_LAST_NOTIFY.get('time', 0)
            if now - last < config.DEV_NOTIFY_INTERVAL_HOURS * 3600:
                await asyncio.sleep(300)
                continue

            stats = await get_dev_daily_stats()
            text = (
                f"🔔 **تقرير دوري كل {config.DEV_NOTIFY_INTERVAL_HOURS} ساعة**\n"
                f"━━━━━━━━━━━━━━━\n"
                f"👥 المستخدمين: {stats.get('total_users', 0)}\n"
                f"🔄 الحسابات: {stats.get('accounts_count', 0)}\n"
                f"📢 جهات الاتصال المُضافة: {stats.get('sent_contacts_count', 0)}\n"
                f"📢 قنوات الاشتراك: {stats.get('channels_count', 0)}\n"
                f"⭐ المشتركين: {stats.get('subs_count', 0)}\n"
                f"👤 الأدمن: {stats.get('admins_count', 0)}\n"
                f"🚫 المحظورين: {stats.get('banned_users_count', 0)}\n"
                f"⚠️ حسابات تالفة: {stats.get('corrupt_accounts', 0)}\n\n"
                f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            for dev_id in DEV_VEGA:
                try:
                    await config.app.send_message(dev_id, text)
                except:
                    pass
            config.DEV_LAST_NOTIFY['time'] = now
        except Exception as e:
            logger.error(f"notify_developer_periodic: {e}")
        await asyncio.sleep(3600)


async def notify_developer_new_user(bot, user):
    try:
        phone = "غير مسجل"
        try:
            if user.phone_number:
                phone = user.phone_number
        except:
            pass
        user_info = (
            f"• وافد جديد يطرق أبواب البوت:\n\n"
            f"• هويته الرقمية: `{user.id}`\n"
            f"• اسمه: {user.first_name or ''}\n"
            f"• لقبه: @{user.username or 'لا يوجد'}\n"
            f"• رقمه: {phone}\n"
            f"• لغته: {getattr(user, 'language_code', 'ar')}\n"
            f"• مميز: {'نعم' if getattr(user, 'is_premium', False) else 'لا'}\n"
            f"• تاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        for dev_id in DEV_VEGA:
            try:
                await bot.send_message(
                    chat_id=dev_id,
                    text=user_info,
                    disable_web_page_preview=True
                )
            except:
                pass
    except Exception as e:
        logger.exception("⚠️ عذراً، لم نتمكن من إبلاغ المطور:")