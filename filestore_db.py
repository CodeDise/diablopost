"""
FileStore Database Connection - READ ONLY
Connects to the FileStore bot's MongoDB for metadata lookups.
Controller bot MUST NEVER write to this database.
"""

from pymongo import MongoClient
from config import FILESTORE_MONGO_URI, FILESTORE_DB_NAME, FILESTORE_BOT_USERNAME
import asyncio
import base64
import logging

logger = logging.getLogger(__name__)

# ==================== CONNECTION ====================
try:
    filestore_client = MongoClient(FILESTORE_MONGO_URI)
    filestore_db = filestore_client[FILESTORE_DB_NAME]
    filestore_files = filestore_db.files

    filestore_client.server_info()
    logger.info(f"✅ FileStore DB connected (READ ONLY): {FILESTORE_DB_NAME}")
    logger.info(f"📊 FileStore files: {filestore_files.count_documents({})}")
except Exception as e:
    logger.warning(f"⚠️ FileStore DB connection failed: {e}")
    logger.warning("FileStore lookups will not work until connection is fixed.")
    filestore_db = None
    filestore_files = None


# ==================== LOOKUP FUNCTIONS ====================

def lookup_file_by_unique_id(file_unique_id):
    """
    Look up file metadata in FileStore DB by file_unique_id.
    Returns the document or None.
    """
    if filestore_files is None:
        return None

    try:
        return filestore_files.find_one({"file_unique_id": file_unique_id})
    except Exception as e:
        logger.error(f"FileStore lookup error (unique_id): {e}")
        return None


def lookup_file_by_message_id(message_id):
    """
    Look up file metadata in FileStore DB by the channel message_id.
    Returns the document or None.
    """
    if filestore_files is None:
        return None

    try:
        return filestore_files.find_one({"message_id": message_id})
    except Exception as e:
        logger.error(f"FileStore lookup error (message_id): {e}")
        return None


async def get_filestore_doc_by_message_id(message_id, retries=10, delay=0.5):
    """
    Retry lookup for FileStore document by message_id.
    FileStore bot inserts asynchronously after receiving the copied file,
    so we must wait until the document appears.

    Args:
        message_id: Telegram message_id in the FileStore channel
        retries: Number of retry attempts (default 10 = ~5 seconds)
        delay: Seconds between retries (default 0.5)

    Returns:
        The FileStore document dict, or None if not found after all retries.
    """
    if filestore_files is None:
        logger.error("FileStore DB not connected — cannot lookup document.")
        return None

    for attempt in range(1, retries + 1):
        try:
            doc = filestore_files.find_one({"message_id": message_id})
            if doc:
                logger.info(
                    f"FileStore doc found on attempt {attempt}: "
                    f"_id={doc['_id']}, message_id={message_id}"
                )
                return doc
        except Exception as e:
            logger.warning(f"FileStore lookup attempt {attempt} error: {e}")

        if attempt < retries:
            await asyncio.sleep(delay)

    logger.warning(
        f"FileStore doc NOT found after {retries} attempts "
        f"(message_id={message_id})"
    )
    return None


# ==================== PAYLOAD ENCODING/DECODING ====================

def encode_payload(doc_id):
    """
    Encode a MongoDB document _id into the FileStore bot's start payload.
    Format: base64url("get-{doc_id}")

    IMPORTANT: doc_id must be the string representation of the MongoDB
    ObjectId, NOT the Telegram message_id.
    """
    raw = f"get-{doc_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_payload(payload):
    """
    Decode a FileStore bot start payload.
    Returns the raw string (e.g., "get-65fa...") or None on failure.
    """
    try:
        decoded = base64.urlsafe_b64decode(payload + "==").decode()
        return decoded
    except Exception as e:
        logger.error(f"Payload decode error: {e}")
        return None


def extract_doc_id_from_payload(payload):
    """
    Decode payload and extract the MongoDB document _id string.
    Returns str or None.
    """
    decoded = decode_payload(payload)
    if decoded and decoded.startswith("get-"):
        return decoded.split("-", 1)[1]
    return None


def build_share_link(doc_id, bot_username=None):
    """
    Build a complete FileStore share link using the MongoDB document _id.

    Args:
        doc_id: String representation of the MongoDB ObjectId
        bot_username: Optional override for bot username
    """
    username = bot_username or FILESTORE_BOT_USERNAME
    payload = encode_payload(doc_id)
    return f"https://t.me/{username}?start={payload}"


print("✅ FileStore DB module loaded")
