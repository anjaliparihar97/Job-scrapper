"""
Generic, config-driven scraper.

Rather than writing four bespoke scrapers, one engine reads config/sites.yaml
and applies the same logic to every company: load the page with a real
headless browser (so JavaScript-rendered job lists work), wait for job cards
to appear, then pull title/link/location out with CSS selectors.

This is the piece most likely to need small tweaks over time - see the
comment block at the top of config/sites.yaml for how to fix a selector.
"""
from __future__ import annotations

import logging
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

from scraper.models import JobPosting

logger = logging.getLogger(__name__)


class SiteScraper:
    def __init__(self, site_key: str, site_config: dict, global_settings: dict):
        self.site_key = site_key
        self.cfg = site_config
        self.settings = global_settings

    def scrape(self) -> list[JobPosting]:
        logger.info("Scraping %s (%s)", self.cfg["display_name"], self.cfg["search_url"])
        jobs: list[JobPosting] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36 JobDigestBot/1.0 "
                    "(+respectful personal job-alert script)"
                )
            )
            try:
                page.goto(
                    self.cfg["search_url"],
                    timeout=self.settings.get("page_timeout_ms", 30000),
                    wait_until="domcontentloaded",
                )
                try:
                    page.wait_for_selector(
                        self.cfg["wait_for"],
                        timeout=self.settings.get("page_timeout_ms", 30000),
                    )
                except PWTimeoutError:
                    logger.warning(
                        "[%s] Timed out waiting for '%s' - the page may have "
                        "changed its markup, be geo-blocked, or show a cookie "
                        "banner blocking content. See config/sites.yaml for "
                        "how to fix selectors.",
                        self.site_key,
                        self.cfg["wait_for"],
                    )

                cards = page.query_selector_all(self.cfg["job_card"])
                max_jobs = self.settings.get("max_jobs_per_site", 100)
                logger.info("[%s] Found %d raw job elements", self.site_key, len(cards))

                for card in cards[:max_jobs]:
                    job = self._parse_card(card)
                    if job:
                        jobs.append(job)

            except Exception as exc:  # noqa: BLE001 - we want to log & continue
                logger.error("[%s] Failed to scrape: %s", self.site_key, exc)
            finally:
                browser.close()

        # De-duplicate within this single scrape (some sites repeat cards
        # for mobile/desktop layouts on the same page).
        unique = {}
        for j in jobs:
            unique[j.url] = j
        return list(unique.values())

    def _parse_card(self, card) -> JobPosting | None:
        try:
            title_selector = self.cfg.get("title", "self")
            if title_selector == "self":
                title = (card.inner_text() or "").strip().split("\n")[0]
            else:
                title_el = card.query_selector(title_selector)
                title = (title_el.inner_text() if title_el else "").strip()

            link_attr = self.cfg.get("link_attr", "href")
            href = card.get_attribute(link_attr) or ""
            url = urljoin(self.cfg["base_url"], href) if href else ""

            location = ""
            loc_selector = self.cfg.get("location")
            if loc_selector:
                loc_el = card.query_selector(loc_selector)
                location = (loc_el.inner_text().strip() if loc_el else "")

            if not title or not url:
                return None

            return JobPosting(
                company=self.site_key,
                company_display=self.cfg["display_name"],
                title=title,
                url=url,
                location=location,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Skipping unparseable card on %s: %s", self.site_key, exc)
            return None
