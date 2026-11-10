# Telegram Controller Post Bot v2.0

Professional Telegram bot with plugin-based architecture for managing channel posts.

## ✨ New Features (v2.0)

- **🏗️ Plugin Architecture** - Modular, maintainable codebase
- **👑 Owner System** - Super owner with admin management
- **📊 Channel Management** - Add/remove channels with inline UI
- **🎨 Format Preservation** - Exact formatting maintained in posts
- **🔧 Complete Edit System** - Edit captions, posters, and buttons
- **📱 Inline Menus** - Clean, professional inline button UI
- **2️⃣ Channel Grid** - 2 channels per row display

## 📁 Project Structure

```
telegram_postbot/
├── main.py              # Bot entry point
├── config.py            # Configuration
├── db.py                # Database setup
├── plugins/             # Modular plugins
│   ├── __init__.py
│   ├── helpers.py       # Shared utilities
│   ├── start.py         # Start menu
│   ├── admins.py        # Admin management
│   ├── channels.py      # Channel CRUD
│   ├── formats.py       # Format templates
│   ├── create_post.py   # Post creation
│   ├── edit_post.py     # Post editing
│   └── settings.py      # Settings & routing
├── posters/             # Poster storage
├── requirements.txt
└── README.md
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Bot

Edit `config.py`:

```python
BOT_TOKEN = "your_bot_token"
OWNER_ID = 123456789  # Your user ID
MONGO_URI = "mongodb://..."
```

### 3. Run Bot

```bash
python main.py
```

## 👑 Owner Commands

Only the owner can use these:

```
/addadmin <user_id>     - Add admin
/removeadmin <user_id>  - Remove admin
/admins                 - List all admins
```

## 📖 Usage

### Main Menu

- **➕ Create Post** - Create new channel post
- **⚙️ Settings** - Configure channels and formats
- **📊 Channels** - Manage channels (add/remove)
- **👑 Admins** - Admin management (owner only)

### Settings Menu

- **📡 Set Channel** - Add new channel
- **📸 Set Format** - Set format template
- **📝 Edit Post** - Edit published posts
- **📂 View Formats** - View/delete formats

### Create Post Flow

1. Select channel
2. Enter episode number
3. Send quality links: `480p - link | 720p - link`
4. Preview post
5. Toggle notification
6. Send to channel

### Edit Post Flow

1. Tap "Edit Post"
2. Forward channel post
3. Choose edit type:
   - Edit Caption (formatting preserved)
   - Edit Poster (caption preserved)
   - Edit Buttons (content preserved)

### Channel Management

1. Tap "Channels"
2. Select channel
3. View details
4. Delete channel (removes format too)

## 🎨 Format System

Formats include:
- Poster image
- Caption template with `{episode}` placeholder

**Caption Formatting:**
- Bold, italic, mono preserved
- Telegram quote style supported
- No format stripping

**Example:**
```
*Episode: {episode}*

> Watch in HD quality
> Fast download

`Enjoy!`
```

## 📊 Database Collections

### admins
```json
{
  "user_id": 123456789,
  "is_owner": true
}
```

### channels
```json
{
  "_id": "-1001234567890",
  "title": "My Channel",
  "has_format": true
}
```

### formats
```json
{
  "_id": "-1001234567890",
  "caption": "Episode: {episode}",
  "poster": "posters/-1001234567890.jpg"
}
```

### sessions
```json
{
  "_id": "123456789",
  "step": "episode",
  "channel": "-1001234567890",
  "notify": true
}
```

### posts
```json
{
  "channel": "-1001234567890",
  "message_id": 123,
  "episode": "S01E01"
}
```

## 🔧 Configuration Options

```python
# config.py

BOT_TOKEN = "your_token"
OWNER_ID = 123456789
PAGE_SIZE = 6              # Channels per page
CHANNELS_PER_ROW = 2       # Channels per row in grid
MONGO_URI = "mongodb://..."
DB_NAME = "postbot"
```

## 🐛 Troubleshooting

### Bot doesn't respond
- Check OWNER_ID in config.py
- Verify MongoDB connection
- Check bot.log for errors

### Admin commands not working
- Ensure you're the owner
- Check user ID is correct
- Verify admins collection in DB

### Format not saving
- Caption must contain `{episode}`
- Send image WITH caption (one message)
- Check posters/ directory permissions

### Edit post fails
- Ensure post was sent by this bot
- Check bot has edit permissions
- Forward from correct channel

## 🚀 Production Deployment

### systemd Service

```ini
[Unit]
Description=Telegram Post Bot
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/bot
ExecStart=/usr/bin/python3 main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot
```

### PM2

```bash
pm2 start main.py --name telegram-bot --interpreter python3
pm2 save
```

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

## 🔒 Security

- Owner cannot be removed
- Admins stored in MongoDB (restart-safe)
- Non-admins automatically rejected
- All data in secure MongoDB
- Token in .gitignore

## 📝 License

MIT License - Use freely

## 🙏 Credits

- python-telegram-bot (PTB v21)
- MongoDB
- Python 3.9+
