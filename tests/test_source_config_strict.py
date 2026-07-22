from pathlib import Path

import pytest

from job_intelligence.source_config import load_source_config


def write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "sources.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_quoted_false_cannot_enable_source(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        """
        sources:
          - id: quoted_enabled
            name: Quoted enabled
            type: rss
            company: Example EPC
            url: https://example.com/jobs.rss
            enabled: "false"
        """,
    )

    with pytest.raises(ValueError, match="enabled.*must be true or false"):
        load_source_config(path)


def test_quoted_policy_boolean_is_rejected(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        """
        sources: []
        policy:
          retain_source_evidence: "false"
        """,
    )

    with pytest.raises(ValueError, match="retain_source_evidence.*must be true or false"):
        load_source_config(path)


def test_private_literal_source_url_is_rejected_during_validation(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        """
        sources:
          - id: private_rss
            name: Private RSS
            type: rss
            company: Example EPC
            url: http://127.0.0.1/jobs.rss
            enabled: false
        """,
    )

    with pytest.raises(ValueError, match="must use a public URL"):
        load_source_config(path)


def test_boolean_is_not_accepted_as_integer_option(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        """
        sources:
          - id: invalid_limit
            name: Invalid limit
            type: greenhouse
            company: Example EPC
            board_token: example
            enabled: false
            max_items: true
        """,
    )

    with pytest.raises(ValueError, match="max_items.*must be an integer"):
        load_source_config(path)


def test_smartrecruiters_detail_flag_requires_boolean(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        """
        sources:
          - id: strict_details
            name: Strict details
            type: smartrecruiters
            company: Example EPC
            company_identifier: example
            enabled: false
            fetch_details: "false"
        """,
    )

    with pytest.raises(ValueError, match="fetch_details.*must be true or false"):
        load_source_config(path)
