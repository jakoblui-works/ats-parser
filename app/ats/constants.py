"""The parser's limits and lists, all in one place. Nothing here is imported from settings: the child has none."""

import re

from app.ats.schemas import SectionKind

# Judgement calls: CVs are short, so these only stop abuse.
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_PAGES = 10
PARSE_TIMEOUT_SECONDS = 30

# Well past any real CV. The result is kept in Redis and sent to the browser, and a 5 MB file can inflate far past it.
MAX_TEXT_CHARS = 200_000

# Enough to import the parser and read a real CV. Decompression bombs hit this and become a MemoryError.
MAX_CHILD_MEMORY_BYTES = 512 * 1024 * 1024
# Each child can use all of the above, and the worker runs many tasks at once.
MAX_CONCURRENT_PARSES = 2
# Past anything the text limit allows, escaped and repeated in sections. More means the child isn't behaving.
MAX_CHILD_OUTPUT_BYTES = 8 * 1024 * 1024
# How long a killed child gets to go away before the worker stops waiting for it.
CHILD_EXIT_GRACE_SECONDS = 2

# Lines whose bottom edges are this close read as one row, so a big name beside small text on one baseline stays whole.
ROW_TOLERANCE_POINTS = 3.0

# Below this average, blank pages aside, a document is only partly readable, as when a scan has a typed header.
MIN_READABLE_CHARS_PER_PAGE = 200

# What pdfminer writes for a character whose font has no Unicode mapping: extracted, but nobody can read it.
UNMAPPED_CHARACTER = re.compile(r"\(cid:\d+\)")

# Stages only ever look at this much of a line, and keep this many links: enough for a CV, and it caps their work.
MAX_LINE_CHARS = 300
MAX_LINKS = 20
MAX_EXPERIENCE_ENTRIES = 50

# Headings as they're written, compared once normalised ("&" as "and", punctuation dropped, any case), against a whole
# line. "other" is for headings with no field of their own, so that they end the section before them.
HEADINGS: dict[SectionKind, tuple[str, ...]] = {
    "summary": (
        "summary",
        "professional summary",
        "career summary",
        "profile",
        "professional profile",
        "personal profile",
        "personal statement",
        "objective",
        "career objective",
        "about",
        "about me",
    ),
    "experience": (
        "experience",
        "work experience",
        "professional experience",
        "relevant experience",
        "employment",
        "employment history",
        "employment record",
        "employment experience",
        "work history",
        "career history",
        "professional background",
    ),
    "education": (
        "education",
        "education and training",
        "education and qualifications",
        "experience and education",
        "educational background",
        "academic background",
        "academic qualifications",
        "professional qualifications",
        "qualifications",
        "training",
    ),
    "skills": (
        "skills",
        "key skills",
        "technical skills",
        "core skills",
        "skills and tools",
        "skills summary",
        "technologies",
        "core competencies",
        "key competencies",
        "areas of expertise",
    ),
    "other": (
        "achievements",
        "awards",
        "certifications",
        "certificates",
        "contact",
        "contact details",
        "personal details",
        "hobbies",
        "hobbies and interests",
        "interests",
        "languages",
        "projects",
        "publications",
        "references",
        "referees",
        "volunteering",
        "volunteer experience",
        "volunteer work",
    ),
}
MAX_HEADING_WORDS = 5
NOT_HEADING_TEXT = re.compile(r"[\W_]+")

# Contact. Quantifiers are bounded, and no group repeats anything that can match the same text two ways.
EMAIL = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63}){1,4}")
# A phone says so by how it starts: `+44 ...`, `(020) ...`, or `0770...` (at least two digits, as an ISBN's first group
# is one), or it has the US shape `415-555-2671`. Groups are split by one character, so ` - ` in a date range ends it.
PHONE = re.compile(
    r"(?<![\w.+/=-])"
    r"(?:(?:\+\d{1,15}(?: ?\(\d{1,4}\) ?\d{1,14})?|\(\d{1,4}\) ?\d{1,14}|0\d{1,14})(?:[ .-]\d{1,14}){0,7}"
    r"|\d{3}[ .-]\d{3}[ .-]\d{4})"
    r"(?![\w/@-])"
)
MIN_PHONE_DIGITS, MAX_PHONE_DIGITS = 9, 15
YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
NOT_A_PHONE = re.compile(r"\bisbn\b", re.IGNORECASE)  # An ISBN-10 written without hyphens looks just like a phone.
LINK = re.compile(
    r"(?<![@\w.-])(?:https?://|www\.|(?:[a-z]{2,3}\.)?(?:linkedin|github|gitlab|bitbucket)\.com/)[^\s|,;<>()\"']{1,200}",
    re.IGNORECASE,
)

# Experience. A date range is what makes a line a job, so a year in a sentence isn't one. Gaps are bounded and nothing
# nests, so this stays linear. `experience.py` checks that two-digit years pair up.
_MONTH_NAME = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
_GAP = r"\s{1,3}"
_FULL_YEAR = r"(?:19|20)\d{2}"
_DATE = (
    # 15 Mar 2026, Mar. 2026, Mar, 2026, Mar 15, 2026
    rf"(?:(?:\d{{1,2}}{_GAP})?(?:{_MONTH_NAME})\.?(?:,?{_GAP}|{_GAP}\d{{1,2}},{_GAP}){_FULL_YEAR}"
    rf"|(?:{_MONTH_NAME})\.?{_GAP}['\u2019]?\d{{2}}"  # Mar '26, Mar 26
    rf"|\d{{1,2}}[/.-]{_FULL_YEAR}|\d{{2}}/\d{{2}}"  # 03/2026, 3/2026, 03.2026, 03-2026, 03/26
    rf"|{_FULL_YEAR}(?:-(?:0[1-9]|1[0-2])(?!\d))?)"  # 2026, 2026-03
)
_ONGOING = rf"present|current|now|today|ongoing|to{_GAP}date"
ONGOING = re.compile(_ONGOING, re.IGNORECASE)
_SEPARATOR = r"[-\u2012-\u2015\u2212]|to|until|till"
DATE_RANGE = re.compile(
    rf"(?<![\w/.-])(?P<start>{_DATE})\s{{0,3}}(?:(?:{_SEPARATOR})\s{{0,3}}|(?=to{_GAP}date))"
    rf"(?P<end>{_DATE}|{_ONGOING})(?![\w/-])",
    re.IGNORECASE,
)
# Only ever reads text DATE_RANGE has matched, so it can be loose: a `2026-03`, or a day, a month and a year.
DATE_PARTS = re.compile(
    rf"(\d{{4}})-(\d{{2}})|(?:\d{{1,2}}\s+)?(?:({_MONTH_NAME})\W*(?:\d{{1,2}},\s+)?|(\d{{1,2}})[/.-])?(\d{{2,4}})",
    re.IGNORECASE,
)
MONTH_NUMBERS = {
    name: number for number, name in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)
}
# Separators left around a title once the dates are gone.
TITLE_EDGES = " ()[]|,;:/-\u2012\u2013\u2014\u2015\u2212\u2022\u00b7"
TITLE_LINES_ABOVE = 2
# A line starting like this, or ending in a full stop, is a bullet or a sentence: neither a job nor a title.
BULLETS = ("\u2022", "\u00b7", "\u25aa", "\u25cf", "\uf0b7", "*", "-", "\u2013")

# Name, employer, education. The separators a CV puts between things on a line. A comma isn't one: it's too often part
# of the value (`University of California, Berkeley`, `Acme Ltd, London`).
ENTRY_SEPARATOR = re.compile(r"\s{1,5}(?:[|•·–—-]|at)\s{1,5}")
CV_LABEL = re.compile(r"\b(?:curriculum\s{1,3}vitae|cv|r[eé]sum[eé])\b", re.IGNORECASE)
MIN_NAME_WORDS, MAX_NAME_WORDS = 2, 4
NAME_PUNCTUATION = "'’.-"
# Past this a line isn't an employer, an institution or a qualification.
MAX_ENTRY_CHARS = 70
MAX_EDUCATION_ENTRIES = 20
INSTITUTION = re.compile(r"\b(?:university|college|school|institute|academy)\b", re.IGNORECASE)
# A year alone, with any month in front of it, so the month isn't left behind as text.
LONE_YEAR = re.compile(
    rf"(?<![\w/.-])(?:(?:{_MONTH_NAME})\.?,?{_GAP}|\d{{1,2}}[/.-])?(?P<year>{_FULL_YEAR})(?![\w/-])", re.IGNORECASE
)

# Skills. Terms that are also ordinary words are left out, in the fuller spelling where there is one (`Microsoft Word`),
# so they only come from a `skills` heading. Each term's spelling here is the one the result uses.
KNOWN_SKILLS = (
    # Languages
    "Python", "Java", "JavaScript", "TypeScript", "C++", "C#", "PHP", "Ruby", "Kotlin", "Scala", "Perl", "MATLAB",
    "SAS", "Objective-C", "Bash", "PowerShell", "SQL", "T-SQL", "PL/SQL", "HTML", "HTML5", "CSS", "CSS3", "Sass",
    # Web and backend
    "React", "React Native", "Next.js", "Vue", "Vue.js", "Angular", "jQuery", "Tailwind CSS", "Bootstrap",
    "Node.js", "Express.js", "Django", "FastAPI", "Flask", "Spring Boot", "Ruby on Rails", "Laravel", ".NET",
    "ASP.NET", "GraphQL", "REST API", "RESTful", "gRPC", "Microservices", "Flutter",
    # Data
    "PostgreSQL", "MySQL", "SQLite", "SQL Server", "MongoDB", "Redis", "Elasticsearch", "NoSQL", "Oracle", "Kafka",
    "Airflow", "dbt", "Databricks", "Snowflake", "BigQuery", "Hadoop", "Spark", "Pandas", "NumPy", "PyTorch",
    "TensorFlow", "scikit-learn", "Jupyter", "Power BI", "Tableau", "Looker", "Machine learning", "Deep learning",
    "Data analysis", "Data science", "Data engineering", "Data modelling", "Data modeling", "Data visualisation",
    "Data visualization", "ETL", "A/B testing", "NLP",
    # Infrastructure and practice
    "AWS", "Azure", "GCP", "Google Cloud", "Docker", "Kubernetes", "Terraform", "Ansible", "Jenkins",
    "GitHub Actions", "Git", "GitHub", "GitLab", "Linux", "Unix", "macOS", "Nginx", "CI/CD", "DevOps", "Prometheus",
    "Grafana", "TDD", "Unit testing", "Selenium", "Playwright", "Cypress", "Jest", "pytest", "Postman", "Agile",
    "Scrum", "Kanban", "Cybersecurity",
    # Design
    "Figma", "Photoshop", "Adobe Illustrator", "InDesign", "Adobe XD", "After Effects", "Premiere Pro", "Canva",
    "AutoCAD", "UX design", "UI design", "User research", "Wireframing", "Prototyping", "Typography",
    # Business
    "Project management", "Product management", "Stakeholder management", "Change management", "Risk management",
    "Team management", "People management", "Account management", "Supply chain management", "Business analysis",
    "Financial analysis", "Financial modelling", "Budgeting", "Forecasting", "Bookkeeping", "Accounting",
    "Auditing", "Digital marketing", "Content marketing", "Email marketing", "Social media marketing", "SEO", "SEM",
    "Copywriting", "Technical writing", "Market research", "Customer service", "Negotiation", "Public speaking",
    "Recruitment", "PMP", "Six Sigma", "GDPR",
    # Office and business tools
    "Excel", "Microsoft Word", "MS Word", "Microsoft Office", "MS Office", "Microsoft 365", "Microsoft Outlook",
    "Microsoft Teams", "PowerPoint",
    "SharePoint", "Power Query", "Google Sheets", "Google Docs", "Google Analytics", "Google Ads", "Slack",
    "Notion", "Jira", "Confluence", "Trello", "Asana", "Salesforce", "HubSpot", "Zendesk", "Mailchimp", "WordPress",
    "Shopify", "SAP", "Workday", "NetSuite", "QuickBooks",
)  # fmt: skip
# These would match an ordinary word in lower case: `react quickly`, `excel at`, `in jest`, `angular momentum`.
EXACT_CASE_SKILLS = (
    "React", "Excel", "Slack", "Spark", "Notion", "Playwright", "Postman", "Workday", "Jest", "Flask", "Cypress",
    "Selenium", "Airflow", "Bootstrap", "Angular", "Ruby", "Jenkins", "Bash", "SAP", "SAS", "SEM", "Agile", "Docker",
)  # fmt: skip
MAX_SKILLS = 100
MAX_SKILL_CHARS = 40
MAX_SKILL_WORDS = 4


def _skill_pattern(skill: str) -> str:
    term = re.escape(skill).replace(r"\ ", rf"{_GAP}")
    return f"(?-i:{term})" if skill in EXACT_CASE_SKILLS else term


# One alternation, longest first, tried once at each position: no quantifier here can run on. `Java` stops at the `S`
# of `JavaScript` by the look-ahead, and `Java.` at the end of a sentence still matches.
KNOWN_SKILL = re.compile(
    r"(?<![\w.#+-])(?:"
    + "|".join(_skill_pattern(skill) for skill in sorted(KNOWN_SKILLS, key=len, reverse=True))
    + r")(?![\w#+@]|\.\w)",
    re.IGNORECASE,
)
# Between items under a `skills` heading. A plain `/` isn't one: `CI/CD`, `TCP/IP`.
# Brackets stay: `Spanish (B2)`.
SKILL_EDGES = TITLE_EDGES.replace("()", "") + "".join(BULLETS)
SKILL_SEPARATOR = re.compile(r"[,;|•·▪●\t]|\s{1,5}[/–—-]\s{1,5}")
