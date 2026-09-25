"""
Main entrypoint.

Usage:
    python -m scraper.run                  # scrape all configured sites, email new jobs
    python -m scraper.run --site infineon  # scrape just one site
    python -m scraper.run --dry-run        # scrape + print, but don't email or save to DB
    python -m scraper.run --no-email       # scrape + save to DB, but don't email

Environment variables are loaded from .env (see .env.example).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from scraper import mailer, storage
from scraper.models import JobPosting
from scraper.site_scraper import SiteScraper

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "sites.yaml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(ROOT / "data" / "run.log"),
    ],
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_args():
    parser = argparse.ArgumentParser(description="Scrape career sites and email new jobs.")
    parser.add_argument(
        "--site",
        action="append",
        help="Only scrape this site key (can be passed multiple times). "
             "Default: all sites listed in SITES env var / config.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape and print results, but do not email or write to the database.",
    )
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Scrape and save to database, but skip sending the email.",
    )
    return parser.parse_args()


def get_target_sites(args, config: dict) -> list[str]:
    if args.site:
        return args.site
    env_sites = os.environ.get("SITES", "")
    if env_sites.strip():
        return [s.strip() for s in env_sites.split(",") if s.strip()]
    return list(config["companies"].keys())


def main():
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    load_dotenv(ROOT / ".env")

    args = parse_args()
    config = load_config()
    site_keys = get_target_sites(args, config)

    unknown = [s for s in site_keys if s not in config["companies"]]
    if unknown:
        logger.error("Unknown site key(s) %s. Valid keys: %s", unknown, list(config["companies"]))
        sys.exit(1)

    all_jobs: list[JobPosting] = []
    for key in site_keys:
        site_cfg = config["companies"][key]
        scraper = SiteScraper(key, site_cfg, config["settings"])
        jobs = scraper.scrape()
        logger.info("[%s] Parsed %d valid job postings", key, len(jobs))
        all_jobs.extend(jobs)

    logger.info("Total jobs scraped across all sites: %d", len(all_jobs))

    keyword_filter = [
        kw for kw in os.environ.get("KEYWORD_FILTER", "").split(",") if kw.strip()
    ]
    if keyword_filter:
        before = len(all_jobs)
        all_jobs = [j for j in all_jobs if j.matches_keywords(keyword_filter)]
        logger.info(
            "Applied keyword filter %s: %d -> %d jobs", keyword_filter, before, len(all_jobs)
        )

    if args.dry_run:
        logger.info("--dry-run set: not touching the database or sending email.")
        _print_jobs(all_jobs)
        return

    new_jobs = storage.filter_new_jobs(all_jobs)
    logger.info("%d of %d jobs are new since the last run", len(new_jobs), len(all_jobs))
    _print_jobs(new_jobs)

    storage.mark_jobs_as_seen(all_jobs)

    send_empty = os.environ.get("SEND_EMPTY_DIGEST", "false").lower() == "true"
    if args.no_email:
        logger.info("--no-email set: skipping email step.")
    elif new_jobs or send_empty:
        mailer.send_digest(new_jobs)
    else:
        logger.info("No new jobs and SEND_EMPTY_DIGEST=false: not sending an email.")

    logger.info("Run complete. DB stats: %s", storage.stats())


def _print_jobs(jobs: list[JobPosting]) -> None:
    for j in jobs:
        print(f"- [{j.company_display}] {j.title} ({j.location}) -> {j.url}")


if __name__ == "__main__":
    main()
