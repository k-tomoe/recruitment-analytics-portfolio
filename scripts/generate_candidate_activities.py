from pathlib import Path

import numpy as np
import pandas as pd


# =========================================================
# 基本設定
# =========================================================

OUTPUT_DIR = Path("data/raw")

rng = np.random.default_rng(46)

DATA_END_DATE = pd.Timestamp("2026-09-30")


# =========================================================
# 元データ読み込み
# =========================================================

candidates = pd.read_csv(
    OUTPUT_DIR / "candidates_test.csv",
    parse_dates=[
        "registration_date",
        "search_end_date",
    ],
)

recruiters = pd.read_csv(
    OUTPUT_DIR / "recruiters.csv",
    parse_dates=[
        "join_date",
        "leave_date",
    ],
)


# =========================================================
# 指定日に稼働中のCAを取得する関数
# =========================================================

def get_active_ca(target_date):

    active_ca = recruiters[
        (recruiters["role_type"] == "CA")
        & (
            recruiters["join_date"]
            <= target_date
        )
        & (
            recruiters["leave_date"].isna()
            |
            (
                recruiters["leave_date"]
                >= target_date
            )
        )
    ]

    return active_ca[
        "recruiter_id"
    ].tolist()


# =========================================================
# 候補者対応履歴を生成
# =========================================================

activity_data = []

activity_counter = 1


for _, candidate in candidates.iterrows():

    candidate_id = candidate[
        "candidate_id"
    ]

    registration_date = candidate[
        "registration_date"
    ]

    search_end_date = candidate[
        "search_end_date"
    ]


    # =====================================================
    # この候補者の対応可能最終日
    # =====================================================

    if pd.notna(search_end_date):
        activity_limit_date = (
            search_end_date
        )
    else:
        activity_limit_date = (
            DATA_END_DATE
        )


    # =====================================================
    # 初回連絡日
    # =====================================================

    # 2026年は担当負荷増加を想定し、
    # 初回連絡まで若干時間がかかる
    if registration_date.year == 2025:

        contact_delay = int(
            rng.integers(
                0,
                4,
            )
        )

    else:

        contact_delay = int(
            rng.integers(
                1,
                6,
            )
        )


    initial_contact_date = (
        registration_date
        + pd.Timedelta(
            days=contact_delay
        )
    )


    # 求職期間終了後なら対応履歴を作らない
    if (
        initial_contact_date
        > activity_limit_date
    ):
        continue


    # =====================================================
    # CA担当者
    # =====================================================

    existing_ca = candidate["ca_id"]


    if pd.notna(existing_ca):

        ca_id = existing_ca

    else:

        active_ca_ids = get_active_ca(
            initial_contact_date
        )

        if len(active_ca_ids) == 0:
            continue

        ca_id = rng.choice(
            active_ca_ids
        )


    # =====================================================
    # 初回連絡
    # =====================================================

    activity_id = (
        f"ACT{activity_counter:05d}"
    )

    activity_data.append(
        [
            activity_id,
            candidate_id,
            initial_contact_date,
            "initial_contact",
            ca_id,
        ]
    )

    activity_counter += 1


    # =====================================================
    # 初回面談
    # =====================================================

    # 全員が初回面談まで進むわけではない
    has_interview = (
        rng.random() < 0.85
    )

    if not has_interview:
        continue


    if registration_date.year == 2025:

        interview_delay = int(
            rng.integers(
                1,
                6,
            )
        )

    else:

        interview_delay = int(
            rng.integers(
                2,
                9,
            )
        )


    initial_interview_date = (
        initial_contact_date
        + pd.Timedelta(
            days=interview_delay
        )
    )


    if (
        initial_interview_date
        > activity_limit_date
    ):
        continue


    activity_id = (
        f"ACT{activity_counter:05d}"
    )

    activity_data.append(
        [
            activity_id,
            candidate_id,
            initial_interview_date,
            "initial_interview",
            ca_id,
        ]
    )

    activity_counter += 1


    # =====================================================
    # フォロー対応
    # =====================================================

    # 0～2回のフォロー
    n_follow_ups = int(
        rng.choice(
            [0, 1, 2],
            p=[
                0.30,
                0.50,
                0.20,
            ],
        )
    )

    previous_activity_date = (
        initial_interview_date
    )


    for _ in range(n_follow_ups):

        follow_up_delay = int(
            rng.integers(
                7,
                22,
            )
        )

        follow_up_date = (
            previous_activity_date
            + pd.Timedelta(
                days=follow_up_delay
            )
        )


        if (
            follow_up_date
            > activity_limit_date
        ):
            break


        activity_id = (
            f"ACT{activity_counter:05d}"
        )

        activity_data.append(
            [
                activity_id,
                candidate_id,
                follow_up_date,
                "follow_up",
                ca_id,
            ]
        )

        activity_counter += 1

        previous_activity_date = (
            follow_up_date
        )


# =========================================================
# DataFrame化
# =========================================================

candidate_activities = pd.DataFrame(
    activity_data,
    columns=[
        "activity_id",
        "candidate_id",
        "activity_date",
        "activity_type",
        "ca_id",
    ],
)


# =========================================================
# データ品質チェック
# =========================================================

assert candidate_activities[
    "activity_id"
].is_unique


assert candidate_activities[
    "candidate_id"
].isin(
    candidates["candidate_id"]
).all()


assert candidate_activities[
    "activity_type"
].isin(
    [
        "initial_contact",
        "initial_interview",
        "follow_up",
    ]
).all()


# CAであることを確認
ca_master = recruiters[
    recruiters["role_type"] == "CA"
]

assert candidate_activities[
    "ca_id"
].isin(
    ca_master[
        "recruiter_id"
    ]
).all()


# 登録日より前の対応がないこと
activity_check = (
    candidate_activities.merge(
        candidates[
            [
                "candidate_id",
                "registration_date",
                "search_end_date",
            ]
        ],
        on="candidate_id",
        how="left",
    )
)

assert (
    activity_check[
        "activity_date"
    ]
    >=
    activity_check[
        "registration_date"
    ]
).all()


# 求職終了後の対応がないこと
ended_check = activity_check[
    activity_check[
        "search_end_date"
    ].notna()
]

assert (
    ended_check[
        "activity_date"
    ]
    <=
    ended_check[
        "search_end_date"
    ]
).all()


# =========================================================
# CSV出力
# =========================================================

candidate_activities.to_csv(
    OUTPUT_DIR
    / "candidate_activities_test.csv",
    index=False,
    encoding="utf-8-sig",
)


# =========================================================
# 内容確認
# =========================================================

print(candidate_activities)

print()
print(
    "候補者対応履歴テストデータを生成しました。"
)

print(
    f"件数: {len(candidate_activities)}"
)


print()
print("対応種別別件数")

print(
    candidate_activities[
        "activity_type"
    ].value_counts()
)


print()
print("候補者ごとの対応件数")

print(
    candidate_activities[
        "candidate_id"
    ].value_counts().sort_index()
)