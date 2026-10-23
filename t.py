#!/usr/bin/env python3
"""
Fixture Analyzer Telegram Bot
Works on Termux + Render (free Web Service).
"""

import os
import io
import base64
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# ===================== CONFIG =====================
BOT_TOKEN = os.environ.get(
    "BOT_TOKEN", "7865136953:AAGS5R23Ycn1FCLC91cI6SpqkaolSvSlkg4"
)

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", "https://arsbcspracsrudeqeukw.supabase.co"
).rstrip("/")
SUPABASE_ANON_KEY = os.environ.get(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFyc2Jjc3ByYWNzcnVkZXFldWt3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTI1MjA4MzAsImV4cCI6MjEwODA5NjgzMH0.2-FBoa9_RJZXqoxfazZsYvlEWKqTJle5nbQ1P2ymYYY",
)

# Website login (email + password) — bot logs in and gets user JWT automatically
SUPABASE_EMAIL = os.environ.get(
    "SUPABASE_EMAIL", "admin@instantvisualhacker.com"
)
SUPABASE_PASSWORD = os.environ.get(
    "SUPABASE_PASSWORD", "Admin#InstantVisual2026!Hacker"
)
# Optional: paste a ready access_token here instead of email/password
SUPABASE_USER_JWT = os.environ.get("SUPABASE_USER_JWT", "")

FUNCTION_NAME = "analyze-fixtures"
MAX_IMAGE_MB = 8
# ==================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("fixture-bot")

_session_jwt = SUPABASE_USER_JWT.strip() or None


def login_supabase():
    global _session_jwt
    if _session_jwt:
        return _session_jwt
    if not SUPABASE_EMAIL or not SUPABASE_PASSWORD:
        return None

    url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
    }
    body = {"email": SUPABASE_EMAIL, "password": SUPABASE_PASSWORD}
    r = requests.post(url, json=body, headers=headers, timeout=30)
    data = r.json() if r.content else {}
    if r.status_code >= 400:
        log.error("Login failed %s: %s", r.status_code, data)
        return None
    token = data.get("access_token")
    if token:
        _session_jwt = token
        log.info("Logged in as %s", SUPABASE_EMAIL)
    return token


def auth_header():
    token = login_supabase() or SUPABASE_ANON_KEY
    return f"Bearer {token}"


def analyze_image(image_bytes, mime_type):
    url = f"{SUPABASE_URL}/functions/v1/{FUNCTION_NAME}"
    b64 = base64.b64encode(image_bytes).decode("ascii")
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": auth_header(),
        "Content-Type": "application/json",
    }
    payload = {"image_base64": b64, "mime_type": mime_type}
    r = requests.post(url, json=payload, headers=headers, timeout=90)
    try:
        data = r.json()
    except Exception:
        data = {"error": r.text[:500], "status_code": r.status_code}

    if r.status_code >= 400:
        return {
            "ok": False,
            "status_code": r.status_code,
            "error": data.get("error")
            or data.get("message")
            or data.get("msg")
            or str(data),
            "raw": data,
        }
    if isinstance(data, dict) and data.get("error"):
        return {"ok": False, "error": data["error"], "raw": data}
    return {"ok": True, "data": data}


def format_matches(data):
    if not isinstance(data, dict):
        return str(data)[:3500]

    matches = data.get("matches")
    if not matches or not isinstance(matches, list):
        import json

        return (
            "No matches array in response.\n```json\n"
            + json.dumps(data, indent=2)[:2800]
            + "\n```"
        )

    if len(matches) == 0:
        return (
            "No legible football fixtures detected. "
            "Please upload a clearer screenshot."
        )

    lines = ["*Fixture picks* (top 2)\n"]
    for i, m in enumerate(matches[:2], 1):
        if not isinstance(m, dict):
            lines.append(f"{i}. {m}")
            continue
        team_a = m.get("teamA") or m.get("homeTeam") or "Home Team"
        team_b = m.get("teamB") or m.get("awayTeam") or "Away Team"
        outcome = (
            m.get("suggestedOutcome")
            or m.get("outcome")
            or m.get("pick")
            or "Match Pick"
        )
        reason = (
            m.get("reason")
            or "Outcome based on visible fixture data in screenshot."
        )
        lines.append(f"*{i}. {team_a} vs {team_b}*")
        lines.append(f"   Pick: `{outcome}`")
        lines.append(f"   {reason}\n")

    return "\n".join(lines)[:3500]


async def start(update, context):
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("How it works", callback_data="help")],
            [InlineKeyboardButton("Status", callback_data="status")],
        ]
    )
    await update.message.reply_text(
        "⚽ *Fixture Analyzer Bot*\n\n"
        "Send a *fixture screenshot* (photo or image file).\n"
        "Same backend as your website:\n"
        "`analyze-fixtures` → `matches[]`\n\n"
        "Tips: clear image, 2 matches visible, JPG/PNG, max 8 MB.",
        parse_mode="Markdown",
        reply_markup=kb,
    )


async def help_cmd(update, context):
    await update.message.reply_text(
        "*Commands*\n"
        "/start — welcome\n"
        "/help — this\n"
        "/status — config check\n"
        "/relogin — refresh Supabase session\n\n"
        "Just send a photo to analyze.",
        parse_mode="Markdown",
    )


async def status_cmd(update, context):
    has_jwt = bool(_session_jwt or SUPABASE_USER_JWT)
    has_login = bool(SUPABASE_EMAIL and SUPABASE_PASSWORD)
    await update.message.reply_text(
        f"*Config*\n"
        f"URL: `{SUPABASE_URL}`\n"
        f"Function: `{FUNCTION_NAME}`\n"
        f"User JWT cached: {'yes' if has_jwt else 'no'}\n"
        f"Email/password login: {'yes' if has_login else 'no'}\n"
        f"Email: `{SUPABASE_EMAIL or 'not set'}`\n"
        f"Bot token: {'set' if BOT_TOKEN else 'MISSING'}",
        parse_mode="Markdown",
    )


async def relogin_cmd(update, context):
    global _session_jwt
    _session_jwt = None
    token = login_supabase()
    if token:
        await update.message.reply_text("✅ Logged in. New access_token cached.")
    else:
        await update.message.reply_text(
            "❌ Login failed. Check SUPABASE_EMAIL + SUPABASE_PASSWORD."
        )


async def on_button(update, context):
    q = update.callback_query
    await q.answer()
    if q.data == "help":
        await q.message.reply_text(
            "Flow (same as site JS):\n"
            "1. Image → base64\n"
            "2. POST functions/v1/analyze-fixtures\n"
            "   body: { image_base64, mime_type }\n"
            "3. Read data.matches[0..1]"
        )
    elif q.data == "status":
        await status_cmd(update, context)


async def handle_photo(update, context):
    msg = update.message
    await msg.chat.send_action("typing")

    if msg.photo:
        photo = msg.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        mime = "image/jpeg"
    elif msg.document and (msg.document.mime_type or "").startswith("image/"):
        file = await context.bot.get_file(msg.document.file_id)
        mime = msg.document.mime_type or "image/jpeg"
    else:
        await msg.reply_text("Send a *photo* or *image file*.", parse_mode="Markdown")
        return

    buf = io.BytesIO()
    await file.download_to_memory(buf)
    image_bytes = buf.getvalue()

    if len(image_bytes) > MAX_IMAGE_MB * 1024 * 1024:
        await msg.reply_text(f"Image too large (max {MAX_IMAGE_MB} MB).")
        return

    status = await msg.reply_text("🔍 Analyzing fixture…")

    try:
        result = analyze_image(image_bytes, mime)
    except requests.Timeout:
        await status.edit_text("Timeout. Try again.")
        return
    except Exception as e:
        log.exception("analyze failed")
        await status.edit_text(f"Request error: `{e}`", parse_mode="Markdown")
        return

    if not result.get("ok"):
        err = result.get("error") or "Unknown error"
        code = result.get("status_code")
        extra = f" (HTTP {code})" if code else ""
        hint = ""
        if code in (401, 403) or "JWT" in str(err) or "auth" in str(err).lower():
            hint = "\n\n_Auth issue — try /relogin or check email/password_"
        await status.edit_text(
            f"❌ Analyzer error{extra}:\n`{err}`{hint}",
            parse_mode="Markdown",
        )
        return

    text = format_matches(result.get("data"))
    await status.edit_text(f"✅ *Analysis*\n\n{text}", parse_mode="Markdown")


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        return


def start_health_server():
    port = int(os.environ.get("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    log.info("Health server on port %s", port)
    server.serve_forever()


def main():
    if not BOT_TOKEN:
        raise SystemExit("Set BOT_TOKEN.")

    if SUPABASE_EMAIL and SUPABASE_PASSWORD:
        tok = login_supabase()
        if not tok:
            log.warning("Startup login failed — analysis may need auth")

    t = threading.Thread(target=start_health_server, daemon=True)
    t.start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("relogin", relogin_cmd))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(
        MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_photo)
    )

    log.info("Fixture Analyzer bot starting…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
