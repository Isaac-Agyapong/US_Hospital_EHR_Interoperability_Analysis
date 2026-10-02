"""
Load Data/raw/ into PostgreSQL (database hospital_interop) and build the star schema.

    1. SQL/01a_schema_raw.sql       raw schema                        (skipped with --skip-raw)
    2. raw.*                        CMS snapshots, CHPL products, hospital finance (skipped with --skip-raw)
    3. SQL/01b_schema_core.sql      core + analytics schemas
    4. SQL/02_transform.sql         raw -> core
    5. SQL/04_analytics_views.sql   one view per question (notebook, Power BI and the ML project read these)

    python Python/02_load_postgres.py              full rebuild
    python Python/02_load_postgres.py --skip-raw   rebuild core/analytics from the loaded raw layer

Connection settings come from the standard PG* environment variables (default postgres@localhost:5432);
the password is read by libpq from pgpass.conf (never stored here). Hospital finance comes from the companion
project's database (hospital_finance, US_Hospital_Financial_Performance_Analysis).
"""
import csv
import io
import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import psycopg

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "Data" / "raw"
SQL = ROOT / "SQL"
DB = os.getenv("PGDATABASE", "hospital_interop")
FINANCE_DB = os.getenv("FINANCE_DB", "hospital_finance")
FLAG_YEARS = ["2019-10-31", "2020-05-01", "2021-10-27", "2022-10-06", "2023-11-06", "2024-10-30"]
LATEST = "2026-08-13"

# source column (any of the spellings CMS used over the years) -> raw column
GENERAL_COLS = {
    "facility_id": ["Facility ID", "Provider ID"],
    "facility_name": ["Facility Name", "Hospital Name"],
    "city": ["City/Town", "City"],
    "state": ["State"],
    "zip_code": ["ZIP Code"],
    "county": ["County/Parish", "County Name"],
    "hospital_type": ["Hospital Type"],
    "hospital_ownership": ["Hospital Ownership"],
    "emergency_services": ["Emergency Services"],
    "interop_flag": ["Meets criteria for promoting interoperability of EHRs", "Meets criteria for meaningful use of EHRs"],
    "overall_rating": ["Hospital overall rating"],
}


def conninfo(db=DB):
    return " ".join([f"host={os.getenv('PGHOST', 'localhost')}", f"port={os.getenv('PGPORT', '5432')}",
                     f"user={os.getenv('PGUSER', 'postgres')}", f"dbname={db}"])


CONNINFO = conninfo()


def copy_frame(cur, table, df):
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False)
    buf.seek(0)
    with cur.copy(f"COPY {table} ({', '.join(df.columns)}) FROM STDIN WITH (FORMAT csv)") as cp:
        while data := buf.read(1 << 20):
            cp.write(data)


def run_sql_file(conn, name):
    t = time.time()
    conn.execute((SQL / name).read_text(encoding="utf-8-sig"))
    conn.commit()
    print(f"  ran {name} ({time.time() - t:.0f}s)")


def ensure_database():
    with psycopg.connect(conninfo("postgres"), autocommit=True) as admin:
        if admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB,)).fetchone():
            return
        print("creating database", DB)
        for stmt in (SQL / "00_create_database.sql").read_text(encoding="utf-8-sig").split(";"):
            body = "\n".join(l for l in stmt.splitlines() if not l.strip().startswith("--")).strip()
            if body:
                admin.execute(body)


def snapshot_csv(date, pattern):
    z = zipfile.ZipFile(RAW / "archives" / f"hospitals_{date}.zip")
    name = next(n for n in z.namelist() if re.search(pattern, n, re.I))
    return pd.read_csv(z.open(name), dtype=str, keep_default_na=False, encoding="latin-1")


def pick(df, spellings):
    for s in spellings:
        if s in df.columns:
            return df[s].str.strip()
    return pd.Series([""] * len(df))


def load_general(cur):
    for date in FLAG_YEARS:
        df = snapshot_csv(date, r"general.?information")
        out = pd.DataFrame({k: pick(df, v) for k, v in GENERAL_COLS.items()})
        out.insert(0, "snapshot_date", date)
        copy_frame(cur, "raw.general_info", out)
        print(f"  raw.general_info {date}: {len(out):>5,} hospitals")


def load_pi(cur):
    df = snapshot_csv(LATEST, r"promoting_?interoperab")
    out = pd.DataFrame({"snapshot_date": LATEST, "facility_id": df["Facility ID"], "facility_name": df["Facility Name"],
                        "state": df["State"], "cehrt_id": df["CEHRT ID"],
                        "meets_criteria": df["Meets criteria for promoting interoperability of EHRs"],
                        "start_date": df["Start Date"], "end_date": df["End Date"]}).apply(lambda s: s.str.strip())
    copy_frame(cur, "raw.pi_hospital", out)
    print(f"  raw.pi_hospital {LATEST}: {len(out):>5,} hospitals")


def load_chpl(cur):
    cache = json.loads((RAW / "chpl_cehrt.json").read_text(encoding="utf-8"))
    rows = []
    for cid, d in cache.items():
        prods = [] if d.get("not_found") else (d.get("products") or [])
        if not prods:
            rows.append({"cehrt_id": cid, "found": "false"})
        for p in prods:
            rows.append({"cehrt_id": cid, "found": "true", "chpl_product_number": p.get("chplProductNumber"),
                         "vendor": p.get("vendor"), "product": p.get("name"), "version": p.get("version"),
                         "acb": p.get("acb"), "cures_update": p.get("curesUpdate")})
    df = pd.DataFrame(rows, columns=["cehrt_id", "found", "chpl_product_number", "vendor", "product", "version", "acb",
                                     "cures_update"])
    copy_frame(cur, "raw.chpl_product", df)
    print(f"  raw.chpl_product: {df.cehrt_id.nunique():,} CEHRT IDs, {len(df):,} product rows")


def load_finance(cur):
    """Latest year per hospital from the companion project, plus 'lost money in both of its two latest reports'."""
    with psycopg.connect(conninfo(FINANCE_DB)) as fin:
        q = fin.execute("""
            SELECT ccn, fiscal_year, hospital_type, ownership, rural_urban, medicaid_status, beds, fte_employees,
                   total_revenue, total_margin, operating_margin, medicaid_day_share, medicare_day_share,
                   days_cash_on_hand, net_income
            FROM analytics.mv_hospital_panel ORDER BY ccn, fiscal_year""")
        df = pd.DataFrame(q.fetchall(), columns=[c.name for c in q.description])
    df["loss"] = df.net_income < 0
    last2 = df.groupby("ccn").tail(2)
    two = last2.groupby("ccn").agg(n=("loss", "size"), losses=("loss", "sum"))
    latest = df.groupby("ccn").tail(1).set_index("ccn")
    latest["lost_money_two_years"] = (two.n == 2) & (two.losses == 2)
    out = latest.reset_index().drop(columns=["net_income", "loss"])
    copy_frame(cur, "raw.finance", out.astype(str).replace({"None": "", "nan": ""}))
    print(f"  raw.finance: {len(out):,} hospitals (from {FINANCE_DB})")


def main():
    start = time.time()
    ensure_database()
    with psycopg.connect(CONNINFO) as conn:
        if "--skip-raw" not in sys.argv:
            print("raw layer")
            run_sql_file(conn, "01a_schema_raw.sql")
            with conn.cursor() as cur:
                load_general(cur)
                load_pi(cur)
                load_chpl(cur)
                load_finance(cur)
            conn.commit()
        print("core layer")
        run_sql_file(conn, "01b_schema_core.sql")
        run_sql_file(conn, "02_transform.sql")
        if (SQL / "04_analytics_views.sql").exists():
            run_sql_file(conn, "04_analytics_views.sql")
        for t in ["core.dim_hospital", "core.fact_interop_year", "core.dim_ehr", "core.fact_hospital_ehr", "core.fact_finance"]:
            print(f"  {t:<26} {conn.execute(f'SELECT count(*) FROM {t}').fetchone()[0]:>7,} rows")
    print(f"done in {(time.time() - start) / 60:.1f} min")


if __name__ == "__main__":
    main()
