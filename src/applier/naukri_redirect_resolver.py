"""
Naukri External Redirect Resolver.
Extracts canonical company career URLs when 'Apply on company site' button is clicked,
handling popups, new browser contexts, and redirect links.
"""

import re
import sys
from typing import Optional, Tuple
from playwright.sync_api import Page, BrowserContext


def safe_print(msg: str):
    try:
        print(msg)
    except Exception:
        try:
            print(msg.encode("ascii", "replace").decode("ascii"))
        except Exception:
            pass


def resolve_company_site_redirect(page: Page, context: BrowserContext, timeout_ms: int = 15000) -> Optional[str]:
    """
    Finds the 'Apply on company site' button or external redirect link on Naukri,
    clicks it, captures the resulting external page/popup URL, and returns the canonical target URL.
    """
    company_site_btn = page.query_selector(
        "button#company-site-button, button.company-site-button, a[id*='company-site'], [class*='company-site-button'], button:has-text('Apply on company site'), a:has-text('Apply on company site')"
    )
    if not company_site_btn:
        return None

    # Check if it has a direct external href attribute
    href = company_site_btn.get_attribute("href")
    if href and href.startswith("http") and "naukri.com" not in href:
        safe_print(f"[RedirectResolver] Found direct external URL: {href}")
        return href

    safe_print("[RedirectResolver] Clicking 'Apply on company site' and waiting for popup/navigation...")
    target_url = None

    # Attempt 1: Expect new tab/page popup
    try:
        with context.expect_page(timeout=timeout_ms) as new_page_info:
            try:
                company_site_btn.click(timeout=5000)
            except Exception:
                # Fallback to JS direct dispatch click if standard click intercepted
                page.evaluate("(el) => el.click()", company_site_btn)

        new_page = new_page_info.value
        try:
            new_page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        except Exception:
            pass

        # Give dynamic redirect hops time to resolve (e.g. tracking links -> ATS portal)
        for _ in range(5):
            new_url = new_page.url
            if new_url and "naukri.com" not in new_url:
                target_url = new_url
                break
            page.wait_for_timeout(1000)

        if not target_url:
            target_url = new_page.url

        safe_print(f"[RedirectResolver] Captured external target URL from popup: {target_url}")
        try:
            new_page.close()
        except Exception:
            pass
    except Exception as e:
        safe_print(f"[RedirectResolver] Popup listener note: {e}")

    # Attempt 2: If no new tab opened, check if the current page itself navigated
    if not target_url or "naukri.com" in target_url:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5000)
            if "naukri.com" not in page.url:
                target_url = page.url
                safe_print(f"[RedirectResolver] Current page navigated to external portal: {target_url}")
        except Exception:
            pass

    # If still on naukri but href attribute exists
    if (not target_url or "naukri.com" in target_url) and href and href.startswith("http"):
        target_url = href

    return target_url if (target_url and "naukri.com" not in target_url) else None

