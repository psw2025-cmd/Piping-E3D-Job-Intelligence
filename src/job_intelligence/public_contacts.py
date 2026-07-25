from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import zipfile
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import dns.exception
import dns.resolver
import pandas as pd
import yaml
from bs4 import BeautifulSoup
from defusedxml import ElementTree
from pypdf import PdfReader

from .collectors.http_client import SafeHttpClient

EMAIL_RE = re.compile(
    r"(?<![A-Z0-9._%+-])([A-Z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
    r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+)",
    re.IGNORECASE,
)
OBFUSCATED_RE = re.compile(
    r"([A-Z0-9._%+-]+)\s*(?:\[at\]|\(at\)|\sat\s)\s*"
    r"([A-Z0-9.-]+)\s*(?:\[dot\]|\(dot\)|\sdot\s)\s*([A-Z]{2,24})",
    re.IGNORECASE,
)
URL_FIELDS = (
    "careers_url",
    "career_url",
    "careers_page",
    "contact_url",
    "direct_ats_endpoint",
    "official_domain",
    "official_url",
    "source_url",
    "url",
    "website",
)
COMMON_PATHS = (
    "/careers",
    "/jobs",
    "/contact",
    "/contact-us",
    "/join-us",
    "/recruitment",
    "/sitemap.xml",
)
LINK_HINTS = (
    "career",
    "contact",
    "employment",
    "hr",
    "job",
    "join",
    "people",
    "recruit",
    "talent",
    "vacan",
)
JOB_LOCALS = {
    "career",
    "careers",
    "cv",
    "employment",
    "hr",
    "hiring",
    "job",
    "jobs",
    "people",
    "recruit",
    "recruiter",
    "recruiting",
    "recruitment",
    "resume",
    "resumes",
    "staffing",
    "talent",
    "vacancy",
    "vacancies",
}
GENERAL_LOCALS = {
    "admin",
    "business",
    "contact",
    "enquiries",
    "enquiry",
    "general",
    "hello",
    "info",
    "office",
}
MULTIPART_SUFFIXES = {
    "co.in",
    "co.uk",
    "com.au",
    "com.br",
    "com.cn",
    "com.my",
    "com.sg",
    "com.tr",
    "com.mx",
    "co.nz",
    "co.za",
    "org.uk",
    "net.au",
}
RETRY_STATUSES = {429, 500, 502, 503, 504}


@dataclass(frozen=True, slots=True)
class Target:
    organization: str
    record_type: str
    country: str
    urls: tuple[str, ...]
    hosts: frozenset[str]


@dataclass(frozen=True, slots=True)
class Contact:
    organization: str
    record_type: str
    country: str
    email: str
    mailbox_type: str
    verification_status: str
    mail_route_status: str
    priority_score: int
    source_url: str
    source_sha256: str
    extraction_method: str
    evidence_context: str
    discovered_at_utc: str
    review_reason: str


@dataclass(frozen=True, slots=True)
class Failure:
    organization: str
    url: str
    stage: str
    error: str


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _valid_url(value: object) -> str:
    text = str(value or "").strip().split("#", 1)[0]
    parsed = urlsplit(text)
    return text if parsed.scheme in {"http", "https"} and parsed.hostname else ""


def _host_variants(urls: Iterable[str]) -> frozenset[str]:
    hosts: set[str] = set()
    for url in urls:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
        if not host:
            continue
        hosts.add(host)
        hosts.add(host[4:] if host.startswith("www.") else f"www.{host}")
    return frozenset(hosts)


def _iter_records(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, dict):
        if payload.get("name") or payload.get("canonical_company_name"):
            yield payload
        for value in payload.values():
            yield from _iter_records(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _iter_records(item)


def load_targets(
    registry_paths: Iterable[str | Path],
    *,
    shard_index: int = 0,
    shard_count: int = 1,
    max_organizations: int = 0,
) -> list[Target]:
    if shard_count < 1 or not 0 <= shard_index < shard_count:
        raise ValueError("invalid shard configuration")
    targets: list[Target] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    position = 0
    for registry_path in registry_paths:
        payload = yaml.safe_load(Path(registry_path).read_text(encoding="utf-8")) or {}
        for row in _iter_records(payload):
            name = str(row.get("canonical_company_name") or row.get("name") or "").strip()
            if not name:
                continue
            urls: list[str] = []
            for field in URL_FIELDS:
                candidate = _valid_url(row.get(field))
                if candidate and candidate not in urls:
                    urls.append(candidate)
            if not urls:
                continue
            key = (name.casefold(), tuple(sorted(urls)))
            if key in seen:
                continue
            seen.add(key)
            selected = position % shard_count == shard_index
            position += 1
            if not selected:
                continue
            targets.append(
                Target(
                    organization=name,
                    record_type=str(row.get("record_type") or "employer").strip().lower(),
                    country=str(row.get("country") or "").strip(),
                    urls=tuple(urls),
                    hosts=_host_variants(urls),
                )
            )
            if max_organizations and len(targets) >= max_organizations:
                return targets
    return targets


def normalize_email(value: str) -> str:
    text = unquote(value).strip()
    if text.lower().startswith("mailto:"):
        text = text[7:]
    text = text.split("?", 1)[0].strip(" <>\"'()[]{}.,;:").lower()
    if len(text) > 254 or text.count("@") != 1:
        return ""
    local, domain = text.rsplit("@", 1)
    if not local or len(local) > 64 or local.startswith(".") or local.endswith("."):
        return ""
    if ".." in local or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+", local):
        return ""
    try:
        domain = domain.encode("idna").decode("ascii").rstrip(".")
    except UnicodeError:
        return ""
    labels = domain.split(".")
    if len(labels) < 2 or any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        or not re.fullmatch(r"[a-z0-9-]+", label)
        for label in labels
    ):
        return ""
    if labels[-1] in {"gif", "jpg", "jpeg", "pdf", "png", "svg", "webp"}:
        return ""
    return f"{local}@{domain}"


def _decode_cfemail(value: str) -> str:
    try:
        key = int(value[:2], 16)
        return "".join(
            chr(int(value[index : index + 2], 16) ^ key)
            for index in range(2, len(value), 2)
        )
    except (ValueError, IndexError):
        return ""


def _context(text: str, needle: str, radius: int = 160) -> str:
    position = text.casefold().find(needle.casefold())
    if position < 0:
        return ""
    start = max(0, position - radius)
    end = position + len(needle) + radius
    return " ".join(text[start:end].split())[:400]


def extract_emails(text: str, *, html_content: bool) -> dict[str, tuple[str, str]]:
    found: dict[str, tuple[str, str]] = {}
    visible = text
    if html_content:
        soup = BeautifulSoup(text, "html.parser")
        visible = soup.get_text(" ", strip=True)
        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href") or "")
            if href.lower().startswith("mailto:"):
                for raw in re.split(r"[,;]", href[7:].split("?", 1)[0]):
                    email = normalize_email(raw)
                    if email:
                        found[email] = (
                            "mailto",
                            anchor.get_text(" ", strip=True)[:400],
                        )
        for element in soup.select("[data-cfemail]"):
            decoded = normalize_email(
                _decode_cfemail(str(element.get("data-cfemail") or ""))
            )
            if decoded:
                found[decoded] = (
                    "cloudflare_obfuscation",
                    element.get_text(" ", strip=True)[:400],
                )
    for match in EMAIL_RE.finditer(text):
        email = normalize_email(match.group(1))
        if email:
            found.setdefault(
                email,
                ("plaintext", _context(visible, match.group(1))),
            )
    for match in OBFUSCATED_RE.finditer(visible):
        email = normalize_email(
            f"{match.group(1)}@{match.group(2)}.{match.group(3)}"
        )
        if email:
            found.setdefault(
                email,
                ("text_obfuscation", _context(visible, match.group(0))),
            )
    return found


def _base_domain(host: str) -> str:
    labels = host.lower().rstrip(".").split(".")
    if len(labels) <= 2:
        return host.lower().rstrip(".")
    suffix = ".".join(labels[-2:])
    return ".".join(labels[-3:]) if suffix in MULTIPART_SUFFIXES else suffix


def is_official_domain(email: str, hosts: Iterable[str]) -> bool:
    email_domain = _base_domain(email.rsplit("@", 1)[1])
    return email_domain in {_base_domain(host) for host in hosts}


def mailbox_type(email: str) -> str:
    local = email.split("@", 1)[0]
    tokens = set(re.split(r"[._+\-]+", local))
    if local in JOB_LOCALS or tokens & JOB_LOCALS:
        return "job_or_recruitment"
    if local in GENERAL_LOCALS or tokens & GENERAL_LOCALS:
        return "general_business"
    return "excluded_non_role"


class MailRouteValidator:
    def __init__(self, lifetime_seconds: float = 6.0) -> None:
        self.resolver = dns.resolver.Resolver(configure=True)
        self.resolver.lifetime = lifetime_seconds
        self.cache: dict[str, str] = {}

    def check(self, domain: str) -> str:
        cached = self.cache.get(domain)
        if cached:
            return cached
        try:
            answers = self.resolver.resolve(domain, "MX")
            exchanges = [str(answer.exchange).rstrip(".") for answer in answers]
            status = "mx" if any(exchanges) else "null_mx"
        except dns.resolver.NXDOMAIN:
            status = "nxdomain"
        except dns.resolver.NoAnswer:
            status = self._implicit(domain)
        except dns.exception.Timeout:
            status = "dns_timeout"
        except dns.exception.DNSException:
            status = "dns_error"
        self.cache[domain] = status
        return status

    def _implicit(self, domain: str) -> str:
        for record_type in ("A", "AAAA"):
            try:
                if list(self.resolver.resolve(domain, record_type)):
                    return "implicit_mx"
            except dns.exception.DNSException:
                continue
        return "no_mail_route"


def verification_decision(kind: str, mail_status: str) -> tuple[str, int, str]:
    if kind == "job_or_recruitment":
        base_score = 100
        verified_status = "verified_official_job_mailbox"
    elif kind == "general_business":
        base_score = 70
        verified_status = "verified_official_general_mailbox"
    else:
        return "excluded", 0, "not a role-based organizational mailbox"
    if mail_status in {"mx", "implicit_mx"}:
        return verified_status, base_score, ""
    return "manual_review_dns", max(base_score - 40, 1), f"mail route not proven: {mail_status}"


def _robots_allowed(
    client: SafeHttpClient,
    url: str,
    cache: dict[str, bool | RobotFileParser],
) -> bool:
    parsed = urlsplit(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    policy = cache.get(origin)
    if policy is None:
        try:
            response = client.get(
                f"{origin}/robots.txt",
                allowed_statuses={200, 403, 404},
            )
            if response.status_code == 404:
                policy = True
            elif response.status_code == 403:
                policy = False
            else:
                parser = RobotFileParser()
                parser.parse(response.text.splitlines())
                policy = parser
        except Exception:
            policy = True
        cache[origin] = policy
    return policy if isinstance(policy, bool) else policy.can_fetch(client.user_agent, url)


def _fetch(client: SafeHttpClient, url: str, attempts: int = 3):
    for attempt in range(attempts):
        response = client.get(
            url,
            allowed_statuses={200, 403, 404, *RETRY_STATUSES},
        )
        if response.status_code not in RETRY_STATUSES or attempt == attempts - 1:
            return response
        time.sleep(min(2**attempt, 4))
    raise AssertionError("unreachable")


def _html_links(
    html_text: str,
    base_url: str,
    allowed_hosts: frozenset[str],
) -> list[str]:
    soup = BeautifulSoup(html_text, "html.parser")
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        if not href or href.lower().startswith(("mailto:", "tel:", "javascript:")):
            continue
        candidate = urljoin(base_url, href).split("#", 1)[0]
        parsed = urlsplit(candidate)
        if parsed.scheme not in {"http", "https"}:
            continue
        if (parsed.hostname or "").lower() not in allowed_hosts:
            continue
        descriptor = f"{parsed.path} {anchor.get_text(' ', strip=True)}".casefold()
        if not any(hint in descriptor for hint in LINK_HINTS):
            if not parsed.path.lower().endswith(".pdf"):
                continue
        if candidate not in links:
            links.append(candidate)
        if len(links) >= 50:
            break
    return links


def _sitemap_links(content: bytes, allowed_hosts: frozenset[str]) -> list[str]:
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError:
        return []
    links: list[str] = []
    for element in root.iter():
        if not element.tag.lower().endswith("loc") or not element.text:
            continue
        candidate = element.text.strip().split("#", 1)[0]
        parsed = urlsplit(candidate)
        if (parsed.hostname or "").lower() not in allowed_hosts:
            continue
        if not any(hint in parsed.path.casefold() for hint in LINK_HINTS):
            continue
        if candidate not in links:
            links.append(candidate)
        if len(links) >= 100:
            break
    return links


def _pdf_text(content: bytes, max_pages: int = 15) -> str:
    reader = PdfReader(BytesIO(content))
    return "\n".join(
        (page.extract_text() or "")
        for page in reader.pages[:max_pages]
    )


def _seed_urls(target: Target) -> list[str]:
    seeds = list(target.urls)
    parsed = urlsplit(target.urls[0])
    origin = f"{parsed.scheme}://{parsed.netloc}"
    for path in COMMON_PATHS:
        candidate = f"{origin}{path}"
        if candidate not in seeds:
            seeds.append(candidate)
    return seeds


def scan_target(
    target: Target,
    *,
    max_pages: int,
    timeout_seconds: int,
    rate_limit: int,
) -> tuple[list[Contact], list[Failure]]:
    client = SafeHttpClient(
        timeout_seconds=timeout_seconds,
        rate_limit_per_minute=rate_limit,
        max_response_bytes=20_000_000,
        allowed_domains=target.hosts,
    )
    validator = MailRouteValidator()
    queue: deque[str] = deque(_seed_urls(target))
    visited: set[str] = set()
    robots: dict[str, bool | RobotFileParser] = {}
    contacts: dict[str, Contact] = {}
    failures: list[Failure] = []
    pages = 0
    while queue and pages < max_pages:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        if not _robots_allowed(client, url, robots):
            failures.append(Failure(target.organization, url, "robots", "disallowed"))
            continue
        try:
            response = _fetch(client, url)
        except Exception as exc:
            failures.append(
                Failure(
                    target.organization,
                    url,
                    "fetch",
                    f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        if response.status_code != 200:
            failures.append(
                Failure(target.organization, url, "http", f"HTTP {response.status_code}")
            )
            continue
        pages += 1
        content_type = response.headers.get("content-type", "").lower()
        source_sha256 = hashlib.sha256(response.content).hexdigest()
        try:
            if "xml" in content_type or response.url.lower().endswith(".xml"):
                queue.extend(_sitemap_links(response.content, target.hosts))
                candidates: dict[str, tuple[str, str]] = {}
            elif "pdf" in content_type or response.url.lower().endswith(".pdf"):
                candidates = extract_emails(
                    _pdf_text(response.content),
                    html_content=False,
                )
            else:
                candidates = extract_emails(response.text, html_content=True)
                queue.extend(_html_links(response.text, response.url, target.hosts))
        except Exception as exc:
            failures.append(
                Failure(
                    target.organization,
                    response.url,
                    "parse",
                    f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        for email, (method, context) in candidates.items():
            kind = mailbox_type(email)
            if kind == "excluded_non_role" or not is_official_domain(email, target.hosts):
                continue
            mail_status = validator.check(email.rsplit("@", 1)[1])
            status, score, reason = verification_decision(kind, mail_status)
            contact = Contact(
                organization=target.organization,
                record_type=target.record_type,
                country=target.country,
                email=email,
                mailbox_type=kind,
                verification_status=status,
                mail_route_status=mail_status,
                priority_score=score,
                source_url=response.url,
                source_sha256=source_sha256,
                extraction_method=method,
                evidence_context=context,
                discovered_at_utc=_now(),
                review_reason=reason,
            )
            previous = contacts.get(email)
            if previous is None or contact.priority_score > previous.priority_score:
                contacts[email] = contact
    return list(contacts.values()), failures


def scan_targets(
    targets: list[Target],
    *,
    workers: int,
    max_pages: int,
    timeout_seconds: int,
    rate_limit: int,
) -> tuple[list[Contact], list[Failure]]:
    contacts: list[Contact] = []
    failures: list[Failure] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(
                scan_target,
                target,
                max_pages=max_pages,
                timeout_seconds=timeout_seconds,
                rate_limit=rate_limit,
            ): target
            for target in targets
        }
        for future in as_completed(futures):
            target = futures[future]
            try:
                target_contacts, target_failures = future.result()
            except Exception as exc:
                failures.append(
                    Failure(
                        target.organization,
                        "",
                        "target",
                        f"{type(exc).__name__}: {exc}",
                    )
                )
                continue
            contacts.extend(target_contacts)
            failures.extend(target_failures)
    return contacts, failures


def _frame(rows: Iterable[Any], columns: list[str]) -> pd.DataFrame:
    data = [asdict(row) for row in rows]
    return pd.DataFrame(data, columns=columns)


def write_outputs(
    output_dir: str | Path,
    contacts: list[Contact],
    failures: list[Failure],
    target_count: int,
) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    all_contacts = _frame(contacts, list(Contact.__dataclass_fields__))
    if not all_contacts.empty:
        all_contacts = (
            all_contacts.sort_values(
                ["priority_score", "organization", "email"],
                ascending=[False, True, True],
            )
            .drop_duplicates(["organization", "email"], keep="first")
            .reset_index(drop=True)
        )
    failures_frame = _frame(failures, list(Failure.__dataclass_fields__))
    official_job = all_contacts[
        all_contacts["verification_status"].eq("verified_official_job_mailbox")
    ] if not all_contacts.empty else all_contacts.copy()
    official_general = all_contacts[
        all_contacts["verification_status"].eq("verified_official_general_mailbox")
    ] if not all_contacts.empty else all_contacts.copy()
    manual_review = all_contacts[
        all_contacts["verification_status"].eq("manual_review_dns")
    ] if not all_contacts.empty else all_contacts.copy()
    frames = {
        "All_Official_Contacts": all_contacts,
        "Official_Job_Mailboxes": official_job,
        "Official_General_Mailboxes": official_general,
        "Manual_Review_DNS": manual_review,
        "Failures": failures_frame,
    }
    for name, frame in frames.items():
        frame.to_csv(output / f"{name}.csv", index=False, encoding="utf-8-sig")
    summary = {
        "generated_at_utc": _now(),
        "targets_scanned": target_count,
        "all_official_contacts": len(all_contacts),
        "official_job_mailboxes": len(official_job),
        "official_general_mailboxes": len(official_general),
        "manual_review_dns": len(manual_review),
        "failures": len(failures_frame),
        "unique_emails": int(all_contacts["email"].nunique()) if not all_contacts.empty else 0,
        "organizations_with_contacts": (
            int(all_contacts["organization"].nunique()) if not all_contacts.empty else 0
        ),
    }
    summary_frame = pd.DataFrame(summary.items(), columns=["metric", "value"])
    summary_frame.to_csv(output / "Summary.csv", index=False)
    with pd.ExcelWriter(
        output / "Global_Official_Hiring_Contacts.xlsx",
        engine="openpyxl",
    ) as writer:
        for name, frame in frames.items():
            frame.to_excel(writer, sheet_name=name[:31], index=False)
        summary_frame.to_excel(writer, sheet_name="Summary", index=False)
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    (output / "SUMMARY.md").write_text(
        "# Global Official Hiring Contacts\n\n"
        + "\n".join(
            f"- **{key.replace('_', ' ').title()}**: {value}"
            for key, value in summary.items()
        )
        + "\n",
        encoding="utf-8",
    )
    archive_path = output / "Global_Official_Hiring_Contacts_Bundle.zip"
    with zipfile.ZipFile(
        archive_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for path in sorted(output.iterdir()):
            if path != archive_path and path.is_file():
                archive.write(path, arcname=path.name)
    return archive_path


def merge_outputs(input_root: str | Path, output_dir: str | Path) -> Path:
    root = Path(input_root)
    contact_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    targets = 0
    for path in root.rglob("All_Official_Contacts.csv"):
        contact_rows.extend(pd.read_csv(path).fillna("").to_dict("records"))
    for path in root.rglob("Failures.csv"):
        failure_rows.extend(pd.read_csv(path).fillna("").to_dict("records"))
    for path in root.rglob("summary.json"):
        targets += int(
            json.loads(path.read_text(encoding="utf-8")).get("targets_scanned", 0)
        )
    contacts = [
        Contact(
            **{
                field: row.get(field, "")
                for field in Contact.__dataclass_fields__
            }
        )
        for row in contact_rows
    ]
    failures = [
        Failure(
            **{
                field: row.get(field, "")
                for field in Failure.__dataclass_fields__
            }
        )
        for row in failure_rows
    ]
    return write_outputs(output_dir, contacts, failures, targets)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover official role-based hiring contact mailboxes"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan = subparsers.add_parser("scan")
    scan.add_argument("--registry", action="append", required=True)
    scan.add_argument("--output", required=True)
    scan.add_argument("--workers", type=int, default=12)
    scan.add_argument("--max-pages", type=int, default=8)
    scan.add_argument("--timeout", type=int, default=20)
    scan.add_argument("--rate-limit", type=int, default=30)
    scan.add_argument("--shard-index", type=int, default=0)
    scan.add_argument("--shard-count", type=int, default=1)
    scan.add_argument("--max-organizations", type=int, default=0)
    merge = subparsers.add_parser("merge")
    merge.add_argument("--input-root", required=True)
    merge.add_argument("--output", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "merge":
        archive = merge_outputs(args.input_root, args.output)
        print(f"PASS: merged official hiring contact bundle at {archive}")
        return 0
    targets = load_targets(
        args.registry,
        shard_index=args.shard_index,
        shard_count=args.shard_count,
        max_organizations=args.max_organizations,
    )
    contacts, failures = scan_targets(
        targets,
        workers=args.workers,
        max_pages=args.max_pages,
        timeout_seconds=args.timeout,
        rate_limit=args.rate_limit,
    )
    archive = write_outputs(args.output, contacts, failures, len(targets))
    print(
        f"PASS: targets={len(targets)} contacts={len(contacts)} "
        f"failures={len(failures)} bundle={archive}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
