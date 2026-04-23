# V2Ray Config Telegram Bot - Complete Documentation

## 🚀 Features

### User Features
- ✅ **خرید سرویس** - Purchase V2Ray plans with wallet system
- ✅ **سرویس های من** - View purchased services and configs
- ✅ **کیف پول** - Wallet management and balance top-up
- ✅ **پشتیبانی** - Support chat with admin forwarding

### Admin Features
- ✅ **📊 آمار ربات** - Bot statistics (users, revenue, etc.)
- ✅ **👤 کاربران** - User management and search
- ✅ **💰 تراکنش ها** - Payment approval/rejection system
- ✅ **📦 سرویس ها** - Plan management (add/edit/delete)
- ✅ **📨 پیام همگانی** - Broadcast messages to all users
- ✅ **⚙️ تنظیمات** - Settings panel

## 📋 Database Structure

### Tables
- **users** - User information, wallet balance, join date
- **plans** - V2Ray plans with pricing and traffic
- **services** - User subscriptions with configs and expiry dates
- **payments** - Payment transactions with approval status
- **support_messages** - Support chat messages
- **settings** - Bot configuration

## 🔧 Installation & Setup

### Local Installation

```bash
# 1. Clone or download the bot
cd v2ray_bot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set environment variables
export BOT_TOKEN="your_telegram_bot_token"
export ADMIN_IDS="123456789,987654321"  # Comma-separated admin IDs

# 4. Run the bot
python v2ray_bot.py
```

### Railway Deployment

```bash
# 1. Install Railway CLI
npm i -g @railway/cli

# 2. Login to Railway
railway login

# 3. Create new project
railway init

# 4. Set environment variables
railway variables set BOT_TOKEN="your_token"
railway variables set ADMIN_IDS="123456789"

# 5. Deploy
railway up
```

### Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY v2ray_bot.py .

CMD ["python", "v2ray_bot.py"]
```

## 📱 Bot Commands

### For Users
- `/start` - Start bot and show menu
- Buttons: خرید سرویس, سرویس های من, کیف پول, پشتیبانی

### For Admins
- `/start` - Show admin panel
- Buttons: 📊 آمار, 👤 کاربران, 💰 تراکنش, 📦 سرویس, 📨 پیام, ⚙️ تنظیمات

## 🔐 Configuration

### Required Environment Variables
```
BOT_TOKEN=your_telegram_bot_token_here
ADMIN_IDS=123456789,987654321
```

### Optional Environment Variables
```
SUPPORT_TELEGRAM_ID=123456789
DATABASE_PATH=bot_database.db
```

## 💳 Payment System

### How It Works
1. User requests wallet top-up
2. System creates pending payment
3. Admin reviews and approves/rejects
4. User wallet updated on approval
5. User notified of transaction status

### Key Features
- ✅ No external payment gateway required (manual admin approval)
- ✅ Wallet system for seamless purchases
- ✅ Automatic service activation on payment
- ✅ Transaction history and records

## 📊 Admin Panel Walkthrough

### 1. آمار ربات (Statistics)
Shows:
- Total users
- Active users (last 7 days)
- Active services count
- Total revenue
- Pending payments count

### 2. کاربران (Users)
- Search user by Telegram ID
- View user details:
  - Join date
  - Wallet balance
  - Number of services
  - Total spent amount
  - Account status

### 3. تراکنش ها (Payments)
- View all pending payments
- Approve payment (auto-add to wallet)
- Reject payment (user notified)
- Payment history

### 4. سرویس ها (Plans)
- Add new plan
- Specify: name, price, traffic, duration
- Auto-save to database
- Plans immediately available to users

### 5. پیام همگانی (Broadcast)
- Send message to all users
- Success/failure count
- Delivery confirmation

### 6. تنظیمات (Settings)
- View bot status
- System health check

## 🔄 V2Ray Config Generation

The bot generates base64-encoded VMess protocol configs with:
- Auto-generated UUID for each service
- TLS security enabled
- WebSocket transport
- Proper structure for client applications

## 📈 Usage Statistics

Track:
- User growth
- Revenue trends
- Service popularity
- Subscription churn
- Payment success rate

## 🛡️ Security Features

- ✅ Admin ID verification
- ✅ User authentication via Telegram
- ✅ Secure config encoding
- ✅ Database encryption support (SQLite)
- ✅ Proper error handling
- ✅ Logging system

## 🐛 Error Handling

The bot handles:
- ✅ Invalid inputs
- ✅ Database errors
- ✅ Network failures
- ✅ Callback failures
- ✅ Telegram API errors
- ✅ File I/O errors

All errors are logged and user-friendly messages displayed.

## 📝 Database Backup

### Manual Backup
```bash
cp bot_database.db bot_database.backup.db
```

### Automatic Backup (Recommended)
```bash
# Add to crontab (every day at 2 AM)
0 2 * * * cp /path/to/bot_database.db /path/to/backups/bot_database_$(date +\%Y\%m\%d).db
```

## 🚨 Troubleshooting

### Bot doesn't start
- Check BOT_TOKEN is valid
- Verify Python version (3.8+)
- Check internet connection

### Database errors
- Delete `bot_database.db` to reinitialize
- Check file permissions
- Verify disk space

### Payment issues
- Check ADMIN_IDS configuration
- Verify admin can receive messages
- Review bot permissions

### Message delivery fails
- Verify Telegram API is accessible
- Check user hasn't blocked bot
- Review user's privacy settings

## 📞 Support

For issues:
1. Check logs: `python v2ray_bot.py 2>&1 | tee bot.log`
2. Enable debug mode in code
3. Contact admin or developer

## 🎯 Development Roadmap

Future features:
- [ ] Real payment gateway integration
- [ ] Automatic service renewal
- [ ] Usage analytics dashboard
- [ ] Multi-language support
- [ ] Automated backups
- [ ] API integration
- [ ] User referral system
- [ ] Monthly revenue reports

## 📄 License

MIT License - Feel free to modify and distribute

## Version History

### v1.0.0
- Initial release
- Full user menu
- Complete admin panel
- Payment system
- Plan management
- Support system

---

**Last Updated:** April 2024
**Developed for:** Production use
**Status:** ✅ Stable & Ready
