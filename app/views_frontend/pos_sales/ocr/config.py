"""OCR view settings: tuning numbers and who may use the camera search."""
from ....utils.pos import ocr_core as core

# re-exported so old tuning / imports keep working
AUTO_ADD_MIN_SCORE = core.AUTO_ADD_MIN_SCORE
AUTO_ADD_MIN_GAP = core.AUTO_ADD_MIN_GAP
MIN_LIST_SCORE = core.MIN_LIST_SCORE
CATALOG_TTL = 120            # seconds the in-memory product index is reused
MAX_CATALOG = 60000
RATE_MATCH = 240             # scans per user per minute (the live camera does ~1-2 per second at most)
RATE_FEEDBACK = 120
LOG_DEDUPE_SECONDS = 10      # the live camera repeats the same text; one log row per text per user per 10 s

_PERMS = ('use_pos', 'create_sales', 'create_purchases', 'manage_orders')
