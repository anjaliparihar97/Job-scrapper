"""
Basic tests for the parts of the project that don't require a real browser
or network access: the JobPosting model and the SQLite dedup logic.

Run with:  pytest
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scraper.models import JobPosting


def make_job(url="https://example.com/job/1", title="Software Engineer"):
    return JobPosting(
        company="infineon",
        company_display="Infineon Technologies",
        title=title,
        url=url,
        location="Munich, Germany",
    )


def test_job_id_is_stable_for_same_url():
    j1 = make_job()
    j2 = make_job()
    assert j1.job_id == j2.job_id


def test_job_id_differs_for_different_url():
    j1 = make_job(url="https://example.com/job/1")
    j2 = make_job(url="https://example.com/job/2")
    assert j1.job_id != j2.job_id


def test_keyword_filter_matches_title():
    job = make_job(title="Working Student: Data Science")
    assert job.matches_keywords(["data science"])
    assert not job.matches_keywords(["marketing"])


def test_keyword_filter_empty_list_matches_everything():
    job = make_job()
    assert job.matches_keywords([])


def test_dedup_filters_previously_seen_jobs(monkeypatch, tmp_path):
    # Point storage at a temp DB so tests don't touch real data.
    from scraper import storage

    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test_seen_jobs.db")

    job_a = make_job(url="https://example.com/job/A")
    job_b = make_job(url="https://example.com/job/B")

    # First run: both are new.
    new_jobs = storage.filter_new_jobs([job_a, job_b])
    assert {j.job_id for j in new_jobs} == {job_a.job_id, job_b.job_id}

    storage.mark_jobs_as_seen([job_a, job_b])

    # Second run: only a genuinely new job (C) should be new.
    job_c = make_job(url="https://example.com/job/C")
    new_jobs_2 = storage.filter_new_jobs([job_a, job_b, job_c])
    assert {j.job_id for j in new_jobs_2} == {job_c.job_id}
