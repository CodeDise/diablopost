"""
Start Menu Plugin - STABLE
"""

from telegram.ext import CommandHandler, CallbackQueryHandler
from plugins.helpers import is_admin, clean_session, show_menu_safe
import logging

logger = logging.getLogger(__name__)

# ==================== REGISTRATION ====================
def register(app):
    """Register start handlers"""
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(back_to_main, pattern="^menu:back$"))

# ==================== START COMMAND ====================
async def start_command(update, context):
    """Show main menu"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text(
            "⛔ *Access Denied*\n\n"
            "This bot is for authorized admins only.",
            parse_mode="Markdown"
        )
        logger.warning(f"Unauthorized access attempt: {user_id}")
        return
    
    clean_session(user_id)
    await show_menu_safe(update, context, user_id)
    logger.info(f"User {user_id} started bot")

# ==================== BACK TO MAIN MENU ====================
async def back_to_main(update, context):
    """Handle back button"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if not is_admin(user_id):
        return
    
    clean_session(user_id)
    await show_menu_safe(update, context, user_id)
