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
    "Finance": ["financial analysis", "financial modeling", "fp&a", "budgeting", "forecasting"],
    "Data Structures & Algorithms": ["data structures", "algorithms", "dsa"],
    "MERN Stack": ["mern"],
    "Microsoft Office": ["ms office", "microsoft office", "ms word", "powerpoint", "ms powerpoint"],
    # Civil / construction
    "AutoCAD": ["autocad", "auto cad"],
    "STAAD Pro": ["staad pro", "staad.pro", "staad"],
    "Revit": ["revit", "bim"],
    "MS Project": ["ms project", "microsoft project"],
    "Primavera": ["primavera", "p6"],
    "Quantity Surveying": ["quantity surveying", "quantity surveyor", "boq", "bill of quantities", "rate analysis"],
    "Estimation & Costing": ["estimation", "costing", "cost estimation"],
    "Site Supervision": ["site supervision", "site execution", "site management"],
    "Construction Management": ["construction management", "construction", "contractor management"],
    "Surveying": ["surveying", "total station", "land survey"],
    "Quality Control": ["quality control", "quality assurance", "qa/qc", "qc"],
    # Mechanical / electrical / manufacturing
    "SolidWorks": ["solidworks", "solid works"],
    "CATIA": ["catia"],
    "ANSYS": ["ansys", "finite element", "fea"],
    "CNC": ["cnc", "machining"],
    "GD&T": ["gd&t"],
    "PLC / SCADA": ["plc", "scada"],
    "MATLAB": ["matlab", "simulink"],
    "Lean / Six Sigma": ["six sigma", "lean manufacturing", "kaizen", "5s"],
    "Production Planning": ["production planning", "ppc"],
    "Maintenance": ["preventive maintenance", "maintenance"],
    # Accounting / finance ops
    "Accounting": ["accounting", "bookkeeping", "general ledger", "accounts payable", "accounts receivable"],
    "Tally": ["tally", "tally erp", "tally prime"],
    "GST & Taxation": ["gst", "taxation", "income tax", "tds"],
    "Auditing": ["audit", "auditing", "internal audit"],
    "SAP": ["sap", "sap fico", "sap mm", "sap sd"],
    "Banking": ["banking", "loans", "kyc"],
    # Sales / marketing / customer
    "Field Sales": ["field sales", "area sales", "territory sales"],
    "Channel Sales": ["channel sales", "distributor management", "dealer management", "distribution"],
    "Lead Generation": ["lead generation", "cold calling", "telecalling", "tele calling"],
    "Key Account Management": ["key account", "account management", "client relationship", "relationship management"],
    "Retail": ["retail", "fmcg", "merchandising"],
    "Negotiation": ["negotiation"],
    "Customer Service": ["customer service", "customer support", "customer care", "call center", "bpo"],
    "Social Media Marketing": ["social media", "instagram marketing", "facebook ads"],
    "Content Writing": ["content writing", "copywriting", "blogging", "technical writing"],
    # Operations / HR / admin
    "Supply Chain": ["supply chain", "scm", "logistics", "warehouse", "inventory management", "procurement", "purchase"],
    "Operations": ["operations management", "operations"],
    "Recruitment": ["recruitment", "talent acquisition", "hiring", "sourcing"],
    "HR Operations": ["payroll", "onboarding", "employee engagement", "hrms", "human resources"],
    "Administration": ["office administration", "front office", "data entry"],
    # Education / healthcare / other
    "Teaching": ["teaching", "lesson planning", "classroom management", "tutoring"],
    "Nursing": ["nursing", "patient care", "icu"],
    "Pharmacy": ["pharmacy", "pharmacovigilance", "clinical research"],
    "Graphic Design": ["graphic design", "photoshop", "illustrator", "coreldraw", "canva"],
    "Video Editing": ["video editing", "premiere pro", "after effects"],
}

# Aliases that are also ordinary English words / short tokens: only count them
# when written in the casing a resume would use for the technology.
_CASE_SENSITIVE = {"node": "Node", "rust": "Rust", "swift": "Swift", "spring": "Spring",
                   "rails": "Rails", "ts": "TS", "ml": "ML", "qa": "QA", "rest": "REST",
                   "ios": "iOS", "go lang": "Go lang", "lambda": "Lambda", "r programming": "R programming",
                   "sap": "SAP", "plc": "PLC", "qc": "QC", "p6": "P6", "5s": "5S", "fea": "FEA", "ppc": "PPC",
                   "gst": "GST", "tds": "TDS", "kyc": "KYC", "dsa": "DSA", "bim": "BIM", "scm": "SCM",
                   "bpo": "BPO", "icu": "ICU", "mern": "MERN", "staad": "STAAD", "cnc": "CNC"}


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

# Soft / ubiquitous skills: shown to the user but weighted lower in matching and
# never used as search keywords.
GENERIC_SKILLS = frozenset({
    "Communication", "Leadership", "Agile", "Git", "Excel", "Linux", "Microsoft Office", "Negotiation",
    "Operations", "Maintenance", "Quality Control", "Testing", "Administration", "Construction Management",
})

# Words that end a job title ("Site Engineer", "Area Sales Executive").
ROLE_NOUNS = frozenset("""
engineer developer manager executive officer analyst consultant designer architect accountant teacher
lecturer professor nurse technician specialist associate administrator coordinator supervisor scientist
representative assistant director head lead programmer tester intern trainee clerk operator agent advisor
auditor pharmacist doctor chef writer editor recruiter planner surveyor foreman electrician mechanic
cashier receptionist marketer strategist founder partner controller buyer merchandiser counsellor
counselor therapist physician pilot steward president vp ceo cto cfo coo owner apprentice fellow
researcher instructor trainer tutor draftsman draughtsman inspector estimator machinist welder fitter
storekeeper telecaller banker underwriter actuary economist statistician lawyer advocate paralegal
""".split())
