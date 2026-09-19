from pathlib import Path

import numpy as np
import pandas as pd


# =========================================================
# 基本設定
# =========================================================

OUTPUT_DIR = Path("data/raw")

rng = np.random.default_rng(44)

N_JOBS_2025 = 10
N_JOBS_2026 = 10


# =========================================================
# マスタ読み込み
# =========================================================

clients = pd.read_csv(
    OUTPUT_DIR / "clients.csv"
)

recruiters = pd.read_csv(
    OUTPUT_DIR / "recruiters.csv",
    parse_dates=[
        "join_date",
        "leave_date",
    ],
)

occupations = pd.read_csv(
    OUTPUT_DIR / "occupations.csv"
)

locations = pd.read_csv(
    OUTPUT_DIR / "locations.csv"
)


# RAのみ取得
ra_ids = recruiters.loc[
    recruiters["role_type"] == "RA",
    "recruiter_id",
].tolist()


# =========================================================
# 職種ごとの求人提示時給の基準
# =========================================================

base_offered_wage = {
    "OCC001": 1500,  # 一般事務
    "OCC002": 1400,  # データ入力
    "OCC003": 1600,  # コールセンター
    "OCC004": 2100,  # 医薬翻訳
    "OCC005": 2000,  # 品質管理（QC）
    "OCC006": 2200,  # DM
    "OCC007": 2100,  # CRC
    "OCC008": 2850,  # CRA
    "OCC009": 3000,  # 統計解析
    "OCC010": 2650,  # 薬事
}


# =========================================================
# 職種ごとの基本必要スキル
# =========================================================

base_required_skill = {
    "OCC001": 1,
    "OCC002": 1,
    "OCC003": 2,
    "OCC004": 3,
    "OCC005": 3,
    "OCC006": 3,
    "OCC007": 3,
    "OCC008": 4,
    "OCC009": 4,
    "OCC010": 4,
}


# =========================================================
# 年度別の職種構成
# =========================================================

occupation_ids = list(
    base_offered_wage.keys()
)

occupation_probs_2025 = [
    0.18,  # 一般事務
    0.15,  # データ入力
    0.15,  # コールセンター
    0.10,  # 医薬翻訳
    0.10,  # QC
    0.10,  # DM
    0.08,  # CRC
    0.06,  # CRA
    0.04,  # 統計解析
    0.04,  # 薬事
]

occupation_probs_2026 = [
    0.12,  # 一般事務
    0.08,  # データ入力
    0.12,  # コールセンター
    0.10,  # 医薬翻訳
    0.10,  # QC
    0.12,  # DM
    0.10,  # CRC
    0.10,  # CRA
    0.08,  # 統計解析
    0.08,  # 薬事
]


# =========================================================
# 勤務地分布
# =========================================================

location_ids = [
    "LOC001",
    "LOC002",
    "LOC003",
    "LOC004",
    "LOC005",
    "LOC006",
    "LOC007",
    "LOC008",
]

location_probs = [
    0.40,
    0.15,
    0.10,
    0.10,
    0.05,
    0.10,
    0.05,
    0.05,
]


# =========================================================
# 求人生成関数
# =========================================================

def generate_jobs(
    year,
    n_jobs,
    occupation_probs,
    start_counter,
):

    job_data = []

    if year == 2025:
        start_date = pd.Timestamp("2025-04-01")
        end_date = pd.Timestamp("2025-09-30")
    else:
        start_date = pd.Timestamp("2026-04-01")
        end_date = pd.Timestamp("2026-09-30")

    total_days = (
        end_date - start_date
    ).days

    for i in range(n_jobs):

        job_id = (
            f"JOB{start_counter + i:05d}"
        )

        # ---------------------------------------------
        # クライアント
        # ---------------------------------------------

        client_id = rng.choice(
            clients["client_id"]
        )


        # ---------------------------------------------
        # RA担当者
        # ---------------------------------------------

        active_ra = recruiters[
            (recruiters["role_type"] == "RA")
            & (
                recruiters["join_date"]
                <= start_date
            )
            & (
                recruiters["leave_date"].isna()
                | (
                    recruiters["leave_date"]
                    >= start_date
                )
            )
        ]

        ra_id = rng.choice(
            active_ra["recruiter_id"]
        )


        # ---------------------------------------------
        # 求人公開日
        # ---------------------------------------------

        open_offset = rng.integers(
            0,
            total_days + 1,
        )

        open_date = (
            start_date
            + pd.Timedelta(
                days=int(open_offset)
            )
        )


        # ---------------------------------------------
        # 職種
        # ---------------------------------------------

        occupation_id = rng.choice(
            occupation_ids,
            p=occupation_probs,
        )


        # ---------------------------------------------
        # 勤務地
        # ---------------------------------------------

        location_id = rng.choice(
            location_ids,
            p=location_probs,
        )


        # ---------------------------------------------
        # 募集枠数
        # ---------------------------------------------

        if year == 2025:

            required_slots = int(
                rng.choice(
                    [1, 2, 3],
                    p=[
                        0.60,
                        0.30,
                        0.10,
                    ],
                )
            )

        else:

            required_slots = int(
                rng.choice(
                    [1, 2, 3, 4],
                    p=[
                        0.45,
                        0.30,
                        0.15,
                        0.10,
                    ],
                )
            )


        # ---------------------------------------------
        # 必要スキルレベル
        # ---------------------------------------------

        required_skill_level = (
            base_required_skill[
                occupation_id
            ]
        )

        skill_adjustment = rng.choice(
            [-1, 0, 1],
            p=[
                0.10,
                0.70,
                0.20,
            ],
        )

        required_skill_level += (
            skill_adjustment
        )

        # 2026年は要求水準を少し引き上げる
        if year == 2026:
            if rng.random() < 0.30:
                required_skill_level += 1

        required_skill_level = int(
            np.clip(
                required_skill_level,
                1,
                5,
            )
        )


        # ---------------------------------------------
        # 求人提示時給
        # ---------------------------------------------

        offered_hourly_wage = (
            base_offered_wage[
                occupation_id
            ]
        )

        # スキル水準による調整
        offered_hourly_wage += (
            required_skill_level - 3
        ) * 100

        # 求人ごとのばらつき
        offered_hourly_wage += rng.normal(
            loc=0,
            scale=80,
        )

        # 2026年は提示時給を3％程度上げる
        if year == 2026:
            offered_hourly_wage *= 1.03

        offered_hourly_wage = int(
            round(
                offered_hourly_wage
                / 50
            )
            * 50
        )

        offered_hourly_wage = max(
            offered_hourly_wage,
            1200,
        )


        # ---------------------------------------------
        # 勤務形態
        # ---------------------------------------------

        work_style = rng.choice(
            [
                "onsite",
                "hybrid",
                "remote",
            ],
            p=[
                0.55,
                0.35,
                0.10,
            ],
        )


        # ---------------------------------------------
        # 求人状態
        # ---------------------------------------------

        # テスト段階では全件open
        status = "open"

        close_date = pd.NaT


        # ---------------------------------------------
        # レコード追加
        # ---------------------------------------------

        job_data.append(
            [
                job_id,
                client_id,
                ra_id,
                open_date,
                close_date,
                occupation_id,
                location_id,
                required_slots,
                offered_hourly_wage,
                required_skill_level,
                work_style,
                status,
            ]
        )

    return job_data


# =========================================================
# 2025・2026年求人を生成
# =========================================================

jobs_2025 = generate_jobs(
    year=2025,
    n_jobs=N_JOBS_2025,
    occupation_probs=occupation_probs_2025,
    start_counter=1,
)

jobs_2026 = generate_jobs(
    year=2026,
    n_jobs=N_JOBS_2026,
    occupation_probs=occupation_probs_2026,
    start_counter=11,
)


# =========================================================
# DataFrame化
# =========================================================

jobs = pd.DataFrame(
    jobs_2025 + jobs_2026,
    columns=[
        "job_id",
        "client_id",
        "ra_id",
        "open_date",
        "close_date",
        "occupation_id",
        "location_id",
        "required_slots",
        "offered_hourly_wage",
        "required_skill_level",
        "work_style",
        "status",
    ],
)


# =========================================================
# データ品質チェック
# =========================================================

assert jobs["job_id"].is_unique

assert jobs[
    "client_id"
].isin(
    clients["client_id"]
).all()

assert jobs[
    "ra_id"
].isin(
    recruiters["recruiter_id"]
).all()

assert jobs[
    "occupation_id"
].isin(
    occupations["occupation_id"]
).all()

assert jobs[
    "location_id"
].isin(
    locations["location_id"]
).all()

assert jobs[
    "required_slots"
].ge(1).all()

assert jobs[
    "offered_hourly_wage"
].gt(0).all()

assert jobs[
    "required_skill_level"
].between(
    1,
    5,
).all()

assert jobs[
    "work_style"
].isin(
    [
        "onsite",
        "hybrid",
        "remote",
    ]
).all()

assert jobs[
    "status"
].isin(
    [
        "open",
        "closed",
    ]
).all()


# =========================================================
# 年度列を確認用に作成
# ※ CSVには出力しない
# =========================================================

jobs_check = jobs.copy()

jobs_check["year"] = (
    jobs_check[
        "open_date"
    ].dt.year
)


# =========================================================
# CSV出力
# =========================================================

jobs.to_csv(
    OUTPUT_DIR / "jobs_test.csv",
    index=False,
    encoding="utf-8-sig",
)


# =========================================================
# 内容確認
# =========================================================

print(jobs)

print()
print("求人テストデータを生成しました。")
print(f"件数: {len(jobs)}")

print()
print("年度別求人件数")
print(
    jobs_check[
        "year"
    ].value_counts().sort_index()
)

print()
print("年度別平均募集枠数")
print(
    jobs_check.groupby(
        "year"
    )["required_slots"].mean()
)

print()
print("年度別平均提示時給")
print(
    jobs_check.groupby(
        "year"
    )["offered_hourly_wage"].mean()
)

print()
print("年度別平均必要スキルレベル")
print(
    jobs_check.groupby(
        "year"
    )["required_skill_level"].mean()
)

print()
print("年度×職種件数")
print(
    pd.crosstab(
        jobs_check["year"],
        jobs_check["occupation_id"],
    )
)