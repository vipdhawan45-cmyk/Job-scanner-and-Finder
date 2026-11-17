"""Runtime configuration, read from environment variables."""
from __future__ import annotations

import os


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    # Keyed aggregators (optional). JSearch aggregates LinkedIn, Indeed, Glassdoor, ZipRecruiter...
    rapidapi_key: str | None = os.getenv("RAPIDAPI_KEY") or None
    adzuna_app_id: str | None = os.getenv("ADZUNA_APP_ID") or None
    adzuna_app_key: str | None = os.getenv("ADZUNA_APP_KEY") or None
    adzuna_country: str = os.getenv("ADZUNA_COUNTRY", "in")

    # Direct scraping of LinkedIn's public guest job pages. Off by default: it is
    # against LinkedIn's User Agreement and is rate-limited / blocked aggressively.
    enable_linkedin_scraper: bool = _bool("ENABLE_LINKEDIN_SCRAPER")
    linkedin_detail_fetch: int = int(os.getenv("LINKEDIN_DETAIL_FETCH", "15"))

    # Bundled sample listings — used when DEMO_MODE is on or every live source fails.
    demo_mode: bool = _bool("DEMO_MODE")
    sample_fallback: bool = _bool("SAMPLE_FALLBACK", True)

    # Optional sentence-transformer embeddings for semantic matching.
    use_embeddings: bool = _bool("USE_EMBEDDINGS")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

    http_timeout: float = float(os.getenv("HTTP_TIMEOUT", "20"))
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", "900"))
    profile_ttl_seconds: int = int(os.getenv("PROFILE_TTL_SECONDS", "3600"))
    cors_origins: list[str] = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]


settings = Settings()
