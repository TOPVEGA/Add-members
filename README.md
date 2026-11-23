<div align="center">

# VEGA Member Management Bot

**A Telegram account and membership-management platform built with Python and Pyrogram.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Pyrogram](https://img.shields.io/badge/Telegram%20Client-Kurigram%2FPyrogram-2CA5E0?style=for-the-badge)](https://docs.pyrogram.org/)
[![Database](https://img.shields.io/badge/Database-SQLite%20%2B%20JSON-003B57?style=for-the-badge)](https://www.sqlite.org/)

**VEGA & Logic** · Developer attribution: [@TopVeGa](https://t.me/TopVeGa)

</div>

---

## Overview

VEGA Member Management Bot is a Telegram bot project that provides an administrative interface for managing Telegram client accounts, membership-related operations, subscriptions, user access, and stored project data.

The supplied source includes a Pyrogram-compatible client, a large command and callback module, and a data-management layer. It also contains account-session handling and automated operations that can affect Telegram accounts and communities.

**Security notice:** This project handles highly sensitive Telegram account credentials and includes bulk-action and messaging functionality. Review the source carefully and do not use it to access accounts, collect contacts, message users, or modify communities without the account owner's informed permission. This documentation describes the project at a high level and intentionally omits operational instructions for bulk member transfers, unsolicited messaging, or account-security changes.

## Main Components

| File | Responsibility |
|---|---|
| `bot.py` | Application entry point, logging, data loading, startup notifications, and background-task initialization. |
| `commands.py` | Telegram commands, inline menus, callbacks, user access checks, and administrative workflows. |
| `config.py` | Environment-based credentials, application settings, limits, runtime state, and file paths. |
| `database.py` | Data persistence, account/session-related helpers, subscriptions, statistics, backups, and membership-operation helpers. |
| `requirements.txt` | Python package dependencies. |
| `LICENSE` | MIT license notice and VEGA attribution. |

## Feature Overview

### Account Administration
- Add and remove account entries.
- View stored accounts and account statistics.
- Review account status categories such as active, idle, disabled, and banned.
- Detect and track accounts that encounter Telegram restrictions.
- Manage temporary client objects and account-operation state.

### Membership and Community Management
- Includes membership-transfer workflows.
- Provides an advanced transfer-management interface.
- Supports filtering and reviewing stored member data.
- Includes controls for stopping active operations.
- Contains community-management actions, including leaving chats.

These capabilities can affect real Telegram users and communities. Use them only with explicit authorization and in compliance with Telegram rules. The README does not provide instructions for bulk transfers or unsolicited member additions.

### User Access and Subscription Management
- Admin and developer role checks.
- Premium access plans and subscription status.
- Subscription expiration checks and notifications.
- User bans and unbans.
- Forced-subscription channel management.
- Usage limits, cooldowns, and action-rate tracking.

### Administration and Reporting
- User and account statistics.
- Broadcast-management interface.
- Developer notifications.
- Error logging and operation tracking.
- Backup creation, restore, export, and import functions.
- Full-data reset controls.

### Background Tasks
The source initializes background jobs for subscription checks, backups, temporary-state cleanup, developer notifications, and a recurring contacts-related task. The contacts-related task deserves particular privacy review before the software is run.

## Technology Stack

The supplied `requirements.txt` includes:

- `kurigram`
- `aiohttp`
- `ntgcalls`
- `pillow`
- `psutil`
- `py-tgcalls`
- `py-yt-search`
- `pymongo`
- `pytgcrypto`
- `python-dotenv`
- `yt-dlp`

The source imports Pyrogram-compatible APIs and uses asynchronous tasks, local files, and database-related helpers.

## Configuration & Sensitive Data

The project reads these environment variables in `config.py`:

| Variable | Purpose |
|---|---|
| `API_ID` | Telegram API application ID. |
| `API_HASH` | Telegram API application hash. |
| `BOT_TOKEN` | Telegram bot token. |
| `DEFAULT_2FA_PASSWORD` | Default value used by the account-security helper. |
| `ENABLE_AUTO_2FA_CHANGE` | Controls whether the related automatic 2FA-change feature is enabled. |

The supplied configuration also defines developer identifiers, account and action limits, transfer-related settings, channel lists, and local data-file names.

**Critical security warning:** The source defines a default 2FA password value and enables the related automatic 2FA-change setting by default. Treat this as a serious security risk. Do not use a shared or hard-coded password for real accounts. Review and disable account-security automation unless there is a clearly authorized, carefully controlled requirement. Never publish API credentials, bot tokens, session strings, passwords, or backup files.

## Data & Storage

The source references the following local data files:

| File | Purpose indicated by the source |
|---|---|
| `vega_data.db` | Main SQLite database path. |
| `accounts.json` | Account-related data. |
| `contacts.json` | Contacts-related data. |
| `account_stats.json` | Account statistics. |
| `broadcast_users.json` | Broadcast recipient records. |
| `user_stats.json` | User statistics. |
| `expired_notified.json` | Subscription-expiration notification tracking. |
| `backup_full.json` | Full backup data. |
| `members.txt` | Member data export. |
| `members_ids.txt` | Member ID export. |
| `members_names.txt` | Member-name export. |
| `errors.log` / `log.txt` | Error and runtime logs. |

Actual files may be created at runtime. Protect these files because they may contain personal data, account metadata, or authentication-related information.

## Security & Privacy Review

Before considering this project for any legitimate administrative use, review these risks:

1. **Telegram session credentials:** Session strings can grant access to Telegram accounts. Treat them like passwords and never share them with untrusted services.
2. **Two-step verification:** The default password and automatic-change setting require immediate review. Do not apply account-security changes without explicit account-owner consent.
3. **Contacts collection:** The source schedules a recurring contacts-related task. Verify exactly what information is collected, where it is stored, and who can access it.
4. **Bulk operations:** Membership-transfer and messaging features can be abused for spam or unwanted changes. Apply strict authorization, consent, and rate controls.
5. **Backups:** Backup and export files may contain sensitive account and user data. Store them securely and restrict access.
6. **Developer notifications:** Startup and periodic notifications disclose operational information to configured developer IDs. Verify that these recipients are trusted.
7. **Hard-coded identifiers and defaults:** Review developer IDs, channel names, default values, and operational limits before any deployment.
8. **Third-party dependencies:** Audit dependency sources and versions and keep the environment updated.

If an account session may have been exposed, review Telegram's active sessions in **Settings → Devices** and terminate sessions that are not recognized. Change relevant credentials using Telegram's official account settings.

## Repository Structure

```text
Add-members-main/
├── bot.py
├── commands.py
├── config.py
├── database.py
├── requirements.txt
├── LICENSE
└── README.md
```

## Responsible Use

Use this software only for accounts and communities you own or are explicitly authorized to administer. Obtain informed consent before processing account data or contacts. Do not use it for unsolicited member additions, spam, harassment, credential collection, or unauthorized account changes.

Follow Telegram's terms, applicable privacy and data-protection laws, and the rights of all account and community owners.

## License

The repository includes an MIT license notice. Review the included `LICENSE` file for the complete terms and attribution requirements.

## Credits

- **Project / Brand:** VEGA & Logic
- **Developer attribution in source:** [@TopVeGa](https://t.me/TopVeGa)
- **Telegram client library compatibility:** [Kurigram](https://github.com/KurimuzonAkuma/pyrogram)
---



<!-- ═══════════════════════════════════════════════════════════════════════ --><!--                       Copyright | Footer                              --><!-- ═══════════════════════════════════════════════════════════════════════ --><div align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&color=0:3B82F6,100:0F172A&height=4&width=40%&section=header" />
  <br><br>  <p style="color: #9CA3AF; font-size: 14px;">
    <b style="color: #3B82F6;">Brand:</b> VEGA &amp; Logic &nbsp;|&nbsp;
    <b style="color: #3B82F6;">Copyright:</b> © 2015 - 2025
  </p>
  <p style="color: #6B7280; font-size: 12px;">
  </p>
</div><br><!-- Smooth Gradient Footer Background --><img src="https://capsule-render.vercel.app/api?type=waving&color=0:3B82F6,50:1E3A8A,100:0F172A&height=120&section=footer" width="100%" /></div>
