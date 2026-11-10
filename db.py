from pymongo import MongoClient, ASCENDING
from pymongo.errors import OperationFailure
from config import MONGO_URI, DB_NAME, OWNER_ID
import logging

logger = logging.getLogger(__name__)

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

channels = db.channels
formats = db.formats
sessions = db.sessions
posts = db.posts
admins = db.admins
menu_messages = db.menu_messages
followups = db.followups
update_settings = db.update_settings
update_channel_prefs = db.update_channel_prefs
saved_posts = db.saved_posts
channel_endings = db.channel_endings

def init_update_settings():
    """Initialize update settings with dual settings"""
    if not update_settings.find_one({"_id": "global"}):
        update_settings.insert_one({
            "_id": "global",
            "update_channel_id": None,
            "update_channel_username": None,
            "update_channel_enabled": False,
            # NEW: Dual update settings
            "update_caption_template": None,
            "dual_channel_id": None,
            "dual_redirect_enabled": False
        })

init_update_settings()

def create_indexes():
    try:
        posts.create_index(
            [("channel", ASCENDING), ("message_id", ASCENDING)],
            unique=True,
            name="channel_message_idx"
        )
    except OperationFailure:
        pass
    
    try:
        sessions.create_index(
            [("_id", ASCENDING)],
            unique=True,
            name="session_user_idx"
        )
    except OperationFailure:
        pass
    
    try:
        admins.create_index(
            [("user_id", ASCENDING)],
            unique=True,
            name="admin_user_idx"
        )
    except OperationFailure:
        pass
    
    try:
        channels.create_index(
            [("title", ASCENDING)],
            name="channel_title_idx"
        )
    except OperationFailure:
        pass
    
    try:
        saved_posts.create_index(
            [("channel_id", ASCENDING), ("original_message_id", ASCENDING)],
            unique=True,
            name="saved_posts_idx"
        )
    except OperationFailure:
        pass

create_indexes()

def initialize_owner():
    try:
        if not admins.find_one({"user_id": OWNER_ID}):
            admins.insert_one({
                "user_id": OWNER_ID,
                "is_owner": True,
                "added_at": "system"
            })
            logger.info(f"✅ Owner initialized: {OWNER_ID}")
        else:
            admins.update_one(
                {"user_id": OWNER_ID},
                {"$set": {"is_owner": True}},
                upsert=False
            )
    except Exception as e:
        logger.error(f"❌ Owner initialization failed: {e}")

initialize_owner()

def get_stats():
    return {
        "channels": channels.count_documents({}),
        "formats": formats.count_documents({}),
        "posts": posts.count_documents({}),
        "admins": admins.count_documents({}),
        "sessions": sessions.count_documents({}),
        "menu_messages": menu_messages.count_documents({}),
        "followups": followups.count_documents({}),
        "update_settings": update_settings.count_documents({}),
        "saved_posts": saved_posts.count_documents({}),
        "channel_endings": channel_endings.count_documents({})
    }

try:
    client.server_info()
    logger.info("✅ MongoDB connected successfully")
    logger.info(f"📊 Database stats: {get_stats()}")
except Exception as e:
    logger.error(f"❌ MongoDB connection failed: {e}")
    raise

print("✅ MongoDB ready")
