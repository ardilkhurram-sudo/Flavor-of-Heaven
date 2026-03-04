"""
Flavour of Haven — WhatsApp Bot
Uses Playwright + persistent Chromium session (same approach as hackathon watcher).

Usage:
  First time:  python bot.py --login    ← opens browser, scan QR code once
  After that:  python bot.py            ← runs silently in background
"""

import os
import sys
import time
import argparse
import urllib.parse
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

load_dotenv()

# ─── Config ──────────────────────────────────────────────────────────────────
OWNER_NUMBER  = os.getenv("OWNER_NUMBER",    "923456070954")
RESTAURANT    = os.getenv("RESTAURANT_NAME", "Flavour of Haven")
SESSION_DIR   = Path(__file__).parent / "sessions" / "whatsapp"
MENU_DIR      = Path(__file__).parent.parent / "whatsapp-bot" / "menu"

# ─── Conversation states ──────────────────────────────────────────────────────
NEW      = "new"
ORDERING = "ordering"
NAME     = "name"
DONE     = "done"

# Active sessions: chat_name → { state, order, name, last_msg }
sessions = {}


# ─── Login (run once to scan QR) ─────────────────────────────────────────────
def login():
    print("\n📱 Opening WhatsApp Web — scan the QR code with your phone...\n")
    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(SESSION_DIR),
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=["--no-sandbox"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://web.whatsapp.com")

        print("Waiting for you to scan the QR code...")
        print("Once WhatsApp loads fully, press Enter here.\n")
        input("Press Enter after you're logged in ▶ ")

        context.close()
        print(f"\n✅ Session saved to: {SESSION_DIR}")
        print("Now run:  python bot.py\n")


# ─── Helpers ──────────────────────────────────────────────────────────────────
def get_menu_images():
    if not MENU_DIR.exists():
        return []
    return sorted(
        f for f in MENU_DIR.iterdir()
        if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )


def send_text(page, text):
    """Type and send a text message in the currently open chat."""
    box = page.locator('[data-testid="conversation-compose-box-input"]')
    box.click()
    # Use clipboard paste to preserve emoji & special chars
    page.evaluate(
        f"""
        const box = document.querySelector('[data-testid="conversation-compose-box-input"]');
        box.focus();
        document.execCommand('insertText', false, {repr(text)});
        """)
    page.keyboard.press("Enter")
    time.sleep(0.6)


def send_image(page, image_path):
    """Attach and send a single image in the currently open chat."""
    try:
        # Click paperclip
        page.locator('[data-testid="attach-menu-icon"]').click()
        time.sleep(0.5)

        # Upload via file chooser
        with page.expect_file_chooser(timeout=6000) as fc_info:
            page.locator('[data-testid="mi-attach-media"]').click()
        fc_info.value.set_files(str(image_path))
        time.sleep(1.5)

        # Send
        send_btn = page.locator('[data-testid="send-image-button"]')
        if send_btn.count():
            send_btn.click()
        else:
            page.keyboard.press("Enter")
        time.sleep(1)
        return True
    except Exception as e:
        print(f"  ⚠️  Image send failed ({image_path.name}): {e}")
        return False


def notify_owner(context, session, chat_name):
    """Open a new tab, send order details to owner, then close the tab."""
    now = time.strftime("%d/%m/%Y %I:%M %p")
    msg = (
        f"🔔 *NEW ORDER — {RESTAURANT}*\n"
        f"─────────────────────\n"
        f"👤 Customer: *{session['name']}*\n"
        f"💬 Chat: *{chat_name}*\n"
        f"🍔 Order: _{session['order']}_\n"
        f"🕐 Time: {now}\n"
        f"─────────────────────"
    )
    encoded = urllib.parse.quote(msg)
    tab = context.new_page()
    try:
        tab.goto(f"https://web.whatsapp.com/send?phone={OWNER_NUMBER}&text={encoded}")
        tab.wait_for_selector(
            '[data-testid="conversation-compose-box-input"]',
            timeout=20000,
        )
        time.sleep(1)
        tab.keyboard.press("Enter")
        time.sleep(2)
        print(f"  ✅ Owner notified for order from {session['name']}")
    except Exception as e:
        print(f"  ⚠️  Could not notify owner: {e}")
    finally:
        tab.close()


# ─── Message extraction ───────────────────────────────────────────────────────
def get_latest_incoming(page):
    """Return text of the latest incoming message in the open chat."""
    return page.evaluate("""
        () => {
            const msgs = [...document.querySelectorAll('.message-in')];
            if (!msgs.length) return null;
            const last = msgs[msgs.length - 1];
            const spans = [...last.querySelectorAll('span[dir="ltr"]')];
            for (const s of spans) {
                const t = s.innerText.trim();
                if (t && !/^\\d{1,2}:\\d{2}\\s*(AM|PM)$/i.test(t)) return t;
            }
            return null;
        }
    """)


def get_unread_chats(page):
    """Return list of {index, name} for chats with unread badges."""
    try:
        page.wait_for_selector('[data-testid="chat-list"]', timeout=8000)
    except PWTimeoutError:
        return []

    return page.evaluate("""
        () => {
            const results = [];
            const items = document.querySelectorAll('[data-testid="cell-frame-container"]');
            items.forEach((item, idx) => {
                const badge = item.querySelector(
                    '[data-testid="icon-unread-count"], [aria-label*="unread"]'
                );
                if (!badge) return;
                const nameEl = item.querySelector('[data-testid="cell-frame-title"]');
                results.push({ index: idx, name: nameEl?.textContent || 'Unknown' });
            });
            return results;
        }
    """) or []


# ─── Conversation handler ─────────────────────────────────────────────────────
def handle_chat(page, context, chat_name, msg):
    # Init session
    if chat_name not in sessions:
        sessions[chat_name] = {
            "state": NEW, "order": "", "name": "", "last_msg": ""
        }
    s = sessions[chat_name]

    # Deduplicate — skip if same message as last time
    if msg == s["last_msg"]:
        return
    s["last_msg"] = msg

    print(f"  [{chat_name}] state={s['state']} msg='{msg}'")

    # ── NEW ───────────────────────────────────────────────────────────────────
    if s["state"] == NEW:
        send_text(
            page,
            f"👋 *Welcome to {RESTAURANT}!*\n\n"
            f"We're delighted to have you here. 😊\n"
            f"Here's our menu — take a look! 👇",
        )
        images = get_menu_images()
        if not images:
            send_text(page, "📋 Menu coming soon! Call: *0345-6070954*")
        else:
            for img in images:
                send_image(page, img)
        time.sleep(0.5)
        send_text(
            page,
            "✍️ *What would you like to order?*\n\n"
            "Just type it below! 👇\n"
            "_(Example: 2 Zinger Burgers, 1 fries, 2 Pepsi)_",
        )
        s["state"] = ORDERING

    # ── ORDERING ──────────────────────────────────────────────────────────────
    elif s["state"] == ORDERING:
        if len(msg) < 3:
            send_text(
                page,
                "🤔 Please type your full order.\n"
                "_(Example: 1 Burger, 1 fries, 1 Pepsi)_",
            )
            return
        s["order"] = msg
        send_text(
            page,
            f"✅ *Got it! Your order:*\n_{msg}_\n\n"
            f"May I have your *name* please? 😊",
        )
        s["state"] = NAME

    # ── NAME ──────────────────────────────────────────────────────────────────
    elif s["state"] == NAME:
        if len(msg) < 2:
            send_text(page, "Please enter your name to confirm the order. 😊")
            return
        s["name"] = msg
        send_text(
            page,
            f"🎉 *Order Confirmed!*\n\n"
            f"👤 Name: *{msg}*\n"
            f"🍔 Order: _{s['order']}_\n\n"
            f"Thank you! We'll prepare your order shortly. 🙏\n"
            f"For queries call: *0345-6070954*",
        )
        notify_owner(context, s, chat_name)
        s["state"] = DONE

    # ── DONE ──────────────────────────────────────────────────────────────────
    elif s["state"] == DONE:
        if any(kw in msg.lower() for kw in ["order", "menu", "again", "new"]):
            sessions[chat_name] = {
                "state": NEW, "order": "", "name": "", "last_msg": ""
            }
            send_text(page, "Sure! Let me show you the menu again. 😊")
            time.sleep(0.5)
            handle_chat(page, context, chat_name, msg)
        else:
            send_text(
                page,
                "😊 Your order has been placed!\n\n"
                "To place a *new order* type: *new order*\n"
                "For help call: *0345-6070954*",
            )


# ─── Main bot loop ────────────────────────────────────────────────────────────
def run_bot():
    print(f"\n🚀 Starting {RESTAURANT} WhatsApp Bot (headless)...\n")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(SESSION_DIR),
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--single-process",
                "--disable-gpu",
            ],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://web.whatsapp.com")

        # Check if QR code is shown (not logged in)
        try:
            page.wait_for_selector(
                'canvas[aria-label*="QR"], [data-testid="qrcode"]',
                timeout=8000,
            )
            print("❌ Not logged in! Run first:  python bot.py --login\n")
            context.close()
            sys.exit(1)
        except PWTimeoutError:
            pass  # Already logged in ✅

        # Wait for chat list
        print("⏳ Loading WhatsApp Web...")
        try:
            page.wait_for_selector('[data-testid="chat-list"]', timeout=30000)
        except PWTimeoutError:
            print("❌ WhatsApp did not load. Check your internet.")
            context.close()
            sys.exit(1)

        print(f"✅ Bot is LIVE — monitoring {RESTAURANT} WhatsApp\n")

        # ── Polling loop ──────────────────────────────────────────────────────
        while True:
            try:
                # Refresh to main list
                page.goto("https://web.whatsapp.com")
                page.wait_for_selector('[data-testid="chat-list"]', timeout=10000)
                time.sleep(2)

                unread = get_unread_chats(page)

                for chat in unread:
                    chat_name = chat["name"]
                    print(f"📨 Unread message from: {chat_name}")

                    # Open the chat
                    try:
                        items = page.locator('[data-testid="cell-frame-container"]')
                        items.nth(chat["index"]).click()
                        time.sleep(1.5)
                    except Exception:
                        continue

                    # Get latest incoming message
                    msg = get_latest_incoming(page)
                    if msg:
                        handle_chat(page, context, chat_name, msg)

                    time.sleep(1)

                time.sleep(5)  # Poll every 5 seconds

            except KeyboardInterrupt:
                print("\n🛑 Bot stopped by user.")
                break
            except Exception as e:
                print(f"⚠️  Error: {e} — retrying in 5s...")
                time.sleep(5)

        context.close()


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=f"{RESTAURANT} WhatsApp Bot")
    parser.add_argument(
        "--login",
        action="store_true",
        help="Open browser to scan WhatsApp QR code (run once)",
    )
    args = parser.parse_args()

    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    if args.login:
        login()
    else:
        run_bot()
