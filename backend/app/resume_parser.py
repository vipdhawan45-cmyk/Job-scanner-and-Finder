"""Turn an uploaded resume (PDF / DOCX / TXT / image) into a structured profile.

Design notes
* PDF text is extracted with pypdfium2 (PDFium, the engine in Chrome). It is ~60x
  faster and uses far less memory than pdfminer-based libraries, which matters on
  small (512 MB) hosting instances.
* Scanned PDFs and photos of resumes fall back to Tesseract OCR when installed.
* Experience is computed only from work-history lines, never from education dates.
"""
from __future__ import annotations

import io
import math
import logging
import re
import threading
from dataclasses import asdict, dataclass, field
from datetime import date

from .skills import GENERIC_SKILLS, ROLE_KEYWORDS, ROLE_NOUNS, extract_skills

log = logging.getLogger("jobfinder.resume")

MAX_RESUME_BYTES = 8 * 1024 * 1024
MAX_PDF_PAGES = 8
OCR_MAX_PAGES = 3
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
_ocr_lock = threading.Lock()  # OCR is memory-heavy: one at a time


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
    custom_skills: list[str] = field(default_factory=list)  # skills outside the taxonomy
    warnings: list[str] = field(default_factory=list)
    used_ocr: bool = False

    def public(self) -> dict:
        d = asdict(self)
        d.pop("text")
        return d


# --------------------------------------------------------------------------- text

def _ocr_available() -> bool:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _ocr_images(images) -> str:
    import pytesseract

    with _ocr_lock:
        return "\n".join(pytesseract.image_to_string(img, lang="eng", timeout=60) for img in images)


def _pdf_text(data: bytes) -> tuple[str, bool]:
    import pypdfium2 as pdfium

    try:
        doc = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        if "password" in str(exc).lower():
            raise ResumeError("This PDF is password-protected. Remove the password and upload it again.") from exc
        raise ResumeError("This PDF looks damaged. Try exporting it again, or upload a DOCX instead.") from exc
    try:
        pages = [doc[i] for i in range(min(len(doc), MAX_PDF_PAGES))]
        text = "\n".join(p.get_textpage().get_text_bounded() for p in pages)
        if len(text.strip()) >= 200 or not _ocr_available():
            return text, False
        # Little or no text layer: this is a scanned / image-only PDF.
        images = [p.render(scale=300 / 72, grayscale=True).to_pil() for p in pages[:OCR_MAX_PAGES]]
        return _ocr_images(images), True
    finally:
        doc.close()


def _image_text(data: bytes) -> str:
    if not _ocr_available():
        raise ResumeError("Reading images needs OCR, which isn't installed on this server. Upload a PDF or DOCX instead.")
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("L")
    if max(img.size) > 4000:
        img.thumbnail((4000, 4000))
    return _ocr_images([img])


def _docx_text(data: bytes) -> str:
    import docx

    doc = docx.Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:  # many resume templates are laid out in tables
        for row in table.rows:
            seen = []
            for c in row.cells:  # merged cells repeat; keep each once
                if c.text not in seen:
                    seen.append(c.text)
            parts.extend(seen)
    for section in doc.sections:
        parts.extend(p.text for p in section.header.paragraphs)
    return "\n".join(parts)


def extract_text(filename: str, data: bytes) -> tuple[str, bool]:
    """Return (text, used_ocr)."""
    if len(data) > MAX_RESUME_BYTES:
        raise ResumeError("Resume is larger than 8 MB. Please upload a smaller file.")
    name = (filename or "").lower()
    used_ocr = False
    try:
        if name.endswith(".pdf") or data[:5] == b"%PDF-":
            text, used_ocr = _pdf_text(data)
        elif name.endswith(".docx"):
            text = _docx_text(data)
        elif name.endswith((".txt", ".md")):
            text = data.decode("utf-8", errors="ignore")
        elif name.endswith(IMAGE_EXTS):
            text, used_ocr = _image_text(data), True
        elif name.endswith((".doc", ".rtf", ".odt", ".pages")):
            raise ResumeError("Old .doc / .rtf / .odt files aren't supported. Save it as PDF or DOCX and upload again.")
        else:
            raise ResumeError("Unsupported file type. Upload a PDF, DOCX, TXT or an image (JPG/PNG).")
    except ResumeError:
        raise
    except Exception as exc:  # corrupt files etc.
        log.warning("failed to read %s: %s", name, exc)
        raise ResumeError("We couldn't read this file. Try exporting it again as PDF, or upload a DOCX.") from exc

    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    if len(text) < 50:
        hint = "" if _ocr_available() else " If it's a scanned document, upload a text-based PDF or DOCX."
        raise ResumeError(f"We found almost no text in this file.{hint}")
    return text[:60000], used_ocr


# ------------------------------------------------------------------------ sections

_HEADINGS = {
    "experience": r"(?:work|professional|employment|career|relevant|industry)?\s*(?:experience|history|employment)(?:\s+details|\s+history|\s+summary)?|work\s*history|employment|internships?|experience",
    "education": r"education(?:al)?(?:\s+(?:qualifications?|details|background))?|academic(?:s|\s+(?:qualifications?|details|background|profile))?|qualifications?|scholastic.*",
    "skills": r"(?:technical|key|core|professional|it|software)?\s*(?:skills?|competenc(?:y|ies)|expertise|proficienc(?:y|ies))(?:\s*(?:&|and)\s*\w+)?|technologies|tools",
    "projects": r"(?:academic|personal|key|major|minor)?\s*projects?",
    "other": r"summary|profile|objective|career\s+objective|about\s+me|certifications?|achievements|awards|hobbies|interests|languages(?:\s+known)?|personal\s+(?:details|information|profile)|declaration|references|strengths|extra[-\s]?curricular.*|activities|publications|trainings?",
}
_HEADING_RE = [(k, re.compile(rf"^\W*(?:{v})\W*$", re.I)) for k, v in _HEADINGS.items()]
_INLINE_SKILLS = re.compile(r"^\W*(?:technical\s+|key\s+|core\s+)?skills?(?:\s+set)?\s*[:\-–]\s*(.+)$", re.I)


def split_sections(text: str) -> dict[str, list[str]]:
    """Group lines by resume section. Lines before the first heading go to 'header'."""
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if len(line) <= 45:
            for key, rx in _HEADING_RE:
                if rx.match(line):
                    current = key
                    sections.setdefault(key, [])
                    break
            else:
                sections.setdefault(current, []).append(line)
            continue
        sections.setdefault(current, []).append(line)
    return sections


# --------------------------------------------------------------------------- dates

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_MON = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE = rf"(?:{_MON}[\s,'’\-]*(?:\d{{4}}|\d{{2}})|\d{{1,2}}\s*[/\-.]\s*(?:19|20)\d{{2}}|(?:19|20)\d{{2}})"
_PRESENT = r"(?:present|current(?:ly)?|now|till\s+date|to\s+date|till\s+now|ongoing|today|date)"
_RANGE = re.compile(rf"({_DATE})\s*(?:-|–|—|to|till|until|~)\s*({_DATE}|{_PRESENT})", re.I)
_YEARS_STATED = re.compile(
    r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)(?:\s+and\s+\d{1,2}\s+months?)?(?:\s+of)?\s+"
    r"(?:total\s+|overall\s+|rich\s+|professional\s+|industry\s+|work\s+|hands[-\s]on\s+|relevant\s+)*experience", re.I)
_NOT_WORK = re.compile(
    r"\b(intern(ship)?|trainee|apprentice|project|b\.?\s?tech|b\.?e\.|m\.?\s?tech|b\.?sc|m\.?sc|b\.?com|m\.?com|bca|mca|mba|"
    r"bba|degree|bachelor|master|diploma|university|college|school|institute|cgpa|gpa|percentage|class\s+(x|xii)|"
    r"hsc|ssc|12th|10th|graduat|course|certificat)", re.I)


def _parse_date(token: str, today: date) -> tuple[int, int] | None:
    t = token.strip().lower()
    if re.fullmatch(_PRESENT, t, re.I):
        return today.year, today.month
    m = re.match(rf"({_MON})[\s,'’\-]*(\d{{4}}|\d{{2}})$", t, re.I)
    if m:
        y = int(m.group(2))
        y = y + 2000 if y < 100 and y <= today.year % 100 + 1 else (y + 1900 if y < 100 else y)
        return y, _MONTHS[m.group(1)[:3]]
    m = re.match(r"(\d{1,2})\s*[/\-.]\s*(\d{4})$", t)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(2)), int(m.group(1))
    m = re.match(r"(\d{4})$", t)
    if m:
        return int(m.group(1)), 1
    return None


def work_ranges(lines: list[str], today: date | None = None) -> list[tuple[int, int]]:
    """Employment periods as (start, end) month indices, ignoring education/internship lines."""
    today = today or date.today()
    now = today.year * 12 + today.month
    spans = []
    for line in lines:
        if _NOT_WORK.search(line):
            continue
        for a, b in _RANGE.findall(line):
            s, e = _parse_date(a, today), _parse_date(b, today)
            if not s or not e:
                continue
            si, ei = s[0] * 12 + s[1], e[0] * 12 + e[1]
            if 1970 * 12 <= si <= ei <= now + 1:
                spans.append((si, ei))
    return spans


def estimate_years(text: str, sections: dict[str, list[str]] | None = None, today: date | None = None) -> float:
    """Prefer an explicit 'N years of experience'; else merge employment date ranges."""
    stated = [float(m) for m in _YEARS_STATED.findall(text) if 0 < float(m) < 50]
    if stated:
        return max(stated)
    sections = sections or split_sections(text)
    if sections.get("experience"):
        lines = sections["experience"]
    else:  # no clear heading: use everything except education/projects
        lines = [ln for k, v in sections.items() if k not in ("education", "projects") for ln in v]
    spans = sorted(work_ranges(lines, today))
    if not spans:
        return 0.0
    total, (cs, ce) = 0, spans[0]
    for s, e in spans[1:]:
        if s <= ce:
            ce = max(ce, e)
        else:
            total += ce - cs
            cs, ce = s, e
    total += ce - cs
    return min(math.floor(total / 12 * 2 + 0.5) / 2, 45.0)  # nearest half year, rounding .25 up


def seniority_for(years: float, titles: list[str]) -> str:
    leader = any(re.search(r"\b(principal|staff|director|head|vp|chief|manager)\b", t) for t in titles)
    if years >= 8 or (leader and years >= 6):
        return "lead"
    if years >= 5:
        return "senior"
    if years >= 2:
        return "mid"
    if years >= 0.5:
        return "junior"
    return "entry"


# -------------------------------------------------------------------------- titles

_SPLIT = re.compile(r"\s+[|•·]\s+|\s*[|•·]\s*|\s+[–—-]\s+|\s*[–—]\s*|,\s+|\s+at\s+|\s+@\s+|:\s+|\(|\)|\t")
_BULLET = re.compile(r"^\s*[-•*▪●◦➢➤►✓o]\s")
_TITLE_OF = re.compile(r"^(head|director|vp|vice president|manager|lead|chief)\s+(of|-)\s+\w+", re.I)
_SENIORITY_WORDS = re.compile(r"\b(senior|sr\.?|junior|jr\.?|trainee|intern|i{1,3}|associate)\b", re.I)


def _title_candidates(line: str) -> list[str]:
    out = []
    for seg in _SPLIT.split(line):
        seg = re.sub(r"[^\w&/+.' -]", " ", seg or "").strip(" .-")
        words = seg.split()
        if not 1 <= len(words) <= 6 or any(ch.isdigit() for ch in seg):
            continue
        last = words[-1].lower().strip(".")
        if last in ROLE_NOUNS or _TITLE_OF.match(seg):
            if len(words) == 1 and last not in {"developer", "accountant", "teacher", "nurse", "architect",
                                                "surveyor", "draftsman", "pharmacist", "recruiter", "designer"}:
                continue  # a lone "Engineer" / "Manager" is too vague
            out.append(" ".join(words).lower())
    return out


def detect_titles(sections: dict[str, list[str]], text: str) -> list[str]:
    found: list[str] = []
    header = sections.get("header", [])[:5]
    exp = sections.get("experience") or [ln for k, v in sections.items()
                                         if k not in ("education", "skills", "projects", "other", "header") for ln in v]
    for line in header + exp:
        if _BULLET.match(line) or len(line) > 140 or "@" in line:
            continue
        for t in _title_candidates(line):
            if t not in found:
                found.append(t)
    lower = text.lower()
    for r in ROLE_KEYWORDS:  # catch titles inside sentences ("...as a data analyst")
        if r in lower and not any(r in f for f in found):
            found.append(r)
    return found[:6]


# ---------------------------------------------------------------------- other bits

_DEGREES = [
    (r"ph\.?\s?d|doctorate", "PhD"), (r"m\.?\s?tech", "M.Tech"), (r"\bm\.e\.", "M.E."), (r"\bmba\b", "MBA"),
    (r"\bmca\b", "MCA"), (r"\bm\.?\s?sc\b", "M.Sc"), (r"\bm\.?\s?com\b", "M.Com"), (r"\bm\.s\.|\bms\s+in\b", "M.S."),
    (r"\bmaster'?s?\b", "Master's"), (r"b\.?\s?tech", "B.Tech"), (r"\bb\.e\.|\bb\.e\b(?=\s+(?:in\s+)?\w)", "B.E."),
    (r"\bbca\b", "BCA"), (r"\bbba\b", "BBA"), (r"\bb\.?\s?sc\b", "B.Sc"), (r"\bb\.?\s?com\b", "B.Com"),
    (r"\bb\.a\.|\bba\s+in\b", "B.A."), (r"\bb\.s\.|\bbs\s+in\b", "B.S."), (r"\bbachelor'?s?\b", "Bachelor's"),
    (r"\bdiploma\b", "Diploma"),
]
_CITIES = (
    "bengaluru|bangalore|mumbai|delhi|new delhi|gurgaon|gurugram|noida|hyderabad|chennai|pune|kolkata|ahmedabad|"
    "jaipur|indore|bhopal|raipur|bhilai|nagpur|lucknow|kanpur|chandigarh|kochi|coimbatore|visakhapatnam|surat|"
    "vadodara|patna|ranchi|bhubaneswar|guwahati|dehradun|mysore|mysuru|thane|navi mumbai|sagar|jabalpur|gwalior|"
    "london|dubai|singapore|toronto|new york|san francisco|berlin|sydney|remote"
)
_LOCATION = re.compile(r"(?i:location|address|based in|city)\s*[:\-]?\s*([A-Za-z][A-Za-z .]+(?:,\s*[A-Za-z][A-Za-z .]+)?)")
_CITY = re.compile(rf"\b({_CITIES})\b", re.I)


def detect_location(sections: dict[str, list[str]], text: str) -> str | None:
    m = _LOCATION.search(text[:3000])
    if m:
        return m.group(1).strip().title()
    for line in sections.get("header", [])[:6]:
        if _NOT_WORK.search(line):  # "B.Tech, NIT Raipur" is the college, not where they live
            continue
        c = _CITY.search(line)
        if c:
            return c.group(1).title()
    return None


_NOT_SKILLS = {"hindi", "english", "marathi", "bengali", "tamil", "telugu", "kannada", "malayalam", "gujarati",
               "punjabi", "urdu", "odia", "french", "german", "spanish", "languages", "others", "etc", "basic",
               "intermediate", "advanced", "beginner", "good", "excellent"}


def parse_skill_section(sections: dict[str, list[str]], text: str) -> list[str]:
    """Free-form items listed under a Skills heading (or 'Skills: a, b, c')."""
    lines = list(sections.get("skills", []))
    lines += [m.group(1) for m in (_INLINE_SKILLS.match(ln) for ln in text.split("\n")) if m]
    items = []
    for line in lines:
        line = re.sub(r"^[^:]{1,30}:\s*", "", line) if ":" in line[:32] else line  # "Tools: X, Y"
        for item in re.split(r"[,;|•·/]|\s{2,}|\s-\s", line):
            item = item.strip(" .-*▪●◦")
            if 2 <= len(item) <= 40 and len(item.split()) <= 4 and not re.search(r"\d{3,}|@|http", item):
                items.append(item)
    return items


def parse_resume(filename: str, data: bytes) -> Profile:
    text, used_ocr = extract_text(filename, data)
    profile = build_profile(text)
    if used_ocr:
        profile.used_ocr = True
        profile.warnings.insert(0, "Your resume looked like a scanned image, so we read it with OCR. Please check the skills below.")
    return profile


def build_profile(text: str) -> Profile:
    sections = split_sections(text)
    skills = extract_skills(text)
    have = {s.lower() for s in skills}
    custom = []
    for item in parse_skill_section(sections, text):
        mapped = extract_skills(item)
        if mapped:
            continue  # already covered by the taxonomy
        name = item if any(c.isupper() for c in item) else item.title()
        if name.lower() not in have and name.lower() not in _NOT_SKILLS:
            have.add(name.lower())
            custom.append(name)
    custom = custom[:20]
    # Specific skills first, then soft skills.
    ordered = [s for s in skills if s not in GENERIC_SKILLS] + custom + [s for s in skills if s in GENERIC_SKILLS]

    titles = detect_titles(sections, text)
    years = estimate_years(text, sections)
    lower = text.lower()
    degrees = []
    for pat, label in _DEGREES:
        if re.search(pat, lower) and label not in degrees:
            degrees.append(label)

    warnings = []
    if not titles and len(ordered) < 3:
        warnings.append("This doesn't look much like a resume — we couldn't find job titles or skills. "
                        "Check you uploaded the right file, or type a job title in Keywords.")
    elif not titles:
        warnings.append("We couldn't detect your job title. Add one in Keywords for better results.")

    return Profile(
        text=text,
        skills=ordered[:50],
        titles=titles,
        years_experience=years,
        seniority=seniority_for(years, titles),
        education=degrees[:4],
        location=detect_location(sections, text),
        custom_skills=custom,
        warnings=warnings,
    )
