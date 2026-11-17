# Job Scanner and Finder (JobMatch AI)

This is an app which helps users search for the best jobs based on their work experience.

Upload a resume and get jobs ranked by how well they fit you. The app searches LinkedIn and several job boards, then explains each match: which of your skills it uses, which skills you're missing, and whether your experience fits.

```
Browser (HTML/CSS/JS)
  ├── POST /api/resume        → parse PDF/DOCX/TXT → skills, roles, years, level
  └── POST /api/jobs/search   → build queries → search sources in parallel → dedupe → ML ranking
                                   ├─ JSearch (LinkedIn, Indeed, Glassdoor…)  [RAPIDAPI_KEY]
                                   ├─ LinkedIn guest scraper                  [opt-in]
                                   ├─ Adzuna                                  [free key]
                                   ├─ Remotive · RemoteOK · Arbeitnow         [no key]
                                   └─ Sample listings (demo / fallback)
```

## Features

- **Resume parsing:** reads PDF, DOCX and TXT files, or pasted text. It extracts about 100 skills (with aliases such as `k8s`→Kubernetes and `react.js`→React), past job titles, years of experience (stated, or worked out from date ranges with overlaps merged), level, degrees and location.
- **Editable profile:** you can add or remove skills and correct your years of experience before searching.
- **Multi-source search:** searches every source at the same time with timeouts. If one source fails, the others still return results. Duplicates are merged, keeping the copy with the longest description. Results are cached for 15 minutes.
- **Explainable ranking (0–100):**

  | Signal | Weight | How it's scored |
  |---|---|---|
  | Skills | 40% | Share of the job's detected skills that you have. Skills named in the title or tags count double. |
  | Content fit | 25% | TF-IDF cosine similarity between your resume and the posting. Optional sentence-transformer embeddings. |
  | Title fit | 20% | Overlap between the job title and your past roles and core skills. |
  | Experience | 15% | Your years compared with the "N+ years" requirement or the seniority in the title. Only counts in proportion to how relevant the job is. |

- **UI:** match ring, reasons, "you have" and "missing" skill chips, score breakdown, filter and sort, saved jobs, dark mode and a mobile layout.
- **Privacy:** resumes are kept in memory only, deleted after 1 hour, and never written to disk. The API is rate-limited per IP.

## Run locally

```bash
pip install -r requirements-dev.txt
```

```bash
cp .env.example .env
```

```bash
cd backend && uvicorn app.main:app --reload --env-file ../.env
```

Open http://localhost:8000. The API docs are at `/api/docs`.

To try the app with no network access or API keys, use demo mode:

```bash
cd backend && DEMO_MODE=true uvicorn app.main:app --reload
```

Run the tests:

```bash
pytest -q tests
```

## Deploy to a public URL

The app runs as one container that serves both the API and the frontend.

- **Render:** push this folder to GitHub, then go to Render → **New + → Blueprint** and pick the repo. `render.yaml` does the rest. Add your keys in the dashboard.
- **Railway / Fly.io / Google Cloud Run / Azure Container Apps:** deploy the `Dockerfile`. It reads `$PORT`.
- **Heroku-style platforms:** use the `Procfile`.

## Getting real LinkedIn results

| Option | How | Notes |
|---|---|---|
| **JSearch (recommended)** | Subscribe to *JSearch* on rapidapi.com (it has a free tier) and set `RAPIDAPI_KEY` | Returns LinkedIn, Indeed, Glassdoor, ZipRecruiter and Naukri listings through an API. Each result shows the original site as its source. |
| LinkedIn guest scraper | `ENABLE_LINKEDIN_SCRAPER=true` | Scrapes LinkedIn's public job-search pages. **This is against LinkedIn's User Agreement.** LinkedIn quickly blocks cloud-server IPs (you get HTTP 429/999 errors), so use it only for personal experiments. |
| Adzuna | Free `ADZUNA_APP_ID` / `ADZUNA_APP_KEY`; set `ADZUNA_COUNTRY` | A large legitimate aggregator covering India, the UK, the US, the EU and more. |

The free sources (Remotive, RemoteOK, Arbeitnow) work without keys but mostly list remote and EU jobs. If every live source fails, the app shows sample listings and clearly labels them.

## Better semantic matching (optional)

```bash
pip install -r requirements-ml.txt
```

Then set `USE_EMBEDDINGS=true`. This uses `all-MiniLM-L6-v2` embeddings instead of TF-IDF, and falls back to TF-IDF automatically if the model can't load.

## Project layout

```
backend/app/
  main.py            FastAPI routes, in-memory profile store, rate limiting, static hosting
  resume_parser.py   file → text → Profile
  skills.py          skill taxonomy + extractor
  matcher.py         hybrid ranking, filters, query builder
  aggregator.py      concurrent multi-source search, dedupe, cache
  sources/           public.py (Remotive, RemoteOK, Arbeitnow, Adzuna, JSearch), linkedin.py, sample.py
frontend/            index.html, styles.css, app.js (no build step)
tests/               pytest suite + PDF/DOCX/TXT resume fixtures
```

## Ideas for v2

- User accounts with Postgres, saved searches and daily email alerts
- An LLM step (e.g. Claude) that rewrites resume bullet points for a chosen job and drafts a cover letter
- Learning-to-rank from user feedback (saves, applies, dismissals)
- A background job queue (Celery or RQ) and Redis cache for multiple server instances
