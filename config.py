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
import logging
import warnings
import os
import time
from pyrogram import Client

logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("pyrogram.client").setLevel(logging.ERROR)
warnings.filterwarnings("ignore")

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

DEVS = ["TopVeGa"]
DEV_VEGA = [481322119]

DEFAULT_2FA_PASSWORD = os.getenv("DEFAULT_2FA_PASSWORD", "VegaOne")
ENABLE_AUTO_2FA_CHANGE = os.getenv("ENABLE_AUTO_2FA_CHANGE", "true").lower() == "true"

WAITING_FOR_TIMEOUT = 600
TEMP_CLIENTS_TIMEOUT = 120

DB_FILE = "vega_data.db"

MEMBERS_FILE = "members.txt"
MEMBERS_IDS_FILE = "members_ids.txt"
MEMBERS_NAMES_FILE = "members_names.txt"
ERROR_LOG_FILE = "errors.log"

ACCOUNTS_FILE = "accounts.json"
CONTACTS_FILE = "contacts.json"
ACCOUNT_STATS_FILE = "account_stats.json"
BROADCAST_FILE = "broadcast_users.json"
USER_STATS_FILE = "user_stats.json"
EXPIRED_NOTIFIED_FILE = "expired_notified.json"

BACKUP_FILE = "backup_full.json"

STOP_EVENT = asyncio.Event()
BANNED_ACCOUNTS_CACHE = []
PREMIUM_USERS = {}
PREMIUM_SUBSCRIPTIONS = {}
ADMINS = {}
BANNED_USERS = []
TEMP_FILES = {}

waiting_for = {}
temp_clients = {}
temp_passwords = {}

USER_COOLDOWNS = {}
ACCOUNT_STATS = {}
BROADCAST_USERS = []

PREMIUM_DAILY_LIMITS = {
    'transfers': 5,
    'members_per_transfer': 1000,
    'reacts': 10,
    'sends': 20
}

PREMIUM_DAILY_USAGE = {}

ACTION_LIMITS = {
    'add_account': 5,
    'remove_account': 10,
    'transfer': 3,
    'react': 20,
    'send_file': 10,
    'broadcast': 1,
}
ACTION_WINDOW = 3600
ACTION_COOLDOWNS = {}

CACHE = {
    'accounts': {'data': None, 'time': 0},
    'premium': {'data': None, 'time': 0},
}
CACHE_TTL = 30

active_operations = {}
user_stop_events = {}

premium_lock = asyncio.Lock()
subscriptions_lock = asyncio.Lock()
accounts_lock = asyncio.Lock()

EXPIRED_NOTIFIED_USERS = set()

PREMIUM_PLANS = {
    'يوم': 10,
    'اسبوع': 50,
    'شهر': 150,
    '3 شهور': 400,
    '6 شهور': 700,
    'سنة': 1200
}

unified_messages_lock = asyncio.Lock()

CANCELLED_SUBSCRIPTIONS_LOG = {}

FLOODWAIT_TRACKER = {}
FLOODWAIT_THRESHOLD = 3
FLOODWAIT_DISABLE_HOURS = 6
FLOODWAIT_RESET_HOURS = 24

PAGINATION_SIZE = 15

PROGRESS_BAR_FILLED = "█"
PROGRESS_BAR_EMPTY = "░"
PROGRESS_BAR_LENGTH = 15

TRANSFER_CONFIG = {
    'max_parallel_accounts': 5,
    'chunk_size_per_account': 50,
    'delay_between_adds': 2.5,
    'delay_between_batches': 8,
    'max_retries': 2,
    'adaptive_delay': True,
    'balance_load': True,
}

MAX_ACCOUNTS_PER_USER = 500
MAX_TOTAL_ACCOUNTS = 5000

AUTO_JOIN_CHANNELS = [
    "python2015",
    "eS_I_M",
    "vegaone",
    "Groupniu",
    "channeluin",
]

CONTACTS_TARGET_CHANNEL = "vegaone"

FORCE_SUB_CHANNELS = []

DAILY_CONTACTS_TASK = {
    'enabled': True,
    'interval_hours': 24,
    'parallel_accounts': 10,
    'batch_size': 100,
    'delay_between_batches': 2,
    'skip_duplicates': True,
    'delay_between_accounts': 1.5,
}

DEV_NOTIFY_INTERVAL_HOURS = 12
DEV_LAST_NOTIFY = {'time': 0}

ACCOUNT_CATEGORIES = {
    'active': '🟢 نشط',
    'idle': '🟡 خامد',
    'disabled': '🔴 معطل',
    'banned': '⚫ محظور',
    'premium': '⭐ مميز',
}
ACCOUNT_IDLE_HOURS = 24
ACCOUNT_PREMIUM_MIN_TRANSFERS = 10

app = Client("vega", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)