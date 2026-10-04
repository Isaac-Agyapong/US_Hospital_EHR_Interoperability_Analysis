"""
Generate the Power BI Project (PBIP). The model imports the CSV extracts in dashboard/data/ (written by
05_export_powerbi.py from the PostgreSQL analytics views), so the report opens on any machine without a database.
The folder is a parameter (DataFolder).

    dashboard/EHR_Interoperability.pbip                 open this in Power BI Desktop
    dashboard/EHR_Interoperability.SemanticModel/       model (TMDL), columns read from the CSV headers
    dashboard/EHR_Interoperability.Report/              6 pages + a state tooltip page (PBIR JSON)

Design (different from every earlier portfolio dashboard): a light "blueprint" page with a fine grid, Corbel type,
the page title sitting on the page under a short blue line (as in the notebook charts), white cards with a thin
coloured stripe along the top, and a white navigation rail on the RIGHT with a navy top block, the page links and
the filters. The artwork is drawn by make_background.py from the same layout; visuals sit on top of it.

Colour meanings (same in the notebook, README and every page):
    blue (cobalt)  met the standards / the leading EHR companies
    red (vermilion) fell short of the standards
    purple          reported no certified EHR at all
    amber           data-quality problems
    teal / slate    small rural hospitals / general hospitals
    grey            everything else
"""
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "dashboard"
DATA = DASH / "data"
ASSETS = DASH / "assets"
NAME = "EHR_Interoperability"
SM = DASH / f"{NAME}.SemanticModel"
RPT = DASH / f"{NAME}.Report"

TABLES = ["hospital", "hospital_year", "states"]
HIDDEN = {"ccn", "in_latest", "not_met", "size_order", "margin_fifth", "history_order", "tile_x", "tile_y", "on_map",
          "files_disagree", "n_files", "finance_match", "years_reported", "years_not_met", "hospitals_sharing_ehr_id",
          "total_margin", "beds"}
SORT_BY = {("hospital", "size_band"): "size_order", ("hospital", "margin_fifth_label"): "margin_fifth",
           ("hospital", "history"): "history_order"}
TEXT_COLS = {"ccn"}
INT_COLS = {"size_order", "margin_fifth", "history_order", "years_reported", "years_not_met", "not_met", "beds",
            "hospitals_sharing_ehr_id", "tile_x", "tile_y", "snapshot_year"}

SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"
S_PBIP = f"{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json"
S_PBISM = f"{SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json"
S_PBIR = f"{SCHEMA}/item/report/definitionProperties/2.0.0/schema.json"
S_VERSION = f"{SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json"
S_REPORT = f"{SCHEMA}/item/report/definition/report/1.2.0/schema.json"
S_PAGES = f"{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json"
S_PAGE = f"{SCHEMA}/item/report/definition/page/1.3.0/schema.json"
S_VISUAL = f"{SCHEMA}/item/report/definition/visualContainer/1.4.0/schema.json"
BASE_THEME = "CY24SU10"
CUSTOM_THEME = "BlueprintTheme.json"

# palette: light grey page, white cards, navy title banner and rail; navy = main colour, red = fell short,
# purple = no certified EHR, teal = small rural, grey = everything else, amber = data problems
COBALT, COBALT_L, NAVY, SKY = "#1F4E9E", "#9DB4E0", "#0B1F4D", "#2563EB"
RED, RED_L, RED_D = "#D64545", "#F0A8A8", "#9F1D1D"
PURPLE, AMBER, TEAL, SLATE, GREY = "#7C3AED", "#D97706", "#0D9488", "#94A3B8", "#B8C1CF"
GREY_D = "#64748B"
PANEL, PANEL_2, DARK = "#FFFFFF", "#F4F6FA", "#1E293B"
CARD_D, REST = "#FFFFFF", "#B8C1CF"
DOT_BLUE, DOT_RED, DOT_PURPLE = "#1F4E9E", "#D64545", "#7C3AED"
RAIL_TEXT, RAIL_MUTED = "#E8EEFB", "#9FB3E0"
INK, INK_2, MUTED, LINE, CARD = "#1E293B", "#475569", "#64748B", "#DDE3EC", "#FFFFFF"
PAPER, PAPER_TOP, GRIDC, MINT = "#E9EDF3", "#F1F4F8", "#E9EDF3", "#5EEAD4"
GLASS_T = 0
FONT = "Segoe UI"
PCT, PCT1, INT = "0%", "0.0%", "#,0"
GENERAL, RURAL = "General hospital", "Small rural (critical access)"
NO_EHR = "No EHR ID reported"


def tag(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "ehr-interop-blueprint/" + "/".join(parts)))


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path, obj):
    write(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def qn(name):
    return name if name.replace("_", "").isalnum() else "'" + name.replace("'", "''") + "'"


def indent(text, tabs):
    return "\n".join("\t" * tabs + line if line else "" for line in text.splitlines())


# =====================================================================
# Facts used in static text (computed from the same extracts, never typed by hand)
# =====================================================================
def facts():
    h = pd.read_csv(DATA / "hospital.csv", dtype={"ccn": str})
    l = h[h.in_latest == 1]
    dev = l[l.main_developer.notna()].main_developer.value_counts()
    six = l[l.years_reported == 6]
    return {
        "n": len(l), "short": int(l.not_met.sum()), "top3": list(dev.index[:3]),
        "not_available": int((l.id_quality == '"Not Available" typed instead of an ID').sum()),
        "not_in_list": int((l.id_quality == "Not found in the federal list").sum()),
        "bad_format": int((l.id_quality == "Wrong format (lowercase or wrong length)").sum()),
        "id_problem_share": (l.id_quality != "Valid ID, found in the federal list").mean(),
        "disagree": int(l.files_disagree.sum()),
        "finance_match": l.finance_match.mean(),
        "no_finance_short": l[l.finance_match == 0].not_met.mean(),
        "finance_short": l[l.finance_match == 1].not_met.mean(),
        "all_six": int((h.n_files == 6).sum()), "program_ever": int((h.n_files > 0).sum()),
        "six_years": len(six), "rail_caption": f"{len(l):,} HOSPITALS  ·  2019-2024",
        "default_hospital": l[l.hospital_label.str.startswith("Cleveland Clinic (Cleveland")].hospital_label.iloc[0],
    }


F = facts()
TOP3 = F["top3"]
TOP3_DAX = "{ " + ", ".join(f'"{d}"' for d in TOP3) + " }"

# =====================================================================
# Measures: (home table, name, DAX, format, folder)
# Every measure respects the filters in the rail: a fixed group inside CALCULATE is wrapped in KEEPFILTERS, so it
# narrows the current selection instead of replacing it. Titles name the top and bottom group of what is shown.
# =====================================================================
LATEST = "hospital[in_latest] = 1"
ONE = "HASONEVALUE ( hospital[hospital_label] )"
SHORT_LBL = "Lost money 2 years in a row"


def kf(*conds):
    return ", ".join(f"KEEPFILTERS ( {c} )" for c in conds)


def share_for(*conds):
    return f"CALCULATE ( [Short Share], {kf(*conds)} )"


def eq(col, value):
    return f'{col} = "{value}"'


def top_bottom(col, min_n, text, fallback, extra=""):
    """Title naming the group with the highest and the lowest share falling short among the groups shown.
    text(hi, hi_pct, lo, lo_pct) returns the DAX string expression."""
    return (f'VAR _t = FILTER ( ADDCOLUMNS ( VALUES ( {col} ), "@v", [Short Share], "@n", [Hospitals] ),\n'
            f'    [@n] >= {min_n} && NOT ISBLANK ( [@v] ) && NOT ISBLANK ( {col} ){extra} )\n'
            'VAR _hi = TOPN ( 1, _t, [@v], DESC )\nVAR _lo = TOPN ( 1, _t, [@v], ASC )\n'
            f'VAR _h = MAXX ( _hi, {col} )\nVAR _l = MAXX ( _lo, {col} )\n'
            'VAR _hp = FORMAT ( MAXX ( _hi, [@v] ), "0%" )\nVAR _lp = FORMAT ( MAXX ( _lo, [@v] ), "0%" )\n'
            f'RETURN IF ( COUNTROWS ( _t ) < 2, "{fallback}", {text} )')


MEASURES = [
    # ---- core (latest reporting year, 2024)
    ("hospital", "Hospitals", f"CALCULATE ( COUNTROWS ( hospital ), {kf(LATEST)} )", INT, "Core"),
    ("hospital", "Short", f"CALCULATE ( SUM ( hospital[not_met] ), {kf(LATEST)} )", INT, "Core"),
    ("hospital", "Short Share", "DIVIDE ( [Short], [Hospitals] )", PCT, "Core"),
    ("hospital_year", "Year Share", "DIVIDE ( SUM ( hospital_year[not_met] ), COUNTROWS ( hospital_year ) )", PCT, "Core"),
    ("hospital", "No EHR Short", f"CALCULATE ( [Short], {kf(eq('hospital[ehr_status]', NO_EHR))} )", INT, "Core"),
    ("hospital", "No EHR Share", "DIVIDE ( [No EHR Short], [Short] )", PCT, "Core"),

    # ---- overview: hero banner and its dot grid (each dot = 1 in 100 hospitals shown)
    ("hospital", "Hero Line",
     'VAR _s = ROUND ( [Short Share] * 100, 0 )\nVAR _n = ROUND ( [No EHR Share] * 10, 0 )\n'
     'RETURN IF ( ISBLANK ( [Hospitals] ), "No hospitals match these filters.",\n'
     '    _s & " in 100 hospitals fell short in 2024" & IF ( [Short] > 0, "; " & _n & " in 10 of those had no certified EHR.", "." ) )',
     None, "Hero"),
    ("hospital", "Hero Hospitals", 'FORMAT ( [Hospitals], "#,0" )', None, "Hero"),
    ("hospital", "Hero Short", 'FORMAT ( [Short] + 0, "#,0" )', None, "Hero"),
    ("hospital", "Hero No EHR", 'FORMAT ( [No EHR Short] + 0, "#,0" )', None, "Hero"),
    ("hospital", "Dot", '"●"', None, "Hero"),
    ("hospital", "Dot Colour",
     "VAR _i = SELECTEDVALUE ( Dots[row] ) * 10 + SELECTEDVALUE ( Dots[col] ) + 1\n"
     "VAR _s = ROUND ( [Short Share] * 100, 0 )\n"
     "VAR _n = ROUND ( DIVIDE ( [No EHR Short], [Hospitals] ) * 100, 0 )\n"
     f'RETURN SWITCH ( TRUE (), _i > 100 - _n, "{DOT_PURPLE}", _i > 100 - _s, "{DOT_RED}", "{DOT_BLUE}" )', None, "Hero"),

    # ---- overview charts
    ("hospital_year", "Trend Title",
     f"VAR _a = CALCULATE ( [Year Share], {kf('hospital_year[snapshot_year] = 2019')} )\n"
     f"VAR _b = CALCULATE ( [Year Share], {kf('hospital_year[snapshot_year] = 2024')} )\n"
     'RETURN IF ( ISBLANK ( _a ) || ISBLANK ( _b ), "Share falling short in each yearly Medicare file",\n'
     '    IF ( _b < _a, "Fewer hospitals fall short than in 2019: ", "More hospitals fall short than in 2019: " )\n'
     '    & FORMAT ( _a, "0%" ) & " then, " & FORMAT ( _b, "0%" ) & " in 2024" )', None, "Titles"),
    ("hospital", "Size Short", "IF ( NOT ISBLANK ( SELECTEDVALUE ( hospital[size_band] ) ) && SELECTEDVALUE ( hospital[size_band] ) <> \"\" && [Hospitals] >= 20, [Short Share] )",
     PCT, "Charts"),
    ("hospital", "Size Colour",
     "VAR _t = FILTER ( ADDCOLUMNS ( ALLSELECTED ( hospital[size_band] ), \"@v\", [Size Short] ), NOT ISBLANK ( [@v] ) )\n"
     f'RETURN IF ( [Size Short] = MAXX ( _t, [@v] ), "{RED}", "{REST}" )', None, "Colours"),
    ("hospital", "Size Title",
     top_bottom("hospital[size_band]", 20,
                'IF ( LEFT ( _h, 5 ) = "Under", _h, _h & " beds" ) & ": " & _hp & " fall short; "'
                ' & IF ( LEFT ( _l, 5 ) = "Under", LOWER ( _l ), _l & " beds" ) & ": " & _lp',
                "Share falling short by number of beds"), None, "Titles"),
    ("hospital", "Owner Short", "IF ( [Hospitals] >= 50, [Short Share] )", PCT, "Charts"),
    ("hospital", "Owner Colour",
     "VAR _t = FILTER ( ADDCOLUMNS ( ALLSELECTED ( hospital[ownership] ), \"@v\", [Owner Short] ), NOT ISBLANK ( [@v] ) )\n"
     f'RETURN IF ( [Owner Short] = MAXX ( _t, [@v] ), "{RED}", "{REST}" )', None, "Colours"),
    ("hospital", "Owner Title",
     top_bottom("hospital[ownership]", 50,
                '_h & " fall short most (" & _hp & "), " & LOWER ( _l ) & " least (" & _lp & ")"',
                "Share falling short by owner"), None, "Titles"),
    ("hospital", "Type Hospitals", "[Hospitals]", INT, "Charts"),
    ("hospital", "Type Short", "[Short]", INT, "Charts"),
    ("hospital", "Pair Title",
     f"VAR _a = DIVIDE ( CALCULATE ( [Hospitals], {kf(eq('hospital[hospital_type]', RURAL))} ), [Hospitals] )\n"
     f"VAR _b = DIVIDE ( CALCULATE ( [Short], {kf(eq('hospital[hospital_type]', RURAL))} ), [Short] )\n"
     'RETURN IF ( ISBLANK ( _a ) || ISBLANK ( _b ) || _a = 1, "Who the hospitals that fell short are",\n'
     '    "Small rural: " & FORMAT ( _a, "0%" ) & " of all, " & FORMAT ( _b, "0%" ) & " of shortfalls" )',
     None, "Titles"),

    # ---- EHR companies (market share ignores the EHR company filter: it describes the whole market)
    ("hospital", "Market Share",
     "VAR _d = SELECTEDVALUE ( hospital[main_developer] )\n"
     "VAR _all = CALCULATE ( [Hospitals], REMOVEFILTERS ( hospital[main_developer], hospital[ehr_group] ), NOT ISBLANK ( hospital[main_developer] ) )\n"
     "RETURN IF ( NOT ISBLANK ( _d ), DIVIDE ( CALCULATE ( [Hospitals], REMOVEFILTERS ( hospital[ehr_group] ) ), _all ) )",
     PCT, "EHR"),
    ("hospital", "Top3 Share",
     f"DIVIDE ( CALCULATE ( [Hospitals], REMOVEFILTERS ( hospital[ehr_group] ), hospital[main_developer] IN {TOP3_DAX} ),\n"
     "    CALCULATE ( [Hospitals], REMOVEFILTERS ( hospital[ehr_group] ), NOT ISBLANK ( hospital[main_developer] ) ) )", PCT, "KPI"),
    ("hospital", "Top3 Context",
     f'"{TOP3[0]} alone: " & FORMAT ( DIVIDE ( CALCULATE ( [Hospitals], REMOVEFILTERS ( hospital[ehr_group] ), hospital[main_developer] = "{TOP3[0]}" ),\n'
     '    CALCULATE ( [Hospitals], REMOVEFILTERS ( hospital[ehr_group] ), NOT ISBLANK ( hospital[main_developer] ) ) ), "0%" ) & " of hospitals"',
     None, "KPI"),
    ("hospital", "Market Colour", f'IF ( SELECTEDVALUE ( hospital[main_developer] ) IN {TOP3_DAX}, "{SKY}", "{GREY}" )',
     None, "Colours"),
    ("hospital", "Market Title",
     f'"{TOP3[0]}, {TOP3[1].split(" (")[0]} and {TOP3[2]} run " & FORMAT ( [Top3 Share], "0%" ) & " of the hospitals shown"',
     None, "Titles"),
    ("hospital", "Epic Short", share_for(eq("hospital[ehr_group]", "Epic")), PCT1, "KPI"),
    ("hospital", "Epic Context",
     f'VAR _n = CALCULATE ( [Hospitals], {kf(eq("hospital[ehr_group]", "Epic"))} )\n'
     f'RETURN IF ( ISBLANK ( _n ), "no Epic hospitals in this selection", FORMAT ( CALCULATE ( [Short] + 0, {kf(eq("hospital[ehr_group]", "Epic"))} ), "#,0" ) & " of " & FORMAT ( _n, "#,0" ) & " hospitals" )',
     None, "KPI"),
    ("hospital", "TruBridge Short", share_for(eq("hospital[ehr_group]", "TruBridge (CPSI)")), PCT1, "KPI"),
    ("hospital", "TruBridge Context",
     f'VAR _n = CALCULATE ( [Hospitals], {kf(eq("hospital[ehr_group]", "TruBridge (CPSI)"))} )\n'
     f'RETURN IF ( ISBLANK ( _n ), "no TruBridge hospitals in this selection", FORMAT ( CALCULATE ( [Short] + 0, {kf(eq("hospital[ehr_group]", "TruBridge (CPSI)"))} ), "#,0" ) & " of " & FORMAT ( _n, "#,0" ) & " hospitals" )',
     None, "KPI"),
    ("hospital", "No EHR Hospitals", f"CALCULATE ( [Hospitals], {kf(eq('hospital[ehr_status]', NO_EHR))} )", INT, "KPI"),
    ("hospital", "No EHR All Context", '"all of them fell short"', None, "KPI"),
    ("hospital", "EHR Short", "IF ( [Hospitals] >= 40 && NOT ISBLANK ( SELECTEDVALUE ( hospital[ehr_group] ) ) && SELECTEDVALUE ( hospital[ehr_group] ) <> \"Other or not identified\", [Short Share] )",
     PCT, "EHR"),
    ("hospital", "EHR Colour", f'IF ( SELECTEDVALUE ( hospital[ehr_group] ) = "{NO_EHR}", "{PURPLE}", "{RED}" )', None, "Colours"),
    ("hospital", "EHR Title",
     top_bottom("hospital[ehr_group]", 40, '_h & " hospitals fall short most (" & _hp & "), " & _l & " least (" & _lp & ")"',
                "Share falling short by EHR company",
                extra=f' && NOT {eq("hospital[ehr_group]", NO_EHR)} && NOT {eq("hospital[ehr_group]", "Other or not identified")}'),
     None, "Titles"),
    ("hospital", "Vendor Type Short",
     f'IF ( SELECTEDVALUE ( hospital[ehr_group] ) IN {{ "{TOP3[0]}", "{TOP3[1]}", "{TOP3[2]}", "TruBridge (CPSI)" }} && [Hospitals] >= 20, [Short Share] )',
     PCT, "EHR"),
    ("hospital", "Matrix Title",
     f'VAR _t = CALCULATE ( [Short Share], {kf(eq("hospital[ehr_group]", "TruBridge (CPSI)"), eq("hospital[hospital_type]", RURAL))} )\n'
     f'VAR _e = CALCULATE ( [Short Share], {kf(eq("hospital[ehr_group]", "Epic"), eq("hospital[hospital_type]", RURAL))} )\n'
     'RETURN IF ( ISBLANK ( _t ) || ISBLANK ( _e ), "Share falling short by EHR company, small rural vs general hospitals",\n'
     '    "Small rural hospitals: " & FORMAT ( _t, "0%" ) & " fall short on TruBridge, " & FORMAT ( _e, "0%" ) & " on Epic" )',
     None, "Titles"),

    # ---- money, size and history
    ("hospital", "Fifth Short", "IF ( NOT ISBLANK ( SELECTEDVALUE ( hospital[margin_fifth] ) ) && [Hospitals] >= 20, [Short Share] )", PCT, "Money"),
    ("hospital", "Fifth Colour", f'IF ( SELECTEDVALUE ( hospital[margin_fifth] ) = 1, "{RED}", "{RED_L}" )', None, "Colours"),
    ("hospital", "Least Profitable Short", share_for("hospital[margin_fifth] = 1"), PCT, "KPI"),
    ("hospital", "Least Profitable Context",
     f'VAR _b = {share_for("hospital[margin_fifth] = 5")}\n'
     'RETURN IF ( ISBLANK ( _b ), "least profitable fifth of hospitals", "vs " & FORMAT ( _b, "0%" ) & " for the most profitable" )',
     None, "KPI"),
    ("hospital", "Fifth Title",
     f'VAR _a = {share_for("hospital[margin_fifth] = 1")}\nVAR _b = {share_for("hospital[margin_fifth] = 5")}\n'
     'RETURN IF ( ISBLANK ( _a ) || ISBLANK ( _b ), "Share falling short by profit",\n'
     '    "The least profitable fall short most (" & FORMAT ( _a, "0%" ) & "), the most profitable " & FORMAT ( _b, "0%" ) )',
     None, "Titles"),
    ("hospital", "Money Short", "IF ( NOT ISBLANK ( SELECTEDVALUE ( hospital[lost_money] ) ) && [Hospitals] >= 20, [Short Share] )", PCT, "Money"),
    ("hospital", "Losses Short", share_for(eq("hospital[lost_money]", SHORT_LBL)), PCT, "KPI"),
    ("hospital", "Losses Context",
     f'VAR _b = {share_for(eq("hospital[lost_money]", "Did not"))}\n'
     'RETURN IF ( ISBLANK ( _b ), "of hospitals that lost money", "vs " & FORMAT ( _b, "0%" ) & " of those without losses" )',
     None, "KPI"),
    ("hospital", "Money Title",
     f'VAR _a = {share_for(eq("hospital[lost_money]", SHORT_LBL))}\nVAR _b = {share_for(eq("hospital[lost_money]", "Did not"))}\n'
     'RETURN IF ( ISBLANK ( _a ) || ISBLANK ( _b ) || _b = 0, "Share falling short, by whether the hospital lost money",\n'
     '    "Losing money: " & FORMAT ( DIVIDE ( _a, _b ), "0.0" ) & " times as likely to fall short" )',
     None, "Titles"),
    ("hospital", "History Count", "IF ( NOT ISBLANK ( SELECTEDVALUE ( hospital[history] ) ), [Hospitals] )", INT, "Money"),
    ("hospital", "History Colour",
     f'SWITCH ( SELECTEDVALUE ( hospital[history] ), "Never", "{COBALT}", "Every year", "{RED_D}",\n'
     f'    "1 of 6 years", "{RED_L}", "2 of 6 years", "{RED_L}", "{RED}" )', None, "Colours"),
    ("hospital", "Every Year", f'CALCULATE ( [Hospitals], {kf(eq("hospital[history]", "Every year"))} )', INT, "KPI"),
    ("hospital", "Every Year Context", '"hospitals, in all six yearly files"', None, "KPI"),
    ("hospital", "Never", f'CALCULATE ( [Hospitals], {kf(eq("hospital[history]", "Never"))} )', INT, "KPI"),
    ("hospital", "Never Context",
     '"of " & FORMAT ( CALCULATE ( [Hospitals], NOT ISBLANK ( hospital[history] ) ), "#,0" ) & " in all six yearly files"',
     None, "KPI"),
    ("hospital", "History Title",
     'IF ( ISBLANK ( [Never] ) && ISBLANK ( [Every Year] ), "How many of the six years hospitals fell short",\n'
     '    FORMAT ( [Never] + 0, "#,0" ) & " hospitals never fell short; " & FORMAT ( [Every Year] + 0, "#,0" ) & " fell short every single year" )',
     None, "Titles"),

    # ---- states (ranks compare every state: REMOVEFILTERS on states only, other filters still apply)
    ("hospital", "Top 10 Share",
     "VAR _cur = [Short Share]\nVAR _n = [Hospitals]\n"
     'VAR _all = CALCULATETABLE ( FILTER ( ADDCOLUMNS ( VALUES ( states[state_name] ), "@r", [Short Share], "@n", [Hospitals] ), [@n] >= 10 ), REMOVEFILTERS ( states ) )\n'
     "RETURN IF ( HASONEVALUE ( states[state_name] ) && _n >= 10 && COUNTROWS ( FILTER ( _all, [@r] > _cur ) ) < 10, _cur )",
     PCT, "States"),
    ("hospital", "Top 10 Hospitals", "IF ( NOT ISBLANK ( [Top 10 Share] ), [Hospitals] )", INT, "States"),
    ("hospital", "Top 10 Short", "IF ( NOT ISBLANK ( [Top 10 Share] ), [Short] )", INT, "States"),
    ("hospital", "Tile Label", "SELECTEDVALUE ( states[state] )", None, "Map"),
    ("hospital", "Tile Colour",
     "VAR _r = [Short Share]\nRETURN SWITCH ( TRUE (),\n"
     f'    ISBLANK ( SELECTEDVALUE ( states[state] ) ), "{PANEL}",\n'
     '    ISBLANK ( _r ), "#E2E8F0",\n    _r < 0.05, "#FDF0EA",\n    _r < 0.10, "#F9CDBB",\n    _r < 0.15, "#F29A78",\n'
     f'    _r < 0.25, "{RED}",\n    "{RED_D}" )', None, "Map"),
    ("hospital", "Tile Font", f'IF ( [Short Share] >= 0.15 || ISBLANK ( [Short Share] ), "#FFFFFF", "{DARK}" )', None, "Map"),
    ("hospital", "Fifth States",
     'COUNTROWS ( FILTER ( CALCULATETABLE ( ADDCOLUMNS ( VALUES ( states[state] ), "@r", [Short Share], "@n", [Hospitals] ), REMOVEFILTERS ( states ) ), [@n] >= 10 && [@r] >= 0.2 ) ) + 0',
     INT, "KPI"),
    ("hospital", "Zero States",
     'COUNTROWS ( FILTER ( CALCULATETABLE ( ADDCOLUMNS ( VALUES ( states[state] ), "@s", [Short] + 0, "@n", [Hospitals] ), REMOVEFILTERS ( states ) ), [@n] >= 10 && [@s] = 0 ) ) + 0',
     INT, "KPI"),
    ("hospital", "Map Title",
     'VAR _t = TOPN ( 1, FILTER ( CALCULATETABLE ( ADDCOLUMNS ( VALUES ( states[state_name] ), "@r", [Short Share], "@n", [Hospitals] ), REMOVEFILTERS ( states ) ), [@n] >= 10 ), [@r], DESC )\n'
     'RETURN IF ( ISBLANK ( MAXX ( _t, [@r] ) ), "Share of hospitals falling short, by state",\n'
     '    MAXX ( _t, states[state_name] ) & " has the highest share falling short: " & FORMAT ( MAXX ( _t, [@r] ), "0%" ) & " of its hospitals" )',
     None, "Titles"),
    ("hospital", "Selected State", 'SELECTEDVALUE ( states[state_name], "All states" )', None, "Tooltip"),
    ("hospital", "State Rank Text",
     "VAR _cur = [Short Share]\n"
     'VAR _all = CALCULATETABLE ( FILTER ( ADDCOLUMNS ( VALUES ( states[state_name] ), "@r", [Short Share], "@n", [Hospitals] ), [@n] >= 10 ), REMOVEFILTERS ( states ) )\n'
     'RETURN IF ( HASONEVALUE ( states[state_name] ) && [Hospitals] >= 10, "#" & COUNTROWS ( FILTER ( _all, [@r] > _cur ) ) + 1 & " of "\n'
     '    & COUNTROWS ( _all ) & " for the share falling short", "Too few hospitals to rank" )', None, "Tooltip"),
    ("hospital", "State Short Text", 'FORMAT ( [Short] + 0, "#,0" ) & " of " & FORMAT ( [Hospitals], "#,0" ) & " hospitals"', None, "Tooltip"),
    ("hospital", "State No EHR", 'FORMAT ( [No EHR Short] + 0, "#,0" ) & " had no certified EHR"', None, "Tooltip"),

    # ---- data quality (latest file)
    ("hospital", "ID Count", "IF ( NOT ISBLANK ( SELECTEDVALUE ( hospital[id_quality] ) ), [Hospitals] )", INT, "Quality"),
    ("hospital", "ID Colour",
     'SWITCH ( SELECTEDVALUE ( hospital[id_quality] ),\n'
     f'    "Valid ID, found in the federal list", "{GREY}",\n'
     f'    """Not Available"" typed instead of an ID", "{PURPLE}",\n    "{AMBER}" )', None, "Colours"),
    ("hospital", "Not Available Count",
     f'CALCULATE ( [Hospitals], KEEPFILTERS ( hospital[id_quality] = """Not Available"" typed instead of an ID" ) ) + 0', INT, "KPI"),
    ("hospital", "Not In List Count", f'CALCULATE ( [Hospitals], {kf(eq("hospital[id_quality]", "Not found in the federal list"))} ) + 0', INT, "KPI"),
    ("hospital", "Bad Format Count", f'CALCULATE ( [Hospitals], {kf(eq("hospital[id_quality]", "Wrong format (lowercase or wrong length)"))} ) + 0', INT, "KPI"),
    ("hospital", "Disagree Count", f"CALCULATE ( SUM ( hospital[files_disagree] ), {kf(LATEST)} ) + 0", INT, "KPI"),
    ("hospital", "Not Available Context", '"hospitals, and every one fell short"', None, "KPI"),
    ("hospital", "Not In List Context", '"IDs missing from the federal list"', None, "KPI"),
    ("hospital", "Bad Format Context", '"lowercase or wrong length"', None, "KPI"),
    ("hospital", "Disagree Context", '"hospitals rated differently"', None, "KPI"),
    ("hospital", "Disagree Count By Type", "IF ( NOT ISBLANK ( SELECTEDVALUE ( hospital[disagree_type] ) ), [Disagree Count] )", INT, "Quality"),
    ("hospital", "Files Count", "IF ( SELECTEDVALUE ( hospital[n_files] ) > 0, COUNTROWS ( hospital ) )", INT, "Quality"),
    ("hospital", "Files Colour", f'IF ( SELECTEDVALUE ( hospital[n_files] ) = 6, "{REST}", "{AMBER}" )', None, "Colours"),
    ("hospital", "ID Title",
     f'VAR _p = DIVIDE ( [Hospitals] - CALCULATE ( [Hospitals], {kf(eq("hospital[id_quality]", "Valid ID, found in the federal list"))} ), [Hospitals] )\n'
     'RETURN IF ( ISBLANK ( _p ), "What hospitals put in the EHR ID field", FORMAT ( ROUND ( _p * 100, 0 ), "0" ) & " in 100 hospitals have a problem in the EHR ID field" )',
     None, "Titles"),
    ("hospital", "Disagree Title",
     'FORMAT ( [Disagree Count], "#,0" ) & " hospitals rated differently by the two files"', None, "Titles"),
    ("hospital", "Files Title",
     'VAR _a = CALCULATE ( COUNTROWS ( hospital ), KEEPFILTERS ( hospital[n_files] = 6 ) )\n'
     'VAR _b = CALCULATE ( COUNTROWS ( hospital ), KEEPFILTERS ( hospital[n_files] > 0 ) )\n'
     'RETURN FORMAT ( _a + 0, "#,0" ) & " of " & FORMAT ( _b + 0, "#,0" ) & " hospitals appear in all six yearly files"', None, "Titles"),
]

RURAL_EQ = eq("hospital[hospital_type]", RURAL)
MEASURES += [
    ("hospital_year", "Rural Year Share", f"CALCULATE ( [Year Share], {kf(eq('hospital_year[year_type]', RURAL))} )", PCT, "Spark"),
    ("hospital", "Short 2019 Context",
     f"VAR _a = CALCULATE ( [Year Share], {kf('hospital_year[snapshot_year] = 2019')} )\n"
     'RETURN FORMAT ( [Short] + 0, "#,0" ) & " hospitals" & IF ( ISBLANK ( _a ), "", "  ·  " & FORMAT ( _a, "0%" ) & " in 2019" )',
     None, "KPI"),
    ("hospital", "No EHR Pct", "[No EHR Share]", PCT, "KPI"),
    ("hospital", "No EHR Context", 'FORMAT ( [No EHR Short] + 0, "#,0" ) & " of the " & FORMAT ( [Short] + 0, "#,0" ) & " that fell short"', None, "KPI"),
    ("hospital", "Rural Short", share_for(RURAL_EQ), PCT, "KPI"),
    ("hospital", "Rural Context",
     f'VAR _g = {share_for(eq("hospital[hospital_type]", GENERAL))}\n'
     'RETURN IF ( ISBLANK ( _g ), "small rural hospitals shown", "vs " & FORMAT ( _g, "0%" ) & " of general hospitals" )', None, "KPI"),
    ("hospital", "Dots Met", 'IF ( ISBLANK ( [Hospitals] ), "–", FORMAT ( 100 - ROUND ( [Short Share] * 100, 0 ), "0" ) )', None, "Hero"),
    ("hospital", "Dots Short",
     'IF ( ISBLANK ( [Hospitals] ), "–", FORMAT ( ROUND ( [Short Share] * 100, 0 ) - ROUND ( DIVIDE ( [No EHR Short], [Hospitals] ) * 100, 0 ), "0" ) )',
     None, "Hero"),
    ("hospital", "Dots No EHR", 'IF ( ISBLANK ( [Hospitals] ), "–", FORMAT ( ROUND ( DIVIDE ( [No EHR Short], [Hospitals] ) * 100, 0 ), "0" ) )',
     None, "Hero"),
    ("hospital", "Owner Tree Title",
     'VAR _t = TOPN ( 1, FILTER ( ADDCOLUMNS ( VALUES ( hospital[ownership] ), "@s", [Short] ), NOT ISBLANK ( [@s] ) ), [@s], DESC )\n'
     'RETURN IF ( ISBLANK ( [Short] ), "Who owns the hospitals that fell short",\n'
     '    MAXX ( _t, hospital[ownership] ) & ": " & FORMAT ( MAXX ( _t, [@s] ), "#,0" ) & " of the " & FORMAT ( [Short], "#,0" ) & " that fell short" )',
     None, "Titles"),
    ("hospital", "Market Count",
     "IF ( NOT ISBLANK ( SELECTEDVALUE ( hospital[main_developer] ) ), CALCULATE ( [Hospitals], REMOVEFILTERS ( hospital[ehr_group] ) ) )",
     INT, "EHR"),
    ("hospital", "EHR Hospitals", "IF ( NOT ISBLANK ( [EHR Short] ), [Hospitals] )", INT, "EHR"),
    ("hospital", "EHR Short Count", "IF ( NOT ISBLANK ( [EHR Short] ), [Short] + 0 )", INT, "EHR"),
    ("hospital", "Gauge Min", "0", PCT, "EHR"),
    ("hospital", "Gauge Max", "0.3", PCT, "EHR"),
    ("hospital", "Rural TruBridge", share_for(eq("hospital[ehr_group]", "TruBridge (CPSI)"), RURAL_EQ), PCT, "EHR"),
    ("hospital", "Rural MEDITECH", share_for(eq("hospital[ehr_group]", "MEDITECH"), RURAL_EQ), PCT, "EHR"),
    ("hospital", "Rural Epic", share_for(eq("hospital[ehr_group]", "Epic"), RURAL_EQ), PCT, "EHR"),
    ("hospital", "Ring Lost",
     f'VAR _s = CALCULATE ( [Short] + 0, {kf(eq("hospital[lost_money]", SHORT_LBL))} )\n'
     f'VAR _n = CALCULATE ( [Hospitals], {kf(eq("hospital[lost_money]", SHORT_LBL))} )\n'
     'RETURN SWITCH ( SELECTEDVALUE ( Result[result] ), "Fell short", _s, "Met the standards", _n - _s )', INT, "Money"),
    ("hospital", "Ring Not",
     f'VAR _s = CALCULATE ( [Short] + 0, {kf(eq("hospital[lost_money]", "Did not"))} )\n'
     f'VAR _n = CALCULATE ( [Hospitals], {kf(eq("hospital[lost_money]", "Did not"))} )\n'
     'RETURN SWITCH ( SELECTEDVALUE ( Result[result] ), "Fell short", _s, "Met the standards", _n - _s )', INT, "Money"),
    ("hospital", "Disagree Up", f'FORMAT ( CALCULATE ( [Disagree Count], {kf(eq("hospital[disagree_type]", "Short in Oct 2024 file, met in latest"))} ), "#,0" )', None, "Quality"),
    ("hospital", "Disagree Down", f'FORMAT ( CALCULATE ( [Disagree Count], {kf(eq("hospital[disagree_type]", "Met in Oct 2024 file, short in latest"))} ), "#,0" )', None, "Quality"),
]

# every KPI number also gets a text version, so a card shows "–" instead of "(Blank)" when a filter leaves no hospitals
MEASURES += [(h, f"{n} Text", f'VAR _v = [{n}]\nRETURN IF ( ISBLANK ( _v ), "–", FORMAT ( _v, "{f}" ) )', None, "KPI text")
             for h, n, d, f, fo in list(MEASURES) if fo == "KPI" and f]


# ---- one hospital
MEASURES += [
    ("hospital", "Profile Name", f'IF ( {ONE}, SELECTEDVALUE ( hospital[display_name] ), "Pick a hospital" )', None, "Hospital"),
    ("hospital", "Profile Facts",
     f'IF ( {ONE}, SELECTEDVALUE ( hospital[hospital_type] ) & "   ·   " & SELECTEDVALUE ( hospital[ownership] )'
     ' & "   ·   " & SELECTEDVALUE ( hospital[city] ) & ", " & SELECTEDVALUE ( hospital[state_name] )'
     ' & IF ( NOT ISBLANK ( SUM ( hospital[beds] ) ), "   ·   " & FORMAT ( SUM ( hospital[beds] ), "#,0" ) & " beds" ),'
     ' "Type a hospital name in the search box on the right" )', None, "Hospital"),
    ("hospital", "Profile Status",
     f'IF ( {ONE}, IF ( SUM ( hospital[in_latest] ) = 0, "Not in the 2024 file", IF ( SUM ( hospital[not_met] ) = 1, "Fell short", "Met the standards" ) ) )',
     None, "Hospital"),
    ("hospital", "Profile Status Colour", f'IF ( SUM ( hospital[not_met] ) = 1, "{RED}", "{COBALT}" )', None, "Hospital"),
    ("hospital", "Profile Status Context", f'IF ( {ONE}, "in the 2024 reporting year" )', None, "Hospital"),
    ("hospital", "Profile EHR",
     f'IF ( {ONE}, IF ( SELECTEDVALUE ( hospital[ehr_status] ) = "{NO_EHR}", "None reported",\n'
     '    COALESCE ( SELECTEDVALUE ( hospital[main_developer] ), "Not identified" ) ) )', None, "Hospital"),
    ("hospital", "Profile EHR Colour", f'IF ( SELECTEDVALUE ( hospital[ehr_status] ) = "{NO_EHR}", "{PURPLE}", "{INK}" )', None, "Hospital"),
    ("hospital", "Profile EHR Context",
     "VAR _k = SUM ( hospital[hospitals_sharing_ehr_id] ) - 1\n"
     f'RETURN IF ( {ONE}, IF ( SELECTEDVALUE ( hospital[ehr_status] ) = "{NO_EHR}", "no certified EHR ID in the 2024 file",\n'
     '    IF ( _k > 0, "same EHR setup as " & _k & " other hospital" & IF ( _k > 1, "s", "" ), "its own EHR setup" ) ) )',
     None, "Hospital"),
    ("hospital", "Profile Years",
     f'IF ( {ONE}, IF ( COUNTROWS ( hospital_year ) > 0, FORMAT ( SUM ( hospital_year[not_met] ) + 0, "0" ) & " of " & COUNTROWS ( hospital_year ), "No history" ) )',
     None, "Hospital"),
    ("hospital", "Profile Years Colour", f'IF ( SUM ( hospital_year[not_met] ) > 0, "{RED}", "{COBALT}" )', None, "Hospital"),
    ("hospital", "Profile Years Context", f'IF ( {ONE}, "yearly Medicare files, 2019-2024" )', None, "Hospital"),
    ("hospital", "Profile Margin", f'IF ( {ONE}, IF ( ISBLANK ( SUM ( hospital[total_margin] ) ), "No report", FORMAT ( SUM ( hospital[total_margin] ) * 100, "0.0" ) & " cents" ) )',
     None, "Hospital"),
    ("hospital", "Profile Margin Colour", f'IF ( SUM ( hospital[total_margin] ) < 0, "{RED}", "{INK}" )', None, "Hospital"),
    ("hospital", "Profile Margin Context",
     f'IF ( {ONE}, IF ( ISBLANK ( SUM ( hospital[total_margin] ) ), "no financial report matched",\n'
     '    "profit kept from each $1" & IF ( SELECTEDVALUE ( hospital[lost_money] ) = "Lost money 2 years in a row", "; lost money 2 years running", "" ) ) )',
     None, "Hospital"),
    ("hospital_year", "Strip Value", f"IF ( {ONE}, COUNTROWS ( hospital_year ) )", "0", "Hospital"),
    ("hospital_year", "Strip Colour", f'IF ( SUM ( hospital_year[not_met] ) = 1, "{RED}", "{COBALT}" )', None, "Hospital"),
    ("hospital", "Profile Sentence",
     "VAR _t = SELECTEDVALUE ( hospital[hospital_type] )\n"
     "VAR _peer = CALCULATE ( [Short Share], REMOVEFILTERS ( hospital ), REMOVEFILTERS ( states ), hospital[hospital_type] = _t )\n"
     "VAR _short = SUM ( hospital[not_met] ) = 1\n"
     "VAR _y = SUM ( hospital_year[not_met] ) + 0\n"
     "VAR _n = COUNTROWS ( hospital_year )\n"
     f"RETURN IF ( {ONE} && SUM ( hospital[in_latest] ) = 1,\n"
     '    "In 2024 this hospital " & IF ( _short, "did not meet", "met" ) & " Medicare\'s standards for sharing health records electronically. "\n'
     f'    & FORMAT ( _peer, "0%" ) & IF ( _t = "{GENERAL}", " of general hospitals", " of small rural hospitals" ) & " fell short. "\n'
     '    & IF ( _n > 0, "It fell short in " & _y & " of the " & _n & " yearly files since 2019"\n'
     '        & IF ( _y = 0, ": a steady record.", IF ( _y = _n, ": it has never met them.", "." ) ), "" )\n'
     '    & IF ( SELECTEDVALUE ( hospital[ehr_status] ) = "' + NO_EHR + '", " It reported no certified EHR, the most common reason hospitals fall short.", "" ),\n'
     '    IF ( ' + ONE + ', "This hospital is not in the latest Medicare file (it may have closed or merged).", "Pick a hospital to see what its numbers mean." ) )',
     None, "Hospital"),
    ("hospital", "Profile Checks",
     f'IF ( {ONE} && SUM ( hospital[in_latest] ) = 1, "EHR ID field: " & SELECTEDVALUE ( hospital[id_quality] ) & ". "\n'
     '    & IF ( SUM ( hospital[files_disagree] ) = 1, "The two Medicare files give different answers for this hospital.",\n'
     '         "The Medicare files agree on its status." ) )', None, "Hospital"),
]
CALC_COLUMNS = []


def csv_columns(table):
    """Column names and types from the CSV extract (pandas infers the type)."""
    df = pd.read_csv(DATA / f"{table}.csv", dtype={c: str for c in TEXT_COLS})
    out = []
    for col, dt in df.dtypes.items():
        if col in TEXT_COLS:
            out.append((col, "string", "type text"))
        elif col in INT_COLS or pd.api.types.is_integer_dtype(dt):
            out.append((col, "int64", "Int64.Type"))
        elif pd.api.types.is_float_dtype(dt):
            out.append((col, "double", "type number"))
        else:
            out.append((col, "string", "type text"))
    return out


def table_tmdl(table, columns):
    out = [f"table {table}", f"\tlineageTag: {tag(table)}", ""]
    for home, name, dax, fmt, folder in MEASURES:
        if home != table:
            continue
        out += [f"\tmeasure {qn(name)} =", indent(dax, 3)] if "\n" in dax else [f"\tmeasure {qn(name)} = {dax}"]
        if fmt:   # TMDL: a format containing quotes must itself be quoted, with inner quotes doubled
            out.append("\t\tformatString: " + ('"' + fmt.replace('"', '""') + '"' if '"' in fmt else fmt))
        out += [f"\t\tdisplayFolder: {folder}", f"\t\tlineageTag: {tag(table, 'm', name)}", ""]
    for col, dtype, _ in columns:
        out += [f"\tcolumn {col}", f"\t\tdataType: {dtype}"]
        if dtype == "double":
            out.append("\t\tformatString: #,0.00")
        elif dtype == "int64":
            out.append("\t\tformatString: 0")
        if col in HIDDEN:
            out.append("\t\tisHidden")
        if (table, col) in SORT_BY:
            out.append(f"\t\tsortByColumn: {SORT_BY[(table, col)]}")
        out += [f"\t\tlineageTag: {tag(table, col)}",
                f"\t\tsummarizeBy: {'none' if dtype in ('string', 'boolean') or col in INT_COLS else 'sum'}",
                f"\t\tsourceColumn: {col}", "", "\t\tannotation SummarizationSetBy = Automatic", ""]
    types = ", ".join(f'{{"{c}", {m}}}' for c, _, m in columns)
    m = (f'let\n    Source = Csv.Document(File.Contents(DataFolder & "{table}.csv"), '
         '[Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),\n'
         '    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),\n'
         '    // empty CSV cells arrive as "" text; make them real blanks so they drop out of charts\n'
         '    Blanks = Table.ReplaceValue(Promoted, "", null, Replacer.ReplaceValue, Table.ColumnNames(Promoted)),\n'
         f'    Typed = Table.TransformColumnTypes(Blanks,{{{types}}}, "en-US")\nin\n    Typed')
    out += [f"\tpartition {table} = m", "\t\tmode: import", "\t\tsource =", indent(m, 4), "",
            "\tannotation PBI_ResultType = Table", ""]
    return "\n".join(out)


def check_names():
    """Power BI rejects a measure whose name matches any column (case-insensitive) or another measure."""
    cols = {c.lower() for t in TABLES for c, *_ in csv_columns(t)} | {"row", "col", "result"}
    names = [n.lower() for _, n, *_ in MEASURES]
    clash = sorted({n for n in names if n in cols} | {n for n in names if names.count(n) > 1})
    if clash:
        raise ValueError(f"measure names clash with columns or each other: {clash}")


def calc_table(name, cols, dax):
    """Small DAX table. cols: (column, dataType)."""
    out = [f"table {name}", f"\tlineageTag: {tag(name)}", ""]
    for col, dtype in cols:
        out += [f"\tcolumn {col}", f"\t\tdataType: {dtype}", *(["\t\tformatString: 0"] if dtype == "int64" else []),
                f"\t\tlineageTag: {tag(name, col)}",
                "\t\tsummarizeBy: none", "\t\tisNameInferred", f"\t\tsourceColumn: [{col}]", "",
                "\t\tannotation SummarizationSetBy = Automatic", ""]
    out += [f"\tpartition {name} = calculated", "\t\tmode: import", "\t\tsource =", indent(dax, 4), ""]
    return "\n".join(out)


def build_model():
    check_names()
    shutil.rmtree(SM, ignore_errors=True)
    d = SM / "definition"
    write_json(SM / "definition.pbism", {"$schema": S_PBISM, "version": "4.0", "settings": {}})
    write(d / "database.tmdl", "database\n\tcompatibilityLevel: 1600\n")
    write(d / "model.tmdl", "\n".join([
        "model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tsourceQueryCulture: en-US", "\tdataAccessOptions", "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull",
        "", "annotation __PBI_TimeIntelligenceEnabled = 0", "",
        *[f"ref table {t}" for t in TABLES + ["Dots", "Result"]], ""]))
    folder = str(DATA) + "\\"
    write(d / "expressions.tmdl", "\n".join([
        f'expression DataFolder = "{folder}" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]',
        f"\tlineageTag: {tag('DataFolder')}", "", "\tannotation PBI_ResultType = Text", ""]))
    for t in TABLES:
        write(d / "tables" / f"{t}.tmdl", table_tmdl(t, csv_columns(t)))
    write(d / "tables" / "Dots.tmdl", calc_table(      # 10 x 10 grid for the hero dot chart, not related to anything
        "Dots", [("row", "int64"), ("col", "int64")],
        'SELECTCOLUMNS ( GENERATESERIES ( 0, 99, 1 ), "row", INT ( [Value] / 10 ), "col", MOD ( [Value], 10 ) )'))
    write(d / "tables" / "Result.tmdl", calc_table(    # two slices for the "fell short / met" rings
        "Result", [("result", "string")], 'DATATABLE ( "result", STRING, { { "Fell short" }, { "Met the standards" } } )'))
    write(d / "relationships.tmdl", "\n".join([
        f"relationship {tag('rel', 'year')}", "\tfromColumn: hospital_year.ccn", "\ttoColumn: hospital.ccn", "",
        f"relationship {tag('rel', 'states')}", "\tfromColumn: hospital.state", "\ttoColumn: states.state", ""]))


# =====================================================================
# Report helpers (PBIR JSON)
# =====================================================================
def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def s(text):
    return lit("'" + text.replace("'", "''") + "'")


def solid(hex_):
    return {"solid": {"color": s(hex_)}}


def field(entity, prop, measure=False):
    return {("Measure" if measure else "Column"): {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def home(measure):
    return next(h for h, n, *_ in MEASURES if n == measure)


def mexpr(measure):
    return {"expr": field(home(measure), measure, True)}


def C(entity, prop, name=None):
    return (entity, prop, False, name) if name else (entity, prop, False)


def M(prop, name=None):
    return (home(prop), prop, True, name) if name else (home(prop), prop, True)


def projections(fields):
    out = []
    for e, p, m, *name in fields:
        pr = {"field": field(e, p, m), "queryRef": f"{e}.{p}", "nativeQueryRef": p}
        if name and name[0]:
            pr["displayName"] = name[0]
        out.append(pr)
    return {"projections": out}


def by_measure(measure):
    return {"solid": {"color": mexpr(measure)}}


def in_filter(entity, prop, value, name):
    """Visual-level filter: keep rows where entity[prop] equals value."""
    v = f"{value}L" if isinstance(value, int) else "'" + value.replace("'", "''") + "'"
    return {"name": name, "field": field(entity, prop), "type": "Categorical", "howCreated": "User",
            "filter": {"Version": 2, "From": [{"Name": "t", "Entity": entity, "Type": 0}],
                       "Where": [{"Condition": {"In": {
                           "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": prop}}],
                           "Values": [[{"Literal": {"Value": v}}]]}}}]}}


def container(title=None, subtitle=None, tooltip_page=None, pad=(12, 6, 12, 12), background=None, radius=0,
              border=None, shadow=False, transparency=0):
    """Transparent by default; cards set a background, a hairline border (Power BI only rounds corners when the
    border is on) and a soft navy shadow. Cards are visuals, not artwork: Power BI Desktop stretches a page image
    over a slightly taller area than the visuals use, so drawn cards drift away from the charts on them."""
    objs = {
        "background": [{"properties": {"show": lit("true" if background else "false"),
                                       **({"color": solid(background), "transparency": lit(f"{transparency}D")} if background else {})}}],
        "border": [{"properties": {"show": lit("true" if background else "false"),
                                   **({"color": solid(border or background), "radius": lit(f"{radius}D")} if background else {})}}],
        "dropShadow": [{"properties": {
            "show": lit("true"), "color": solid("#1E293B"), "position": s("Outer"), "preset": s("Custom"),
            "transparency": lit("90D"), "shadowBlur": lit("10D"), "shadowSpread": lit("0D"),
            "shadowDistance": lit("2D"), "angle": lit("90D")}}] if shadow else [{"properties": {"show": lit("false")}}],
        "visualHeader": [{"properties": {"background": solid(PANEL), "border": solid(LINE), "foreground": solid(INK_2)}}],
        "padding": [{"properties": {"top": lit(f"{pad[0]}D"), "bottom": lit(f"{pad[1]}D"),
                                    "left": lit(f"{pad[2]}D"), "right": lit(f"{pad[3]}D")}}],
        "title": [{"properties": {"show": lit("false")}}],
    }
    if title:
        text = mexpr(title[1:]) if title.startswith("=") else s(title)
        objs["title"] = [{"properties": {"show": lit("true"), "text": text, "fontColor": solid(INK), "fontSize": lit("13D"),
                                         "fontFamily": s("Segoe UI Semibold"), "bold": lit("false"), "titleWrap": lit("true")}}]
    if subtitle:
        objs["subTitle"] = [{"properties": {"show": lit("true"), "text": s(subtitle), "fontColor": solid(INK_2),
                                            "fontSize": lit("10D"), "fontFamily": s(FONT), "titleWrap": lit("true")}}]
    if tooltip_page:
        objs["visualTooltip"] = [{"properties": {"type": s("ReportPage"), "section": s(tooltip_page)}}]
    return objs


def axes(show_value=False, cat_size=11, inner_padding=None, label_area=None, categorical=False, show_cat=True,
         value_start=None, value_end=None):
    cat = {"show": lit("true" if show_cat else "false"), "showAxisTitle": lit("false"), "labelColor": solid(INK_2),
           "fontSize": lit(f"{cat_size}D"), "fontFamily": s(FONT)}
    if inner_padding is not None:
        cat["innerPadding"] = lit(f"{inner_padding}L")
    if label_area is not None:
        cat["maxMarginFactor"] = lit(f"{label_area}L")
    if categorical:
        cat["axisType"] = s("Categorical")
    val = {"show": lit("true" if show_value else "false"), "showAxisTitle": lit("false"), "labelColor": solid(INK_2),
           "fontSize": lit("10D"), "fontFamily": s(FONT), "gridlineShow": lit("true" if show_value else "false"),
           "gridlineColor": solid("#E2E8F0")}
    if value_start is not None:
        val["start"] = lit(f"{value_start}D")
    if value_end is not None:
        val["end"] = lit(f"{value_end}D")
    return {"categoryAxis": [{"properties": cat}], "valueAxis": [{"properties": val}]}


def labels(size=12, colour=INK, show=True):
    return {"labels": [{"properties": {"show": lit("true" if show else "false"), "color": solid(colour),
                                       "fontSize": lit(f"{min(size, 11)}D"), "bold": lit("false"), "fontFamily": s(FONT),
                                       "labelDisplayUnits": lit("1D")}}]}


def legend(position="Top", show=True):
    return {"legend": [{"properties": {"show": lit("true" if show else "false"), "position": s(position),
                                       "labelColor": solid(INK_2), "fontSize": lit("11D"), "fontFamily": s(FONT),
                                       "showTitle": lit("false")}}]}


def fill_by(measure):
    return [{"properties": {"fill": by_measure(measure)}, "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}]}}]


def fill_by_value(entity, prop, colours):
    col = field(entity, prop)
    return [{"properties": {"fill": solid(c)}, "selector": {"data": [{"scopeId": {"Comparison": {
        "ComparisonKind": 0, "Left": col, "Right": {"Literal": {"Value": f"'{v}'"}}}}}]}} for v, c in colours.items()]


def chart(vtype, roles, title=None, subtitle=None, sort=None, objects=None, tooltip_page=None, pad=(12, 6, 12, 12),
          filters=None):
    v = {"visualType": vtype, "query": {"queryState": {r: projections(f) for r, f in roles.items()}},
         "visualContainerObjects": container(title, subtitle, tooltip_page, pad=pad), "drillFilterOtherVisuals": True}
    if sort:
        (e, p, m, *_), direction = sort
        v["query"]["sortDefinition"] = {"sort": [{"field": field(e, p, m), "direction": direction}], "isDefaultSort": False}
    if objects:
        v["objects"] = dict(objects)
    out = {"visual": v}
    if filters:
        out["filterConfig"] = {"filters": filters}
    return out


def textbox(paragraphs, align=None, pad=(0, 0, 4, 4), background=None, radius=0, border=None, shadow=False, transparency=0):
    """paragraphs: list of (text, size, bold, colour) or lists of such runs for one line.
    With a background and no text it is a plain shape (card, stripe, panel)."""
    def run(t, size, bold, col):
        return {"value": t, "textStyle": {"fontSize": f"{size}pt", "color": col, "fontFamily": FONT,
                                          **({"fontWeight": "bold"} if bold else {})}}
    paras = [{"textRuns": [run(*r) for r in (p if isinstance(p, list) else [p])],
              **({"horizontalTextAlignment": align} if align else {})} for p in paragraphs if p]
    if not paras:
        paras = [{"textRuns": [{"value": ""}]}]
    v = {"visualType": "textbox", "drillFilterOtherVisuals": True,
         "objects": {"general": [{"properties": {"paragraphs": paras}}]},
         "visualContainerObjects": container(pad=pad, background=background, radius=radius, border=border, shadow=shadow,
                                            transparency=transparency)}
    if background:      # shapes and panels: no hover toolbar
        v["visualContainerObjects"]["visualHeader"] = [{"properties": {"show": lit("false")}}]
    return {"visual": v}


def shape(colour, radius=0, border=None, shadow=False, transparency=0):
    return textbox([], background=colour, radius=radius, border=border, shadow=shadow, pad=(0, 0, 0, 0),
                   transparency=transparency)


def image(item_name):
    return {"visual": {"visualType": "image", "drillFilterOtherVisuals": True,
                       "objects": {"general": [{"properties": {"imageUrl": {"expr": {"ResourcePackageItem": {
                           "PackageName": "RegisteredResources", "PackageType": 1, "ItemName": item_name}}}}}],
                                   "imageScaling": [{"properties": {"imageScalingType": s("Fit")}}]},
                       "visualContainerObjects": {**container(pad=(0, 0, 0, 0)),
                                                  "visualHeader": [{"properties": {"show": lit("false")}}]}}}


def tint(hex_, amount=0.88):
    """Mix a colour with white (amount = share of white)."""
    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return "#{:02X}{:02X}{:02X}".format(*(round(c + (255 - c) * amount) for c in (r, g, b)))


def card(measure, colour=INK, size=24, bold=True, colour_measure=None, pad=(0, 0, 2, 2), wrap=False):
    col = by_measure(colour_measure) if colour_measure else solid(colour)
    props = {"color": col, "fontSize": lit(f"{size}D"), "fontFamily": s(FONT), "labelDisplayUnits": lit("1D"),
             "bold": lit("true" if bold else "false")}
    v = {"visualType": "card", "query": {"queryState": {"Values": projections([M(measure, " ")])}},
         "objects": {"labels": [{"properties": props}],
                     "categoryLabels": [{"properties": {"show": lit("false")}}],
                     **({"wordWrap": [{"properties": {"show": lit("true")}}]} if wrap else {})},
         "visualContainerObjects": container(pad=pad), "drillFilterOtherVisuals": True}
    return {"visual": v}


def slicer(entity, prop, group, title, default=None, search=False, filters=None):
    """Dropdown slicer on the navy rail. Its header shows the label and, on hover, the eraser that clears it."""
    v = {"visualType": "slicer", "query": {"queryState": {"Values": projections([C(entity, prop)])}},
         "objects": {"data": [{"properties": {"mode": s("Dropdown")}}],
                     "header": [{"properties": {"show": lit("true"), "text": s(title), "fontColor": solid(RAIL_TEXT),
                                                "fontSize": lit("11D"), "fontFamily": s(FONT), "bold": lit("true"),
                                                "outline": s("None")}}],
                     "items": [{"properties": {"fontColor": solid(DARK), "background": solid(CARD),
                                               "fontSize": lit("11D"), "fontFamily": s(FONT)}}]},
         "visualContainerObjects": {**container(pad=(0, 0, 0, 0)),
                                    "visualHeader": [{"properties": {"show": lit("false")}}]},
         "drillFilterOtherVisuals": True,
         "syncGroup": {"groupName": group, "fieldChanges": True, "filterChanges": True}}
    general = {}
    if default is not None:
        v["objects"]["selection"] = [{"properties": {"singleSelect": lit("true")}}]
        general["filter"] = {"filter": in_filter(entity, prop, default, "x")["filter"]}
    if search:
        general["selfFilterEnabled"] = lit("true")
    if general:
        v["objects"]["general"] = [{"properties": general}]
    out = {"visual": v}
    if filters:
        out["filterConfig"] = {"filters": filters}
    return out


def navigator():
    state = lambda sid, props: {"properties": props, "selector": {"id": sid}}
    return {"visual": {"visualType": "pageNavigator", "drillFilterOtherVisuals": True,
            "objects": {
                "layout": [{"properties": {"orientation": lit("1D"), "cellPadding": lit("3L")}}],
                "pages": [{"properties": {"showHiddenPages": lit("false"), "showTooltipPages": lit("false")}}],
                "shape": [{"properties": {"tileShape": s("rectangleRounded"), "rectangleRoundedCurve": lit("6L")}}],
                "fill": [state("default", {"show": lit("true"), "fillColor": solid(NAVY), "transparency": lit("100D")}),
                         state("hover", {"fillColor": solid("#16306B"), "transparency": lit("0D")}),
                         state("selected", {"fillColor": solid("#1E3F8A"), "transparency": lit("0D")})],
                "text": [state("default", {"fontColor": solid("#C9D6F5"), "fontSize": lit("12D"), "fontFamily": s(FONT),
                                           "horizontalAlignment": s("left"), "leftMargin": lit("14D")}),
                         state("selected", {"fontColor": solid(CARD), "bold": lit("true")})],
                "outline": [state(k, {"show": lit("false"), "lineColor": solid(NAVY), "transparency": lit("100D")})
                            for k in ("default", "hover", "selected")],
                "accentBar": [state("default", {"show": lit("false")}),
                              state("selected", {"show": lit("true"), "position": s("Left"), "width": lit("4D"),
                                                 "accentBarColor": solid(MINT)})],
            },
            "visualContainerObjects": {"background": [{"properties": {"show": lit("false")}}],
                                       "visualHeader": [{"properties": {"show": lit("false")}}]}}}


class Page:
    def __init__(self, name, display, width=1280, height=720, kind=None):
        self.name, self.display, self.visuals = name, display, []
        self.no_filter = []
        self.width, self.height, self.kind = width, height, kind

    def add(self, vid, x, y, w, h, item):
        n = len(self.visuals)
        self.visuals.append({"$schema": S_VISUAL, "name": vid,
                             "position": {"x": x, "y": y, "z": n * 1000, "height": h, "width": w, "tabOrder": n * 1000},
                             **item})

    def tile(self, vid, x, y, w, h, item, stripe=COBALT, icon=None, label=None, accent=None, panel=False):
        """A white rounded card with a thin coloured stripe along its top. With a visual, the visual itself is the
        card (its own background, border and shadow); without one, a plain card shape is added for what follows."""
        if item:
            vco = item["visual"]["visualContainerObjects"]
            look = (dict(background=PANEL, radius=10, border=LINE, shadow=True) if panel else
                    dict(background=CARD_D, radius=10, border=LINE, shadow=True))
            vco.update({k: v for k, v in container(**look).items() if k in ("background", "border", "dropShadow")})
            pad = vco["padding"][0]["properties"]
            pad["top"] = lit(f"{max(int(pad['top']['expr']['Literal']['Value'][:-1]), 14)}D")
            self.add(vid, x, y, w, h, item)
        else:
            self.add(vid, x, y, w, h, shape(PANEL, radius=10, border=LINE, shadow=True) if panel else
                     shape(CARD_D, radius=10, border=LINE, shadow=True))
        pass                                                  # no stripe: plain white cards
        if icon:
            self.add(vid + "Icon", x + 14, y + 16, 30, 30, textbox(
                [(icon, 13 if len(icon) == 1 else 11, True, accent)], align="center", pad=(2, 0, 0, 0),
                background=tint(accent), radius=7, border=accent))
            self.add(vid + "Label", x + 50, y + 18, w - 56, 30, textbox([(label, 10.5, False, INK_2)]))

    def json(self):
        page = {"$schema": S_PAGE, "name": self.name, "displayName": self.display, "displayOption": "FitToPage",
                "height": self.height, "width": self.width,
                "objects": {"background": [{"properties": {"color": solid(PAPER), "transparency": lit("0D"),
                                                           "image": {"image": {
                                                               "name": s("page_bg.png"),
                                                               "url": {"expr": {"ResourcePackageItem": {
                                                                   "PackageName": "RegisteredResources", "PackageType": 1,
                                                                   "ItemName": "page_bg.png"}}},
                                                               "scaling": s("Fit")}}}}],
                            "outspace": [{"properties": {"color": solid(PAPER)}}]}}
        if self.no_filter:
            page["visualInteractions"] = [{"source": a, "target": b, "type": "NoFilter"} for a, b in self.no_filter]
        if self.kind == "Tooltip":
            page.update({"displayOption": "ActualSize", "visibility": "HiddenInViewMode", "type": "Tooltip",
                         "pageBinding": {"name": f"{self.name}Binding", "type": "Tooltip", "parameters": []}})
            page["objects"] = {"background": [{"properties": {"color": solid(PANEL), "transparency": lit("0D")}}]}
        return page


RAIL_X = 1064
X0, W = 24, 1016            # content area (x 24 to 1040)
GAP = 12
KPI_Y, KPI_H = 78, 104
R1, RH = 194, 244
R2 = R1 + RH + GAP
BOTTOM = 706


def clear_button():
    lit_s = s
    return {"visual": {"visualType": "actionButton", "drillFilterOtherVisuals": True,
            "objects": {
                "icon": [{"properties": {"shapeType": lit_s("clearAllSlicers"), "lineColor": solid(MINT),
                                         "lineWeight": lit("2L")}, "selector": {"id": "default"}},
                         {"properties": {"show": lit("true")}}],
                "text": [{"properties": {"show": lit("true")}},
                         {"properties": {"text": lit_s("Clear all filters"), "fontColor": solid(MINT), "fontSize": lit("11D"),
                                         "fontFamily": lit_s(FONT), "bold": lit("true")}, "selector": {"id": "default"}}],
                "outline": [{"properties": {"show": lit("true"), "lineColor": solid(MINT), "transparency": lit("40D"),
                                            "roundEdge": lit("8L")}, "selector": {"id": "default"}}],
                "fill": [{"properties": {"show": lit("true"), "fillColor": solid("#16306B"), "transparency": lit("0D")},
                          "selector": {"id": "default"}},
                         {"properties": {"fillColor": solid("#1E3F8A")}, "selector": {"id": "hover"}}]},
            "visualContainerObjects": {
                "visualLink": [{"properties": {"show": lit("true"), "type": lit_s("ClearAllSlicers"),
                                               "tooltipPlaceholderText": lit_s("Clear every filter on this page")}}],
                "background": [{"properties": {"show": lit("false")}}],
                "visualHeader": [{"properties": {"show": lit("false")}}]}}}


TITLE = "U.S. Hospital EHR Interoperability Scorecard 2019-2024"
BANNER_H = 64


def rail(page, filters="all"):
    """Navy rail on the right, under the banner: page links, filters with a clear button, data credit.
    (The rail panel itself is in the page image; it is full height, so the image stretch does not matter.)"""
    def heading(vid, y, text):
        page.add(vid, RAIL_X + 12, y, 196, 20, textbox([(text, 9.5, True, RAIL_MUTED)]))

    heading("lPages", BANNER_H + 12, "PAGES")
    page.add("navigator", RAIL_X + 8, BANNER_H + 30, 200, 186, navigator())
    if filters == "all":
        heading("lFilters", 288, "FILTERS")
        for k, (vid, text, item) in enumerate([
                ("fType", "Hospital type", slicer("hospital", "hospital_type", "type", "Hospital type")),
                ("fOwner", "Owner", slicer("hospital", "ownership", "owner", "Owner")),
                ("fArea", "Rural or urban", slicer("hospital", "rural_urban", "area", "Rural or urban")),
                ("fState", "State", slicer("states", "state_name", "state", "State", search=True)),
                ("fEhr", "EHR company", slicer("hospital", "ehr_group", "ehr", "EHR company"))]):
            page.add(vid, RAIL_X + 14, 306 + 61 * k, 188, 60, item)      # 60 tall: the dropdown box is drawn low in its frame
        page.add("clearAll", RAIL_X + 14, 616, 188, 26, clear_button())
    if filters == "hospital":
        heading("lLookup", 288, "LOOK UP")
        page.add("search", RAIL_X + 14, 306, 188, 60,
                 slicer("hospital", "hospital_label", "hospital", "Hospital name", default=F["default_hospital"],
                        search=True, filters=[in_filter("hospital", "in_latest", 1, "inLatest")]))
        page.add("searchNote", RAIL_X + 12, 374, 196, 70, textbox(
            [("Open the box and type part of a name, for example Mayo or Memorial.", 10, False, RAIL_TEXT)]))
    page.add("credit", RAIL_X + 12, 660, 204, 56, textbox(
        [(F["rail_caption"].title().replace("·", "·"), 9, False, RAIL_MUTED),
         ("Data: Medicare (CMS) and the ONC certified EHR list", 9, False, RAIL_MUTED)]))


def header(page, finding, sub=None):
    """Title banner across the whole top of the page: logo, report title, page name + its finding, author badge."""
    page.add("banner", 0, 0, 1280, BANNER_H, shape(NAVY))
    page.add("bannerLine", 0, BANNER_H - 3, 1280, 3, shape(MINT))
    page.add("logo", 16, 12, 38, 38, image("logo.png"))
    page.add("reportTitle", 62, 6, 900, 30, textbox([(TITLE, 17, True, CARD)], pad=(0, 0, 4, 4)))
    page.add("pageLine", 62, 34, 980, 24, textbox(
        [[(page.display.upper() + "   ", 9.5, True, MINT), (finding, 10.5, False, "#D6E0F5")]], pad=(0, 0, 4, 4)))
    page.add("badge", 1088, 17, 176, 28, textbox([("Built by Isaac Agyapong", 10, True, NAVY)], align="center",
                                                    background=MINT, radius=14, pad=(4, 0, 4, 4)))


def sparkline(measure, colour):
    """Small trend line by yearly file for a KPI card (no axes, no labels)."""
    return chart("areaChart", {"Category": [C("hospital_year", "snapshot_year")], "Y": [M(measure)]}, pad=(0, 0, 0, 0),
                 objects={**axes(show_cat=False), **labels(show=False), **legend(show=False),
                          "dataPoint": [{"properties": {"fill": solid(colour)}}],
                          "lineStyles": [{"properties": {"strokeWidth": lit("2D"), "lineChartType": s("smooth")}}]})


def text_of(measure):
    """The '<measure> Text' version when it exists (shows '–' instead of '(Blank)')."""
    return measure + " Text" if any(n == measure + " Text" for _, n, *_ in MEASURES) else measure


def kpi(page, i, x, y, w, glyph, label, accent, value, context, value_colour=None, value_measure=None, size=26,
        spark=None):
    page.tile(f"kpiTile{i}", x, y, w, KPI_H, None, stripe=accent, icon=glyph, label=label, accent=accent)
    vw = int(w * 0.5) if spark else w - 24
    page.add(f"kpi{i}", x + 12, y + 44, vw, 38,
             card(text_of(value), colour=value_colour or accent, colour_measure=value_measure, size=size))
    if spark:
        page.add(f"kpiSpark{i}", x + 12 + vw, y + 26, w - vw - 20, 54, sparkline(spark, accent))
    page.add(f"kpiContext{i}", x + 8, y + 78, w - 16, 24, card(context, colour=INK_2, size=11, bold=False))


def kpi_row(page, items, y=KPI_Y):
    w = (W - 3 * GAP) // 4
    for i, item in enumerate(items):
        kpi(page, i, X0 + i * (w + GAP), y, w, *item)


def bars(category, measure, title, subtitle, colour_measure=None, sort_by_value=True, column=False, size=12,
         inner=26, area=36, cat_size=11):
    """Bar (or column) chart of one measure by one category, coloured by a measure, labelled, no value axis."""
    obj = {**axes(inner_padding=inner, label_area=None if column else area, cat_size=cat_size, categorical=column),
           **labels(size)}
    if colour_measure:
        obj["dataPoint"] = fill_by(colour_measure)
    sort = (M(measure), "Descending") if sort_by_value else (C(category[0], category[1]), "Ascending")
    return chart("clusteredColumnChart" if column else "clusteredBarChart",
                 {"Category": [C(*category)], "Y": [M(measure)]}, title, subtitle, sort=sort, objects=obj)


def hero(page):
    """Dark banner: question, plain-language headline from the data, three glass stat tiles and the 100-dot grid."""
    hx, hy, hw, hh = X0, 14, W, 246
    page.add("hero", hx, hy, hw, hh, shape(PANEL, radius=12, border=LINE, shadow=True))
    page.add("heroKicker", hx + 22, hy + 14, 640, 22, textbox(
        [("MEDICARE PROMOTING INTEROPERABILITY PROGRAM  ·  2024 REPORTING YEAR", 10, True, MINT)]))
    page.add("heroTitle", hx + 22, hy + 34, 650, 40, textbox([("Can U.S. hospitals share health records electronically?", 19, True, CARD)]))
    page.add("heroSub", hx + 22, hy + 74, 640, 44, textbox(
        [("Medicare checks every year if hospitals use a certified electronic health record (EHR) to share records, "
          "e-prescribe and give patients online access. Falling short cuts their Medicare pay.", 11, False, "#C9D6F5")]))
    page.add("heroLine", hx + 18, hy + 122, 650, 36, card("Hero Line", colour=MINT, size=14))
    tw = 200
    for k, (measure, label, colour) in enumerate([
            ("Hero Hospitals", "hospitals checked in 2024", CARD),
            ("Hero Short", "fell short of the standards", DOT_RED),
            ("Hero No EHR", "of them had no certified EHR", DOT_PURPLE)]):
        x = hx + 22 + k * (tw + 12)
        page.add(f"glass{k}", x, hy + 172, tw, 62, textbox([], background=CARD, radius=8, border="#3A5596",
                                                          pad=(0, 0, 0, 0), transparency=90))
        page.add(f"glassValue{k}", x + 10, hy + 174, tw - 20, 32, card(measure, colour=colour, size=21))
        page.add(f"glassLabel{k}", x + 10, hy + 206, tw - 20, 24, textbox([(label, 10.5, False, "#C9D6F5")], align="center"))
    # 100-dot grid: one dot per 1 in 100 hospitals shown, coloured by result
    every_cell = {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": "hospital.Dot"}
    hidden = {"fontColor": solid(PANEL), "backColor": solid(PANEL), "fontSize": lit("6D"), "outline": s("None")}
    grid = {"visualType": "pivotTable",
            "query": {"queryState": {"Rows": projections([C("Dots", "row")]), "Columns": projections([C("Dots", "col")]),
                                     "Values": projections([M("Dot", " ")])}},
            "objects": {
                "values": [{"properties": {"fontSize": lit("9D"), "fontFamily": s("Segoe UI Symbol"),
                                           "backColorPrimary": solid(PANEL), "backColorSecondary": solid(PANEL)}},
                           {"properties": {"fontColor": by_measure("Dot Colour")}, "selector": every_cell}],
                "columnHeaders": [{"properties": hidden}], "rowHeaders": [{"properties": hidden}],
                "subTotals": [{"properties": {"rowSubtotals": lit("false"), "columnSubtotals": lit("false")}}],
                "grid": [{"properties": {"gridVertical": lit("false"), "gridHorizontal": lit("false"),
                                         "outlineColor": solid(PANEL), "rowPadding": lit("0D")}}]},
            "visualContainerObjects": {**container(pad=(0, 0, 0, 0)),
                                       "visualHeader": [{"properties": {"show": lit("false")}}]},
            "drillFilterOtherVisuals": True}
    page.add("dotGrid", hx + 664, hy + 12, 228, 228, {"visual": grid})
    page.add("dotLegend", hx + 884, hy + 28, 128, 206, textbox([
        [("● ", 13, False, DOT_BLUE), ("met the standards", 10.5, False, "#E8EEFB")],
        [("● ", 13, False, DOT_RED), ("fell short", 10.5, False, "#E8EEFB")],
        [("● ", 13, False, DOT_PURPLE), ("fell short, no certified EHR", 10.5, False, "#E8EEFB")],
        ("", 6, False, PANEL),
        ("Each dot is 1 in every 100 hospitals shown. The filters on the right change it.", 9.5, False, RAIL_MUTED)]))


def donut(category, measure, colours, label_style="Percent of total", size=11, inner=58):
    return chart("donutChart", {"Category": [C(*category)], "Y": [M(measure)]}, pad=(0, 0, 0, 0), objects={
        "labels": [{"properties": {"show": lit("true"), "labelStyle": s(label_style), "color": solid(INK),
                                   "fontSize": lit(f"{size}D"), "fontFamily": s(FONT), "bold": lit("true"),
                                   "percentageLabelPrecision": lit("0L")}}],
        **legend(show=False), "slices": [{"properties": {"innerRadiusRatio": lit(f"{inner}L")}}],
        "dataPoint": fill_by_value(category[0], category[1], colours)})


def treemap(category, measure, title, subtitle, colours):
    return chart("treemap", {"Group": [C(*category)], "Values": [M(measure)]}, title, subtitle, objects={
        "labels": [{"properties": {"show": lit("true"), "color": solid("#FFFFFF"), "fontSize": lit("12D"), "fontFamily": s(FONT),
                                   "bold": lit("true"), "labelDisplayUnits": lit("1D")}}],
        "categoryLabels": [{"properties": {"show": lit("true"), "color": solid("#FFFFFF"), "fontSize": lit("11D"),
                                           "fontFamily": s(FONT)}}],
        **legend(show=False), "dataPoint": fill_by_value(category[0], category[1], colours)})


def gauge(value, target, colour):
    return chart("gauge", {"Y": [M(value)], "MinValue": [M("Gauge Min")], "MaxValue": [M("Gauge Max")],
                           "TargetValue": [M(target)]}, pad=(0, 0, 0, 0), objects={
        "dataPoint": [{"properties": {"fill": solid(colour), "target": solid(INK)}}],
        "calloutValue": [{"properties": {"color": solid(colour), "fontSize": lit("26D"), "fontFamily": s(FONT),
                                         "labelPrecision": lit("0L")}}],
        "labels": [{"properties": {"show": lit("false")}}],
        "target": [{"properties": {"show": lit("false")}}]})


def big_number(page, vid, x, y, w, measure, colour, text, size=30):
    page.add(vid, x, y, w, 46, card(measure, colour=colour, size=size))
    page.add(vid + "Txt", x, y + 46, w, 44, textbox([(text, 11, False, INK_2)], align="center"))


def build_pages():
    half = (W - GAP) // 2
    third = (W - 2 * GAP) // 3

    # ---------------------------------------------------------------- 1. Overview
    p1 = Page("overview", "Overview")
    rail(p1)
    header(p1, "Can U.S. hospitals share health records electronically?",
           "Medicare's yearly check of certified electronic health records (EHRs): sharing records, e-prescribing, "
           "patient online access. 2024 reporting year.")
    kpi_row(p1, [
        ("✕", "Fell short of the standards", RED, "Short Share", "Short 2019 Context", None, None, 30, "Year Share"),
        ("∅", "Of those: no certified EHR", PURPLE, "No EHR Pct", "No EHR Context", None, None, 30),
        ("▲", "Small rural: fell short", TEAL, "Rural Short", "Rural Context", None, None, 30, "Rural Year Share"),
        ("◆", "Top 3 EHR companies", SKY, "Top3 Share", "Top3 Context", None, None, 30),
    ])
    rah = 262
    rb = R1 + rah + GAP
    rbh = BOTTOM - rb
    tw_ = 604
    p1.tile("trend", X0, R1, tw_, rah, chart(
        "clusteredColumnChart", {"Category": [C("hospital_year", "snapshot_year", "Yearly file")],
                                 "Series": [C("hospital_year", "year_type", "Hospital type")],
                                 "Y": [M("Year Share", "Share falling short")]},
        "=Trend Title", "Share falling short in each yearly Medicare file. Teal = small rural, grey = general hospitals.",
        objects={**axes(categorical=True, cat_size=11, inner_padding=24), **labels(10), **legend(show=False),
                 "dataPoint": fill_by_value("hospital_year", "year_type", {RURAL: TEAL, GENERAL: SLATE})}))
    gx, gw = X0 + tw_ + GAP, W - tw_ - GAP
    p1.tile("every100", gx, R1, gw, rah, None)
    p1.add("e100Title", gx + 14, R1 + 10, gw - 28, 26, textbox([("In every 100 hospitals in 2024", 13, True, INK)]))
    for k, (measure, colour, text) in enumerate([
            ("Dots Met", COBALT, "met the standards"),
            ("Dots No EHR", PURPLE, "fell short with no certified EHR"),
            ("Dots Short", RED, "fell short with a certified EHR")]):
        y = R1 + 48 + k * 68
        p1.add(f"e100Num{k}", gx + 14, y, 88, 52, card(measure, colour=colour, size=30))
        p1.add(f"e100Txt{k}", gx + 106, y + 12, gw - 120, 40, textbox([(text, 11.5, False, INK)]))
    # row B: donut pair, treemap, columns
    p1.tile("pair", X0, rb, third, rbh, None, stripe=TEAL)
    p1.add("pairTitle", X0 + 8, rb + 10, third - 16, 44, card("Pair Title", colour=INK, size=12))
    for k, (measure, lab) in enumerate([("Type Hospitals", "All hospitals"), ("Type Short", "Fell short")]):
        x = X0 + 6 + k * (third - 12) // 2
        p1.add(f"pairLabel{k}", x, rb + 54, (third - 12) // 2, 22, textbox([(lab, 11, True, INK_2)], align="center"))
        p1.add(f"pairDonut{k}", x, rb + 74, (third - 12) // 2, rbh - 104, donut(
            ("hospital", "hospital_type", "Hospital type"), measure, {RURAL: TEAL, GENERAL: SLATE}))
    p1.add("pairKey", X0 + 6, rb + rbh - 30, third - 12, 24, textbox(
        [[("● ", 12, False, TEAL), ("small rural   ", 10.5, False, INK_2), ("● ", 12, False, SLATE), ("general", 10.5, False, INK_2)]],
        align="center"))
    p1.tile("owner", X0 + third + GAP, rb, third, rbh, bars(
        ("hospital", "ownership", "Owner"), "Owner Short", "=Owner Title", "Share falling short, by owner (50+ hospitals)",
        colour_measure="Owner Colour", area=34, inner=30, cat_size=10))
    p1.tile("size", X0 + 2 * (third + GAP), rb, W - 2 * (third + GAP), rbh, bars(
        ("hospital", "size_band", "Beds"), "Size Short", "=Size Title", "Share falling short, by number of beds",
        colour_measure="Size Colour", sort_by_value=False, column=True, inner=26, cat_size=10), stripe=RED)

    # ---------------------------------------------------------------- 2. EHR companies
    p2 = Page("ehr", "EHR Companies")
    rail(p2)
    header(p2, "The EHR company matters, even for the same kind of hospital",
           "I looked up each hospital's certified EHR ID in the federal product list to find the company behind it.")
    kpi_row(p2, [
        ("◆", "Top 3 companies' share", SKY, "Top3 Share", "Top3 Context"),
        ("✓", "Epic: fell short", RED, "Epic Short", "Epic Context"),
        ("✕", "TruBridge: fell short", RED, "TruBridge Short", "TruBridge Context"),
        ("∅", "No certified EHR", PURPLE, "No EHR Hospitals", "No EHR All Context"),
    ])
    r1h = 300
    r2 = R1 + r1h + GAP
    mw = 540
    p2.tile("market", X0, R1, mw, r1h, treemap(
        ("hospital", "main_developer", "EHR company"), "Market Count", "=Market Title",
        "Hospitals by the company behind their main EHR. Bigger block = more hospitals.",
        {TOP3[0]: "#1F4E9E", TOP3[1]: "#4F86D9", TOP3[2]: "#9DB4E0", "TruBridge (CPSI)": "#E08A3C", "MEDHOST": "#C9D1DE",
         "Altera (Allscripts)": "#B8C1CF", "Other EHR vendor": "#A3AEBF"}), stripe=SKY)
    p2.tile("ehrTable", X0 + mw + GAP, R1, W - mw - GAP, r1h, chart(
        "tableEx", {"Values": [C("hospital", "ehr_group", "EHR company"), M("EHR Hospitals", "Hospitals"),
                               M("EHR Short Count", "Fell short"), M("EHR Short", "Share")]},
        "=EHR Title", None, sort=(M("EHR Short"), "Descending"),
        objects={"values": [{"properties": {"fontSize": lit("11D"), "fontFamily": s(FONT), "fontColor": solid(INK),
                                            "backColorPrimary": solid(PANEL), "backColorSecondary": solid(PANEL_2)}}],
                 "columnHeaders": [{"properties": {"fontSize": lit("11D"), "fontFamily": s(FONT), "bold": lit("true"),
                                                   "fontColor": solid(INK_2), "backColor": solid(PANEL)}}],
                 "grid": [{"properties": {"rowPadding": lit("1D"), "gridHorizontalColor": solid(LINE),
                                          "gridVerticalColor": solid(PANEL), "outlineColor": solid(LINE)}}],
                 "total": [{"properties": {"totals": lit("false")}}],
                 "columnFormatting": [{"properties": {"dataBars": {"positiveColor": solid(RED), "negativeColor": solid(RED),
                                                                   "axisColor": solid(PANEL), "reverseDirection": lit("false"),
                                                                   "hideText": lit("false")}},
                                       "selector": {"metadata": "hospital.EHR Short"}}],
                 "columnWidth": [{"properties": {"value": lit(f"{w}D")}, "selector": {"metadata": k}} for k, w in {
                     "hospital.ehr_group": 140, "hospital.EHR Hospitals": 76, "hospital.EHR Short Count": 84,
                     "hospital.EHR Short": 88}.items()]}), stripe=RED, panel=True)
    gwid = 660
    p2.tile("gauges", X0, r2, gwid, BOTTOM - r2, None, stripe=TEAL)
    p2.add("gaugeTitle", X0 + 12, r2 + 10, gwid - 24, 26, card("Matrix Title", colour=INK, size=14))
    p2.add("gaugeSub", X0 + 12, r2 + 36, gwid - 24, 22, textbox(
        [("Small rural hospitals falling short, by EHR company. Black mark = all small rural hospitals.", 11, False, INK_2)]))
    gw3 = (gwid - 24) // 3
    for k, (m, name, colour) in enumerate([("Rural TruBridge", "TruBridge", RED), ("Rural MEDITECH", "MEDITECH", AMBER),
                                           ("Rural Epic", "Epic", SKY)]):
        x = X0 + 12 + k * gw3
        p2.add(f"gauge{k}", x, r2 + 58, gw3, BOTTOM - r2 - 92, gauge(m, "Rural Short", colour))
        p2.add(f"gaugeName{k}", x, BOTTOM - 34, gw3, 24, textbox([(name, 12, True, colour)], align="center"))
    ex = X0 + gwid + GAP
    p2.tile("meaning", ex, r2, W - gwid - GAP, BOTTOM - r2, textbox([
        ("What this means", 14, True, INK),
        ("Hospitals on Epic, Oracle Health or MEDITECH almost never fall short.", 12, False, INK),
        ("TruBridge hospitals fall short far more often, even next to the same kind of hospital.", 12, False, INK),
        ("A link, not proof of cause: small budgets and few IT staff often come with cheaper systems.", 11, False, INK_2)],
        pad=(12, 6, 14, 14)), stripe=SKY)

    # ---------------------------------------------------------------- 3. Money and history
    p3 = Page("money", "Money and History")
    rail(p3)
    header(p3, "Hospitals short of money fall behind, and some never catch up",
           "Profit comes from each hospital's yearly cost report to Medicare. History covers the six yearly files, 2019-2024.")
    kpi_row(p3, [
        ("$", "Least profitable fifth", RED, "Least Profitable Short", "Least Profitable Context"),
        ("↘", "After 2 years of losses", RED, "Losses Short", "Losses Context"),
        ("⟳", "Fell short every year", RED, "Every Year", "Every Year Context"),
        ("✓", "Never fell short", COBALT, "Never", "Never Context"),
    ])
    p3.tile("fifths", X0, R1, half, RH, chart(
        "areaChart", {"Category": [C("hospital", "margin_fifth_label", "Profit")], "Y": [M("Fifth Short", "Share falling short")]},
        "=Fifth Title", "Hospitals in five equal groups, from least to most profitable (cents kept from each $1)",
        sort=(C("hospital", "margin_fifth_label"), "Ascending"),
        objects={**axes(show_value=False, categorical=True, cat_size=11), **labels(13), **legend(show=False),
                 "dataPoint": [{"properties": {"fill": solid(RED)}}],
                 "lineStyles": [{"properties": {"strokeWidth": lit("3D"), "showMarker": lit("true"), "markerSize": lit("7D"),
                                                "lineChartType": s("smooth")}}]}), stripe=RED)
    rx, rw = X0 + half + GAP, W - half - GAP
    p3.tile("rings", rx, R1, rw, RH, None, stripe=RED)
    p3.add("ringsTitle", rx + 12, R1 + 10, rw - 24, 44, card("Money Title", colour=INK, size=13))
    for k, (m, lab) in enumerate([("Ring Lost", "Lost money 2 years in a row"), ("Ring Not", "Did not lose money 2 years")]):
        x = rx + 8 + k * (rw - 16) // 2
        p3.add(f"ring{k}", x, R1 + 56, (rw - 16) // 2, RH - 92, donut(
            ("Result", "result", "Result"), m, {"Fell short": RED, "Met the standards": "#3B4F86"}, inner=62))
        p3.add(f"ringLab{k}", x, R1 + RH - 34, (rw - 16) // 2, 24, textbox([(lab, 11, True, INK_2)], align="center"))
    p3.tile("history", X0, R2, W, BOTTOM - R2, bars(
        ("hospital", "history", "Years falling short"), "History Count", "=History Title",
        "Hospitals in all six yearly Medicare files (2019-2024), by how many of those years they fell short",
        colour_measure="History Colour", sort_by_value=False, column=True, inner=34), stripe=RED)

    # ---------------------------------------------------------------- 4. States
    p4 = Page("states", "States")
    rail(p4)
    header(p4, "Where hospitals fall short",
           "Share of hospitals in each state that did not meet the standards in 2024. Hover over a state for details.")
    every_cell = {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": "hospital.Tile Label"}
    hidden_header = {"fontColor": solid(PANEL), "backColor": solid(PANEL), "fontSize": lit("6D")}
    tile_map = chart(
        "pivotTable", {"Rows": [C("states", "tile_y")], "Columns": [C("states", "tile_x")], "Values": [M("Tile Label", " ")]},
        "=Map Title", "Darker red = a bigger share of hospitals falling short", tooltip_page="stateTooltip",
        filters=[in_filter("states", "on_map", 1, "onMap")],
        objects={
            "values": [{"properties": {"fontSize": lit("13D"), "bold": lit("true"), "fontFamily": s(FONT),
                                       "backColorPrimary": solid(PANEL), "backColorSecondary": solid(PANEL)}},
                       {"properties": {"backColor": by_measure("Tile Colour"), "fontColor": by_measure("Tile Font")},
                        "selector": every_cell}],
            "columnHeaders": [{"properties": hidden_header}], "rowHeaders": [{"properties": hidden_header}],
            "subTotals": [{"properties": {"rowSubtotals": lit("false"), "columnSubtotals": lit("false")}}],
            "grid": [{"properties": {"gridVertical": lit("true"), "gridVerticalColor": solid(PANEL),
                                     "gridVerticalWeight": lit("4D"), "gridHorizontal": lit("true"),
                                     "gridHorizontalColor": solid(PANEL), "gridHorizontalWeight": lit("4D"),
                                     "outlineColor": solid(PANEL), "rowPadding": lit("10D")}}]})
    mapw = 600
    p4.tile("tileMap", X0, KPI_Y, mapw, BOTTOM - KPI_Y, tile_map, stripe=RED, panel=True)
    leg = [("Falling short   ", 10.5, True, INK_2)]
    for colr, lab in [("#FDF0EA", "under 5%"), ("#F9CDBB", "5-10%"), ("#F29A78", "10-15%"), (RED, "15-25%"), (RED_D, "25%+")]:
        leg += [("■ ", 14, False, colr), (lab + "   ", 10.5, False, INK_2)]
    p4.add("mapLegend", X0 + 16, BOTTOM - 40, mapw - 32, 30, textbox([leg]))
    p4.no_filter += [("tileMap", "top10"), ("tileMap", "kpiFifth"), ("tileMap", "kpiZero")]
    tx, tw = X0 + mapw + GAP, W - mapw - GAP
    th = 440
    p4.tile("top10", tx, KPI_Y, tw, th, chart(
        "tableEx", {"Values": [C("states", "state_name", "State"), M("Top 10 Hospitals", "Hospitals"),
                               M("Top 10 Short", "Fell short"), M("Top 10 Share", "Share")]},
        "The 10 states with the biggest share falling short", "States with 10 or more hospitals in the selection",
        tooltip_page="stateTooltip", sort=(M("Top 10 Share"), "Descending"),
        objects={"values": [{"properties": {"fontSize": lit("11D"), "fontFamily": s(FONT), "fontColor": solid(INK),
                                            "backColorPrimary": solid(PANEL), "backColorSecondary": solid(PANEL_2)}}],
                 "columnHeaders": [{"properties": {"fontSize": lit("11D"), "fontFamily": s(FONT), "bold": lit("true"),
                                                   "fontColor": solid(INK_2), "backColor": solid(PANEL)}}],
                 "grid": [{"properties": {"rowPadding": lit("3D"), "gridHorizontalColor": solid(LINE),
                                          "gridVerticalColor": solid(PANEL), "outlineColor": solid(LINE)}}],
                 "total": [{"properties": {"totals": lit("false")}}],
                 "columnFormatting": [{"properties": {"dataBars": {"positiveColor": solid(RED_L), "negativeColor": solid(RED_L),
                                                                   "axisColor": solid(PANEL), "reverseDirection": lit("false"),
                                                                   "hideText": lit("false")}},
                                       "selector": {"metadata": "hospital.Top 10 Share"}}],
                 "columnWidth": [{"properties": {"value": lit(f"{w}D")}, "selector": {"metadata": k}} for k, w in {
                     "states.state_name": 100, "hospital.Top 10 Hospitals": 80, "hospital.Top 10 Short": 74,
                     "hospital.Top 10 Share": 86}.items()]}), stripe=RED, panel=True)
    ky = KPI_Y + th + GAP
    kw = (tw - GAP) // 2
    kh = BOTTOM - ky
    for vid, x, glyph, label, accent, value, ctx in [
            ("kpiFifth", tx, "✕", "1 in 5+ fell short", RED, "Fifth States", "states and territories with 10+ hospitals"),
            ("kpiZero", tx + kw + GAP, "✓", "None fell short", COBALT, "Zero States", "states and territories with 10+ hospitals")]:
        p4.tile(vid + "Tile", x, ky, kw, kh, None, stripe=accent, icon=glyph, label=label, accent=accent)
        p4.add(vid, x + 12, ky + 54, kw - 24, 50, card(value, colour=accent, size=30))
        p4.add(vid + "Ctx", x + 12, ky + 106, kw - 24, 44, textbox([(ctx, 11, False, INK_2)]))

    # ---------------------------------------------------------------- 5. Find a hospital
    p5 = Page("lookup", "Find a Hospital")
    rail(p5, filters="hospital")
    header(p5, "Find a hospital",
           "Did it meet Medicare's standards for sharing records, which EHR does it use, and how has it done since 2019?")
    p5.add("namePanel", X0, KPI_Y, W, 72, shape(NAVY, radius=10, shadow=True))     # dark panel for the key result
    p5.add("nameTitle", X0 + 16, KPI_Y + 8, W - 32, 36, card("Profile Name", colour=CARD, size=20))
    p5.add("nameFacts", X0 + 16, KPI_Y + 42, W - 32, 24, card("Profile Facts", colour="#C9D6F5", size=11, bold=False))
    ky = KPI_Y + 72 + GAP
    w4 = (W - 3 * GAP) // 4
    for i, (glyph, label, accent, value, ctx, vcol) in enumerate([
            ("◉", "Status in 2024", COBALT, "Profile Status", "Profile Status Context", "Profile Status Colour"),
            ("▣", "Main EHR company", SKY, "Profile EHR", "Profile EHR Context", "Profile EHR Colour"),
            ("⟳", "Years it fell short", RED, "Profile Years", "Profile Years Context", "Profile Years Colour"),
            ("$", "Profit, latest report", GREY_D, "Profile Margin", "Profile Margin Context", "Profile Margin Colour")]):
        kpi(p5, i, X0 + i * (w4 + GAP), ky, w4, glyph, label, accent, value, ctx, value_measure=vcol, size=17)
    ry = ky + KPI_H + GAP
    rh = BOTTOM - ry
    sw = 520
    p5.tile("strip", X0, ry, sw, rh, chart(
        "clusteredColumnChart", {"Category": [C("hospital_year", "snapshot_year", "Yearly file")], "Y": [M("Strip Value", "Record")]},
        "Its record in each yearly Medicare file", "Blue = met the standards, red = fell short",
        sort=(C("hospital_year", "snapshot_year"), "Ascending"),
        objects={**axes(inner_padding=18, categorical=True, cat_size=12), **labels(show=False),
                 "dataPoint": fill_by("Strip Colour")}))
    mx = X0 + sw + GAP
    mw2 = W - sw - GAP
    p5.tile("meaning", mx, ry, mw2, rh, None, stripe=SKY)
    p5.add("meaningTitle", mx + 14, ry + 14, mw2 - 28, 28, textbox([("What this means", 14, True, INK)]))
    p5.add("meaningText", mx + 10, ry + 44, mw2 - 20, 124, card("Profile Sentence", colour=INK, size=12, bold=False, wrap=True))
    p5.add("checksTitle", mx + 14, ry + 172, mw2 - 28, 26, textbox([("Data checks for this hospital", 12, True, AMBER)]))
    p5.add("checksText", mx + 10, ry + 198, mw2 - 20, 70, card("Profile Checks", colour=INK_2, size=11.5, bold=False, wrap=True))

    # ---------------------------------------------------------------- 6. Data quality
    p6 = Page("quality", "Data Quality")
    rail(p6)
    header(p6, "Can we trust the data? Mostly, with problems worth fixing",
           "Checked the way EHR data-quality research does: filled in, right format, consistent across files, linked to other data.")
    kpi_row(p6, [
        ("?", "'Not Available' as the ID", AMBER, "Not Available Count", "Not Available Context", PURPLE),
        ("⚠", "Unknown EHR IDs", AMBER, "Not In List Count", "Not In List Context"),
        ("Aa", "Badly formatted EHR IDs", AMBER, "Bad Format Count", "Bad Format Context"),
        ("≠", "Two Medicare files disagree", AMBER, "Disagree Count", "Disagree Context"),
    ])
    p6.tile("idQuality", X0, R1, half, RH, None, stripe=AMBER)
    p6.add("idTitle", X0 + 12, R1 + 10, half - 24, 26, card("ID Title", colour=INK, size=14))
    p6.add("idSub", X0 + 12, R1 + 36, half - 24, 22, textbox([("What hospitals put in the EHR ID field of the 2024 file", 11, False, INK_2)]))
    p6.add("idDonut", X0 + 8, R1 + 60, 250, RH - 70, donut(
        ("hospital", "id_quality", "EHR ID field"), "ID Count",
        {"Valid ID, found in the federal list": "#3B4F86", '"Not Available" typed instead of an ID': PURPLE,
         "Not found in the federal list": AMBER, "Wrong format (lowercase or wrong length)": "#E9C46A"},
        label_style="Data value", size=12))
    p6.visuals[-1]["visual"]["objects"]["labels"][0]["properties"]["show"] = lit("false")
    p6.add("idKey", X0 + 262, R1 + 74, half - 274, 150, textbox([
        [("● ", 13, False, "#3B4F86"), (f"{F['n'] - F['not_available'] - F['not_in_list'] - F['bad_format']:,}  valid ID found in the federal list", 11, False, INK)],
        [("● ", 13, False, PURPLE), (f"{F['not_available']:,}  typed \"Not Available\"", 11, False, INK)],
        [("● ", 13, False, AMBER), (f"{F['not_in_list']:,}  ID not in the federal list", 11, False, INK)],
        [("● ", 13, False, "#E9C46A"), (f"{F['bad_format']:,}  lowercase or wrong length", 11, False, INK)]]))
    dx_, dw_ = X0 + half + GAP, W - half - GAP
    p6.tile("disagree", dx_, R1, dw_, RH, None, stripe=AMBER)
    p6.add("disTitle", dx_ + 12, R1 + 10, dw_ - 24, 26, card("Disagree Title", colour=INK, size=14))
    p6.add("disSub", dx_ + 12, R1 + 36, dw_ - 24, 40, textbox(
        [("The October 2024 hospital file and the latest dedicated file cover different reporting years.", 11, False, INK_2)]))
    bw = (dw_ - 36) // 2
    big_number(p6, "disUp", dx_ + 12, R1 + 96, bw, "Disagree Up", AMBER, "fell short in the October 2024 file, met in the latest")
    big_number(p6, "disDown", dx_ + 24 + bw, R1 + 96, bw, "Disagree Down", RED, "met in the October 2024 file, fell short in the latest")
    p6.tile("files", X0, R2, half, BOTTOM - R2, bars(
        ("hospital", "n_files", "Yearly files"), "Files Count", "=Files Title",
        "Hospitals by how many of the six yearly Medicare files (2019-2024) they appear in",
        colour_measure="Files Colour", sort_by_value=False, column=True, inner=30), stripe=AMBER)
    p6.tile("checks", X0 + half + GAP, R2, W - half - GAP, BOTTOM - R2, textbox([
        ("How I checked the data", 14, True, INK),
        [("✓  ", 12, True, MINT), ("No hospital appears twice in the same file", 12, False, INK)],
        [("✓  ", 12, True, MINT), ("Hospital types outside the program are never marked as meeting the standards", 12, False, INK)],
        [("✓  ", 12, True, MINT), ("Every hospital in the latest file reports the same period (calendar year 2024)", 12, False, INK)],
        [("✓  ", 12, True, MINT), (f"{F['finance_match']:.0%} of hospitals link to their yearly financial report", 12, False, INK)],
        [("!  ", 12, True, AMBER), (f"Hospitals with no financial report fall short far more often ({F['no_finance_short']:.0%} vs "
                                     f"{F['finance_short']:.0%}): missing data is itself a warning sign", 12, False, INK)],
    ], pad=(12, 6, 14, 14)), stripe=MINT)

    # ---------------------------------------------------------------- 7. Data notes
    p7 = Page("dataNotes", "Data Notes")
    rail(p7, filters="none")
    header(p7, "Data notes", "What the words mean, where the data comes from, and what to keep in mind")
    third = (W - 2 * GAP) // 3
    cols = [
        ("Words used here", COBALT, [
            "EHR: electronic health record, the software a hospital keeps patient records in",
            "Interoperability: records that can move safely between hospitals, doctors, labs and patients",
            "Met the standards: met Medicare's Promoting Interoperability program for the year (certified EHR, "
            "sharing records, e-prescribing, patient online access, reporting to public health)",
            "Fell short: did not meet them, which cuts the hospital's Medicare payments",
            "Small rural (critical access) hospital: 25 beds or fewer, far from other hospitals",
            "Certified EHR ID: the code that names the certified software a hospital used"]),
        ("Where the data comes from", SKY, [
            "CMS Hospital General Information, six yearly files 2019-2024 (status of every hospital)",
            "CMS Promoting Interoperability file, latest release (2024 reporting year, with EHR IDs)",
            "ONC Certified Health IT Product List: each EHR ID looked up to find the company behind it",
            "CMS hospital cost reports for profit and size (companion financial project)",
            "Loaded into PostgreSQL; numbers on every page match the SQL results in the repository",
            "Which hospitals will fall short next year: see the companion machine learning project"]),
        ("Keep in mind", AMBER, [
            "Only general and small rural hospitals are in the program; psychiatric, children's, VA and military "
            "hospitals are left out because they are never rated",
            "The yearly files and the latest file cover different reporting years, so a few hospitals differ",
            "Main EHR company = the company with the most certified products in the hospital's EHR setup",
            "Links between money, size, software and falling short are associations, not proof of cause",
            "Puerto Rico and four small territories are included; only Puerto Rico is drawn on the map"]),
    ]
    for i, (heading_text, colour, lines) in enumerate(cols):
        x = X0 + i * (third + GAP)
        p7.tile(f"notes{i + 1}", x, KPI_Y, third, BOTTOM - KPI_Y, textbox(
            [(heading_text, 16, True, colour)] + [("•  " + t, 12.5, False, INK) for t in lines], pad=(14, 10, 16, 16)),
            stripe=colour)

    # ---------------------------------------------------------------- tooltip: state
    tt = Page("stateTooltip", "State Tooltip", width=300, height=200, kind="Tooltip")
    tt.add("ttName", 4, 4, 292, 36, card("Selected State", colour=INK, size=16))
    tt.add("ttShareLabel", 12, 44, 140, 20, textbox([("Fell short in 2024", 10.5, False, INK_2)]))
    tt.add("ttShare", 8, 62, 140, 40, card("Short Share", colour=RED, size=22))
    tt.add("ttCount", 150, 66, 146, 30, card("State Short Text", colour=INK, size=11, bold=False))
    tt.add("ttNoEhr", 8, 110, 288, 26, card("State No EHR", colour=PURPLE, size=11, bold=False))
    tt.add("ttRank", 8, 140, 288, 30, card("State Rank Text", colour=INK_2, size=11, bold=False))
    return [p1, p2, p3, p4, p5, p6, p7, tt]


def find_base_theme():
    install = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-AppxPackage Microsoft.MicrosoftPowerBIDesktop | Sort-Object Version | Select-Object -Last 1).InstallLocation"],
        capture_output=True, text=True).stdout.strip()
    f = Path(install) / "bin/WebView2Resources/minerva/sharedresources/BaseThemes" / f"{BASE_THEME}.json"
    if install and f.exists():
        return f
    raise FileNotFoundError("Power BI Desktop (Microsoft Store version) base theme not found")


def build_report():
    shutil.rmtree(RPT, ignore_errors=True)
    pages = build_pages()
    colours = {"paper": PAPER, "paper_top": PAPER_TOP, "grid": GRIDC, "card": CARD, "line": LINE, "rail": "#06122F",
               "violet": "#8B5CF6",
               "cobalt": COBALT, "mint": MINT, "rail_x": RAIL_X}
    ASSETS.mkdir(parents=True, exist_ok=True)
    for old in ASSETS.glob("bg_*.png"):
        old.unlink()
    write_json(ASSETS / "layout.json", {"colors": colours})
    subprocess.run([sys.executable, str(ROOT / "Python" / "make_background.py")], check=True)
    images = ["page_bg.png", "logo.png"]

    d = RPT / "definition"
    write_json(RPT / "definition.pbir", {"$schema": S_PBIR, "version": "4.0",
                                         "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
    write_json(d / "version.json", {"$schema": S_VERSION, "version": "2.0.0"})
    write_json(d / "report.json", {
        "$schema": S_REPORT,
        "themeCollection": {
            "baseTheme": {"name": BASE_THEME, "reportVersionAtImport": "5.59", "type": "SharedResources"},
            "customTheme": {"name": CUSTOM_THEME, "reportVersionAtImport": "5.59", "type": "RegisteredResources"}},
        "layoutOptimization": "None",
        "resourcePackages": [
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": BASE_THEME, "path": f"BaseThemes/{BASE_THEME}.json", "type": "BaseTheme"}]},
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": [{"name": CUSTOM_THEME, "path": CUSTOM_THEME, "type": "CustomTheme"},
                       *[{"name": im, "path": im, "type": "Image"} for im in images]]}]})
    static = RPT / "StaticResources"
    (static / "SharedResources" / "BaseThemes").mkdir(parents=True, exist_ok=True)
    shutil.copy(find_base_theme(), static / "SharedResources" / "BaseThemes" / f"{BASE_THEME}.json")
    (static / "RegisteredResources").mkdir(parents=True, exist_ok=True)
    for im in images:
        shutil.copy(ASSETS / im, static / "RegisteredResources" / im)
    write_json(static / "RegisteredResources" / CUSTOM_THEME, {
        "name": "Deep Blue Glass",
        "dataColors": [COBALT, RED, PURPLE, TEAL, AMBER, SLATE, COBALT_L, RED_L],
        "foreground": INK, "foregroundNeutralSecondary": INK_2, "background": PANEL, "backgroundLight": PANEL_2,
        "tableAccent": COBALT,
        "textClasses": {"title": {"fontFace": FONT, "color": INK}, "label": {"fontFace": FONT, "color": INK_2},
                        "callout": {"fontFace": FONT, "color": INK}, "header": {"fontFace": FONT, "color": INK}}})
    write_json(d / "pages" / "pages.json", {"$schema": S_PAGES, "pageOrder": [p.name for p in pages],
                                            "activePageName": pages[0].name})
    for p in pages:
        write_json(d / "pages" / p.name / "page.json", p.json())
        for v in p.visuals:
            write_json(d / "pages" / p.name / "visuals" / v["name"] / "visual.json", v)


def main():
    build_model()
    build_report()
    write_json(DASH / f"{NAME}.pbip", {"$schema": S_PBIP, "version": "1.0",
                                       "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
                                       "settings": {"enableAutoRecovery": True}})
    print(f"wrote dashboard/{NAME}.pbip")


if __name__ == "__main__":
    main()
