#!/usr/bin/env python3
"""Build a shareable, interactive HTML report from a CFTC electricity
Commitments of Traders page (disaggregated, short format, futures only).

Usage:
  cot_electricity.py [URL_OR_FILE] [--backfill N] [--open]

  URL_OR_FILE   CFTC page, e.g.
                https://www.cftc.gov/sites/default/files/files/dea/cotarchives/2026/futures/electricity_sf012726.htm
                Omit it to pull the current week's release.
  --backfill N  Also fetch the N prior weekly reports (adds week-over-week
                open-interest changes and the trend chart).
  --open        Open the finished report in the default browser.
  --site DIR    Build the hosted site instead: one page per stored week,
                DIR/index.html = latest (used by the GitHub Pages workflow).

Output: reports/electricity-cot-<date>.html, one self-contained file with no
external dependencies, so it can be emailed as an attachment.
"""
import argparse
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
TEMPLATE = ROOT / "template.html"
LATEST_URL = "https://www.cftc.gov/dea/futures/electricity_sf.htm"
ARCHIVE_URL = ("https://www.cftc.gov/sites/default/files/files/dea/cotarchives/"
               "{d:%Y}/futures/electricity_sf{d:%m%d%y}.htm")
HISTORY_WEEKS = 26

# Column order of every number row in the short-format report.
COLS = {"pm": (0, 1, None), "swap": (2, 3, 4), "mm": (5, 6, 7), "other": (8, 9, 10)}


def fetch(src):
    if not src.lower().startswith(("http://", "https://")):
        return Path(src).read_text(encoding="latin-1")
    req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0 (cot-electricity)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("latin-1")


def parse_date(s):
    return dt.datetime.strptime(" ".join(s.split()), "%B %d, %Y").date()


def number_row(line):
    """Return the 11 values of a ': n n n ... :' row, or None if it isn't one."""
    s = line.strip()
    if not s.startswith(":"):
        return None
    toks = s.strip(":").split()
    if len(toks) != 11 or not all(re.fullmatch(r"-?[\d,]*\.?\d*|\.", t) for t in toks):
        return None
    out = []
    for t in toks:
        if t == ".":
            out.append(None)
        elif "." in t:
            out.append(float(t.replace(",", "")))
        else:
            out.append(int(t.replace(",", "")))
    return out


def by_category(row):
    return {k: {"l": row[a], "s": row[b], "sp": row[c] if c is not None else None}
            for k, (a, b, c) in COLS.items()}


def region_of(name):
    n = name.upper()
    if "PJM" in n or "AEP DAYTON" in n:
        return "PJM"
    if "ERCOT" in n:
        return "ERCOT"
    if "MISO" in n:
        return "MISO"
    if "NYISO" in n:
        return "NYISO"
    if "ISO NE" in n or "ISONE" in n:
        return "ISO-NE"
    if any(k in n for k in ("CAISO", "SP15", "SP-15", "NP-15", "NP15", "MID-C", "MID C", "PALO VERDE")):
        return "West"
    return "Other"


def describe(name):
    n = name.upper()
    period = "Off-peak" if ("OFF" in n or "7X8" in n) else "Peak"
    tenor = "Daily" if re.search(r"\bDA(I)?LY\b|\bDLY\b", n) else "Monthly"
    return period, tenor


def parse(text):
    m = re.search(r"<pre>(.*?)</pre>", text, re.S | re.I)
    body = html.unescape(re.sub(r"<[^>]+>", "", m.group(1) if m else text))
    footer = re.search(r"Updated\s+(\w+\s+\d+,\s+\d{4})", text)
    as_of = changes_from = None
    contracts, cur, expect = [], None, None

    for line in body.splitlines():
        s = line.strip()
        if s.startswith("Disaggregated Commitments of Traders"):
            d = re.search(r"as of\s+(\w+\s+\d+,\s+\d{4})", s)
            as_of = as_of or (parse_date(d.group(1)) if d else None)
            cur, expect = None, "name"
            continue
        if expect == "name":
            if s and not s.startswith((":", "-")):
                nm = re.match(r"^(.*\S)\s+-\s+(\S.*?)(?:\s{2,}(.*))?$", s.rstrip(": "))
                name, exch, unit = (nm.group(1), nm.group(2), nm.group(3) or "") if nm else (s, "", "")
                period, tenor = describe(name)
                cur = {"name": " ".join(name.split()), "exchange": exch.strip(),
                       "unit": re.sub(r"^\((.*)\)$", r"\1", unit.strip()).strip(), "region": region_of(name),
                       "period": period, "tenor": tenor}
                contracts.append(cur)
                expect = None
            continue
        if cur is None:
            continue
        if s.startswith("CFTC Code"):
            cur["code"] = re.search(r"#\s*(\S+)", s).group(1)
            oi = re.search(r"Open Interest is\s+([\d,]+)", s)
            cur["oi"] = int(oi.group(1).replace(",", "")) if oi else None
        elif s.startswith(": Positions"):
            expect = "pos"
        elif s.startswith(": Changes from"):
            d = re.search(r"from:\s+(\w+\s+\d+,\s+\d{4})", s)
            if d and not changes_from:
                changes_from = parse_date(d.group(1))
            expect = "chg"
        elif s.startswith(": Percent of Open Interest"):
            expect = "pct"
        elif s.startswith(": Number of Traders"):
            t = re.search(r"Total Traders:\s+([\d,]+)", s)
            cur["traders"] = int(t.group(1).replace(",", "")) if t else None
            expect = "trd"
        elif expect:
            row = number_row(line)
            if row is not None:
                cur[expect] = by_category(row)
                expect = None

    out = []
    for c in contracts:
        if "pos" not in c or c.get("oi") is None:
            continue
        for k in ("chg", "pct", "trd"):
            c.setdefault(k, None)
        # Non-reportables = open interest not held by reportable traders (spreads count on both sides).
        p = c["pos"]
        tot_l = sum((p[k]["l"] or 0) + (p[k]["sp"] or 0) for k in p)
        tot_s = sum((p[k]["s"] or 0) + (p[k]["sp"] or 0) for k in p)
        p["nr"] = {"l": max(c["oi"] - tot_l, 0), "s": max(c["oi"] - tot_s, 0), "sp": None}
        out.append(c)

    if not as_of or not out:
        raise ValueError("No Commitments of Traders blocks found - is this an electricity short-format page?")
    return {"asOf": as_of.isoformat(),
            "changesFrom": changes_from.isoformat() if changes_from else None,
            "released": parse_date(footer.group(1)).isoformat() if footer else None,
            "contracts": out}


def ingest(src):
    rep = parse(fetch(src))
    rep["source"] = src
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / f"{rep['asOf']}.json").write_text(json.dumps(rep), encoding="utf-8")
    print(f"  parsed {len(rep['contracts'])} contracts, positions as of {rep['asOf']}")
    return rep


def backfill(as_of, weeks):
    d0 = dt.date.fromisoformat(as_of)
    for k in range(1, weeks + 1):
        d = d0 - dt.timedelta(weeks=k)
        if (DATA_DIR / f"{d.isoformat()}.json").exists():
            continue
        url = ARCHIVE_URL.format(d=d)
        time.sleep(0.5)  # be polite to cftc.gov
        try:
            print(f"backfill {d}: {url}")
            ingest(url)
        except Exception as e:  # holiday weeks shift the file name; skip rather than fail
            print(f"  skipped ({e})")


def build(rep, out=None, archive=None):
    hist = []
    for f in sorted(DATA_DIR.glob("*.json")):
        if f.stem <= rep["asOf"]:
            hist.append(json.loads(f.read_text(encoding="utf-8")))
    hist = hist[-HISTORY_WEEKS:]

    prev = {c["code"]: c for c in hist[-2]["contracts"]} if len(hist) >= 2 else {}
    for c in rep["contracts"]:
        p = prev.get(c["code"])
        c["oiChg"] = c["oi"] - p["oi"] if p else None
        if c.get("chg") is not None:
            c["chg"]["nr"] = ({"l": c["pos"]["nr"]["l"] - p["pos"]["nr"]["l"],
                               "s": c["pos"]["nr"]["s"] - p["pos"]["nr"]["s"], "sp": None} if p else None)

    payload = dict(rep)
    payload["prevDate"] = hist[-2]["asOf"] if len(hist) >= 2 else None
    payload["generated"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    payload["archive"] = archive
    payload["history"] = [{"date": h["asOf"],
                           "oi": {c["code"]: c["oi"] for c in h["contracts"]},
                           "region": {c["code"]: c["region"] for c in h["contracts"]}}
                          for h in hist]

    blob = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    page = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", blob, 1)
    out = out or REPORTS_DIR / f"electricity-cot-{rep['asOf']}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out


def build_site(site):
    """Hosted version: one page per stored week, index.html = latest, with a week picker."""
    weeks = sorted(f.stem for f in DATA_DIR.glob("*.json"))
    for d in weeks:
        rep = json.loads((DATA_DIR / f"{d}.json").read_text(encoding="utf-8"))
        build(rep, site / f"{d}.html", weeks)
    latest = json.loads((DATA_DIR / f"{weeks[-1]}.json").read_text(encoding="utf-8"))
    build(latest, site / "index.html", weeks)
    (site / ".nojekyll").write_text("", encoding="utf-8")
    print(f"site -> {site} ({len(weeks)} weeks, latest {weeks[-1]})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", nargs="?", default=LATEST_URL, help="CFTC report URL or saved .htm file")
    ap.add_argument("--backfill", type=int, default=0, metavar="N", help="also fetch the N prior weeks")
    ap.add_argument("--open", action="store_true", help="open the report when done")
    ap.add_argument("--site", metavar="DIR", help="build the hosted multi-week site into DIR instead")
    a = ap.parse_args()

    print(f"fetch {a.src}")
    rep = ingest(a.src)
    if a.backfill:
        backfill(rep["asOf"], a.backfill)
    if a.site:
        build_site(Path(a.site))
        return
    out = build(rep)
    print(f"report -> {out}")
    if a.open:
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    sys.exit(main())
