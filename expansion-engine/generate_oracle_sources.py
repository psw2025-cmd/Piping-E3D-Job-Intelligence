from pathlib import Path

import yaml


def main():
    master_path = Path("config/employers_master_verified.yaml")
    output_path = Path("expansion-engine/oracle.generated.yaml")
    if not master_path.exists():
        print("Error: employers_master_verified.yaml not found!")
        return
    data = yaml.safe_load(master_path.read_text(encoding="utf-8"))
    orgs = data.get("organizations", [])
    oracle_sources = []
    seen_companies = set()
    for org in orgs:
        ats = str(org.get("ats_platform_verified") or org.get("ats") or "")
        if "Oracle" not in ats:
            continue
        name = org.get("canonical_company_name") or org.get("name")
        if not name:
            continue
        norm_name = name.strip().lower()
        if norm_name in seen_companies:
            continue
        seen_companies.add(norm_name)
        career_url = org.get("careers_url") or ""
        safe_name = name.lower().replace(' ', '_').replace(',', '').replace('.', '').replace('(', '').replace(')', '')
        source_id = f"oracle_{safe_name}"
        spec = {
            "id": source_id,
            "name": f"{name} Oracle HCM Careers",
            "type": "oracle_hcm",
            "company": name,
            "enabled": False,
            "profile_filter": True,
            "base_url": career_url,
            "include_terms": [
                "piping", "pipe layout", "plant layout", "plant design",
                "e3d", "aveva e3d", "pdms", "sp3d", "smart 3d",
                "smartplant 3d", "pipe support", "piping stress"
            ]
        }
        oracle_sources.append(spec)
    with open(output_path, "w", encoding="utf-8") as out:
        yaml.safe_dump({"sources": oracle_sources}, out, sort_keys=False, allow_unicode=True)
    print(f"SUCCESS: Generated {len(oracle_sources)} Oracle sources.")

if __name__ == "__main__":
    main()
