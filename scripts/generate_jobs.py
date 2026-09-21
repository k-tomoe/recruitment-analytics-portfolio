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

# 合成データの観察終了日
#
# この日までに実際にクローズした求人のみ
# close_date を記録する。
DATA_END_DATE = pd.Timestamp("2026-09-30")


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


        # =================================================
        # 修正① 求人終了日・求人状態の生成
        # =================================================
        #
        # 【変更前】
        # 小規模テストでは、すべての求人を
        # status = "open"
        # close_date = NULL
        # としていた。
        #
        # 【問題点】
        # 初回EDAでは、2025年に公開された求人が
        # 2026年にもCA紹介対象として残っていた。
        #
        # その結果、
        # ・2025年公開求人に2026年の応募が紐づく
        # ・古い求人が長期間紹介対象として残る
        # ・求人公開年と応募年の関係が不自然になる
        # という問題が確認された。
        #
        # 長期募集求人が存在すること自体は現実的だが、
        # 全求人が長期OPENとなるのは不自然である。
        #
        # 【修正仕様】
        # 求人ごとに求人期間タイプを設定する。
        #
        # ・約15%：短期求人
        #   公開後60～90日程度で終了
        #
        # ・約70%：通常求人
        #   公開後90～180日程度で終了
        #
        # ・約15%：長期OPEN求人
        #   close_dateはNULL
        #
        # ただし、計算上の終了予定日が
        # DATA_END_DATE（2026-09-30）より後の場合は、
        # 観察期間内ではまだクローズしていないため、
        # close_date = NULL
        # status = "open"
        # とする。
        #
        # -------------------------------------------------
        # 変更前コード
        # -------------------------------------------------
        #
        # # テスト段階では全件open
        # status = "open"
        #
        # close_date = pd.NaT
        #
        # -------------------------------------------------
        # 変更後コード
        # -------------------------------------------------

        job_duration_type = rng.choice(
            [
                "short",
                "standard",
                "long_open",
            ],
            p=[
                0.15,
                0.70,
                0.15,
            ],
        )

        if job_duration_type == "short":

            # 短期求人：
            # 公開後60～90日程度で終了
            open_days = int(
                rng.integers(
                    60,
                    91,
                )
            )

            calculated_close_date = (
                open_date
                + pd.Timedelta(
                    days=open_days
                )
            )

        elif job_duration_type == "standard":

            # 通常求人：
            # 公開後90～180日程度で終了
            open_days = int(
                rng.integers(
                    90,
                    181,
                )
            )

            calculated_close_date = (
                open_date
                + pd.Timedelta(
                    days=open_days
                )
            )

        else:

            # 長期OPEN求人
            calculated_close_date = pd.NaT


        # ---------------------------------------------
        # データ観察終了日時点の求人状態を決定
        # ---------------------------------------------

        if pd.isna(
            calculated_close_date
        ):

            # 長期OPEN求人
            close_date = pd.NaT
            status = "open"

        elif (
            calculated_close_date
            <= DATA_END_DATE
        ):

            # データ期間内に終了した求人
            close_date = (
                calculated_close_date
            )

            status = "closed"

        else:

            # 計算上は将来終了する求人だが、
            # DATA_END_DATE時点ではまだ公開中。
            #
            # 未来の終了イベントは観察していないため、
            # close_dateはNULLとする。
            close_date = pd.NaT
            status = "open"


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
# 修正①に対する追加品質チェック
# =========================================================

# close_dateが存在する求人では、
# close_dateがopen_dateより後であること
closed_jobs = jobs[
    jobs["close_date"].notna()
]

assert (
    closed_jobs[
        "close_date"
    ]
    >
    closed_jobs[
        "open_date"
    ]
).all()


# closed求人には必ずclose_dateが存在すること
assert jobs.loc[
    jobs["status"] == "closed",
    "close_date",
].notna().all()


# open求人ではclose_dateがNULLであること
assert jobs.loc[
    jobs["status"] == "open",
    "close_date",
].isna().all()


# close_dateが存在する場合、
# データ観察終了日を超えていないこと
assert (
    closed_jobs[
        "close_date"
    ]
    <= DATA_END_DATE
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


# 求人公開期間を確認するための列
#
# close_dateがある求人のみ計算され、
# OPEN求人はNaNになる
jobs_check[
    "open_days"
] = (
    jobs_check[
        "close_date"
    ]
    -
    jobs_check[
        "open_date"
    ]
).dt.days


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
    )[
        "required_skill_level"
    ].mean()
)


print()
print("年度×職種件数")

print(
    pd.crosstab(
        jobs_check["year"],
        jobs_check["occupation_id"],
    )
)


# =========================================================
# 修正①の内容確認
# =========================================================

print()
print("求人ステータス別件数")

print(
    jobs[
        "status"
    ].value_counts(
        dropna=False
    )
)


print()
print("年度×求人ステータス件数")

print(
    pd.crosstab(
        jobs_check["year"],
        jobs_check["status"],
    )
)


print()
print("求人公開日・終了日確認")

print(
    jobs[
        [
            "job_id",
            "open_date",
            "close_date",
            "status",
        ]
    ].sort_values(
        "open_date"
    )
)


print()
print("終了済み求人の公開期間（日数）")

print(
    jobs_check.loc[
        jobs_check[
            "close_date"
        ].notna(),
        [
            "job_id",
            "year",
            "open_date",
            "close_date",
            "open_days",
        ],
    ].sort_values(
        "open_date"
    )
)