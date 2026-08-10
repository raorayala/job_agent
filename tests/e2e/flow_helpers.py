"""Shared helpers for paced, user-visible E2E walkthroughs in Google Chrome."""

from __future__ import annotations

import os
import time

from playwright.sync_api import Dialog, Page

DEFAULT_FLOW_PAUSE_SECONDS = 30


def flow_pause_seconds() -> float:
    raw = os.environ.get("E2E_FLOW_PAUSE_SECONDS", "0")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0


def accept_dialogs(page: Page) -> None:
    page.on("dialog", lambda dialog: dialog.accept())


def show_flow_step(page: Page, step: int, total: int, title: str, detail: str) -> None:
    """Overlay a step guide in the browser so users can follow the walkthrough."""
    page.evaluate(
        """({ step, total, title, detail }) => {
            let el = document.getElementById('e2e-flow-guide');
            if (!el) {
                el = document.createElement('div');
                el.id = 'e2e-flow-guide';
                el.style.cssText = [
                    'position:fixed', 'bottom:24px', 'right:24px', 'z-index:99999',
                    'max-width:380px', 'background:#0f172a', 'color:#f8fafc',
                    'padding:18px 22px', 'border-radius:14px',
                    'box-shadow:0 12px 40px rgba(0,0,0,.45)',
                    'font-family:Segoe UI,system-ui,sans-serif', 'border:1px solid #334155'
                ].join(';');
                document.body.appendChild(el);
            }
            el.innerHTML = `
                <div style="opacity:.75;font-size:12px;margin-bottom:6px;letter-spacing:.04em">
                    GUIDED WALKTHROUGH · Step ${step} of ${total}
                </div>
                <div style="font-weight:700;font-size:17px;margin-bottom:8px;line-height:1.3">${title}</div>
                <div style="font-size:13px;line-height:1.5;opacity:.92">${detail}</div>`;
        }""",
        {"step": step, "total": total, "title": title, "detail": detail},
    )


def flow_step(
    page: Page,
    step: int,
    total: int,
    title: str,
    detail: str,
    *,
    pause_seconds: float | None = None,
) -> None:
    """Announce the current step in Chrome, then pause so the user can observe."""
    show_flow_step(page, step, total, title, detail)
    delay = DEFAULT_FLOW_PAUSE_SECONDS if pause_seconds is None else pause_seconds
    env_delay = flow_pause_seconds()
    if env_delay > 0:
        delay = env_delay
    if delay > 0:
        time.sleep(delay)


def click_tab(page: Page, tab_id: str) -> None:
    tab = page.locator(tab_id)
    tab.click()
    tab.wait_for(state="visible")
