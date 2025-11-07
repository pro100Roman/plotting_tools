#!/usr/bin/env python3
import argparse, csv, os
import pandas as pd
import matplotlib.pyplot as plt
from threading import thre

def sniff_sep(path):
    with open(path, "r", newline="") as f:
        sample = f.read(4096)
    try:
        return csv.Sniffer().sniff(sample).delimiter
    except Exception:
        return ","  # default

def main():
    p = argparse.ArgumentParser(description="Plot columns from a CSV.")
    p.add_argument("csv", help="Path to CSV file")
    p.add_argument("--x", help="X-axis column (default: first column)")
    p.add_argument("--y", nargs="+", help="Y columns (default: all numeric except X)")
    p.add_argument("--sep", help="CSV separator (auto by default)")
    p.add_argument("--decimal", default=".", help="Decimal point (default: .)")
    p.add_argument("--title", help="Plot title")
    p.add_argument("--out", help="Save to file instead of showing (e.g., plot.png)")
    p.add_argument("--no-grid", action="store_true", help="Disable grid")
    args = p.parse_args()

    sep = args.sep or sniff_sep(args.csv)
    df = pd.read_csv(args.csv, sep=sep, decimal=args.decimal)

    # Choose X column
    xcol = args.x or df.columns[0]

    # Parse dates if the X looks like time
    parse_as_date = any(k in xcol.lower() for k in ("time", "date", "timestamp"))
    if parse_as_date:
        df[xcol] = pd.to_datetime(df[xcol], errors="coerce")

    # Choose Y columns
    if args.y:
        ycols = args.y
    else:
        numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
        ycols = [c for c in numeric_cols if c != xcol]
        if not ycols:
            # if no numeric, just take all except X
            ycols = [c for c in df.columns if c != xcol]

    # Plot
    plt.figure()
    for c in ycols:
        plt.plot(df[xcol], df[c], label=c)
    plt.xlabel(xcol)
    plt.ylabel("value")
    plt.title(args.title or os.path.basename(args.csv))
    if not args.no_grid:
        plt.grid(True)
    if len(ycols) > 1:
        plt.legend()
    plt.tight_layout()

    if args.out:
        plt.savefig(args.out, dpi=150)
    else:
        plt.show()

if __name__ == "__main__":
    main()
