# 🚀 Quick Start Guide

## Step 1: Get Bot Token
1. Open Telegram and search for `@BotFather`
2. Send `/start`
3. Send `/newbot`
4. Follow instructions
5. Copy the API token

## Step 2: Find Your Telegram ID
1. Open Telegram and search for `@userinfobot`
2. Send `/start`
3. You'll see your ID (e.g., 123456789)

## Step 3: Local Setup

### Windows/Mac/Linux
```bash
# 1. Install Python 3.10+
python --version

# 2. Clone repository
git clone https://github.com/yourusername/v2ray_bot.git
cd v2ray_bot

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file
cp .env.example .env

# 5. Edit .env
# BOT_TOKEN=your_token_here
# ADMIN_IDS=your_id_here

# 6. Run bot
python v2ray_bot.py
```

## Step 4: Test Locally

1. Open Telegram
2. Search for your bot (e.g., @MyV2RayBot)
3. Send `/start`
4. Click buttons to test

## Step 5: Deploy to Railway

### Prerequisites
- Railway account (free at railway.app)
- GitHub account
- Git installed

### Deployment Steps

```bash
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login
railway login

# 3. Create new project
railway init

# 4. Link GitHub repo
# Or upload files directly

# 5. Set environment variables
railway variables set BOT_TOKEN "your_token"
railway variables set ADMIN_IDS "your_id"

# 6. Deploy
railway up

# 7. View logs
railway logs
```

## Common Issues & Solutions

### "ModuleNotFoundError: No module named 'telegram'"
```bash
pip install python-telegram-bot
```

### "Invalid token"
- Double-check BOT_TOKEN
- No spaces or extra characters
- Get fresh token from @BotFather

### Bot not responding
- Check bot hasn't crashed: `python v2ray_bot.py` in terminal
- Verify token is correct
- Restart bot: Ctrl+C then run again

### Database locked error
- Only one instance should run
- Delete `bot_database.db` to reset
- Check permissions on file

## Commands Cheat Sheet

### User Commands
- `/start` - Open main menu

### Admin Commands (for you)
- `/start` - Open admin panel
- Click "📊 آمار ربات" - View statistics
- Click "💰 تراکنش ها" - Approve payments

## Plan Default Prices

| Plan | Price | Traffic | Duration |
|------|-------|---------|----------|
| 30 روزه | 50,000 تومان | 50 GB | 30 days |
| 60 روزه | 90,000 تومان | 120 GB | 60 days |
| 90 روزه | 120,000 تومان | 200 GB | 90 days |

**Edit in bot code to customize prices!**

## How to Get Money

1. **Wait for customers to request wallet top-up**
   - They'll submit amount
   - You'll see notification

2. **Approve in admin panel**
   - Click "💰 تراکنش ها"
   - Click "✅ تایید"
   - Money added to their wallet

3. **They buy plans**
   - Wallet charged automatically
   - You get notified of purchase

4. **Check revenue**
   - "📊 آمار ربات" shows total revenue

## Customize Plans

Open `v2ray_bot.py` and find this section:

```python
# Add default plans if not exist
if not db.get_all_plans():
    logger.info("Adding default plans...")
    db.add_plan('30 روزه', 50000, '50 GB', 30)
    db.add_plan('60 روزه', 90000, '120 GB', 60)
    db.add_plan('90 روزه', 120000, '200 GB', 90)
```

Change prices and traffic amounts, then restart bot.

Or use admin panel:
1. Click "📦 سرویس ها"
2. Click "➕ اضافه کردن پلن جدید"
3. Follow prompts

## Monitor Activity

### Check Logs
```bash
# Save logs while running
python v2ray_bot.py > bot.log 2>&1
```

### Check Database
```python
import sqlite3
conn = sqlite3.connect('bot_database.db')
cursor = conn.cursor()
cursor.execute('SELECT * FROM users')
for row in cursor.fetchall():
    print(row)
```

## Next Steps

1. ✅ Bot is running
2. ✅ Add at least 1 user (yourself)
3. ✅ Test purchase flow
4. ✅ Deploy to Railway
5. ✅ Share bot link with customers
6. ✅ Monitor admin panel daily
7. ✅ Approve payments promptly

## Support & Help

**Common Questions:**

Q: How do I add more plans?
A: Use admin panel → "📦 سرویس ها" → "➕ اضافه کردن"

Q: Where's my money?
A: Admin panel → "📊 آمار ربات" shows total revenue

Q: User bought but no config?
A: Check admin panel → "💰 تراکنش ها", may be pending approval

Q: Database keeps resetting?
A: Don't delete `bot_database.db`, only reset if absolutely necessary

Q: Can I edit v2ray config?
A: Edit `V2RayConfigGenerator` class in bot code

---

**Ready to earn! Start accepting payments now! 💰**
