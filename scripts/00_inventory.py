"""Stage 0: check raw data is intact and matches the AGENTS.md §3 inventory.

Prints shapes only (no data values). Run: uv run python scripts/00_inventory.py
"""
from src import loaders

EXPECTED_ROWS = {
    "collar": 19, "survey": 99, "assay": 2476, "lithology": 286,
    "alteration": 707, "mineralisation": 2684, "oxide": 3017,
    "rock": 469, "soil": 259,
}


def main() -> None:
    bad = loaders.verify_raw()
    print("raw manifest:", "OK" if not bad else f"CHANGED {bad}")

    tables = {name: loaders.load_dh(name) for name in loaders.DH_TABLES}
    tables["rock"] = loaders.load_rock()
    tables["soil"] = loaders.load_soil()
    for name, df in tables.items():
        flag = "OK" if len(df) == EXPECTED_ROWS[name] else f"EXPECTED {EXPECTED_ROWS[name]}"
        print(f"{name:15s} {df.shape[0]:5d} x {df.shape[1]:3d}  {flag}")

    con = loaders.load_contours()
    print(f"contours        {len(con):5d} lines, crs={con.crs}, "
          f"Z_Avg in cols: {'Z_Avg' in con.columns}, bounds={con.total_bounds.round(0)}")


if __name__ == "__main__":
    main()
