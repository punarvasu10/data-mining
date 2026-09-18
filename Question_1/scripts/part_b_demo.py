from pathlib import Path
import subprocess
import sys
import os

# Project location
PROJECT = Path(__file__).resolve().parents[1]

# Actual sales directory in the exam data
SALES_DIR = PROJECT.parent / "sales"

env = os.environ.copy()
env["SALES_DIR"] = str(SALES_DIR)

print("========== PART (B) IDEMPOTENCY ==========")
print()
print("Sales directory:", SALES_DIR)
print()

for run in range(1, 4):
    print(f"----- RUN {run} -----")

    result = subprocess.run(
        [sys.executable, "scripts/ingest_sales.py"],
        cwd=PROJECT,
        env=env,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise SystemExit("Ingestion failed")

    lines = result.stdout.splitlines()

    # Overall ingestion summary
    if lines:
        print(lines[0])

    # Find the S03 October 2024 manifest row
    target = [
        line for line in lines
        if line.startswith("S03,202410")
    ]

    if target:
        print("S03 October manifest:")
        print(target[0])

    print()

print("RESULT:")
print("The ingestion process was executed 3 times.")
print("The groups, raw row count, duplicate count and S03 October")
print("manifest/checksum should remain identical across all runs.")