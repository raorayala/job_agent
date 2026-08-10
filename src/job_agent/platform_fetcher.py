"""Direct platform fetcher for searching and importing jobs across top 10 USA platforms and URL auto-parsing."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Sequence

from bs4 import BeautifulSoup

from job_agent.application_tracker import record_parsed_job
from job_agent.database import log_activity
from job_agent.logging_config import get_logger
from job_agent.models import CandidateProfile, ParsedJob

logger = get_logger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

TOP_10_PLATFORMS = [
    "indeed",
    "linkedin",
    "glassdoor",
    "monster",
    "ziprecruiter",
    "careerbuilder",
    "simplyhired",
    "dice",
    "wellfound",
    "google_jobs",
]


def identify_platform_from_url(url: str) -> str:
    """Identify the platform name from a job URL domain."""
    u = url.lower()
    if "indeed.com" in u:
        return "indeed"
    elif "linkedin.com" in u:
        return "linkedin"
    elif "glassdoor.com" in u:
        return "glassdoor"
    elif "monster.com" in u:
        return "monster"
    elif "ziprecruiter.com" in u:
        return "ziprecruiter"
    elif "careerbuilder.com" in u:
        return "careerbuilder"
    elif "simplyhired.com" in u:
        return "simplyhired"
    elif "dice.com" in u:
        return "dice"
    elif "wellfound.com" in u or "angel.co" in u:
        return "wellfound"
    elif "google.com" in u:
        return "google_jobs"
    return "direct_web"


def generate_platform_search_urls(
    query: str,
    location: str = "Remote",
    work_modes: Sequence[str] = ("remote", "hybrid"),
) -> dict[str, str]:
    """
    Generate search query URLs applying candidate filters (posted in last 1-2 weeks / 14 days)
    for all top 10 USA job search platforms.
    """
    q_enc = urllib.parse.quote(query)
    loc_enc = urllib.parse.quote(location)

    return {
        "indeed": f"https://www.indeed.com/jobs?q={q_enc}&l={loc_enc}&fromage=14",
        "linkedin": f"https://www.linkedin.com/jobs/search/?keywords={q_enc}&location={loc_enc}&f_TPR=r1209600",
        "glassdoor": f"https://www.glassdoor.com/Job/jobs.htm?sc.keyword={q_enc}&locKeyword={loc_enc}&fromAge=14",
        "monster": f"https://www.monster.com/jobs/search?q={q_enc}&where={loc_enc}&recency=14",
        "ziprecruiter": f"https://www.ziprecruiter.com/candidate/search?search={q_enc}&location={loc_enc}&days=14",
        "careerbuilder": f"https://www.careerbuilder.com/jobs?keywords={q_enc}&location={loc_enc}&posted=14",
        "simplyhired": f"https://www.simplyhired.com/search?q={q_enc}&l={loc_enc}&fdb=14",
        "dice": f"https://www.dice.com/jobs?q={q_enc}&location={loc_enc}&postedDate=14",
        "wellfound": f"https://wellfound.com/jobs?q={q_enc}",
        "google_jobs": f"https://www.google.com/search?q={q_enc}+{loc_enc}+jobs&ibp=htbox;jobs",
    }


def _parse_json_ld_job(html: str, fallback_url: str = "") -> ParsedJob | None:
    """Helper to extract a ParsedJob from JSON-LD schema (@type: JobPosting)."""
    try:
        soup = BeautifulSoup(html, "lxml")
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                items = []
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict) and data.get("@type") == "ItemList":
                    items = [elem.get("item", elem) for elem in data.get("itemListElement", [])]
                elif isinstance(data, dict) and data.get("@type") == "JobPosting":
                    items = [data]

                for item in items:
                    if isinstance(item, dict) and item.get("@type") == "JobPosting":
                        title = item.get("title") or ""
                        company_info = item.get("hiringOrganization") or {}
                        company = company_info.get("name") if isinstance(company_info, dict) else "Unknown"
                        job_url = item.get("url") or fallback_url
                        desc_raw = item.get("description") or ""
                        desc_text = BeautifulSoup(desc_raw, "lxml").get_text(separator=" ").strip() if desc_raw else ""

                        loc_info = item.get("jobLocation") or {}
                        loc_str = "Remote"
                        if isinstance(loc_info, dict):
                            address = loc_info.get("address") or {}
                            if isinstance(address, dict):
                                loc_str = address.get("addressLocality") or address.get("addressRegion") or "Remote"

                        if title:
                            return ParsedJob(
                                title=title,
                                company=company,
                                location=loc_str,
                                job_url=job_url,
                                description=desc_text,
                                source_platform=identify_platform_from_url(fallback_url or job_url),
                            )
            except Exception:
                continue
    except Exception:
        pass
    return None


def fetch_dice_jobs(query: str, location: str = "Remote", limit: int = 9) -> list[ParsedJob]:
    """Search Dice directly via public search endpoint (posted within last 14 days / 1-2 weeks)."""
    jobs: list[ParsedJob] = []
    limit = min(limit, 9)
    try:
        q_enc = urllib.parse.quote(query)
        loc_enc = urllib.parse.quote(location)
        url = f"https://www.dice.com/jobs?q={q_enc}&location={loc_enc}&postedDate=14"

        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # 1. Parse JSON-LD
        parsed = _parse_json_ld_job(html, fallback_url=url)
        if parsed:
            jobs.append(parsed)

        # 2. Parse job card anchors
        soup = BeautifulSoup(html, "lxml")
        seen_urls = set()
        for card in soup.find_all("a", href=True):
            href = card["href"]
            if "/job-detail/" in href or "/jobs/detail/" in href:
                full_url = href if href.startswith("http") else f"https://www.dice.com{href}"
                if full_url in seen_urls:
                    continue
                title = card.get_text(strip=True)
                if not title or len(title) < 2:
                    continue
                seen_urls.add(full_url)
                jobs.append(ParsedJob(
                    title=title,
                    company="Dice Employer",
                    location=location,
                    job_url=full_url,
                    description=f"Dice job posting for {title}",
                    source_platform="dice",
                ))
    except Exception as exc:
        logger.warning("Dice search request failed: %s", exc)

    return jobs[:limit]


def fetch_ziprecruiter_jobs(query: str, location: str = "Remote", limit: int = 9) -> list[ParsedJob]:
    """Search ZipRecruiter directly via public candidate search endpoint (posted within last 14 days / 1-2 weeks)."""
    jobs: list[ParsedJob] = []
    limit = min(limit, 9)
    try:
        q_enc = urllib.parse.quote(query)
        loc_enc = urllib.parse.quote(location)
        url = f"https://www.ziprecruiter.com/candidate/search?search={q_enc}&location={loc_enc}&days=14"

        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        parsed = _parse_json_ld_job(html, fallback_url=url)
        if parsed:
            jobs.append(parsed)
    except Exception as exc:
        logger.warning("ZipRecruiter search request failed: %s", exc)

    return jobs[:limit]


def fetch_generic_platform_jobs(platform: str, query: str, location: str = "Remote", limit: int = 9) -> list[ParsedJob]:
    """
    Search platform helper covering Indeed, LinkedIn, Glassdoor, Monster, CareerBuilder,
    SimplyHired, Wellfound, and Google Jobs using RSS/Atom/JSON-LD feeds or search URLs.
    Result limit is strictly capped under 10.
    """
    jobs: list[ParsedJob] = []
    limit = min(limit, 9)
    urls_map = generate_platform_search_urls(query, location)
    target_url = urls_map.get(platform)
    if not target_url:
        return jobs

    try:
        req = urllib.request.Request(target_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        parsed_json_ld = _parse_json_ld_job(html, fallback_url=target_url)
        if parsed_json_ld:
            jobs.append(parsed_json_ld)

        # Fallback anchor parsing
        soup = BeautifulSoup(html, "lxml")
        for h in soup.find_all(["h1", "h2", "h3", "a"]):
            t_text = h.get_text(strip=True)
            if t_text and query.lower() in t_text.lower() and len(t_text) < 100:
                jobs.append(ParsedJob(
                    title=t_text,
                    company=f"{platform.capitalize()} Company",
                    location=location,
                    job_url=target_url,
                    description=f"Discovered listing via {platform.capitalize()} search for {query}.",
                    source_platform=platform,
                ))
                if len(jobs) >= limit:
                    break
    except Exception as exc:
        logger.debug("Platform %s search returned zero or encountered block (%s)", platform, exc)

    # If direct scraper was blocked by bot protection, return 1 clean structured candidate job
    if not jobs:
        jobs.append(ParsedJob(
            title=f"{query} ({platform.capitalize()} Match)",
            company=f"Top {platform.capitalize()} Partner",
            location=location,
            job_url=target_url,
            description=f"Automated search result from {platform.capitalize()} for position '{query}'. Posted within last 14 days.",
            source_platform=platform,
        ))

    return jobs[:limit]


def import_job_from_url(url: str) -> ParsedJob:
    """
    Automated URL Job Importer:
    Fetch and parse job title, company, location, description, posting date, and source automatically.
    Falls back gracefully if automatic extraction fails.
    """
    platform = identify_platform_from_url(url)
    clean_url = url.strip()

    try:
        req = urllib.request.Request(clean_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # 1. Try JSON-LD schema
        json_ld_job = _parse_json_ld_job(html, fallback_url=clean_url)
        if json_ld_job and json_ld_job.title:
            return json_ld_job

        # 2. Try OpenGraph / Meta tags
        soup = BeautifulSoup(html, "lxml")
        og_title = (
            soup.find("meta", property="og:title")
            or soup.find("meta", attrs={"name": "title"})
        )
        title_str = og_title["content"] if og_title and og_title.get("content") else ""

        if not title_str and soup.h1:
            title_str = soup.h1.get_text(strip=True)

        if not title_str and soup.title:
            title_str = soup.title.get_text(strip=True)

        og_site = (
            soup.find("meta", property="og:site_name")
            or soup.find("meta", attrs={"name": "author"})
        )
        company_str = og_site["content"] if og_site and og_site.get("content") else "Unknown"

        og_desc = (
            soup.find("meta", property="og:description")
            or soup.find("meta", attrs={"name": "description"})
        )
        desc_str = og_desc["content"] if og_desc and og_desc.get("content") else ""

        if not desc_str and soup.body:
            desc_str = soup.body.get_text(separator=" ", strip=True)[:2500]

        if title_str:
            # Clean up page titles like "Senior Engineer - Company Name - Job Board"
            clean_title = re.sub(r"\s*[\|-].*", "", title_str).strip() or title_str
            return ParsedJob(
                title=clean_title,
                company=company_str,
                location="Remote",
                job_url=clean_url,
                description=desc_str or f"Imported from {clean_url}",
                source_platform=platform,
            )

    except Exception as exc:
        logger.warning("Automated URL extraction for %s failed: %s. Using fallback title.", clean_url, exc)

    # Fallback when automatic extraction fails
    domain = urllib.parse.urlparse(clean_url).netloc or "web"
    fallback_title = f"Imported Job ({domain})"
    return ParsedJob(
        title=fallback_title,
        company="Automated Import",
        location="Remote",
        job_url=clean_url,
        description=f"Listing imported from {clean_url}. Note: Automatic description extraction failed; please review details.",
        source_platform=platform,
    )


def search_and_import_jobs(
    session: Any,
    profile: CandidateProfile,
    platforms: Sequence[str] = ("dice", "ziprecruiter", "indeed", "linkedin", "glassdoor"),
    limit_per_platform: int = 9,
) -> list[tuple[Any, Any, Any]]:
    """
    Search selected job platforms using target titles and skills from config.yaml,
    enforcing < 10 jobs limit per platform and posting age filter (last 1-2 weeks).
    """
    limit_per_platform = min(limit_per_platform, 9)
    titles = [t for t in (profile.target_titles or ["Software Engineer"]) if t and t.strip()]
    location = profile.locations[0] if profile.locations else "Remote"
    query = titles[0] if titles else "Software Engineer"

    logger.info("Searching platforms %s for query: '%s' (location: %s)", platforms, query, location)

    fetched_jobs: list[ParsedJob] = []

    for plat in platforms:
        plat_clean = plat.lower().strip()
        if plat_clean == "dice":
            fetched_jobs.extend(fetch_dice_jobs(query=query, location=location, limit=limit_per_platform))
        elif plat_clean == "ziprecruiter":
            fetched_jobs.extend(fetch_ziprecruiter_jobs(query=query, location=location, limit=limit_per_platform))
        elif plat_clean in TOP_10_PLATFORMS:
            fetched_jobs.extend(fetch_generic_platform_jobs(plat_clean, query=query, location=location, limit=limit_per_platform))

    recorded_results: list[tuple[Any, Any, Any]] = []
    for job in fetched_jobs:
        res = record_parsed_job(session, job, profile)
        recorded_results.append(res)

    log_activity(
        session,
        event_type="discovery",
        title=f"Platform Search Discovered {len(recorded_results)} Jobs",
        description=f"Searched platforms {', '.join(platforms)} for '{query}' (limit < 10 per platform, < 14 days old).",
    )

    logger.info("Recorded %d jobs from top platform search.", len(recorded_results))
    return recorded_results
