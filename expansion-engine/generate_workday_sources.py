import yaml
from pathlib import Path

def main():
    master_path = Path("config/employers_master_verified.yaml")
    output_path = Path("expansion-engine/workday.generated.yaml")
    if not master_path.exists():
        print("Error: employers_master_verified.yaml not found!")
        return
    data = yaml.safe_load(master_path.read_text(encoding="utf-8"))
    orgs = data.get("organizations", [])
    workday_sources = []
    seen_companies = set()
    for org in orgs:
        ats = str(org.get("ats_platform_verified") or org.get("ats") or "")
        if "Workday" not in ats:
            continue
        name = org.get("canonical_company_name") or org.get("name")
        if not name:
            continue
        norm_name = name.strip().lower()
        if norm_name in seen_companies:
            continue
        seen_companies.add(norm_name)
        career_url = org.get("careers_url") or ""
        source_id = f"workday_{name.lower().replace(" ", "_").replace(",", "").replace(".", "").replace("(", "").replace(")", "")}"
        spec = {
            "id": source_id,
            "name": f"{name} Workday Job Openings",
            "type": "workday",
            "company": name,
            "enabled": False,
            "profile_filter": True,
            "careers_url": career_url,
            "include_terms": [
                "piping", "pipe layout", "plant layout", "plant design",
                "e3d", "aveva e3d", "pdms", "sp3d", "smart 3d",
                "smartplant 3d", "pipe support", "piping stress"
            ]
        }
        workday_sources.append(spec)
    with open(output_path, "w", encoding="utf-8") as out:
        yaml.safe_dump({"sources": workday_sources}, out, sort_keys=False, allow_unicode=True)
    print(f"SUCCESS: Generated {len(workday_sources)} Workday sources.")

if __name__ == "__main__":
    main()
