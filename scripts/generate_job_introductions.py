from pathlib import Path

import numpy as np
import pandas as pd


# =========================================================
# 基本設定
# =========================================================

OUTPUT_DIR = Path("data/raw")
REVIEW_DIR = Path("data/review")

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

REVIEW_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

OUTPUT_FILE = (
    OUTPUT_DIR
    / "job_introductions.csv"
)

REVIEW_FILE = (
    REVIEW_DIR
    / "job_introductions_review.csv"
)

# このスクリプト専用の乱数シード
#
# 分析結果を確認した後で、
# 都合のよいseedへ変更しない。
SEED = 47

rng = np.random.default_rng(
    SEED
)

DATA_END_DATE = pd.Timestamp(
    "2026-09-30"
)


# =========================================================
# 元データ読み込み
# =========================================================
#
# 【変更前】
#
# candidate_activities_test.csv
# candidates_test.csv
# candidate_preferences_test.csv
# candidate_experiences_test.csv
# jobs_test.csv
#
#
# 【問題点】
#
# 小規模テスト用ファイルを参照していた。
#
#
# 【修正仕様】
#
# 分析用正式データへ切り替える。
# =========================================================

candidate_activities = pd.read_csv(
    OUTPUT_DIR
    / "candidate_activities.csv",
    parse_dates=[
        "activity_date",
    ],
)

candidates = pd.read_csv(
    OUTPUT_DIR
    / "candidates.csv",
    parse_dates=[
        "registration_date",
        "search_end_date",
    ],
)

candidate_preferences = pd.read_csv(
    OUTPUT_DIR
    / "candidate_preferences.csv",
    parse_dates=[
        "effective_from",
        "effective_to",
    ],
)

candidate_experiences = pd.read_csv(
    OUTPUT_DIR
    / "candidate_experiences.csv",
    parse_dates=[
        "start_date",
        "end_date",
    ],
)

jobs = pd.read_csv(
    OUTPUT_DIR
    / "jobs.csv",
    parse_dates=[
        "open_date",
        "close_date",
    ],
)

recruiters = pd.read_csv(
    OUTPUT_DIR
    / "recruiters.csv",
    parse_dates=[
        "join_date",
        "leave_date",
    ],
)

occupations = pd.read_csv(
    OUTPUT_DIR
    / "occupations.csv"
)

locations = pd.read_csv(
    OUTPUT_DIR
    / "locations.csv"
)


# =========================================================
# 入力データの基本品質チェック
# =========================================================

assert candidate_activities[
    "activity_id"
].is_unique

assert candidates[
    "candidate_id"
].is_unique

assert jobs[
    "job_id"
].is_unique

assert recruiters[
    "recruiter_id"
].is_unique

assert candidate_activities[
    "candidate_id"
].isin(
    candidates[
        "candidate_id"
    ]
).all()


# =========================================================
# 補助辞書
# =========================================================

occupation_group_map = dict(
    zip(
        occupations[
            "occupation_id"
        ],
        occupations[
            "occupation_group"
        ],
    )
)

area_group_map = dict(
    zip(
        locations[
            "location_id"
        ],
        locations[
            "area_group"
        ],
    )
)


# =========================================================
# 修正① 希望条件検索を高速化
# =========================================================
#
# 【変更前】
#
# get_active_preference()を呼ぶたびに、
# candidate_preferences全体を検索していた。
#
#
# 【問題点】
#
# 1,950候補者規模では、
# 求人紹介活動が数千件になるため、
# 同じDataFrame検索を繰り返すと処理効率が悪い。
#
#
# 【修正仕様】
#
# candidate_idごとに希望条件を事前に分割しておき、
# 対象候補者の希望条件だけを検索する。
# =========================================================

preferences_by_candidate = {
    candidate_id:
        group.sort_values(
            "effective_from"
        ).copy()

    for candidate_id, group
    in candidate_preferences.groupby(
        "candidate_id"
    )
}


def get_active_preference(
    candidate_id,
    target_date,
):

    candidate_pref = (
        preferences_by_candidate.get(
            candidate_id
        )
    )

    if candidate_pref is None:
        return None

    preference_rows = (
        candidate_pref[
            (
                candidate_pref[
                    "effective_from"
                ]
                <=
                target_date
            )
            &
            (
                candidate_pref[
                    "effective_to"
                ].isna()
                |
                (
                    candidate_pref[
                        "effective_to"
                    ]
                    >=
                    target_date
                )
            )
        ]
    )

    if len(
        preference_rows
    ) == 0:

        return None

    return (
        preference_rows.iloc[0]
    )


# =========================================================
# 修正② 候補者スキル検索を高速化
# =========================================================
#
# 【変更前】
#
# 求人を1件評価するたびに、
#
# candidate_experiences[
#     candidate_id × occupation_id
# ]
#
# を検索していた。
#
#
# 【問題点】
#
# 数千回の活動 × 数百求人を評価するため、
# 同じ検索を大量に繰り返すことになる。
#
#
# 【修正仕様】
#
# candidate_id × occupation_idごとの
# 最大skill_levelを事前に集計し、
# 辞書から取得する。
#
# 分析結果そのものは変えず、
# 処理効率のみ改善する。
# =========================================================

candidate_skill_lookup = (
    candidate_experiences
    .groupby(
        [
            "candidate_id",
            "occupation_id",
        ]
    )[
        "skill_level"
    ]
    .max()
    .to_dict()
)


def get_candidate_skill(
    candidate_id,
    occupation_id,
):

    skill = (
        candidate_skill_lookup.get(
            (
                candidate_id,
                occupation_id,
            )
        )
    )

    if skill is None:
        return None

    return int(
        skill
    )


# =========================================================
# H1用：月別CA負荷を計算
# =========================================================
#
# 【変更前】
#
# CA負荷は求人紹介件数へ直接影響していなかった。
#
#
# 【問題点】
#
# H1では、
#
# 候補者・求人需要の増加
# ↓
# CA1人あたり負荷増加
# ↓
# 紹介処理能力が追いつきにくくなる
#
# という関係を確認したい。
#
#
# 【修正仕様】
#
# candidate_activities.pyと同じ考え方で、
#
# 月内アクティブ候補者数
# ÷
# 月内稼働CA数
#
# を計算する。
#
# 負荷が高いほど、
# interview / follow_upが発生していても
# 求人紹介まで実施できない確率を
# わずかに高くする。
#
# ただしplacement等の最終結果を
# CA負荷から直接決めることはしない。
# =========================================================

def get_active_ca_count(
    target_date,
):

    active_ca = recruiters[
        (
            recruiters[
                "role_type"
            ]
            ==
            "CA"
        )
        &
        (
            recruiters[
                "join_date"
            ]
            <=
            target_date
        )
        &
        (
            recruiters[
                "leave_date"
            ].isna()
            |
            (
                recruiters[
                    "leave_date"
                ]
                >=
                target_date
            )
        )
    ]

    return len(
        active_ca
    )


analysis_months = pd.period_range(
    start="2025-01",
    end="2026-09",
    freq="M",
)

monthly_ca_workload_data = []


for month in analysis_months:

    month_start = (
        month.to_timestamp()
    )

    month_end = (
        month.to_timestamp(
            how="end"
        ).normalize()
    )

    if (
        month_end
        >
        DATA_END_DATE
    ):

        month_end = (
            DATA_END_DATE
        )


    active_candidate_count = int(
        (
            (
                candidates[
                    "registration_date"
                ]
                <=
                month_end
            )
            &
            (
                candidates[
                    "search_end_date"
                ].isna()
                |
                (
                    candidates[
                        "search_end_date"
                    ]
                    >=
                    month_start
                )
            )
        ).sum()
    )


    active_ca_count = (
        get_active_ca_count(
            month_end
        )
    )

    assert (
        active_ca_count
        >
        0
    )


    active_candidates_per_ca = (
        active_candidate_count
        /
        active_ca_count
    )


    monthly_ca_workload_data.append(
        [
            month,
            active_candidate_count,
            active_ca_count,
            active_candidates_per_ca,
        ]
    )


monthly_ca_workload = pd.DataFrame(
    monthly_ca_workload_data,
    columns=[
        "month",
        "active_candidate_count",
        "active_ca_count",
        "active_candidates_per_ca",
    ],
)


baseline_mask = (
    (
        monthly_ca_workload[
            "month"
        ]
        >=
        pd.Period(
            "2025-04",
            freq="M",
        )
    )
    &
    (
        monthly_ca_workload[
            "month"
        ]
        <=
        pd.Period(
            "2025-12",
            freq="M",
        )
    )
)


BASELINE_CA_LOAD = float(
    monthly_ca_workload.loc[
        baseline_mask,
        "active_candidates_per_ca",
    ].median()
)


assert (
    BASELINE_CA_LOAD
    >
    0
)


monthly_ca_workload[
    "workload_ratio"
] = (
    monthly_ca_workload[
        "active_candidates_per_ca"
    ]
    /
    BASELINE_CA_LOAD
)


monthly_workload_ratio_map = dict(
    zip(
        monthly_ca_workload[
            "month"
        ],
        monthly_ca_workload[
            "workload_ratio"
        ],
    )
)


def get_ca_workload_ratio(
    target_date,
):

    target_month = (
        target_date.to_period(
            "M"
        )
    )

    return float(
        monthly_workload_ratio_map.get(
            target_month,
            1.0,
        )
    )


# =========================================================
# 修正③ 求人紹介を実施できる確率
# =========================================================
#
# 基準では約90%のinterview/follow_upで
# 何らかの求人紹介を試みる。
#
# CA負荷が基準を超えた場合だけ、
# その確率を少し下げる。
#
# 例：
#
# workload_ratio = 1.0
# → 約90%
#
# workload_ratio = 1.3
# → 約82～83%
#
# 程度。
#
# H1を強く作り込みすぎないよう、
# 下限は70%とする。
# =========================================================

def get_introduction_capacity_probability(
    activity_date,
):

    workload_ratio = (
        get_ca_workload_ratio(
            activity_date
        )
    )

    excess_load = max(
        0.0,
        workload_ratio
        - 1.0,
    )

    probability = (
        0.90
        -
        (
            excess_load
            * 0.25
        )
    )

    return float(
        np.clip(
            probability,
            0.70,
            0.90,
        )
    )


# =========================================================
# CA紹介対象求人のスキル条件
# =========================================================
#
# 【変更前】
#
# 小規模テスト修正後、
#
# required_skill_level >= 3
# かつ
# 同職種経験なし
#
# の候補者は紹介対象外としていた。
#
#
# 【問題点】
#
# このルール自体には問題が確認されていない。
#
#
# 【修正仕様】
#
# 分析用データでも維持する。
#
# 高スキル求人では同職種経験を要求する一方、
# skill_gapがマイナスの経験者は
# 紹介候補として残す。
#
# これにより、
#
# 「同職種経験なし」
#
# と
#
# 「同職種経験ありだがスキル不足」
#
# を分けてH3で分析できる。
# =========================================================

def is_skill_eligible_for_introduction(
    candidate_id,
    job,
):

    required_skill_level = int(
        job[
            "required_skill_level"
        ]
    )

    candidate_skill = (
        get_candidate_skill(
            candidate_id,
            job[
                "occupation_id"
            ],
        )
    )


    if (
        required_skill_level
        >=
        3
        and
        candidate_skill is None
    ):

        return False


    return True


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
        preference[
            "preferred_occupation_id"
        ]
    )

    preferred_location_id = (
        preference[
            "preferred_location_id"
        ]
    )

    preferred_work_style = (
        preference[
            "preferred_work_style"
        ]
    )

    desired_wage = float(
        preference[
            "desired_hourly_wage"
        ]
    )


    job_occupation_id = (
        job[
            "occupation_id"
        ]
    )

    job_location_id = (
        job[
            "location_id"
        ]
    )

    offered_wage = float(
        job[
            "offered_hourly_wage"
        ]
    )


    # -----------------------------------------------------
    # 1. 職種
    # -----------------------------------------------------

    exact_occupation_match = (
        preferred_occupation_id
        ==
        job_occupation_id
    )

    same_occupation_group = (
        occupation_group_map[
            preferred_occupation_id
        ]
        ==
        occupation_group_map[
            job_occupation_id
        ]
    )


    if exact_occupation_match:

        score += 5.0

    elif same_occupation_group:

        score += 1.5


    # -----------------------------------------------------
    # 2. 勤務地
    # -----------------------------------------------------

    exact_location_match = (
        preferred_location_id
        ==
        job_location_id
    )

    same_area_group = (
        area_group_map[
            preferred_location_id
        ]
        ==
        area_group_map[
            job_location_id
        ]
    )


    if exact_location_match:

        score += 2.0

    elif same_area_group:

        score += 0.8


    # -----------------------------------------------------
    # 3. 給与
    # -----------------------------------------------------

    wage_gap_ratio = (
        offered_wage
        -
        desired_wage
    ) / desired_wage


    if wage_gap_ratio >= 0:

        score += 2.0

    elif wage_gap_ratio >= -0.05:

        score += 1.2

    elif wage_gap_ratio >= -0.10:

        score += 0.5

    elif wage_gap_ratio < -0.20:

        score -= 0.5


    # -----------------------------------------------------
    # 4. 勤務形態
    # -----------------------------------------------------
    #
    # 【変更前】
    #
    # preferred_work_style
    # ==
    # job["work_style"]
    #
    # ならscore +0.4
    #
    #
    # 【問題点】
    #
    # H6を「支持されなかった仮説」として
    # 探索したいため、
    # work_styleそのものに結果を
    # 直接作り込まない方がよい。
    #
    #
    # 【修正仕様】
    #
    # work_style_matchは確認用に算出するが、
    # match_scoreへは加点しない。
    # -----------------------------------------------------

    work_style_match = (
        preferred_work_style
        ==
        job[
            "work_style"
        ]
    )


    # -----------------------------------------------------
    # 5. スキル
    # -----------------------------------------------------

    candidate_skill = (
        get_candidate_skill(
            candidate_id,
            job_occupation_id,
        )
    )


    if candidate_skill is not None:

        skill_gap = (
            candidate_skill
            -
            int(
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

        skill_gap = None

        # required_skill <= 2なら
        # 未経験者も紹介可能だが、
        # 経験者より優先順位は低い。
        score -= 0.8


    return {
        "match_score":
            score,

        "candidate_skill":
            candidate_skill,

        "skill_gap":
            skill_gap,

        "wage_gap_ratio":
            wage_gap_ratio,

        "exact_occupation_match":
            exact_occupation_match,

        "same_occupation_group":
            same_occupation_group,

        "exact_location_match":
            exact_location_match,

        "same_area_group":
            same_area_group,

        "work_style_match":
            work_style_match,

        "desired_wage":
            desired_wage,

        "offered_wage":
            offered_wage,
    }


# =========================================================
# 求人紹介履歴生成
# =========================================================

introduction_data = []

review_data = []

introduction_counter = 1


# =========================================================
# 修正④ candidate × job の重複紹介防止
# =========================================================
#
# 【変更前】
#
# 同一activity内では同じ求人を
# 2回紹介しなかったが、
#
# initial_interview
# ↓
# follow_up
#
# の別activityでは、
# 同じ候補者へ同じ求人を
# 再紹介する可能性があった。
#
#
# 【問題点】
#
# 分析用データではfollow_up件数が増えるため、
# 同一求人の重複紹介が多くなりやすい。
#
#
# 【修正仕様】
#
# candidate_id × job_idごとに、
# 1回だけ紹介する。
# =========================================================

introduced_candidate_job_pairs = set()


# 求人紹介対象activity
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
    .sort_values(
        [
            "activity_date",
            "candidate_id",
        ]
    )
)


for _, activity in (
    introduction_activities.iterrows()
):

    activity_id = (
        activity[
            "activity_id"
        ]
    )

    candidate_id = (
        activity[
            "candidate_id"
        ]
    )

    activity_date = (
        activity[
            "activity_date"
        ]
    )


    # =====================================================
    # H1：CA負荷による紹介処理キャパシティ
    # =====================================================

    capacity_probability = (
        get_introduction_capacity_probability(
            activity_date
        )
    )


    does_process_introduction = (
        rng.random()
        <
        capacity_probability
    )


    if not does_process_introduction:
        continue


    # =====================================================
    # その時点の希望条件
    # =====================================================

    preference = (
        get_active_preference(
            candidate_id,
            activity_date,
        )
    )


    if preference is None:
        continue


    # =====================================================
    # 活動日時点で紹介可能な求人
    # =====================================================
    #
    # open_date <= activity_date
    #
    # かつ
    #
    # close_dateがNULL
    # または
    # activity_date <= close_date
    #
    # を満たす求人。
    # =====================================================

    available_jobs = jobs[
        (
            jobs[
                "open_date"
            ]
            <=
            activity_date
        )
        &
        (
            jobs[
                "close_date"
            ].isna()
            |
            (
                activity_date
                <=
                jobs[
                    "close_date"
                ]
            )
        )
    ].copy()


    if len(
        available_jobs
    ) == 0:

        continue


    # =====================================================
    # 過去に同じ候補者へ紹介済みの求人を除外
    # =====================================================

    already_introduced_job_ids = {
        job_id
        for pair_candidate_id, job_id
        in introduced_candidate_job_pairs
        if (
            pair_candidate_id
            ==
            candidate_id
        )
    }


    if len(
        already_introduced_job_ids
    ) > 0:

        available_jobs = (
            available_jobs[
                ~available_jobs[
                    "job_id"
                ].isin(
                    already_introduced_job_ids
                )
            ]
            .copy()
        )


    if len(
        available_jobs
    ) == 0:

        continue


    # =====================================================
    # 高スキル求人の経験条件
    # =====================================================

    available_jobs[
        "skill_eligible"
    ] = (
        available_jobs.apply(
            lambda job:
                is_skill_eligible_for_introduction(
                    candidate_id,
                    job,
                ),
            axis=1,
        )
    )


    available_jobs = (
        available_jobs[
            available_jobs[
                "skill_eligible"
            ]
        ]
        .copy()
    )


    if len(
        available_jobs
    ) == 0:

        continue


    # =====================================================
    # 各求人へmatch_scoreを付与
    # =====================================================

    score_results = (
        available_jobs.apply(
            lambda job:
                calculate_job_score(
                    candidate_id,
                    preference,
                    job,
                ),
            axis=1,
        )
    )


    score_result_df = pd.DataFrame(
        score_results.tolist(),
        index=available_jobs.index,
    )


    available_jobs = pd.concat(
        [
            available_jobs,
            score_result_df,
        ],
        axis=1,
    )


    # -----------------------------------------------------
    # 一定以上の求人だけ紹介候補
    # -----------------------------------------------------

    available_jobs = (
        available_jobs[
            available_jobs[
                "match_score"
            ]
            >=
            1.0
        ]
        .sort_values(
            "match_score",
            ascending=False,
        )
    )


    if len(
        available_jobs
    ) == 0:

        continue


    # =====================================================
    # 修正⑤ 1活動あたりの紹介件数
    # =====================================================
    #
    # 【変更前】
    #
    # 1件：45%
    # 2件：40%
    # 3件：15%
    #
    # 平均約1.7件
    #
    #
    # 【問題点】
    #
    # 分析用データではinterview/follow_upが
    # 数千回発生するため、
    # 同じ比率ではCA紹介件数が
    # 過剰になりやすい。
    #
    #
    # 【修正仕様】
    #
    # 1件：65%
    # 2件：30%
    # 3件： 5%
    #
    # 平均約1.4件。
    #
    # 最終的なapplicationsを
    # self_entryと合わせて
    # 2,000～3,000件程度へ
    # 自然に着地させることを狙う。
    # =====================================================

    n_introductions = int(
        rng.choice(
            [
                1,
                2,
                3,
            ],
            p=[
                0.65,
                0.30,
                0.05,
            ],
        )
    )


    n_introductions = min(
        n_introductions,
        len(
            available_jobs
        ),
    )


    # =====================================================
    # 上位候補求人から少しランダム性を持って選択
    # =====================================================
    #
    # 【変更前】
    #
    # 上位5件から一様ランダム選択。
    #
    #
    # 【修正仕様】
    #
    # 上位8件程度を候補とし、
    # match_score順位が高いほど
    # 少し選ばれやすくする。
    #
    # ただし1位求人が必ず選ばれる
    # 決定論にはしない。
    # =====================================================

    candidate_pool = (
        available_jobs.head(
            min(
                8,
                len(
                    available_jobs
                ),
            )
        )
    )


    # 上位ほど少し高い重み
    #
    # 8求人なら
    # 8,7,6,...,1
    #
    # のような重み。
    ranking_weights = np.arange(
        len(
            candidate_pool
        ),
        0,
        -1,
        dtype=float,
    )


    ranking_weights = (
        ranking_weights
        /
        ranking_weights.sum()
    )


    selected_indices = (
        rng.choice(
            candidate_pool.index.to_numpy(),
            size=n_introductions,
            replace=False,
            p=ranking_weights,
        )
    )


    selected_jobs = (
        candidate_pool.loc[
            selected_indices
        ]
    )


    # =====================================================
    # 紹介求人ごとに候補者回答を生成
    # =====================================================

    for _, job in (
        selected_jobs.iterrows()
    ):

        match_score = float(
            job[
                "match_score"
            ]
        )


        # -------------------------------------------------
        # match_scoreと応募意向
        # -------------------------------------------------
        #
        # 高スコアでも必ずapplyせず、
        # 低スコアでもapplyするケースを残す。
        # -------------------------------------------------

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


        candidate_response = (
            rng.choice(
                [
                    "apply",
                    "considering",
                    "decline",
                ],
                p=response_probs,
            )
        )


        introduction_id = (
            f"INT{introduction_counter:06d}"
        )


        introduction_data.append(
            [
                introduction_id,
                activity_id,
                job[
                    "job_id"
                ],
                candidate_response,
            ]
        )


        # -------------------------------------------------
        # review用
        # -------------------------------------------------

        review_data.append(
            [
                introduction_id,
                activity_id,
                candidate_id,
                job[
                    "job_id"
                ],
                activity_date,
                get_ca_workload_ratio(
                    activity_date
                ),
                capacity_probability,
                match_score,
                job[
                    "candidate_skill"
                ],
                job[
                    "required_skill_level"
                ],
                job[
                    "skill_gap"
                ],
                job[
                    "desired_wage"
                ],
                job[
                    "offered_wage"
                ],
                job[
                    "wage_gap_ratio"
                ],
                job[
                    "exact_occupation_match"
                ],
                job[
                    "same_occupation_group"
                ],
                job[
                    "exact_location_match"
                ],
                job[
                    "same_area_group"
                ],
                job[
                    "work_style_match"
                ],
                candidate_response,
            ]
        )


        introduced_candidate_job_pairs.add(
            (
                candidate_id,
                job[
                    "job_id"
                ],
            )
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


job_introductions_review = pd.DataFrame(
    review_data,
    columns=[
        "introduction_id",
        "activity_id",
        "candidate_id",
        "job_id",
        "activity_date",
        "ca_workload_ratio",
        "capacity_probability",
        "match_score",
        "candidate_skill_level",
        "required_skill_level",
        "skill_gap",
        "desired_hourly_wage",
        "offered_hourly_wage",
        "wage_gap_ratio",
        "occupation_exact_match",
        "same_occupation_group",
        "location_exact_match",
        "same_area_group",
        "work_style_match",
        "candidate_response",
    ],
)


# =========================================================
# データ品質チェック
# =========================================================

assert (
    len(
        job_introductions
    )
    >
    0
)


# ---------------------------------------------------------
# ID
# ---------------------------------------------------------

assert job_introductions[
    "introduction_id"
].is_unique


# ---------------------------------------------------------
# 外部キー
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# candidate_response
# ---------------------------------------------------------

assert job_introductions[
    "candidate_response"
].isin(
    [
        "apply",
        "considering",
        "decline",
    ]
).all()


# =========================================================
# activityとの結合
# =========================================================

introduction_check = (
    job_introductions.merge(
        candidate_activities[
            [
                "activity_id",
                "candidate_id",
                "activity_type",
                "activity_date",
            ]
        ],
        on="activity_id",
        how="left",
    )
)


# 紹介元activityは
# interview / follow_upのみ
assert introduction_check[
    "activity_type"
].isin(
    [
        "initial_interview",
        "follow_up",
    ]
).all()


# =========================================================
# 修正④ candidate × job 重複紹介チェック
# =========================================================

assert not (
    introduction_check.duplicated(
        subset=[
            "candidate_id",
            "job_id",
        ]
    ).any()
)


# =========================================================
# 求人情報を結合
# =========================================================

introduction_check = (
    introduction_check.merge(
        jobs[
            [
                "job_id",
                "open_date",
                "close_date",
                "required_skill_level",
                "occupation_id",
            ]
        ],
        on="job_id",
        how="left",
    )
)


# =========================================================
# 求人公開期間との整合性
# =========================================================

# 求人公開後
assert (
    introduction_check[
        "activity_date"
    ]
    >=
    introduction_check[
        "open_date"
    ]
).all()


# close_dateがある場合、
# close_date以前
closed_job_introductions = (
    introduction_check[
        introduction_check[
            "close_date"
        ].notna()
    ]
)


assert (
    closed_job_introductions[
        "activity_date"
    ]
    <=
    closed_job_introductions[
        "close_date"
    ]
).all()


# DATA_END_DATE以前
assert (
    introduction_check[
        "activity_date"
    ]
    <=
    DATA_END_DATE
).all()


# =========================================================
# 候補者求職期間との整合性
# =========================================================

introduction_check = (
    introduction_check.merge(
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
    introduction_check[
        "activity_date"
    ]
    >=
    introduction_check[
        "registration_date"
    ]
).all()


ended_candidate_introductions = (
    introduction_check[
        introduction_check[
            "search_end_date"
        ].notna()
    ]
)


assert (
    ended_candidate_introductions[
        "activity_date"
    ]
    <=
    ended_candidate_introductions[
        "search_end_date"
    ]
).all()


# =========================================================
# 高スキル求人で同職種経験があること
# =========================================================

high_skill_introductions = (
    introduction_check[
        introduction_check[
            "required_skill_level"
        ]
        >=
        3
    ]
)


for _, row in (
    high_skill_introductions.iterrows()
):

    candidate_skill = (
        get_candidate_skill(
            row[
                "candidate_id"
            ],
            row[
                "occupation_id"
            ],
        )
    )

    assert (
        candidate_skill
        is not None
    )


# =========================================================
# reviewデータとの件数一致
# =========================================================

assert (
    len(
        job_introductions
    )
    ==
    len(
        job_introductions_review
    )
)


# =========================================================
# CSV出力
# =========================================================
#
# 【変更前】
#
# job_introductions_test.csv
#
#
# 【修正仕様】
#
# job_introductions.csv
# =========================================================

job_introductions.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig",
)


job_introductions_review.to_csv(
    REVIEW_FILE,
    index=False,
    encoding="utf-8-sig",
)


# =========================================================
# 内容確認
# =========================================================
#
# 【変更前】
#
# 全紹介履歴をprintしていた。
#
#
# 【問題点】
#
# 数千行になる可能性があるため、
# 全件表示は確認しづらい。
#
#
# 【修正仕様】
#
# 件数・分布・統計量・サンプルを表示する。
# =========================================================

print(
    "分析用求人紹介履歴データを生成しました。"
)

print()

print(
    f"求人紹介件数: "
    f"{len(job_introductions):,}"
)


# =========================================================
# 候補者回答
# =========================================================

print()
print(
    "【候補者回答別件数】"
)

print(
    job_introductions[
        "candidate_response"
    ].value_counts()
)


print()
print(
    "【候補者回答別割合】"
)

print(
    job_introductions[
        "candidate_response"
    ].value_counts(
        normalize=True
    )
)


# =========================================================
# activityごとの紹介件数
# =========================================================

introductions_per_activity = (
    job_introductions
    .groupby(
        "activity_id"
    )
    .size()
)


print()
print(
    "【紹介が発生したactivity数】"
)

print(
    introductions_per_activity
    .index
    .nunique()
)


print()
print(
    "【紹介件数 / activity】"
)

print(
    introductions_per_activity
    .describe()
)


# =========================================================
# CA負荷と紹介
# =========================================================

print()
print(
    "【CA負荷比率の基本統計量】"
)

print(
    job_introductions_review[
        "ca_workload_ratio"
    ].describe()
)


print()
print(
    "【紹介処理可能確率の基本統計量】"
)

print(
    job_introductions_review[
        "capacity_probability"
    ].describe()
)


# =========================================================
# H3確認
# =========================================================

print()
print(
    "【紹介求人の要求スキルレベル】"
)

print(
    introduction_check[
        "required_skill_level"
    ]
    .value_counts()
    .sort_index()
)


print()
print(
    "【紹介時skill_gapの基本統計量】"
)

print(
    job_introductions_review[
        "skill_gap"
    ].describe()
)


print()
print(
    "【要求スキル3以上の紹介件数】"
)

print(
    len(
        high_skill_introductions
    )
)


# =========================================================
# H2確認
# =========================================================

print()
print(
    "【紹介時給与差率の基本統計量】"
)

print(
    job_introductions_review[
        "wage_gap_ratio"
    ].describe()
)


# =========================================================
# H6確認
# =========================================================

print()
print(
    "【勤務形態一致率】"
)

print(
    job_introductions_review[
        "work_style_match"
    ].mean()
)


# =========================================================
# 年次件数
# =========================================================

introduction_check[
    "introduction_year"
] = (
    introduction_check[
        "activity_date"
    ].dt.year
)


print()
print(
    "【紹介年別件数】"
)

print(
    introduction_check[
        "introduction_year"
    ]
    .value_counts()
    .sort_index()
)


# =========================================================
# サンプル表示
# =========================================================

print()
print(
    "【job_introductionsサンプル：先頭20件】"
)

print(
    job_introductions
    .head(
        20
    )
)


print()
print(
    "【reviewサンプル：先頭20件】"
)

print(
    job_introductions_review
    .sort_values(
        "activity_date"
    )
    .head(
        20
    )
)