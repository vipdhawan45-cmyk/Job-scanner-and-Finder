import asyncio
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DEMO_MODE", "true")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.matcher import build_queries, experience_fit, filter_jobs, rank_jobs, required_years  # noqa: E402
from app.models import Job, clean_text, format_salary  # noqa: E402
from app.resume_parser import ResumeError, build_profile, estimate_years, extract_text  # noqa: E402
from app.skills import extract_skills  # noqa: E402
from app.sources.linkedin import parse_detail_html, parse_search_html  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
RESUME_TXT = (FIX / "sample_resume.txt").read_text()


# ---------- skills / parsing ----------

def test_skill_extraction_handles_symbols_and_ambiguous_words():
    s = extract_skills("C++, C#, Node, CI/CD and react.js. I rest on weekends and go hiking.")
    assert {"C++", "C#", "Node.js", "CI/CD", "React"} <= set(s)
    assert "REST APIs" not in s and "Go" not in s


@pytest.mark.parametrize("name", ["sample_resume.pdf", "sample_resume.docx", "sample_resume.txt"])
def test_extract_text_all_formats(name):
    text = extract_text(name, (FIX / name).read_bytes())
    assert "FastAPI" in text and "Kubernetes" in text


def test_rejects_unsupported_and_empty():
    with pytest.raises(ResumeError):
        extract_text("cv.exe", b"MZ" + b"0" * 100)
    with pytest.raises(ResumeError):
        extract_text("cv.txt", b"hi")


def test_profile_fields():
    p = build_profile(RESUME_TXT)
    assert p.years_experience == 6
    assert p.seniority == "senior"
    assert "software engineer" in p.titles
    assert {"Python", "FastAPI", "AWS", "Kubernetes"} <= set(p.skills)
    assert p.location and p.location.startswith("Bengaluru")


def test_years_from_date_ranges_merges_overlaps():
    assert estimate_years("Acme 2015 - 2018\nBeta 2017 - 2020\nGamma 2021 - 2022") == 6


# ---------- matcher ----------

def _job(title, desc, **kw):
    return Job(title=title, company="Co", url=f"https://x/{title}", source="t", description=desc, **kw)


def test_ranking_prefers_relevant_jobs():
    p = build_profile(RESUME_TXT)
    jobs = [
        _job("Registered Nurse", "Patient care in ICU. 3 years nursing experience."),
        _job("Senior Python Engineer", "5+ years. Python, FastAPI, PostgreSQL, Docker, AWS, Kubernetes."),
        _job("Java Developer", "Java, Spring Boot, Oracle. 4 years."),
    ]
    ranked = rank_jobs(p, jobs)
    assert ranked[0].job.title == "Senior Python Engineer"
    assert ranked[0].score > 70
    assert all(r.score < 25 for r in ranked[1:])  # unrelated roles stay low
    assert "Python" in ranked[0].matched_skills


def test_edited_skills_change_ranking():
    p = build_profile(RESUME_TXT)
    jobs = [_job("Flutter Developer", "Flutter, Dart, Firebase"), _job("Python Developer", "Python, Django")]
    assert rank_jobs(p, jobs)[0].job.title == "Python Developer"
    assert rank_jobs(p, jobs, skills=["Flutter"])[0].job.title == "Flutter Developer"


def test_required_years_and_fit():
    assert required_years(_job("Engineer", "Minimum 3+ years of experience")) == 3
    assert required_years(_job("Senior Engineer", "")) == 5
    assert required_years(_job("Junior Developer", "")) == 0
    assert experience_fit(6, 5) == 1.0
    assert experience_fit(1, 5) == 0.0
    assert experience_fit(3, None) == 0.75


def test_filter_jobs_location_and_remote():
    jobs = [_job("A", "", location="Pune, India"), _job("B", "", location="Remote"), _job("C", "", location="Berlin")]
    assert [j.title for j in filter_jobs(jobs, "Pune")] == ["A", "B"]
    assert [j.title for j in filter_jobs(jobs, remote_only=True)] == ["B"]


def test_build_queries():
    p = build_profile(RESUME_TXT)
    assert build_queries(p, p.skills) == ["software engineer", "Python engineer"]
    assert build_queries(p, p.skills, "  data engineer ") == ["data engineer"]


# ---------- models / scrapers ----------

def test_clean_text_and_salary():
    assert clean_text("<p>Hello&nbsp;<b>world</b></p>\n\n") == "Hello world"
    assert format_salary(90000, 120000, "USD", "yr") == "USD 90k–120k/yr"
    assert format_salary(None, None) is None


LINKEDIN_SEARCH = """
<li><div class="base-card base-search-card job-search-card" data-entity-urn="urn:li:jobPosting:3912345678">
 <a class="base-card__full-link" href="https://in.linkedin.com/jobs/view/python-dev-at-acme-3912345678?refId=abc"></a>
 <div class="base-search-card__info">
  <h3 class="base-search-card__title"> Python Developer </h3>
  <h4 class="base-search-card__subtitle"><a>Acme Corp</a></h4>
  <div class="base-search-card__metadata">
   <span class="job-search-card__location">Bengaluru, Karnataka, India</span>
   <time class="job-search-card__listdate" datetime="2026-11-10">1 week ago</time>
  </div></div></div></li>"""
LINKEDIN_DETAIL = """
<div class="show-more-less-html__markup">We need <strong>Python</strong> and AWS skills.</div>
<ul><li class="description__job-criteria-item"><h3 class="description__job-criteria-subheader">Employment type</h3>
<span class="description__job-criteria-text">Full-time</span></li></ul>"""


def test_linkedin_parsers():
    cards = parse_search_html(LINKEDIN_SEARCH)
    assert cards == [{
        "job_id": "3912345678", "title": "Python Developer", "company": "Acme Corp",
        "location": "Bengaluru, Karnataka, India",
        "url": "https://in.linkedin.com/jobs/view/python-dev-at-acme-3912345678",
        "posted_at": "2026-11-10", "salary": None,
    }]
    desc, jt = parse_detail_html(LINKEDIN_DETAIL)
    assert "Python" in desc and jt == "Full-time"


def test_aggregator_isolates_failing_source_and_dedupes():
    from app.aggregator import Aggregator
    from app.sources.base import JobSource, SearchQuery

    class Good(JobSource):
        name, label = "good", "Good"

        async def search(self, client, q):
            return [_job("Python Dev", "short"), _job("Python  Dev", "a much longer description wins")]

    class Bad(JobSource):
        name, label = "bad", "Bad"

        async def search(self, client, q):
            raise RuntimeError("boom")

    from app.config import settings
    old = settings.demo_mode
    settings.demo_mode = False
    try:
        agg = Aggregator({"good": Good(), "bad": Bad(), "sample": Good()})
        jobs, status = asyncio.run(agg.search([SearchQuery("python")]))
    finally:
        settings.demo_mode = old
    assert len(jobs) == 1 and jobs[0].description.startswith("a much longer")
    assert status["bad"]["errors"] and status["good"]["count"] == 2


# ---------- API ----------

def test_api_end_to_end():
    c = TestClient(app)
    assert c.get("/api/health").json()["status"] == "ok"
    assert any(s["name"] == "linkedin" for s in c.get("/api/sources").json()["sources"])
    r = c.post("/api/resume", files={"file": ("cv.pdf", (FIX / "sample_resume.pdf").read_bytes(), "application/pdf")})
    assert r.status_code == 200, r.text
    pid = r.json()["profile_id"]
    r = c.post("/api/jobs/search", json={"profile_id": pid, "limit": 5, "remote_only": True})
    assert r.status_code == 200
    jobs = r.json()["jobs"]
    assert 0 < len(jobs) <= 5 and all(j["remote"] for j in jobs)
    assert jobs == sorted(jobs, key=lambda j: -j["score"])


def test_api_errors():
    c = TestClient(app)
    assert c.post("/api/resume", data={"text": "too short"}).status_code == 422
    assert c.post("/api/jobs/search", json={"profile_id": "nope"}).status_code == 404
    assert c.get("/").status_code == 200
