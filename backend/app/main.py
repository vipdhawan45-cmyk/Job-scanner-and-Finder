"""JobMatch AI — FastAPI application (API + static frontend)."""
from __future__ import annotations

import logging
import time
import uuid
from collections import OrderedDict, defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .aggregator import Aggregator
from .config import settings
from .matcher import build_queries, filter_jobs, rank_jobs
from .resume_parser import Profile, ResumeError, build_profile, parse_resume
from .sources import SearchQuery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(title="JobMatch AI", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
if settings.cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

aggregator = Aggregator()


class ProfileStore:
    """In-memory, TTL-bounded store. Resumes are never written to disk."""

    def __init__(self, ttl: int, max_items: int = 2000):
        self.ttl, self.max_items = ttl, max_items
        self._data: OrderedDict[str, tuple[float, Profile]] = OrderedDict()

    def put(self, profile: Profile) -> str:
        pid = uuid.uuid4().hex
        self._data[pid] = (time.time(), profile)
        while len(self._data) > self.max_items:
            self._data.popitem(last=False)
        return pid

    def get(self, pid: str) -> Profile | None:
        item = self._data.get(pid)
        if not item or time.time() - item[0] > self.ttl:
            self._data.pop(pid, None)
            return None
        return item[1]


profiles = ProfileStore(settings.profile_ttl_seconds)

# Simple sliding-window rate limit per client IP for the expensive endpoints.
_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(request: Request, limit: int = 20, window: int = 60) -> None:
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    q, now = _hits[ip], time.time()
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Too many requests — please wait a minute.")
    q.append(now)


@app.get("/api/health")
def health():
    return {"status": "ok", "demo_mode": settings.demo_mode}


@app.get("/api/sources")
def sources():
    return {"sources": aggregator.list_sources(), "demo_mode": settings.demo_mode}


@app.post("/api/resume")
async def upload_resume(request: Request, file: UploadFile | None = File(None), text: str | None = Form(None)):
    rate_limit(request)
    try:
        if file is not None and file.filename:
            data = await file.read()
            profile = parse_resume(file.filename, data)
        elif text and len(text.strip()) >= 50:
            profile = build_profile(text.strip()[:60000])
        else:
            raise ResumeError("Upload a resume file or paste at least a few lines of resume text.")
    except ResumeError as exc:
        raise HTTPException(422, str(exc)) from exc
    pid = profiles.put(profile)
    return {"profile_id": pid, "profile": profile.public(), "suggested_queries": build_queries(profile, profile.skills)}


class SearchRequest(BaseModel):
    profile_id: str
    skills: list[str] | None = Field(None, description="Edited skill list; defaults to parsed skills")
    years_experience: float | None = Field(None, ge=0, le=50)
    keywords: str = Field("", max_length=120)
    location: str = Field("", max_length=80)
    remote_only: bool = False
    sources: list[str] | None = None
    limit: int = Field(40, ge=1, le=100)


@app.post("/api/jobs/search")
async def search_jobs(req: SearchRequest, request: Request):
    rate_limit(request)
    profile = profiles.get(req.profile_id)
    if profile is None:
        raise HTTPException(404, "Your session expired. Please upload your resume again.")
    if req.years_experience is not None:
        profile.years_experience = req.years_experience
    skills = [s.strip() for s in (req.skills if req.skills is not None else profile.skills) if s.strip()][:60]

    query_strings = build_queries(profile, skills, req.keywords)
    queries = [SearchQuery(q, req.location.strip(), req.remote_only, 50) for q in query_strings]
    started = time.perf_counter()
    jobs, status = await aggregator.search(queries, req.sources)
    jobs = filter_jobs(jobs, req.location, req.remote_only)
    ranked = rank_jobs(profile, jobs, skills)[: req.limit]
    return {
        "queries": query_strings,
        "total_found": len(jobs),
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "source_status": status,
        "jobs": [r.to_dict() for r in ranked],
    }


if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(FRONTEND / "index.html")
