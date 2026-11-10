"""
Helper Functions - FIXED
Added dual button routing to message router
"""

from db import sessions, admins, channels, menu_messages, formats, update_settings
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity, CallbackQuery
from telegram.error import BadRequest
from config import PAGE_SIZE, CHANNELS_PER_ROW, OWNER_ID
from collections import OrderedDict
import difflib
import logging
import os
import re
import unicodedata

logger = logging.getLogger(__name__)

# ==================== SAFE query.answer() (FIX: double-answer error) ====================
# Many handlers call query.answer() and then call another function that
# calls query.answer() AGAIN (e.g. toggle/delete update channel -> show_menu).
# Telegram rejects the 2nd answer ("query is too old / invalid") and the
# handler crashes before refreshing the menu. This patch makes answer()
# idempotent for the same callback query.
_ANSWERED = OrderedDict()
_orig_answer = CallbackQuery.answer

async def _safe_answer(self, *args, **kwargs):
    qid = self.id
    if qid in _ANSWERED:
        return True
    _ANSWERED[qid] = True
    while len(_ANSWERED) > 500:
        _ANSWERED.popitem(last=False)
    try:
        return await _orig_answer(self, *args, **kwargs)
    except BadRequest as e:
        logger.debug(f"query.answer ignored: {e}")
        return False

def patch_query_answer():
    """Call once at startup (main.py)."""
    if CallbackQuery.answer is not _safe_answer:
        CallbackQuery.answer = _safe_answer

# ==================== MARKDOWN ESCAPE ====================
def escape_md(text):
    """Escape legacy-Markdown special chars so titles/templates never break parse_mode."""
    if text is None:
        return ""
    return re.sub(r'([_*`\[])', lambda m: '\\' + m.group(1), str(text))

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
def _u16(text):
    """Length of text in UTF-16 code units (Telegram entity offsets use this)."""
    return len(text.encode("utf-16-le")) // 2

def _entity_to_dict(entity):
    if isinstance(entity, MessageEntity):
        d = {"type": entity.type, "offset": entity.offset, "length": entity.length}
        if entity.url:
            d["url"] = entity.url
        if entity.user:
            d["user"] = entity.user.id if hasattr(entity.user, "id") else entity.user
        if entity.language:
            d["language"] = entity.language
        if entity.custom_emoji_id:
            d["custom_emoji_id"] = entity.custom_emoji_id
        return d
    return dict(entity)

def adjust_caption_entities(caption, entities, placeholder="{episode}", replacement=""):
    """
    Replace placeholder in caption and shift entity offsets correctly.
    FIX: works in UTF-16 units (emoji before {episode} no longer break
    formatting) and handles the placeholder appearing more than once.
    """
    if not caption:
        return caption, (None if not entities else entities)

    new_caption = caption.replace(placeholder, replacement)

    if not entities:
        return new_caption, None

    if placeholder not in caption:
        return caption, entities

    # Occurrences of placeholder as (start_u16, end_u16)
    occ = []
    idx = 0
    while True:
        i = caption.find(placeholder, idx)
        if i == -1:
            break
        start_u = _u16(caption[:i])
        occ.append((start_u, start_u + _u16(placeholder)))
        idx = i + len(placeholder)

    rep_len = _u16(replacement)
    ph_len = _u16(placeholder)
    diff = rep_len - ph_len

    def map_pos(pos, is_end):
        shift = 0
        for k, (a, b) in enumerate(occ):
            if pos >= b:
                shift += diff
            elif pos > a:
                # inside a placeholder
                new_a = a + k * diff
                return new_a + rep_len if is_end else new_a
            else:
                break
        return pos + shift

    adjusted = []
    for entity in entities:
        d = _entity_to_dict(entity)
        old_start = d["offset"]
        old_end = old_start + d["length"]
        new_start = map_pos(old_start, False)
        new_end = map_pos(old_end, True)
        length = new_end - new_start
        if length <= 0:
            continue
        d["offset"] = new_start
        d["length"] = length
        adjusted.append(d)

    return new_caption, adjusted

# ==================== CHANNEL AUTO-DETECT (from file name) ====================
_TITLE_CUT_RE = re.compile(
    r'(?ix)'
    r'(?:[\s._\-]+|^)'
    r'(?:S\d{1,2}[\s._\-]*E\d{1,4}'          # S01E05
    r'|E\d{1,4}(?![a-z])'                      # E05
    r'|Ep\.?[\s._\-]*\d{1,4}'                 # Ep05
    r'|Episode[\s._\-]*\d{1,4}'               # Episode 5
    r'|\d{1,4}[\s._]*(?:480p|720p|1080p|2160p)' # 05 720p
    r'|480p|720p|1080p|2160p|4k|hdrip|144fps)'
)
_DASH_EP_RE = re.compile(r'\s-\s*\d{1,4}(?:\s|\.|$)')
_TAGS_RE = re.compile(r'\[[^\]]*\]|\([^)]*\)')

def _norm(text):
    text = unicodedata.normalize("NFKC", str(text or "")).casefold()
    return "".join(ch for ch in text if ch.isalnum())

def extract_title_from_filename(filename):
    """'[Grp] Solo.Leveling.S01E05.720p.mkv' -> 'Solo Leveling'"""
    name = os.path.basename(filename or "")
    base, ext = os.path.splitext(name)
    if ext and len(ext) <= 5:
        name = base
    name = _TAGS_RE.sub(" ", name)
    name = name.replace("_", " ").replace(".", " ")
    name = re.sub(r"\s+", " ", name).strip()
    m = _DASH_EP_RE.search(name)
    if m:
        name = name[:m.start()]
    m = _TITLE_CUT_RE.search(name)
    if m:
        name = name[:m.start()]
    return name.strip(" -._")

def detect_channel_from_filename(filename):
    """
    Match a file name against saved channel titles.
    Returns (status, channel_doc, candidates)
      status: "found" | "ambiguous" | "none"
    """
    title_part = extract_title_from_filename(filename)
    tp = _norm(title_part)

    name = os.path.basename(filename or "")
    base, ext = os.path.splitext(name)
    file_norm = _norm(base if ext and len(ext) <= 5 else name)

    scored = []
    for ch in channels.find():
        nt = _norm(ch.get("title", ""))
        if len(nt) < 3:
            continue
        score = 0
        if tp and nt == tp:
            score = 2000 + len(nt)
        elif nt in file_norm:
            score = 1000 + len(nt)
        elif len(tp) >= 4 and tp in nt:
            score = 500 + len(tp)
        elif tp:
            ratio = difflib.SequenceMatcher(None, tp, nt).ratio()
            if ratio >= 0.88:
                score = int(ratio * 100)
        if score:
            scored.append((score, ch))

    if not scored:
        return "none", None, []

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[0][0]
    best = [ch for sc, ch in scored if sc == top]
    if len(best) == 1:
        return "found", best[0], best
    return "ambiguous", None, best

# ==================== CHANNEL SETUP (format + update format) ====================
# A newly added channel is "in setup" (setup_done=False) until BOTH its
# format and its update format are saved. Old channels (no setup_done field)
# keep working exactly as before.
def channel_setup_state(channel_id):
    """Returns (has_format, has_update_format)."""
    has_fmt = bool(formats.find_one({"_id": channel_id}))
    cfg = update_settings.find_one({"_id": "global"}) or {}
    tpl = (cfg.get("update_channel_formats") or {}).get(channel_id)
    has_upd = bool(isinstance(tpl, dict) and tpl.get("caption"))
    return has_fmt, has_upd

def channel_ready(channel_id):
    """True if the channel may be used for posting."""
    ch = channels.find_one({"_id": channel_id})
    if not ch:
        return False
    if ch.get("setup_done") is False:
        return False
    return bool(formats.find_one({"_id": channel_id}))

def sync_channel_setup(channel_id):
    """Mark channel as set once both formats exist. Returns (has_fmt, has_upd, done)."""
    has_fmt, has_upd = channel_setup_state(channel_id)
    done = has_fmt and has_upd
    if done:
        channels.update_one({"_id": channel_id}, {"$set": {"setup_done": True}})
    return has_fmt, has_upd, done

def build_setup_buttons(channel_id):
    has_fmt, has_upd = channel_setup_state(channel_id)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(("✅ " if has_fmt else "📸 ") + "Set Format", callback_data=f"setfmt:{channel_id}:0")],
        [InlineKeyboardButton(("✅ " if has_upd else "📝 ") + "Set Update Format", callback_data=f"updatefmt:{channel_id}:0")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="menu:settings")]
    ])

def build_setup_text(channel_id, header="📡 *Channel Setup*"):
    ch = channels.find_one({"_id": channel_id}) or {}
    title = escape_md(ch.get("title", channel_id))
    has_fmt, has_upd = channel_setup_state(channel_id)
    return (
        f"{header}\n\n"
        f"*Channel:* {title}\n"
        f"*ID:* `{channel_id}`\n\n"
        f"{'✅' if has_fmt else '❌'} Format\n"
        f"{'✅' if has_upd else '❌'} Update Format\n\n"
        f"The channel becomes active only after *both* are set."
    )

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
        
        if ch.get("setup_done", ch.get("has_format")):
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
