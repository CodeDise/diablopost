"""
Plugins Package - Modular bot components
UPDATED: Added smart_collector
"""

from . import helpers
from . import start
from . import admins
from . import channels
from . import formats
from . import create_post
from . import edit_post
from . import settings
from . import followups
from . import update_channel
from . import saved_posts
from . import bulk_replace
from . import dual_update
from . import smart_collector  # NEW

__all__ = [
    'helpers',
    'start',
    'admins',
    'channels',
    'formats',
    'create_post',
    'edit_post',
    'settings',
    'followups',
    'update_channel',
    'saved_posts',
    'bulk_replace',
    'dual_update',
    'smart_collector'  # NEW
]

