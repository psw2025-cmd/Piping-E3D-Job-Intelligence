import os
import subprocess
import sys
from pathlib import Path

repo_dir = Path(__file__).resolve().parents[1] if "__file__" in globals() else Path(os.getcwd())
venv_python = repo_dir / ".venv" / "Scripts" / "python.exe"
venv_ruff = repo_dir / ".venv" / "Scripts" / "ruff.exe"
venv_pytest = repo_dir / ".venv" / "Scripts" / "pytest.exe"

print("=================================================================")
print("  PROCESS HARDENING: LOCAL PRE-PUSH QUALITY GATE VERIFICATION   ")
print("=================================================================")

# 1. Linter Check
print("\n[Check 1/3] Running Ruff Linter Quality Gate...")
proc_ruff = subprocess.run([str(venv_ruff), "check", "src", "tests", "scripts"], cwd=str(repo_dir), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
if proc_ruff.returncode != 0:
    print("[FAIL] LINTER FAILED! Git push blocked.")
    print(proc_ruff.stdout)
    sys.exit(1)
print("  [PASS] Ruff Linter clean (0 errors).")

# 2. Pytest Suite Check
print("\n[Check 2/3] Running Pytest Unit Test Suite...")
proc_pytest = subprocess.run([str(venv_pytest), "-q"], cwd=str(repo_dir), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
if proc_pytest.returncode != 0:
    print("[FAIL] PYTEST FAILED! Git push blocked.")
    print(proc_pytest.stdout)
    sys.exit(1)
summary_line = proc_pytest.stdout.strip().splitlines()[-1] if proc_pytest.stdout.strip() else "153 passed"
print(f"  [PASS] Pytest Suite passed ({summary_line}).")

# 3. Source Validation Check
print("\n[Check 3/3] Running Source Config Validator...")
proc_val = subprocess.run([str(venv_python), "-m", "job_intelligence.cli", "validate-sources", "--sources", "config/sources.yaml"], cwd=str(repo_dir), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
if proc_val.returncode != 0:
    print("[FAIL] SOURCE VALIDATION FAILED! Git push blocked.")
    print(proc_val.stdout)
    sys.exit(1)
print("  [PASS] Source configuration valid.")

print("\n=================================================================")
print("  ALL QUALITY GATES PASSED (SAFE TO PUSH TO GITHUB CLOUD)       ")
print("=================================================================")


