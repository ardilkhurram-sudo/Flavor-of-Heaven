# Flavour of Haven — WhatsApp Bot

Automated WhatsApp chatbot that greets customers, sends the menu, takes orders, and notifies the owner.

## Conversation Flow

```
Customer → any message
  Bot → Welcome + sends all menu images
  Bot → "What would you like to order?"
Customer → types order
  Bot → Confirms order, asks for name
Customer → types name
  Bot → "Order Confirmed!" message to customer
  Bot → Sends order details to owner's WhatsApp
```

---

## Setup

### 1. Add your menu images
Drop your menu images (JPG/PNG) into the `menu/` folder.
Name them in order: `menu1.jpg`, `menu2.jpg`, etc.

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env with your owner WhatsApp number
```

### 3. Run locally (for testing)
```bash
npm install
npm start
# Scan the QR code with your WhatsApp
```

---

## Deploy to a Cloud Server (VPS)

### Requirements
- Ubuntu 20.04+ VPS (DigitalOcean, Linode, Hetzner, etc.)
- Docker + Docker Compose installed

### Steps

```bash
# 1. SSH into your server
ssh root@YOUR_SERVER_IP

# 2. Install Docker
curl -fsSL https://get.docker.com | sh

# 3. Clone / upload the bot files
git clone https://github.com/ardilkhurram-sudo/Flavor-of-Heaven.git
cd "Flavor-of-Heaven/whatsapp-bot"

# 4. Add menu images to menu/ folder

# 5. Start the bot
docker compose up -d

# 6. Scan QR code (first time only)
docker compose logs -f
# Scan the QR code shown in the terminal with your WhatsApp

# Session is saved — QR scan is only needed ONCE
```

### Useful commands
```bash
docker compose logs -f          # View live logs
docker compose restart          # Restart bot
docker compose down             # Stop bot
docker compose up -d --build    # Rebuild after changes
```

---

## Free Cloud Hosting Option (Railway)

1. Go to https://railway.app
2. Create new project → Deploy from GitHub repo
3. Point to the `whatsapp-bot` folder
4. Add environment variables in Railway dashboard
5. Upload menu images to the `menu/` folder
