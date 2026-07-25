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
    "career", "careers", "cv", "employment", "hr", "hiring", "job", "jobs",
    "people", "recruit", "recruiter", "recruiting", "recruitment", "resume",
    "resumes", "staffing", "talent", "vacancy", "vacancies",
}
GENERAL_LOCALS = {
    "admin", "business", "contact", "enquiries", "enquiry", "general", "hello",
    "info", "office",
}
REJECT_LOCALS = {
    "abuse", "billing", "compliance", "dmarc", "donotreply", "do-not-reply",
    "legal", "noreply", "no-reply", "postmaster", "privacy", "security",
    "support", "webmaster",
}
FREE_MAIL = {
    "aol.com", "gmail.com", "googlemail.com", "hotmail.com", "icloud.com",
    "live.com", "mail.com", "outlook.com", "proton.me", "protonmail.com",
    "rediffmail.com", "yahoo.com", "yahoo.co.in",
}
CONTEXT_TERMS = (
    "apply", "application", "candidate", "career", "cv", "employment", "hiring",
    "human resources", "job", "people team", "recruit", "resume",
    "talent acquisition", "vacancy",
)
MULTIPART_SUFFIXES = {
    "co.in", "co.uk", "com.au", "com.br", "com.cn", "com.my", "com.sg",
    "com.tr", "com.mx", "co.nz", "co.za", "org.uk", "net.au", "ae.org",
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
    classification: str
    verification_status: str
    domain_relation: str
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
        if any(payload.get(field) for field in ("name", "canonical_company_name")):
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
        not label or len(label) > 63 or label.startswith("-") or label.endswith("-")
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
        return "".join(chr(int(value[index:index + 2], 16) ^ key) for index in range(2, len(value), 2))
    except (ValueError, IndexError):
        return ""


def _context(text: str, needle: str, radius: int = 160) -> str:
    position = text.casefold().find(needle.casefold())
    if position < 0:
        return ""
    return " ".join(text[max(0, position - radius):position + len(needle) + radius].split())[:400]


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
                        found[email] = ("mailto", anchor.get_text(" ", strip=True)[:400])
        for element in soup.select("[data-cfemail]"):
            decoded = normalize_email(_decode_cfemail(str(element.get("data-cfemail") or "")))
            if decoded:
                found[decoded] = ("cloudflare_obfuscation", element.get_text(" ", strip=True)[:400])
    for match in EMAIL_RE.finditer(text):
        email = normalize_email(match.group(1))
        if email:
            found.setdefault(email, ("plaintext", _context(visible, match.group(1))))
    for match in OBFUSCATED_RE.finditer(visible):
        email = normalize_email(f"{match.group(1)}@{match.group(2)}.{match.group(3)}")
        if email:
            found.setdefault(email, ("text_obfuscation", _context(visible, match.group(0))))
    return found


def _base_domain(host: str) -> str:
    labels = host.lower().rstrip(".").split(".")
    if len(labels) <= 2:
        return host.lower().rstrip(".")
    suffix2 = ".".join(labels[-2:])
    return ".".join(labels[-3:]) if suffix2 in MULTIPART_SUFFIXES else suffix2


def domain_relation(email: str, hosts: Iterable[str]) -> str:
    domain = email.rsplit("@", 1)[1]
    if domain in FREE_MAIL:
        return "free_mail"
    official_bases = {_base_domain(host) for host in hosts}
    return "official_domain" if _base_domain(domain) in official_bases else "third_party_domain"


def classify_contact(email: str, context: str) -> str:
    local = email.split("@", 1)[0]
    tokens = set(re.split(r"[._+\-]+", local))
    collapsed = re.sub(r"[^a-z0-9]", "", local)
    rejected = {re.sub(r"[^a-z0-9]", "", item) for item in REJECT_LOCALS}
    if local in REJECT_LOCALS or collapsed in rejected:
        return "system_or_non_application"
    if local in JOB_LOCALS or tokens & JOB_LOCALS:
        return "recruitment_role_mailbox"
    if any(term in context.casefold() for term in CONTEXT_TERMS):
        return "named_recruitment_contact"
    if local in GENERAL_LOCALS or tokens & GENERAL_LOCALS:
        return "general_business_contact"
    return "other_public_contact"


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


def verification_decision(classification: str, relation: str, mail_status: str) -> tuple[str, int, str]:
    if classification == "system_or_non_application":
        return "rejected", 0, "non-application mailbox"
    if mail_status not in {"mx", "implicit_mx"}:
        return "manual_review", 10, f"mail route not proven: {mail_status}"
    score = 20 + (35 if relation == "official_domain" else -10 if relation == "free_mail" else 0)
    score += {
        "recruitment_role_mailbox": 45,
        "named_recruitment_contact": 35,
        "general_business_contact": 20,
        "other_public_contact": 10,
    }[classification]
    if relation == "official_domain" and classification == "recruitment_role_mailbox":
        return "verified_public_job_contact", min(score, 100), ""
    if relation == "official_domain" and classification == "named_recruitment_contact":
        return "verified_public_named_recruiter", min(score, 100), ""
    if relation == "official_domain":
        return "verified_public_general_contact", min(score, 100), ""
    reason = "public address uses third-party domain"
    if relation == "free_mail":
        reason = "public free-mail address requires review"
    return "manual_review", min(score, 100), reason


def _robots_allowed(client: SafeHttpClient, url: str, cache: dict[str, bool | RobotFileParser]) -> bool:
    parsed = urlsplit(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    policy = cache.get(origin)
    if policy is None:
        try:
            response = client.get(f"{origin}/robots.txt", allowed_statuses={200, 403, 404})
            if response.status_code == 404:
                policy = True
            elif response.status_code == 403:
                policy = False
            else:
                parser = RobotFileParser()
                parser.parse(response.text.splitlines())
                policy = parser
        except Exception:
            policy = False
        cache[origin] = policy
    return policy if isinstance(policy, bool) else policy.can_fetch(client.user_agent, url)


def _fetch(client: SafeHttpClient, url: str, attempts: int = 3):
    for attempt in range(attempts):
        response = client.get(url, allowed_statuses={200, 403, 404, *RETRY_STATUSES})
        if response.status_code not in RETRY_STATUSES or attempt == attempts - 1:
            return response
        time.sleep(min(2 ** attempt, 4))
    raise AssertionError("unreachable")


def _links(html_text: str, base_url: str, allowed_hosts: frozenset[str]) -> list[str]:
    soup = BeautifulSoup(html_text, "html.parser")
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        if not href or href.lower().startswith(("mailto:", "tel:", "javascript:")):
            continue
        candidate = urljoin(base_url, href).split("#", 1)[0]
        parsed = urlsplit(candidate)
        if parsed.scheme not in {"http", "https"} or (parsed.hostname or "").lower() not in allowed_hosts:
            continue
        descriptor = f"{parsed.path} {anchor.get_text(' ', strip=True)}".casefold()
        if not any(hint in descriptor for hint in LINK_HINTS) and not parsed.path.lower().endswith(".pdf"):
            continue
        if candidate not in links:
            links.append(candidate)
        if len(links) >= 40:
            break
    return links


def _pdf_text(content: bytes, max_pages: int = 15) -> str:
    reader = PdfReader(BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages[:max_pages])


def _seed_urls(target: Target) -> list[str]:
    seeds = list(target.urls)
    first = target.urls[0]
    parsed = urlsplit(first)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    for path in COMMON_PATHS:
        candidate = f"{origin}{path}"
        if candidate not in seeds:
            seeds.append(candidate)
    return seeds


def scan_target(target: Target, *, max_pages: int, timeout_seconds: int, rate_limit: int) -> tuple[list[Contact], list[Failure]]:
    client = SafeHttpClient(
        timeout_seconds=timeout_seconds,
        rate_limit_per_minute=rate_limit,
        max_response_bytes=20_000_000,
        allowed_domains=target.hosts,
    )
    mail = MailRouteValidator()
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
            failures.append(Failure(target.organization, url, "robots", "disallowed or unavailable policy"))
            continue
        try:
            response = _fetch(client, url)
        except Exception as exc:
            failures.append(Failure(target.organization, url, "fetch", f"{type(exc).__name__}: {exc}"))
            continue
        if response.status_code != 200:
            failures.append(Failure(target.organization, url, "http", f"HTTP {response.status_code}"))
            continue
        pages += 1
        content_type = response.headers.get("content-type", "").lower()
        sha256 = hashlib.sha256(response.content).hexdigest()
        try:
            if "pdf" in content_type or urlsplit(response.url).path.lower().endswith(".pdf"):
                text = _pdf_text(response.content)
                candidates = extract_emails(text, html_content=False)
            else:
                text = response.text
                candidates = extract_emails(text, html_content=True)
                queue.extend(_links(text, response.url, target.hosts))
        except Exception as exc:
            failures.append(Failure(target.organization, url, "parse", f"{type(exc).__name__}: {exc}"))
            continue
        for email, (method, context) in candidates.items():
            classification = classify_contact(email, context)
            relation = domain_relation(email, target.hosts)
            mail_status = mail.check(email.rsplit("@", 1)[1])
            status, score, reason = verification_decision(classification, relation, mail_status)
            contact = Contact(
                organization=target.organization,
                record_type=target.record_type,
                country=target.country,
                email=email,
                classification=classification,
                verification_status=status,
                domain_relation=relation,
                mail_route_status=mail_status,
                priority_score=score,
                source_url=response.url,
                source_sha256=sha256,
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
                failures.append(Failure(target.organization, "", "target", f"{type(exc).__name__}: {exc}"))
                continue
            contacts.extend(target_contacts)
            failures.extend(target_failures)
    return contacts, failures


def _frame(rows: Iterable[Any], columns: list[str]) -> pd.DataFrame:
    data = [asdict(row) if hasattr(row, "__dataclass_fields__") else dict(row) for row in rows]
    return pd.DataFrame(data, columns=columns)


def write_outputs(output_dir: str | Path, contacts: list[Contact], failures: list[Failure], target_count: int) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    contact_columns = list(Contact.__dataclass_fields__)
    failure_columns = list(Failure.__dataclass_fields__)
    all_contacts = _frame(contacts, contact_columns)
    if not all_contacts.empty:
        all_contacts = all_contacts.sort_values(
            ["priority_score", "organization", "email"], ascending=[False, True, True]
        ).drop_duplicates(["organization", "email"], keep="first")
    failures_frame = _frame(failures, failure_columns)
    verified_job = all_contacts[all_contacts["verification_status"].isin(
        ["verified_public_job_contact", "verified_public_named_recruiter"]
    )] if not all_contacts.empty else all_contacts.copy()
    verified_general = all_contacts[all_contacts["verification_status"].eq(
        "verified_public_general_contact"
    )] if not all_contacts.empty else all_contacts.copy()
    manual = all_contacts[all_contacts["verification_status"].eq("manual_review")] if not all_contacts.empty else all_contacts.copy()
    rejected = all_contacts[all_contacts["verification_status"].eq("rejected")] if not all_contacts.empty else all_contacts.copy()
    frames = {
        "All_Public_Contacts": all_contacts,
        "Verified_Job_Contacts": verified_job,
        "Verified_General": verified_general,
        "Manual_Review": manual,
        "Rejected": rejected,
        "Failures": failures_frame,
    }
    for name, frame in frames.items():
        frame.to_csv(output / f"{name}.csv", index=False, encoding="utf-8-sig")
    summary = {
        "generated_at_utc": _now(),
        "targets_scanned": target_count,
        "all_public_contacts": len(all_contacts),
        "verified_job_contacts": len(verified_job),
        "verified_general_contacts": len(verified_general),
        "manual_review": len(manual),
        "rejected": len(rejected),
        "failures": len(failures_frame),
        "unique_emails": int(all_contacts["email"].nunique()) if not all_contacts.empty else 0,
        "organizations_with_contacts": int(all_contacts["organization"].nunique()) if not all_contacts.empty else 0,
    }
    pd.DataFrame(summary.items(), columns=["metric", "value"]).to_csv(output / "Summary.csv", index=False)
    with pd.ExcelWriter(output / "Global_Public_Contacts.xlsx", engine="openpyxl") as writer:
        for name, frame in frames.items():
            frame.to_excel(writer, sheet_name=name[:31], index=False)
        pd.DataFrame(summary.items(), columns=["metric", "value"]).to_excel(writer, sheet_name="Summary", index=False)
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output / "SUMMARY.md").write_text(
        "# Global Public Contact Discovery\n\n"
        + "\n".join(f"- **{key.replace('_', ' ').title()}**: {value}" for key, value in summary.items())
        + "\n",
        encoding="utf-8",
    )
    archive_path = output / "Global_Public_Contacts_Bundle.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.iterdir()):
            if path != archive_path and path.is_file():
                archive.write(path, arcname=path.name)
    return archive_path


def merge_outputs(input_root: str | Path, output_dir: str | Path) -> Path:
    root = Path(input_root)
    contact_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    targets = 0
    for path in root.rglob("All_Public_Contacts.csv"):
        contact_rows.extend(pd.read_csv(path).fillna("").to_dict("records"))
    for path in root.rglob("Failures.csv"):
        failure_rows.extend(pd.read_csv(path).fillna("").to_dict("records"))
    for path in root.rglob("summary.json"):
        targets += int(json.loads(path.read_text(encoding="utf-8")).get("targets_scanned", 0))
    contacts = [Contact(**{field: row.get(field, "") for field in Contact.__dataclass_fields__}) for row in contact_rows]
    failures = [Failure(**{field: row.get(field, "") for field in Failure.__dataclass_fields__}) for row in failure_rows]
    return write_outputs(output_dir, contacts, failures, targets)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Discover public employer/recruiter contacts")
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
        print(f"PASS: merged public contacts bundle at {archive}")
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
    print(f"PASS: targets={len(targets)} contacts={len(contacts)} failures={len(failures)} bundle={archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
