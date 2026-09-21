from pathlib import Path

import numpy as np
import pandas as pd


# =========================================================
# 基本設定
# =========================================================

OUTPUT_DIR = Path("data/raw")

rng = np.random.default_rng(49)

DATA_END_DATE = pd.Timestamp("2026-09-30")


# =========================================================
# 元データ読み込み
# =========================================================

applications = pd.read_csv(
    OUTPUT_DIR / "applications_test.csv",
    parse_dates=[
        "intent_confirmed_date",
        "recommendation_date",
        "withdrawal_date",
    ],
)

jobs = pd.read_csv(
    OUTPUT_DIR / "jobs_test.csv",
    parse_dates=[
        "open_date",
        "close_date",
    ],
)


# =========================================================
# 職場見学対象
# =========================================================

visit_candidates = applications[
    applications["recommendation_result"]
    == "accepted"
].copy()


# =========================================================
# 職場見学データ生成
# =========================================================

visit_data = []

visit_counter = 1


for _, application in visit_candidates.iterrows():

    application_id = application[
        "application_id"
    ]

    recommendation_date = application[
        "recommendation_date"
    ]

    job_id = application[
        "job_id"
    ]


    # =====================================================
    # 職場見学設定までの日数
    # =====================================================

    if recommendation_date.year == 2025:

        schedule_delay = int(
            rng.integers(
                1,
                5,
            )
        )

    else:

        schedule_delay = int(
            rng.integers(
                2,
                8,
            )
        )


    scheduled_date = (
        recommendation_date
        + pd.Timedelta(
            days=schedule_delay
        )
    )


    if scheduled_date > DATA_END_DATE:
        continue


    # =====================================================
    # 職場見学実施までの日数
    # =====================================================

    if recommendation_date.year == 2025:

        visit_delay = int(
            rng.integers(
                2,
                6,
            )
        )

    else:

        visit_delay = int(
            rng.integers(
                3,
                9,
            )
        )


    visit_date = (
        scheduled_date
        + pd.Timedelta(
            days=visit_delay
        )
    )


    # =====================================================
    # キャンセル判定
    # =====================================================

    # 2026年はプロセス長期化により
    # キャンセル率をやや高める
    if recommendation_date.year == 2025:

        cancel_probability = 0.10

    else:

        cancel_probability = 0.16


    is_cancelled = (
        rng.random()
        < cancel_probability
    )


    if is_cancelled:

        visit_status = "cancelled"

        actual_visit_date = pd.NaT

        result = None


    else:

        # ---------------------------------------------
        # データ期間外の場合はscheduled扱い
        # ---------------------------------------------

        if visit_date > DATA_END_DATE:

            visit_status = "scheduled"

            actual_visit_date = pd.NaT

            result = None


        else:

            visit_status = "completed"

            actual_visit_date = visit_date


            # -----------------------------------------
            # 職場見学結果
            # -----------------------------------------

            # この段階では、
            # ある程度の候補者が次工程へ進むよう設定
            continue_probability = 0.72


            # 2026年は若干低下
            if recommendation_date.year == 2026:
                continue_probability -= 0.04


            if (
                rng.random()
                < continue_probability
            ):

                result = "continue"

            else:

                result = "decline"


    # =====================================================
    # レコード追加
    # =====================================================

    visit_id = (
        f"VIS{visit_counter:05d}"
    )


    visit_data.append(
        [
            visit_id,
            application_id,
            scheduled_date,
            actual_visit_date,
            visit_status,
            result,
        ]
    )


    visit_counter += 1


# =========================================================
# DataFrame化
# =========================================================

workplace_visits = pd.DataFrame(
    visit_data,
    columns=[
        "visit_id",
        "application_id",
        "scheduled_date",
        "visit_date",
        "visit_status",
        "result",
    ],
)


# =========================================================
# データ品質チェック
# =========================================================

assert workplace_visits[
    "visit_id"
].is_unique


assert workplace_visits[
    "application_id"
].isin(
    applications[
        "application_id"
    ]
).all()


assert workplace_visits[
    "visit_status"
].isin(
    [
        "scheduled",
        "completed",
        "cancelled",
    ]
).all()


completed_rows = workplace_visits[
    workplace_visits[
        "visit_status"
    ]
    == "completed"
]

assert completed_rows[
    "visit_date"
].notna().all()

assert completed_rows[
    "result"
].isin(
    [
        "continue",
        "decline",
    ]
).all()


cancelled_rows = workplace_visits[
    workplace_visits[
        "visit_status"
    ]
    == "cancelled"
]

assert cancelled_rows[
    "visit_date"
].isna().all()

assert cancelled_rows[
    "result"
].isna().all()


scheduled_rows = workplace_visits[
    workplace_visits[
        "visit_status"
    ]
    == "scheduled"
]

assert scheduled_rows[
    "visit_date"
].isna().all()

# =========================================================
# 職場見学対象の整合性
# =========================================================

# 職場見学が生成された応募案件は、
# 企業推薦結果がacceptedであること
visit_application_check = (
    workplace_visits.merge(
        applications[
            [
                "application_id",
                "status",
                "recommendation_result",
            ]
        ],
        on="application_id",
        how="left",
    )
)

assert (
    visit_application_check[
        "recommendation_result"
    ]
    == "accepted"
).all()


# accepted案件はapplication上では
# recommendedステータスであること
assert (
    visit_application_check[
        "status"
    ]
    == "recommended"
).all()

# 職場見学設定日は推薦日以降
visit_check = workplace_visits.merge(
    applications[
        [
            "application_id",
            "recommendation_date",
        ]
    ],
    on="application_id",
    how="left",
)

assert (
    visit_check[
        "scheduled_date"
    ]
    >=
    visit_check[
        "recommendation_date"
    ]
).all()


# 実施済みの場合、
# 実施日は設定日以降
completed_check = visit_check[
    visit_check[
        "visit_date"
    ].notna()
]

assert (
    completed_check[
        "visit_date"
    ]
    >=
    completed_check[
        "scheduled_date"
    ]
).all()


# =========================================================
# CSV出力
# =========================================================

workplace_visits.to_csv(
    OUTPUT_DIR
    / "workplace_visits_test.csv",
    index=False,
    encoding="utf-8-sig",
)


# =========================================================
# 内容確認
# =========================================================

print(workplace_visits)

print()
print(
    "職場見学テストデータを生成しました。"
)

print(
    f"件数: {len(workplace_visits)}"
)


print()
print("職場見学ステータス")

print(
    workplace_visits[
        "visit_status"
    ].value_counts()
)


print()
print("職場見学結果")

print(
    workplace_visits[
        "result"
    ].value_counts(
        dropna=False
    )
)