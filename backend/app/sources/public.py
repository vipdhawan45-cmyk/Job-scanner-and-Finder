"""Free job boards with public JSON APIs (no key required)."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from ..models import Job, format_salary
from .base import USER_AGENT, JobSource


def _matches(text: str, keywords: str) -> bool:
    """True if any meaningful keyword appears in text (for sources without server-side search)."""
    words = [w for w in re.findall(r"[a-z0-9+#.]+", keywords.lower()) if len(w) > 1]
    t = text.lower()
    return not words or any(w in t for w in words)


class RemotiveSource(JobSource):
    name, label = "remotive", "Remotive"
    description = "Remote jobs worldwide (remotive.com public API)."

    async def search(self, client, query):
        r = await client.get(
            "https://remotive.com/api/remote-jobs",
            params={"search": query.keywords, "limit": query.limit},
        )
        r.raise_for_status()
        return [
            Job(
                title=j.get("title", ""),
                company=j.get("company_name", ""),
                url=j.get("url", ""),
                source=self.label,
                description=j.get("description", ""),
                location=j.get("candidate_required_location") or "Remote",
                remote=True,
                posted_at=j.get("publication_date"),
                salary=j.get("salary") or None,
                job_type=(j.get("job_type") or "").replace("_", " ") or None,
                tags=j.get("tags") or [],
            )
            for j in r.json().get("jobs", [])
        ]


class ArbeitnowSource(JobSource):
    name, label = "arbeitnow", "Arbeitnow"
    description = "Europe-focused job board (arbeitnow.com public API)."

    async def search(self, client, query):
        jobs: list[Job] = []
        for page in (1, 2):
            r = await client.get("https://www.arbeitnow.com/api/job-board-api", params={"page": page})
            r.raise_for_status()
            for j in r.json().get("data", []):
                text = f"{j.get('title', '')} {' '.join(j.get('tags') or [])} {j.get('description', '')[:1500]}"
                if not _matches(text, query.keywords):
                    continue
                created = j.get("created_at")
                jobs.append(
                    Job(
                        title=j.get("title", ""),
                        company=j.get("company_name", ""),
                        url=j.get("url", ""),
                        source=self.label,
                        description=j.get("description", ""),
                        location=j.get("location", ""),
                        remote=bool(j.get("remote")),
                        posted_at=datetime.fromtimestamp(created, timezone.utc).isoformat() if created else None,
                        job_type=", ".join(j.get("job_types") or []) or None,
                        tags=j.get("tags") or [],
                    )
                )
        return jobs[: query.limit]


class RemoteOKSource(JobSource):
    name, label = "remoteok", "RemoteOK"
    description = "Remote tech jobs (remoteok.com public API)."

    async def search(self, client, query):
        # RemoteOK filters by a single tag; use the most specific keyword.
        words = [w for w in re.findall(r"[a-z0-9+#.]+", query.keywords.lower()) if len(w) > 2]
        params = {"tag": words[0]} if words else {}
        r = await client.get("https://remoteok.com/api", params=params, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        jobs = []
        for j in r.json():
            if not isinstance(j, dict) or "position" not in j:  # first item is a legal notice
                continue
            jobs.append(
                Job(
                    title=j.get("position", ""),
                    company=j.get("company", ""),
                    url=j.get("url") or j.get("apply_url", ""),
                    source=self.label,
                    description=j.get("description", ""),
                    location=j.get("location") or "Remote",
                    remote=True,
                    posted_at=j.get("date"),
                    salary=format_salary(j.get("salary_min") or None, j.get("salary_max") or None, "USD", "yr"),
                    tags=j.get("tags") or [],
                )
            )
        return jobs[: query.limit]


class AdzunaSource(JobSource):
    name, label = "adzuna", "Adzuna"
    description = "Large aggregator across 16+ countries (needs free ADZUNA_APP_ID / ADZUNA_APP_KEY)."

    def __init__(self, app_id: str | None, app_key: str | None, country: str = "in"):
        self.app_id, self.app_key, self.country = app_id, app_key, country

    @property
    def enabled(self):
        return bool(self.app_id and self.app_key)

    @property
    def disabled_reason(self):
        return None if self.enabled else "Set ADZUNA_APP_ID and ADZUNA_APP_KEY (free at developer.adzuna.com)."

    async def search(self, client, query):
        what = f"{query.keywords} remote" if query.remote_only else query.keywords
        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "what": what,
            "results_per_page": min(query.limit, 50),
            "content-type": "application/json",
        }
        if query.location:
            params["where"] = query.location
        r = await client.get(f"https://api.adzuna.com/v1/api/jobs/{self.country}/search/1", params=params)
        r.raise_for_status()
        return [
            Job(
                title=j.get("title", ""),
                company=(j.get("company") or {}).get("display_name", ""),
                url=j.get("redirect_url", ""),
                source=self.label,
                description=j.get("description", ""),
                location=(j.get("location") or {}).get("display_name", ""),
                posted_at=j.get("created"),
                salary=format_salary(j.get("salary_min"), j.get("salary_max")),
                job_type=(j.get("contract_time") or "").replace("_", " ") or None,
            )
            for j in r.json().get("results", [])
        ]


class JSearchSource(JobSource):
    """JSearch (RapidAPI) aggregates Google for Jobs: LinkedIn, Indeed, Glassdoor, ZipRecruiter, Naukri…"""

    name, label = "jsearch", "JSearch (LinkedIn · Indeed · Glassdoor)"
    description = "Aggregates LinkedIn, Indeed, Glassdoor & more via Google for Jobs (needs RAPIDAPI_KEY)."

    def __init__(self, api_key: str | None):
        self.api_key = api_key

    @property
    def enabled(self):
        return bool(self.api_key)

    @property
    def disabled_reason(self):
        return None if self.enabled else "Set RAPIDAPI_KEY (subscribe to JSearch on rapidapi.com; free tier available)."

    async def search(self, client, query):
        q = f"{query.keywords} in {query.location}" if query.location else query.keywords
        r = await client.get(
            "https://jsearch.p.rapidapi.com/search",
            params={"query": q, "page": 1, "num_pages": max(1, min(query.limit // 10, 5)), "date_posted": "month",
                    **({"remote_jobs_only": "true"} if query.remote_only else {})},
            headers={"X-RapidAPI-Key": self.api_key, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"},
        )
        r.raise_for_status()
        jobs = []
        for j in r.json().get("data", []):
            loc = ", ".join(p for p in (j.get("job_city"), j.get("job_state"), j.get("job_country")) if p)
            publisher = j.get("job_publisher") or "JSearch"
            jobs.append(
                Job(
                    title=j.get("job_title", ""),
                    company=j.get("employer_name", ""),
                    url=j.get("job_apply_link") or j.get("job_google_link", ""),
                    source=publisher,
                    description=j.get("job_description", ""),
                    location=loc or ("Remote" if j.get("job_is_remote") else ""),
                    remote=bool(j.get("job_is_remote")),
                    posted_at=j.get("job_posted_at_datetime_utc"),
                    salary=format_salary(j.get("job_min_salary"), j.get("job_max_salary"),
                                         j.get("job_salary_currency") or "", (j.get("job_salary_period") or "").lower()),
                    job_type=(j.get("job_employment_type") or "").replace("_", " ").title() or None,
                )
            )
        return jobs
