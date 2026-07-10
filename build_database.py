"""
Loads the two source CSV files into a SQLite database.
It reads the raw files, normalizes all date
and timestamp columns to YYYY-MM-DD format (handles both M/D/YYYY and
YYYY-MM-DD inputs), then writes everything into SQLite.
"""

import sqlite3
import pandas as pd
from pathlib import Path


DATA_DIR = Path("data")
DB_PATH = "app174.db"


def normalize_dates(df):
    
    # Convert any date or timestamp column to a consistent YYYY-MM-DD string.
    
    for col in df.columns:
        if "date" not in col.lower() and "timestamp" not in col.lower():
            continue
        parsed = pd.to_datetime(df[col], format="mixed", dayfirst=False, errors="coerce")
        if parsed.isna().all():
            continue
        has_time = df[col].astype(str).str.contains(r"\d{1,2}:\d{2}").any()
        if has_time:
            df[col] = parsed.dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            df[col] = parsed.dt.strftime("%Y-%m-%d")
    return df


def load_csv_to_table(conn, csv_path, table_name):
    df = pd.read_csv(csv_path)
    df = normalize_dates(df)
    df.to_sql(table_name, conn, if_exists="replace", index=False)
    date_cols = [c for c in df.columns if "date" in c.lower()]
    sample = df[date_cols[0]].iloc[0] if date_cols else "n/a"
    print(f"  loaded {len(df):,} rows from {csv_path.name} -> '{table_name}'  (date sample: {sample})")
    return len(df)


def main():
    conn = sqlite3.connect(DB_PATH)
    print(f"Building {DB_PATH} ...")

    load_csv_to_table(conn, DATA_DIR / "installs.csv", "installs_raw")
    load_csv_to_table(conn, DATA_DIR / "revenue.csv", "revenue_raw")

    # indexes on the join key speed up the later joins on a file this size
    conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_uid ON installs_raw(user_install_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rev_uid ON revenue_raw(user_install_id)")
    conn.commit()

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()