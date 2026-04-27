"""Video engine — public API exports for video generation pipeline."""
from apps.api.services.video_engine.assembler import build_mp4, get_audio_duration
from apps.api.services.video_engine.constants import (
    SECTOR_SYMBOLS,
    SHORTS_SLOTS,
    SLIDE_SECONDS,
)
from apps.api.services.video_engine.data import (
    compute_foreign_net_k,
    get_chip_data,
    get_company_name,
    get_sector_chip,
)
from apps.api.services.video_engine.fonts import setup_matplotlib_fonts
from apps.api.services.video_engine.models import (
    ChipSummary,
    GenerateSectorRequest,
    GenerateSectorResponse,
    N8nGenerateRequest,
    N8nGenerateResponse,
    N8nUploadRequest,
    N8nUploadResponse,
    PickSectorRequest,
    PickSectorResponse,
    PickStockRequest,
    PickStockResponse,
    RotationPickResponse,
    SlotType,
    TdccPickResponse,
    TdccSummary,
    VideoRequest,
    WeeklyReviewResponse,
)
from apps.api.services.video_engine.parallel import render_slides_parallel
from apps.api.services.video_engine.pick_stock import (
    SLOT_CONFIG,
    build_chip_summary,
    build_pick_response,
    score_symbols_with_fallback,
)
from apps.api.services.video_engine.script_gen import openai_script
from apps.api.services.video_engine.slides import (
    make_cumulative_chart,
    make_foreign_chart,
    make_rotation_shorts_slide,
    make_sector_breakdown_chart,
    make_sector_title_slide,
    make_shorts_slide,
    make_stock_summary_slide,
    make_summary_slide,
    make_tdcc_shorts_slide,
    make_trends_shorts_slide,
    make_thumbnail,
    make_title_slide,
    make_trust_dealer_chart,
    make_weekly_review_summary_slide,
    make_weekly_review_title_slide,
)
from apps.api.services.video_engine.tts import (
    clean_script_for_tts,
    tts_edge,
    tts_to_mp3,
)

__all__ = [
    # assembler
    "build_mp4",
    "get_audio_duration",
    # constants
    "SECTOR_SYMBOLS",
    "SHORTS_SLOTS",
    "SLIDE_SECONDS",
    # data
    "compute_foreign_net_k",
    "get_chip_data",
    "get_company_name",
    "get_sector_chip",
    # fonts
    "setup_matplotlib_fonts",
    # models
    "ChipSummary",
    "GenerateSectorRequest",
    "GenerateSectorResponse",
    "N8nGenerateRequest",
    "N8nGenerateResponse",
    "N8nUploadRequest",
    "N8nUploadResponse",
    "PickSectorRequest",
    "PickSectorResponse",
    "PickStockRequest",
    "PickStockResponse",
    "RotationPickResponse",
    "SlotType",
    "TdccPickResponse",
    "TdccSummary",
    "VideoRequest",
    "WeeklyReviewResponse",
    # parallel
    "render_slides_parallel",
    # pick_stock
    "SLOT_CONFIG",
    "build_chip_summary",
    "build_pick_response",
    "score_symbols_with_fallback",
    # script_gen
    "openai_script",
    # slides
    "make_cumulative_chart",
    "make_foreign_chart",
    "make_rotation_shorts_slide",
    "make_sector_breakdown_chart",
    "make_sector_title_slide",
    "make_shorts_slide",
    "make_stock_summary_slide",
    "make_summary_slide",
    "make_tdcc_shorts_slide",
    "make_trends_shorts_slide",
    "make_thumbnail",
    "make_title_slide",
    "make_trust_dealer_chart",
    "make_weekly_review_summary_slide",
    "make_weekly_review_title_slide",
    # tts
    "clean_script_for_tts",
    "tts_edge",
    "tts_to_mp3",
]
