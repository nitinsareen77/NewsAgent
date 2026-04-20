"""
Curated news sources for AI + Real Estate intelligence.

Each source has:
  name         – Display name
  rss          – RSS/Atom feed URL
  home         – Human-readable homepage
  tier         – 1 (highest authority) → 3 (solid but narrower reach)
  focus        – Category tag
  base_auth    – Starting authenticity score (0-100) before Claude adjusts it
  keywords     – Terms that hint this source is relevant even without Claude
"""

SOURCES: list[dict] = [
    # ── Tier 1 ─ High-authority AI publications ────────────────────────────
    {
        "name": "MIT Technology Review",
        "rss": "https://www.technologyreview.com/feed/",
        "home": "https://www.technologyreview.com",
        "tier": 1,
        "focus": "ai_general",
        "base_auth": 95,
        "keywords": ["AI", "machine learning", "automation", "real estate", "property tech"],
    },
    {
        "name": "VentureBeat AI",
        "rss": "https://venturebeat.com/category/ai/feed/",
        "home": "https://venturebeat.com/ai/",
        "tier": 1,
        "focus": "ai_general",
        "base_auth": 88,
        "keywords": ["AI", "LLM", "generative AI", "proptech", "real estate", "enterprise AI"],
    },
    {
        "name": "TechCrunch AI",
        "rss": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "home": "https://techcrunch.com/artificial-intelligence/",
        "tier": 1,
        "focus": "ai_general",
        "base_auth": 90,
        "keywords": ["AI", "startup", "proptech", "real estate technology", "automation"],
    },
    {
        "name": "DeepLearning.AI – The Batch",
        "rss": "https://www.deeplearning.ai/the-batch/rss.xml",
        "home": "https://www.deeplearning.ai/the-batch/",
        "tier": 1,
        "focus": "ai_research",
        "base_auth": 92,
        "keywords": ["deep learning", "neural network", "LLM", "AI research", "foundation model"],
    },
    {
        "name": "McKinsey – Real Estate & AI",
        "rss": "https://www.mckinsey.com/industries/real-estate/our-insights/rss",
        "home": "https://www.mckinsey.com/industries/real-estate/our-insights",
        "tier": 1,
        "focus": "real_estate_strategy",
        "base_auth": 93,
        "keywords": ["AI", "digital transformation", "real estate", "property management", "analytics"],
    },
    {
        "name": "Ars Technica – Technology Lab",
        "rss": "https://feeds.arstechnica.com/arstechnica/technology-lab",
        "home": "https://arstechnica.com/information-technology/",
        "tier": 1,
        "focus": "ai_general",
        "base_auth": 88,
        "keywords": ["AI", "ML", "automation", "data center", "algorithms", "large language model"],
    },
    # ── Tier 2 ─ Real Estate / PropTech ────────────────────────────────────
    {
        "name": "Propmodo",
        "rss": "https://propmodo.com/feed/",
        "home": "https://propmodo.com",
        "tier": 2,
        "focus": "proptech",
        "base_auth": 83,
        "keywords": ["proptech", "AI", "real estate technology", "CRE", "property management", "tenant"],
    },
    {
        "name": "The Real Deal",
        "rss": "https://therealdeal.com/feed/",
        "home": "https://therealdeal.com",
        "tier": 2,
        "focus": "real_estate",
        "base_auth": 85,
        "keywords": ["AI", "technology", "proptech", "commercial real estate", "CRE", "Blackstone"],
    },
    {
        "name": "GlobeSt – Commercial Real Estate",
        "rss": "https://www.globest.com/feed/",
        "home": "https://www.globest.com",
        "tier": 2,
        "focus": "real_estate",
        "base_auth": 83,
        "keywords": ["AI", "technology", "commercial real estate", "property management", "analytics"],
    },
    {
        "name": "Bisnow",
        "rss": "https://www.bisnow.com/rss",
        "home": "https://www.bisnow.com",
        "tier": 2,
        "focus": "real_estate",
        "base_auth": 80,
        "keywords": ["AI", "proptech", "commercial real estate", "CRE technology", "smart building"],
    },
    {
        "name": "NAIOP – CRE Development",
        "rss": "https://www.naiop.org/research-and-publications/magazine/articles/feed",
        "home": "https://www.naiop.org",
        "tier": 2,
        "focus": "real_estate",
        "base_auth": 84,
        "keywords": ["AI", "technology", "commercial real estate", "industrial", "office", "innovation"],
    },
    {
        "name": "Commercial Observer",
        "rss": "https://commercialobserver.com/feed/",
        "home": "https://commercialobserver.com",
        "tier": 2,
        "focus": "real_estate",
        "base_auth": 80,
        "keywords": ["AI", "technology", "commercial real estate", "proptech", "Blackstone"],
    },
    # ── Tier 3 ─ Enterprise AI / Business Tech ─────────────────────────────
    {
        "name": "AI Business",
        "rss": "https://aibusiness.com/feed",
        "home": "https://aibusiness.com",
        "tier": 3,
        "focus": "ai_business",
        "base_auth": 78,
        "keywords": ["enterprise AI", "real estate", "property", "automation", "predictive analytics"],
    },
    {
        "name": "The Verge – AI",
        "rss": "https://www.theverge.com/rss/index.xml",
        "home": "https://www.theverge.com/ai-artificial-intelligence",
        "tier": 3,
        "focus": "ai_general",
        "base_auth": 84,
        "keywords": ["AI", "machine learning", "automation", "real estate"],
    },
    {
        "name": "InfoQ – AI & ML",
        "rss": "https://feed.infoq.com/",
        "home": "https://www.infoq.com/ai-ml-data-eng/",
        "tier": 3,
        "focus": "ai_engineering",
        "base_auth": 80,
        "keywords": ["AI", "ML", "machine learning", "enterprise architecture", "data platform"],
    },
]

# ── Blackstone ecosystem entity lists (used by scorer for the 5th axis) ──────────

BLACKSTONE_ENTITIES = {
    # Direct Blackstone / Revantage mentions → highest bonus
    "direct": [
        "blackstone", "revantage", "breit", "bpp", "blackstone real estate",
        "blackstone property partners", "blackstone real estate income trust",
        "blackstone real estate debt strategies", "breds",
        "equity commonwealth", "invitation homes", "tricon residential",
        "stuyvesant town", "peter cooper village", "hilton", "extended stay",
        "cosmopolitan", "simply storage", "lasalle hotel", "scp",
        "shore capital", "bxmt",
    ],
    # Blackstone's direct CRE peers — AI adoption here is immediately comparable
    "peers": [
        "brookfield", "brookfield asset management", "brookfield real estate",
        "cbre", "jll", "jones lang lasalle", "prologis", "cushman & wakefield",
        "kkr real estate", "carlyle real estate", "carlyle group",
        "equity residential", "avalonbay", "digital realty", "welltower",
        "simon property", "vornado", "boston properties", "hines",
        "oxford properties", "ares real estate", "greystar", "nuveen real estate",
        "starwood capital", "tishman speyer", "related companies",
    ],
    # Revantage-specific workflows & asset types — signals direct applicability
    "workflows": [
        "lease abstraction", "covenant monitoring", "predictive maintenance",
        "smart building", "tenant analytics", "tenant experience",
        "portfolio optimisation", "portfolio optimization",
        "industrial logistics ai", "last-mile logistics",
        "multi-family ai", "multifamily ai",
        "esg scoring", "carbon tracking", "energy optimisation", "energy optimization",
        "rent comps", "automated valuation", "underwriting ai",
        "construction risk ai", "capex forecasting",
        "facilities management ai", "property management ai",
    ],
}

# ── Revantage context injected into every scoring prompt ───────────────────────
REVANTAGE_CONTEXT = """
Revantage is Blackstone Real Estate's global shared-services company that
supports Blackstone's $330 B+ real-estate portfolio across:
  • Asset types : office, industrial/logistics, retail, hospitality,
                  multi-family residential
  • Functions   : Portfolio analytics, Property & facilities management,
                  Lease administration & abstraction, Tenant experience,
                  Financial reporting & close, ESG / sustainability,
                  Market intelligence & valuations, CapEx / construction mgmt,
                  Insurance & risk, Workforce / HR technology

AI applications most valuable to Revantage:
  1. Predictive maintenance & smart-building IoT
  2. Automated lease abstraction & covenant monitoring
  3. AI-driven portfolio optimisation & scenario modelling
  4. Tenant sentiment & experience analytics
  5. Generative AI for financial narratives & reporting
  6. Energy optimisation & carbon tracking (ESG)
  7. Market-data ingestion & automated rent comps
  8. Construction project risk & cost estimation AI
  9. Property underwriting & acquisition due-diligence AI
 10. Enterprise AI platforms (RAG, agents, fine-tuning) that can be
     deployed across any of the above workflows
"""
