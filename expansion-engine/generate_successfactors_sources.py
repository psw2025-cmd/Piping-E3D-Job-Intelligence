import yaml
from pathlib import Path

def main():
    master_path = Path("config/employers_master_verified.yaml")
    output_path = Path("expansion-engine/successfactors.generated.yaml")
    if not master_path.exists():
        print("Error: employers_master_verified.yaml not found!")
        return
    data = yaml.safe_load(master_path.read_text(encoding="utf-8"))
    orgs = data.get("organizations", [])
    sf_sources = []
    seen_companies = set()
    for org in orgs:
        ats = str(org.get("ats_platform_verified") or org.get("ats") or "")
        if "SuccessFactors" not in ats:
            continue
        name = org.get("canonical_company_name") or org.get("name")
        if not name:
            continue
        norm_name = name.strip().lower()
        if norm_name in seen_companies:
            continue
        seen_companies.add(norm_name)
        career_url = org.get("careers_url") or ""
        source_id = f"successfactors_{name.lower().replace(" ", "_").replace(",", "").replace(".", "").replace("(", "").replace(")", "")}"
        spec = {
            "id": source_id,
            "name": f"{name} SuccessFactors Openings",
            "type": "sitemap",
            "company": name,
            "enabled": False,
            "profile_filter": True,
            "url": career_url,
            "anchor_text_patterns": ["piping", "e3d", "pdms", "sp3d"]
        }
        sf_sources.append(spec)
    with open(output_path, "w", encoding="utf-8") as out:
        yaml.safe_dump({"sources": sf_sources}, out, sort_keys=False, allow_unicode=True)
    print(f"SUCCESS: Generated {len(sf_sources)} SuccessFactors sources.")

if __name__ == "__main__":
    main()
