from __future__ import annotations

from collections.abc import Callable

from ..source_config import SourceSpec
from .common import CollectionResult
from .greenhouse import collect_greenhouse
from .http_client import HttpClient
from .lever import collect_lever
from .public_html import collect_public_html
from .rss import collect_rss
from .sitemap import collect_sitemap
from .smartrecruiters import collect_smartrecruiters

Collector = Callable[[SourceSpec, HttpClient], CollectionResult]

COLLECTORS: dict[str, Collector] = {
    "greenhouse": collect_greenhouse,
    "lever": collect_lever,
    "smartrecruiters": collect_smartrecruiters,
    "rss": collect_rss,
}

__all__ = [
    "COLLECTORS",
    "CollectionResult",
    "Collector",
    "collect_public_html",
    "collect_sitemap",
]
