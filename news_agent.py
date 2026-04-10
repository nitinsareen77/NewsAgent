#!/usr/bin/env python3
"""
AI News Agent for Real Estate (Revantage)
==========================================
Pipeline:
  1. Fetch items from 15 curated RSS feeds (AI + CRE press)
  2. Deduplicate by URL / title similarity
  3. Score every item with Claude on four axes:
       Relevance · Uniqueness · Authenticity · Applicability to Revantage
  4. Determine a dynamic score threshold (default ≥ 65 / 100)
  5. Rank the top-5 sources by aggregate item quality
  6. Generate a structured report with:
       • Synopsis / highlights
       • Detailed description per qualifying item
       • Plain-English mental model
       • Technical explanation

Usage:
    python news_agent.py                      # print report to stdout
    python news_agent.py --save               # also write JSON + text to reports/
    python news_agent.py --threshold 70       # override score threshold
    python news_agent.py --no-claude          # keyword-only scoring (no API key)
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree as ET

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import anthropic as _anthropic_module
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

from sources import SOURCES, REVANTAGE_CONTEXT

# ══════════════════════════════════════════════════════════════════════════════
# RUNTIME CONFIG  (override via environment variables or CLI flags)
# ══════════════════════════════════════════════════════════════════════════════

ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL        = os.getenv("CLAUDE_MODEL", "claude-opus-4-6")
REPORT_DIR          = os.getenv("REPORT_DIR", "reports")
DEFAULT_THRESHOLD   = int(os.getenv("SCORE_THRESHOLD", "65"))
MAX_PER_SOURCE      = int(os.getenv("MAX_ITEMS_PER_SOURCE", "12"))
REQUEST_TIMEOUT     = 20   # seconds per HTTP call
SCORE_BATCH_SIZE    = 8    # items sent to Claude per API call (keep prompts manageable)
USER_AGENT          = (
    "Mozilla/5.0 (compatible; RevantageNewsAgent/1.0; research bot)"
)

# ── Logging ───────────────────────────────────────────────────────────────────
_log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(
    level=_log_level,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("news_agent.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("news_agent")


# ══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class NewsItem:
    title:       str
    url:         str
    source_name: str
    source_tier: int
    base_auth:   int          # authenticity prior from sources.py (0-100)
    published:   str = ""
    summary:     str = ""     # raw excerpt from RSS <description>

    # populated by scorer
    score_relevance:    int = 0
    score_uniqueness:   int = 0
    score_authenticity: int = 0
    score_applicability: int = 0
    total_score:        int = 0
    score_rationale:    str = ""

    # populated by report generator
    synopsis:           str = ""
    simple_explanation: str = ""
    technical_explanation: str = ""

    @property
    def score_label(self) -> str:
        if self.total_score >= 85:
            return "★★★ Exceptional"
        if self.total_score >= 75:
            return "★★  High"
        if self.total_score >= 65:
            return "★   Solid"
        return "○   Below threshold"


@dataclass
class SourceReport:
    name:         str
    tier:         int
    item_count:   int         # items fetched
    qualifying:   int         # items above threshold
    avg_score:    float
    top_score:    int


# ══════════════════════════════════════════════════════════════════════════════
# FETCHER  – pull & parse RSS feeds
# ══════════════════════════════════════════════════════════════════════════════

class NewsFetcher:
    """Downloads RSS/Atom feeds and returns a flat list of NewsItem objects."""

    _NS = {
        "atom":    "http://www.w3.org/2005/Atom",
        "content": "http://purl.org/rss/1.0/modules/content/",
        "dc":      "http://purl.org/dc/elements/1.1/",
        "media":   "http://search.yahoo.com/mrss/",
    }

    def __init__(self, max_per_source: int = MAX_PER_SOURCE):
        self.max_per_source = max_per_source
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    # ── public ────────────────────────────────────────────────────────────────

    def fetch_all(self, sources: list[dict]) -> list[NewsItem]:
        items: list[NewsItem] = []
        for src in sources:
            try:
                fetched = self._fetch_source(src)
                log.info("%-40s  %d items", src["name"], len(fetched))
                items.extend(fetched)
            except Exception as exc:
                log.warning("%-40s  FAILED: %s", src["name"], exc)
        return self._deduplicate(items)

    # ── private ───────────────────────────────────────────────────────────────

    def _fetch_source(self, src: dict) -> list[NewsItem]:
        resp = self.session.get(src["rss"], timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return self._parse_feed(resp.content, src)

    def _parse_feed(self, raw: bytes, src: dict) -> list[NewsItem]:
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            raise ValueError(f"XML parse error: {exc}") from exc

        # Detect feed type: RSS 2.0 vs Atom
        tag = root.tag.lower()
        if "feed" in tag:          # Atom
            entries = root.findall("atom:entry", self._NS) or root.findall("entry")
        else:                       # RSS 2.0 / RSS 1.0
            channel = root.find("channel") or root
            entries = channel.findall("item")

        items: list[NewsItem] = []
        for entry in entries[: self.max_per_source]:
            item = self._parse_entry(entry, src)
            if item:
                items.append(item)
        return items

    def _parse_entry(self, entry: ET.Element, src: dict) -> NewsItem | None:
        """Extract title, url, published, and summary from a feed entry."""
        title = self._text(entry, ["title", "atom:title"])
        url   = self._link(entry)
        if not title or not url:
            return None

        published = self._text(entry, [
            "pubDate", "published", "atom:published", "dc:date",
        ])
        summary = self._text(entry, [
            "description", "summary", "atom:summary",
            "content:encoded", "atom:content",
        ])
        summary = self._clean_html(summary or "")[:800]

        return NewsItem(
            title=title.strip(),
            url=url.strip(),
            source_name=src["name"],
            source_tier=src["tier"],
            base_auth=src["base_auth"],
            published=published or "",
            summary=summary,
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    def _text(self, el: ET.Element, tags: list[str]) -> str:
        for tag in tags:
            child = el.find(tag, self._NS) if ":" in tag else el.find(tag)
            if child is not None and child.text:
                return child.text.strip()
        return ""

    def _link(self, el: ET.Element) -> str:
        # Atom <link href="..."/>
        atom_link = el.find("atom:link", self._NS)
        if atom_link is not None:
            href = atom_link.get("href", "")
            if href:
                return href

        # Standard <link> text
        link_el = el.find("link")
        if link_el is not None:
            if link_el.text:
                return link_el.text.strip()
            # Some feeds store URL in href attribute
            href = link_el.get("href", "")
            if href:
                return href

        return ""

    @staticmethod
    def _clean_html(text: str) -> str:
        text = re.sub(r"<[^>]+>", " ", text)
        text = html_lib.unescape(text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def _deduplicate(items: list[NewsItem]) -> list[NewsItem]:
        seen_urls:   set[str] = set()
        seen_titles: set[str] = set()
        out: list[NewsItem] = []
        for item in items:
            norm_url   = item.url.rstrip("/").split("?")[0].lower()
            norm_title = re.sub(r"\W+", " ", item.title.lower()).strip()
            if norm_url in seen_urls or norm_title in seen_titles:
                continue
            seen_urls.add(norm_url)
            seen_titles.add(norm_title)
            out.append(item)
        log.info("Deduplication: %d → %d unique items", len(items) + (len(items) - len(out)), len(out))
        return out


# ══════════════════════════════════════════════════════════════════════════════
# SCORER  – rate items with Claude (or keyword fallback)
# ══════════════════════════════════════════════════════════════════════════════

_SCORING_SYSTEM = f"""
You are an expert analyst who evaluates news articles for relevance to
AI technology and its applications in commercial real estate, specifically
for Revantage (Blackstone Real Estate's global services company).

{REVANTAGE_CONTEXT}

SCORING DIMENSIONS (each 0–25, total 0–100):
  1. relevance     – Is this about AI being applied to real estate or directly
                     adjacent domains (construction, finance, facilities)?
  2. uniqueness    – Is this a genuinely new development, not a rehash or press
                     release?  Novel research, product launches, and case studies
                     score higher.
  3. authenticity  – How credible and trustworthy is the source and claim?
                     Peer-reviewed > tier-1 press > trade press > PR/blog.
  4. applicability – How directly actionable is this for Revantage's workflows?
                     Something Revantage could pilot within 12 months scores highest.

THRESHOLD GUIDELINE:
  ≥ 65  →  Include in report (useful signal)
  ≥ 75  →  High value
  ≥ 85  →  Exceptional / must-read

Respond ONLY with a valid JSON array — one object per article, in the same
order as provided, with keys:
  "relevance"     : integer 0–25
  "uniqueness"    : integer 0–25
  "authenticity"  : integer 0–25
  "applicability" : integer 0–25
  "rationale"     : 1–2 sentence explanation of the overall score
""".strip()


_REPORT_SYSTEM = f"""
You are a senior technology strategist preparing an intelligence briefing for
the leadership team at Revantage (Blackstone Real Estate's global shared-services
organisation).

{REVANTAGE_CONTEXT}

Your writing must be crisp, specific, and actionable. No filler, no hype.
""".strip()


class NewsScorer:
    """Scores NewsItem objects using Claude or keyword heuristics."""

    # Keywords that boost relevance if found in title+summary
    _AI_TERMS = {
        "artificial intelligence", "machine learning", "deep learning",
        "llm", "large language model", "generative ai", "neural network",
        "computer vision", "natural language processing", "nlp",
        "foundation model", "gpt", "chatgpt", "claude", "gemini",
        "automation", "ai agent", "rag", "retrieval", "embedding",
    }
    _RE_TERMS = {
        "real estate", "commercial real estate", "cre", "property",
        "proptech", "tenant", "lease", "building", "facility",
        "portfolio", "blackstone", "revantage", "reit", "industrial",
        "office", "retail", "logistics", "multi-family", "residential",
    }

    def __init__(self, use_claude: bool = True):
        self.use_claude = use_claude and _ANTHROPIC_AVAILABLE and bool(ANTHROPIC_API_KEY)
        if self.use_claude:
            self._client = _anthropic_module.Anthropic(api_key=ANTHROPIC_API_KEY)
            log.info("Scorer: using Claude (%s)", CLAUDE_MODEL)
        else:
            log.warning("Scorer: Claude unavailable — using keyword heuristics")

    # ── public ────────────────────────────────────────────────────────────────

    def score_all(self, items: list[NewsItem]) -> list[NewsItem]:
        if self.use_claude:
            return self._score_with_claude(items)
        return [self._score_keyword(item) for item in items]

    # ── Claude scoring ────────────────────────────────────────────────────────

    def _score_with_claude(self, items: list[NewsItem]) -> list[NewsItem]:
        scored: list[NewsItem] = []
        for i in range(0, len(items), SCORE_BATCH_SIZE):
            batch = items[i: i + SCORE_BATCH_SIZE]
            log.info("Scoring batch %d–%d of %d …",
                     i + 1, min(i + SCORE_BATCH_SIZE, len(items)), len(items))
            try:
                self._score_batch(batch)
            except Exception as exc:
                log.warning("Claude batch failed (%s); falling back to keywords", exc)
                for item in batch:
                    self._score_keyword(item)
            scored.extend(batch)
            if i + SCORE_BATCH_SIZE < len(items):
                time.sleep(1)          # gentle rate-limiting
        return scored

    def _score_batch(self, batch: list[NewsItem]) -> None:
        articles_text = "\n\n".join(
            f"[{idx + 1}] SOURCE: {item.source_name} (Tier {item.source_tier})\n"
            f"TITLE: {item.title}\n"
            f"SUMMARY: {item.summary or '(no excerpt available)'}"
            for idx, item in enumerate(batch)
        )
        prompt = (
            f"Score these {len(batch)} articles. "
            f"Return a JSON array of {len(batch)} objects.\n\n"
            f"{articles_text}"
        )
        response = self._client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1500,
            system=_SCORING_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        # Extract JSON even if Claude wraps it in a code fence
        json_match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not json_match:
            raise ValueError("Claude did not return a JSON array")
        scores: list[dict] = json.loads(json_match.group())

        for item, sc in zip(batch, scores):
            item.score_relevance    = int(sc.get("relevance",     0))
            item.score_uniqueness   = int(sc.get("uniqueness",    0))
            item.score_authenticity = int(sc.get("authenticity",  0))
            item.score_applicability = int(sc.get("applicability", 0))
            item.total_score = (
                item.score_relevance +
                item.score_uniqueness +
                item.score_authenticity +
                item.score_applicability
            )
            item.score_rationale = sc.get("rationale", "")

    # ── Keyword heuristic fallback ─────────────────────────────────────────────

    def _score_keyword(self, item: NewsItem) -> NewsItem:
        text = (item.title + " " + item.summary).lower()

        ai_hits = sum(1 for t in self._AI_TERMS if t in text)
        re_hits = sum(1 for t in self._RE_TERMS if t in text)

        item.score_relevance     = min(25, (ai_hits * 5) + (re_hits * 3))
        item.score_uniqueness    = 12  # neutral — we can't judge without Claude
        item.score_authenticity  = int(item.base_auth * 25 / 100)
        item.score_applicability = min(25, re_hits * 4)
        item.total_score = (
            item.score_relevance +
            item.score_uniqueness +
            item.score_authenticity +
            item.score_applicability
        )
        item.score_rationale = "(keyword heuristic — no Claude API key)"
        return item


# ══════════════════════════════════════════════════════════════════════════════
# REPORT GENERATOR  – turn scored items into a readable briefing
# ══════════════════════════════════════════════════════════════════════════════

class ReportGenerator:
    """Uses Claude to produce the final narrative report."""

    def __init__(self, use_claude: bool = True):
        self.use_claude = use_claude and _ANTHROPIC_AVAILABLE and bool(ANTHROPIC_API_KEY)
        if self.use_claude:
            self._client = _anthropic_module.Anthropic(api_key=ANTHROPIC_API_KEY)

    # ── public ────────────────────────────────────────────────────────────────

    def generate(
        self,
        qualifying: list[NewsItem],
        all_items: list[NewsItem],
        threshold: int,
        source_reports: list[SourceReport],
        run_date: str,
    ) -> str:
        if self.use_claude:
            return self._generate_with_claude(
                qualifying, all_items, threshold, source_reports, run_date
            )
        return self._generate_simple(
            qualifying, all_items, threshold, source_reports, run_date
        )

    # ── Claude report ─────────────────────────────────────────────────────────

    def _generate_with_claude(
        self,
        qualifying: list[NewsItem],
        all_items: list[NewsItem],
        threshold: int,
        source_reports: list[SourceReport],
        run_date: str,
    ) -> str:
        items_block = "\n\n".join(
            f"### [{i + 1}] {item.title}\n"
            f"Source : {item.source_name} | Score : {item.total_score}/100 "
            f"(R:{item.score_relevance} U:{item.score_uniqueness} "
            f"A:{item.score_authenticity} Ap:{item.score_applicability})\n"
            f"URL    : {item.url}\n"
            f"Excerpt: {item.summary or '(none)'}\n"
            f"Rationale: {item.score_rationale}"
            for i, item in enumerate(qualifying)
        )
        sources_block = "\n".join(
            f"  {i + 1}. {sr.name}  (Tier {sr.tier})  "
            f"avg={sr.avg_score:.1f}  qualifying={sr.qualifying}/{sr.item_count}"
            for i, sr in enumerate(source_reports[:5])
        )
        prompt = f"""
Date: {run_date}
Total articles scanned : {len(all_items)}
Score threshold applied: {threshold}/100
Qualifying articles    : {len(qualifying)}

TOP 5 SOURCES BY AGGREGATE SCORE:
{sources_block}

QUALIFYING ARTICLES (score ≥ {threshold}):
{items_block}

---
Please produce the FULL intelligence briefing structured EXACTLY as follows
(use Markdown headings):

# AI × Real Estate Intelligence Brief  —  {run_date}

## Executive Summary
(3–5 bullet points capturing the most important themes across all qualifying articles)

## Top 5 Sources This Week
(Table: Rank | Source | Avg Score | Qualifying Items | Why It Matters)

## Score Threshold Rationale
(Explain why {threshold}/100 was used today, how the score distribution looks,
and what a reader can trust about items above this bar)

## Qualifying Articles

For EACH qualifying article write:

### [N] <Title>
**Score**: <total>/100 · Relevance <R>/25 · Uniqueness <U>/25 · Authenticity <A>/25 · Applicability <Ap>/25
**Source**: <name> | **Published**: <date if available> | [Read →](<url>)

**Synopsis** (2–3 sentences): What happened and why it matters.

**Simple English** (mental model for a non-technical executive):
Explain this as if describing it to a smart, non-technical real-estate executive
using a simple analogy or mental model. What should they picture in their head?

**Technical Deep-Dive**:
For a technical audience — explain the underlying AI method or system, how it
works, what data it needs, what the engineering challenges are, and how
Revantage's engineering team might evaluate or adopt it.

---

## Key Themes & Strategic Implications
(What patterns emerge across today's articles? What should Revantage watch or act on?)
""".strip()

        response = self._client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=6000,
            system=_REPORT_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    # ── Simple text fallback ───────────────────────────────────────────────────

    def _generate_simple(
        self,
        qualifying: list[NewsItem],
        all_items: list[NewsItem],
        threshold: int,
        source_reports: list[SourceReport],
        run_date: str,
    ) -> str:
        lines = [
            f"# AI × Real Estate Intelligence Brief  —  {run_date}",
            f"\nScanned {len(all_items)} articles · threshold {threshold}/100 "
            f"· {len(qualifying)} qualifying\n",
            "## Top 5 Sources\n",
        ]
        for i, sr in enumerate(source_reports[:5]):
            lines.append(
                f"  {i + 1}. {sr.name}  avg={sr.avg_score:.1f}  "
                f"qualifying={sr.qualifying}/{sr.item_count}"
            )
        lines.append("\n## Qualifying Articles\n")
        for i, item in enumerate(qualifying):
            lines.extend([
                f"### [{i + 1}] {item.title}",
                f"Score : {item.total_score}/100  "
                f"(R:{item.score_relevance} U:{item.score_uniqueness} "
                f"A:{item.score_authenticity} Ap:{item.score_applicability})",
                f"Source: {item.source_name}",
                f"URL   : {item.url}",
                f"Excerpt: {item.summary[:300] if item.summary else '—'}",
                "",
            ])
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# THRESHOLD CALCULATOR  – dynamic threshold from score distribution
# ══════════════════════════════════════════════════════════════════════════════

def compute_threshold(items: list[NewsItem], default: int) -> int:
    """
    If we have enough scored items, set the threshold at the
    score that keeps at most 40 % of items (i.e. the 60th percentile).
    Never goes below the user-supplied default.
    """
    if len(items) < 5:
        return default

    scores = sorted(item.total_score for item in items)
    p60_index = int(len(scores) * 0.60)
    p60_value = scores[p60_index]

    # respect the floor
    dynamic = max(default, p60_value)
    log.info(
        "Threshold: default=%d  60th-pct=%d  chosen=%d",
        default, p60_value, dynamic,
    )
    return dynamic


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

class NewsAgent:
    def __init__(
        self,
        threshold: int = DEFAULT_THRESHOLD,
        save: bool = False,
        use_claude: bool = True,
    ):
        self.threshold  = threshold
        self.save       = save
        self.fetcher    = NewsFetcher()
        self.scorer     = NewsScorer(use_claude=use_claude)
        self.reporter   = ReportGenerator(use_claude=use_claude)
        self.run_date   = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── pipeline ──────────────────────────────────────────────────────────────

    def run(self) -> str:
        log.info("=" * 60)
        log.info("NewsAgent starting  —  %s", self.run_date)
        log.info("Sources: %d  |  threshold (floor): %d", len(SOURCES), self.threshold)
        log.info("=" * 60)

        # Step 1 – Fetch
        log.info("── Step 1: Fetching feeds …")
        all_items = self.fetcher.fetch_all(SOURCES)
        log.info("Fetched %d unique items from %d sources", len(all_items), len(SOURCES))

        if not all_items:
            return "No articles fetched — check network / RSS URLs."

        # Step 2 – Score
        log.info("── Step 2: Scoring %d items …", len(all_items))
        all_items = self.scorer.score_all(all_items)

        # Step 3 – Dynamic threshold
        threshold = compute_threshold(all_items, self.threshold)

        # Step 4 – Filter & sort
        qualifying = sorted(
            [it for it in all_items if it.total_score >= threshold],
            key=lambda x: x.total_score,
            reverse=True,
        )
        log.info("Qualifying items (≥%d): %d of %d", threshold, len(qualifying), len(all_items))

        # Step 5 – Source rankings
        source_reports = self._rank_sources(all_items, threshold)

        # Step 6 – Generate report
        log.info("── Step 3: Generating report …")
        report = self.reporter.generate(
            qualifying, all_items, threshold, source_reports, self.run_date
        )

        # Step 7 – Save artifacts
        if self.save:
            self._save(report, qualifying, all_items, threshold, source_reports)

        return report

    # ── helpers ───────────────────────────────────────────────────────────────

    def _rank_sources(
        self, items: list[NewsItem], threshold: int
    ) -> list[SourceReport]:
        from collections import defaultdict

        buckets: dict[str, list[NewsItem]] = defaultdict(list)
        for item in items:
            buckets[item.source_name].append(item)

        reports: list[SourceReport] = []
        for src in SOURCES:
            name = src["name"]
            src_items = buckets.get(name, [])
            if not src_items:
                continue
            scores = [it.total_score for it in src_items]
            reports.append(
                SourceReport(
                    name=name,
                    tier=src["tier"],
                    item_count=len(src_items),
                    qualifying=sum(1 for s in scores if s >= threshold),
                    avg_score=sum(scores) / len(scores),
                    top_score=max(scores),
                )
            )

        return sorted(reports, key=lambda r: r.avg_score, reverse=True)

    def _save(
        self,
        report: str,
        qualifying: list[NewsItem],
        all_items: list[NewsItem],
        threshold: int,
        source_reports: list[SourceReport],
    ) -> None:
        os.makedirs(REPORT_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Text / Markdown report
        txt_path = os.path.join(REPORT_DIR, f"report_{ts}.md")
        with open(txt_path, "w", encoding="utf-8") as fh:
            fh.write(report)
        log.info("Report saved → %s", txt_path)

        # JSON artefact (machine-readable)
        json_path = os.path.join(REPORT_DIR, f"data_{ts}.json")
        payload = {
            "run_date": self.run_date,
            "threshold": threshold,
            "total_fetched": len(all_items),
            "total_qualifying": len(qualifying),
            "top_sources": [
                {
                    "name": sr.name,
                    "tier": sr.tier,
                    "avg_score": round(sr.avg_score, 1),
                    "qualifying": sr.qualifying,
                    "item_count": sr.item_count,
                }
                for sr in source_reports[:5]
            ],
            "qualifying_items": [
                {
                    "title": it.title,
                    "url": it.url,
                    "source": it.source_name,
                    "published": it.published,
                    "total_score": it.total_score,
                    "scores": {
                        "relevance": it.score_relevance,
                        "uniqueness": it.score_uniqueness,
                        "authenticity": it.score_authenticity,
                        "applicability": it.score_applicability,
                    },
                    "rationale": it.score_rationale,
                    "summary": it.summary,
                }
                for it in qualifying
            ],
        }
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        log.info("JSON data saved → %s", json_path)


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI × Real Estate News Agent for Revantage"
    )
    parser.add_argument(
        "--threshold", type=int, default=DEFAULT_THRESHOLD,
        help=f"Minimum score to include an item (default: {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--save", action="store_true",
        help="Save Markdown + JSON report to the reports/ directory",
    )
    parser.add_argument(
        "--no-claude", action="store_true",
        help="Skip Claude API; use keyword heuristics only",
    )
    args = parser.parse_args()

    agent = NewsAgent(
        threshold=args.threshold,
        save=args.save,
        use_claude=not args.no_claude,
    )
    report = agent.run()
    print("\n" + report)


if __name__ == "__main__":
    main()
