require('dotenv').config();
const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const fs = require('fs');
const path = require('path');

// ─── Config ──────────────────────────────────────────────────────────────────
const OWNER_NUMBER  = process.env.OWNER_NUMBER  || '923456070954';
const RESTAURANT    = process.env.RESTAURANT_NAME || 'Flavour of Haven';
const MENU_DIR      = path.join(__dirname, 'menu');

// ─── Conversation states ──────────────────────────────────────────────────────
const STATE = {
  NEW:        'new',        // first message, send menu
  ORDERING:   'ordering',   // waiting for order text
  NAME:       'name',       // waiting for customer name
  DONE:       'done',       // order confirmed
};

// Active conversations: phone → { state, order, name, lastActive }
const sessions = new Map();

// ─── WhatsApp client ──────────────────────────────────────────────────────────
const client = new Client({
  authStrategy: new LocalAuth({ dataPath: './session' }),
  puppeteer: {
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-accelerated-2d-canvas',
      '--no-first-run',
      '--no-zygote',
      '--single-process',
      '--disable-gpu',
    ],
  },
});

// ─── Startup events ───────────────────────────────────────────────────────────
client.on('qr', (qr) => {
  console.log('\n📱 Scan this QR code with your WhatsApp:\n');
  qrcode.generate(qr, { small: true });
  console.log('\nWaiting for scan...\n');
});

client.on('authenticated', () => {
  console.log('✅ WhatsApp authenticated — session saved.');
});

client.on('auth_failure', (msg) => {
  console.error('❌ Authentication failed:', msg);
  process.exit(1);
});

client.on('ready', () => {
  console.log(`\n🚀 ${RESTAURANT} WhatsApp Bot is LIVE!\n`);
  console.log(`📞 Monitoring: ${OWNER_NUMBER}`);
  console.log(`🍔 Menu images in: ${MENU_DIR}\n`);
});

client.on('disconnected', (reason) => {
  console.warn('⚠️  Disconnected:', reason);
  process.exit(1); // Docker/PM2 will restart automatically
});

// ─── Message handler ──────────────────────────────────────────────────────────
client.on('message', async (msg) => {
  // Ignore group messages and status updates
  if (msg.isGroupMsg || msg.from === 'status@broadcast') return;

  // Ignore messages from the owner (prevent self-loop)
  const sender = msg.from; // e.g. "923001234567@c.us"
  const ownerJid = `${OWNER_NUMBER}@c.us`;
  if (sender === ownerJid) return;

  const chat = await msg.getChat();
  const customerPhone = sender.replace('@c.us', '');

  // Get or create session
  if (!sessions.has(sender)) {
    sessions.set(sender, { state: STATE.NEW, order: '', name: '' });
  }
  const session = sessions.get(sender);
  session.lastActive = Date.now();

  console.log(`[${customerPhone}] State: ${session.state} | Msg: "${msg.body}"`);

  // ── State machine ───────────────────────────────────────────────────────────
  switch (session.state) {

    // ── NEW: greet + send full menu ─────────────────────────────────────────
    case STATE.NEW: {
      await chat.sendStateTyping();
      await delay(1000);

      await msg.reply(
        `👋 *Welcome to ${RESTAURANT}!*\n\n` +
        `We're delighted to have you here. 😊\n` +
        `Here's our menu — take a look! 👇`
      );

      // Send all menu images from the /menu folder
      const menuFiles = getMenuImages();
      if (menuFiles.length === 0) {
        await client.sendMessage(sender,
          '📋 Our menu is being updated. Please call us:\n📞 *0345-6070954*'
        );
      } else {
        for (const file of menuFiles) {
          const media = MessageMedia.fromFilePath(file);
          await client.sendMessage(sender, media, {
            caption: menuFiles.indexOf(file) === menuFiles.length - 1
              ? '🍽️ That\'s our full menu!' : '',
          });
          await delay(600);
        }
      }

      await delay(800);
      await client.sendMessage(sender,
        `✍️ *What would you like to order?*\n\n` +
        `Just type your order below and I'll take care of it!\n` +
        `_(Example: 2 Zinger Burgers, 1 large fries, 2 Pepsi)_`
      );

      session.state = STATE.ORDERING;
      break;
    }

    // ── ORDERING: receive order text ────────────────────────────────────────
    case STATE.ORDERING: {
      const orderText = msg.body.trim();

      if (orderText.length < 3) {
        await msg.reply(
          '🤔 That seems too short. Please type your full order.\n' +
          '_(Example: 1 Burger, 1 fries, 1 Pepsi)_'
        );
        break;
      }

      session.order = orderText;

      await chat.sendStateTyping();
      await delay(800);

      await msg.reply(
        `✅ *Got it! Your order:*\n_"${orderText}"_\n\n` +
        `May I have your *name* please? 😊`
      );

      session.state = STATE.NAME;
      break;
    }

    // ── NAME: receive name, confirm, notify owner ───────────────────────────
    case STATE.NAME: {
      const name = msg.body.trim();

      if (name.length < 2) {
        await msg.reply('Please enter your name so we can confirm your order. 😊');
        break;
      }

      session.name = name;

      await chat.sendStateTyping();
      await delay(1000);

      // Confirm to customer
      await msg.reply(
        `🎉 *Order Confirmed!*\n\n` +
        `👤 Name: *${name}*\n` +
        `🍔 Order: _${session.order}_\n\n` +
        `Thank you! We'll prepare your order shortly. 🙏\n` +
        `For queries call: *0345-6070954*`
      );

      // Notify owner
      const ownerMsg =
        `🔔 *NEW ORDER — ${RESTAURANT}*\n` +
        `─────────────────────\n` +
        `👤 Customer: *${name}*\n` +
        `📞 Phone: *${customerPhone}*\n` +
        `🍔 Order: _${session.order}_\n` +
        `🕐 Time: ${new Date().toLocaleString('en-PK', { timeZone: 'Asia/Karachi' })}\n` +
        `─────────────────────`;

      await client.sendMessage(ownerJid, ownerMsg);
      console.log(`✅ Order from ${name} (${customerPhone}) forwarded to owner.`);

      session.state = STATE.DONE;
      break;
    }

    // ── DONE: handle follow-up messages ─────────────────────────────────────
    case STATE.DONE: {
      const text = msg.body.toLowerCase().trim();

      if (text.includes('order') || text.includes('menu') || text.includes('again') || text.includes('new')) {
        // Reset for a new order
        sessions.set(sender, { state: STATE.NEW, order: '', name: '' });
        // Re-trigger by processing again
        await client.sendMessage(sender,
          `Sure! Let me show you the menu again. 😊`
        );
        await delay(500);
        sessions.get(sender).state = STATE.NEW;
        // Manually trigger new state
        await sendMenu(sender, chat);
        break;
      }

      await msg.reply(
        `😊 Your order has been placed!\n\n` +
        `If you'd like to place a *new order*, just type *"new order"*.\n` +
        `For help call: *0345-6070954*`
      );
      break;
    }
  }

  // Clean up old sessions (older than 2 hours)
  cleanSessions();
});

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getMenuImages() {
  if (!fs.existsSync(MENU_DIR)) return [];
  const allowed = ['.jpg', '.jpeg', '.png', '.webp'];
  return fs
    .readdirSync(MENU_DIR)
    .filter(f => allowed.includes(path.extname(f).toLowerCase()))
    .sort()                          // alphabetical order
    .map(f => path.join(MENU_DIR, f));
}

async function sendMenu(sender, chat) {
  const menuFiles = getMenuImages();
  if (menuFiles.length === 0) {
    await client.sendMessage(sender, '📋 Menu coming soon! Call: *0345-6070954*');
  } else {
    for (const file of menuFiles) {
      const media = MessageMedia.fromFilePath(file);
      await client.sendMessage(sender, media);
      await delay(600);
    }
  }
  await client.sendMessage(sender,
    `✍️ *What would you like to order?*\nJust type it below! 👇`
  );
  sessions.get(sender).state = STATE.ORDERING;
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function cleanSessions() {
  const TWO_HOURS = 2 * 60 * 60 * 1000;
  const now = Date.now();
  for (const [key, val] of sessions.entries()) {
    if (now - (val.lastActive || 0) > TWO_HOURS) {
      sessions.delete(key);
    }
  }
}

// ─── Start ────────────────────────────────────────────────────────────────────
client.initialize();
