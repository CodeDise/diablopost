"""
Format Templates Plugin - STABLE
"""

from telegram.ext import CallbackQueryHandler
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, MessageEntity
from plugins.helpers import (
    is_admin,
    update_session,
    get_session,
    clean_session,
    channel_keyboard,
    validate_format_caption,
    show_menu_safe
)
from db import formats, channels
from config import DB_CHANNEL_ID
import logging

logger = logging.getLogger(__name__)

# ==================== REGISTRATION ====================
def register(app):
    """Register format handlers"""
    app.add_handler(CallbackQueryHandler(show_channel_list, pattern="^settings:setformat$"))
    app.add_handler(CallbackQueryHandler(select_channel, pattern="^setfmt:"))
    app.add_handler(CallbackQueryHandler(view_formats_list, pattern="^settings:viewformats$"))
    app.add_handler(CallbackQueryHandler(view_format_detail, pattern="^viewfmt:"))
    app.add_handler(CallbackQueryHandler(delete_format, pattern="^delfmt:"))
    app.add_handler(CallbackQueryHandler(back_to_formats_list, pattern="^backtolist$"))
    app.add_handler(CallbackQueryHandler(cancel_format_edit, pattern="^cancelfmt$"))
    app.add_handler(CallbackQueryHandler(add_next_channel, pattern="^addnext$"))
    app.add_handler(CallbackQueryHandler(cancel_after_format, pattern="^cancelafter$"))
    app.add_handler(CallbackQueryHandler(pagination, pattern="^page:"))

# ==================== SHOW CHANNEL LIST ====================
async def show_channel_list(update, context):
    """Show channel list for format selection"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    clean_session(query.from_user.id)
    
    try:
        await query.message.edit_text(
            "📸 *Set Format*\n\n"
            "Select a channel to configure format:",
            reply_markup=channel_keyboard(0, "setfmt"),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error showing channel list: {e}")

# ==================== SELECT CHANNEL ====================
async def select_channel(update, context):
    """Channel selected - ask for poster + caption"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split(":")
    channel_id = parts[1]
    
    update_session(query.from_user.id, {
        "step": "format",
        "channel": channel_id
    })
    
    ch = channels.find_one({"_id": channel_id})
    channel_title = ch.get("title", channel_id) if ch else channel_id
    
    await query.message.reply_text(
        f"📸 *Set Format for:* {channel_title}\n\n"
        f"Send a poster image WITH caption.\n\n"
        f"⚠️ *Important:*\n"
        f"• Caption MUST contain: `{{episode}}`\n"
        f"• You can use **bold**, *italic*, `mono` formatting\n"
        f"• Formatting will be preserved\n\n"
        f"*Example:*\n"
        f"```\n"
        f"**Episode: {{episode}}**\n\n"
        f"> Watch in HD\n"
        f"> Fast download\n\n"
        f"`Enjoy!`\n"
        f"```",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Cancel", callback_data="cancelfmt")
        ]]),
        parse_mode="Markdown"
    )

# ==================== CANCEL FORMAT EDIT ====================
async def cancel_format_edit(update, context):
    """Cancel format editing and return to settings"""
    query = update.callback_query
    await query.answer("❌ Cancelled")
    
    user_id = query.from_user.id
    
    clean_session(user_id)
    
    logger.info(f"Format edit cancelled by user {user_id}")
    
    from plugins.settings import show_menu
    await show_menu(update, context)

# ==================== RECEIVE FORMAT ====================
async def receive_format(update, context):
    """Receive poster + caption and save to DB"""
    user_id = update.effective_user.id
    s = get_session(user_id)
    
    if not s or s.get("step") != "format":
        return
    
    if not is_admin(user_id):
        return
    
    caption = update.message.caption
    channel_id = s["channel"]
    
    is_valid, error = validate_format_caption(caption)
    if not is_valid:
        await update.message.reply_text(
            f"❌ *Invalid Caption*\n\n"
            f"{error}\n\n"
            f"Example: `Episode: {{episode}}`",
            parse_mode="Markdown"
        )
        return
    
    try:
        db_msg = await context.bot.send_photo(
            chat_id=DB_CHANNEL_ID,
            photo=update.message.photo[-1].file_id,
            caption=caption,
            caption_entities=update.message.caption_entities
        )
        
        logger.info(f"Format backed up to DB channel: {db_msg.message_id}")
        
        entities_data = None
        if update.message.caption_entities:
            entities_data = [
                {
                    "type": e.type,
                    "offset": e.offset,
                    "length": e.length,
                    "url": e.url if e.url else None,
                    "user": e.user.id if e.user else None,
                    "language": e.language if e.language else None,
                    "custom_emoji_id": e.custom_emoji_id if e.custom_emoji_id else None
                }
                for e in update.message.caption_entities
            ]
        
        formats.update_one(
            {"_id": channel_id},
            {"$set": {
                "poster_file_id": db_msg.photo[-1].file_id,
                "caption": caption,
                "caption_entities": entities_data,
                "db_message_id": db_msg.message_id
            }},
            upsert=True
        )
        
        channels.update_one(
            {"_id": channel_id},
            {"$set": {"has_format": True}}
        )
        
        clean_session(user_id)
        
        ch = channels.find_one({"_id": channel_id})
        channel_title = ch.get("title", channel_id) if ch else channel_id
        
        await update.message.reply_text(
            f"✅ *Format Saved Successfully!*\n\n"
            f"*Channel:* {channel_title}\n"
            f"*Poster:* Stored in DB channel\n"
            f"*Caption:* Template saved\n"
            f"*Formatting:* Preserved\n\n"
            f"This format will be used for all future posts.\n\n"
            f"**What's next?**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "➕ Add Next Channel",
                    callback_data="addnext"
                )],
                [InlineKeyboardButton(
                    "❌ Cancel",
                    callback_data="cancelafter"
                )]
            ]),
            parse_mode="Markdown"
        )
        
        logger.info(f"Format saved for channel {channel_id}")
        
    except Exception as e:
        logger.error(f"Error saving format: {e}")
        clean_session(user_id)
        
        await update.message.reply_text(
            f"❌ *Error Saving Format*\n\n"
            f"Error: `{str(e)}`\n\n"
            f"Make sure bot is admin in DB channel.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Settings", callback_data="menu:settings")
            ]]),
            parse_mode="Markdown"
        )

# ==================== ADD NEXT CHANNEL ====================
async def add_next_channel(update, context):
    """User clicked "Add Next Channel" after setting format"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if not is_admin(user_id):
        return
    
    clean_session(user_id)
    
    update_session(user_id, {
        "step": "channel"
    })
    
    await query.message.reply_text(
        "📡 *Add Channel*\n\n"
        "**Method 1: Send Channel ID**\n"
        "Send the channel ID (numeric ID only)\n"
        "*Format:* `-1001234567890`\n\n"
        "**Method 2: Forward Message** 🆕\n"
        "Forward any message from your channel to this bot\n\n"
        "**How to get channel ID:**\n"
        "1. Forward a message from channel to @userinfobot\n"
        "2. Or add @UnityPostingBot as admin\n"
        "3. Copy the channel ID\n\n"
        "⚠️ Bot must be admin in the channel",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Cancel", callback_data="addch:cancel")
        ]]),
        parse_mode="Markdown"
    )
    
    logger.info(f"User {user_id} clicked Add Next Channel")

# ==================== CANCEL AFTER FORMAT ====================
async def cancel_after_format(update, context):
    """User clicked "Cancel" after setting format"""
    query = update.callback_query
    await query.answer("✅ Done")
    
    user_id = query.from_user.id
    
    clean_session(user_id)
    
    logger.info(f"User {user_id} finished adding channels")
    
    from plugins.settings import show_menu
    await show_menu(update, context)

# ==================== VIEW FORMATS LIST ====================
async def view_formats_list(update, context):
    """Show list of channels to view their formats"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    clean_session(query.from_user.id)
    
    try:
        await query.message.edit_text(
            "📂 *View Formats*\n\n"
            "Select a channel to view its format:",
            reply_markup=channel_keyboard(0, "viewfmt"),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error showing formats list: {e}")

# ==================== VIEW FORMAT DETAIL ====================
async def view_format_detail(update, context):
    """Show format details"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split(":")
    channel_id = parts[1]
    
    fmt = formats.find_one({"_id": channel_id})
    if not fmt:
        await query.answer("❌ No format set for this channel", show_alert=True)
        return
    
    ch = channels.find_one({"_id": channel_id})
    channel_title = ch.get("title", channel_id) if ch else channel_id
    
    buttons = [
        [InlineKeyboardButton("✏️ Edit Format", callback_data=f"setfmt:{channel_id}:0")],
        [InlineKeyboardButton("🗑️ Delete Format", callback_data=f"delfmt:{channel_id}:0")],
        [InlineKeyboardButton("🔙 Back to List", callback_data="backtolist")],
        [InlineKeyboardButton("🏠 Settings Menu", callback_data="menu:settings")]
    ]
    
    caption = fmt["caption"]
    entities = None
    
    if fmt.get("caption_entities"):
        entities = []
        for e in fmt["caption_entities"]:
            kwargs = {
                "type": e["type"],
                "offset": e["offset"],
                "length": e["length"],
            }
            if e.get("url"):
                kwargs["url"] = e["url"]
            if e.get("language"):
                kwargs["language"] = e["language"]
            if e.get("custom_emoji_id"):
                kwargs["custom_emoji_id"] = e["custom_emoji_id"]
            entities.append(MessageEntity(**kwargs))
    try:
        try:
            await query.message.delete()
        except:
            pass
        
        await context.bot.send_photo(
            chat_id=query.from_user.id,
            photo=fmt["poster_file_id"],
            caption=caption,
            caption_entities=entities,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
    except Exception as e:
        logger.error(f"Error showing format detail: {e}")
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=f"❌ *Error Loading Format*\n\n"
                 f"Channel: {channel_title}\n"
                 f"Error: `{str(e)}`",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )

# ==================== BACK TO FORMATS LIST ====================
async def back_to_formats_list(update, context):
    """Return to formats list"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    clean_session(query.from_user.id)
    
    try:
        await query.message.delete()
    except:
        pass
    
    try:
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text="📂 *View Formats*\n\n"
                 "Select a channel to view its format:",
            reply_markup=channel_keyboard(0, "viewfmt"),
            parse_mode="Markdown"
        )
        logger.info(f"Returned to formats list for user {query.from_user.id}")
    except Exception as e:
        logger.error(f"Error returning to formats list: {e}")

# ==================== DELETE FORMAT ====================
async def delete_format(update, context):
    """Delete format for a channel"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split(":")
    channel_id = parts[1]
    
    ch = channels.find_one({"_id": channel_id})
    channel_title = ch.get("title", channel_id) if ch else channel_id
    
    result = formats.delete_one({"_id": channel_id})
    
    channels.update_one(
        {"_id": channel_id},
        {"$set": {"has_format": False}}
    )
    
    if result.deleted_count > 0:
        try:
            await query.message.delete()
        except:
            pass
        
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=f"✅ *Format Deleted*\n\n"
                 f"*Channel:* {channel_title}\n\n"
                 f"Channel cannot be used for posting until format is set again.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Settings", callback_data="menu:settings")
            ]]),
            parse_mode="Markdown"
        )
        logger.info(f"Format deleted for channel {channel_id}")
    else:
        await query.answer("⚠️ Format not found", show_alert=True)

# ==================== PAGINATION ====================
async def pagination(update, context):
    """Handle pagination for channel lists"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split(":")
    page = int(parts[1])
    prefix = parts[2]
    
    try:
        await query.message.edit_reply_markup(
            reply_markup=channel_keyboard(page, prefix)
        )
    except Exception as e:
        logger.error(f"Pagination error: {e}")
