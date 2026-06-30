"""
Flavour of Haven — WhatsApp Bot
Uses Playwright + persistent Chromium session.

Usage:
  First time:  python bot.py --login         ← opens browser, scan QR once
  Normal run:  python bot.py                 ← headless background bot
  Debug run:   python bot.py --debug         ← visible browser + extra logs
"""

import os
import sys
import time
import argparse
import urllib.parse
from pathlib import Path
import pyperclip
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

load_dotenv()

# ─── Config ──────────────────────────────────────────────────────────────────
OWNER_NUMBER = os.getenv("OWNER_NUMBER",    "923456070954")
RESTAURANT   = os.getenv("RESTAURANT_NAME", "Flavour of Haven")
SESSION_DIR  = Path(__file__).parent / "sessions" / "whatsapp"
MENU_DIR     = Path(__file__).parent.parent / "whatsapp-bot" / "menu"

DEBUG = False  # set via --debug flag

# ─── Conversation states ──────────────────────────────────────────────────────
NEW      = "new"
ORDERING = "ordering"
NAME     = "name"
DONE     = "done"

sessions = {}  # chat_name → { state, order, name, last_msg }


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


# ─── Login ────────────────────────────────────────────────────────────────────
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
        print("Scan the QR code in the browser window.")
        print("Once WhatsApp loads fully, press Enter here.\n")
        input("Press Enter after you're logged in ▶ ")
        context.close()
    print(f"\n✅ Session saved to: {SESSION_DIR}")
    print("Now run:  python bot.py\n")


# ─── Helpers ──────────────────────────────────────────────────────────────────
def get_menu_images():
    if not MENU_DIR.exists():
        log(f"⚠️  Menu folder not found: {MENU_DIR}")
        return []
    imgs = sorted(
        f for f in MENU_DIR.iterdir()
        if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )
    if DEBUG:
        log(f"  Menu images found: {[i.name for i in imgs]}")
    return imgs


def send_text(page, text):
    """Send a text message using clipboard paste (most reliable method)."""
    try:
        pyperclip.copy(text)
        box = page.locator('[data-testid="conversation-compose-box-input"]')
        box.wait_for(timeout=5000)
        box.click()
        time.sleep(0.2)
        page.keyboard.press("Control+v")
        time.sleep(0.3)
        page.keyboard.press("Enter")
        time.sleep(0.8)
        if DEBUG:
            log(f"  ✉️  Sent: {text[:60]}...")
    except Exception as e:
        log(f"  ❌ send_text failed: {e}")


def send_image(page, image_path):
    """Attach and send an image in the current chat."""
    try:
        page.locator('[data-testid="attach-menu-icon"]').click(timeout=5000)
        time.sleep(0.6)

        with page.expect_file_chooser(timeout=6000) as fc_info:
            page.locator('[data-testid="mi-attach-media"]').click()
        fc_info.value.set_files(str(image_path))
        time.sleep(2)

        # Try the send button, fall back to Enter
        send_btn = page.locator('[data-testid="send-image-button"]')
        if send_btn.count():
            send_btn.click()
        else:
            page.keyboard.press("Enter")
        time.sleep(1.5)
        if DEBUG:
            log(f"  🖼️  Sent image: {image_path.name}")
        return True
    except Exception as e:
        log(f"  ⚠️  Image send failed ({image_path.name}): {e}")
        return False


def notify_owner(context, session, chat_name):
    """Send new order alert to owner in a separate tab."""
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
            '[data-testid="conversation-compose-box-input"]', timeout=20000
        )
        time.sleep(1.5)
        tab.keyboard.press("Enter")
        time.sleep(2)
        log(f"  ✅ Owner notified — order from {session['name']}")
    except Exception as e:
        log(f"  ⚠️  Owner notification failed: {e}")
    finally:
        tab.close()


# ─── Message / chat extraction ────────────────────────────────────────────────
def get_latest_incoming(page):
    """Extract text of the latest incoming message in the open chat."""
    result = page.evaluate("""
        () => {
            // Try multiple selectors for incoming messages
            const selectors = [
                '.message-in span[dir="ltr"]',
                '[data-testid="msg-container"] span[dir="ltr"]',
                'div.copyable-text span[dir="ltr"]',
            ];
            for (const sel of selectors) {
                const spans = [...document.querySelectorAll(sel)];
                // Walk backwards to find last real text
                for (let i = spans.length - 1; i >= 0; i--) {
                    const t = spans[i].innerText.trim();
                    if (t && t.length > 0 && !/^\\d{1,2}:\\d{2}(\\s*(AM|PM))?$/.test(t)) {
                        return t;
                    }
                }
            }
            return null;
        }
    """)
    if DEBUG:
        log(f"  Latest incoming msg: {result!r}")
    return result


def get_unread_chats(page):
    """Return [{index, name}] for chats showing unread badge."""
    try:
        page.wait_for_selector('[data-testid="chat-list"]', timeout=8000)
    except PWTimeoutError:
        log("  ⚠️  Chat list not found")
        return []

    result = page.evaluate("""
        () => {
            const results = [];
            // Multiple selectors for chat list items
            const items = document.querySelectorAll(
                '[data-testid="cell-frame-container"], [role="listitem"]'
            );
            items.forEach((item, idx) => {
                const badge = item.querySelector(
                    '[data-testid="icon-unread-count"], ' +
                    '[aria-label*="unread"], ' +
                    'span[data-testid="unread-count"], ' +
                    'span[aria-label*="unread"]'
                );
                if (!badge) return;
                const nameEl = item.querySelector(
                    '[data-testid="cell-frame-title"], ' +
                    'span[dir="auto"]'
                );
                results.push({
                    index: idx,
                    name: nameEl?.textContent?.trim() || 'Unknown',
                    badge_text: badge.textContent?.trim(),
                });
            });
            return results;
        }
    """) or []

    if DEBUG:
        log(f"  Unread chats found: {result}")
    return result


# ─── Conversation handler ─────────────────────────────────────────────────────
def handle_chat(page, context, chat_name, msg):
    if chat_name not in sessions:
        sessions[chat_name] = {"state": NEW, "order": "", "name": "", "last_msg": ""}
    s = sessions[chat_name]

    # Skip if same message as last processed
    if msg == s["last_msg"]:
        if DEBUG:
            log(f"  Skipping duplicate msg from {chat_name}")
        return
    s["last_msg"] = msg

    log(f"  [{chat_name}] state={s['state']} | msg='{msg}'")

    if s["state"] == NEW:
        send_text(
            page,
            f"👋 *Welcome to {RESTAURANT}!*\n\n"
            "We're delighted to have you here. 😊\n"
            "Here's our menu — take a look! 👇",
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
            "Just type your order below! 👇\n"
            "_(Example: 2 Zinger Burgers, 1 fries, 2 Pepsi)_",
        )
        s["state"] = ORDERING

    elif s["state"] == ORDERING:
        if len(msg.strip()) < 3:
            send_text(
                page,
                "🤔 Please type your full order.\n"
                "_(Example: 1 Burger, 1 fries, 1 Pepsi)_",
            )
            return
        s["order"] = msg.strip()
        send_text(
            page,
            f"✅ *Got it! Your order:*\n_{s['order']}_\n\n"
            "May I have your *name* please? 😊",
        )
        s["state"] = NAME

    elif s["state"] == NAME:
        if len(msg.strip()) < 2:
            send_text(page, "Please enter your name to confirm the order. 😊")
            return
        s["name"] = msg.strip()
        send_text(
            page,
            f"🎉 *Order Confirmed!*\n\n"
            f"👤 Name: *{s['name']}*\n"
            f"🍔 Order: _{s['order']}_\n\n"
            "Thank you! We'll prepare your order shortly. 🙏\n"
            "For queries call: *0345-6070954*",
        )
        notify_owner(context, s, chat_name)
        s["state"] = DONE

    elif s["state"] == DONE:
        if any(kw in msg.lower() for kw in ["order", "menu", "again", "new"]):
            sessions[chat_name] = {"state": NEW, "order": "", "name": "", "last_msg": ""}
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
def run_bot(headless=True):
    log(f"🚀 Starting {RESTAURANT} WhatsApp Bot {'(debug/visible)' if not headless else '(headless)'}...")
    log(f"   Menu folder : {MENU_DIR}")
    log(f"   Session dir : {SESSION_DIR}\n")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(SESSION_DIR),
            headless=headless,
            viewport={"width": 1280, "height": 800},
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

        # Check login
        try:
            page.wait_for_selector(
                'canvas[aria-label*="QR"], [data-testid="qrcode"]', timeout=8000
            )
            log("❌ Not logged in! Run:  python bot.py --login")
            context.close()
            sys.exit(1)
        except PWTimeoutError:
            pass

        log("⏳ Loading WhatsApp Web...")
        try:
            page.wait_for_selector('[data-testid="chat-list"]', timeout=30000)
        except PWTimeoutError:
            log("❌ Chat list did not load. Check internet connection.")
            context.close()
            sys.exit(1)

        log(f"✅ Bot is LIVE — monitoring {RESTAURANT} WhatsApp\n")

        while True:
            try:
                page.goto("https://web.whatsapp.com")
                page.wait_for_selector('[data-testid="chat-list"]', timeout=10000)
                time.sleep(2)

                unread = get_unread_chats(page)

                if not unread:
                    if DEBUG:
                        log("  No unread chats.")
                else:
                    for chat in unread:
                        chat_name = chat["name"]
                        log(f"📨 Unread from: {chat_name} (badge: {chat.get('badge_text')})")

                        try:
                            items = page.locator(
                                '[data-testid="cell-frame-container"], [role="listitem"]'
                            )
                            items.nth(chat["index"]).click()
                            time.sleep(2)
                        except Exception as e:
                            log(f"  ⚠️  Could not open chat: {e}")
                            continue

                        msg = get_latest_incoming(page)
                        if msg:
                            handle_chat(page, context, chat_name, msg)
                        else:
                            log(f"  ⚠️  Could not read message from {chat_name}")

                        time.sleep(1)

                time.sleep(4)

            except KeyboardInterrupt:
                log("\n🛑 Bot stopped.")
                break
            except Exception as e:
                log(f"⚠️  Error: {e} — retrying in 5s...")
                time.sleep(5)

        context.close()


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=f"{RESTAURANT} WhatsApp Bot")
    parser.add_argument("--login", action="store_true", help="Scan QR code (run once)")
    parser.add_argument("--debug", action="store_true", help="Visible browser + verbose logs")
    args = parser.parse_args()

    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    if args.login:
        login()
    elif args.debug:
        DEBUG = True
        run_bot(headless=False)
    else:
        run_bot(headless=True)
