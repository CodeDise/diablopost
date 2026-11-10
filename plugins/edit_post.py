"""
Edit Post Plugin - STABLE
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, MessageEntity
from telegram.ext import CallbackQueryHandler, MessageHandler, filters
from plugins.helpers import (
    is_admin,
    get_session,
    update_session,
    clean_session,
    build_quality_buttons,
    parse_quality_links,
    show_menu_safe
)
from db import posts
import logging

logger = logging.getLogger(__name__)

# ==================== REGISTRATION ====================
def register(app):
    """Register edit post handlers"""
    app.add_handler(CallbackQueryHandler(start_edit, pattern="^settings:editpost$"))
    app.add_handler(CallbackQueryHandler(edit_caption_btn, pattern="^editcaption$"))
    app.add_handler(CallbackQueryHandler(edit_poster_btn, pattern="^editposter$"))
    app.add_handler(CallbackQueryHandler(edit_buttons_btn, pattern="^editbuttons$"))
    app.add_handler(CallbackQueryHandler(back_to_menu, pattern="^editback$"))
    app.add_handler(CallbackQueryHandler(ask_edit_caption, pattern="^askcaption$"))
    app.add_handler(CallbackQueryHandler(done_editing, pattern="^doneedit$"))
    
    app.add_handler(MessageHandler(
        filters.FORWARDED & ~filters.COMMAND,
        receive_forward,
        block=False
    ), group=1)
    
    app.add_handler(MessageHandler(
        filters.PHOTO & ~filters.COMMAND & ~filters.FORWARDED,
        apply_photo_edit,
        block=False
    ), group=2)

# ==================== START EDIT ====================
async def start_edit(update, context):
    """Start edit post flow"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    clean_session(query.from_user.id)
    
    update_session(query.from_user.id, {
        "step": "forward",
        "action": "edit_post"
    })
    
    try:
        await query.message.edit_text(
            "📝 *Edit Post*\n\n"
            "**Step-by-step guide:**\n\n"
            "**On Mobile:**\n"
            "1. Open your channel\n"
            "2. Find the post to edit\n"
            "3. Tap and hold the post\n"
            "4. Tap 'Forward'\n"
            "5. Select this chat\n"
            "6. Tap Send (arrow icon)\n\n"
            "**On Desktop:**\n"
            "1. Right-click the post\n"
            "2. Select 'Forward Message'\n"
            "3. Choose this chat\n"
            "4. Send\n\n"
            "⚠️ *Requirements:*\n"
            "• Post must be created by this bot\n"
            "• Forward from channel (not screenshot)\n"
            "• Bot must have edit permissions",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="menu:back")
            ]]),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error editing menu: {e}")

# ==================== RECEIVE FORWARD ====================
async def receive_forward(update, context):
    """Handle forwarded message"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    s = get_session(user_id)
    if not s:
        return
    
    if s.get("step") != "forward" or s.get("action") != "edit_post":
        return
    
    logger.info(f"=== FORWARD RECEIVED from user {user_id} ===")
    
    if not hasattr(update.message, 'forward_origin') or not update.message.forward_origin:
        await update.message.reply_text(
            "❌ *Invalid Message*\n\n"
            "This doesn't appear to be a forwarded message.\n\n"
            "Please forward a post from your channel.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="menu:back")
            ]]),
            parse_mode="Markdown"
        )
        return
    
    forward_origin = update.message.forward_origin
    
    channel_id = None
    message_id = None
    
    if hasattr(forward_origin, 'chat'):
        channel_id = str(forward_origin.chat.id)
        message_id = forward_origin.message_id
        logger.info(f"✅ Channel forward: {channel_id}/{message_id}")
    
    elif hasattr(forward_origin, 'sender_user_name') or hasattr(forward_origin, 'sender_user'):
        await update.message.reply_text(
            "❌ *Wrong Source*\n\n"
            "This was forwarded from a user, not a channel.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="menu:back")
            ]]),
            parse_mode="Markdown"
        )
        return
    
    else:
        await update.message.reply_text(
            "❌ *Unsupported Forward Type*",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="menu:back")
            ]]),
            parse_mode="Markdown"
        )
        return
    
    if not channel_id or not message_id:
        await update.message.reply_text(
            "❌ *Failed to Extract Info*\n\n"
            "Could not get channel/message ID.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="menu:back")
            ]]),
            parse_mode="Markdown"
        )
        return
    
    logger.info(f"Searching database: {channel_id}/{message_id}")
    
    post = posts.find_one({
        "channel": channel_id,
        "message_id": message_id
    })
    
    if not post:
        total_posts = posts.count_documents({"channel": channel_id})
        
        await update.message.reply_text(
            "❌ *Post Not Found*\n\n"
            "This post is not in the database.\n\n"
            "**Possible reasons:**\n"
            "• Post was not created by this bot\n"
            "• Database was cleared\n\n"
            f"**Debug Info:**\n"
            f"• Channel ID: `{channel_id}`\n"
            f"• Message ID: `{message_id}`\n"
            f"• Posts in channel: {total_posts}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="menu:back")
            ]]),
            parse_mode="Markdown"
        )
        clean_session(user_id)
        return
    
    logger.info(f"✅ Post found")
    
    update_session(user_id, {
        "step": "edit_menu",
        "channel": channel_id,
        "message_id": message_id,
        "action": "edit_post"
    })
    
    buttons = [
        [InlineKeyboardButton("📝 Edit Caption", callback_data="editcaption")],
        [InlineKeyboardButton("📸 Edit Poster", callback_data="editposter")],
        [InlineKeyboardButton("🔗 Edit Buttons", callback_data="editbuttons")],
        [InlineKeyboardButton("🔙 Back", callback_data="editback")]
    ]
    
    from db import channels
    ch = channels.find_one({"_id": channel_id})
    channel_name = ch.get("title", "Unknown") if ch else "Unknown"
    
    await update.message.reply_text(
        "✅ *Post Found!*\n\n"
        f"*Channel:* {channel_name}\n"
        f"*Channel ID:* `{channel_id}`\n"
        f"*Message ID:* `{message_id}`\n"
        f"*Episode:* {post.get('episode', 'N/A')}\n\n"
        "Select what you want to edit:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )
    
    logger.info(f"✅ Edit menu shown")

# ==================== EDIT CAPTION BUTTON ====================
async def edit_caption_btn(update, context):
    """User selected to edit caption"""
    query = update.callback_query
    await query.answer()
    
    s = get_session(query.from_user.id)
    if not s or s.get("step") != "edit_menu":
        await query.answer("⚠️ Session expired", show_alert=True)
        return
    
    update_session(query.from_user.id, {
        "edit_type": "caption"
    })
    
    await query.message.reply_text(
        "📝 *Edit Caption*\n\n"
        "Send the new caption text.\n\n"
        "💡 *Formatting Tips:*\n"
        "• **Bold**: `**text**`\n"
        "• *Italic*: `*text*`\n"
        "• `Code`: `` `text` ``\n"
        "• > Quote: `> text`\n\n"
        "⚠️ *Important:*\n"
        "• Existing buttons will be preserved\n"
        "• Poster will remain unchanged",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back", callback_data="editback")
        ]]),
        parse_mode="Markdown"
    )

# ==================== EDIT POSTER BUTTON ====================
async def edit_poster_btn(update, context):
    """User selected to edit poster"""
    query = update.callback_query
    await query.answer()
    
    s = get_session(query.from_user.id)
    if not s or s.get("step") != "edit_menu":
        await query.answer("⚠️ Session expired", show_alert=True)
        return
    
    update_session(query.from_user.id, {
        "edit_type": "poster"
    })
    
    await query.message.reply_text(
        "📸 *Edit Poster*\n\n"
        "Send the new poster image.\n\n"
        "✅ Caption will be preserved\n"
        "✅ Buttons will be preserved",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back", callback_data="editback")
        ]]),
        parse_mode="Markdown"
    )

# ==================== EDIT BUTTONS BUTTON ====================
async def edit_buttons_btn(update, context):
    """User selected to edit buttons"""
    query = update.callback_query
    await query.answer()
    
    s = get_session(query.from_user.id)
    if not s or s.get("step") != "edit_menu":
        await query.answer("⚠️ Session expired", show_alert=True)
        return
    
    update_session(query.from_user.id, {
        "edit_type": "buttons"
    })
    
    await query.message.reply_text(
        "🔗 *Edit Buttons*\n\n"
        "Send quality links:\n\n"
        "**Single line:**\n"
        "`480p - link && 720p - link && 1080p - link`\n\n"
        "**Multiple lines:**\n"
        "```\n"
        "480p - https://example.com/480\n"
        "720p - https://example.com/720\n"
        "1080p - https://example.com/1080\n"
        "HDRip - https://example.com/hd\n"
        "```\n\n"
        "✅ Caption preserved\n"
        "✅ Poster preserved",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back", callback_data="editback")
        ]]),
        parse_mode="Markdown"
    )

# ==================== APPLY TEXT EDIT ====================
async def apply_text_edit(update, context):
    """Apply caption or buttons edit"""
    user_id = update.effective_user.id
    
    s = get_session(user_id)
    if not s or s.get("step") != "edit_menu":
        return
    
    edit_type = s.get("edit_type")
    if not edit_type or edit_type not in ["caption", "buttons"]:
        return
    
    channel_id = s["channel"]
    message_id = s["message_id"]
    
    post = posts.find_one({"channel": channel_id, "message_id": message_id})
    if not post:
        clean_session(user_id)
        await update.message.reply_text("❌ *Post Not Found*", parse_mode="Markdown")
        return
    
    # EDIT CAPTION
    if edit_type == "caption":
        new_caption = update.message.text
        
        entities_data = None
        if update.message.entities:
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
                for e in update.message.entities
            ]
        
        entities_objects = None
        if entities_data:
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
                for e in entities_data
            ]
        
        try:
            await context.bot.edit_message_caption(
                chat_id=channel_id,
                message_id=message_id,
                caption=new_caption,
                caption_entities=entities_objects
            )
            
            if post.get("buttons"):
                links = post["buttons"]
                quality_rows = build_quality_buttons(links, buttons_per_row=3)
                
                await context.bot.edit_message_reply_markup(
                    chat_id=channel_id,
                    message_id=message_id,
                    reply_markup=InlineKeyboardMarkup(quality_rows)
                )
            
            posts.update_one(
                {"channel": channel_id, "message_id": message_id},
                {"$set": {
                    "caption": new_caption,
                    "caption_entities": entities_data
                }}
            )
            
            # SYNC DB CHANNEL (NEW)
            from plugins.dual_update import sync_db_post
            await sync_db_post(context, channel_id, message_id)
            
            await update.message.reply_text(
                "✅ *Caption Edited Successfully!*\n\n"
                "✅ Caption changed\n"
                "✅ Buttons preserved\n"
                "✅ Poster unchanged",
                parse_mode="Markdown"
            )
            
            clean_session(user_id)
            await show_menu_safe(update, context, user_id)
            
            logger.info(f"Caption edited: {channel_id}/{message_id}")
            
        except Exception as e:
            logger.error(f"Caption edit failed: {e}")
            clean_session(user_id)
            
            await update.message.reply_text(
                f"❌ *Failed to Edit Caption*\n\nError: `{str(e)}`",
                parse_mode="Markdown"
            )
            
            await show_menu_safe(update, context, user_id)
    
    # EDIT BUTTONS
    elif edit_type == "buttons":
        links = parse_quality_links(update.message.text)
        
        if not links:
            await update.message.reply_text(
                "❌ *Invalid Format*\n\n"
                "Use: `quality - url && quality - url`",
                parse_mode="Markdown"
            )
            return
        
        quality_rows = build_quality_buttons(links, buttons_per_row=3)
        
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=channel_id,
                message_id=message_id,
                reply_markup=InlineKeyboardMarkup(quality_rows)
            )
            
            posts.update_one(
                {"channel": channel_id, "message_id": message_id},
                {"$set": {"buttons": links}}
            )
            
            # SYNC DB CHANNEL (NEW)
            from plugins.dual_update import sync_db_post
            await sync_db_post(context, channel_id, message_id)
            
            await update.message.reply_text(
                "✅ *Buttons Edited Successfully!*\n\n"
                "✅ Buttons changed\n"
                "✅ Caption preserved\n"
                "✅ Poster unchanged\n\n"
                "Do you want to edit caption also?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✏️ Edit Caption", callback_data="askcaption")],
                    [InlineKeyboardButton("❌ Done", callback_data="doneedit")]
                ]),
                parse_mode="Markdown"
            )
            
            logger.info(f"Buttons edited: {channel_id}/{message_id}")
            
        except Exception as e:
            logger.error(f"Buttons edit failed: {e}")
            clean_session(user_id)
            
            await update.message.reply_text(
                f"❌ *Failed to Edit Buttons*\n\nError: `{str(e)}`",
                parse_mode="Markdown"
            )
            
            await show_menu_safe(update, context, user_id)

# ==================== ASK EDIT CAPTION ====================
async def ask_edit_caption(update, context):
    """User clicked "Edit Caption" after editing buttons"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    s = get_session(user_id)
    
    if not s:
        await query.answer("⚠️ Session expired", show_alert=True)
        return
    
    update_session(user_id, {
        "edit_type": "caption"
    })
    
    await query.message.reply_text(
        "📝 *Edit Caption*\n\n"
        "Send the new caption text.\n\n"
        "💡 *Formatting Tips:*\n"
        "• **Bold**: `**text**`\n"
        "• *Italic*: `*text*`\n"
        "• `Code`: `` `text` ``\n"
        "• > Quote: `> text`\n\n"
        "⚠️ *Important:*\n"
        "• Existing buttons will be preserved\n"
        "• Poster will remain unchanged",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back", callback_data="editback")
        ]]),
        parse_mode="Markdown"
    )

# ==================== DONE EDITING ====================
async def done_editing(update, context):
    """User clicked "Done" - return to menu"""
    query = update.callback_query
    await query.answer("✅ Done")
    
    user_id = query.from_user.id
    
    clean_session(user_id)
    await show_menu_safe(update, context, user_id)

# ==================== APPLY PHOTO EDIT ====================
async def apply_photo_edit(update, context):
    """Apply poster edit"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    s = get_session(user_id)
    if not s or s.get("step") != "edit_menu":
        return
    
    edit_type = s.get("edit_type")
    if edit_type != "poster":
        return
    
    channel_id = s["channel"]
    message_id = s["message_id"]
    
    post = posts.find_one({"channel": channel_id, "message_id": message_id})
    if not post:
        clean_session(user_id)
        await update.message.reply_text("❌ *Post Not Found*", parse_mode="Markdown")
        return
    
    caption = post.get("caption", "")
    entities_data = post.get("caption_entities")
    
    entities_objects = None
    if entities_data:
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
            for e in entities_data
        ]
    
    try:
        new_photo_file_id = update.message.photo[-1].file_id
        
        media = InputMediaPhoto(
            media=new_photo_file_id,
            caption=caption,
            caption_entities=entities_objects
        )
        
        await context.bot.edit_message_media(
            chat_id=channel_id,
            message_id=message_id,
            media=media
        )
        
        if post.get("buttons"):
            links = post["buttons"]
            quality_rows = build_quality_buttons(links, buttons_per_row=3)
            
            await context.bot.edit_message_reply_markup(
                chat_id=channel_id,
                message_id=message_id,
                reply_markup=InlineKeyboardMarkup(quality_rows)
            )
        
        posts.update_one(
            {"channel": channel_id, "message_id": message_id},
            {"$set": {"poster_file_id": new_photo_file_id}}
        )
        
        # SYNC DB CHANNEL (NEW)
        from plugins.dual_update import sync_db_post
        await sync_db_post(context, channel_id, message_id)
        
        await update.message.reply_text(
            "✅ *Poster Edited Successfully!*\n\n"
            "✅ Poster changed\n"
            "✅ Caption preserved\n"
            "✅ Buttons preserved",
            parse_mode="Markdown"
        )
        
        clean_session(user_id)
        await show_menu_safe(update, context, user_id)
        
        logger.info(f"Poster edited: {channel_id}/{message_id}")
        
    except Exception as e:
        logger.error(f"Poster edit failed: {e}")
        clean_session(user_id)
        
        await update.message.reply_text(
            f"❌ *Failed to Edit Poster*\n\nError: `{str(e)}`",
            parse_mode="Markdown"
        )
        
        await show_menu_safe(update, context, user_id)

# ==================== BACK TO MENU ====================
async def back_to_menu(update, context):
    """Back button - return to menu"""
    query = update.callback_query
    await query.answer("🔙 Returning to menu...")
    
    user_id = query.from_user.id
    
    clean_session(user_id)
    
    logger.info(f"Edit cancelled by user {user_id}")
    
    await show_menu_safe(update, context, user_id)
