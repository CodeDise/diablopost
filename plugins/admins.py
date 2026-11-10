"""
Admin Management Plugin
Owner-only commands for managing admins
"""

from telegram.ext import CommandHandler, CallbackQueryHandler
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from plugins.helpers import is_owner, is_admin
from db import admins
from config import OWNER_ID
import logging

logger = logging.getLogger(__name__)

# ==================== REGISTRATION ====================
def register(app):
    """Register admin management handlers"""
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("removeadmin", remove_admin))
    app.add_handler(CommandHandler("admins", list_admins))
    app.add_handler(CallbackQueryHandler(show_admin_menu, pattern="^menu:admins$"))

# ==================== SHOW ADMIN MENU ====================
async def show_admin_menu(update, context):
    """Show admin management menu (owner only)"""
    query = update.callback_query
    await query.answer()
    
    if not is_owner(query.from_user.id):
        await query.answer("⛔ Owner only", show_alert=True)
        return
    
    # Get admin count
    admin_count = admins.count_documents({})
    
    try:
        await query.message.edit_text(
            f"👑 *Admin Management*\n\n"
            f"*Total Admins:* {admin_count}\n"
            f"*Owner:* {OWNER_ID}\n\n"
            f"**Commands:**\n"
            f"`/addadmin <user_id>` - Add admin\n"
            f"`/removeadmin <user_id>` - Remove admin\n"
            f"`/admins` - List all admins\n\n"
            f"⚠️ Owner cannot be removed",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="menu:back")
            ]])
        )
    except Exception as e:
        logger.error(f"Error showing admin menu: {e}")

# ==================== ADD ADMIN ====================
async def add_admin(update, context):
    """
    Add a new admin
    Usage: /addadmin <user_id>
    Owner only
    """
    user_id = update.effective_user.id
    
    # Owner check
    if not is_owner(user_id):
        await update.message.reply_text(
            "⛔ *Access Denied*\n\n"
            "Only the owner can add admins.",
            parse_mode="Markdown"
        )
        return
    
    # Validate arguments
    if not context.args or len(context.args) != 1:
        await update.message.reply_text(
            "❌ *Invalid Usage*\n\n"
            "*Usage:* `/addadmin <user_id>`\n\n"
            "*Example:* `/addadmin 123456789`\n\n"
            "Get user ID from @userinfobot",
            parse_mode="Markdown"
        )
        return
    
    try:
        new_admin_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ *Invalid User ID*\n\n"
            "User ID must be a number.\n\n"
            "Example: `123456789`",
            parse_mode="Markdown"
        )
        return
    
    # Check if already admin
    if admins.find_one({"user_id": new_admin_id}):
        await update.message.reply_text(
            f"⚠️ User `{new_admin_id}` is already an admin.",
            parse_mode="Markdown"
        )
        return
    
    # Add admin
    try:
        admins.insert_one({
            "user_id": new_admin_id,
            "is_owner": False
        })
        
        await update.message.reply_text(
            f"✅ *Admin Added*\n\n"
            f"*User ID:* `{new_admin_id}`\n\n"
            f"They can now use the bot.",
            parse_mode="Markdown"
        )
        
        logger.info(f"Admin added: {new_admin_id} by {user_id}")
        
    except Exception as e:
        logger.error(f"Error adding admin: {e}")
        await update.message.reply_text(
            f"❌ *Error Adding Admin*\n\n"
            f"Error: `{str(e)}`",
            parse_mode="Markdown"
        )

# ==================== REMOVE ADMIN ====================
async def remove_admin(update, context):
    """
    Remove an admin
    Usage: /removeadmin <user_id>
    Owner only, cannot remove owner
    """
    user_id = update.effective_user.id
    
    # Owner check
    if not is_owner(user_id):
        await update.message.reply_text(
            "⛔ *Access Denied*\n\n"
            "Only the owner can remove admins.",
            parse_mode="Markdown"
        )
        return
    
    # Validate arguments
    if not context.args or len(context.args) != 1:
        await update.message.reply_text(
            "❌ *Invalid Usage*\n\n"
            "*Usage:* `/removeadmin <user_id>`\n\n"
            "*Example:* `/removeadmin 123456789`",
            parse_mode="Markdown"
        )
        return
    
    try:
        remove_admin_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ *Invalid User ID*\n\n"
            "User ID must be a number.",
            parse_mode="Markdown"
        )
        return
    
    # Prevent removing owner
    if remove_admin_id == OWNER_ID:
        await update.message.reply_text(
            "⛔ *Cannot Remove Owner*\n\n"
            "The owner cannot be removed from admins.",
            parse_mode="Markdown"
        )
        return
    
    # Check if admin exists
    admin_doc = admins.find_one({"user_id": remove_admin_id})
    if not admin_doc:
        await update.message.reply_text(
            f"⚠️ User `{remove_admin_id}` is not an admin.",
            parse_mode="Markdown"
        )
        return
    
    # Prevent removing owner via is_owner flag
    if admin_doc.get("is_owner", False):
        await update.message.reply_text(
            "⛔ *Cannot Remove Owner*\n\n"
            "This user is marked as owner.",
            parse_mode="Markdown"
        )
        return
    
    # Remove admin
    try:
        result = admins.delete_one({
            "user_id": remove_admin_id,
            "is_owner": False  # Extra safety
        })
        
        if result.deleted_count > 0:
            await update.message.reply_text(
                f"✅ *Admin Removed*\n\n"
                f"*User ID:* `{remove_admin_id}`\n\n"
                f"They can no longer use the bot.",
                parse_mode="Markdown"
            )
            
            logger.info(f"Admin removed: {remove_admin_id} by {user_id}")
        else:
            await update.message.reply_text(
                "❌ Failed to remove admin.",
                parse_mode="Markdown"
            )
        
    except Exception as e:
        logger.error(f"Error removing admin: {e}")
        await update.message.reply_text(
            f"❌ *Error Removing Admin*\n\n"
            f"Error: `{str(e)}`",
            parse_mode="Markdown"
        )

# ==================== LIST ADMINS ====================
async def list_admins(update, context):
    """
    List all admins
    Usage: /admins
    Owner only
    """
    user_id = update.effective_user.id
    
    # Owner check
    if not is_owner(user_id):
        await update.message.reply_text(
            "⛔ *Access Denied*\n\n"
            "Only the owner can view admin list.",
            parse_mode="Markdown"
        )
        return
    
    # Get all admins
    all_admins = list(admins.find())
    
    if not all_admins:
        await update.message.reply_text(
            "⚠️ No admins found in database.\n\n"
            "This shouldn't happen - owner should exist.",
            parse_mode="Markdown"
        )
        return
    
    # Build admin list
    admin_list = "👑 *Admin List*\n\n"
    
    owner_count = 0
    regular_count = 0
    
    for admin in all_admins:
        admin_id = admin["user_id"]
        is_owner_flag = admin.get("is_owner", False)
        
        if is_owner_flag:
            admin_list += f"👑 `{admin_id}` (Owner)\n"
            owner_count += 1
        else:
            admin_list += f"👤 `{admin_id}` (Admin)\n"
            regular_count += 1
    
    admin_list += f"\n*Total:* {len(all_admins)}\n"
    admin_list += f"*Owners:* {owner_count}\n"
    admin_list += f"*Regular Admins:* {regular_count}"
    
    await update.message.reply_text(
        admin_list,
        parse_mode="Markdown"
    )
    
    logger.info(f"Admin list viewed by {user_id}")
