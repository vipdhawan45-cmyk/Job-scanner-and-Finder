"""Deterministic sample listings (fictional companies) for demos and offline use.

Every job is tagged with source "Sample" so the UI can label it clearly.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from ..models import Job
from .base import JobSource, SearchQuery

COMPANIES = [
    "Northwind Labs", "Bluepeak Analytics", "Cobalt Systems", "Lumen Health Tech", "Orbital Commerce",
    "Quantia Finance", "Vertex Mobility", "Greenleaf Energy", "Helix Bio AI", "Skyline Logistics",
    "Pixelforge Studios", "Tidewater Insurance", "Kestrel Security", "Maple Edtech", "Nimbus Cloudworks",
]
LOCATIONS = [
    ("Bengaluru, India", False), ("Hyderabad, India", False), ("Pune, India", False), ("Remote", True),
    ("London, UK", False), ("Berlin, Germany", False), ("New York, NY, USA", False), ("Remote (Worldwide)", True),
    ("Toronto, Canada", False), ("Singapore", False), ("Austin, TX, USA", False), ("Remote (EU)", True),
]

# (title, years, must-have skills, nice-to-have, summary)
ROLES = [
    ("Senior Python Backend Engineer", 5, ["Python", "FastAPI", "PostgreSQL", "Docker", "AWS"], ["Kafka", "Redis", "Kubernetes"],
     "design and scale high-throughput REST APIs and microservices"),
    ("Backend Developer (Django)", 2, ["Python", "Django", "REST APIs", "MySQL"], ["Celery", "Redis", "Docker"],
     "build product features end to end on our Django platform"),
    ("Full Stack Developer", 3, ["JavaScript", "React", "Node.js", "MongoDB"], ["TypeScript", "AWS", "Docker"],
     "ship customer-facing features across the React frontend and Node.js services"),
    ("Frontend Engineer (React)", 3, ["React", "TypeScript", "HTML", "CSS"], ["Next.js", "Redux", "Testing"],
     "build fast, accessible interfaces used by millions of people"),
    ("Machine Learning Engineer", 4, ["Python", "PyTorch", "Machine Learning", "MLOps", "Docker"], ["Kubernetes", "AWS", "Spark"],
     "train, deploy and monitor ML models in production"),
    ("Data Scientist", 3, ["Python", "Machine Learning", "Statistics", "SQL", "Pandas"], ["scikit-learn", "Tableau", "Spark"],
     "turn data into models and insights that drive product decisions"),
    ("NLP / LLM Engineer", 3, ["Python", "NLP", "LLMs", "PyTorch"], ["MLOps", "AWS", "Elasticsearch"],
     "build retrieval-augmented generation and language model features"),
    ("Data Engineer", 3, ["Python", "SQL", "Spark", "Airflow", "ETL"], ["Kafka", "Snowflake", "AWS"],
     "own batch and streaming pipelines feeding our analytics platform"),
    ("Data Analyst", 1, ["SQL", "Excel", "Data Analysis", "Tableau"], ["Python", "Power BI", "Statistics"],
     "build dashboards and answer business questions with data"),
    ("DevOps Engineer", 4, ["AWS", "Kubernetes", "Terraform", "CI/CD", "Linux"], ["Monitoring", "Python", "Ansible"],
     "automate infrastructure and keep our platform reliable"),
    ("Site Reliability Engineer", 5, ["Kubernetes", "Linux", "Monitoring", "GCP", "Go"], ["Terraform", "Python"],
     "improve availability, latency and incident response"),
    ("Java Backend Engineer", 4, ["Java", "Spring", "Microservices", "PostgreSQL"], ["Kafka", "Docker", "AWS"],
     "develop core payment services on the JVM"),
    ("Android Developer", 2, ["Kotlin", "Android", "REST APIs", "Git"], ["Flutter", "Testing"],
     "build our flagship Android app"),
    ("iOS Engineer", 3, ["Swift", "iOS", "REST APIs", "Git"], ["React Native", "Testing"],
     "craft delightful native iOS experiences"),
    ("QA Automation Engineer", 2, ["Testing", "Python", "CI/CD", "Agile"], ["JavaScript", "Docker"],
     "build automated test suites for web and API products"),
    ("Product Manager", 5, ["Product Management", "Agile", "Data Analysis", "Communication"], ["SQL", "UI/UX Design"],
     "own the roadmap for a core product area"),
    ("UI/UX Designer", 3, ["UI/UX Design", "HTML", "CSS"], ["Communication", "Agile"],
     "design intuitive workflows from research to polished UI"),
    ("Cloud Solutions Architect", 8, ["AWS", "Azure", "System Design", "Microservices", "Terraform"], ["Kubernetes", "Security"],
     "design secure, scalable cloud architectures for enterprise clients"),
    ("Junior Software Developer", 0, ["Python", "Git", "SQL"], ["JavaScript", "Docker", "Linux"],
     "learn from senior engineers while shipping real features"),
    ("Engineering Manager", 9, ["Leadership", "System Design", "Agile", "Microservices"], ["AWS", "Python", "Java"],
     "lead a team of 8 engineers building our platform"),
    ("Security Engineer", 4, ["Security", "Linux", "AWS", "Python"], ["Kubernetes", "Monitoring"],
     "harden infrastructure and run our application security program"),
    ("Business Analyst", 2, ["Data Analysis", "SQL", "Excel", "Communication"], ["Power BI", "Agile"],
     "translate business needs into clear requirements and reports"),
    ("Digital Marketing Manager", 4, ["Digital Marketing", "Data Analysis", "Communication"], ["Excel", "Leadership"],
     "grow acquisition across paid and organic channels"),
    ("Financial Analyst", 2, ["Finance", "Excel", "Data Analysis"], ["SQL", "Power BI"],
     "build financial models and support planning cycles"),
]


def _description(title, years, must, nice, summary, company):
    yrs = f"{years}+ years of professional experience" if years else "0–1 years of experience (fresh graduates welcome)"
    return (
        f"{company} is hiring a {title}. You will {summary}. "
        f"Requirements: {yrs}; strong skills in {', '.join(must)}. "
        f"Nice to have: {', '.join(nice)}. "
        "You will collaborate with product, design and engineering, write clean, well-tested code, "
        "participate in code reviews and help shape our technical direction. "
        "Benefits: flexible hours, learning budget, health insurance."
    )


def generate_sample_jobs() -> list[Job]:
    rng = random.Random(42)
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    jobs: list[Job] = []
    for i, (title, years, must, nice, summary) in enumerate(ROLES):
        for k in range(2):
            company = COMPANIES[(i * 2 + k) % len(COMPANIES)]
            loc, remote = LOCATIONS[(i * 5 + k * 7) % len(LOCATIONS)]
            lo = 40 + years * 12 + rng.randint(0, 20)
            jobs.append(Job(
                title=title, company=company, source="Sample",
                url=f"https://example.com/jobs/{i}-{k}",
                description=_description(title, years, must, nice, summary, company),
                location=loc, remote=remote,
                posted_at=(now - timedelta(days=rng.randint(0, 25))).isoformat(),
                salary=f"USD {lo}k–{lo + 25}k/yr",
                job_type="Full-time" if rng.random() > 0.1 else "Contract",
                tags=must + nice,
            ))
    return jobs


class SampleSource(JobSource):
    name, label = "sample", "Sample listings"
    description = "Bundled demo listings from fictional companies (used offline or as a fallback)."

    def __init__(self):
        self._jobs = generate_sample_jobs()

    async def search(self, client, query: SearchQuery) -> list[Job]:
        # Return everything; the matcher ranks them. Location/remote filters are applied later.
        return list(self._jobs)
