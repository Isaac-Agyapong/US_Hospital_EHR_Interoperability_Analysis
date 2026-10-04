"""Rebuild the whole project in order.

    python run_all.py              full rebuild
    python run_all.py --skip-download

Steps: download sources -> load PostgreSQL (raw, core, analytics) -> data quality and business queries
-> analysis notebook -> Power BI extracts -> Power BI project.
The download step looks up EHR IDs in the ONC product list (CHPL); it needs a free CHPL API key in a .env file
(CHPL_API_KEY=...) unless Data/raw/chpl_cehrt.json is already there. Hospital finances come from the companion
project's database (US_Hospital_Financial_Performance_Analysis), which must be loaded first.
"""
import subprocess
import sys
import time
from pathlib import Path

PY = Path(__file__).resolve().parent / "Python"
STEPS = [
    ("01_download_data.py", "download CMS files and look up EHR IDs"),
    ("02_load_postgres.py", "load PostgreSQL star schema"),
    ("03_run_sql_queries.py", "data quality + business questions -> SQL/query_results.md"),
    ("04_build_notebook.py", "build and execute Python/04_analysis.ipynb"),
    ("05_export_powerbi.py", "export tables for the Power BI report"),
    ("06_build_powerbi_project.py", "generate the Power BI project (PBIP)"),
]


def main():
    start = time.time()
    for script, what in STEPS:
        if script.startswith("01_") and "--skip-download" in sys.argv:
            continue
        print(f"\n== {script}: {what}")
        t = time.time()
        subprocess.run([sys.executable, script], cwd=PY, check=True)
        print(f"   done in {time.time() - t:.0f}s")
    print(f"\nall steps finished in {(time.time() - start) / 60:.1f} min")


if __name__ == "__main__":
    main()
