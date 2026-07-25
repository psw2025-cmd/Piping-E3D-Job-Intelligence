from __future__ import annotations

from pathlib import Path

from .database import fetch_jobs


def generate_executive_digest(db_path: Path | str, output_path: Path | str, min_score: int = 80) -> Path:
    """Generate an executive summary report for high-priority matching jobs."""
    db_file = Path(db_path)
    out_file = Path(output_path)
    
    jobs = fetch_jobs(db_file)
    
    # Filter high-priority jobs
    high_match = [j for j in jobs if int(str(j.get("match_score") or 0)) >= min_score]
    high_match.sort(key=lambda x: int(str(x.get("match_score") or 0)), reverse=True)
    
    lines = [
        "# Executive Job Intelligence Digest",
        f"**Generated:** {db_file.name}",
        f"**Total Verified High-Priority Vacancies (Score >= {min_score}):** {len(high_match)}",
        "",
        "---",
        "",
        "## Top Matching Piping & E3D Engineering Vacancies",
        ""
    ]
    
    for idx, j in enumerate(high_match, 1):
        title = str(j.get("title") or "Unknown Title")
        company = str(j.get("company") or "Unknown Employer")
        location = str(j.get("location") or "Global")
        score = int(str(j.get("match_score") or 0))
        url = str(j.get("apply_url") or "#")
        software = str(j.get("normalized_role") or "Piping Engineering")
        
        lines.append(f"### {idx}. {title}")
        lines.append(f"- **Company:** {company}")
        lines.append(f"- **Location:** {location}")
        lines.append(f"- **Match Score:** {score} / 100")
        lines.append(f"- **Domain & Role:** {software}")
        lines.append(f"- **Direct Application URL:** [{url}]({url})")
        lines.append("")
        
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text("\n".join(lines), encoding="utf-8")
    return out_file
