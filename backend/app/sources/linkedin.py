"""Scraper for LinkedIn's public (logged-out) job search pages.

Disabled unless ENABLE_LINKEDIN_SCRAPER=true. Scraping LinkedIn is against its
User Agreement and LinkedIn rate-limits/blocks datacenter IPs quickly, so for
production prefer the JSearch source, which returns LinkedIn listings via an API.
"""
from __future__ import annotations

import asyncio
import re

import httpx
from bs4 import BeautifulSoup

from ..models import Job
from .base import USER_AGENT, JobSource, SearchQuery

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}


def parse_search_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cards = []
    for card in soup.select("div.base-search-card, div.job-search-card"):
        urn = card.get("data-entity-urn", "")
        m = re.search(r"(\d+)$", urn)
        title = card.select_one(".base-search-card__title")
        company = card.select_one(".base-search-card__subtitle")
        loc = card.select_one(".job-search-card__location")
        link = card.select_one("a.base-card__full-link") or card.select_one("a")
        time_el = card.select_one("time")
        salary = card.select_one(".job-search-card__salary-info")
        if not (title and link):
            continue
        cards.append({
            "job_id": m.group(1) if m else None,
            "title": title.get_text(strip=True),
            "company": company.get_text(strip=True) if company else "",
            "location": loc.get_text(strip=True) if loc else "",
            "url": link.get("href", "").split("?")[0],
            "posted_at": time_el.get("datetime") if time_el else None,
            "salary": salary.get_text(" ", strip=True) if salary else None,
        })
    return cards


def parse_detail_html(html: str) -> tuple[str, str | None]:
    soup = BeautifulSoup(html, "html.parser")
    desc = soup.select_one(".show-more-less-html__markup") or soup.select_one(".description__text")
    job_type = None
    for item in soup.select(".description__job-criteria-item"):
        header = item.select_one(".description__job-criteria-subheader")
        value = item.select_one(".description__job-criteria-text")
        if header and value and "employment type" in header.get_text().lower():
            job_type = value.get_text(strip=True)
    return (desc.get_text(" ", strip=True) if desc else ""), job_type


class LinkedInGuestSource(JobSource):
    name, label = "linkedin", "LinkedIn"
    description = "Scrapes LinkedIn's public job search (opt-in; may be rate-limited)."

    def __init__(self, enabled: bool, detail_fetch: int = 15):
        self._enabled, self.detail_fetch = enabled, detail_fetch

    @property
    def enabled(self):
        return self._enabled

    @property
    def disabled_reason(self):
        return None if self._enabled else "Opt-in: set ENABLE_LINKEDIN_SCRAPER=true (or use JSearch for LinkedIn listings)."

    async def search(self, client, query):
        params = {"keywords": query.keywords, "location": query.location or "Worldwide", "sortBy": "R"}
        if query.remote_only:
            params["f_WT"] = "2"
        cards: list[dict] = []
        for start in range(0, min(query.limit, 75), 25):
            r = await client.get(SEARCH_URL, params={**params, "start": start}, headers=HEADERS)
            if r.status_code in (429, 999):  # 999 = LinkedIn's bot block
                break
            r.raise_for_status()
            page = parse_search_html(r.text)
            if not page:
                break
            cards.extend(page)
            await asyncio.sleep(0.8)

        # Descriptions live on a separate page; fetch a limited number politely.
        sem = asyncio.Semaphore(3)

        async def detail(card):
            if not card["job_id"]:
                return "", None
            async with sem:
                try:
                    resp = await client.get(DETAIL_URL.format(job_id=card["job_id"]), headers=HEADERS)
                    return parse_detail_html(resp.text) if resp.status_code == 200 else ("", None)
                except httpx.HTTPError:
                    return "", None

        details = await asyncio.gather(*(detail(c) for c in cards[: self.detail_fetch]))
        jobs = []
        for i, c in enumerate(cards[: query.limit]):
            desc, jt = details[i] if i < len(details) else ("", None)
            jobs.append(Job(
                title=c["title"], company=c["company"], url=c["url"], source=self.label,
                description=desc, location=c["location"], posted_at=c["posted_at"],
                salary=c["salary"], job_type=jt, remote=query.remote_only,
            ))
        return jobs
