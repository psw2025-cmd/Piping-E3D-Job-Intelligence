from pathlib import Path

import pytest

from job_intelligence.source_config import load_source_config


def write_config(tmp_path: Path, source_body: str) -> Path:
    path = tmp_path / "sources.yaml"
    path.write_text(
        f"sources:\n{source_body}\npolicy:\n  retain_source_evidence: true\n",
        encoding="utf-8",
    )
    return path


def test_valid_oracle_source_loads_normalized_terms(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        """
  - id: official_oracle
    name: Official Oracle careers
    type: oracle_hcm
    company: Example EPC
    base_url: https://example.fa.oraclecloud.com
    site_number: CX_1
    enabled: true
    include_terms:
      - Piping
      - E3D
    location_terms:
      - India
""",
    )

    config = load_source_config(path)
    source = config.sources[0]
    assert source.text_list_option("include_terms") == ("piping", "e3d")
    assert source.text_list_option("location_terms") == ("india",)


def test_oracle_base_url_must_be_https_origin(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        """
  - id: invalid_oracle
    name: Invalid Oracle careers
    type: oracle_hcm
    company: Example EPC
    base_url: https://example.fa.oraclecloud.com/path
    site_number: CX_1
    enabled: false
""",
    )

    with pytest.raises(ValueError, match="base_url must be an HTTPS origin"):
        load_source_config(path)


def test_oracle_site_number_rejects_path_characters(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        """
  - id: invalid_site
    name: Invalid Oracle site
    type: oracle_hcm
    company: Example EPC
    base_url: https://example.fa.oraclecloud.com
    site_number: ../CX_1
    enabled: false
""",
    )

    with pytest.raises(ValueError, match="site_number contains invalid characters"):
        load_source_config(path)


def test_oracle_terms_must_be_string_lists(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        """
  - id: invalid_terms
    name: Invalid Oracle terms
    type: oracle_hcm
    company: Example EPC
    base_url: https://example.fa.oraclecloud.com
    site_number: CX_1
    enabled: false
    include_terms: piping
""",
    )

    with pytest.raises(ValueError, match="include_terms.*must be a list"):
        load_source_config(path)
