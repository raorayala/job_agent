"""Direct platform fetcher for searching and importing jobs from Dice, ZipRecruiter, Indeed, and Glassdoor without Gmail."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Sequence
from bs4 import BeautifulSoup

from job_agent.application_tracker import record_parsed_job
from job_agent.config import load_candidate_profile
from job_agent.database import JobRecord
from job_agent.logging_config import get_logger
from job_agent.models import CandidateProfile, ParsedJob

logger = get_logger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def fetch_dice_jobs(query: str, location: str = "Remote", limit: int = 15) -> list[ParsedJob]:
    """
    Search Dice directly by querying www.dice.com/jobs HTML and JSON-LD schema.
    """
    jobs: list[ParsedJob] = []
    try:
        q_enc = urllib.parse.quote(query)
        loc_enc = urllib.parse.quote(location)
        url = f"https://www.dice.com/jobs?q={q_enc}&location={loc_enc}"

        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        soup = BeautifulSoup(html, "lxml")

        # 1. Parse JSON-LD structured job posting scripts if present
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
                        job_url = item.get("url") or url
                        desc = item.get("description") or ""

                        if title:
                            jobs.append(ParsedJob(
                                title=title,
                                company=company,
                                location=location,
                                job_url=job_url,
                                description=BeautifulSoup(desc, "lxml").get_text(separator=" ").strip(),
                                source_platform="dice",
                            ))
            except Exception:
                continue

        # 2. Parse job card anchors directly
        if not jobs:
            seen_urls = set()
            for card in soup.find_all("a", href=True):
                href = card["href"]
                if "/job-detail/" in href:
                    if not href.startswith("http"):
                        full_url = f"https://www.dice.com{href}"
                    else:
                        full_url = href

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
                        description=f"Dice job listing for {title}",
                        source_platform="dice",
                    ))

        logger.info("Dice search returned %d jobs for query: '%s'", len(jobs), query)
    except Exception as exc:
        logger.warning("Dice search request failed: %s", exc)

    return jobs[:limit]


def fetch_ziprecruiter_jobs(query: str, location: str = "Remote", limit: int = 10) -> list[ParsedJob]:
    """
    Search ZipRecruiter directly by parsing public search page JSON-LD schema / HTML.
    """
    jobs: list[ParsedJob] = []
    try:
        q_enc = urllib.parse.quote(query)
        loc_enc = urllib.parse.quote(location)
        url = f"https://www.ziprecruiter.com/candidate/search?search={q_enc}&location={loc_enc}"

        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        soup = BeautifulSoup(html, "lxml")

        # Parse JSON-LD structured job posting scripts if present
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict) and data.get("@type") == "ItemList":
                    items = [elem.get("item", elem) for elem in data.get("itemListElement", [])]
                elif isinstance(data, dict) and data.get("@type") == "JobPosting":
                    items = [data]
                else:
                    items = []

                for item in items:
                    if isinstance(item, dict) and item.get("@type") == "JobPosting":
                        title = item.get("title") or ""
                        company_info = item.get("hiringOrganization") or {}
                        company = company_info.get("name") if isinstance(company_info, dict) else "Unknown"
                        job_url = item.get("url") or url
                        desc = item.get("description") or ""

                        if title:
                            jobs.append(ParsedJob(
                                title=title,
                                company=company,
                                location=location,
                                job_url=job_url,
                                description=BeautifulSoup(desc, "lxml").get_text(separator=" ").strip(),
                                source_platform="ziprecruiter",
                            ))
            except Exception:
                continue

        logger.info("ZipRecruiter search returned %d jobs for query: '%s'", len(jobs), query)
    except Exception as exc:
        logger.warning("ZipRecruiter search request failed: %s", exc)

    return jobs


def search_and_import_jobs(
    session: Any,
    profile: CandidateProfile,
    platforms: Sequence[str] = ("dice", "ziprecruiter"),
    limit_per_platform: int = 15,
) -> list[tuple[JobRecord, Any, Any]]:
    """
    Automatically search selected job platforms (Dice, ZipRecruiter, etc.)
    using target titles and skills from config.yaml, and record results in SQLite.
    """
    titles = [t for t in (profile.target_titles or ["Java Developer"]) if t and t.strip()]
    location = profile.locations[0] if profile.locations else "Remote"

    # Search with primary target titles
    query = titles[0] if titles else "Java Developer"
    logger.info("Searching platforms %s with query: '%s' (location: %s)", platforms, query, location)

    fetched_jobs: list[ParsedJob] = []

    if "dice" in platforms:
        fetched_jobs.extend(fetch_dice_jobs(query=query, location=location, limit=limit_per_platform))

    if "ziprecruiter" in platforms:
        fetched_jobs.extend(fetch_ziprecruiter_jobs(query=query, location=location, limit=limit_per_platform))

    recorded_results: list[tuple[JobRecord, Any, Any]] = []
    for job in fetched_jobs:
        res = record_parsed_job(session, job, profile)
        recorded_results.append(res)

    logger.info("Recorded %d jobs directly from platform search.", len(recorded_results))
    return recorded_results
