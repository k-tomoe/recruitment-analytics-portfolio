from pathlib import Path

import numpy as np
import pandas as pd


# =========================================================
# 基本設定
# =========================================================

OUTPUT_DIR = Path("data/raw")

rng = np.random.default_rng(47)

DATA_END_DATE = pd.Timestamp("2026-09-30")


# =========================================================
# 元データ読み込み
# =========================================================

candidate_activities = pd.read_csv(
    OUTPUT_DIR / "candidate_activities_test.csv",
    parse_dates=[
        "activity_date",
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

jobs = pd.read_csv(
    OUTPUT_DIR / "jobs_test.csv",
    parse_dates=[
        "open_date",
        "close_date",
    ],
)

occupations = pd.read_csv(
    OUTPUT_DIR / "occupations.csv"
)

locations = pd.read_csv(
    OUTPUT_DIR / "locations.csv"
)


# =========================================================
# 補助辞書
# =========================================================

occupation_group_map = dict(
    zip(
        occupations["occupation_id"],
        occupations["occupation_group"],
    )
)

area_group_map = dict(
    zip(
        locations["location_id"],
        locations["area_group"],
    )
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
        matching_rows["skill_level"].max()
    )


# =========================================================
# 求人紹介候補のスコア計算
# =========================================================

def calculate_job_score(
    candidate_id,
    preference,
    job,
):

    score = 0.0

    preferred_occupation_id = (
        preference["preferred_occupation_id"]
    )

    preferred_location_id = (
        preference["preferred_location_id"]
    )

    preferred_work_style = (
        preference["preferred_work_style"]
    )

    desired_wage = float(
        preference["desired_hourly_wage"]
    )

    job_occupation_id = (
        job["occupation_id"]
    )

    job_location_id = (
        job["location_id"]
    )

    offered_wage = float(
        job["offered_hourly_wage"]
    )

    # -----------------------------------------------------
    # 職種
    # -----------------------------------------------------

    if (
        preferred_occupation_id
        == job_occupation_id
    ):
        score += 5.0

    elif (
        occupation_group_map[
            preferred_occupation_id
        ]
        ==
        occupation_group_map[
            job_occupation_id
        ]
    ):
        score += 1.5


    # -----------------------------------------------------
    # 勤務地
    # -----------------------------------------------------

    if (
        preferred_location_id
        == job_location_id
    ):
        score += 2.0

    elif (
        area_group_map[
            preferred_location_id
        ]
        ==
        area_group_map[
            job_location_id
        ]
    ):
        score += 0.8


    # -----------------------------------------------------
    # 給与
    # -----------------------------------------------------

    wage_gap_ratio = (
        offered_wage
        - desired_wage
    ) / desired_wage

    if wage_gap_ratio >= 0:
        score += 2.0

    elif wage_gap_ratio >= -0.05:
        score += 1.2

    elif wage_gap_ratio >= -0.10:
        score += 0.5


    # -----------------------------------------------------
    # 勤務形態
    # -----------------------------------------------------

    if (
        preferred_work_style
        == job["work_style"]
    ):
        score += 0.4


    # -----------------------------------------------------
    # スキル
    # -----------------------------------------------------

    candidate_skill = get_candidate_skill(
        candidate_id,
        job_occupation_id,
    )

    if candidate_skill is not None:

        skill_gap = (
            candidate_skill
            - int(
                job[
                    "required_skill_level"
                ]
            )
        )

        if skill_gap >= 0:
            score += 2.0

        elif skill_gap == -1:
            score += 0.8

        elif skill_gap <= -2:
            score -= 0.8

    else:

        # 未経験職種
        score -= 0.8


    return score


# =========================================================
# 求人紹介履歴生成
# =========================================================

introduction_data = []

introduction_counter = 1


# 求人紹介を行う活動だけ対象
introduction_activities = (
    candidate_activities[
        candidate_activities[
            "activity_type"
        ].isin(
            [
                "initial_interview",
                "follow_up",
            ]
        )
    ]
)


for _, activity in introduction_activities.iterrows():

    activity_id = activity[
        "activity_id"
    ]

    candidate_id = activity[
        "candidate_id"
    ]

    activity_date = activity[
        "activity_date"
    ]


    # =====================================================
    # その時点の希望条件
    # =====================================================

    preference = get_active_preference(
        candidate_id,
        activity_date,
    )

    if preference is None:
        continue


    # =====================================================
    # 活動日時点で公開済みの求人
    # =====================================================

    available_jobs = jobs[
        (
            jobs["open_date"]
            <= activity_date
        )
        &
        (
            jobs["close_date"].isna()
            |
            (
                jobs["close_date"]
                >= activity_date
            )
        )
    ].copy()


    if len(available_jobs) == 0:
        continue


    # =====================================================
    # 各求人に紹介スコアを付与
    # =====================================================

    available_jobs["match_score"] = (
        available_jobs.apply(
            lambda job: calculate_job_score(
                candidate_id,
                preference,
                job,
            ),
            axis=1,
        )
    )


    # スコアが一定以上の求人だけ候補
    available_jobs = (
        available_jobs[
            available_jobs["match_score"]
            >= 1.0
        ]
        .sort_values(
            "match_score",
            ascending=False,
        )
    )


    if len(available_jobs) == 0:
        continue


    # =====================================================
    # 1活動あたり1～3件紹介
    # =====================================================

    n_introductions = int(
        rng.choice(
            [1, 2, 3],
            p=[
                0.45,
                0.40,
                0.15,
            ],
        )
    )

    n_introductions = min(
        n_introductions,
        len(available_jobs),
    )


    # 上位候補から少しランダム性を持たせる
    candidate_pool = available_jobs.head(
        min(
            5,
            len(available_jobs),
        )
    )

    selected_indices = rng.choice(
        candidate_pool.index,
        size=n_introductions,
        replace=False,
    )


    selected_jobs = (
        candidate_pool.loc[
            selected_indices
        ]
    )


    # =====================================================
    # 紹介求人ごとに候補者回答を生成
    # =====================================================

    for _, job in selected_jobs.iterrows():

        match_score = float(
            job["match_score"]
        )

        # スコアが高いほど応募意向が強い
        if match_score >= 7.0:

            response_probs = [
                0.65,
                0.25,
                0.10,
            ]

        elif match_score >= 4.0:

            response_probs = [
                0.40,
                0.40,
                0.20,
            ]

        else:

            response_probs = [
                0.20,
                0.45,
                0.35,
            ]


        candidate_response = rng.choice(
            [
                "apply",
                "considering",
                "decline",
            ],
            p=response_probs,
        )


        introduction_id = (
            f"INT{introduction_counter:05d}"
        )


        introduction_data.append(
            [
                introduction_id,
                activity_id,
                job["job_id"],
                candidate_response,
            ]
        )


        introduction_counter += 1


# =========================================================
# DataFrame化
# =========================================================

job_introductions = pd.DataFrame(
    introduction_data,
    columns=[
        "introduction_id",
        "activity_id",
        "job_id",
        "candidate_response",
    ],
)


# =========================================================
# データ品質チェック
# =========================================================

assert job_introductions[
    "introduction_id"
].is_unique


assert job_introductions[
    "activity_id"
].isin(
    candidate_activities[
        "activity_id"
    ]
).all()


assert job_introductions[
    "job_id"
].isin(
    jobs[
        "job_id"
    ]
).all()


assert job_introductions[
    "candidate_response"
].isin(
    [
        "apply",
        "considering",
        "decline",
    ]
).all()


# 同一活動内で同じ求人を
# 2回紹介していないこと
assert not job_introductions.duplicated(
    subset=[
        "activity_id",
        "job_id",
    ]
).any()


# 紹介元activityが
# interview / follow_upのみ
introduction_check = (
    job_introductions.merge(
        candidate_activities[
            [
                "activity_id",
                "activity_type",
                "activity_date",
            ]
        ],
        on="activity_id",
        how="left",
    )
)

assert introduction_check[
    "activity_type"
].isin(
    [
        "initial_interview",
        "follow_up",
    ]
).all()


# 求人公開後に紹介されていること
introduction_check = (
    introduction_check.merge(
        jobs[
            [
                "job_id",
                "open_date",
            ]
        ],
        on="job_id",
        how="left",
    )
)

assert (
    introduction_check[
        "activity_date"
    ]
    >=
    introduction_check[
        "open_date"
    ]
).all()


# =========================================================
# CSV出力
# =========================================================

job_introductions.to_csv(
    OUTPUT_DIR
    / "job_introductions_test.csv",
    index=False,
    encoding="utf-8-sig",
)


# =========================================================
# 内容確認
# =========================================================

print(job_introductions)

print()
print(
    "求人紹介履歴テストデータを生成しました。"
)

print(
    f"件数: {len(job_introductions)}"
)

print()
print("候補者回答別件数")

print(
    job_introductions[
        "candidate_response"
    ].value_counts()
)

print()
print("活動ごとの紹介求人件数")

print(
    job_introductions[
        "activity_id"
    ].value_counts().sort_index()
)