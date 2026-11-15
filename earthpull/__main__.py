"""Usage:
  python -m earthpull login
  python -m earthpull check   --bbox W,S,E,N [--start 2003-01-01 --end 2024-12-31]
  python -m earthpull pull    --bbox W,S,E,N [--start ... --end ...] [--only air_temp,precip] [--include-daily]
  python -m earthpull inspect <variable_id>
"""
import argparse

import pandas as pd

from .core import DATA, BBox, check, inspect, login, pull


def main():
    ap = argparse.ArgumentParser(prog="earthpull")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login")
    for name in ("check", "pull"):
        p = sub.add_parser(name)
        p.add_argument("--bbox", required=True, help="west,south,east,north in degrees")
        p.add_argument("--start", default="2003-01-01")
        p.add_argument("--end", default="2024-12-31")
        p.add_argument("--only", help="comma-separated variable ids from sources.yaml")
        if name == "pull":
            p.add_argument("--include-daily", action="store_true")
            p.add_argument("--min-valid", type=float, default=0.7)
    pi = sub.add_parser("inspect")
    pi.add_argument("variable_id")
    a = ap.parse_args()

    pd.set_option("display.width", 200, "display.max_columns", 20)
    if a.cmd == "login":
        login(); print("logged in; ~/.netrc saved")
    elif a.cmd == "inspect":
        inspect(a.variable_id)
    else:
        bbox = BBox.parse(a.bbox)
        ids = a.only.split(",") if a.only else None
        if a.cmd == "check":
            print(check(bbox, a.start, a.end, ids).to_string(index=False))
        else:
            wide, report = pull(bbox, a.start, a.end, ids, a.include_daily, a.min_valid)
            out = DATA / "out" / f"box_{a.bbox.replace(',', '_')}_{a.start[:7]}_{a.end[:7]}"
            out.parent.mkdir(parents=True, exist_ok=True)
            from .core import export_csv

            pathlib_out = f"{out}.csv"
            open(pathlib_out, "w").write(export_csv(wide, report, f"box {a.bbox}", a.start, a.end))
            wide.to_parquet(f"{out}.parquet")
            report.to_csv(f"{out}_report.csv", index=False)
            print(report.to_string(index=False))
            print(f"\nwrote {out}.csv / .parquet ({wide.shape[0]} months x {wide.shape[1]} variables)")


if __name__ == "__main__":
    main()
