"""Rank jobs against a candidate profile.

Hybrid score (0–100) built from four explainable signals:

* **skills**     – share of the job's detected skills the candidate has (weighted by
                   whether the skill appears in the job title / requirements)
* **semantic**   – TF-IDF (or optional sentence-embedding) cosine similarity
                   between the full resume text and the job posting
* **title**      – how closely the job title matches the candidate's past roles
* **experience** – fit between the candidate's years of experience and the role's
                   seniority / "N+ years" requirement
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .config import settings
from .models import Job
from .resume_parser import Profile
from .skills import PRIMARY_SKILLS, extract_skills

log = logging.getLogger("jobfinder.matcher")

WEIGHTS = {"skills": 0.40, "semantic": 0.25, "title": 0.20, "experience": 0.15}
_STOP = {"senior", "junior", "lead", "sr", "jr", "ii", "iii", "i", "the", "and", "of", "for", "with", "remote",
         "m", "f", "d", "w", "x", "-", "&", "(", ")", "intern", "principal", "staff", "head", "associate"}
_REQ_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years|yrs)", re.I)


@dataclass
class MatchResult:
    job: Job
    score: float
    breakdown: dict[str, float]
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    required_years: int | None = None

    def to_dict(self) -> dict:
        return {
            **self.job.to_dict(),
            "score": round(self.score, 1),
            "breakdown": {k: round(v * 100) for k, v in self.breakdown.items()},
            "matched_skills": self.matched_skills,
            "missing_skills": self.missing_skills,
            "reasons": self.reasons,
            "required_years": self.required_years,
        }


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9+#.]+", s.lower()) if t not in _STOP and len(t) > 1}


def required_years(job: Job) -> int | None:
    """Infer required experience from the posting text or title seniority."""
    found = [int(n) for n in _REQ_YEARS.findall(job.description[:6000]) if 0 < int(n) <= 20]
    if found:
        return min(found)  # the minimum stated requirement is the gate
    t = job.title.lower()
    if re.search(r"\b(intern|graduate|entry|junior|jr\.?|trainee)\b", t):
        return 0
    if re.search(r"\b(principal|staff|head|director|manager|architect)\b", t):
        return 8
    if re.search(r"\b(lead)\b", t):
        return 7
    if re.search(r"\b(senior|sr\.?)\b", t):
        return 5
    return None


def experience_fit(candidate: float, required: int | None) -> float:
    if required is None:
        return 0.75  # unknown: neutral
    gap = required - candidate
    if gap <= 0:
        return 0.85 if -gap > 7 else 1.0  # far over-qualified: slight penalty
    return max(0.0, 1 - gap / 4)


def title_fit(job_title: str, profile: Profile, skills: list[str]) -> float:
    jt = _tokens(job_title)
    if not jt:
        return 0.0
    best = 0.0
    for t in profile.titles:
        tt = _tokens(t)
        if tt:
            best = max(best, len(jt & tt) / len(jt | tt))
    # Core skills in the title ("Python Developer", "React Engineer") are a strong signal.
    title_lower = job_title.lower()
    skill_hits = sum(1 for s in skills[:8] if s.lower() in title_lower)
    return min(1.0, best * 1.4 + 0.3 * skill_hits)


@lru_cache(maxsize=1)
def _embedder():
    from sentence_transformers import SentenceTransformer  # optional dependency

    return SentenceTransformer(settings.embedding_model)


def semantic_scores(resume_text: str, docs: list[str]) -> np.ndarray:
    if not docs:
        return np.array([])
    if settings.use_embeddings:
        try:
            model = _embedder()
            vecs = model.encode([resume_text[:5000]] + [d[:3000] for d in docs], normalize_embeddings=True)
            sims = vecs[1:] @ vecs[0]
            return np.clip((sims - 0.15) / 0.55, 0, 1)  # MiniLM cosines mostly fall in 0.15–0.7
        except Exception as exc:  # fall back to TF-IDF if model unavailable
            log.warning("embeddings unavailable, using TF-IDF: %s", exc)
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True, min_df=1, max_features=40000)
    matrix = vec.fit_transform([resume_text] + docs)
    sims = cosine_similarity(matrix[0], matrix[1:]).ravel()
    top = sims.max() or 1.0
    # Blend relative (vs best job in this batch) and absolute similarity so scores are stable.
    return 0.5 * (sims / top) + 0.5 * np.clip(sims * 3, 0, 1)


def rank_jobs(profile: Profile, jobs: list[Job], skills: list[str] | None = None) -> list[MatchResult]:
    skills = skills if skills is not None else profile.skills
    have = {s.lower() for s in skills}
    docs = [f"{j.title}. {j.title}. {' '.join(j.tags)}. {j.description}" for j in jobs]
    resume_doc = f"{' '.join(profile.titles)} {' '.join(skills)} {profile.text}"
    sem = semantic_scores(resume_doc, docs)

    results: list[MatchResult] = []
    for job, doc, s_sem in zip(jobs, docs, sem):
        # Strip the company name so e.g. "Bluepeak Analytics" doesn't read as a skill.
        job_skills = extract_skills(doc.replace(job.company, " ") if job.company else doc)
        title_lower = job.title.lower()
        # Skills named in the title or tags are the core requirements -> double weight.
        weights = {s: (2.0 if s.lower() in title_lower or s in job.tags else 1.0) for s in job_skills}
        matched = [s for s in job_skills if s.lower() in have]
        missing = [s for s in job_skills if s.lower() not in have]
        if weights:
            s_skill = sum(weights[s] for s in matched) / sum(weights.values())
            # Small boost for postings that use many of the candidate's skills.
            s_skill = min(1.0, s_skill + 0.03 * max(0, len(matched) - 3))
        else:
            s_skill = float(s_sem) * 0.8

        req = required_years(job)
        s_exp = experience_fit(profile.years_experience, req)
        s_title = title_fit(job.title, profile, skills)
        breakdown = {"skills": s_skill, "semantic": float(s_sem), "title": s_title, "experience": s_exp}
        # Experience fit only counts in proportion to relevance: being "senior enough"
        # for an unrelated job shouldn't earn points.
        relevance = 0.6 * s_skill + 0.4 * float(s_sem)
        gated = {**breakdown, "experience": s_exp * min(1.0, relevance / 0.5)}
        score = 100 * sum(WEIGHTS[k] * v for k, v in gated.items())

        reasons = []
        if job_skills:
            reasons.append(f"You have {len(matched)} of {len(job_skills)} skills this role mentions")
        if s_title >= 0.5:
            reasons.append("Job title closely matches your background")
        if req is not None:
            if profile.years_experience >= req:
                reasons.append(f"Your ~{profile.years_experience:g} yrs meets the {req}+ yrs asked")
            else:
                reasons.append(f"Asks for {req}+ yrs; you have ~{profile.years_experience:g}")
        if missing:
            reasons.append(f"Skills to highlight or learn: {', '.join(missing[:3])}")

        results.append(MatchResult(job, score, breakdown, matched[:12], missing[:8], reasons, req))

    results.sort(key=lambda r: r.score, reverse=True)
    return results


def filter_jobs(jobs: list[Job], location: str = "", remote_only: bool = False) -> list[Job]:
    out = []
    loc_terms = [t for t in re.split(r"[,\s]+", location.lower()) if len(t) > 2]
    for j in jobs:
        if remote_only and not j.remote:
            continue
        if loc_terms and not j.remote and not any(t in j.location.lower() for t in loc_terms):
            continue
        out.append(j)
    return out


def build_queries(profile: Profile, skills: list[str], keywords: str = "") -> list[str]:
    """Pick up to 3 search phrases from the profile for the job sources."""
    if keywords.strip():
        return [keywords.strip()]
    queries: list[str] = []
    for t in profile.titles[:2]:
        queries.append(t)
    primary = next(([s for s in skills if s in tier] for tier in PRIMARY_SKILLS if any(s in tier for s in skills)), [])
    if primary:
        role = "developer" if not profile.titles else profile.titles[0].split()[-1]
        queries.append(f"{primary[0]} {role}")
    if not queries:
        queries.append("software developer")
    seen, unique = set(), []
    for q in queries:
        if q.lower() not in seen:
            seen.add(q.lower())
            unique.append(q)
    return unique[:3]
