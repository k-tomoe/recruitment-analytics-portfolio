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
# 修正① 指定したCAが活動日時点で稼働中か確認する関数
# =========================================================
#
# 【変更前】
# candidatesにca_idが入っている場合、
# そのCAを初回連絡・初回面談・フォローまで
# 継続して利用していた。
#
# 【問題点】
# candidatesのca_idは登録日時点で在籍しているCAを
# 割り当てているが、その後CAが離任した場合でも、
# 後日のcandidate_activitiesで同じCAが
# 担当し続ける可能性があった。
#
# 特にfollow_upは登録から数週間後になることがあるため、
# activity_date時点ではすでに離任済みのCAが
# 活動履歴に残る可能性がある。
#
# 【修正仕様】
# ・各activity_date時点でCAが稼働中か確認する
# ・現在のCAが稼働中なら同じCAを継続する
# ・離任済みの場合は、その日時点で稼働中のCAへ変更する
# ・稼働中CAが存在しない場合は、その活動を生成しない
#
# ---------------------------------------------------------
# 変更後コード
# ---------------------------------------------------------

def is_ca_active(
    ca_id,
    target_date,
):

    if pd.isna(ca_id):
        return False

    matching_ca = recruiters[
        (
            recruiters["recruiter_id"]
            == ca_id
        )
        &
        (
            recruiters["role_type"]
            == "CA"
        )
        &
        (
            recruiters["join_date"]
            <= target_date
        )
        &
        (
            recruiters["leave_date"].isna()
            |
            (
                recruiters["leave_date"]
                >= target_date
            )
        )
    ]

    return len(matching_ca) > 0


# =========================================================
# 修正① 活動日時点の担当CAを取得する関数
# =========================================================

def get_activity_ca(
    current_ca_id,
    target_date,
):

    # 現在の担当CAが活動日時点でも稼働中なら継続
    if is_ca_active(
        current_ca_id,
        target_date,
    ):
        return current_ca_id


    # 現在の担当CAが存在しない、
    # または離任済みの場合は
    # 活動日時点で稼働中のCAから再割当
    active_ca_ids = get_active_ca(
        target_date
    )


    if len(active_ca_ids) == 0:
        return None


    return rng.choice(
        active_ca_ids
    )


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

    if pd.notna(
        search_end_date
    ):

        activity_limit_date = min(
            search_end_date,
            DATA_END_DATE,
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


    # 求職期間終了後、
    # またはデータ観察終了後なら対応履歴を作らない
    if (
        initial_contact_date
        > activity_limit_date
    ):
        continue


    # =====================================================
    # 修正① 初回連絡日時点のCA担当者
    # =====================================================
    #
    # 【変更前】
    #
    # existing_ca = candidate["ca_id"]
    #
    # if pd.notna(existing_ca):
    #
    #     ca_id = existing_ca
    #
    # else:
    #
    #     active_ca_ids = get_active_ca(
    #         initial_contact_date
    #     )
    #
    #     if len(active_ca_ids) == 0:
    #         continue
    #
    #     ca_id = rng.choice(
    #         active_ca_ids
    #     )
    #
    #
    # 【問題点】
    # candidateにCAが設定されていれば、
    # initial_contact_date時点で離任済みでも
    # そのCAが利用される可能性があった。
    #
    # 【修正仕様】
    # initial_contact_date時点でCAが稼働中か確認し、
    # 必要なら再割当する。
    #
    # -----------------------------------------------------
    # 変更後コード
    # -----------------------------------------------------

    existing_ca = candidate[
        "ca_id"
    ]


    ca_id = get_activity_ca(
        existing_ca,
        initial_contact_date,
    )


    if ca_id is None:
        continue


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


    # =====================================================
    # 修正① 初回面談日時点のCA確認
    # =====================================================

    ca_id = get_activity_ca(
        ca_id,
        initial_interview_date,
    )


    if ca_id is None:
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


    for _ in range(
        n_follow_ups
    ):

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


        # =================================================
        # 修正① フォロー日時点のCA確認
        # =================================================
        #
        # フォロー日までに現在の担当CAが離任していた場合は、
        # その日時点で稼働中のCAへ再割当する。

        ca_id = get_activity_ca(
            ca_id,
            follow_up_date,
        )


        if ca_id is None:
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
    candidates[
        "candidate_id"
    ]
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
    recruiters[
        "role_type"
    ]
    == "CA"
]

assert candidate_activities[
    "ca_id"
].isin(
    ca_master[
        "recruiter_id"
    ]
).all()


# =========================================================
# 登録日・求職終了日との整合性
# =========================================================

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


# 登録日より前の対応がないこと
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


# データ観察終了日を超えていないこと
assert (
    candidate_activities[
        "activity_date"
    ]
    <= DATA_END_DATE
).all()


# =========================================================
# 修正①に対する追加品質チェック
# CAがactivity_date時点で稼働中であること
# =========================================================

activity_ca_check = (
    candidate_activities.merge(
        recruiters[
            [
                "recruiter_id",
                "role_type",
                "join_date",
                "leave_date",
            ]
        ],
        left_on="ca_id",
        right_on="recruiter_id",
        how="left",
    )
)


# CA以外が活動担当になっていないこと
assert (
    activity_ca_check[
        "role_type"
    ]
    == "CA"
).all()


# CA着任日以降の活動であること
assert (
    activity_ca_check[
        "activity_date"
    ]
    >=
    activity_ca_check[
        "join_date"
    ]
).all()


# 離任済みCAについては、
# 離任日以前の活動であること
left_ca_activities = (
    activity_ca_check[
        activity_ca_check[
            "leave_date"
        ].notna()
    ]
)


assert (
    left_ca_activities[
        "activity_date"
    ]
    <=
    left_ca_activities[
        "leave_date"
    ]
).all()


# =========================================================
# 活動順序の品質チェック
# =========================================================

activity_order = {
    "initial_contact": 1,
    "initial_interview": 2,
    "follow_up": 3,
}


candidate_activities_check = (
    candidate_activities.copy()
)

candidate_activities_check[
    "activity_order"
] = (
    candidate_activities_check[
        "activity_type"
    ].map(
        activity_order
    )
)


candidate_activities_check = (
    candidate_activities_check
    .sort_values(
        [
            "candidate_id",
            "activity_date",
            "activity_order",
        ]
    )
)


# 各候補者の最初の活動は
# initial_contactであること
first_activities = (
    candidate_activities_check
    .groupby(
        "candidate_id"
    )
    .first()
)


assert (
    first_activities[
        "activity_type"
    ]
    == "initial_contact"
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

print(
    candidate_activities
)

print()

print(
    "候補者対応履歴テストデータを生成しました。"
)

print(
    f"件数: {len(candidate_activities)}"
)


print()
print(
    "対応種別別件数"
)

print(
    candidate_activities[
        "activity_type"
    ].value_counts()
)


print()
print(
    "候補者ごとの対応件数"
)

print(
    candidate_activities[
        "candidate_id"
    ].value_counts().sort_index()
)


# =========================================================
# 修正①の内容確認
# =========================================================

print()
print(
    "CA担当者別活動件数"
)

print(
    candidate_activities[
        "ca_id"
    ].value_counts().sort_index()
)


print()
print(
    "活動日時点のCA在籍状況確認"
)

print(
    activity_ca_check[
        [
            "activity_id",
            "candidate_id",
            "activity_type",
            "activity_date",
            "ca_id",
            "join_date",
            "leave_date",
        ]
    ].sort_values(
        [
            "activity_date",
            "candidate_id",
        ]
    )
)