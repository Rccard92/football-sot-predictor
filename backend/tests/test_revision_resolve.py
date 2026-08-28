"""Test risoluzione revisione codice Lab storico."""

from __future__ import annotations

import os
from unittest.mock import patch

from app.services.cecchino_data_lab.revision_resolve import resolve_code_revision


def test_git_commit_sha_has_priority_over_source_version():
    with patch.dict(
        os.environ,
        {
            "GIT_COMMIT_SHA": "aaa111",
            "SOURCE_VERSION": "bbb222",
            "RAILWAY_GIT_COMMIT_SHA": "ccc333",
        },
        clear=False,
    ):
        rev = resolve_code_revision()
    assert rev["git_commit"] == "aaa111"
    assert rev["git_commit_source"] == "GIT_COMMIT_SHA"
    assert rev["revision_status"] == "resolved"


def test_source_version_used_when_git_commit_sha_absent():
    with patch.dict(
        os.environ,
        {
            "SOURCE_VERSION": "bbb222",
            "RAILWAY_GIT_COMMIT_SHA": "ccc333",
        },
        clear=False,
    ):
        for key in ("GIT_COMMIT_SHA",):
            os.environ.pop(key, None)
        rev = resolve_code_revision()
    assert rev["git_commit"] == "bbb222"
    assert rev["git_commit_source"] == "SOURCE_VERSION"
    assert rev["revision_status"] == "resolved"


def test_unknown_when_no_env_and_git_fails():
    with patch.dict(os.environ, {}, clear=True):
        with patch(
            "app.services.cecchino_data_lab.revision_resolve.subprocess.check_output",
            side_effect=FileNotFoundError("git"),
        ):
            rev = resolve_code_revision()
    assert rev["git_commit"] is None
    assert rev["revision_status"] == "unknown"
