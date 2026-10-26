#!/usr/bin/env python3
"""
ScoreX Correct Score Bot
Live active correct scores from sh.appmedo.com (Supabase matches table).
Render Web Service compatible: binds to $PORT for health checks.
"""

import os
import logging
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# ============== CONFIG ==============
TELEGRAM_TOKEN = os.getenv(
    "TELEGRAM_TOKEN",
    "8802264885:AAEUs7I4FMxbPUir-M7yBCFtiNxjbBS6at4",
)
ADMIN_IDS = [7941824028]

SUPABASE_URL = "https://xmlwakxtegkjethxwgvq.supabase.co"
SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhtbHdha3h0ZWdramV0aHh3Z3ZxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTI5Njg1NzEsImV4cCI6MjEwODU0NDU3MX0."
    "wmATgtTyjHIPUAf15jsPC5jQW0IUPPrr-1L5bo-dKUA"
)
SITE_NAME = "ScoreX"
SITE_URL = "https://app-fchbdfn9a8sh.appmedo.com/"
PORT = int(os.getenv("PORT", "10000"))
# ====================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("scorex_bot")


def supabase_headers():
    return {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
    }


def fetch_active_matches():
    """Active / upcoming published matches (not finished)."""
    url = f"{SUPABASE_URL}/rest/v1/matches"
    params = {
        "select": "*",
        "is_published": "eq.true",
        "status": "neq.finished",
        "order": "match_date.asc,match_time.asc",
    }
    r = requests.get(url, headers=supabase_headers(), params=params, timeout=25)
    r.raise_for_status()
    return r.json() if r.content else []


def fetch_recent_matches(limit: int = 20):
    """Recent published matches including finished."""
    url = f"{SUPABASE_URL}/rest/v1/matches"
    params = {
        "select": "*",
        "is_published": "eq.true",
        "order": "created_at.desc",
        "limit": str(limit),
    }
    r = requests.get(url, headers=supabase_headers(), params=params, timeout=25)
    r.raise_for_status()
    return r.json() if r.content else []


def main_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔥 Active Correct Scores", callback_data="active"),
            ],
            [
                InlineKeyboardButton("📋 Recent / Results", callback_data="all"),
                InlineKeyboardButton("🔄 Refresh", callback_data="active"),
            ],
            [
                InlineKeyboardButton("🌐 Open Website", url=SITE_URL),
                InlineKeyboardButton("ℹ Help", callback_data="help"),
            ],
        ]
    )


def format_active_match(m: dict) -> str:
    home = (m.get("home_team") or "?").strip()
    away = (m.get("away_team") or "?").strip()
    league = (m.get("league") or "").strip()
    time_ = (m.get("match_time") or "").strip()
    date_ = (m.get("match_date") or "").strip()
    score = (m.get("predicted_score") or "—").strip()
    odds = m.get("odds") or "—"
    conf = m.get("confidence") or "—"
    price = m.get("price_ghs")
    category = (m.get("category") or "").strip()
    status = (m.get("status") or "upcoming").strip()

    lines = [
        f"🏟 *{home} vs {away}*",
        f"📌 {league}" if league else None,
        f"🕐 {date_} · {time_}" if (date_ or time_) else None,
        f"🏷 {category}" if category else None,
        f"⏱ Status: `{status}`",
        "",
        f"🎯 *Correct Score: {score}*",
        f"📈 Odds: `{odds}`  ·  Confidence: `{conf}`",
    ]
    if price is not None:
        lines.append(f"💰 Site price: *{price} GHS*")
    return "\n".join(x for x in lines if x is not None)


def format_result_match(m: dict) -> str:
    home = (m.get("home_team") or "?").strip()
    away = (m.get("away_team") or "?").strip()
    league = (m.get("league") or "").strip()
    time_ = (m.get("match_time") or "").strip()
    date_ = (m.get("match_date") or "").strip()
    predicted = (m.get("predicted_score") or "—").strip()
    final = m.get("final_score")
    settlement = m.get("settlement")
    status = (m.get("status") or "").strip()
    won = m.get("is_verified_winning")

    badge = "✅ WON" if (settlement == "WON" or won) else ("❌ LOST" if settlement == "LOST" else status or "—")

    lines = [
        f"🏟 *{home} vs {away}*",
        f"📌 {league}" if league else None,
        f"🕐 {date_} · {time_}" if (date_ or time_) else None,
        f"🎯 Predicted: *{predicted}*",
        f"🏁 Final: *{final}*" if final else "🏁 Final: pending",
        f"📊 {badge}",
    ]
    return "\n".join(x for x in lines if x is not None)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"⚡ *{SITE_NAME} Correct Score Bot*\n\n"
        f"Live tips from the site database\n"
        f"🌐 {SITE_URL}\n\n"
        "Tap *Active Correct Scores* to see bets the site posted that are still active."
    )
    if update.message:
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=main_keyboard(), disable_web_page_preview=True
        )


async def send_active(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q:
        await q.answer("Loading active scores…")

    try:
        matches = fetch_active_matches()
    except Exception as e:
        log.exception("fetch active failed")
        msg = f"❌ Failed to load active matches:\n`{e}`"
        if q:
            await q.edit_message_text(msg, parse_mode="Markdown", reply_markup=main_keyboard())
        elif update.message:
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_keyboard())
        return

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    if not matches:
        text = (
            f"📭 *No active correct scores right now*\n\n"
            f"Checked: `{now}`\n"
            "Site has no upcoming tips at the moment."
        )
    else:
        blocks = [format_active_match(m) for m in matches]
        text = (
            f"🔥 *Active Correct Scores* ({len(matches)})\n"
            f"🕐 Checked: `{now}`\n"
            f"🌐 {SITE_URL}\n\n"
            + "\n\n——————————\n\n".join(blocks)
        )

    if len(text) > 4000:
        text = text[:3900] + "\n\n…truncated"

    if q:
        await q.edit_message_text(
            text, parse_mode="Markdown", reply_markup=main_keyboard(), disable_web_page_preview=True
        )
    elif update.message:
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=main_keyboard(), disable_web_page_preview=True
        )


async def send_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q:
        await q.answer("Loading recent…")

    try:
        matches = fetch_recent_matches()
    except Exception as e:
        log.exception("fetch all failed")
        msg = f"❌ Failed to load matches:\n`{e}`"
        if q:
            await q.edit_message_text(msg, parse_mode="Markdown", reply_markup=main_keyboard())
        elif update.message:
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_keyboard())
        return

    if not matches:
        text = "📭 No published matches found."
    else:
        blocks = [format_result_match(m) for m in matches]
        text = (
            f"📋 *Recent Published Matches* ({len(matches)})\n\n"
            + "\n\n——————————\n\n".join(blocks)
        )

    if len(text) > 4000:
        text = text[:3900] + "\n\n…truncated"

    if q:
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=main_keyboard())
    elif update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"ℹ *{SITE_NAME} Bot Help*\n\n"
        "• *Active Correct Scores* — tips still active (status ≠ finished)\n"
        "• *Recent / Results* — latest published tips + final scores\n"
        "• Data is live from the site database\n\n"
        "Commands:\n"
        "/start — menu\n"
        "/active — active correct scores\n"
        "/all — recent matches\n"
    )
    q = update.callback_query
    if q:
        await q.answer()
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=main_keyboard())
    elif update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data if update.callback_query else ""
    if data == "active":
        await send_active(update, context)
    elif data == "all":
        await send_all(update, context)
    elif data == "help":
        await help_cmd(update, context)
    else:
        await update.callback_query.answer()


# ---- Render health check (Web Service) ----
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    log.info("Health server listening on port %s", PORT)
    server.serve_forever()


def main():
    # Bind $PORT so Render Web Service health check passes
    t = threading.Thread(target=start_health_server, daemon=True)
    t.start()

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("active", send_active))
    app.add_handler(CommandHandler("all", send_all))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(on_callback))
    log.info("ScoreX bot starting (polling)…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
