from pathlib import Path
import sqlite3
import pandas as pd


# =========================================================
# パス設定
# =========================================================

RAW_DIR = Path("data/raw")
DATABASE_DIR = Path("database")

DATABASE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

DB_PATH = (
    DATABASE_DIR
    / "recruitment_analytics.sqlite"
)


# =========================================================
# SQLite接続
# =========================================================

conn = sqlite3.connect(DB_PATH)


# =========================================================
# CSVファイルとテーブル名の対応
# =========================================================

tables = {
    "clients": "clients.csv",
    "recruiters": "recruiters.csv",
    "occupations": "occupations.csv",
    "locations": "locations.csv",
    "candidates": "candidates_test.csv",
    "candidate_experiences":
        "candidate_experiences_test.csv",
    "candidate_preferences":
        "candidate_preferences_test.csv",
    "jobs": "jobs_test.csv",
    "job_entries": "job_entries_test.csv",
    "candidate_activities":
        "candidate_activities_test.csv",
    "job_introductions":
        "job_introductions_test.csv",
    "applications":
        "applications_test.csv",
    "workplace_visits":
        "workplace_visits_test.csv",
    "placements":
        "placements_test.csv",
}


# =========================================================
# CSV → SQLite
# =========================================================

for table_name, file_name in tables.items():

    csv_path = RAW_DIR / file_name

    if not csv_path.exists():
        raise FileNotFoundError(
            f"ファイルが見つかりません: {csv_path}"
        )

    df = pd.read_csv(csv_path)

    df.to_sql(
        table_name,
        conn,
        if_exists="replace",
        index=False,
    )

    print(
        f"{table_name}: "
        f"{len(df)} rows loaded"
    )


# =========================================================
# テーブル一覧確認
# =========================================================

table_list = pd.read_sql_query(
    """
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
    ORDER BY name
    """,
    conn,
)

print()
print("SQLite内のテーブル一覧")
print(table_list)


# =========================================================
# 接続終了
# =========================================================

conn.close()

print()
print(
    f"SQLite database created: {DB_PATH}"
)