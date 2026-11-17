from ..config import settings
from .base import JobSource, SearchQuery
from .linkedin import LinkedInGuestSource
from .public import AdzunaSource, ArbeitnowSource, JSearchSource, RemoteOKSource, RemotiveSource
from .sample import SampleSource


def build_sources() -> dict[str, JobSource]:
    sources: list[JobSource] = [
        JSearchSource(settings.rapidapi_key),
        LinkedInGuestSource(settings.enable_linkedin_scraper, settings.linkedin_detail_fetch),
        AdzunaSource(settings.adzuna_app_id, settings.adzuna_app_key, settings.adzuna_country),
        RemotiveSource(),
        RemoteOKSource(),
        ArbeitnowSource(),
        SampleSource(),
    ]
    return {s.name: s for s in sources}


__all__ = ["JobSource", "SearchQuery", "build_sources"]
