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
    / "workplace_visits.csv"
)

REVIEW_FILE = (
    REVIEW_DIR
    / "workplace_visits_review.csv"
)

# このスクリプト専用の乱数シード
#
# 分析結果を見た後で、
# 都合のよいseedへ変更しない。
SEED = 49

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
# applications_test.csv
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
#
# また今回から、
#
# ・給与不足
# ・スキル適合度
# ・候補者の求職期間
#
# も利用するため、
#
# candidate_preferences.csv
# candidate_experiences.csv
# candidates.csv
#
# も読み込む。
# =========================================================

applications = pd.read_csv(
    OUTPUT_DIR
    / "applications.csv",
    parse_dates=[
        "intent_confirmed_date",
        "recommendation_date",
        "withdrawal_date",
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

recruiters = pd.read_csv(
    OUTPUT_DIR
    / "recruiters.csv",
    parse_dates=[
        "join_date",
        "leave_date",
    ],
)


# =========================================================
# 入力データの基本品質チェック
# =========================================================

assert applications[
    "application_id"
].is_unique

assert jobs[
    "job_id"
].is_unique

assert candidates[
    "candidate_id"
].is_unique

assert applications[
    "job_id"
].isin(
    jobs[
        "job_id"
    ]
).all()

assert applications[
    "candidate_id"
].isin(
    candidates[
        "candidate_id"
    ]
).all()


# =========================================================
# 検索高速化用データ
# =========================================================
#
# 【変更前】
#
# 20件程度のテストデータだったため、
# DataFrame検索を都度行っていた。
#
#
# 【問題点】
#
# 分析用データでは数百～数千件の
# 推薦案件を処理するため、
# 同じ検索を繰り返すと処理効率が悪い。
#
#
# 【修正仕様】
#
# job / candidate / preference / skillを
# 事前に検索しやすい形へ整理する。
# =========================================================

job_lookup = (
    jobs
    .set_index(
        "job_id"
    )
)

candidate_lookup = (
    candidates
    .set_index(
        "candidate_id"
    )
)

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


# =========================================================
# 指定日時点の希望条件を取得
# =========================================================

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
# 候補者の職種別スキルを取得
# =========================================================

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
# H1 / H5用：月別CA負荷
# =========================================================
#
# 【変更前】
#
# 職場見学設定までの日数を
#
# 2025年
# 2026年
#
# で直接変更していた。
#
#
# 【問題点】
#
# 「2026年だから遅い」
#
# という結果を直接生成していた。
#
#
# 【修正仕様】
#
# これまでのスクリプトと同じく、
#
# 月内アクティブ候補者数
# ÷
# 月内稼働CA数
#
# をCA負荷として利用する。
#
# CA負荷が高い場合、
# 推薦後の見学調整にも
# 数日の追加遅延が発生しやすくする。
#
# year自体は使用しない。
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
# 修正① 推薦→職場見学設定までの日数
# =========================================================
#
# 【変更前】
#
# 2025：
# 1～4日
#
# 2026：
# 2～7日
#
#
# 【問題点】
#
# 年を直接使ってプロセス長期化を作っていた。
#
#
# 【修正仕様】
#
# 基本日数：
# 1～4日
#
# ＋
#
# CA負荷が高い場合に
# 0～3日程度の追加遅延
#
# とする。
# =========================================================

def generate_schedule_delay(
    recommendation_date,
):

    base_delay = int(
        rng.integers(
            1,
            5,
        )
    )


    workload_ratio = (
        get_ca_workload_ratio(
            recommendation_date
        )
    )


    excess_load = max(
        0.0,
        workload_ratio
        -
        1.0,
    )


    workload_delay = int(
        rng.poisson(
            excess_load
            *
            3.0
        )
    )


    workload_delay = min(
        workload_delay,
        3,
    )


    return (
        base_delay
        +
        workload_delay
    )


# =========================================================
# 修正② 見学設定→実施までの日数
# =========================================================
#
# 【変更前】
#
# 2025：
# 2～5日
#
# 2026：
# 3～8日
#
#
# 【問題点】
#
# こちらもyearを直接原因としていた。
#
#
# 【修正仕様】
#
# 2～7日を基本とする。
#
# この区間は候補者・企業双方の日程都合も
# 大きいため、CA負荷の直接効果は入れない。
#
# これにより、
# H5のすべてをCA負荷だけで説明しない。
# =========================================================

def generate_visit_delay():

    return int(
        rng.integers(
            2,
            8,
        )
    )


# =========================================================
# 修正③ 推薦後辞退確率
# =========================================================
#
# 【変更前】
#
# cancelledの確率を、
#
# 2025：10%
# 2026：16%
#
# と年で直接変更していた。
#
#
# 【問題点】
#
# 「2026年だから辞退する」
#
# という構造になっていた。
#
#
# 【修正仕様】
#
# 推薦後辞退は、
#
# ・給与不足
# ・応募→推薦までの日数
# ・推薦→見学までの日数
#
# によって確率が変化する。
#
# 基本は5%程度。
#
# 条件が悪い場合に、
# 8～20%程度まで上昇し得る。
#
# ただし最大30%とし、
# 条件が悪くても全員が辞退する
# 決定論にはしない。
# =========================================================

def get_post_recommendation_withdrawal_probability(
    wage_shortfall_rate,
    intent_to_recommend_days,
    recommendation_to_visit_days,
):

    probability = 0.05


    # -----------------------------------------------------
    # H2 給与不足
    # -----------------------------------------------------

    if wage_shortfall_rate >= 0.15:

        probability += 0.06

    elif wage_shortfall_rate >= 0.10:

        probability += 0.04

    elif wage_shortfall_rate >= 0.05:

        probability += 0.02


    # -----------------------------------------------------
    # H5 応募→推薦
    # -----------------------------------------------------

    if intent_to_recommend_days >= 7:

        probability += 0.08

    elif intent_to_recommend_days >= 5:

        probability += 0.05

    elif intent_to_recommend_days >= 3:

        probability += 0.02


    # -----------------------------------------------------
    # H5 推薦→職場見学
    # -----------------------------------------------------

    if recommendation_to_visit_days >= 9:

        probability += 0.06

    elif recommendation_to_visit_days >= 7:

        probability += 0.04

    elif recommendation_to_visit_days >= 5:

        probability += 0.02


    return float(
        np.clip(
            probability,
            0.03,
            0.30,
        )
    )


# =========================================================
# 推薦後辞退理由
# =========================================================

def select_post_recommendation_withdrawal_reason(
    wage_shortfall_rate,
    intent_to_recommend_days,
    recommendation_to_visit_days,
):

    wage_issue = (
        wage_shortfall_rate
        >=
        0.10
    )


    delay_issue = (
        intent_to_recommend_days
        >=
        5
        or
        recommendation_to_visit_days
        >=
        7
    )


    if (
        wage_issue
        and
        delay_issue
    ):

        return rng.choice(
            [
                "wage",
                "process_delay",
                "other",
            ],
            p=[
                0.40,
                0.45,
                0.15,
            ],
        )


    if wage_issue:

        return rng.choice(
            [
                "wage",
                "other",
            ],
            p=[
                0.75,
                0.25,
            ],
        )


    if delay_issue:

        return rng.choice(
            [
                "process_delay",
                "other",
            ],
            p=[
                0.80,
                0.20,
            ],
        )


    return "other"


# =========================================================
# 修正④ 職場見学後の次工程継続確率
# =========================================================
#
# 【変更前】
#
# 基本72%
#
# 2026年のみ -4%
#
#
# 【問題点】
#
# ここでもyearが直接結果に影響していた。
#
#
# 【修正仕様】
#
# 見学後の結果は、
# 求人要求スキルと候補者同職種スキルの
# 適合度を主に利用する。
#
# これによりH3について、
#
# skill gap
# ↓
# 職場見学後の継続率
#
# も分析できる。
#
# yearは利用しない。
# =========================================================

def get_visit_continue_probability(
    candidate_skill,
    required_skill_level,
):

    # -----------------------------------------------------
    # 同職種経験なし
    # -----------------------------------------------------

    if candidate_skill is None:

        if (
            required_skill_level
            <=
            2
        ):

            return 0.60

        return 0.40


    # -----------------------------------------------------
    # 同職種経験あり
    # -----------------------------------------------------

    skill_gap = (
        candidate_skill
        -
        required_skill_level
    )


    if skill_gap >= 0:

        return 0.82

    elif skill_gap == -1:

        return 0.72

    elif skill_gap == -2:

        return 0.60

    else:

        return 0.48


# =========================================================
# 職場見学対象
# =========================================================
#
# recommendation_result == accepted
#
# かつ
#
# status == recommended
#
# の案件のみ対象。
#
# applications.py時点で既に
# pre_recommendation withdrawal等となった案件は
# 対象にならない。
# =========================================================

visit_candidates = applications[
    (
        applications[
            "recommendation_result"
        ]
        ==
        "accepted"
    )
    &
    (
        applications[
            "status"
        ]
        ==
        "recommended"
    )
].copy()


# =========================================================
# 職場見学データ生成
# =========================================================

visit_data = []

review_data = []

visit_counter = 1


for index, application in (
    visit_candidates.iterrows()
):

    application_id = (
        application[
            "application_id"
        ]
    )

    candidate_id = (
        application[
            "candidate_id"
        ]
    )

    job_id = (
        application[
            "job_id"
        ]
    )

    recommendation_date = (
        application[
            "recommendation_date"
        ]
    )

    intent_confirmed_date = (
        application[
            "intent_confirmed_date"
        ]
    )


    # recommendation_dateがないものは
    # この段階では異常
    assert pd.notna(
        recommendation_date
    )


    # =====================================================
    # 求人情報
    # =====================================================

    job = (
        job_lookup.loc[
            job_id
        ]
    )


    # =====================================================
    # H2 給与不足
    # =====================================================

    preference = (
        get_active_preference(
            candidate_id,
            recommendation_date,
        )
    )


    if preference is None:

        # 通常は発生しない想定だが、
        # 有効希望条件を取得できない場合は
        # 見学生成対象外とする。
        continue


    desired_wage = float(
        preference[
            "desired_hourly_wage"
        ]
    )

    offered_wage = float(
        job[
            "offered_hourly_wage"
        ]
    )


    wage_shortfall_rate = max(
        (
            desired_wage
            -
            offered_wage
        )
        /
        desired_wage,
        0.0,
    )


    # =====================================================
    # H3 スキル
    # =====================================================

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


    if candidate_skill is None:

        skill_gap = None

    else:

        skill_gap = (
            candidate_skill
            -
            required_skill_level
        )


    # =====================================================
    # H5 応募→推薦リードタイム
    # =====================================================

    intent_to_recommend_days = (
        recommendation_date
        -
        intent_confirmed_date
    ).days


    # =====================================================
    # 職場見学設定予定日
    # =====================================================

    schedule_delay = (
        generate_schedule_delay(
            recommendation_date
        )
    )


    planned_scheduled_date = (
        recommendation_date
        +
        pd.Timedelta(
            days=schedule_delay
        )
    )


    # =====================================================
    # 職場見学実施予定日
    # =====================================================

    visit_delay = (
        generate_visit_delay()
    )


    planned_visit_date = (
        planned_scheduled_date
        +
        pd.Timedelta(
            days=visit_delay
        )
    )


    recommendation_to_visit_days = (
        planned_visit_date
        -
        recommendation_date
    ).days


    # =====================================================
    # 修正③ 推薦後辞退判定
    # =====================================================

    post_recommendation_withdrawal_probability = (
        get_post_recommendation_withdrawal_probability(
            wage_shortfall_rate=(
                wage_shortfall_rate
            ),
            intent_to_recommend_days=(
                intent_to_recommend_days
            ),
            recommendation_to_visit_days=(
                recommendation_to_visit_days
            ),
        )
    )


    withdraws_after_recommendation = (
        rng.random()
        <
        post_recommendation_withdrawal_probability
    )


    # =====================================================
    # 推薦後辞退
    # =====================================================
    #
    # 推薦後～職場見学実施前のどこかで
    # 候補者が辞退した状態。
    #
    # scheduled_dateより前に辞退した場合：
    # → workplace_visit自体を作らない
    #
    # scheduled_date以降、
    # 実施前に辞退した場合：
    # → cancelled visitとして残す
    #
    # これにより、
    #
    # 「見学調整前辞退」
    #
    # と
    #
    # 「見学予定を入れた後のキャンセル」
    #
    # の両方を
    # post_recommendationとして扱える。
    # =====================================================

    if withdraws_after_recommendation:

        # 推薦翌日～見学予定日前までの期間
        #
        # visit予定が推薦翌日より後なら、
        # その範囲からランダムに辞退日を選択。
        withdrawal_window_days = max(
            1,
            (
                planned_visit_date
                -
                recommendation_date
            ).days,
        )


        withdrawal_delay = int(
            rng.integers(
                1,
                withdrawal_window_days + 1,
            )
        )


        withdrawal_date = (
            recommendation_date
            +
            pd.Timedelta(
                days=withdrawal_delay
            )
        )


        # データ観察期間後に起きる辞退は
        # 観察できないため辞退扱いしない。
        if (
            withdrawal_date
            <=
            DATA_END_DATE
        ):

            withdrawal_reason = (
                select_post_recommendation_withdrawal_reason(
                    wage_shortfall_rate=(
                        wage_shortfall_rate
                    ),
                    intent_to_recommend_days=(
                        intent_to_recommend_days
                    ),
                    recommendation_to_visit_days=(
                        recommendation_to_visit_days
                    ),
                )
            )


            # ---------------------------------------------
            # applicationsを更新
            # ---------------------------------------------

            application_row_index = (
                applications.index[
                    applications[
                        "application_id"
                    ]
                    ==
                    application_id
                ][0]
            )


            applications.loc[
                application_row_index,
                "withdrawal_date",
            ] = withdrawal_date


            applications.loc[
                application_row_index,
                "withdrawal_reason",
            ] = withdrawal_reason


            applications.loc[
                application_row_index,
                "withdrawal_stage",
            ] = (
                "post_recommendation"
            )


            applications.loc[
                application_row_index,
                "status",
            ] = "withdrawn"


            # ---------------------------------------------
            # 見学設定前に辞退
            # ---------------------------------------------

            if (
                withdrawal_date
                <
                planned_scheduled_date
            ):

                review_data.append(
                    [
                        application_id,
                        candidate_id,
                        job_id,
                        recommendation_date,
                        intent_to_recommend_days,
                        schedule_delay,
                        visit_delay,
                        recommendation_to_visit_days,
                        get_ca_workload_ratio(
                            recommendation_date
                        ),
                        wage_shortfall_rate,
                        candidate_skill,
                        required_skill_level,
                        skill_gap,
                        post_recommendation_withdrawal_probability,
                        True,
                        withdrawal_date,
                        "withdrawn_before_schedule",
                        None,
                    ]
                )

                continue


            # ---------------------------------------------
            # 見学設定後～実施前に辞退
            # ---------------------------------------------

            if (
                planned_scheduled_date
                <=
                DATA_END_DATE
            ):

                visit_id = (
                    f"VIS{visit_counter:06d}"
                )


                visit_data.append(
                    [
                        visit_id,
                        application_id,
                        planned_scheduled_date,
                        pd.NaT,
                        "cancelled",
                        None,
                    ]
                )


                visit_counter += 1


            review_data.append(
                [
                    application_id,
                    candidate_id,
                    job_id,
                    recommendation_date,
                    intent_to_recommend_days,
                    schedule_delay,
                    visit_delay,
                    recommendation_to_visit_days,
                    get_ca_workload_ratio(
                        recommendation_date
                    ),
                    wage_shortfall_rate,
                    candidate_skill,
                    required_skill_level,
                    skill_gap,
                    post_recommendation_withdrawal_probability,
                    True,
                    withdrawal_date,
                    "withdrawn_after_schedule",
                    None,
                ]
            )

            continue


    # =====================================================
    # 推薦後辞退しなかった場合
    # =====================================================

    # -----------------------------------------------------
    # 見学設定日が観察期間外
    # -----------------------------------------------------
    #
    # 未来のscheduled_dateは記録しない。
    #
    # applicationはrecommendedのまま残り、
    # 観察期間末時点で
    # 「推薦通過後・見学設定前」の案件となる。
    # -----------------------------------------------------

    if (
        planned_scheduled_date
        >
        DATA_END_DATE
    ):

        review_data.append(
            [
                application_id,
                candidate_id,
                job_id,
                recommendation_date,
                intent_to_recommend_days,
                schedule_delay,
                visit_delay,
                recommendation_to_visit_days,
                get_ca_workload_ratio(
                    recommendation_date
                ),
                wage_shortfall_rate,
                candidate_skill,
                required_skill_level,
                skill_gap,
                post_recommendation_withdrawal_probability,
                False,
                pd.NaT,
                "right_censored_before_schedule",
                None,
            ]
        )

        continue


    # =====================================================
    # 見学設定済み
    # =====================================================

    scheduled_date = (
        planned_scheduled_date
    )


    # -----------------------------------------------------
    # 実施予定日が観察期間外
    # -----------------------------------------------------

    if (
        planned_visit_date
        >
        DATA_END_DATE
    ):

        visit_id = (
            f"VIS{visit_counter:06d}"
        )


        visit_data.append(
            [
                visit_id,
                application_id,
                scheduled_date,
                pd.NaT,
                "scheduled",
                None,
            ]
        )


        visit_counter += 1


        review_data.append(
            [
                application_id,
                candidate_id,
                job_id,
                recommendation_date,
                intent_to_recommend_days,
                schedule_delay,
                visit_delay,
                recommendation_to_visit_days,
                get_ca_workload_ratio(
                    recommendation_date
                ),
                wage_shortfall_rate,
                candidate_skill,
                required_skill_level,
                skill_gap,
                post_recommendation_withdrawal_probability,
                False,
                pd.NaT,
                "scheduled_right_censored",
                None,
            ]
        )

        continue


    # =====================================================
    # 職場見学実施
    # =====================================================

    actual_visit_date = (
        planned_visit_date
    )


    # =====================================================
    # 見学後の次工程継続判定
    # =====================================================

    continue_probability = (
        get_visit_continue_probability(
            candidate_skill=(
                candidate_skill
            ),
            required_skill_level=(
                required_skill_level
            ),
        )
    )


    continues_after_visit = (
        rng.random()
        <
        continue_probability
    )


    if continues_after_visit:

        result = "continue"

    else:

        result = "decline"


    # =====================================================
    # レコード追加
    # =====================================================

    visit_id = (
        f"VIS{visit_counter:06d}"
    )


    visit_data.append(
        [
            visit_id,
            application_id,
            scheduled_date,
            actual_visit_date,
            "completed",
            result,
        ]
    )


    visit_counter += 1


    review_data.append(
        [
            application_id,
            candidate_id,
            job_id,
            recommendation_date,
            intent_to_recommend_days,
            schedule_delay,
            visit_delay,
            recommendation_to_visit_days,
            get_ca_workload_ratio(
                recommendation_date
            ),
            wage_shortfall_rate,
            candidate_skill,
            required_skill_level,
            skill_gap,
            post_recommendation_withdrawal_probability,
            False,
            pd.NaT,
            "completed",
            continue_probability,
        ]
    )


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


workplace_visits_review = pd.DataFrame(
    review_data,
    columns=[
        "application_id",
        "candidate_id",
        "job_id",
        "recommendation_date",
        "intent_to_recommend_days",
        "recommendation_to_schedule_days",
        "schedule_to_visit_days",
        "recommendation_to_visit_days",
        "ca_workload_ratio",
        "wage_shortfall_rate",
        "candidate_skill_level",
        "required_skill_level",
        "skill_gap",
        "post_recommendation_withdrawal_probability",
        "post_recommendation_withdrawal",
        "withdrawal_date",
        "process_state",
        "visit_continue_probability",
    ],
)


# =========================================================
# データ品質チェック
# =========================================================

# 見学が1件以上生成されること
assert (
    len(
        workplace_visits
    )
    >
    0
)


# ---------------------------------------------------------
# ID
# ---------------------------------------------------------

assert workplace_visits[
    "visit_id"
].is_unique


# ---------------------------------------------------------
# application
# ---------------------------------------------------------

assert workplace_visits[
    "application_id"
].isin(
    applications[
        "application_id"
    ]
).all()


# applicationごとに見学は最大1件
assert not workplace_visits.duplicated(
    subset=[
        "application_id",
    ]
).any()


# ---------------------------------------------------------
# status
# ---------------------------------------------------------

assert workplace_visits[
    "visit_status"
].isin(
    [
        "scheduled",
        "completed",
        "cancelled",
    ]
).all()


# =========================================================
# completed
# =========================================================

completed_rows = (
    workplace_visits[
        workplace_visits[
            "visit_status"
        ]
        ==
        "completed"
    ]
)


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


# =========================================================
# cancelled
# =========================================================

cancelled_rows = (
    workplace_visits[
        workplace_visits[
            "visit_status"
        ]
        ==
        "cancelled"
    ]
)


assert cancelled_rows[
    "visit_date"
].isna().all()


assert cancelled_rows[
    "result"
].isna().all()


# =========================================================
# scheduled
# =========================================================

scheduled_rows = (
    workplace_visits[
        workplace_visits[
            "visit_status"
        ]
        ==
        "scheduled"
    ]
)


assert scheduled_rows[
    "visit_date"
].isna().all()


assert scheduled_rows[
    "result"
].isna().all()


# =========================================================
# 職場見学対象の整合性
# =========================================================

visit_application_check = (
    workplace_visits.merge(
        applications[
            [
                "application_id",
                "status",
                "recommendation_date",
                "recommendation_result",
                "withdrawal_stage",
                "withdrawal_date",
            ]
        ],
        on="application_id",
        how="left",
    )
)


# workplace_visitが存在する案件は、
# 企業推薦結果accepted
assert (
    visit_application_check[
        "recommendation_result"
    ]
    ==
    "accepted"
).all()


# =========================================================
# 推薦後辞退とcancelledの整合性
# =========================================================

cancelled_application_check = (
    visit_application_check[
        visit_application_check[
            "visit_status"
        ]
        ==
        "cancelled"
    ]
)


assert (
    cancelled_application_check[
        "status"
    ]
    ==
    "withdrawn"
).all()


assert (
    cancelled_application_check[
        "withdrawal_stage"
    ]
    ==
    "post_recommendation"
).all()


assert cancelled_application_check[
    "withdrawal_date"
].notna().all()


# =========================================================
# completed / scheduledは推薦後辞退していない
# =========================================================

non_cancelled_application_check = (
    visit_application_check[
        visit_application_check[
            "visit_status"
        ].isin(
            [
                "scheduled",
                "completed",
            ]
        )
    ]
)


assert non_cancelled_application_check[
    "withdrawal_stage"
].isna().all()


# =========================================================
# 日付整合性
# =========================================================

visit_check = (
    workplace_visits.merge(
        applications[
            [
                "application_id",
                "recommendation_date",
            ]
        ],
        on="application_id",
        how="left",
    )
)


# 設定日は推薦日以降
assert (
    visit_check[
        "scheduled_date"
    ]
    >=
    visit_check[
        "recommendation_date"
    ]
).all()


# 設定日は観察期間内
assert (
    visit_check[
        "scheduled_date"
    ]
    <=
    DATA_END_DATE
).all()


# 実施済みの場合、
# visit_date >= scheduled_date
completed_check = (
    visit_check[
        visit_check[
            "visit_date"
        ].notna()
    ]
)


assert (
    completed_check[
        "visit_date"
    ]
    >=
    completed_check[
        "scheduled_date"
    ]
).all()


assert (
    completed_check[
        "visit_date"
    ]
    <=
    DATA_END_DATE
).all()


# =========================================================
# applicationsの辞退ステージ品質チェック
# =========================================================

assert applications[
    "withdrawal_stage"
].dropna().isin(
    [
        "pre_recommendation",
        "post_recommendation",
    ]
).all()


# pre_recommendationでは推薦日なし
pre_recommendation_rows = (
    applications[
        applications[
            "withdrawal_stage"
        ]
        ==
        "pre_recommendation"
    ]
)


assert pre_recommendation_rows[
    "recommendation_date"
].isna().all()


# post_recommendationでは推薦日・acceptedが必要
post_recommendation_rows = (
    applications[
        applications[
            "withdrawal_stage"
        ]
        ==
        "post_recommendation"
    ]
)


assert post_recommendation_rows[
    "recommendation_date"
].notna().all()


assert (
    post_recommendation_rows[
        "recommendation_result"
    ]
    ==
    "accepted"
).all()


assert post_recommendation_rows[
    "withdrawal_date"
].notna().all()


assert (
    post_recommendation_rows[
        "withdrawal_date"
    ]
    >=
    post_recommendation_rows[
        "recommendation_date"
    ]
).all()


# =========================================================
# CSV出力
# =========================================================
#
# 【変更前】
#
# workplace_visits_test.csv
#
#
# 【修正仕様】
#
# workplace_visits.csv
#
# また、post_recommendation辞退を反映した
# applications.csvも上書きする。
# =========================================================

workplace_visits.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig",
)


applications.to_csv(
    OUTPUT_DIR
    / "applications.csv",
    index=False,
    encoding="utf-8-sig",
)


workplace_visits_review.to_csv(
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
# workplace_visits全件をprintしていた。
#
#
# 【問題点】
#
# 分析用データでは数百件になるため、
# 全件表示は確認しづらい。
#
#
# 【修正仕様】
#
# 件数・分布・リードタイム・辞退率・
# スキル分布などを集計して表示する。
# =========================================================

print(
    "分析用職場見学データを生成しました。"
)

print()

print(
    f"職場見学レコード数: "
    f"{len(workplace_visits):,}"
)


# =========================================================
# ステータス
# =========================================================

print()
print(
    "【職場見学ステータス】"
)

print(
    workplace_visits[
        "visit_status"
    ].value_counts()
)


print()
print(
    "【職場見学結果】"
)

print(
    workplace_visits[
        "result"
    ].value_counts(
        dropna=False
    )
)


# =========================================================
# 推薦後辞退
# =========================================================

accepted_recommendation_count = (
    (
        applications[
            "recommendation_result"
        ]
        ==
        "accepted"
    ).sum()
)


post_recommendation_withdrawal_count = (
    (
        applications[
            "withdrawal_stage"
        ]
        ==
        "post_recommendation"
    ).sum()
)


if (
    accepted_recommendation_count
    >
    0
):

    post_recommendation_withdrawal_rate = (
        post_recommendation_withdrawal_count
        /
        accepted_recommendation_count
    )

else:

    post_recommendation_withdrawal_rate = (
        np.nan
    )


print()
print(
    "【推薦後辞退】"
)

print(
    f"推薦accepted件数: "
    f"{accepted_recommendation_count:,}"
)

print(
    f"推薦後辞退件数: "
    f"{post_recommendation_withdrawal_count:,}"
)

print(
    "推薦後辞退率: "
    f"{post_recommendation_withdrawal_rate:.1%}"
)


# =========================================================
# H5 リードタイム
# =========================================================

workplace_visits_review[
    "recommendation_year"
] = (
    workplace_visits_review[
        "recommendation_date"
    ].dt.year
)


print()
print(
    "【推薦年別：応募→推薦日数】"
)

print(
    workplace_visits_review
    .groupby(
        "recommendation_year"
    )[
        "intent_to_recommend_days"
    ]
    .agg(
        [
            "count",
            "mean",
            "median",
            "std",
        ]
    )
)


print()
print(
    "【推薦年別：推薦→見学設定日数】"
)

print(
    workplace_visits_review
    .groupby(
        "recommendation_year"
    )[
        "recommendation_to_schedule_days"
    ]
    .agg(
        [
            "count",
            "mean",
            "median",
            "std",
        ]
    )
)


print()
print(
    "【推薦年別：推薦→見学予定日数】"
)

print(
    workplace_visits_review
    .groupby(
        "recommendation_year"
    )[
        "recommendation_to_visit_days"
    ]
    .agg(
        [
            "count",
            "mean",
            "median",
            "std",
        ]
    )
)


# =========================================================
# H2 給与
# =========================================================

print()
print(
    "【推薦後対象案件の給与不足率】"
)

print(
    workplace_visits_review[
        "wage_shortfall_rate"
    ].describe()
)


print()
print(
    "【推薦後辞退有無 × 平均給与不足率】"
)

print(
    workplace_visits_review
    .groupby(
        "post_recommendation_withdrawal"
    )[
        "wage_shortfall_rate"
    ]
    .agg(
        [
            "count",
            "mean",
            "median",
        ]
    )
)


# =========================================================
# H3 スキル
# =========================================================

print()
print(
    "【職場見学対象のskill_gap】"
)

print(
    workplace_visits_review[
        "skill_gap"
    ].describe()
)


completed_review = (
    workplace_visits_review[
        workplace_visits_review[
            "process_state"
        ]
        ==
        "completed"
    ]
)


print()
print(
    "【見学継続確率の基本統計量】"
)

print(
    completed_review[
        "visit_continue_probability"
    ].describe()
)


# =========================================================
# H1 CA負荷
# =========================================================

print()
print(
    "【職場見学対象案件のCA負荷比率】"
)

print(
    workplace_visits_review[
        "ca_workload_ratio"
    ].describe()
)


# =========================================================
# applications更新結果
# =========================================================

print()
print(
    "【applications更新後の辞退ステージ】"
)

print(
    applications[
        "withdrawal_stage"
    ].value_counts(
        dropna=False
    )
)


print()
print(
    "【applications更新後ステータス】"
)

print(
    applications[
        "status"
    ].value_counts()
)


# =========================================================
# サンプル
# =========================================================

print()
print(
    "【workplace_visitsサンプル：先頭20件】"
)

print(
    workplace_visits
    .sort_values(
        "scheduled_date"
    )
    .head(
        20
    )
)


print()
print(
    "【workplace_visits_reviewサンプル：先頭20件】"
)

print(
    workplace_visits_review
    .sort_values(
        "recommendation_date"
    )
    .head(
        20
    )
)