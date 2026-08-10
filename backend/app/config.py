from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> repo root (…/flowstudio_app)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Runtime settings. Prefers process env, then absolute repo-root `.env`."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "CreativeFlow Studio Backend"
    api_prefix: str = "/api/v1"
    creativeflow_root: Path | None = None
    remote_creativeflow_worker_url: str | None = None
    remote_creativeflow_real_jobs: bool = False
    remote_creativeflow_transfer_variant: str = "minimal"
    remote_creativeflow_auto_hy3d: bool = False
    remote_creativeflow_hy3d_max_candidates: int = 1
    remote_segmentation_adapter: str = "sam3d"
    remote_segmentation_real_default: bool = True
    remote_partfield_real_default: bool = True
    remote_partfield_wait_timeout_sec: float = 120
    remote_partfield_poll_interval_sec: float = 2
    iul_vlm_intent_url: str | None = None
    iul_vlm_fallback_urls: str | None = None
    iul_vlm_model: str = "qwen3-planner"
    iul_vlm_timeout_sec: float = 8
    iul_vlm_fallback_to_rules: bool = True
    divergence_llm_enabled: bool = True
    divergence_llm_timeout_sec: float = 15
    semantic_divergence_enabled: bool = True
    semantic_divergence_timeout_sec: float = 25
    semantic_divergence_vlm_timeout_sec: float = 35
    semantic_divergence_min_candidates: int = 9
    semantic_divergence_max_candidates: int = 15
    system_services_auto_bootstrap: bool = False
    system_services_enabled: bool = True
    gemini_rerepresentation_enabled: bool = False
    gemini_api_base: str = "https://128api.cn/v1"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    gemini_timeout_sec: float = 60
    gemini_max_retries: int = 2
    gemini_max_images: int = 4
    gemini_max_image_bytes: int = 5_242_880
    model_api_base: str | None = None
    model_api_key: str | None = None
    model_fast_text: str = "gemini-3.6-flash"
    model_reasoning_text: str = "gpt-5.5"
    model_image: str = "gpt-image-2"
    model_api_timeout_sec: float = 60
    model_api_max_retries: int = 2
    enable_legacy_local_models: bool = False
    enable_3d_generation: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
