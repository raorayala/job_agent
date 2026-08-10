"""Review-gated assisted Auto Apply after ATS-optimized resume approval."""

from __future__ import annotations

import os
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from job_agent.application_tracker import mark_applied, update_status
from job_agent.config import Settings
from job_agent.database import JobRecord, get_job, log_activity
from job_agent.logging_config import get_logger
from job_agent.models import ApplicationStatus
from job_agent.resume_optimize import load_optimize_bundle

logger = get_logger(__name__)


@dataclass
class AutoApplyEligibility:
    job_id: int
    eligible: bool
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    title: str = ""
    company: str = ""
    job_url: str = ""
    approval_status: str = ""
    status: str = ""
    final_resume_path: str = ""
    optimize_accepted: int = 0
    ats_ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AutoApplyResult:
    status: str
    job_id: int
    job_url: str = ""
    resume_path: str = ""
    browser_opened: bool = False
    folder_opened: bool = False
    marked_status: str = ""
    checklist: list[str] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _find_chrome_path() -> str | None:
    possible = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    return next((p for p in possible if os.path.exists(p)), None)


def open_url_in_browser(url: str, browser_choice: str = "system") -> bool:
    """Open application URL in preferred browser (new tab when possible)."""
    import webbrowser

    if not url:
        return False
    choice = (browser_choice or "system").lower()
    chrome = _find_chrome_path()
    use_chrome = choice in ("chrome", "google-chrome") or (choice in ("system", "default") and chrome)
    if use_chrome and chrome:
        try:
            subprocess.Popen(
                [chrome, "--new-tab", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception as exc:
            logger.debug("Chrome open failed: %s", exc)
    try:
        webbrowser.open_new_tab(url)
        return True
    except Exception as exc:
        logger.warning("Could not open browser for %s: %s", url, exc)
        return False


def open_path_in_explorer(path: Path | str) -> bool:
    """Reveal resume folder/file in OS file manager."""
    p = Path(path)
    target = p if p.is_dir() else p.parent
    if not target.exists():
        return False
    try:
        if os.name == "nt":
            if p.is_file():
                subprocess.Popen(["explorer", "/select,", str(p)])
            else:
                subprocess.Popen(["explorer", str(target)])
        elif sys_platform_is_darwin():
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
        return True
    except Exception as exc:
        logger.debug("Could not open folder %s: %s", target, exc)
        return False


def sys_platform_is_darwin() -> bool:
    import sys

    return sys.platform == "darwin"


def evaluate_auto_apply_eligibility(job: JobRecord) -> AutoApplyEligibility:
    """
    Auto Apply is allowed only after human review of an ATS-tailored resume.
    Does not auto-submit forms or bypass CAPTCHAs — launches assisted apply.
    """
    blockers: list[str] = []
    warnings: list[str] = []

    resume_path = job.final_resume_path or job.tailored_resume_path or ""
    approval = (job.approval_status or "").lower()
    status = job.status or ""

    if approval != "approved" and status not in {
        ApplicationStatus.APPROVED.value,
        ApplicationStatus.READY_TO_APPLY.value,
    }:
        blockers.append(
            "Approve & Finalize the ATS-optimized resume in Review & Optimize before Auto Apply."
        )

    if not resume_path or not Path(resume_path).exists():
        blockers.append("Finalized resume file is missing. Approve a draft first.")

    if not (job.job_url or "").strip():
        blockers.append("Job URL is missing — cannot open the employer application page.")

    optimize_accepted = 0
    ats_ready = False
    draft = job.draft_resume_path
    if draft:
        bundle = load_optimize_bundle(draft)
        if bundle:
            optimize_accepted = sum(
                1 for s in bundle.suggestions if s.status in {"accepted", "edited"}
            )
            if optimize_accepted > 0:
                ats_ready = True
            elif bundle.keyword_gaps:
                warnings.append(
                    "AI Optimize ran but no keyword/bullet suggestions were accepted. "
                    "Consider accepting ATS keyword suggestions before applying."
                )
        elif "AI Optimize" not in (job.diff_summary or ""):
            warnings.append(
                "No AI Optimize session found. Resume was approved without recorded ATS optimize accepts."
            )
    else:
        warnings.append("Draft path missing; ATS Optimize history unavailable.")

    if "AI Optimize suggestions applied" in (job.diff_summary or ""):
        ats_ready = True

    return AutoApplyEligibility(
        job_id=job.id,
        eligible=len(blockers) == 0,
        blockers=blockers,
        warnings=warnings,
        title=job.title or "",
        company=job.company or "",
        job_url=job.job_url or "",
        approval_status=job.approval_status or "",
        status=status,
        final_resume_path=resume_path,
        optimize_accepted=optimize_accepted,
        ats_ready=ats_ready,
    )


def launch_auto_apply(
    session: Session,
    job_id: int,
    settings: Settings,
    *,
    open_browser: bool = True,
    open_resume_folder: bool = True,
    mark_as_applied: bool = False,
    confirm: bool = False,
) -> AutoApplyResult:
    """
    Assisted Auto Apply after review:
    1) Validate approved ATS resume
    2) Open employer job URL
    3) Open finalized resume folder for upload
    4) Optionally mark Applied (requires confirm=True)
    """
    job = get_job(session, job_id)
    if not job:
        raise LookupError(f"Job #{job_id} not found")

    eligibility = evaluate_auto_apply_eligibility(job)
    if not eligibility.eligible:
        raise PermissionError("; ".join(eligibility.blockers))

    if mark_as_applied and not confirm:
        raise PermissionError("mark_as_applied requires confirm=True (explicit user confirmation).")

    resume_path = eligibility.final_resume_path
    checklist = [
        "Confirmed ATS-optimized resume was reviewed and approved",
        "Employer application page will open in your browser",
        "Upload the finalized resume from the Jobs Applied folder",
        "Complete any employer form fields manually (no CAPTCHA bypass)",
        "Mark Applied only after you successfully submit",
    ]

    browser_opened = False
    folder_opened = False
    if open_browser and eligibility.job_url:
        browser_opened = open_url_in_browser(eligibility.job_url, settings.preferred_browser)
    if open_resume_folder and resume_path:
        folder_opened = open_path_in_explorer(resume_path)

    marked = ""
    if mark_as_applied and confirm:
        mark_applied(session, job_id, confirm=True)
        marked = ApplicationStatus.APPLIED.value
        message = "Application page opened and job marked Applied."
    else:
        update_status(session, job_id, ApplicationStatus.READY_TO_APPLY.value, confirm_applied=False)
        marked = ApplicationStatus.READY_TO_APPLY.value
        message = "Assisted Auto Apply launched. Submit on the employer site, then mark Applied."

    log_activity(
        session,
        event_type="auto_apply",
        title=f"Auto Apply launched for #{job_id}",
        description=(
            f"browser_opened={browser_opened}, folder_opened={folder_opened}, "
            f"status={marked}, resume={resume_path}"
        ),
        job_id=job_id,
    )

    return AutoApplyResult(
        status="success",
        job_id=job_id,
        job_url=eligibility.job_url,
        resume_path=resume_path,
        browser_opened=browser_opened,
        folder_opened=folder_opened,
        marked_status=marked,
        checklist=checklist,
        message=message,
    )
