"""
Follow-up System Plugin
Owner-only global sticker/message sent after every episode post
CRITICAL: Uses DB channel storage via copyMessage
"""

from telegram.ext import CallbackQueryHandler, MessageHandler, filters
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from plugins.helpers import is_owner, is_admin, update_session, get_session, clean_session
from db import followups, channel_endings
from config import DB_CHANNEL_ID
import logging

logger = logging.getLogger(__name__)

# ==================== REGISTRATION ====================
def register(app):
    """Register followup handlers"""
    app.add_handler(CallbackQueryHandler(show_followup_menu, pattern="^settings:followups$"))
    app.add_handler(CallbackQueryHandler(set_sticker_start, pattern="^followup:setsticker$"))
    app.add_handler(CallbackQueryHandler(set_message_start, pattern="^followup:setmessage$"))
    app.add_handler(CallbackQueryHandler(manage_sticker, pattern="^followup:managesticker$"))
    app.add_handler(CallbackQueryHandler(manage_message, pattern="^followup:managemessage$"))
    app.add_handler(CallbackQueryHandler(disable_sticker, pattern="^followup:disablesticker$"))
    app.add_handler(CallbackQueryHandler(disable_message, pattern="^followup:disablemessage$"))
    app.add_handler(CallbackQueryHandler(delete_sticker, pattern="^followup:deletesticker$"))
    app.add_handler(CallbackQueryHandler(delete_message, pattern="^followup:deletemessage$"))
    app.add_handler(CallbackQueryHandler(enable_sticker, pattern="^followup:enablesticker$"))
    app.add_handler(CallbackQueryHandler(enable_message, pattern="^followup:enablemessage$"))

# ==================== HELPER: GET FOLLOWUP ====================
def get_followup():
    """Get global followup config"""
    return followups.find_one({"_id": "global"})

# ==================== HELPER: UPDATE FOLLOWUP ====================
def update_followup(data):
    """Update global followup config"""
    followups.update_one(
        {"_id": "global"},
        {"$set": data},
        upsert=True
    )

# ==================== SHOW FOLLOWUP MENU ====================
async def show_followup_menu(update, context):
    """Show follow-up management menu"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Unauthorized", show_alert=True)
        return
    
    followup = get_followup()
    
    sticker_status = "❌ Not Set"
    message_status = "❌ Not Set"
    
    if followup:
        if followup.get("sticker"):
            sticker_enabled = followup["sticker"].get("enabled", False)
            sticker_status = "✅ Enabled" if sticker_enabled else "🚫 Disabled"
        
        if followup.get("message"):
            message_enabled = followup["message"].get("enabled", False)
            message_status = "✅ Enabled" if message_enabled else "🚫 Disabled"
    
    buttons = [
        [InlineKeyboardButton(
            f"🎨 Custom Sticker ({sticker_status})",
            callback_data="followup:managesticker" if followup and followup.get("sticker") else "followup:setsticker"
        )],
        [InlineKeyboardButton(
            f"💬 Custom Message ({message_status})",
            callback_data="followup:managemessage" if followup and followup.get("message") else "followup:setmessage"
        )],
        [InlineKeyboardButton("🔙 Back", callback_data="menu:settings")]
    ]
    
    try:
        await query.message.edit_text(
            "📬 *Follow-up Management*\n\n"
            "Configure sticker/message sent after every episode post.\n\n"
            f"*Sticker:* {sticker_status}\n"
            f"*Message:* {message_status}\n\n"
            "⚠️ *Owner Only Feature*",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error showing followup menu: {e}")

# ==================== SET STICKER START ====================
async def set_sticker_start(update, context):
    """Owner clicks Set Custom Sticker"""
    query = update.callback_query
    await query.answer()
    
    if not is_owner(query.from_user.id):
        await query.answer("⛔ Only owner can use this feature", show_alert=True)
        return
    
    update_session(query.from_user.id, {
        "step": "followup_sticker",
        "action": "set_sticker"
    })
    
    await query.message.reply_text(
        "🎨 *Set Custom Sticker*\n\n"
        "Send a sticker, image, or video.\n\n"
        "This will be sent automatically after every episode post.\n\n"
        "Type /cancel to abort",
        parse_mode="Markdown"
    )
    
    logger.info(f"Owner {query.from_user.id} started set sticker flow")

# ==================== SET MESSAGE START ====================
async def set_message_start(update, context):
    """Owner clicks Set Custom Message"""
    query = update.callback_query
    await query.answer()
    
    if not is_owner(query.from_user.id):
        await query.answer("⛔ Only owner can use this feature", show_alert=True)
        return
    
    update_session(query.from_user.id, {
        "step": "followup_message",
        "action": "set_message"
    })
    
    await query.message.reply_text(
        "💬 *Set Custom Message*\n\n"
        "Send a text message or photo with caption.\n\n"
        "You can use:\n"
        "• **Bold**\n"
        "• *Italic*\n"
        "• `Code`\n"
        "• > Quote\n"
        "• Links\n\n"
        "This will be sent automatically after every episode post.\n\n"
        "Type /cancel to abort",
        parse_mode="Markdown"
    )
    
    logger.info(f"Owner {query.from_user.id} started set message flow")

# ==================== RECEIVE STICKER ====================
async def receive_sticker(update, context):
    """Receive sticker/image/video from owner"""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        return
    
    s = get_session(user_id)
    if not s or s.get("step") != "followup_sticker":
        return
    
    try:
        # Send to DB channel
        db_msg = await context.bot.copy_message(
            chat_id=DB_CHANNEL_ID,
            from_chat_id=update.message.chat_id,
            message_id=update.message.message_id
        )
        
        logger.info(f"Followup sticker saved to DB channel: {db_msg.message_id}")
        
        # Save to database
        update_followup({
            "sticker": {
                "enabled": True,
                "db_msg_id": db_msg.message_id
            }
        })
        
        clean_session(user_id)
        
        # Show manage menu
        buttons = [
            [InlineKeyboardButton("🚫 Disable Sticker", callback_data="followup:disablesticker")],
            [InlineKeyboardButton("🗑️ Delete Sticker", callback_data="followup:deletesticker")],
            [InlineKeyboardButton("🔙 Back", callback_data="settings:followups")]
        ]
        
        await update.message.reply_text(
            "✅ *Custom Sticker Saved!*\n\n"
            "This sticker will be sent automatically after every episode post.\n\n"
            "*Status:* Enabled",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )
        
        logger.info(f"Followup sticker set by owner {user_id}")
        
    except Exception as e:
        logger.error(f"Error saving followup sticker: {e}")
        await update.message.reply_text(
            f"❌ *Error Saving Sticker*\n\n"
            f"Error: `{str(e)}`\n\n"
            f"Make sure bot is admin in DB channel.",
            parse_mode="Markdown"
        )

# ==================== RECEIVE MESSAGE ====================
async def receive_message(update, context):
    """Receive text/photo message from owner"""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        return
    
    s = get_session(user_id)
    if not s or s.get("step") != "followup_message":
        return
    
    try:
        # Send to DB channel
        db_msg = await context.bot.copy_message(
            chat_id=DB_CHANNEL_ID,
            from_chat_id=update.message.chat_id,
            message_id=update.message.message_id
        )
        
        logger.info(f"Followup message saved to DB channel: {db_msg.message_id}")
        
        # Save to database
        update_followup({
            "message": {
                "enabled": True,
                "db_msg_id": db_msg.message_id
            }
        })
        
        clean_session(user_id)
        
        # Show manage menu
        buttons = [
            [InlineKeyboardButton("✏️ Edit Message", callback_data="followup:setmessage")],
            [InlineKeyboardButton("🚫 Disable Message", callback_data="followup:disablemessage")],
            [InlineKeyboardButton("🗑️ Delete Message", callback_data="followup:deletemessage")],
            [InlineKeyboardButton("🔙 Back", callback_data="settings:followups")]
        ]
        
        await update.message.reply_text(
            "✅ *Custom Message Saved!*\n\n"
            "This message will be sent automatically after every episode post.\n\n"
            "*Status:* Enabled",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )
        
        logger.info(f"Followup message set by owner {user_id}")
        
    except Exception as e:
        logger.error(f"Error saving followup message: {e}")
        await update.message.reply_text(
            f"❌ *Error Saving Message*\n\n"
            f"Error: `{str(e)}`\n\n"
            f"Make sure bot is admin in DB channel.",
            parse_mode="Markdown"
        )

# ==================== MANAGE STICKER ====================
async def manage_sticker(update, context):
    """Show sticker management menu"""
    query = update.callback_query
    await query.answer()
    
    if not is_owner(query.from_user.id):
        await query.answer("⛔ Only owner can use this feature", show_alert=True)
        return
    
    followup = get_followup()
    
    if not followup or not followup.get("sticker"):
        await query.answer("❌ No sticker configured", show_alert=True)
        await show_followup_menu(update, context)
        return
    
    sticker_data = followup["sticker"]
    enabled = sticker_data.get("enabled", False)
    
    buttons = []
    
    if enabled:
        buttons.append([InlineKeyboardButton("🚫 Disable Sticker", callback_data="followup:disablesticker")])
    else:
        buttons.append([InlineKeyboardButton("✅ Enable Sticker", callback_data="followup:enablesticker")])
    
    buttons.append([InlineKeyboardButton("🗑️ Delete Sticker", callback_data="followup:deletesticker")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="settings:followups")])
    
    try:
        await query.message.edit_text(
            f"🎨 *Custom Sticker Management*\n\n"
            f"*Status:* {'✅ Enabled' if enabled else '🚫 Disabled'}\n\n"
            f"This sticker is sent automatically after every episode post.",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error showing sticker management: {e}")

# ==================== MANAGE MESSAGE ====================
async def manage_message(update, context):
    """Show message management menu"""
    query = update.callback_query
    await query.answer()
    
    if not is_owner(query.from_user.id):
        await query.answer("⛔ Only owner can use this feature", show_alert=True)
        return
    
    followup = get_followup()
    
    if not followup or not followup.get("message"):
        await query.answer("❌ No message configured", show_alert=True)
        await show_followup_menu(update, context)
        return
    
    message_data = followup["message"]
    enabled = message_data.get("enabled", False)
    
    buttons = [
        [InlineKeyboardButton("✏️ Edit Message", callback_data="followup:setmessage")]
    ]
    
    if enabled:
        buttons.append([InlineKeyboardButton("🚫 Disable Message", callback_data="followup:disablemessage")])
    else:
        buttons.append([InlineKeyboardButton("✅ Enable Message", callback_data="followup:enablemessage")])
    
    buttons.append([InlineKeyboardButton("🗑️ Delete Message", callback_data="followup:deletemessage")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="settings:followups")])
    
    try:
        await query.message.edit_text(
            f"💬 *Custom Message Management*\n\n"
            f"*Status:* {'✅ Enabled' if enabled else '🚫 Disabled'}\n\n"
            f"This message is sent automatically after every episode post.",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error showing message management: {e}")

# ==================== DISABLE STICKER ====================
async def disable_sticker(update, context):
    """Disable sticker followup"""
    query = update.callback_query
    await query.answer()
    
    if not is_owner(query.from_user.id):
        await query.answer("⛔ Only owner can use this feature", show_alert=True)
        return
    
    followup = get_followup()
    if followup and followup.get("sticker"):
        update_followup({"sticker.enabled": False})
        await query.answer("✅ Sticker disabled", show_alert=False)
        logger.info(f"Followup sticker disabled by owner {query.from_user.id}")
    
    await manage_sticker(update, context)

# ==================== DISABLE MESSAGE ====================
async def disable_message(update, context):
    """Disable message followup"""
    query = update.callback_query
    await query.answer()
    
    if not is_owner(query.from_user.id):
        await query.answer("⛔ Only owner can use this feature", show_alert=True)
        return
    
    followup = get_followup()
    if followup and followup.get("message"):
        update_followup({"message.enabled": False})
        await query.answer("✅ Message disabled", show_alert=False)
        logger.info(f"Followup message disabled by owner {query.from_user.id}")
    
    await manage_message(update, context)

# ==================== ENABLE STICKER ====================
async def enable_sticker(update, context):
    """Enable sticker followup"""
    query = update.callback_query
    await query.answer()
    
    if not is_owner(query.from_user.id):
        await query.answer("⛔ Only owner can use this feature", show_alert=True)
        return
    
    followup = get_followup()
    if followup and followup.get("sticker"):
        update_followup({"sticker.enabled": True})
        await query.answer("✅ Sticker enabled", show_alert=False)
        logger.info(f"Followup sticker enabled by owner {query.from_user.id}")
    
    await manage_sticker(update, context)

# ==================== ENABLE MESSAGE ====================
async def enable_message(update, context):
    """Enable message followup"""
    query = update.callback_query
    await query.answer()
    
    if not is_owner(query.from_user.id):
        await query.answer("⛔ Only owner can use this feature", show_alert=True)
        return
    
    followup = get_followup()
    if followup and followup.get("message"):
        update_followup({"message.enabled": True})
        await query.answer("✅ Message enabled", show_alert=False)
        logger.info(f"Followup message enabled by owner {query.from_user.id}")
    
    await manage_message(update, context)

# ==================== DELETE STICKER ====================
async def delete_sticker(update, context):
    """Delete sticker from database"""
    query = update.callback_query
    await query.answer()
    
    if not is_owner(query.from_user.id):
        await query.answer("⛔ Only owner can use this feature", show_alert=True)
        return
    
    followups.update_one(
        {"_id": "global"},
        {"$unset": {"sticker": ""}}
    )
    
    await query.answer("✅ Sticker deleted", show_alert=False)
    logger.info(f"Followup sticker deleted by owner {query.from_user.id}")
    
    await show_followup_menu(update, context)

# ==================== DELETE MESSAGE ====================
async def delete_message(update, context):
    """Delete message from database"""
    query = update.callback_query
    await query.answer()
    
    if not is_owner(query.from_user.id):
        await query.answer("⛔ Only owner can use this feature", show_alert=True)
        return
    
    followups.update_one(
        {"_id": "global"},
        {"$unset": {"message": ""}}
    )
    
    await query.answer("✅ Message deleted", show_alert=False)
    logger.info(f"Followup message deleted by owner {query.from_user.id}")
    
    await show_followup_menu(update, context)

# ==================== SEND FOLLOWUPS (CALLED BY CREATE_POST) ====================
async def send_followups(context, channel_id):
    """
    Send sticker and message followups to channel
    CRITICAL: Called after episode post is sent
    
    AUTO CLEANUP: Deletes previous episode's ending sticker/message
    before sending new ones, then saves new IDs to DB.
    """
    from db import channel_endings
    from datetime import datetime
    
    followup = get_followup()
    
    if not followup:
        return
    
    # ===== STEP 1: Delete previous episode's ending message (NOT sticker) =====
    try:
        prev = channel_endings.find_one({"channel_id": str(channel_id)})
        if prev:
            # Delete old message only (sticker stays)
            old_message_id = prev.get("last_message_message_id")
            if old_message_id:
                try:
                    await context.bot.delete_message(
                        chat_id=channel_id,
                        message_id=old_message_id
                    )
                    logger.info(f"🗑 Deleted old ending message {old_message_id} from {channel_id}")
                except Exception:
                    pass  # Already deleted / not found / no rights — safe to ignore
    except Exception:
        pass  # DB read failed — don't crash posting flow
    
    # ===== STEP 2: Send new ending sticker + message =====
    new_sticker_msg_id = None
    new_message_msg_id = None
    
    try:
        # Send sticker if enabled
        if followup.get("sticker") and followup["sticker"].get("enabled"):
            db_msg_id = followup["sticker"]["db_msg_id"]
            sent = await context.bot.copy_message(
                chat_id=channel_id,
                from_chat_id=DB_CHANNEL_ID,
                message_id=db_msg_id
            )
            new_sticker_msg_id = sent.message_id
            logger.info(f"Followup sticker sent to {channel_id} (msg_id={new_sticker_msg_id})")
        
        # Send message if enabled
        if followup.get("message") and followup["message"].get("enabled"):
            db_msg_id = followup["message"]["db_msg_id"]
            sent = await context.bot.copy_message(
                chat_id=channel_id,
                from_chat_id=DB_CHANNEL_ID,
                message_id=db_msg_id
            )
            new_message_msg_id = sent.message_id
            logger.info(f"Followup message sent to {channel_id} (msg_id={new_message_msg_id})")
            
    except Exception as e:
        logger.error(f"Error sending followups to {channel_id}: {e}")
    
    # ===== STEP 3: Save new ending message IDs to DB =====
    try:
        if new_sticker_msg_id or new_message_msg_id:
            update_data = {"updated_at": datetime.utcnow()}
            if new_sticker_msg_id:
                update_data["last_sticker_message_id"] = new_sticker_msg_id
            if new_message_msg_id:
                update_data["last_message_message_id"] = new_message_msg_id
            
            channel_endings.update_one(
                {"channel_id": str(channel_id)},
                {"$set": update_data},
                upsert=True
            )
            logger.info(f"💾 Saved ending IDs for {channel_id}: sticker={new_sticker_msg_id}, msg={new_message_msg_id}")
    except Exception:
        pass  # DB write failed — don't crash posting flow

