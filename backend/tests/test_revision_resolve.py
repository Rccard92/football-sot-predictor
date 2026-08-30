"""Test risoluzione revisione codice Lab storico."""

from __future__ import annotations

import os
from unittest.mock import patch

from app.services.cecchino_data_lab.revision_resolve import resolve_code_revision


def test_railway_has_priority_over_stale_git_commit_sha():
    """Caso critico: GIT_COMMIT_SHA stale non deve mascherare Railway."""
    with patch.dict(
        os.environ,
        {
            "GIT_COMMIT_SHA": "2c36064stale",
            "SOURCE_VERSION": "2c36064stale",
            "RAILWAY_GIT_COMMIT_SHA": "e1eb82enewsha",
        },
        clear=False,
    ):
        rev = resolve_code_revision()
    assert rev["git_commit"] == "e1eb82enewsha"
    assert rev["git_commit_source"] == "RAILWAY_GIT_COMMIT_SHA"
    assert rev["revision_status"] == "resolved"
    assert rev["revision_conflict"] is True
    assert rev["revision_conflict_sources"]["GIT_COMMIT_SHA"] == "2c36064stale"
    assert rev["revision_conflict_sources"]["RAILWAY_GIT_COMMIT_SHA"] == "e1eb82enewsha"


def test_git_commit_sha_used_when_platform_absent():
    with patch.dict(
        os.environ,
        {
            "GIT_COMMIT_SHA": "aaa111",
            "SOURCE_VERSION": "bbb222",
        },
        clear=False,
    ):
        for key in ("RAILWAY_GIT_COMMIT_SHA", "VERCEL_GIT_COMMIT_SHA"):
            os.environ.pop(key, None)
        rev = resolve_code_revision()
    assert rev["git_commit"] == "aaa111"
    assert rev["git_commit_source"] == "GIT_COMMIT_SHA"
    assert rev["revision_conflict"] is True
    assert set(rev["revision_conflict_sources"].keys()) == {
        "GIT_COMMIT_SHA",
        "SOURCE_VERSION",
    }


def test_no_conflict_when_sources_agree():
    with patch.dict(
        os.environ,
        {
            "RAILWAY_GIT_COMMIT_SHA": "same123",
            "GIT_COMMIT_SHA": "same123",
            "SOURCE_VERSION": "same123",
        },
        clear=False,
    ):
        rev = resolve_code_revision()
    assert rev["git_commit"] == "same123"
    assert rev["git_commit_source"] == "RAILWAY_GIT_COMMIT_SHA"
    assert rev["revision_conflict"] is False
    assert rev["revision_conflict_sources"] is None


def test_source_version_used_when_higher_absent():
    with patch.dict(
        os.environ,
        {
            "SOURCE_VERSION": "bbb222",
        },
        clear=False,
    ):
        for key in (
            "RAILWAY_GIT_COMMIT_SHA",
            "VERCEL_GIT_COMMIT_SHA",
            "GIT_COMMIT_SHA",
        ):
            os.environ.pop(key, None)
        rev = resolve_code_revision()
    assert rev["git_commit"] == "bbb222"
    assert rev["git_commit_source"] == "SOURCE_VERSION"
    assert rev["revision_conflict"] is False


def test_unknown_when_no_env_and_git_fails():
    with patch.dict(os.environ, {}, clear=True):
        with patch(
            "app.services.cecchino_data_lab.revision_resolve.subprocess.check_output",
            side_effect=FileNotFoundError("git"),
        ):
            rev = resolve_code_revision()
    assert rev["git_commit"] is None
    assert rev["revision_status"] == "unknown"
    assert rev["revision_conflict"] is False
