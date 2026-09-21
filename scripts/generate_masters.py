from pathlib import Path

import pandas as pd


# =========================================================
# 出力先
# =========================================================

OUTPUT_DIR = Path("data/raw")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# =========================================================
# 1. 職種マスタ occupations
# =========================================================

occupations = pd.DataFrame(
    [
        ["OCC001", "一般事務", "事務"],
        ["OCC002", "データ入力", "事務"],
        ["OCC003", "コールセンター", "カスタマーサポート"],
        ["OCC004", "医薬翻訳", "医薬専門職"],
        ["OCC005", "品質管理（QC）", "医薬専門職"],
        ["OCC006", "DM（データマネジメント）", "医薬専門職"],
        ["OCC007", "CRC", "医薬専門職"],
        ["OCC008", "CRA", "医薬専門職"],
        ["OCC009", "統計解析", "医薬専門職"],
        ["OCC010", "薬事", "医薬専門職"],
    ],
    columns=[
        "occupation_id",
        "occupation_name",
        "occupation_group",
    ],
)


# =========================================================
# 2. 勤務地マスタ locations
# =========================================================

locations = pd.DataFrame(
    [
        ["LOC001", "東京都", "首都圏"],
        ["LOC002", "神奈川県", "首都圏"],
        ["LOC003", "埼玉県", "首都圏"],
        ["LOC004", "千葉県", "首都圏"],
        ["LOC005", "群馬県", "北関東"],
        ["LOC006", "大阪府", "関西"],
        ["LOC007", "愛知県", "東海"],
        ["LOC008", "福岡県", "九州"],
    ],
    columns=[
        "location_id",
        "prefecture_name",
        "area_group",
    ],
)


# =========================================================
# 3. クライアントマスタ clients
# =========================================================

clients = pd.DataFrame(
    {
        "client_id": [
            f"CLI{i:03d}"
            for i in range(1, 101)
        ],
        "client_name": [
            f"クライアント企業{i:03d}"
            for i in range(1, 101)
        ],
    }
)


# =========================================================
# 4. 担当者マスタ recruiters
# =========================================================

recruiters_data = []

# 2025年分析開始時点ですでに在籍しているRA：13名
#
# 今回の分析では担当者の勤続年数そのものは分析対象とせず、
# 年度ごとの稼働人数・担当負荷を分析する。
# そのため既存担当者のjoin_dateは2024-04-01に統一する。
for i in range(1, 14):
    recruiters_data.append(
        [
            f"RA{i:03d}",
            "RA",
            "2024-04-01",
            None,
        ]
    )

# 2026年にRAを1名追加
recruiters_data.append(
    [
        "RA014",
        "RA",
        "2026-04-01",
        None,
    ]
)

# 2025年分析開始時点ですでに在籍しているCA：21名
#
# 今回の分析では担当者の勤続年数そのものは分析対象とせず、
# 年度ごとの稼働人数・担当負荷を分析する。
# そのため既存担当者のjoin_dateは2024-04-01に統一する。
for i in range(1, 22):
    recruiters_data.append(
        [
            f"CA{i:03d}",
            "CA",
            "2024-04-01",
            None,
        ]
    )

# 2026年にCAを1名追加
recruiters_data.append(
    [
        "CA022",
        "CA",
        "2026-04-01",
        None,
    ]
)

recruiters = pd.DataFrame(
    recruiters_data,
    columns=[
        "recruiter_id",
        "role_type",
        "join_date",
        "leave_date",
    ],
)

recruiters["join_date"] = pd.to_datetime(
    recruiters["join_date"]
)

recruiters["leave_date"] = pd.to_datetime(
    recruiters["leave_date"]
)


# =========================================================
# データ品質チェック
# =========================================================

assert occupations["occupation_id"].is_unique
assert locations["location_id"].is_unique
assert clients["client_id"].is_unique
assert recruiters["recruiter_id"].is_unique

assert occupations["occupation_id"].notna().all()
assert locations["location_id"].notna().all()
assert clients["client_id"].notna().all()
assert recruiters["recruiter_id"].notna().all()

assert recruiters["role_type"].isin(
    ["RA", "CA"]
).all()


# =========================================================
# CSV出力
# =========================================================

occupations.to_csv(
    OUTPUT_DIR / "occupations.csv",
    index=False,
    encoding="utf-8-sig",
)

locations.to_csv(
    OUTPUT_DIR / "locations.csv",
    index=False,
    encoding="utf-8-sig",
)

clients.to_csv(
    OUTPUT_DIR / "clients.csv",
    index=False,
    encoding="utf-8-sig",
)

recruiters.to_csv(
    OUTPUT_DIR / "recruiters.csv",
    index=False,
    encoding="utf-8-sig",
)


# =========================================================
# 実行結果
# =========================================================

print("マスタデータを生成しました。")
print(f"occupations: {len(occupations)} rows")
print(f"locations: {len(locations)} rows")
print(f"clients: {len(clients)} rows")
print(f"recruiters: {len(recruiters)} rows")