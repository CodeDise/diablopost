"""
Channel Management Plugin - STABLE
"""

from telegram.ext import CallbackQueryHandler, MessageHandler, filters
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from plugins.helpers import (
    is_admin,
    update_session,
    get_session,
    clean_session,
    channel_keyboard,
    show_menu_safe,
    build_setup_buttons
)
from db import channels, formats, posts
import logging
import re

logger = logging.getLogger(__name__)

# ==================== REGISTRATION ====================
def register(app):
    """Register channel handlers"""
    app.add_handler(CallbackQueryHandler(start_add, pattern="^settings:setchannel$"))
    app.add_handler(CallbackQueryHandler(delete_channel_list, pattern="^settings:deletechannel$"))
    app.add_handler(CallbackQueryHandler(delete_channel_confirm, pattern="^delch:"))
    app.add_handler(CallbackQueryHandler(pagination, pattern="^page:"))
    app.add_handler(CallbackQueryHandler(cancel_add_channel, pattern="^addch:cancel$"))
    
    app.add_handler(MessageHandler(
        filters.FORWARDED & ~filters.COMMAND,
        receive_channel_forward,
        block=False
    ), group=3)

# ==================== START ADD CHANNEL ====================
async def start_add(update, context):
    """Start add channel flow"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    update_session(query.from_user.id, {
        "step": "channel"
    })
    
    try:
        await query.message.edit_text(
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
    except Exception as e:
        logger.error(f"Error editing menu for add channel: {e}")

# ==================== CANCEL ADD CHANNEL ====================
async def cancel_add_channel(update, context):
    """Cancel add channel and return to settings menu"""
    query = update.callback_query
    await query.answer("❌ Cancelled")
    
    user_id = query.from_user.id
    
    clean_session(user_id)
    
    logger.info(f"Add channel cancelled by user {user_id}")
    
    from plugins.settings import show_menu
    await show_menu(update, context)

# ==================== RECEIVE CHANNEL FORWARD ====================
async def receive_channel_forward(update, context):
    """Handle forwarded message from channel"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    s = get_session(user_id)
    
    if not s or s.get("step") != "channel":
        return
    
    logger.info(f"=== CHANNEL FORWARD RECEIVED from user {user_id} ===")
    
    if not hasattr(update.message, 'forward_origin') or not update.message.forward_origin:
        return
    
    forward_origin = update.message.forward_origin
    
    channel_id = None
    channel_title = None
    
    if hasattr(forward_origin, 'chat'):
        channel_id = str(forward_origin.chat.id)
        channel_title = forward_origin.chat.title if hasattr(forward_origin.chat, 'title') else channel_id
        logger.info(f"✅ Channel forward detected: {channel_id} ({channel_title})")
    
    elif hasattr(forward_origin, 'sender_user_name') or hasattr(forward_origin, 'sender_user'):
        await update.message.reply_text(
            "❌ *Wrong Source*\n\n"
            "This was forwarded from a user, not a channel.\n\n"
            "Please forward a message from your channel.",
            parse_mode="Markdown"
        )
        return
    
    else:
        await update.message.reply_text(
            "❌ *Unsupported Forward Type*\n\n"
            f"Could not extract channel information.",
            parse_mode="Markdown"
        )
        return
    
    if not channel_id:
        await update.message.reply_text(
            "❌ *Failed to Extract Channel ID*\n\n"
            "Could not get channel ID from forwarded message.",
            parse_mode="Markdown"
        )
        return
    
    if channels.find_one({"_id": channel_id}):
        clean_session(user_id)
        
        await update.message.reply_text(
            f"⚠️ *Channel Already Exists*\n\n"
            f"*Title:* {channel_title}\n"
            f"*ID:* `{channel_id}`\n\n"
            f"This channel is already in the database.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Settings", callback_data="menu:settings")
            ]]),
            parse_mode="Markdown"
        )
        return
    
    try:
        chat = await context.bot.get_chat(channel_id)
        channel_title = chat.title if hasattr(chat, 'title') else channel_title
        
        bot_member = await context.bot.get_chat_member(channel_id, context.bot.id)
        
        if bot_member.status not in ["administrator", "creator"]:
            clean_session(user_id)
            await update.message.reply_text(
                f"❌ *Bot Not Admin*\n\n"
                f"*Channel:* {channel_title}\n"
                f"*ID:* `{channel_id}`\n\n"
                f"**Bot must be admin with post permission in this channel.**\n\n"
                f"Please:\n"
                f"1. Add @{context.bot.username} as admin\n"
                f"2. Grant post messages permission\n"
                f"3. Try again",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back to Settings", callback_data="menu:settings")
                ]]),
                parse_mode="Markdown"
            )
            logger.warning(f"Channel rejected (not admin): {channel_id}")
            return
        
        channels.insert_one({
            "_id": channel_id,
            "title": channel_title,
            "has_format": False,
            "setup_done": False
        })
        
        clean_session(user_id)
        
        await update.message.reply_text(
            f"✅ *Channel Added Successfully!*\n\n"
            f"*Title:* {channel_title}\n"
            f"*ID:* `{channel_id}`\n"
            f"*Method:* Forwarded Message 🆕\n\n"
            f"**Next Step:**\n"
            f"Set *Format* and *Update Format*.\n"
            f"The channel becomes active only after both are set.",
            reply_markup=build_setup_buttons(channel_id),
            parse_mode="Markdown"
        )
        
        logger.info(f"Channel added via forward: {channel_id} ({channel_title})")
        
    except Exception as e:
        logger.error(f"Error accessing forwarded channel {channel_id}: {e}")
        clean_session(user_id)
        
        await update.message.reply_text(
            f"❌ *Cannot Access Channel*\n\n"
            f"*Title:* {channel_title}\n"
            f"*ID:* `{channel_id}`\n"
            f"*Error:* `{str(e)}`\n\n"
            f"**Make sure:**\n"
            f"• Bot is added as admin\n"
            f"• Bot has post permissions\n"
            f"• Channel ID is correct",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Settings", callback_data="menu:settings")
            ]]),
            parse_mode="Markdown"
        )

# ==================== RECEIVE CHANNEL ID ====================
async def receive_channel_id(update, context):
    """Receive and validate channel ID (text input)"""
    user_id = update.effective_user.id
    
    channel_id = update.message.text.strip()
    
    if not re.match(r'^-100\d{10,}$', channel_id):
        await update.message.reply_text(
            "❌ *Invalid Channel ID Format*\n\n"
            "Channel ID must:\n"
            "• Start with `-100`\n"
            "• Followed by 10+ digits\n\n"
            "Example: `-1001234567890`\n\n"
            "**Or:** Forward any message from your channel",
            parse_mode="Markdown"
        )
        return
    
    if channels.find_one({"_id": channel_id}):
        clean_session(user_id)
        
        await update.message.reply_text(
            "⚠️ *Channel Already Exists*\n\nThis channel is already in the database.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Settings", callback_data="menu:settings")
            ]]),
            parse_mode="Markdown"
        )
        return
    
    try:
        chat = await context.bot.get_chat(channel_id)
        channel_title = chat.title if hasattr(chat, 'title') else channel_id
        
        bot_member = await context.bot.get_chat_member(channel_id, context.bot.id)
        
        if bot_member.status not in ["administrator", "creator"]:
            clean_session(user_id)
            await update.message.reply_text(
                f"❌ *Bot Not Admin*\n\n"
                f"*Channel:* {channel_title}\n"
                f"*ID:* `{channel_id}`\n\n"
                f"**Bot must be admin with post permission in this channel.**\n\n"
                f"Please:\n"
                f"1. Add @{context.bot.username} as admin\n"
                f"2. Grant post messages permission\n"
                f"3. Try again",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back to Settings", callback_data="menu:settings")
                ]]),
                parse_mode="Markdown"
            )
            logger.warning(f"Channel rejected (not admin): {channel_id}")
            return
        
        channels.insert_one({
            "_id": channel_id,
            "title": channel_title,
            "has_format": False,
            "setup_done": False
        })
        
        clean_session(user_id)
        
        await update.message.reply_text(
            f"✅ *Channel Added Successfully!*\n\n"
            f"*Title:* {channel_title}\n"
            f"*ID:* `{channel_id}`\n"
            f"*Method:* Channel ID\n\n"
            f"**Next Step:**\n"
            f"Set *Format* and *Update Format*.\n"
            f"The channel becomes active only after both are set.",
            reply_markup=build_setup_buttons(channel_id),
            parse_mode="Markdown"
        )
        
        logger.info(f"Channel added via ID: {channel_id} ({channel_title})")
        
    except Exception as e:
        logger.error(f"Error accessing channel {channel_id}: {e}")
        clean_session(user_id)
        
        await update.message.reply_text(
            f"❌ *Cannot Access Channel*\n\n"
            f"Error: `{str(e)}`\n\n"
            f"**Make sure:**\n"
            f"• Bot is added as admin\n"
            f"• Bot has post permissions\n"
            f"• Channel ID is correct",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Settings", callback_data="menu:settings")
            ]]),
            parse_mode="Markdown"
        )

# ==================== DELETE CHANNEL LIST ====================
async def delete_channel_list(update, context):
    """Show channel list for deletion"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    clean_session(query.from_user.id)
    
    all_channels = list(channels.find())
    
    if not all_channels:
        await query.answer("❌ No channels to delete", show_alert=True)
        return
    
    try:
        await query.message.edit_text(
            "🗑️ *Delete Channel*\n\n"
            "Select a channel to delete:\n\n"
            "⚠️ **Warning:**\n"
            "• This will delete the channel\n"
            "• Format will also be deleted\n"
            "• Posts will remain in channel",
            reply_markup=channel_keyboard(0, "delch"),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error showing delete list: {e}")

# ==================== DELETE CHANNEL CONFIRM ====================
async def delete_channel_confirm(update, context):
    """Confirm and delete channel"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split(":")
    channel_id = parts[1]
    
    ch = channels.find_one({"_id": channel_id})
    channel_title = ch.get("title", channel_id) if ch else channel_id
    
    fmt = formats.find_one({"_id": channel_id})
    if fmt:
        formats.delete_one({"_id": channel_id})
        logger.info(f"Format deleted for channel {channel_id}")
    
    result = channels.delete_one({"_id": channel_id})
    
    if result.deleted_count > 0:
        await query.message.edit_text(
            f"✅ *Channel Deleted*\n\n"
            f"*Title:* {channel_title}\n"
            f"*ID:* `{channel_id}`\n\n"
            f"Format was also deleted.\n"
            f"Posts in channel remain unchanged.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Settings", callback_data="menu:settings")
            ]]),
            parse_mode="Markdown"
        )
        logger.info(f"Channel deleted: {channel_id}")
    else:
        await query.answer("❌ Channel not found", show_alert=True)

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
