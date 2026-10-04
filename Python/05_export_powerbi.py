"""Export the tables the Power BI report imports to dashboard/data/*.csv.

The report reads small CSV extracts instead of connecting to PostgreSQL, so anyone who clones the repository
can open the dashboard without a database. Every number comes from the analytics views; nothing is recalculated
here beyond relabelling into plain words.

    hospital       one row per program hospital (latest attributes, 2024 status, EHR, finance, data-quality flags)
    hospital_year  one row per program hospital per yearly snapshot, 2019-2024 (the trend)
    states         state names and tile-map positions
"""
import sys
from importlib import import_module
from pathlib import Path

import pandas as pd
import psycopg

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dashboard" / "data"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "Python"))
CONNINFO = import_module("02_load_postgres").CONNINFO

TYPE = {"General acute care": "General hospital", "Critical access": "Small rural"}
STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "PR": "Puerto Rico", "GU": "Guam", "VI": "U.S. Virgin Islands", "MP": "Northern Mariana Islands",
    "AS": "American Samoa",
}
# tile-map grid (column, row); Puerto Rico sits below Florida, the small Pacific/Caribbean territories are not drawn
STATE_GRID = {
    "AK": (0, 0), "ME": (10, 0),
    "WI": (5, 1), "VT": (9, 1), "NH": (10, 1),
    "WA": (0, 2), "ID": (1, 2), "MT": (2, 2), "ND": (3, 2), "MN": (4, 2), "IL": (5, 2), "MI": (6, 2),
    "NY": (8, 2), "MA": (9, 2),
    "OR": (0, 3), "NV": (1, 3), "WY": (2, 3), "SD": (3, 3), "IA": (4, 3), "IN": (5, 3), "OH": (6, 3),
    "PA": (7, 3), "NJ": (8, 3), "CT": (9, 3), "RI": (10, 3),
    "CA": (0, 4), "UT": (1, 4), "CO": (2, 4), "NE": (3, 4), "MO": (4, 4), "KY": (5, 4), "WV": (6, 4),
    "VA": (7, 4), "MD": (8, 4), "DE": (9, 4),
    "AZ": (1, 5), "NM": (2, 5), "KS": (3, 5), "AR": (4, 5), "TN": (5, 5), "NC": (6, 5), "SC": (7, 5), "DC": (8, 5),
    "OK": (3, 6), "LA": (4, 6), "MS": (5, 6), "AL": (6, 6), "GA": (7, 6),
    "HI": (0, 7), "TX": (3, 7), "FL": (8, 7), "PR": (10, 7),
}


ACRONYMS = {"UCSF", "UCLA", "UC", "UNC", "NYU", "OSF", "SSM", "HCA", "LDS", "MUSC", "UPMC", "VCU", "OU", "UT", "UAB",
            "UVA", "UNM", "LSU", "OHSU", "UW", "USC", "CHI", "ECU", "WVU", "UI", "UH", "UF", "UM", "MD", "VA", "II", "III"}
SMALL = {"of", "and", "the", "at", "in", "for", "on"}


def nice_name(name):
    """'UCSF HEALTH ST. MARY'S HOSPITAL' -> 'UCSF Health St. Mary's Hospital' (CMS names are all capitals)."""
    out = []
    for k, w in enumerate(str(name).split()):
        core = w.strip(".,()-'&")
        if core.upper() in ACRONYMS or (core.upper() not in {"ST", "MT", "FT", "DR", "PT", "CTR", "HLTH", "JR", "SR", "MED", "HOSP"} and len(core) <= 4 and core.isalpha() and not set(core.upper()) & set("AEIOUY")):
            out.append(w.upper())
        elif k and w.lower() in SMALL:
            out.append(w.lower())
        else:
            out.append(w[:1].upper() + w[1:].lower())
    return " ".join(out)



def q(conn, sql):
    cur = conn.execute(sql)
    df = pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])
    for c in df.columns:
        if df[c].dtype == object and df[c].map(lambda v: v.__class__.__name__ == "Decimal").any():
            df[c] = df[c].astype(float)
    return df


def save(df, name):
    df.to_csv(OUT / f"{name}.csv", index=False)
    print(f"  {name:<14} {len(df):>7,} rows")


def main():
    with psycopg.connect(CONNINFO) as conn:
        hy = q(conn, "SELECT ccn, snapshot_year, hospital_type AS year_type, not_met::int AS not_met "
                     "FROM analytics.v_hospital_year ORDER BY ccn, snapshot_year")
        hy["year_type"] = hy.year_type.map(TYPE)

        latest = q(conn, """
            SELECT m.*, p.cehrt_id AS raw_cehrt_id,
                   CASE WHEN m.total_margin IS NOT NULL
                        THEN ntile(5) OVER (PARTITION BY m.total_margin IS NOT NULL ORDER BY m.total_margin) END AS margin_fifth
            FROM analytics.mv_hospital_latest m
            JOIN raw.pi_hospital p ON p.facility_id = m.ccn""")
        # every program hospital that appears in any snapshot (some closed before 2024)
        names = q(conn, """SELECT ccn, hospital_name, city, state, hospital_type, ownership
                           FROM core.dim_hospital WHERE ccn IN (SELECT ccn FROM analytics.v_hospital_year)
                                                     OR ccn IN (SELECT ccn FROM analytics.mv_hospital_latest)""")

    h = names.merge(latest.drop(columns=["hospital_name", "city", "state", "hospital_type", "ownership"]),
                    on="ccn", how="left")
    h["in_latest"] = h.not_met.notna().astype(int)
    h["not_met"] = h.not_met.map({True: 1, False: 0}).astype("Int64")
    h["hospital_type"] = h.hospital_type.map(TYPE)
    h["rural_urban"] = h.rural_urban.fillna("Unknown")
    h["ehr_group"] = h.ehr_group.replace({"Unknown": "Other or not identified", "Other": "Other or not identified"})
    h["ehr_status"] = h.reported_ehr_id.map({True: "Reported a certified EHR", False: "No EHR ID reported"})
    h["lost_money"] = h.lost_money_two_years.map({True: "Lost money 2 years in a row", False: "Did not"})
    bands = [(25, "Under 25 beds", 1), (50, "25-49", 2), (100, "50-99", 3), (250, "100-249", 4), (1e9, "250+", 5)]
    h["size_band"] = h.beds.map(lambda b: next((lab for top, lab, _ in bands if b < top), None) if pd.notna(b) else None)
    h["size_order"] = h.beds.map(lambda b: next((o for top, _, o in bands if b < top), None) if pd.notna(b) else None)
    fifth = {1: "Least profitable", 2: "2nd", 3: "Middle", 4: "4th", 5: "Most profitable"}
    h["margin_fifth_label"] = h.margin_fifth.map(fifth)
    h["years_not_met"] = h.years_not_met.astype("Int64")
    h["history"] = h.apply(lambda r: None if r.years_reported != 6 else (
        "Never" if r.years_not_met == 0 else "Every year" if r.years_not_met == 6 else f"{r.years_not_met} of 6 years"),
        axis=1)
    h["history_order"] = h.years_not_met.where(h.years_reported == 6)

    # data-quality flags (same rules as SQL/03_data_quality.sql)
    raw = h.raw_cehrt_id.fillna("")
    h["id_quality"] = None
    h.loc[h.in_latest == 1, "id_quality"] = "Valid ID, found in the federal list"
    h.loc[(h.in_latest == 1) & (raw == "Not Available"), "id_quality"] = "\"Not Available\" typed instead of an ID"
    h.loc[(h.in_latest == 1) & (raw == ""), "id_quality"] = "Left empty"
    bad = (h.in_latest == 1) & ~raw.isin(["", "Not Available"]) & ~raw.str.fullmatch(r"0015[A-Z0-9]{11}")
    h.loc[bad, "id_quality"] = "Wrong format (lowercase or wrong length)"
    h.loc[(h.in_latest == 1) & (h.found_in_chpl == False) & ~bad, "id_quality"] = "Not found in the federal list"
    flag24 = hy[hy.snapshot_year == 2024].set_index("ccn").not_met
    h["status_2024_file"] = h.ccn.map(flag24).astype("Int64")
    h["files_disagree"] = ((h.in_latest == 1) & h.status_2024_file.notna() &
                           (h.status_2024_file != h.not_met)).astype(int)
    h["disagree_type"] = None
    h.loc[(h.files_disagree == 1) & (h.not_met == 0), "disagree_type"] = "Failed in Oct 2024 file, passed in latest"
    h.loc[(h.files_disagree == 1) & (h.not_met == 1), "disagree_type"] = "Passed in Oct 2024 file, failed in latest"
    h["n_files"] = h.ccn.map(hy.groupby("ccn").size()).fillna(0).astype(int)
    h["finance_match"] = (h.rural_urban != "Unknown").astype(int)
    h["state_name"] = h.state.map(STATES).fillna(h.state)
    h["display_name"] = h.hospital_name.map(nice_name)
    h["hospital_label"] = h.display_name + " (" + h.city.fillna("").str.title() + ", " + h.state + ")"
    dup = h.hospital_label.duplicated(keep=False)
    h.loc[dup, "hospital_label"] += " #" + h.loc[dup, "ccn"]

    keep = ["ccn", "hospital_label", "display_name", "city", "state", "state_name", "hospital_type", "ownership", "rural_urban",
            "in_latest", "not_met", "ehr_status", "ehr_group", "main_developer", "beds", "size_band", "size_order",
            "total_margin", "margin_fifth", "margin_fifth_label", "lost_money", "years_reported", "years_not_met",
            "history", "history_order", "hospitals_sharing_ehr_id", "id_quality", "files_disagree", "disagree_type", "n_files", "finance_match"]
    save(h[keep].sort_values("ccn"), "hospital")
    save(hy, "hospital_year")
    st = pd.DataFrame({"state": sorted(set(h.state))})
    st["state_name"] = st.state.map(STATES).fillna(st.state)
    st["tile_x"] = st.state.map(lambda a: STATE_GRID.get(a, (None, None))[0]).astype("Int64")
    st["tile_y"] = st.state.map(lambda a: STATE_GRID.get(a, (None, None))[1]).astype("Int64")
    st["on_map"] = st.tile_x.notna().astype(int)
    save(st, "states")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
