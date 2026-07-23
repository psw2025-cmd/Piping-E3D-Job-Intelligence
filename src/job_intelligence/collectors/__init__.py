from __future__ import annotations

from collections.abc import Callable

from ..source_config import SourceSpec
from .common import CollectionResult
from .greenhouse import collect_greenhouse
from .http_client import HttpClient
from .lever import collect_lever
from .oracle_hcm import collect_oracle_hcm
from .public_html import collect_public_html
from .rss import collect_rss
from .sitemap import collect_sitemap
from .smartrecruiters import collect_smartrecruiters
from .workday import collect_workday

Collector = Callable[[SourceSpec, HttpClient], CollectionResult]

COLLECTORS: dict[str, Collector] = {
    "greenhouse": collect_greenhouse,
    "lever": collect_lever,
    "oracle_hcm": collect_oracle_hcm,
    "smartrecruiters": collect_smartrecruiters,
    "rss": collect_rss,
    "workday": collect_workday,
}

__all__ = [
    "COLLECTORS",
    "CollectionResult",
    "Collector",
    "collect_public_html",
    "collect_sitemap",
]
