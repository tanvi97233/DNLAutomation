"""
Single source of truth for all data used by the DNL Automation Tool.

Contains:
    - COMPANIES: list of monitored company names (used for Google News search)
    - PR_WEBSITES: list of company website press release pages to scrape
    - RELEVANT_KEYWORDS / EXCLUDE_KEYWORDS: keyword pre-filter vocab
    - HOT_KEYWORDS: triggers that mark a record as HOT
    - NEWS_TYPE_RULES: classifies a headline into one news type
    - HEADERS / REQUEST_TIMEOUT: HTTP request defaults
"""

# ---------------------------------------------------------------------------
# 3A — Company list for Google News search
# ---------------------------------------------------------------------------
COMPANIES = [
    "Aesku Diagnostics",
    "Abbott",
    "Danaher",
    "Beckman Coulter",
    "Bio-Rad",
    "Diasorin",
    "Dr. Fooke",
    "SVAR Lifesciences",
    "Euroimmun",
    "Eurospital",
    "HOB Biotech",
    "Hycor Biomedical",
    "MBL",
    "JSR Corporation",
    "QuidelOrtho",
    "Sharay/C-Luminary",
    "Nippon Chemiphar",
    "Human Diagnostics",
    "Autobio Diagnostics",
    "Siemens Healthineers",
    "Menarini",
    "Biosynex",
    "Roche",
    "DBV",
    "Sebia",
    "Revvity",
    "Zeus Scientific",
    "Sino Biopharma",
    "AliveDx",
    "Werfen",
    "Biosynex/Theradiag",
    "Trinity Biotech",
    "BUHLMANN",
    "Gold Standard Diagnostics",
    "R-Biopharm",
    "Allergenis",
    "MADx",
    "Sunstone Lifesciences",
    "Aimmune",
    "Stallergenes Greer",
    "Allergy Therapeutics",
    "ALK",
]

# ---------------------------------------------------------------------------
# 3B — PR / Company website list to scrape
# ---------------------------------------------------------------------------
PR_WEBSITES = [
    {"company": "Aesku Diagnostics", "url": "https://www.aesku.com/"},
    {"company": "Abbott", "url": "https://abbott.mediaroom.com/press-releases"},
    {"company": "Danaher", "url": "https://www.danaher.com/newsroom"},
    {"company": "Beckman Coulter", "url": "https://www.beckmancoulter.com/about-beckman-coulter/newsroom/press-releases"},
    {"company": "Bio-Rad (Food Science)", "url": "https://www.bio-rad.com/en-in/food-science/news?vertical=FSD"},
    {"company": "Bio-Rad (News)", "url": "https://www.bio-rad.com/en-in/nws/pnws"},
    {"company": "Bio-Rad (IR)", "url": "https://investors.bio-rad.com/press-releases/default.aspx"},
    {"company": "Bio-Rad (General)", "url": "https://www.bio-rad.com/en-in/nws"},
    {"company": "Diasorin", "url": "https://int.diasorin.com/en/investors/finance/press-releases"},
    {"company": "Dr. Fooke", "url": "https://www.fooke-labs.de/veranstaltungen?lang=en"},
    {"company": "SVAR Lifesciences", "url": "https://www.svarlifescience.com/news"},
    {"company": "Euroimmun", "url": "https://www.euroimmun.us/recent-news"},
    {"company": "Eurospital", "url": "https://www.eurospital.com/news/"},
    {"company": "HOB Biotech", "url": "http://en.hob-biotech.com/media-55.html"},
    {"company": "Hycor Biomedical", "url": "https://www.hycorbiomedical.com/news/categories/hycor-news-archive-2023"},
    {"company": "MBL", "url": "https://www.mblbio.com/e/ir/press.html#"},
    {"company": "JSR Corporation", "url": "https://www.jsr.co.jp/jsr_e/news/2026/"},
    {"company": "QuidelOrtho", "url": "https://ir.quidelortho.com/home/default.aspx"},
    {"company": "C-Luminary", "url": "https://www.c-luminary.com/list-46-1.html"},
    {"company": "Nippon Chemiphar", "url": "https://www.chemiphar.co.jp/english/"},
    {"company": "Human Diagnostics", "url": "https://www.human.de/about-human/overview-human/news"},
    {"company": "Autobio Diagnostics", "url": "https://en.autobio.com.cn/News/index/fid/3/cid/2/id/142.html"},
    {"company": "Siemens Healthineers", "url": "https://www.siemens-healthineers.com/press/releases"},
    {"company": "Menarini", "url": "https://www.menarini.com/en-us/news"},
    {"company": "BHR Pharma", "url": "https://bhr.co.uk/blogs/news-releases"},
    {"company": "Roche", "url": "https://www.roche.com/media/releases"},
    {"company": "Sebia", "url": "https://www.sebia.com/en-in/resources/"},
    {"company": "Revvity", "url": "https://news.revvity.com/press-announcements/press-releases/default.aspx"},
    {"company": "Zeus Scientific", "url": "https://www.zeusscientific.com/news-events"},
    {"company": "Sino Biopharma", "url": "https://www.sinobiopharm.com/en/news-center/dynamic/#submenu"},
    {"company": "Beckman (India)", "url": "https://www.mybeckman.in/news"},
    {"company": "AliveDx", "url": "https://alivedx.com/news/"},
    {"company": "Werfen", "url": "https://www.werfen.com/en/news"},
    {"company": "Theradiag", "url": "https://www.theradiag.com/en/category/press-releases/"},
    {"company": "Trinity Biotech", "url": "https://www.trinitybiotech.com/category/press-releases/"},
    {"company": "BUHLMANN Laboratories", "url": "https://www.buhlmannlabs.ch/news/"},
    {"company": "IDS plc", "url": "https://www.idsplc.com/blog/"},
    {"company": "Gold Standard Diagnostics (News)", "url": "https://www.goldstandarddiagnostics.com/news-event/category/news"},
    {"company": "Gold Standard Diagnostics (Events)", "url": "https://www.goldstandarddiagnostics.com/news-event/category/events"},
    {"company": "R-Biopharm", "url": "https://clinical.r-biopharm.com/news/"},
    {"company": "Allergenis", "url": "https://www.allergenis.com/in-the-news"},
    {"company": "MADx", "url": "https://www.macroarraydx.com/news/overview"},
    {"company": "Sunstone Lifesciences", "url": "https://sunstone.eu/news-insights/"},
    {"company": "Aimmune", "url": "https://www.aimmune.com/news-releases"},
    {"company": "Stallergenes Greer", "url": "https://www.stallergenesgreer.com/press-releases#"},
    {"company": "Allergy Therapeutics", "url": "https://www.allergytherapeutics.com/investors/regulatory-news/"},
    {"company": "ALK-Abelló", "url": "https://ir.alk.net/news-events/company-releases"},
    {"company": "DBV Technologies", "url": "https://dbv-technologies.com/investor-overview/news/"},
    {"company": "Eurospital (EGL)", "url": "https://egl.eurospital.com/en/news-and-events/"},
]

# ---------------------------------------------------------------------------
# 4 — Relevancy keyword filter
# ---------------------------------------------------------------------------
RELEVANT_KEYWORDS = [
    "immunodiagnostic", "allergy diagnostic", "autoimmune diagnostic",
    "immunoassay", "diagnostic platform", "point-of-care", "poc", "ivd",
    "elisa", "lateral flow", "multiplex", "serology",
    "allergy immunotherapy", "allergen immunotherapy", "scit", "slit",
    "allergy therapeutic", "allergy", "autoimmune", "immunology",
    "merger", "acquisition", "acquires", "acquired", "takeover", "divest",
    "partnership", "collaboration", "agreement", "alliance", "joint venture",
    "product launch", "new product", "launches", "launch", "platform",
    "ce mark", "ce-mark", "fda clearance", "fda approval", "510(k)",
    "regulatory approval", "regulatory", "ema approval", "market authorization",
    "conference", "symposium", "congress",
    "eaaci", "aaaai", "acaai", "escmid",
    "diagnostics", "diagnostic", "assay", "reagent", "analyzer",
    "laboratory", "lab", "clinical", "test kit",
    "revenue", "earnings", "financial results",
    "ceo", "cfo", "appoints", "appointment", "leadership", "executive",
]

EXCLUDE_KEYWORDS = [
    "generic drug", "biosimilar",
    "chemotherapy", "oncology drug",
    "cardiovascular drug", "diabetes drug", "obesity drug",
    "mental health", "psychiatry",
    "neurology drug", "orthopedic", "dermatology drug",
    "ophthalmology drug",
]

# ---------------------------------------------------------------------------
# 5 — HOT triggers
# ---------------------------------------------------------------------------
HOT_KEYWORDS = [
    # M&A
    "merger", "acquisition", "acquires", "acquired", "takeover", "divest",
    # Regulatory
    "fda approval", "fda clearance", "ce mark", "510(k) clearance",
    "market authorization", "regulatory approval",
    # Major partnership
    "strategic alliance", "joint venture", "major partnership",
    # Major launch
    "platform launch", "breakthrough", "pivotal", "landmark",
]

# ---------------------------------------------------------------------------
# 6 — News type classification rules (order matters; first match wins)
# ---------------------------------------------------------------------------
NEWS_TYPE_RULES = {
    "M&A": ["merger", "acquisition", "acquires", "acquired", "takeover", "divest"],
    "Regulatory": [
        "regulatory", "approval", "cleared", "clearance", "authorized",
        "authorization", "fda", "ema", "ce mark", "ce-mark", "510(k)",
    ],
    "Product Launch": [
        "launch", "launches", "new product", "new platform", "introduces",
        "unveiled", "unveils",
    ],
    "Partnership": [
        "partnership", "collaboration", "agreement", "alliance",
        "joint venture", "co-develop", "license", "licensing",
    ],
    "Conference": [
        "conference", "congress", "symposium", "expo",
        "eaaci", "aaaai", "acaai", "ecp", "esh", "escmid",
    ],
    "Organizational": [
        "ceo", "cfo", "appoints", "appointment", "leadership",
        "executive", "board", "director", "restructure",
    ],
    "Financial": [
        "revenue", "earnings", "results", "financial", "profit",
        "growth", "guidance",
    ],
}

# ---------------------------------------------------------------------------
# 7 — HTTP defaults
# ---------------------------------------------------------------------------
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

REQUEST_TIMEOUT = 15
