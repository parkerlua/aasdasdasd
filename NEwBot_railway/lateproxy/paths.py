"""Where things live on disk."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FONTS = ASSETS / "fonts"
BADGES = ASSETS / "badges"
ICONS_JSON = ASSETS / "icons.json"
DATA_DIR = ROOT / "data"  # runtime files (database). Not committed.
