"""
Helper Functions - FIXED
Added dual button routing to message router
"""

from db import sessions, admins, channels, menu_messages
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity
from telegram.error import BadRequest
from config import PAGE_SIZE, CHANNELS_PER_ROW, OWNER_ID
import logging

logger = logging.getLogger(__name__)

# ==================== AUTH ====================
def is_owner(uid):
    """Check if user is the owner"""
    return int(uid) == int(OWNER_ID)

def is_admin(uid):
    """Check if user is admin or owner"""
    if is_owner(uid):
        return True
    return bool(admins.find_one({"user_id": int(uid)}))

# ==================== SESSION ====================
def clean_session(uid):
    """Clear user session completely"""
    sessions.delete_one({"_id": str(uid)})

def get_session(uid):
    """Get user session"""
    return sessions.find_one({"_id": str(uid)})

def update_session(uid, data):
    """Update user session (merge with existing)"""
    sessions.update_one(
        {"_id": str(uid)},
        {"$set": data},
        upsert=True
    )

# ==================== MENU SYSTEM ====================

def build_main_menu_buttons(user_id):
    """Build main menu buttons based on user role - FIXED: Added Add Dual"""
    buttons = [
        [InlineKeyboardButton("➕ ​ᴄʀᴇᴀᴛᴇ ᴘᴏsᴛ", callback_data="menu:create")],
        [InlineKeyboardButton("✏️ ​ᴇᴅɪᴛ ᴘᴏsᴛ", callback_data="settings:editpost")],
        [InlineKeyboardButton("🔄 ᴀᴅᴅ ᴅᴜᴀʟ", callback_data="menu:adddual")],  # FIXED: Added here
        [InlineKeyboardButton("⚙️ ​sᴇᴛᴛɪɴɢs", callback_data="menu:settings")]
    ]
    
    if is_owner(user_id):
        buttons.append([InlineKeyboardButton(
            "👑 ᴀᴅᴍɪɴꜱ",
            callback_data="menu:admins"
        )])
    
    return buttons

def build_menu_text():
    """Build main menu text"""
    return (
        "🎬 *ᴍᴀɴᴀɢᴇ ᴘᴏꜱᴛꜱ, ᴄʜᴀɴɴᴇʟꜱ, ꜰᴏʀᴍᴀᴛꜱ, ᴀɴᴅ ᴜᴘᴅᴀᴛᴇꜱ ꜰʀᴏᴍ ᴏɴᴇ ᴄᴇɴᴛʀᴀʟ ᴄᴏɴᴛʀᴏʟ ᴘᴀɴᴇʟ.*\n\n"
        "ꜱᴇʟᴇᴄᴛ ᴀɴ ᴏᴘᴛɪᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ:"
    )

async def show_menu_safe(update, context, user_id=None):
    """
    STABLE MENU: Always shows menu, never crashes
    """
    if user_id is None:
        if hasattr(update, 'callback_query') and update.callback_query:
            user_id = update.callback_query.from_user.id
        elif hasattr(update, 'message') and update.message:
            user_id = update.message.from_user.id
        elif hasattr(update, 'effective_user'):
            user_id = update.effective_user.id
    
    buttons = build_main_menu_buttons(user_id)
    text = build_menu_text()
    keyboard = InlineKeyboardMarkup(buttons)
    
    menu_doc = menu_messages.find_one({"_id": str(user_id)})
    stored_msg_id = menu_doc.get("message_id") if menu_doc else None
    
    if stored_msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=stored_msg_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            logger.info(f"✅ Menu edited for {user_id}")
            return
        except BadRequest:
            logger.info(f"Menu not editable, sending new for {user_id}")
        except Exception as e:
            logger.warning(f"Menu edit failed: {e}, sending new")
    
    try:
        msg = await context.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        menu_messages.update_one(
            {"_id": str(user_id)},
            {"$set": {"message_id": msg.message_id}},
            upsert=True
        )
        logger.info(f"✅ New menu sent to {user_id}")
    except Exception as e:
        logger.error(f"Failed to send menu: {e}")

async def send_main_menu(chat_id, context, notification_text=None):
    """Send new menu with optional notification"""
    buttons = build_main_menu_buttons(chat_id)
    text = build_menu_text()
    
    if notification_text:
        text = f"{notification_text}\n\n─────────────────\n\n{text}"
    
    try:
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )
        
        menu_messages.update_one(
            {"_id": str(chat_id)},
            {"$set": {"message_id": msg.message_id}},
            upsert=True
        )
        
        logger.info(f"✅ Menu sent to {chat_id}")
        return msg
    except Exception as e:
        logger.error(f"Failed to send menu: {e}")
        return None

# ==================== CAPTION ENTITIES FIX ====================
def adjust_caption_entities(caption, entities, placeholder="{episode}", replacement=""):
    """Adjust caption entity offsets when replacing placeholder"""
    
    if not entities:
        return caption.replace(placeholder, replacement), None
    
    placeholder_pos = caption.find(placeholder)
    if placeholder_pos == -1:
        return caption, entities
    
    placeholder_len = len(placeholder)
    replacement_len = len(replacement)
    offset_diff = replacement_len - placeholder_len
    
    adjusted_entities = []
    
    for entity in entities:
        if isinstance(entity, MessageEntity):
            entity_dict = {
                "type": entity.type,
                "offset": entity.offset,
                "length": entity.length
            }
            if entity.url:
                entity_dict["url"] = entity.url
            if entity.user:
                entity_dict["user"] = entity.user
            if entity.language:
                entity_dict["language"] = entity.language
            if entity.custom_emoji_id:
                entity_dict["custom_emoji_id"] = entity.custom_emoji_id
        else:
            entity_dict = dict(entity)
        
        entity_start = entity_dict["offset"]
        entity_end = entity_start + entity_dict["length"]
        placeholder_end = placeholder_pos + placeholder_len
        
        if entity_end <= placeholder_pos:
            adjusted_entities.append(entity_dict)
        elif entity_start >= placeholder_end:
            entity_dict["offset"] += offset_diff
            adjusted_entities.append(entity_dict)
        else:
            if entity_start <= placeholder_pos and entity_end >= placeholder_end:
                entity_dict["length"] += offset_diff
                adjusted_entities.append(entity_dict)
            elif entity_start >= placeholder_pos and entity_start < placeholder_end:
                entity_dict["offset"] = placeholder_pos
                if entity_end > placeholder_end:
                    entity_dict["length"] = (entity_end - placeholder_end) + replacement_len
                else:
                    entity_dict["length"] = replacement_len
                adjusted_entities.append(entity_dict)
            elif entity_end > placeholder_pos and entity_end <= placeholder_end:
                entity_dict["length"] = placeholder_pos - entity_start
                if entity_dict["length"] > 0:
                    adjusted_entities.append(entity_dict)
    
    new_caption = caption.replace(placeholder, replacement)
    return new_caption, adjusted_entities

# ==================== CHANNEL KEYBOARD ====================
def channel_keyboard(page=0, prefix="post"):
    """Build paginated channel selection keyboard"""
    data = list(channels.find())
    
    if not data:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ No channels", callback_data="none")
        ]])
    
    data.sort(key=lambda x: x.get("title", x["_id"]).lower())
    
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_data = data[start:end]
    
    buttons = []
    row = []
    
    for ch in page_data:
        title = ch.get("title", ch["_id"])
        
        if ch.get("has_format"):
            display = f"✅ {title}"
        else:
            display = f"❌ {title}"
        
        btn = InlineKeyboardButton(
            display,
            callback_data=f"{prefix}:{ch['_id']}:{page}"
        )
        row.append(btn)
        
        if len(row) == CHANNELS_PER_ROW:
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    nav = []
    if start > 0:
        nav.append(InlineKeyboardButton(
            "⬅️ Prev",
            callback_data=f"page:{page-1}:{prefix}"
        ))
    if end < len(data):
        nav.append(InlineKeyboardButton(
            "Next ➡️",
            callback_data=f"page:{page+1}:{prefix}"
        ))
    
    if nav:
        buttons.append(nav)
    
    buttons.append([InlineKeyboardButton(
        "🔙 Back",
        callback_data="menu:back"
    )])
    
    return InlineKeyboardMarkup(buttons)

# ==================== BUILD QUALITY BUTTONS ====================
def build_quality_buttons(links, buttons_per_row=3):
    """Build inline keyboard from quality links"""
    rows = []
    row = []
    
    for quality, url in links:
        row.append(InlineKeyboardButton(quality, url=url))
        if len(row) >= buttons_per_row:
            rows.append(row)
            row = []
    
    if row:
        rows.append(row)
    
    return rows

# ==================== PARSE QUALITY LINKS ====================
def parse_quality_links(text):
    """Parse quality links from text"""
    text = text.replace("\n", " && ")
    text = text.replace("|", " && ")
    
    links = []
    parts = text.split("&&")
    
    for part in parts:
        part = part.strip()
        if " - " not in part:
            continue
        
        quality, url = part.split(" - ", 1)
        quality = quality.strip()
        url = url.strip()
        
        if quality and url:
            links.append([quality, url])
    
    return links

# ==================== VALIDATE EPISODE PLACEHOLDER ====================
def validate_format_caption(caption):
    """Validate that caption contains {episode} placeholder"""
    if not caption:
        return False, "Caption cannot be empty"
    
    if "{episode}" not in caption:
        return False, "Caption must contain {episode} placeholder"
    
    return True, None

# ==================== MESSAGE ROUTER (FIXED) ====================
async def route_message(update, context):
    """Central message router based on session step - FIXED: Added dual routing"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    s = get_session(user_id)
    if not s:
        return
    
    step = s.get("step")
    action = s.get("action")
    
    from plugins import channels, create_post, edit_post, bulk_replace, dual_update
    
    # Smart Collector routing
    if step == "collector":
        from plugins.smart_collector import smart_collect_input
        await smart_collect_input(update, context)
    
    elif step == "collector_episode_fallback":
        from plugins.smart_collector import receive_episode_fallback
        await receive_episode_fallback(update, context)
    
    # FIXED: Added dual button routing
    elif step == "dual_buttons":
        await dual_update.receive_dual_buttons(update, context)
    
    elif action == "bulk_replace":
        await bulk_replace.route_replace_text(update, context)
    
    elif step == "channel":
        await channels.receive_channel_id(update, context)
    
    elif step == "episode":
        await create_post.receive_episode(update, context)
    
    elif step == "links":
        await create_post.receive_links(update, context)
    
    elif step == "edit_menu":
        edit_type = s.get("edit_type")
        if edit_type in ["caption", "buttons"]:
            await edit_post.apply_text_edit(update, context)
    
    elif step == "update_channel":
        from plugins.update_channel import receive_update_channel
        await receive_update_channel(update, context)

    elif step == "update_channel_format":
        from plugins.update_channel import receive_update_channel_format
        await receive_update_channel_format(update, context)
