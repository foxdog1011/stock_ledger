"""Font configuration and path resolution for matplotlib and PIL rendering."""
from __future__ import annotations

import glob as _glob
import logging
from pathlib import Path

import matplotlib
import matplotlib.font_manager as fm
from PIL import ImageFont

logger = logging.getLogger(__name__)

# ── Known locations of Noto Sans CJK (installed via fonts-noto-cjk) ──────────

_NOTO_SANS_CJK_PATHS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]

# Module-level mutable state for resolved font
_CJK_FONT_PATH: str = ""
_CJK_FONT_PROP: fm.FontProperties | None = None


def setup_matplotlib_fonts() -> None:
    """Find and configure the first available CJK font for matplotlib."""
    global _CJK_FONT_PATH, _CJK_FONT_PROP

    candidates = list(_NOTO_SANS_CJK_PATHS)
    # Windows CJK fonts
    candidates += [
        "C:/Windows/Fonts/msjh.ttc",    # Microsoft JhengHei (繁體)
        "C:/Windows/Fonts/msyh.ttc",    # Microsoft YaHei (簡體)
        "C:/Windows/Fonts/mingliu.ttc", # MingLiU
    ]
    candidates += _glob.glob("/usr/share/fonts/**/*SansCJK*.ttc", recursive=True)
    candidates += _glob.glob("/usr/share/fonts/**/*SansCJK*.otf", recursive=True)

    for path in candidates:
        if Path(path).exists():
            try:
                fm.fontManager.addfont(path)
                prop = fm.FontProperties(fname=path)
                _CJK_FONT_PATH = path
                _CJK_FONT_PROP = prop
                matplotlib.rcParams["font.sans-serif"] = [prop.get_name(), "DejaVu Sans"]
                matplotlib.rcParams["axes.unicode_minus"] = False
                logger.info("CJK font ready: %s -> %s", path, prop.get_name())
                return
            except Exception as e:
                logger.debug("addfont failed for %s: %s", path, e)

    matplotlib.rcParams["axes.unicode_minus"] = False
    logger.warning("No CJK font found -- Chinese text will show as boxes")


def get_cjk_font_path() -> str:
    """Return the resolved CJK font file path (empty string if none found)."""
    return _CJK_FONT_PATH


def fp(size: int) -> fm.FontProperties:
    """Return FontProperties for CJK font at given size (bypasses family lookup)."""
    if _CJK_FONT_PROP is not None:
        return fm.FontProperties(fname=_CJK_FONT_PATH, size=size)
    return fm.FontProperties(size=size)


def pil_font(size: int) -> ImageFont.FreeTypeFont:
    """Load Noto Sans CJK at given size for PIL rendering."""
    if _CJK_FONT_PATH:
        try:
            return ImageFont.truetype(_CJK_FONT_PATH, size)
        except Exception:
            pass
    return ImageFont.load_default()


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    """Convert hex color string to (R, G, B) tuple."""
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


# Run font setup on import
setup_matplotlib_fonts()
