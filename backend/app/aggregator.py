"""Fan a search out to every enabled source concurrently, then merge and de-duplicate."""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

from .config import settings
from .models import Job
from .sources import JobSource, SearchQuery, build_sources

log = logging.getLogger("jobfinder.aggregator")


class Aggregator:
    def __init__(self, sources: dict[str, JobSource] | None = None):
        self.sources = sources or build_sources()
        self._cache: dict[tuple, tuple[float, list[Job], dict]] = {}

    def list_sources(self) -> list[dict]:
        return [s.info() for s in self.sources.values()]

    def _selected(self, names: list[str] | None) -> list[JobSource]:
        if settings.demo_mode:
            return [self.sources["sample"]]
        chosen = [s for n, s in self.sources.items() if s.enabled and n != "sample" and (not names or n in names)]
        if names and "sample" in names:
            chosen.append(self.sources["sample"])
        return chosen

    async def search(self, queries: list[SearchQuery], source_names: list[str] | None = None) -> tuple[list[Job], dict]:
        """Run each query against each selected source. Returns (jobs, per-source status)."""
        selected = self._selected(source_names)
        key = (tuple((q.keywords, q.location, q.remote_only) for q in queries), tuple(s.name for s in selected))
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < settings.cache_ttl_seconds:
            return hit[1], hit[2]

        status: dict[str, dict] = {}
        async with httpx.AsyncClient(timeout=settings.http_timeout, follow_redirects=True) as client:

            async def run(source: JobSource, q: SearchQuery):
                started = time.perf_counter()
                try:
                    jobs = await source.search(client, q)
                    err = None
                except Exception as exc:  # one failing source must not break the search
                    log.warning("source %s failed for %r: %s", source.name, q.keywords, exc)
                    jobs, err = [], f"{type(exc).__name__}: {exc}"[:200]
                st = status.setdefault(source.name, {"label": source.label, "count": 0, "errors": [], "ms": 0})
                st["count"] += len(jobs)
                st["ms"] = max(st["ms"], int((time.perf_counter() - started) * 1000))
                if err:
                    st["errors"].append(err)
                return jobs

            results = await asyncio.gather(*(run(s, q) for s in selected for q in queries))

        merged: dict[str, Job] = {}
        for job in (j for batch in results for j in batch):
            if not job.title or not job.url:
                continue
            existing = merged.get(job.dedupe_key)
            # Keep the copy with the richest description.
            if existing is None or len(job.description) > len(existing.description):
                merged[job.dedupe_key] = job
        jobs = list(merged.values())

        if not jobs and settings.sample_fallback and "sample" not in [s.name for s in selected]:
            jobs = await self.sources["sample"].search(None, queries[0])  # type: ignore[arg-type]
            status["sample"] = {"label": "Sample listings", "count": len(jobs), "errors": [], "ms": 0,
                                "fallback": True}

        self._cache[key] = (time.time(), jobs, status)
        if len(self._cache) > 200:
            self._cache.pop(next(iter(self._cache)))
        return jobs, status
