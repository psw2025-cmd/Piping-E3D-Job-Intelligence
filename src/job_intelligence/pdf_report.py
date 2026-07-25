from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

from .database import fetch_jobs


class ExecutivePDF(FPDF):
    def header(self):
        # Top banner
        self.set_fill_color(24, 43, 73) # Deep Navy
        self.rect(0, 0, 210, 18, "F")
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(255, 255, 255)
        self.set_xy(10, 4)
        self.cell(0, 10, "PIPING & E3D EXECUTIVE JOB INTELLIGENCE BRIEFING", border=False, align="L")
        self.ln(16)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}} | Confidential Executive Report | Piping-E3D-Job-Intelligence", align="C")


def generate_executive_digest(db_path: Path | str, output_path: Path | str, min_score: int = 80) -> Path:
    """Generate a world-class executive summary report in both Markdown and PDF format."""
    db_file = Path(db_path)
    out_file = Path(output_path)
    
    pdf_out_file = out_file.with_suffix(".pdf")
    md_out_file = out_file.with_suffix(".md")
    
    jobs = fetch_jobs(db_file)
    
    # Filter high-priority jobs
    high_match = [j for j in jobs if int(str(j.get("match_score") or 0)) >= min_score]
    high_match.sort(key=lambda x: int(str(x.get("match_score") or 0)), reverse=True)
    
    # Analytics breakdown
    top_employers = list(dict.fromkeys([str(j.get("company")) for j in high_match if j.get("company")]))[:5]
    top_locations = list(dict.fromkeys([str(j.get("location")) for j in high_match if j.get("location")]))[:5]
    
    # 1. Generate Markdown Digest
    lines = [
        "# Executive Job Intelligence Digest - Piping & E3D Briefing",
        f"**Database Ledger:** `{db_file.name}`",
        f"**Total Verified High-Priority Vacancies (Score >= {min_score}):** {len(high_match)}",
        f"**Top Hiring Employers:** {', '.join(top_employers) if top_employers else 'Global EPCs'}",
        f"**Top Global Hubs:** {', '.join(top_locations) if top_locations else 'Worldwide'}",
        "",
        "---",
        "",
        "## Top Verified Piping, E3D & Pipe Stress Vacancies",
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
        reasons = str(j.get("match_reasons") or "High match on Piping Layout & 3D Modeling")
        
        lines.append(f"### {idx}. {title}")
        lines.append(f"- **Company:** {company}")
        lines.append(f"- **Location:** {location}")
        lines.append(f"- **Match Score:** {score} / 100")
        lines.append(f"- **Posted Date:** {posted}")
        lines.append(f"- **Software & Domain:** {software}")
        lines.append(f"- **Match Justification:** {reasons}")
        lines.append(f"- **Direct Application Link:** [{url}]({url})")
        lines.append("")
        
    md_out_file.parent.mkdir(parents=True, exist_ok=True)
    md_out_file.write_text("\n".join(lines), encoding="utf-8")
    
    # 2. Generate World-Class PDF Digest using FPDF
    pdf = ExecutivePDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Executive Analytics Card Banner
    pdf.set_fill_color(245, 247, 250) # Light blue background
    pdf.set_draw_color(200, 210, 225)
    pdf.rect(10, 22, 190, 24, "DF")
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(24, 43, 73)
    pdf.set_xy(14, 25)
    pdf.cell(0, 5, f"EXECUTIVE SUMMARY ANALYTICS | TOTAL HIGH-PRIORITY MATCHES: {len(high_match)}", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(60, 60, 60)
    pdf.set_x(14)
    pdf.cell(0, 5, f"Top Employers: {', '.join(top_employers[:4]) if top_employers else 'Tier-1 EPCs'}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(14)
    pdf.cell(0, 5, f"Top Locations: {', '.join(top_locations[:3]) if top_locations else 'Global Hubs'}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    
    # Section Title
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(24, 43, 73)
    pdf.cell(0, 8, "VERIFIED HIGH-MATCHING PIPING & E3D OPPORTUNITIES", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(24, 43, 73)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)
    
    # Render Job Cards
    for idx, j in enumerate(high_match, 1):
        title = str(j.get("title") or "Unknown Title").encode("latin-1", "replace").decode("latin-1")
        company = str(j.get("company") or "Unknown Employer").encode("latin-1", "replace").decode("latin-1")
        location = str(j.get("location") or "Global").encode("latin-1", "replace").decode("latin-1")
        score = int(str(j.get("match_score") or 0))
        url = str(j.get("apply_url") or "#")
        software = str(j.get("software_text") or j.get("normalized_role") or "Piping Engineering").encode("latin-1", "replace").decode("latin-1")
        posted = str(j.get("published_at") or "Recently Posted")[:10]
        reasons = str(j.get("match_reasons") or "High match on Piping Layout & E3D 3D Modeling").encode("latin-1", "replace").decode("latin-1")
        
        # Check page boundary
        if pdf.get_y() > 240:
            pdf.add_page()
            pdf.ln(6)
            
        start_y = pdf.get_y()
        
        # Card Background box
        pdf.set_fill_color(255, 255, 255)
        pdf.set_draw_color(220, 225, 235)
        pdf.rect(10, start_y, 190, 32, "DF")
        
        # Score Badge
        pdf.set_fill_color(5, 150, 105) # Emerald green
        pdf.rect(172, start_y + 3, 25, 7, "F")
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(172, start_y + 4)
        pdf.cell(25, 5, f"{score}/100", align="C")
        
        # Title & Company
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(24, 43, 73)
        pdf.set_xy(14, start_y + 3)
        pdf.cell(155, 6, f"{idx}. {title}", new_x="LMARGIN", new_y="NEXT")
        
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(70, 70, 70)
        pdf.set_x(14)
        pdf.cell(0, 5, f"Company: {company}  |  Location: {location}  |  Posted: {posted}", new_x="LMARGIN", new_y="NEXT")
        
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(90, 90, 90)
        pdf.set_x(14)
        pdf.cell(0, 5, f"Domain/Software: {software}", new_x="LMARGIN", new_y="NEXT")
        
        pdf.set_x(14)
        pdf.cell(0, 5, f"Match Focus: {reasons[:80]}...", new_x="LMARGIN", new_y="NEXT")
        
        # Apply Link
        pdf.set_x(14)
        if url and url != "#":
            pdf.set_font("Helvetica", "U", 8.5)
            pdf.set_text_color(0, 102, 204)
            pdf.cell(0, 5, "Click Here to Apply Directly on Portal", link=url, new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font("Helvetica", "I", 8.5)
            pdf.set_text_color(130, 130, 130)
            pdf.cell(0, 5, "Direct Link: Contact via Employer Portal", new_x="LMARGIN", new_y="NEXT")
            
        pdf.set_y(start_y + 36)
        
    pdf.output(str(pdf_out_file))
    return md_out_file if out_file.suffix == ".md" else pdf_out_file
