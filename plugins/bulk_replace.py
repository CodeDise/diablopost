"""
Bulk Bot Username Replacer Plugin
Selectively replace old bot username with new bot username in post buttons
UPDATED: Also replaces links in DB channel saved posts
"""

from telegram.ext import CommandHandler, CallbackQueryHandler
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from plugins.helpers import (
    is_admin,
    update_session,
    get_session,
    clean_session,
    show_menu_safe
)
from db import posts, saved_posts, channels
from config import DB_CHANNEL_ID
import logging
import re

logger = logging.getLogger(__name__)

def register(app):
    app.add_handler(CommandHandler("replace", start_replace))
    app.add_handler(CallbackQueryHandler(cancel_replace, pattern="^replace:cancel$"))
    app.add_handler(CallbackQueryHandler(execute_replace, pattern="^replace:execute$"))

async def start_replace(update, context):
    """Start bulk replace flow"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text(
            "⛔ *Access Denied*\n\n"
            "Only admins can use this command.",
            parse_mode="Markdown"
        )
        return
    
    clean_session(user_id)
    
    update_session(user_id, {
        "step": "replace_channel",
        "action": "bulk_replace"
    })
    
    await update.message.reply_text(
        "🔄 *Bulk Bot Username Replacer*\n\n"
        "**Step 1/3:** Send channel ID\n\n"
        "*Format:* `-1001234567890`",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Cancel", callback_data="replace:cancel")
        ]]),
        parse_mode="Markdown"
    )
    
    logger.info(f"Bulk replace started by user {user_id}")

async def receive_channel(update, context):
    """Receive channel ID"""
    user_id = update.effective_user.id
    
    s = get_session(user_id)
    if not s or s.get("step") != "replace_channel":
        return
    
    channel_id = update.message.text.strip()
    
    if not re.match(r'^-100\d{10,}$', channel_id):
        await update.message.reply_text(
            "❌ *Invalid Channel ID*\n\n"
            "Format: `-1001234567890`",
            parse_mode="Markdown"
        )
        return
    
    ch = channels.find_one({"_id": channel_id})
    if not ch:
        await update.message.reply_text(
            "❌ *Channel Not Found*\n\n"
            "This channel is not in the database.",
            parse_mode="Markdown"
        )
        return
    
    channel_title = ch.get("title", channel_id)
    
    update_session(user_id, {
        "step": "replace_old_bot",
        "channel_id": channel_id,
        "channel_title": channel_title
    })
    
    await update.message.reply_text(
        f"✅ *Channel Selected*\n\n"
        f"*Channel:* {channel_title}\n\n"
        f"**Step 2/3:** Send OLD bot username\n\n"
        f"*Format:* `@OldBot`",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Cancel", callback_data="replace:cancel")
        ]]),
        parse_mode="Markdown"
    )

async def receive_old_bot(update, context):
    """Receive old bot username"""
    user_id = update.effective_user.id
    
    s = get_session(user_id)
    if not s or s.get("step") != "replace_old_bot":
        return
    
    old_bot = update.message.text.strip()
    
    if not old_bot.startswith("@"):
        await update.message.reply_text(
            "❌ *Invalid Format*\n\n"
            "Username must start with `@`\n\n"
            "*Example:* `@OldBot`",
            parse_mode="Markdown"
        )
        return
    
    old_bot_clean = old_bot[1:]
    
    update_session(user_id, {
        "step": "replace_new_bot",
        "old_bot": old_bot,
        "old_bot_clean": old_bot_clean
    })
    
    await update.message.reply_text(
        f"✅ *Old Bot Set*\n\n"
        f"*Old Bot:* `{old_bot}`\n\n"
        f"**Step 3/3:** Send NEW bot username\n\n"
        f"*Format:* `@NewBot`",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Cancel", callback_data="replace:cancel")
        ]]),
        parse_mode="Markdown"
    )

async def receive_new_bot(update, context):
    """Receive new bot username"""
    user_id = update.effective_user.id
    
    s = get_session(user_id)
    if not s or s.get("step") != "replace_new_bot":
        return
    
    new_bot = update.message.text.strip()
    
    if not new_bot.startswith("@"):
        await update.message.reply_text(
            "❌ *Invalid Format*\n\n"
            "Username must start with `@`\n\n"
            "*Example:* `@NewBot`",
            parse_mode="Markdown"
        )
        return
    
    new_bot_clean = new_bot[1:]
    
    update_session(user_id, {
        "step": "replace_confirm",
        "new_bot": new_bot,
        "new_bot_clean": new_bot_clean
    })
    
    channel_title = s.get("channel_title")
    old_bot = s.get("old_bot")
    
    await update.message.reply_text(
        f"🔄 *Confirm Replacement*\n\n"
        f"*Channel:* {channel_title}\n"
        f"*Old Bot:* `{old_bot}`\n"
        f"*New Bot:* `{new_bot}`\n\n"
        f"This will replace ALL links from old bot with new bot in:\n"
        f"• Channel posts\n"
        f"• DB channel backups\n"
        f"• Saved posts database\n\n"
        f"**Are you sure?**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Start Replace", callback_data="replace:execute")],
            [InlineKeyboardButton("❌ Cancel", callback_data="replace:cancel")]
        ]),
        parse_mode="Markdown"
    )

async def cancel_replace(update, context):
    """Cancel replacement at any step"""
    query = update.callback_query
    await query.answer("❌ Cancelled")
    
    user_id = query.from_user.id
    
    clean_session(user_id)
    
    try:
        await query.message.edit_text(
            "❌ *Operation Cancelled*",
            parse_mode="Markdown"
        )
    except:
        pass
    
    await show_menu_safe(update, context, user_id)
    
    logger.info(f"Bulk replace cancelled by user {user_id}")

async def execute_replace(update, context):
    """Execute bulk replacement in channel, DB channel, and saved_posts"""
    query = update.callback_query
    await query.answer("🔄 Starting replacement...")
    
    user_id = query.from_user.id
    
    s = get_session(user_id)
    if not s or s.get("step") != "replace_confirm":
        await query.answer("⚠️ Session expired", show_alert=True)
        return
    
    channel_id = s.get("channel_id")
    old_bot_clean = s.get("old_bot_clean")
    new_bot_clean = s.get("new_bot_clean")
    
    # Get all posts for this channel
    all_posts = list(posts.find({"channel": channel_id}))
    
    if not all_posts:
        await query.message.edit_text(
            "⚠️ *No Posts Found*\n\n"
            "No posts found in this channel.",
            parse_mode="Markdown"
        )
        clean_session(user_id)
        return
    
    total = len(all_posts)
    channel_success = 0
    channel_fail = 0
    db_channel_success = 0
    db_channel_fail = 0
    no_match_count = 0
    
    try:
        await query.message.edit_text(
            f"🔄 *Replacing Links...*\n\n"
            f"Progress: 0 / {total}",
            parse_mode="Markdown"
        )
    except:
        pass
    
    for idx, post in enumerate(all_posts, 1):
        try:
            buttons = post.get("buttons")
            if not buttons:
                no_match_count += 1
                continue
            
            old_pattern = f"https://t.me/{old_bot_clean}?start="
            
            # Check if any button has old bot link
            has_match = False
            for quality, url in buttons:
                if old_pattern in url:
                    has_match = True
                    break
            
            if not has_match:
                no_match_count += 1
                continue
            
            # Create new buttons with replaced links
            new_buttons = []
            for quality, url in buttons:
                if old_pattern in url:
                    new_url = url.replace(
                        f"https://t.me/{old_bot_clean}",
                        f"https://t.me/{new_bot_clean}"
                    )
                    new_buttons.append([quality, new_url])
                else:
                    new_buttons.append([quality, url])
            
            from plugins.helpers import build_quality_buttons
            quality_rows = build_quality_buttons(new_buttons, buttons_per_row=3)
            
            # 1. REPLACE IN CHANNEL POST
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=channel_id,
                    message_id=post["message_id"],
                    reply_markup=InlineKeyboardMarkup(quality_rows)
                )
                channel_success += 1
                logger.info(f"✅ Channel post replaced: {channel_id}/{post['message_id']}")
            except Exception as e:
                logger.error(f"❌ Channel post replace failed: {channel_id}/{post['message_id']}: {e}")
                channel_fail += 1
            
            # 2. REPLACE IN DB CHANNEL BACKUP (if exists)
            saved_post = saved_posts.find_one({
                "channel_id": channel_id,
                "original_message_id": post["message_id"]
            })
            
            if saved_post and saved_post.get("db_channel_message_id"):
                db_msg_id = saved_post["db_channel_message_id"]
                try:
                    await context.bot.edit_message_reply_markup(
                        chat_id=DB_CHANNEL_ID,
                        message_id=db_msg_id,
                        reply_markup=InlineKeyboardMarkup(quality_rows)
                    )
                    db_channel_success += 1
                    logger.info(f"✅ DB channel post replaced: {DB_CHANNEL_ID}/{db_msg_id}")
                except Exception as e:
                    logger.error(f"❌ DB channel replace failed: {DB_CHANNEL_ID}/{db_msg_id}: {e}")
                    db_channel_fail += 1
            
            # 3. UPDATE DATABASE (posts + saved_posts)
            posts.update_one(
                {"channel": channel_id, "message_id": post["message_id"]},
                {"$set": {"buttons": new_buttons}}
            )
            
            saved_posts.update_one(
                {"channel_id": channel_id, "original_message_id": post["message_id"]},
                {"$set": {"buttons": new_buttons}}
            )
            
        except Exception as e:
            logger.error(f"Failed to process post {post.get('message_id')}: {e}")
        
        # Update progress every 10 posts or at the end
        if idx % 10 == 0 or idx == total:
            try:
                await query.message.edit_text(
                    f"🔄 *Replacing Links...*\n\n"
                    f"Progress: {idx} / {total}\n\n"
                    f"Channel: {channel_success} ✅ | {channel_fail} ❌\n"
                    f"DB Backup: {db_channel_success} ✅ | {db_channel_fail} ❌",
                    parse_mode="Markdown"
                )
            except:
                pass
    
    clean_session(user_id)
    
    # Final summary
    try:
        await query.message.edit_text(
            f"✅ *Replacement Complete!*\n\n"
            f"*Total Posts:* {total}\n"
            f"*No Match:* {no_match_count}\n\n"
            f"**Channel Posts:**\n"
            f"✅ Success: {channel_success}\n"
            f"❌ Failed: {channel_fail}\n\n"
            f"**DB Channel Backups:**\n"
            f"✅ Success: {db_channel_success}\n"
            f"❌ Failed: {db_channel_fail}\n\n"
            f"*Database updated for all posts.*",
            parse_mode="Markdown"
        )
    except:
        pass
    
    logger.info(
        f"Bulk replace complete: "
        f"Channel: {channel_success} success, {channel_fail} failed | "
        f"DB Channel: {db_channel_success} success, {db_channel_fail} failed"
    )

async def route_replace_text(update, context):
    """Route text messages for replace flow"""
    user_id = update.effective_user.id
    
    s = get_session(user_id)
    if not s or s.get("action") != "bulk_replace":
        return
    
    step = s.get("step")
    
    if step == "replace_channel":
        await receive_channel(update, context)
    elif step == "replace_old_bot":
        await receive_old_bot(update, context)
    elif step == "replace_new_bot":
        await receive_new_bot(update, context)
