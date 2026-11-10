"""
plugins/saved_posts.py - EXTENDED WITH DELETE OPTIONS
Saved Posts Feature with Resend + Sticker Support + Channel Selection + DELETE
ABSOLUTE: Resend logic UNTOUCHED - only ADDED delete options
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity
from telegram.ext import CallbackQueryHandler, MessageHandler, filters
from plugins.helpers import (
    is_admin,
    update_session,
    get_session,
    clean_session,
    build_quality_buttons
)
from db import saved_posts, channels, followups
from config import DB_CHANNEL_ID, PAGE_SIZE
from datetime import datetime
import logging
import re

logger = logging.getLogger(__name__)

def register(app):
    # EXISTING HANDLERS (UNTOUCHED)
    app.add_handler(CallbackQueryHandler(show_saved_posts_menu, pattern="^settings:savedposts$"))
    app.add_handler(CallbackQueryHandler(show_channel_list, pattern="^savedposts:channels$"))
    app.add_handler(CallbackQueryHandler(show_episodes, pattern="^savedposts:episodes:"))
    app.add_handler(CallbackQueryHandler(resend_single_ask, pattern="^savedposts:resend:"))
    app.add_handler(CallbackQueryHandler(resend_all_ask, pattern="^savedposts:resendall:"))
    app.add_handler(CallbackQueryHandler(resend_single_sticker_choice, pattern="^savedposts:single:sticker:"))
    app.add_handler(CallbackQueryHandler(resend_all_sticker_choice, pattern="^savedposts:all:sticker:"))
    app.add_handler(CallbackQueryHandler(pagination_episodes, pattern="^savedposts:page:"))
    app.add_handler(CallbackQueryHandler(cancel_resend, pattern="^savedposts:cancel"))
    
    # NEW DELETE HANDLERS
    app.add_handler(CallbackQueryHandler(delete_single_confirm, pattern="^savedposts:delete:single:"))
    app.add_handler(CallbackQueryHandler(delete_single_execute, pattern="^savedposts:delete:execute:"))
    app.add_handler(CallbackQueryHandler(delete_all_confirm, pattern="^savedposts:delete:all:"))
    app.add_handler(CallbackQueryHandler(delete_all_execute, pattern="^savedposts:delete:allexecute:"))
    app.add_handler(CallbackQueryHandler(cancel_delete, pattern="^savedposts:delete:cancel:"))
    
    # EXISTING TEXT HANDLER (UNTOUCHED)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        receive_target_channel,
        block=False
    ), group=10)

# ==================== EXISTING SAVE FUNCTION (UNTOUCHED) ====================
async def save_post_to_db(context, channel_id, original_message_id, episode, poster_file_id, caption, caption_entities, buttons):
    """
    SAVE POST HOOK
    Called after successful post send
    """
    try:
        quality_rows = build_quality_buttons(buttons, buttons_per_row=3)
        
        entities_objects = None
        if caption_entities:
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
                for e in caption_entities
            ]
        
        db_channel_message_id = None
        
        try:
            db_msg = await context.bot.send_photo(
                chat_id=DB_CHANNEL_ID,
                photo=poster_file_id,
                caption=caption,
                caption_entities=entities_objects,
                reply_markup=InlineKeyboardMarkup(quality_rows),
                disable_notification=True
            )
            db_channel_message_id = db_msg.message_id
            logger.info(f"✅ Post saved to DB channel: {db_channel_message_id}")
        except Exception as e:
            logger.error(f"⚠️ DB channel save failed (non-critical): {e}")
        
        saved_posts.insert_one({
            "channel_id": channel_id,
            "original_message_id": original_message_id,
            "db_channel_message_id": db_channel_message_id,
            "episode": episode,
            "poster_file_id": poster_file_id,
            "caption": caption,
            "caption_entities": caption_entities,
            "buttons": buttons,
            "created_at": datetime.utcnow()
        })
        
        logger.info(f"✅ Post metadata saved: {channel_id}/{original_message_id}")
        
    except Exception as e:
        logger.error(f"⚠️ Save post failed (non-critical): {e}")

# ==================== EXISTING MENU (UNTOUCHED) ====================
async def show_saved_posts_menu(update, context):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    total_saved = saved_posts.count_documents({})
    
    try:
        await query.message.edit_text(
            f"💾 *Saved Posts*\n\n"
            f"*Total Saved:* {total_saved}\n\n"
            f"All posts are backed up in DB channel.\n"
            f"You can resend posts to same or different channel.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📂 View by Channel", callback_data="savedposts:channels")],
                [InlineKeyboardButton("🔙 Back", callback_data="menu:settings")]
            ]),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error showing saved posts menu: {e}")

# ==================== EXISTING CHANNEL LIST (UNTOUCHED) ====================
async def show_channel_list(update, context):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    pipeline = [
        {"$group": {
            "_id": "$channel_id",
            "count": {"$sum": 1}
        }}
    ]
    
    channel_stats = list(saved_posts.aggregate(pipeline))
    
    if not channel_stats:
        await query.answer("❌ No saved posts found", show_alert=True)
        return
    
    buttons = []
    
    for stat in channel_stats:
        channel_id = stat["_id"]
        count = stat["count"]
        
        ch = channels.find_one({"_id": channel_id})
        channel_title = ch.get("title", "Unknown") if ch else "Unknown"
        
        buttons.append([InlineKeyboardButton(
            f"{channel_title} ({count} posts)",
            callback_data=f"savedposts:episodes:{channel_id}:0"
        )])
    
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="settings:savedposts")])
    
    try:
        await query.message.edit_text(
            "📂 *Select Channel*\n\n"
            "Choose a channel to view saved posts:",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error showing channel list: {e}")

# ==================== EXTENDED EPISODE LIST (ADDED DELETE BUTTON) ====================
async def show_episodes(update, context):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    parts = query.data.split(":")
    channel_id = parts[2]
    page = int(parts[3])
    
    ch = channels.find_one({"_id": channel_id})
    channel_title = ch.get("title", "Unknown") if ch else "Unknown"
    
    all_posts = list(saved_posts.find({"channel_id": channel_id}).sort("created_at", -1))
    
    if not all_posts:
        await query.answer("❌ No posts found", show_alert=True)
        return
    
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_posts = all_posts[start:end]
    
    buttons = []
    
    for post in page_posts:
        episode = post["episode"]
        created = post["created_at"].strftime("%Y-%m-%d %H:%M")
        
        buttons.append([InlineKeyboardButton(
            f"📺 {episode} ({created})",
            callback_data=f"savedposts:resend:{channel_id}:{post['_id']}"
        )])
    
    nav = []
    if start > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"savedposts:page:{channel_id}:{page-1}"))
    if end < len(all_posts):
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"savedposts:page:{channel_id}:{page+1}"))
    
    if nav:
        buttons.append(nav)
    
    buttons.append([InlineKeyboardButton(
        "📤 Resend All",
        callback_data=f"savedposts:resendall:{channel_id}"
    )])
    
    # NEW: DELETE ALL BUTTON
    buttons.append([InlineKeyboardButton(
        "🗑 Delete All Saved Posts",
        callback_data=f"savedposts:delete:all:{channel_id}"
    )])
    
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="savedposts:channels")])
    
    try:
        await query.message.edit_text(
            f"📺 *{channel_title}*\n\n"
            f"*Total Posts:* {len(all_posts)}\n\n"
            f"Select episode to resend or delete:",
            parse_mode="Markdown"
        )
        
        await query.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logger.error(f"Error showing episodes: {e}")

# ==================== EXISTING RESEND SINGLE ASK (EXTENDED WITH DELETE) ====================
async def resend_single_ask(update, context):
    """Ask for target channel ID - EXTENDED with delete option"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    parts = query.data.split(":")
    source_channel_id = parts[2]
    post_id = parts[3]
    
    from bson import ObjectId
    post = saved_posts.find_one({"_id": ObjectId(post_id)})
    
    if not post:
        await query.answer("❌ Post not found", show_alert=True)
        return
    
    update_session(query.from_user.id, {
        "step": "resend_target_channel",
        "action": "resend_single",
        "source_channel_id": source_channel_id,
        "post_id": str(post_id),
        "episode": post["episode"]
    })
    
    try:
        await query.message.edit_text(
            f"📺 *Resend Post*\n\n"
            f"*Episode:* {post['episode']}\n\n"
            f"Send target channel ID where you want to repost:\n\n"
            f"*Format:* `-1001234567890`\n\n"
            f"⚠️ Bot must be admin in target channel",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 Delete This Post Instead", callback_data=f"savedposts:delete:single:{source_channel_id}:{post_id}")],
                [InlineKeyboardButton("🔙 Cancel", callback_data=f"savedposts:cancel:{source_channel_id}")]
            ]),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error asking target channel: {e}")

# ==================== EXISTING RESEND ALL ASK (UNTOUCHED) ====================
async def resend_all_ask(update, context):
    """Ask for target channel ID for bulk resend"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    parts = query.data.split(":")
    source_channel_id = parts[2]
    
    total = saved_posts.count_documents({"channel_id": source_channel_id})
    
    update_session(query.from_user.id, {
        "step": "resend_target_channel",
        "action": "resend_all",
        "source_channel_id": source_channel_id,
        "total": total
    })
    
    try:
        await query.message.edit_text(
            f"📤 *Resend All Posts*\n\n"
            f"*Total:* {total} posts\n\n"
            f"Send target channel ID where you want to repost:\n\n"
            f"*Format:* `-1001234567890`\n\n"
            f"⚠️ Bot must be admin in target channel",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Cancel", callback_data=f"savedposts:cancel:{source_channel_id}")
            ]]),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error asking target channel: {e}")

# ==================== EXISTING RECEIVE TARGET CHANNEL (UNTOUCHED) ====================
async def receive_target_channel(update, context):
    """Receive target channel ID and ask sticker preference"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    s = get_session(user_id)
    if not s or s.get("step") != "resend_target_channel":
        return
    
    target_channel_id = update.message.text.strip()
    
    if not re.match(r'^-100\d{10,}$', target_channel_id):
        await update.message.reply_text(
            "❌ *Invalid Channel ID Format*\n\n"
            "Channel ID must:\n"
            "• Start with `-100`\n"
            "• Followed by 10+ digits\n\n"
            "Example: `-1001234567890`",
            parse_mode="Markdown"
        )
        return
    
    try:
        chat = await context.bot.get_chat(target_channel_id)
        bot_member = await context.bot.get_chat_member(target_channel_id, context.bot.id)
        
        if bot_member.status not in ["administrator", "creator"]:
            await update.message.reply_text(
                f"❌ *Bot Not Admin*\n\n"
                f"Bot must be admin in target channel.",
                parse_mode="Markdown"
            )
            return
        
        update_session(user_id, {
            "target_channel_id": target_channel_id,
            "target_channel_title": chat.title if hasattr(chat, 'title') else target_channel_id
        })
        
        followup = followups.find_one({"_id": "global"})
        has_sticker = followup and followup.get("sticker") and followup["sticker"].get("enabled")
        
        action = s.get("action")
        
        if has_sticker:
            if action == "resend_single":
                episode = s.get("episode")
                await update.message.reply_text(
                    f"✅ *Target Channel Confirmed*\n\n"
                    f"*Episode:* {episode}\n"
                    f"*Target:* {chat.title}\n\n"
                    f"Send sticker with post?",
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("✅ Yes", callback_data=f"savedposts:single:sticker:yes"),
                            InlineKeyboardButton("❌ No", callback_data=f"savedposts:single:sticker:no")
                        ],
                        [InlineKeyboardButton("🔙 Cancel", callback_data=f"savedposts:cancel:{s['source_channel_id']}")]
                    ]),
                    parse_mode="Markdown"
                )
            else:
                total = s.get("total")
                await update.message.reply_text(
                    f"✅ *Target Channel Confirmed*\n\n"
                    f"*Total Posts:* {total}\n"
                    f"*Target:* {chat.title}\n\n"
                    f"Send sticker with posts?",
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("✅ Yes", callback_data=f"savedposts:all:sticker:yes"),
                            InlineKeyboardButton("❌ No", callback_data=f"savedposts:all:sticker:no")
                        ],
                        [InlineKeyboardButton("🔙 Cancel", callback_data=f"savedposts:cancel:{s['source_channel_id']}")]
                    ]),
                    parse_mode="Markdown"
                )
        else:
            if action == "resend_single":
                await execute_resend_single(update, context, send_sticker=False)
            else:
                await execute_resend_all(update, context, send_sticker=False)
        
    except Exception as e:
        logger.error(f"Error validating target channel: {e}")
        await update.message.reply_text(
            f"❌ *Cannot Access Channel*\n\n"
            f"Error: `{str(e)}`\n\n"
            f"Make sure bot is admin in the channel.",
            parse_mode="Markdown"
        )

# ==================== EXISTING STICKER CHOICES (UNTOUCHED) ====================
async def resend_single_sticker_choice(update, context):
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split(":")
    choice = parts[3]
    
    send_sticker = (choice == "yes")
    
    await execute_resend_single(update, context, send_sticker)

async def resend_all_sticker_choice(update, context):
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split(":")
    choice = parts[3]
    
    send_sticker = (choice == "yes")
    
    await execute_resend_all(update, context, send_sticker)

# ==================== EXISTING RESEND SINGLE (UNTOUCHED) ====================
async def execute_resend_single(update, context, send_sticker):
    user_id = update.callback_query.from_user.id if hasattr(update, 'callback_query') else update.effective_user.id
    
    s = get_session(user_id)
    if not s:
        return
    
    post_id = s.get("post_id")
    target_channel_id = s.get("target_channel_id")
    
    from bson import ObjectId
    post = saved_posts.find_one({"_id": ObjectId(post_id)})
    
    if not post:
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ Post not found",
            parse_mode="Markdown"
        )
        clean_session(user_id)
        return
    
    try:
        quality_rows = build_quality_buttons(post["buttons"], buttons_per_row=3)
        
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
        
        await context.bot.send_photo(
            chat_id=target_channel_id,
            photo=post["poster_file_id"],
            caption=post["caption"],
            caption_entities=entities_objects,
            reply_markup=InlineKeyboardMarkup(quality_rows),
            disable_notification=True
        )
        
        if send_sticker:
            try:
                followup = followups.find_one({"_id": "global"})
                if followup and followup.get("sticker"):
                    sticker_data = followup["sticker"]
                    db_msg_id = sticker_data.get("db_msg_id")
                    
                    if db_msg_id:
                        await context.bot.copy_message(
                            chat_id=target_channel_id,
                            from_chat_id=DB_CHANNEL_ID,
                            message_id=db_msg_id,
                            disable_notification=True
                        )
                        logger.info(f"✅ Sticker sent after resend")
            except Exception as e:
                logger.error(f"⚠️ Sticker send failed: {e}")
        
        target_title = s.get("target_channel_title", target_channel_id)
        
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ *Post Resent!*\n\n*Episode:* {post['episode']}\n*Target:* {target_title}",
            parse_mode="Markdown"
        )
        
        clean_session(user_id)
        
        logger.info(f"✅ Post resent: {target_channel_id}/{post['episode']}")
        
    except Exception as e:
        logger.error(f"Error resending post: {e}")
        await context.bot.send_message(
            chat_id=user_id,
            text=f"❌ *Failed to Resend*\n\nError: `{str(e)}`",
            parse_mode="Markdown"
        )
        clean_session(user_id)

# ==================== EXISTING RESEND ALL (UNTOUCHED) ====================
async def execute_resend_all(update, context, send_sticker):
    user_id = update.callback_query.from_user.id if hasattr(update, 'callback_query') else update.effective_user.id
    
    s = get_session(user_id)
    if not s:
        return
    
    source_channel_id = s.get("source_channel_id")
    target_channel_id = s.get("target_channel_id")
    target_title = s.get("target_channel_title", target_channel_id)
    
    all_posts = list(saved_posts.find({"channel_id": source_channel_id}).sort("created_at", 1))
    
    if not all_posts:
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ No posts to resend",
            parse_mode="Markdown"
        )
        clean_session(user_id)
        return
    
    success_count = 0
    fail_count = 0
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"📤 *Starting Resend*\n\n*Total:* {len(all_posts)} posts\n*Target:* {target_title}",
            parse_mode="Markdown"
        )
    except:
        pass
    
    for post in all_posts:
        try:
            quality_rows = build_quality_buttons(post["buttons"], buttons_per_row=3)
            
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
            
            await context.bot.send_photo(
                chat_id=target_channel_id,
                photo=post["poster_file_id"],
                caption=post["caption"],
                caption_entities=entities_objects,
                reply_markup=InlineKeyboardMarkup(quality_rows),
                disable_notification=True
            )
            
            if send_sticker:
                try:
                    followup = followups.find_one({"_id": "global"})
                    if followup and followup.get("sticker"):
                        sticker_data = followup["sticker"]
                        db_msg_id = sticker_data.get("db_msg_id")
                        
                        if db_msg_id:
                            await context.bot.copy_message(
                                chat_id=target_channel_id,
                                from_chat_id=DB_CHANNEL_ID,
                                message_id=db_msg_id,
                                disable_notification=True
                            )
                except Exception as e:
                    logger.error(f"⚠️ Sticker send failed: {e}")
            
            success_count += 1
            logger.info(f"✅ Resent: {post['episode']}")
            
        except Exception as e:
            fail_count += 1
            logger.error(f"❌ Failed to resend {post['episode']}: {e}")
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"✅ *Resend Complete!*\n\n"
                f"*Target:* {target_title}\n"
                f"*Success:* {success_count}\n"
                f"*Failed:* {fail_count}"
            ),
            parse_mode="Markdown"
        )
    except:
        pass
    
    clean_session(user_id)
    
    logger.info(f"✅ Bulk resend complete: {success_count} success, {fail_count} failed")

# ==================== EXISTING CANCEL (UNTOUCHED) ====================
async def cancel_resend(update, context):
    query = update.callback_query
    await query.answer("❌ Cancelled")
    
    parts = query.data.split(":")
    source_channel_id = parts[2]
    
    clean_session(query.from_user.id)
    
    query.data = f"savedposts:episodes:{source_channel_id}:0"
    await show_episodes(update, context)

# ==================== EXISTING PAGINATION (UNTOUCHED) ====================
async def pagination_episodes(update, context):
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split(":")
    channel_id = parts[2]
    page = int(parts[3])
    
    query.data = f"savedposts:episodes:{channel_id}:{page}"
    await show_episodes(update, context)

# ==================== NEW: DELETE SINGLE CONFIRM ====================
async def delete_single_confirm(update, context):
    """Confirm deletion of single post"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    parts = query.data.split(":")
    source_channel_id = parts[3]
    post_id = parts[4]
    
    from bson import ObjectId
    post = saved_posts.find_one({"_id": ObjectId(post_id)})
    
    if not post:
        await query.answer("❌ Post not found", show_alert=True)
        return
    
    try:
        await query.message.edit_text(
            f"⚠️ *Delete Backup Post*\n\n"
            f"*Episode:* {post['episode']}\n\n"
            f"Are you sure you want to delete this backup?\n\n"
            f"**This will:**\n"
            f"• Delete from saved_posts database\n"
            f"• Delete from DB channel backup\n\n"
            f"**This will NOT:**\n"
            f"• Delete from original channel",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Yes, Delete", callback_data=f"savedposts:delete:execute:{source_channel_id}:{post_id}")],
                [InlineKeyboardButton("❌ Cancel", callback_data=f"savedposts:delete:cancel:{source_channel_id}")]
            ]),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error showing delete confirm: {e}")

# ==================== NEW: DELETE SINGLE EXECUTE ====================
async def delete_single_execute(update, context):
    """Execute deletion of single post"""
    query = update.callback_query
    await query.answer("🗑 Deleting...")
    
    if not is_admin(query.from_user.id):
        return
    
    parts = query.data.split(":")
    source_channel_id = parts[3]
    post_id = parts[4]
    
    from bson import ObjectId
    post = saved_posts.find_one({"_id": ObjectId(post_id)})
    
    if not post:
        await query.answer("❌ Post not found", show_alert=True)
        return
    
    episode = post.get("episode", "Unknown")
    db_msg_id = post.get("db_channel_message_id")
    
    # Delete from DB channel (try, don't fail if error)
    if db_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=DB_CHANNEL_ID,
                message_id=db_msg_id
            )
            logger.info(f"✅ Deleted from DB channel: {db_msg_id}")
        except Exception as e:
            logger.error(f"⚠️ DB channel delete failed (non-critical): {e}")
    
    # Delete from database
    result = saved_posts.delete_one({"_id": ObjectId(post_id)})
    
    if result.deleted_count > 0:
        try:
            await query.message.edit_text(
                f"✅ *Backup Deleted*\n\n"
                f"*Episode:* {episode}\n\n"
                f"Backup has been removed from database and DB channel.",
                parse_mode="Markdown"
            )
        except:
            pass
        
        logger.info(f"✅ Deleted saved post: {episode}")
        
        # Return to episode list
        query.data = f"savedposts:episodes:{source_channel_id}:0"
        await show_episodes(update, context)
    else:
        await query.answer("❌ Delete failed", show_alert=True)

# ==================== NEW: DELETE ALL CONFIRM ====================
async def delete_all_confirm(update, context):
    """Confirm deletion of all posts for channel"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    parts = query.data.split(":")
    channel_id = parts[3]
    
    ch = channels.find_one({"_id": channel_id})
    channel_title = ch.get("title", "Unknown") if ch else "Unknown"
    
    total = saved_posts.count_documents({"channel_id": channel_id})
    
    if total == 0:
        await query.answer("❌ No posts to delete", show_alert=True)
        return
    
    try:
        await query.message.edit_text(
            f"⚠️ *Delete All Saved Posts*\n\n"
            f"*Channel:* {channel_title}\n"
            f"*Total Posts:* {total}\n\n"
            f"This will **permanently delete** all saved backups for this channel.\n\n"
            f"**This will:**\n"
            f"• Delete {total} posts from database\n"
            f"• Delete backups from DB channel\n\n"
            f"**This will NOT:**\n"
            f"• Delete from original channel\n\n"
            f"**Are you sure?**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 Confirm Delete All", callback_data=f"savedposts:delete:allexecute:{channel_id}")],
                [InlineKeyboardButton("❌ Cancel", callback_data=f"savedposts:delete:cancel:{channel_id}")]
            ]),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error showing delete all confirm: {e}")

# ==================== NEW: DELETE ALL EXECUTE ====================
async def delete_all_execute(update, context):
    """Execute deletion of all posts for channel"""
    query = update.callback_query
    await query.answer("🗑 Deleting all...")
    
    if not is_admin(query.from_user.id):
        return
    
    parts = query.data.split(":")
    channel_id = parts[3]
    
    ch = channels.find_one({"_id": channel_id})
    channel_title = ch.get("title", "Unknown") if ch else "Unknown"
    
    all_posts = list(saved_posts.find({"channel_id": channel_id}))
    
    if not all_posts:
        await query.answer("❌ No posts found", show_alert=True)
        return
    
    total = len(all_posts)
    db_deleted = 0
    db_failed = 0
    
    try:
        await query.message.edit_text(
            f"🗑 *Deleting...*\n\n"
            f"Progress: 0 / {total}",
            parse_mode="Markdown"
        )
    except:
        pass
    
    # Delete from DB channel first
    for idx, post in enumerate(all_posts, 1):
        db_msg_id = post.get("db_channel_message_id")
        
        if db_msg_id:
            try:
                await context.bot.delete_message(
                    chat_id=DB_CHANNEL_ID,
                    message_id=db_msg_id
                )
                db_deleted += 1
            except Exception as e:
                logger.error(f"⚠️ DB channel delete failed: {db_msg_id}: {e}")
                db_failed += 1
        
        # Update progress every 10 posts
        if idx % 10 == 0 or idx == total:
            try:
                await query.message.edit_text(
                    f"🗑 *Deleting...*\n\n"
                    f"Progress: {idx} / {total}",
                    parse_mode="Markdown"
                )
            except:
                pass
    
    # Delete from database
    result = saved_posts.delete_many({"channel_id": channel_id})
    
    try:
        await query.message.edit_text(
            f"✅ *All Backups Deleted*\n\n"
            f"*Channel:* {channel_title}\n"
            f"*Total Deleted:* {result.deleted_count}\n\n"
            f"**DB Channel:**\n"
            f"✅ Deleted: {db_deleted}\n"
            f"❌ Failed: {db_failed}",
            parse_mode="Markdown"
        )
    except:
        pass
    
    logger.info(f"✅ Deleted all saved posts for channel {channel_id}: {result.deleted_count} posts")
    
    # Return to channel list
    query.data = "savedposts:channels"
    await show_channel_list(update, context)

# ==================== NEW: CANCEL DELETE ====================
async def cancel_delete(update, context):
    """Cancel delete operation"""
    query = update.callback_query
    await query.answer("❌ Cancelled")
    
    parts = query.data.split(":")
    channel_id = parts[3]
    
    # Return to episode list
    query.data = f"savedposts:episodes:{channel_id}:0"
    await show_episodes(update, context)
