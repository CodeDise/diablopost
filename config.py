"""
Configuration File - Telegram Controller Post Bot
PRODUCTION GRADE - DO NOT COMMIT TO GIT
"""

# ==================== BOT TOKEN ====================
BOT_TOKEN = "8773512678:AAECYUGLDYWWpDLwZ9FI9ZcsbmFSr0iuRLY"

# ==================== MONGODB ====================
MONGO_URI = "mongodb+srv://otxstudioofficial1_db_user:MEAH3IXpZFAxHHew@cluster0.n23pbwq.mongodb.net/?appName=Cluster0"
DB_NAME = "pressurework"

# ==================== OWNER ====================
# Super admin with full control
OWNER_ID = 8531489053

# ==================== DB CHANNEL ====================
# Private channel for poster + caption backup storage
# Bot MUST be admin with post permission
DB_CHANNEL_ID = -1003720669935

# ==================== PAGINATION ====================
PAGE_SIZE = 14              # Channels per page
CHANNELS_PER_ROW = 2       # Channels per row in grid display

# ==================== FILESTORE ====================
# FileStore storage channel (bot forwards files here)
FILESTORE_CHANNEL_ID = -1003763877447   # CHANGE THIS to your FileStore channel ID

# FileStore bot username (for share links)
FILESTORE_BOT_USERNAME = "Dekufilebot"

# ==================== SECURITY ====================
# Add to .gitignore to prevent token leaks
# Recommended: Use environment variables in production

