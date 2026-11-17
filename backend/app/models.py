from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field

from bs4 import BeautifulSoup


@dataclass
class Job:
    title: str
    company: str
    url: str
    source: str
    description: str = ""
    location: str = ""
    remote: bool = False
    posted_at: str | None = None  # ISO 8601
    salary: str | None = None
    job_type: str | None = None
    tags: list[str] = field(default_factory=list)
    id: str = ""

    def __post_init__(self) -> None:
        self.title = clean_text(self.title)[:200]
        self.company = clean_text(self.company)[:120] or "Unknown company"
        self.description = clean_text(self.description)[:20000]
        self.location = clean_text(self.location)[:160]
        if not self.remote and re.search(r"\b(remote|anywhere|work from home|wfh)\b", f"{self.location} {self.title}", re.I):
            self.remote = True
        if not self.id:
            self.id = hashlib.sha1(f"{self.source}|{self.url}|{self.title}".encode()).hexdigest()[:16]

    @property
    def dedupe_key(self) -> str:
        norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())  # noqa: E731
        return f"{norm(self.title)}|{norm(self.company)}"

    def to_dict(self) -> dict:
        return asdict(self)


def clean_text(value: str | None) -> str:
    """Strip HTML and collapse whitespace."""
    if not value:
        return ""
    if "<" in value and ">" in value:
        value = BeautifulSoup(value, "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", value).strip()


def format_salary(lo, hi, currency: str = "", period: str = "") -> str | None:
    def fmt(v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        return f"{v / 1000:.0f}k" if v >= 1000 else f"{v:.0f}"

    lo_s, hi_s = fmt(lo), fmt(hi)
    if not lo_s and not hi_s:
        return None
    body = f"{lo_s}–{hi_s}" if lo_s and hi_s and lo_s != hi_s else (lo_s or hi_s)
    return " ".join(p for p in (currency, body, f"/{period}" if period else "") if p).replace(" /", "/")
