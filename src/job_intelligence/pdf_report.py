from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

from .database import fetch_jobs


class ExecutivePDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(24, 43, 73) # Navy blue
        self.cell(0, 10, "Executive Job Intelligence Digest", border=False, new_x="LMARGIN", new_y="NEXT", align="C")
        self.set_font("Helvetica", "I", 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 6, "Verified Piping, AVEVA E3D & Plant Engineering Vacancies", border=False, new_x="LMARGIN", new_y="NEXT", align="C")
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}} | Confidential Piping & E3D Job Intelligence Report", align="C")


def generate_executive_digest(db_path: Path | str, output_path: Path | str, min_score: int = 80) -> Path:
    """Generate an executive summary report for high-priority matching jobs in both Markdown and PDF format."""
    db_file = Path(db_path)
    out_file = Path(output_path)
    
    # Ensure both PDF and Markdown output paths
    pdf_out_file = out_file.with_suffix(".pdf")
    md_out_file = out_file.with_suffix(".md")
    
    jobs = fetch_jobs(db_file)
    
    # Filter high-priority jobs
    high_match = [j for j in jobs if int(str(j.get("match_score") or 0)) >= min_score]
    high_match.sort(key=lambda x: int(str(x.get("match_score") or 0)), reverse=True)
    
    # 1. Generate Markdown Digest
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
        software = str(j.get("software_text") or j.get("normalized_role") or "Piping Engineering")
        posted = str(j.get("published_at") or "Recently Posted")[:10]
        
        lines.append(f"### {idx}. {title}")
        lines.append(f"- **Company:** {company}")
        lines.append(f"- **Location:** {location}")
        lines.append(f"- **Match Score:** {score} / 100")
        lines.append(f"- **Posted Date:** {posted}")
        lines.append(f"- **Software / Domain:** {software}")
        lines.append(f"- **Direct Application Link:** [{url}]({url})")
        lines.append("")
        
    md_out_file.parent.mkdir(parents=True, exist_ok=True)
    md_out_file.write_text("\n".join(lines), encoding="utf-8")
    
    # 2. Generate PDF Digest using FPDF
    pdf = ExecutivePDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(24, 43, 73)
    pdf.cell(0, 8, f"Total High-Priority Verified Vacancies (Score >= {min_score}): {len(high_match)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    
    for idx, j in enumerate(high_match, 1):
        title = str(j.get("title") or "Unknown Title").encode("latin-1", "replace").decode("latin-1")
        company = str(j.get("company") or "Unknown Employer").encode("latin-1", "replace").decode("latin-1")
        location = str(j.get("location") or "Global").encode("latin-1", "replace").decode("latin-1")
        score = int(str(j.get("match_score") or 0))
        url = str(j.get("apply_url") or "#")
        software = str(j.get("software_text") or j.get("normalized_role") or "Piping Engineering").encode("latin-1", "replace").decode("latin-1")
        posted = str(j.get("published_at") or "Recently Posted")[:10]
        
        # Job Card Header
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(24, 43, 73)
        pdf.cell(0, 6, f"{idx}. {title}", new_x="LMARGIN", new_y="NEXT")
        
        # Meta Info
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(70, 70, 70)
        pdf.cell(0, 5, f"Employer: {company}  |  Location: {location}  |  Match Score: {score}/100", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 5, f"Posted Date: {posted}  |  Software: {software}", new_x="LMARGIN", new_y="NEXT")
        
        # Clickable Apply Link
        if url and url != "#":
            pdf.set_font("Helvetica", "U", 9)
            pdf.set_text_color(0, 102, 204) # Blue hyperlink
            pdf.cell(0, 5, "Click Here to Apply Directly", link=url, new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_text_color(120, 120, 120)
            pdf.cell(0, 5, "Direct Link: Contact via Employer Portal", new_x="LMARGIN", new_y="NEXT")
            
        pdf.ln(3)
        
    pdf.output(str(pdf_out_file))
    
    # Return the markdown path or primary specified path
    return md_out_file if out_file.suffix == ".md" else pdf_out_file
