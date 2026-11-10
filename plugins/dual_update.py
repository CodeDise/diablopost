"""
Dual Update Plugin - TIMEOUT FIXED
Added retry logic and timeout handling for old posts
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity
from telegram.ext import CallbackQueryHandler, MessageHandler, filters
from plugins.helpers import (
    is_admin,
    update_session,
    get_session,
    clean_session,
    build_quality_buttons,
    parse_quality_links
)
from db import posts, saved_posts, channels, update_settings, formats
from config import DB_CHANNEL_ID
import logging
import re
import asyncio

logger = logging.getLogger(__name__)

# ==================== REGISTRATION ====================
def register(app):
    app.add_handler(CallbackQueryHandler(show_dual_settings, pattern="^settings:dualsettings$"))
    app.add_handler(CallbackQueryHandler(set_dual_channel_start, pattern="^dual:setchannel$"))
    app.add_handler(CallbackQueryHandler(enable_dual_redirect, pattern="^dual:enable$"))
    app.add_handler(CallbackQueryHandler(disable_dual_redirect, pattern="^dual:disable$"))
    app.add_handler(CallbackQueryHandler(delete_dual_channel, pattern="^dual:delete$"))
    app.add_handler(CallbackQueryHandler(manual_update_dual_start, pattern="^menu:adddual$"))
    app.add_handler(CallbackQueryHandler(send_dual_redirect_yes, pattern="^dual:sendyes$"))
    app.add_handler(CallbackQueryHandler(send_dual_redirect_no, pattern="^dual:sendno$"))
    app.add_handler(CallbackQueryHandler(cancel_dual, pattern="^dual:cancel$"))
    
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        receive_dual_channel_text,
        block=False
    ), group=11)
    
    app.add_handler(MessageHandler(
        filters.FORWARDED & ~filters.COMMAND,
        receive_dual_forward,
        block=False
    ), group=12)
    
    logger.info("✅ Dual update handlers registered")

def register_proceed(app):
    app.add_handler(CallbackQueryHandler(proceed_dual_update, pattern="^dual:proceed$"))
    logger.info("✅ Dual proceed handler registered")

def register_buttons(app):
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        receive_dual_buttons,
        block=False
    ), group=13)
    logger.info("✅ Dual button text handler registered at group 13")

# ==================== HELPER: SYNC DB POST ====================
async def sync_db_post(context, channel_id, message_id):
    try:
        logger.info(f"🔄 Syncing DB post: {channel_id}/{message_id}")
        
        saved_post = saved_posts.find_one({
            "channel_id": channel_id,
            "original_message_id": message_id
        })
        
        if not saved_post:
            logger.warning(f"No saved post found for {channel_id}/{message_id}")
            return
        
        db_msg_id = saved_post.get("db_channel_message_id")
        if not db_msg_id:
            logger.warning(f"No DB message ID for {channel_id}/{message_id}")
            return
        
        post = posts.find_one({"channel": channel_id, "message_id": message_id})
        if not post:
            logger.warning(f"Post not found: {channel_id}/{message_id}")
            return
        
        entities_objects = None
        if post.get("caption_entities"):
            entities_objects = [
                MessageEntity(
                    type=e["type"],
                    offset=e["offset"],
                    length=e["length"],
                    url=e.get("url"),
                    user=e.get("user"),
                    language=e.get("language"),
                    custom_emoji_id=e.get("custom_emoji_id")
                )
                for e in post["caption_entities"]
            ]
        
        await context.bot.edit_message_caption(
            chat_id=DB_CHANNEL_ID,
            message_id=db_msg_id,
            caption=post.get("caption", ""),
            caption_entities=entities_objects
        )
        
        if post.get("buttons"):
            quality_rows = build_quality_buttons(post["buttons"], buttons_per_row=3)
            await context.bot.edit_message_reply_markup(
                chat_id=DB_CHANNEL_ID,
                message_id=db_msg_id,
                reply_markup=InlineKeyboardMarkup(quality_rows)
            )
        
        logger.info(f"✅ DB channel synced: {DB_CHANNEL_ID}/{db_msg_id}")
        
    except Exception as e:
        logger.error(f"⚠️ DB sync failed: {channel_id}/{message_id}: {e}")

# ==================== HELPER: SEND DUAL REDIRECT ====================
async def send_dual_redirect_post(context, channel_id, message_id, caption, caption_entities, poster_file_id):
    try:
        logger.info(f"📤 Attempting to send dual redirect for {channel_id}/{message_id}")
        
        config = update_settings.find_one({"_id": "global"})
        
        if not config:
            logger.warning("No update settings found")
            return False
        
        dual_channel_id = config.get("dual_channel_id")
        dual_redirect_enabled = config.get("dual_redirect_enabled", False)
        
        logger.info(f"Dual channel ID: {dual_channel_id}, Enabled: {dual_redirect_enabled}")
        
        if not dual_channel_id or not dual_redirect_enabled:
            logger.info("Dual redirect not enabled or channel not set")
            return False
        
        ch = channels.find_one({"_id": channel_id})
        channel_username = None
        
        if ch:
            try:
                chat = await context.bot.get_chat(channel_id)
                if hasattr(chat, 'username') and chat.username:
                    channel_username = chat.username
            except:
                pass
        
        if channel_username:
            post_link = f"https://t.me/{channel_username}/{message_id}"
        else:
            post_link = f"https://t.me/c/{channel_id.replace('-100', '')}/{message_id}"
        
        logger.info(f"Post link generated: {post_link}")
        
        redirect_button = [[InlineKeyboardButton("⛩ Download Now ⛩", url=post_link)]]

        redirect_caption = caption
        redirect_caption_entities = caption_entities

        # Build caption from source channel format when episode is available
        # so redirect caption can reliably use {episode}.
        post_doc = posts.find_one({"channel": channel_id, "message_id": message_id})
        if post_doc and post_doc.get("episode"):
            fmt = formats.find_one({"_id": channel_id})
            if fmt and fmt.get("caption"):
                from plugins.helpers import adjust_caption_entities
                redirect_caption, redirect_caption_entities = adjust_caption_entities(
                    caption=fmt["caption"],
                    entities=fmt.get("caption_entities"),
                    placeholder="{episode}",
                    replacement=str(post_doc["episode"])
                )
        
        entities_objects = None
        if redirect_caption_entities:
            entities_objects = [
                MessageEntity(
                    type=e["type"],
                    offset=e["offset"],
                    length=e["length"],
                    url=e.get("url"),
                    user=e.get("user"),
                    language=e.get("language"),
                    custom_emoji_id=e.get("custom_emoji_id")
                )
                for e in redirect_caption_entities
            ]
        
        logger.info(f"Sending redirect post to {dual_channel_id}")
        
        await context.bot.send_photo(
            chat_id=dual_channel_id,
            photo=poster_file_id,
            caption=redirect_caption,
            caption_entities=entities_objects,
            reply_markup=InlineKeyboardMarkup(redirect_button),
            disable_notification=True
        )
        
        logger.info(f"✅ Dual redirect sent to {dual_channel_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Dual redirect failed: {e}", exc_info=True)
        return False

# ==================== SHOW DUAL SETTINGS ====================
async def show_dual_settings(update, context):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    config = update_settings.find_one({"_id": "global"})
    
    dual_channel_id = None
    dual_redirect_enabled = False
    
    if config:
        dual_channel_id = config.get("dual_channel_id")
        dual_redirect_enabled = config.get("dual_redirect_enabled", False)
    
    status_text = "❌ Not Set"
    if dual_channel_id:
        if dual_redirect_enabled:
            status_text = f"✅ Enabled\n*Channel:* `{dual_channel_id}`"
        else:
            status_text = f"🚫 Disabled\n*Channel:* `{dual_channel_id}`"
    
    buttons = []
    
    buttons.append([InlineKeyboardButton(
        "📡 Set Dual Update Channel",
        callback_data="dual:setchannel"
    )])
    
    if dual_channel_id:
        if dual_redirect_enabled:
            buttons.append([InlineKeyboardButton(
                "⛔ Disable Dual Redirect",
                callback_data="dual:disable"
            )])
        else:
            buttons.append([InlineKeyboardButton(
                "🔄 Enable Dual Redirect",
                callback_data="dual:enable"
            )])
        
        buttons.append([InlineKeyboardButton(
            "🗑 Delete Dual Channel",
            callback_data="dual:delete"
        )])
    
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="menu:settings")])
    
    try:
        await query.message.edit_text(
            f"⚙️ *Dual Update Settings*\n\n"
            f"*Status:* {status_text}\n\n"
            f"**Features:**\n"
            f"• Auto detect dual audio posts\n"
            f"• Send redirect to update channel",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error showing dual settings: {e}")

# ==================== SET DUAL CHANNEL START ====================
async def set_dual_channel_start(update, context):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    update_session(query.from_user.id, {
        "step": "dual_channel_input",
        "action": "set_dual_channel"
    })
    
    await query.message.reply_text(
        "📡 *Set Dual Update Channel*\n\n"
        "Send channel ID or @username:\n\n"
        "*Format:*\n"
        "• Channel ID: `-1001234567890`\n"
        "• Username: `@channelname`\n\n"
        "⚠️ Bot must be admin in the channel",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Cancel", callback_data="dual:cancel")
        ]]),
        parse_mode="Markdown"
    )

# ==================== RECEIVE DUAL CHANNEL TEXT ====================
async def receive_dual_channel_text(update, context):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    s = get_session(user_id)
    if not s or s.get("step") != "dual_channel_input":
        return
    
    channel_input = update.message.text.strip()
    
    channel_id = None
    
    if channel_input.startswith("@"):
        try:
            chat = await context.bot.get_chat(channel_input)
            channel_id = str(chat.id)
        except Exception as e:
            await update.message.reply_text(
                f"❌ *Cannot Access Channel*\n\n"
                f"Error: `{str(e)}`",
                parse_mode="Markdown"
            )
            return
    
    elif re.match(r'^-100\d{10,}$', channel_input):
        channel_id = channel_input
    
    else:
        await update.message.reply_text(
            "❌ *Invalid Format*\n\n"
            "Send: `-1001234567890` or `@username`",
            parse_mode="Markdown"
        )
        return
    
    try:
        bot_member = await context.bot.get_chat_member(channel_id, context.bot.id)
        
        if bot_member.status not in ["administrator", "creator"]:
            await update.message.reply_text(
                "❌ *Bot Not Admin*\n\n"
                "Bot must be admin with send messages permission.",
                parse_mode="Markdown"
            )
            return
        
        update_settings.update_one(
            {"_id": "global"},
            {"$set": {
                "dual_channel_id": channel_id,
                "dual_redirect_enabled": True
            }},
            upsert=True
        )
        
        clean_session(user_id)
        
        await update.message.reply_text(
            f"✅ *Dual Channel Set*\n\n"
            f"*Channel ID:* `{channel_id}`\n"
            f"*Status:* ✅ Enabled\n\n"
            f"Dual audio posts will auto-redirect here.",
            parse_mode="Markdown"
        )
        
        logger.info(f"Dual channel set: {channel_id} by user {user_id}")
        
    except Exception as e:
        logger.error(f"Error setting dual channel: {e}")
        await update.message.reply_text(
            f"❌ *Error*\n\n`{str(e)}`",
            parse_mode="Markdown"
        )

# ==================== ENABLE/DISABLE/DELETE DUAL REDIRECT ====================
async def enable_dual_redirect(update, context):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    update_settings.update_one(
        {"_id": "global"},
        {"$set": {"dual_redirect_enabled": True}}
    )
    
    await query.answer("✅ Dual redirect enabled")
    await show_dual_settings(update, context)

async def disable_dual_redirect(update, context):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    update_settings.update_one(
        {"_id": "global"},
        {"$set": {"dual_redirect_enabled": False}}
    )
    
    await query.answer("✅ Dual redirect disabled")
    await show_dual_settings(update, context)

async def delete_dual_channel(update, context):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    update_settings.update_one(
        {"_id": "global"},
        {"$set": {
            "dual_channel_id": None,
            "dual_redirect_enabled": False
        }}
    )
    
    await query.answer("✅ Dual channel deleted")
    await show_dual_settings(update, context)

# ==================== MANUAL UPDATE DUAL START ====================
async def manual_update_dual_start(update, context):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    logger.info(f"🔧 Manual dual update started by user {query.from_user.id}")
    
    update_session(query.from_user.id, {
        "step": "dual_forward",
        "action": "manual_dual"
    })
    
    await query.message.reply_text(
        "🔧 *Manual Update Dual*\n\n"
        "Forward the source episode post from your channel.\n\n"
        "The bot will:\n"
        "1. Let you replace buttons\n"
        "2. Edit audio line in caption\n"
        "3. Ask if you want to send redirect post",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Cancel", callback_data="dual:cancel")
        ]]),
        parse_mode="Markdown"
    )

# ==================== RECEIVE DUAL FORWARD ====================
async def receive_dual_forward(update, context):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    s = get_session(user_id)
    if not s or s.get("step") != "dual_forward":
        return
    
    logger.info(f"📨 Dual forward received from user {user_id}")
    
    if not hasattr(update.message, 'forward_origin') or not update.message.forward_origin:
        await update.message.reply_text("❌ Please forward from channel")
        return
    
    forward_origin = update.message.forward_origin
    
    if not hasattr(forward_origin, 'chat'):
        await update.message.reply_text("❌ Forward from channel, not user")
        return
    
    channel_id = str(forward_origin.chat.id)
    message_id = forward_origin.message_id
    
    logger.info(f"Forward details: channel={channel_id}, message={message_id}")
    
    post = posts.find_one({"channel": channel_id, "message_id": message_id})
    
    if not post:
        await update.message.reply_text(
            "❌ *Post Not Found*\n\n"
            "This post is not in the database.",
            parse_mode="Markdown"
        )
        clean_session(user_id)
        return
    
    logger.info(f"✅ Post found in database")
    
    original_caption = post.get("caption", "")
    original_buttons = post.get("buttons", [])
    original_entities = post.get("caption_entities", [])
    
    update_session(user_id, {
        "channel_id": channel_id,
        "message_id": message_id,
        "original_caption": original_caption,
        "original_buttons": original_buttons,
        "original_entities": original_entities,
        "poster_file_id": post.get("poster_file_id"),
        "step": "dual_buttons"
    })
    
    logger.info(f"Session updated, asking for buttons")
    
    await update.message.reply_text(
        f"✅ *Post Found*\n\n"
        f"*Channel:* `{channel_id}`\n"
        f"*Message ID:* `{message_id}`\n\n"
        f"**Step 1/3:** Send NEW buttons\n\n"
        f"Format:\n"
        f"`480p - link && 720p - link && 1080p - link`",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Cancel", callback_data="dual:cancel")
        ]]),
        parse_mode="Markdown"
    )

# ==================== RECEIVE NEW BUTTONS ====================
async def receive_dual_buttons(update, context):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        logger.info(f"User {user_id} not admin, skipping")
        return
    
    s = get_session(user_id)
    if not s:
        logger.info(f"No session for user {user_id}")
        return
        
    if s.get("step") != "dual_buttons":
        logger.info(f"Wrong step for user {user_id}: {s.get('step')}")
        return
    
    logger.info(f"🔘 receive_dual_buttons called for user {user_id}")
    logger.info(f"Message text: {update.message.text}")
    
    links = parse_quality_links(update.message.text)
    
    if not links:
        logger.warning(f"Invalid link format from user {user_id}")
        await update.message.reply_text(
            "❌ *Invalid Format*\n\n"
            "Use: `quality - url && quality - url`",
            parse_mode="Markdown"
        )
        return
    
    logger.info(f"✅ Links parsed successfully: {len(links)} buttons")
    
    update_session(user_id, {
        "new_buttons": links,
        "step": "dual_caption"
    })
    
    await update.message.reply_text(
        "✅ *Buttons Received*\n\n"
        "**Step 2/3:** Confirm caption edit\n\n"
        "This will replace the Audio line with:\n"
        "`Audio: Japanese & English`\n\n"
        "All other formatting will be preserved.\n\n"
        "Ready to proceed?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Proceed", callback_data="dual:proceed")],
            [InlineKeyboardButton("❌ Cancel", callback_data="dual:cancel")]
        ]),
        parse_mode="Markdown"
    )
    
    logger.info(f"✅ Sent proceed confirmation to user {user_id}")

# ==================== PROCEED WITH DUAL UPDATE (TIMEOUT FIXED) ====================
async def proceed_dual_update(update, context):
    """Execute dual update with retry and timeout handling for old posts"""
    query = update.callback_query
    await query.answer("🔄 Updating...")
    
    user_id = query.from_user.id
    s = get_session(user_id)
    
    if not s:
        logger.error("No session in proceed_dual_update")
        return
    
    logger.info(f"🔄 Proceeding with dual update for user {user_id}")
    
    channel_id = s.get("channel_id")
    message_id = s.get("message_id")
    original_caption = s.get("original_caption")
    original_entities = s.get("original_entities")
    new_buttons = s.get("new_buttons")
    
    logger.info(f"Updating post: {channel_id}/{message_id}")
    
    new_caption = re.sub(
        r'(?i)(Audio\s*:\s*)([^\n]*)',
        r'\1Japanese & English',
        original_caption
    )
    
    logger.info(f"Caption updated (audio line replaced)")
    
    entities_objects = None
    if original_entities:
        entities_objects = [
            MessageEntity(
                type=e["type"],
                offset=e["offset"],
                length=e["length"],
                url=e.get("url"),
                user=e.get("user"),
                language=e.get("language"),
                custom_emoji_id=e.get("custom_emoji_id")
            )
            for e in original_entities
        ]
    
    quality_rows = build_quality_buttons(new_buttons, buttons_per_row=3)
    
    caption_success = False
    button_success = False
    
    # Step 1: Edit caption WITH RETRY AND TIMEOUT
    max_retries = 3
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting caption edit (attempt {attempt + 1}/{max_retries})...")
            
            await context.bot.edit_message_caption(
                chat_id=channel_id,
                message_id=message_id,
                caption=new_caption,
                caption_entities=entities_objects,
                read_timeout=60,
                write_timeout=60,
                connect_timeout=30,
                pool_timeout=30
            )
            logger.info(f"✅ Caption edited in source channel")
            caption_success = True
            break
            
        except Exception as cap_error:
            error_str = str(cap_error).lower()
            if attempt < max_retries - 1:
                wait_time = 3 * (attempt + 1)
                logger.warning(f"Caption edit attempt {attempt + 1} failed: {cap_error}, retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"❌ Caption edit failed after {max_retries} attempts: {cap_error}")
    
    if not caption_success:
        await query.message.edit_text(
            "⚠️ *Caption Edit Failed*\n\n"
            "Could not edit caption (timeout on old post).\n\n"
            "**Options:**\n"
            "1. Wait a minute and try again\n"
            "2. Cancel and try later",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Try Again", callback_data="dual:proceed")],
                [InlineKeyboardButton("❌ Cancel", callback_data="dual:cancel")]
            ]),
            parse_mode="Markdown"
        )
        return
    
    # Delay between API calls to avoid Telegram conflicts on old posts
    await asyncio.sleep(2)
    
    # Step 2: Edit buttons WITH RETRY AND TIMEOUT
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting button edit (attempt {attempt + 1}/{max_retries})...")
            
            await context.bot.edit_message_reply_markup(
                chat_id=channel_id,
                message_id=message_id,
                reply_markup=InlineKeyboardMarkup(quality_rows),
                read_timeout=60,
                write_timeout=60,
                connect_timeout=30,
                pool_timeout=30
            )
            
            logger.info(f"✅ Buttons edited in source channel")
            button_success = True
            break
            
        except Exception as btn_error:
            if attempt < max_retries - 1:
                wait_time = 3 * (attempt + 1)
                logger.warning(f"Button edit attempt {attempt + 1} failed: {btn_error}, retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"❌ Button edit failed after {max_retries} attempts: {btn_error}")
    
    if not button_success:
        await query.message.edit_text(
            "⚠️ *Partial Update*\n\n"
            "• Caption updated ✅\n"
            "• Buttons failed ❌ (timeout)\n\n"
            "**This can happen with old posts. Options:**\n"
            "1. Wait a few minutes and try again\n"
            "2. Continue anyway to send redirect",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Try Again", callback_data="dual:proceed")],
                [InlineKeyboardButton("➡️ Skip & Send Redirect", callback_data="dual:sendyes")],
                [InlineKeyboardButton("❌ Cancel", callback_data="dual:cancel")]
            ]),
            parse_mode="Markdown"
        )
        return
    
    # Step 3: Update database
    try:
        posts.update_one(
            {"channel": channel_id, "message_id": message_id},
            {"$set": {
                "caption": new_caption,
                "caption_entities": original_entities,
                "buttons": new_buttons
            }}
        )
        logger.info(f"✅ Database updated")
        
        saved_posts.update_one(
            {"channel_id": channel_id, "original_message_id": message_id},
            {"$set": {
                "caption": new_caption,
                "caption_entities": original_entities,
                "buttons": new_buttons
            }}
        )
        logger.info(f"✅ Saved posts updated")
    except Exception as db_err:
        logger.error(f"DB update error (non-fatal): {db_err}")
    
    # Step 4: Sync to DB channel
    try:
        await sync_db_post(context, channel_id, message_id)
    except Exception as sync_err:
        logger.error(f"DB sync error (non-fatal): {sync_err}")
    
    update_session(user_id, {"new_caption": new_caption})
    
    # Step 5: Ask about redirect
    await query.message.edit_text(
        "✅ *Source Post Updated*\n\n"
        "Caption and buttons edited successfully.\n\n"
        "**Step 3/3:** Send update to dual channel?",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Yes", callback_data="dual:sendyes"),
                InlineKeyboardButton("❌ No", callback_data="dual:sendno")
            ]
        ]),
        parse_mode="Markdown"
    )
    
    logger.info(f"✅ Dual update applied: {channel_id}/{message_id}")

# ==================== SEND DUAL REDIRECT YES/NO ====================
async def send_dual_redirect_yes(update, context):
    query = update.callback_query
    await query.answer("📤 Sending...")
    
    user_id = query.from_user.id
    s = get_session(user_id)
    
    if not s:
        logger.error("No session in send_dual_redirect_yes")
        return
    
    logger.info(f"📤 User {user_id} chose to send redirect")
    
    channel_id = s.get("channel_id")
    message_id = s.get("message_id")
    new_caption = s.get("new_caption")
    original_entities = s.get("original_entities")
    poster_file_id = s.get("poster_file_id")
    
    success = await send_dual_redirect_post(
        context,
        channel_id,
        message_id,
        new_caption,
        original_entities,
        poster_file_id
    )
    
    if success:
        await query.message.edit_text(
            "✅ *Complete*\n\n"
            "• Source post updated\n"
            "• Redirect sent to dual channel",
            parse_mode="Markdown"
        )
        logger.info(f"✅ Complete dual update with redirect")
    else:
        await query.message.edit_text(
            "⚠️ *Partial Success*\n\n"
            "• Source post updated ✅\n"
            "• Redirect failed ❌\n\n"
            "Check dual channel settings.",
            parse_mode="Markdown"
        )
        logger.warning(f"⚠️ Redirect failed but post updated")
    
    clean_session(user_id)
    
    from plugins.helpers import build_main_menu_buttons, build_menu_text
    from db import menu_messages
    
    menu_text = build_menu_text()
    menu_buttons = build_main_menu_buttons(user_id)
    
    menu_msg = await context.bot.send_message(
        chat_id=user_id,
        text=menu_text,
        reply_markup=InlineKeyboardMarkup(menu_buttons),
        parse_mode="Markdown"
    )
    
    menu_messages.update_one(
        {"_id": str(user_id)},
        {"$set": {"message_id": menu_msg.message_id}},
        upsert=True
    )

async def send_dual_redirect_no(update, context):
    query = update.callback_query
    await query.answer("✅ Done")
    
    logger.info(f"User {query.from_user.id} chose NOT to send redirect")
    
    await query.message.edit_text(
        "✅ *Update Complete*\n\n"
        "Source post updated.\n"
        "No redirect sent.",
        parse_mode="Markdown"
    )
    
    user_id = query.from_user.id
    clean_session(user_id)
    
    from plugins.helpers import build_main_menu_buttons, build_menu_text
    from db import menu_messages
    
    menu_text = build_menu_text()
    menu_buttons = build_main_menu_buttons(user_id)
    
    menu_msg = await context.bot.send_message(
        chat_id=user_id,
        text=menu_text,
        reply_markup=InlineKeyboardMarkup(menu_buttons),
        parse_mode="Markdown"
    )
    
    menu_messages.update_one(
        {"_id": str(user_id)},
        {"$set": {"message_id": menu_msg.message_id}},
        upsert=True
    )

# ==================== CANCEL DUAL ====================
async def cancel_dual(update, context):
    query = update.callback_query
    await query.answer("❌ Cancelled")
    
    user_id = query.from_user.id
    clean_session(user_id)
    
    logger.info(f"Dual update cancelled by user {user_id}")
    
    from plugins.helpers import build_main_menu_buttons, build_menu_text
    from db import menu_messages
    
    menu_text = build_menu_text()
    menu_buttons = build_main_menu_buttons(user_id)
    
    menu_msg = await context.bot.send_message(
        chat_id=user_id,
        text=menu_text,
        reply_markup=InlineKeyboardMarkup(menu_buttons),
        parse_mode="Markdown"
    )
    
    menu_messages.update_one(
        {"_id": str(user_id)},
        {"$set": {"message_id": menu_msg.message_id}},
        upsert=True
    )

# ==================== AUTO DUAL DETECTION ====================
async def auto_detect_and_send_dual(context, channel_id, message_id, caption, caption_entities, poster_file_id):
    if not caption:
        return
    
    caption_lower = caption.lower()
    
    if "dual" in caption_lower or "japanese & english" in caption_lower:
        logger.info(f"🔍 Dual audio detected in post: {channel_id}/{message_id}")
        
        success = await send_dual_redirect_post(
            context,
            channel_id,
            message_id,
            caption,
            caption_entities,
            poster_file_id
        )
        
        if success:
            logger.info(f"✅ Auto dual redirect sent successfully")
        else:
            logger.warning(f"⚠️ Auto dual redirect failed")
