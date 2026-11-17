"""Skill taxonomy used to extract skills from resumes and job descriptions.

Each canonical skill maps to the aliases that should be recognised in free text.
Matching is case-insensitive and boundary-aware (see ``extract_skills``).
"""
from __future__ import annotations

import re
from functools import lru_cache

SKILL_ALIASES: dict[str, list[str]] = {
    # Languages
    "Python": ["python"],
    "Java": ["java"],
    "JavaScript": ["javascript", "js", "es6", "ecmascript"],
    "TypeScript": ["typescript", "ts"],
    "C++": ["c++", "cpp"],
    "C#": ["c#", "csharp", ".net", "dotnet", "asp.net"],
    "Go": ["golang", "go lang"],
    "Rust": ["rust"],
    "Ruby": ["ruby"],
    "PHP": ["php", "laravel"],
    "Kotlin": ["kotlin"],
    "Swift": ["swift"],
    "Scala": ["scala"],
    "R": ["r programming", "rstudio", "tidyverse"],
    "SQL": ["sql", "t-sql", "pl/sql", "plsql"],
    "Bash": ["bash", "shell scripting", "shell script"],
    # Frontend
    "React": ["react", "react.js", "reactjs"],
    "Angular": ["angular", "angularjs"],
    "Vue": ["vue", "vue.js", "vuejs", "nuxt"],
    "Next.js": ["next.js", "nextjs"],
    "Svelte": ["svelte", "sveltekit"],
    "HTML": ["html", "html5"],
    "CSS": ["css", "css3", "sass", "scss", "tailwind", "tailwindcss"],
    "Redux": ["redux"],
    # Backend
    "Node.js": ["node.js", "nodejs", "node", "express", "express.js", "nestjs"],
    "Django": ["django"],
    "Flask": ["flask"],
    "FastAPI": ["fastapi"],
    "Spring": ["spring", "spring boot", "springboot"],
    "Rails": ["rails", "ruby on rails"],
    "GraphQL": ["graphql"],
    "REST APIs": ["rest", "restful", "rest api", "rest apis"],
    "Microservices": ["microservices", "microservice"],
    "gRPC": ["grpc"],
    # Data / ML
    "Machine Learning": ["machine learning", "ml"],
    "Deep Learning": ["deep learning", "neural networks", "neural network"],
    "NLP": ["nlp", "natural language processing"],
    "Computer Vision": ["computer vision", "opencv", "image processing"],
    "LLMs": ["llm", "llms", "large language models", "generative ai", "genai", "rag", "langchain", "prompt engineering"],
    "TensorFlow": ["tensorflow", "keras"],
    "PyTorch": ["pytorch", "torch"],
    "scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "Spark": ["spark", "pyspark", "apache spark", "databricks"],
    "Hadoop": ["hadoop", "hive", "hdfs"],
    "Airflow": ["airflow"],
    "Kafka": ["kafka"],
    "Data Analysis": ["data analysis", "data analytics", "analytics"],
    "Statistics": ["statistics", "statistical modeling", "a/b testing", "hypothesis testing"],
    "Tableau": ["tableau"],
    "Power BI": ["power bi", "powerbi"],
    "Excel": ["excel", "vba"],
    "ETL": ["etl", "elt", "data pipeline", "data pipelines", "dbt"],
    "MLOps": ["mlops", "mlflow", "kubeflow", "sagemaker"],
    # Databases
    "PostgreSQL": ["postgresql", "postgres"],
    "MySQL": ["mysql", "mariadb"],
    "MongoDB": ["mongodb", "mongo"],
    "Redis": ["redis"],
    "Elasticsearch": ["elasticsearch", "elastic search", "opensearch"],
    "Snowflake": ["snowflake"],
    "BigQuery": ["bigquery"],
    "DynamoDB": ["dynamodb"],
    # Cloud / DevOps
    "AWS": ["aws", "amazon web services", "ec2", "s3", "lambda"],
    "Azure": ["azure"],
    "GCP": ["gcp", "google cloud"],
    "Docker": ["docker", "containers", "containerization"],
    "Kubernetes": ["kubernetes", "k8s", "helm", "eks", "gke", "aks"],
    "Terraform": ["terraform", "infrastructure as code", "iac"],
    "CI/CD": ["ci/cd", "cicd", "continuous integration", "jenkins", "github actions", "gitlab ci"],
    "Linux": ["linux", "unix"],
    "Git": ["git", "github", "gitlab", "bitbucket"],
    "Ansible": ["ansible"],
    "Monitoring": ["prometheus", "grafana", "datadog", "observability"],
    # Mobile
    "Android": ["android"],
    "iOS": ["ios"],
    "React Native": ["react native"],
    "Flutter": ["flutter", "dart"],
    # Practices / other
    "Agile": ["agile", "scrum", "kanban", "jira"],
    "System Design": ["system design", "distributed systems", "scalability"],
    "Testing": ["unit testing", "pytest", "jest", "selenium", "cypress", "tdd", "test automation", "qa"],
    "Security": ["cybersecurity", "security", "owasp", "penetration testing", "siem"],
    "UI/UX Design": ["ui/ux", "ux design", "ui design", "figma", "sketch", "user research"],
    "Product Management": ["product management", "product manager", "roadmap", "product strategy"],
    "Project Management": ["project management", "pmp", "prince2", "stakeholder management"],
    "Digital Marketing": ["digital marketing", "seo", "sem", "google ads", "content marketing"],
    "Sales": ["sales", "business development", "b2b sales", "crm", "salesforce"],
    "Communication": ["communication", "presentation skills", "public speaking"],
    "Leadership": ["leadership", "team lead", "mentoring", "people management"],
    "Finance": ["financial analysis", "financial modeling", "accounting", "fp&a"],
}

# Aliases that are also ordinary English words / short tokens: only count them
# when written in the casing a resume would use for the technology.
_CASE_SENSITIVE = {"node": "Node", "rust": "Rust", "swift": "Swift", "spring": "Spring",
                   "rails": "Rails", "ts": "TS", "ml": "ML", "qa": "QA", "rest": "REST",
                   "ios": "iOS", "go lang": "Go lang", "lambda": "Lambda", "r programming": "R programming"}


@lru_cache(maxsize=1)
def _compiled() -> list[tuple[str, re.Pattern[str]]]:
    patterns: list[tuple[str, re.Pattern[str]]] = []
    for canonical, aliases in SKILL_ALIASES.items():
        for alias in aliases:
            cased = _CASE_SENSITIVE.get(alias)
            text, flags = (cased, 0) if cased else (alias, re.IGNORECASE)
            # Custom boundaries so that "c++", "c#", ".net", "ci/cd" work.
            patterns.append((canonical, re.compile(rf"(?<![\w+#.]){re.escape(text)}(?![\w+#])", flags)))
    return patterns


def extract_skills(text: str) -> list[str]:
    """Return canonical skills found in ``text`` ordered by frequency."""
    if not text:
        return []
    counts: dict[str, int] = {}
    for canonical, pat in _compiled():
        n = len(pat.findall(text))
        if n:
            counts[canonical] = counts.get(canonical, 0) + n
    return sorted(counts, key=lambda s: (-counts[s], s))


ROLE_KEYWORDS = [
    "software engineer", "software developer", "backend engineer", "backend developer",
    "frontend engineer", "frontend developer", "full stack developer", "full stack engineer",
    "fullstack developer", "data scientist", "data analyst", "data engineer",
    "machine learning engineer", "ml engineer", "ai engineer", "devops engineer",
    "site reliability engineer", "cloud engineer", "cloud architect", "solutions architect",
    "mobile developer", "android developer", "ios developer", "qa engineer", "test engineer",
    "product manager", "project manager", "program manager", "engineering manager",
    "ui/ux designer", "product designer", "ux designer", "business analyst",
    "security engineer", "web developer", "technical lead", "tech lead", "architect",
    "marketing manager", "sales manager", "account executive", "financial analyst",
]

# Skills that make good search keywords on their own ("Python developer"),
# in two tiers: languages/frameworks first, then broader domains.
PRIMARY_SKILLS: tuple[frozenset[str], ...] = (
    frozenset({"Python", "Java", "JavaScript", "TypeScript", "C++", "C#", "Go", "Rust", "Ruby", "PHP", "Kotlin",
               "Swift", "Scala", "React", "Angular", "Vue", "Node.js", "Android", "iOS", "Flutter"}),
    frozenset({"Machine Learning", "Data Analysis", "Product Management", "UI/UX Design", "Digital Marketing",
               "AWS", "Azure", "Kubernetes", "Tableau", "Power BI", "Finance", "Sales"}),
)
