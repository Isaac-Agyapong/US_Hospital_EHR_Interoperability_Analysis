"""Download the source data and record it in Data/raw/manifest.json (URL, size, SHA-256).

    python Python/01_download_data.py

1. CMS Provider Data hospital archives (data.cms.gov/provider-data), one snapshot per year. Each holds the
   "Meets criteria for promoting interoperability of EHRs" flag (called "meaningful use" before 2020):
   - 2019-2024 snapshots: column in Hospital General Information
   - latest snapshot: separate Promoting Interoperability - Hospital file (reporting year 2024) with each
     hospital's CEHRT ID (the ID of its certified EHR technology)
2. ONC Certified Health IT Product List (CHPL): every CEHRT ID looked up once to get the EHR developer and
   products. Needs a free API key in .env as CHPL_API_KEY (the file is git-ignored). Answers are cached in
   Data/raw/chpl_cehrt.json so the API is called only for new IDs.
"""
import csv
import hashlib
import io
import json
import re
import subprocess
import time
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "Data" / "raw"
ARCH = RAW / "archives"
ARCH.mkdir(parents=True, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0"}
ARCHIVE_API = "https://data.cms.gov/provider-data/api/1/archive/aggregate/theme/hospitals/relative"
# one snapshot per year that holds the flag (checked by hand: some 2020 snapshots use id-only file names)
SNAPSHOTS = ["2019-10-31", "2020-05-01", "2021-10-27", "2022-10-06", "2023-11-06", "2024-10-30", "2026-08-13"]
CHPL = "https://chpl.healthit.gov/rest/certification_ids/{}"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def curl(url, out):
    subprocess.run(["curl", "-sL", "--fail", "--retry", "5", "-C", "-", "-o", str(out), url], check=True)


def api_key():
    env = ROOT / ".env"
    if not env.exists():
        raise SystemExit("Missing .env with CHPL_API_KEY=... (free key from chpl.healthit.gov)")
    vals = dict(line.split("=", 1) for line in env.read_text().split() if "=" in line)
    return vals["CHPL_API_KEY"].strip()


def pi_file(zip_path):
    """The Promoting Interoperability - Hospital CSV inside a snapshot, if present."""
    z = zipfile.ZipFile(zip_path)
    names = [n for n in z.namelist() if re.search(r"(?i)promoting_?interoperab", n)]
    return (z, names[0]) if names else (z, None)


def main():
    manifest = {"downloaded": str(date.today()), "files": {}}
    index = json.load(urllib.request.urlopen(urllib.request.Request(ARCHIVE_API, headers=H), timeout=120))["data"]
    by_date = {x["date"]: x for x in index if x["type"] == "theme"}
    for d in SNAPSHOTS:
        x = by_date[d]
        url = "https://data.cms.gov" + x["url"]
        out = ARCH / Path(x["url"]).name
        if not out.exists() or out.stat().st_size != int(x["size"]):
            curl(url, out)
        manifest["files"][f"archives/{out.name}"] = {"url": url, "bytes": out.stat().st_size, "sha256": sha256(out)}
        print(f"  {out.name:<32} {out.stat().st_size / 1e6:6.1f} MB")

    # CEHRT IDs from the latest Promoting Interoperability file -> CHPL
    z, name = pi_file(ARCH / f"hospitals_{SNAPSHOTS[-1]}.zip")
    rows = list(csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8-sig", errors="replace")))
    ids = sorted({r["CEHRT ID"].strip() for r in rows if r["CEHRT ID"].strip()})
    cache_path = RAW / "chpl_cehrt.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    key, todo = api_key(), [i for i in ids if i not in cache]
    print(f"CHPL: {len(ids)} CEHRT IDs, {len(todo)} to look up")
    for k, cid in enumerate(todo, 1):
        req = urllib.request.Request(CHPL.format(cid), headers={**H, "API-Key": key, "Accept": "application/json"})
        for attempt in range(4):
            try:
                cache[cid] = json.load(urllib.request.urlopen(req, timeout=60))
                break
            except urllib.error.HTTPError as e:
                if e.code == 404:          # ID not found in CHPL: record it (a data-quality finding)
                    cache[cid] = {"not_found": True}
                    break
                time.sleep(2 * (attempt + 1))
            except Exception:
                time.sleep(2 * (attempt + 1))
        if k % 100 == 0:
            cache_path.write_text(json.dumps(cache), encoding="utf-8")
            print(f"  {k}/{len(todo)}")
        time.sleep(0.15)
    cache_path.write_text(json.dumps(cache), encoding="utf-8")
    manifest["files"]["chpl_cehrt.json"] = {"url": "https://chpl.healthit.gov/rest/certification_ids/{CEHRT ID}",
                                            "bytes": cache_path.stat().st_size, "sha256": sha256(cache_path),
                                            "note": "one CHPL API response per CEHRT ID (free API key required)"}
    (RAW / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    missing = sum(1 for v in cache.values() if v.get("not_found"))
    print(f"wrote Data/raw/manifest.json; CEHRT IDs not found in CHPL: {missing}")


if __name__ == "__main__":
    main()
