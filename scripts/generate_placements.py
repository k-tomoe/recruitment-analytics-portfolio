from pathlib import Path

import numpy as np
import pandas as pd


# =========================================================
# 基本設定
# =========================================================

OUTPUT_DIR = Path("data/raw")

rng = np.random.default_rng(50)

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

workplace_visits = pd.read_csv(
    OUTPUT_DIR / "workplace_visits_test.csv",
    parse_dates=[
        "scheduled_date",
        "visit_date",
    ],
)

jobs = pd.read_csv(
    OUTPUT_DIR / "jobs_test.csv",
    parse_dates=[
        "open_date",
        "close_date",
    ],
)

candidates = pd.read_csv(
    OUTPUT_DIR / "candidates_test.csv",
    parse_dates=[
        "registration_date",
        "search_end_date",
    ],
)

candidate_preferences = pd.read_csv(
    OUTPUT_DIR / "candidate_preferences_test.csv",
    parse_dates=[
        "effective_from",
        "effective_to",
    ],
)

candidate_experiences = pd.read_csv(
    OUTPUT_DIR / "candidate_experiences_test.csv",
    parse_dates=[
        "start_date",
        "end_date",
    ],
)


# =========================================================
# 指定日時点の希望条件を取得
# =========================================================

def get_active_preference(
    candidate_id,
    target_date,
):

    preference_rows = candidate_preferences[
        (
            candidate_preferences["candidate_id"]
            == candidate_id
        )
        &
        (
            candidate_preferences["effective_from"]
            <= target_date
        )
        &
        (
            candidate_preferences["effective_to"].isna()
            |
            (
                candidate_preferences["effective_to"]
                >= target_date
            )
        )
    ]

    if len(preference_rows) == 0:
        return None

    return preference_rows.iloc[0]


# =========================================================
# 求職者の職種別スキルを取得
# =========================================================

def get_candidate_skill(
    candidate_id,
    occupation_id,
):

    matching_rows = candidate_experiences[
        (
            candidate_experiences["candidate_id"]
            == candidate_id
        )
        &
        (
            candidate_experiences["occupation_id"]
            == occupation_id
        )
    ]

    if len(matching_rows) == 0:
        return None

    return int(
        matching_rows[
            "skill_level"
        ].max()
    )


# =========================================================
# 就業決定候補を作成
# =========================================================

placement_candidates = (
    workplace_visits[
        (
            workplace_visits["visit_status"]
            == "completed"
        )
        &
        (
            workplace_visits["result"]
            == "continue"
        )
    ]
    .merge(
        applications,
        on="application_id",
        how="inner",
    )
    .merge(
        jobs[
            [
                "job_id",
                "occupation_id",
                "required_slots",
                "offered_hourly_wage",
                "open_date",
            ]
        ],
        on="job_id",
        how="left",
    )
)


# 時系列順に判定
placement_candidates = (
    placement_candidates
    .sort_values(
        "visit_date"
    )
    .reset_index(
        drop=True
    )
)


# =========================================================
# 就業決定データ生成
# =========================================================

placement_data = []

placement_counter = 1

# 今回のMVPでは1求職者につき就業決定1件まで
placed_candidates = set()

# 求人ごとの決定人数
job_placement_counts = {}


for _, row in placement_candidates.iterrows():

    application_id = row[
        "application_id"
    ]

    candidate_id = row[
        "candidate_id"
    ]

    job_id = row[
        "job_id"
    ]

    visit_date = row[
        "visit_date"
    ]

    intent_confirmed_date = row[
        "intent_confirmed_date"
    ]


    # =====================================================
    # 既に別求人で就業決定済みならスキップ
    # =====================================================

    if candidate_id in placed_candidates:
        continue


    # =====================================================
    # 募集枠上限チェック
    # =====================================================

    current_placements = (
        job_placement_counts.get(
            job_id,
            0,
        )
    )

    required_slots = int(
        row[
            "required_slots"
        ]
    )

    if (
        current_placements
        >= required_slots
    ):
        continue


    # =====================================================
    # 希望条件
    # =====================================================

    preference = get_active_preference(
        candidate_id,
        intent_confirmed_date,
    )

    if preference is None:
        continue


    desired_wage = float(
        preference[
            "desired_hourly_wage"
        ]
    )

    offered_wage = float(
        row[
            "offered_hourly_wage"
        ]
    )


    # =====================================================
    # 給与条件ギャップ
    # =====================================================

    wage_gap_ratio = (
        offered_wage
        - desired_wage
    ) / desired_wage


    # =====================================================
    # スキルギャップ
    # =====================================================

    candidate_skill = (
        get_candidate_skill(
            candidate_id,
            row[
                "occupation_id"
            ],
        )
    )

    if candidate_skill is None:

        skill_gap = -3

    else:

        job_row = jobs[
            jobs["job_id"]
            == job_id
        ].iloc[0]

        required_skill_level = int(
            job_row[
                "required_skill_level"
            ]
        )

        skill_gap = (
            candidate_skill
            - required_skill_level
        )


    # =====================================================
    # 選考リードタイム
    # =====================================================

    process_days = (
        visit_date
        - intent_confirmed_date
    ).days


    # =====================================================
    # 就業決定確率
    # =====================================================

    placement_probability = 0.72


    # -----------------------------------------------------
    # 給与条件
    # -----------------------------------------------------

    if wage_gap_ratio >= 0:

        placement_probability += 0.08

    elif wage_gap_ratio >= -0.05:

        placement_probability += 0.03

    elif wage_gap_ratio >= -0.10:

        placement_probability -= 0.05

    elif wage_gap_ratio >= -0.15:

        placement_probability -= 0.12

    else:

        placement_probability -= 0.20


    # -----------------------------------------------------
    # スキル条件
    # -----------------------------------------------------

    if skill_gap >= 0:

        placement_probability += 0.08

    elif skill_gap == -1:

        placement_probability -= 0.04

    elif skill_gap == -2:

        placement_probability -= 0.12

    else:

        placement_probability -= 0.20


    # -----------------------------------------------------
    # 選考スピード
    # -----------------------------------------------------

    if process_days <= 7:

        placement_probability += 0.05

    elif process_days <= 14:

        pass

    elif process_days <= 21:

        placement_probability -= 0.08

    else:

        placement_probability -= 0.15


    # -----------------------------------------------------
    # ランダム性を残しつつ、
    # 極端な確率にならないよう制限
    # -----------------------------------------------------

    placement_probability = float(
        np.clip(
            placement_probability,
            0.15,
            0.92,
        )
    )


    # =====================================================
    # 就業決定判定
    # =====================================================

    is_placed = (
        rng.random()
        < placement_probability
    )

    if not is_placed:
        continue


    # =====================================================
    # 就業決定日
    # =====================================================

    decision_delay = int(
        rng.integers(
            1,
            6,
        )
    )

    decision_date = (
        visit_date
        + pd.Timedelta(
            days=decision_delay
        )
    )


    if decision_date > DATA_END_DATE:
        continue


    # =====================================================
    # 就業時給
    # =====================================================

    # 基本的には求人提示時給を起点にする
    agreed_hourly_wage = (
        offered_wage
    )


    # 候補者希望の方が高い場合は、
    # 一部だけ条件調整が成立するケースを作る
    if desired_wage > offered_wage:

        wage_difference = (
            desired_wage
            - offered_wage
        )

        adjustment_ratio = rng.uniform(
            0.0,
            0.50,
        )

        agreed_hourly_wage += (
            wage_difference
            * adjustment_ratio
        )


    # 50円単位に丸める
    agreed_hourly_wage = int(
        round(
            agreed_hourly_wage
            / 50
        )
        * 50
    )


    # =====================================================
    # 就業開始予定日
    # =====================================================

    start_delay = int(
        rng.integers(
            7,
            31,
        )
    )

    start_date = (
        decision_date
        + pd.Timedelta(
            days=start_delay
        )
    )


    # =====================================================
    # 就業ステータス
    # =====================================================

    if (
        start_date
        <= DATA_END_DATE
    ):

        status = "started"

    else:

        status = "planned"


    # =====================================================
    # レコード追加
    # =====================================================

    placement_id = (
        f"PLC{placement_counter:05d}"
    )


    placement_data.append(
        [
            placement_id,
            application_id,
            decision_date,
            start_date,
            agreed_hourly_wage,
            status,
        ]
    )


    placed_candidates.add(
        candidate_id
    )

    job_placement_counts[
        job_id
    ] = (
        current_placements + 1
    )


    placement_counter += 1


# =========================================================
# DataFrame化
# =========================================================

placements = pd.DataFrame(
    placement_data,
    columns=[
        "placement_id",
        "application_id",
        "decision_date",
        "start_date",
        "agreed_hourly_wage",
        "status",
    ],
)


# =========================================================
# データ品質チェック
# =========================================================

assert placements[
    "placement_id"
].is_unique


# 1応募案件につき就業決定は最大1件
assert placements[
    "application_id"
].is_unique


assert placements[
    "application_id"
].isin(
    applications[
        "application_id"
    ]
).all()


assert placements[
    "agreed_hourly_wage"
].gt(0).all()


assert placements[
    "status"
].isin(
    [
        "planned",
        "started",
        "cancelled",
    ]
).all()


# =========================================================
# 就業決定日は応募意思確認日以降
# =========================================================

placement_check = (
    placements.merge(
        applications[
            [
                "application_id",
                "candidate_id",
                "job_id",
                "intent_confirmed_date",
            ]
        ],
        on="application_id",
        how="left",
    )
)


assert (
    placement_check[
        "decision_date"
    ]
    >=
    placement_check[
        "intent_confirmed_date"
    ]
).all()


# =========================================================
# 開始日は就業決定日以降
# =========================================================

assert (
    placements[
        "start_date"
    ]
    >=
    placements[
        "decision_date"
    ]
).all()


# =========================================================
# 今回は1求職者1就業決定まで
# =========================================================

assert not placement_check.duplicated(
    subset=[
        "candidate_id"
    ]
).any()


# =========================================================
# 求人募集枠数を超えていないこと
# =========================================================

job_placement_check = (
    placement_check.groupby(
        "job_id"
    )
    .size()
    .reset_index(
        name="placement_count"
    )
    .merge(
        jobs[
            [
                "job_id",
                "required_slots",
            ]
        ],
        on="job_id",
        how="left",
    )
)


assert (
    job_placement_check[
        "placement_count"
    ]
    <=
    job_placement_check[
        "required_slots"
    ]
).all()


# =========================================================
# applicationsのstatus更新
# =========================================================

placed_application_ids = (
    placements[
        "application_id"
    ].tolist()
)


applications.loc[
    applications[
        "application_id"
    ].isin(
        placed_application_ids
    ),
    "status",
] = "placed"


# =========================================================
# candidatesのstatus更新
# =========================================================

candidate_placements = (
    placement_check[
        [
            "candidate_id",
            "decision_date",
        ]
    ]
    .sort_values(
        "decision_date"
    )
    .drop_duplicates(
        subset=[
            "candidate_id"
        ],
        keep="first",
    )
)


for _, placed_candidate in (
    candidate_placements.iterrows()
):

    candidate_id = (
        placed_candidate[
            "candidate_id"
        ]
    )

    decision_date = (
        placed_candidate[
            "decision_date"
        ]
    )

    candidates.loc[
        candidates[
            "candidate_id"
        ]
        == candidate_id,
        "status",
    ] = "placed"

    candidates.loc[
        candidates[
            "candidate_id"
        ]
        == candidate_id,
        "search_end_date",
    ] = decision_date


# =========================================================
# CSV出力
# =========================================================

placements.to_csv(
    OUTPUT_DIR
    / "placements_test.csv",
    index=False,
    encoding="utf-8-sig",
)


# applications更新
applications.to_csv(
    OUTPUT_DIR
    / "applications_test.csv",
    index=False,
    encoding="utf-8-sig",
)


# candidates更新
candidates.to_csv(
    OUTPUT_DIR
    / "candidates_test.csv",
    index=False,
    encoding="utf-8-sig",
)


# =========================================================
# 内容確認
# =========================================================

print(placements)

print()
print(
    "就業決定テストデータを生成しました。"
)

print(
    f"件数: {len(placements)}"
)


print()
print("就業ステータス")

print(
    placements[
        "status"
    ].value_counts()
)


print()
print("応募案件ステータス更新後")

print(
    applications[
        "status"
    ].value_counts()
)


print()
print("求職者ステータス更新後")

print(
    candidates[
        "status"
    ].value_counts()
)


print()
print("求人別就業決定数")

print(
    placement_check[
        "job_id"
    ].value_counts().sort_index()
)