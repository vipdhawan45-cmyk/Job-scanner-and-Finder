"""Turn an uploaded resume (PDF / DOCX / TXT) into a structured profile."""
from __future__ import annotations

import io
import re
from dataclasses import asdict, dataclass, field
from datetime import date

from .skills import ROLE_KEYWORDS, extract_skills

MAX_RESUME_BYTES = 5 * 1024 * 1024


class ResumeError(ValueError):
    """Raised when a resume can't be read."""


@dataclass
class Profile:
    text: str
    skills: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)
    years_experience: float = 0.0
    seniority: str = "mid"
    education: list[str] = field(default_factory=list)
    location: str | None = None

    def public(self) -> dict:
        d = asdict(self)
        d.pop("text")
        return d


def extract_text(filename: str, data: bytes) -> str:
    if len(data) > MAX_RESUME_BYTES:
        raise ResumeError("Resume is larger than 5 MB.")
    name = (filename or "").lower()
    try:
        if name.endswith(".pdf") or data[:4] == b"%PDF":
            import pdfplumber

            with pdfplumber.open(io.BytesIO(data)) as pdf:
                text = "\n".join((p.extract_text() or "") for p in pdf.pages[:15])
        elif name.endswith(".docx"):
            import docx

            doc = docx.Document(io.BytesIO(data))
            parts = [p.text for p in doc.paragraphs]
            for table in doc.tables:
                for row in table.rows:
                    parts.append(" | ".join(c.text for c in row.cells))
            text = "\n".join(parts)
        elif name.endswith((".txt", ".md")):
            text = data.decode("utf-8", errors="ignore")
        else:
            raise ResumeError("Unsupported file type. Upload a PDF, DOCX or TXT file.")
    except ResumeError:
        raise
    except Exception as exc:  # corrupt / encrypted files
        raise ResumeError(f"Could not read the resume: {exc}") from exc
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) < 50:
        raise ResumeError("Very little text found. If this is a scanned PDF, upload a text-based version.")
    return text


_MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_RANGE = re.compile(
    rf"(?:{_MONTHS}\s*)?((?:19|20)\d{{2}})\s*(?:-|–|—|to)\s*(?:{_MONTHS}\s*)?((?:19|20)\d{{2}}|present|current|now|till date|date)",
    re.IGNORECASE,
)
_YEARS_STATED = re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years|yrs)(?:\s+of)?\s+(?:professional\s+|industry\s+|work\s+)?experience", re.I)


def estimate_years(text: str) -> float:
    """Prefer an explicit "N years of experience"; else merge employment date ranges."""
    stated = [float(m) for m in _YEARS_STATED.findall(text) if float(m) < 50]
    if stated:
        return max(stated)
    this_year = date.today().year
    spans: list[tuple[int, int]] = []
    for start, end in _RANGE.findall(text):
        s = int(start)
        e = this_year if not end[:1].isdigit() else int(end)
        if 1970 <= s <= e <= this_year:
            spans.append((s, e))
    if not spans:
        return 0.0
    spans.sort()
    total, (cs, ce) = 0, spans[0]
    for s, e in spans[1:]:
        if s <= ce:
            ce = max(ce, e)
        else:
            total += ce - cs
            cs, ce = s, e
    total += ce - cs
    return float(min(total, 45))


def seniority_for(years: float, text: str) -> str:
    t = text.lower()
    leader_title = re.search(r"\b(principal|staff engineer|director|head of|vp|chief)\b", t)
    if years >= 8 or (leader_title and years >= 6):
        return "lead"
    if years >= 5:
        return "senior"
    if years >= 2:
        return "mid"
    return "junior"


_DEGREES = re.compile(
    r"\b(ph\.?d|doctorate|master'?s?|m\.?s\.?c?|m\.?tech|m\.?e\.|mba|bachelor'?s?|b\.?s\.?c?|b\.?tech|b\.?e\.|b\.?a\.|bca|mca|diploma)\b",
    re.I,
)
_LOCATION = re.compile(r"(?i:location|address|based in)\s*[:\-]?\s*([A-Z][A-Za-z .]+(?:,\s*[A-Z][A-Za-z .]+)?)")


def parse_resume(filename: str, data: bytes) -> Profile:
    return build_profile(extract_text(filename, data))


def build_profile(text: str) -> Profile:
    lower = text.lower()
    titles = [r for r in ROLE_KEYWORDS if r in lower]
    # Drop generic titles that are contained in more specific ones.
    titles = [t for t in titles if not any(t != o and t in o for o in titles)]
    years = estimate_years(text)
    degrees = sorted({m.group(0).strip().upper().replace(".", "") for m in _DEGREES.finditer(text)})
    loc = _LOCATION.search(text)
    return Profile(
        text=text,
        skills=extract_skills(text),
        titles=titles[:5],
        years_experience=years,
        seniority=seniority_for(years, text),
        education=degrees[:4],
        location=loc.group(1).strip() if loc else None,
    )
