from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from ..models import Job

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36"
)


@dataclass
class SearchQuery:
    keywords: str            # e.g. "python developer"
    location: str = ""       # free text, e.g. "Bangalore" or "" for anywhere
    remote_only: bool = False
    limit: int = 50


class JobSource(ABC):
    """A provider of job listings. Implementations must never raise for 'no results'."""

    name: str = "base"
    label: str = "Base"
    description: str = ""

    @property
    def enabled(self) -> bool:
        return True

    @property
    def disabled_reason(self) -> str | None:
        return None

    @abstractmethod
    async def search(self, client: httpx.AsyncClient, query: SearchQuery) -> list[Job]:
        ...

    def info(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "enabled": self.enabled,
            "disabled_reason": self.disabled_reason,
        }
