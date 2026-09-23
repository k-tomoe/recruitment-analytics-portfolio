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
    / "applications.csv"
)

REVIEW_FILE = (
    REVIEW_DIR
    / "applications_review.csv"
)

# このスクリプト専用の乱数シード
#
# 分析結果を見て都合のよいseedへ変更しない。
SEED = 48

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
# candidates_test.csv
# candidate_experiences_test.csv
# candidate_preferences_test.csv
# candidate_activities_test.csv
# job_entries_test.csv
# job_introductions_test.csv
# jobs_test.csv
#
#
# 【問題点】
#
# 小規模テスト用データを参照していた。
#
#
# 【修正仕様】
#
# 分析用正式データへ切り替える。
# =========================================================

candidates = pd.read_csv(
    OUTPUT_DIR
    / "candidates.csv",
    parse_dates=[
        "registration_date",
        "search_end_date",
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

candidate_preferences = pd.read_csv(
    OUTPUT_DIR
    / "candidate_preferences.csv",
    parse_dates=[
        "effective_from",
        "effective_to",
    ],
)

candidate_activities = pd.read_csv(
    OUTPUT_DIR
    / "candidate_activities.csv",
    parse_dates=[
        "activity_date",
    ],
)

job_entries = pd.read_csv(
    OUTPUT_DIR
    / "job_entries.csv",
    parse_dates=[
        "entry_date",
    ],
)

job_introductions = pd.read_csv(
    OUTPUT_DIR
    / "job_introductions.csv"
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


# =========================================================
# 入力データの基本品質チェック
# =========================================================

assert candidates[
    "candidate_id"
].is_unique

assert jobs[
    "job_id"
].is_unique

assert job_entries[
    "entry_id"
].is_unique

assert job_introductions[
    "introduction_id"
].is_unique

assert candidate_activities[
    "activity_id"
].is_unique

assert recruiters[
    "recruiter_id"
].is_unique


# =========================================================
# 検索高速化用の辞書・DataFrame
# =========================================================
#
# 【変更前】
#
# candidateやjob、experienceを参照するたびに
# DataFrame全体をfilterしていた。
#
#
# 【問題点】
#
# applicationsが2,000～3,000件規模になると、
# 同じ検索を何千回も繰り返すことになる。
#
#
# 【修正仕様】
#
# ・candidate
# ・job
# ・candidate skill
# ・candidate preference
# ・candidate activities
#
# を事前に検索しやすい形へ整理する。
#
# 分析結果は変えず、処理効率だけ改善する。
# =========================================================


candidate_lookup = (
    candidates
    .set_index(
        "candidate_id"
    )
)


job_lookup = (
    jobs
    .set_index(
        "job_id"
    )
)


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


activities_by_candidate = {
    candidate_id:
        group.sort_values(
            "activity_date"
        ).copy()

    for candidate_id, group
    in candidate_activities.groupby(
        "candidate_id"
    )
}


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
# 求職者の職種別スキルを取得
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
# 指定CAが指定日時点で稼働中か確認
# =========================================================

def is_ca_active(
    ca_id,
    target_date,
):

    if pd.isna(
        ca_id
    ):
        return False


    matching_ca = recruiters[
        (
            recruiters[
                "recruiter_id"
            ]
            ==
            ca_id
        )
        &
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


    return (
        len(
            matching_ca
        )
        >
        0
    )


# =========================================================
# 求職者の担当CAを取得
# =========================================================
#
# 【変更前】
#
# candidates.ca_idが存在すれば、
# target_date時点の在籍確認をせずに
# そのCAを返していた。
#
#
# 【問題点】
#
# 登録後にCAが離任している場合でも、
# application担当CAとして残る可能性がある。
#
#
# 【修正仕様】
#
# 優先順位を以下とする。
#
# 1. target_date以前の最新candidate_activityのCA
# 2. candidates.ca_id
# 3. target_date時点の稼働CAから新規割当
#
# ただし必ずtarget_date時点で
# 稼働中であることを確認する。
# =========================================================

def get_candidate_ca(
    candidate_id,
    target_date,
):

    # -----------------------------------------------------
    # 1. target_date以前の最新activity
    # -----------------------------------------------------

    activities = (
        activities_by_candidate.get(
            candidate_id
        )
    )


    if activities is not None:

        past_activities = (
            activities[
                activities[
                    "activity_date"
                ]
                <=
                target_date
            ]
        )


        if len(
            past_activities
        ) > 0:

            latest_ca_id = (
                past_activities
                .iloc[-1][
                    "ca_id"
                ]
            )


            if is_ca_active(
                latest_ca_id,
                target_date,
            ):

                return (
                    latest_ca_id
                )


    # -----------------------------------------------------
    # 2. candidatesに登録された担当CA
    # -----------------------------------------------------

    candidate_ca_id = (
        candidate_lookup.loc[
            candidate_id,
            "ca_id",
        ]
    )


    if is_ca_active(
        candidate_ca_id,
        target_date,
    ):

        return (
            candidate_ca_id
        )


    # -----------------------------------------------------
    # 3. target_date時点の稼働CAから新規割当
    # -----------------------------------------------------

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


    if len(
        active_ca
    ) == 0:

        return None


    return rng.choice(
        active_ca[
            "recruiter_id"
        ]
    )


# =========================================================
# H1 / H5用：月別CA負荷
# =========================================================
#
# 【変更前】
#
# 推薦までの日数を
#
# 2025年
# 2026年
#
# で直接分けていた。
#
#
# 【問題点】
#
# 「2026年だから遅い」
#
# という結果を生成段階で直接作ることになる。
#
#
# 【修正仕様】
#
# candidate_activities.py /
# generate_job_introductions.pyと同様に、
#
# 月内アクティブ候補者数
# ÷
# 月内稼働CA数
#
# をCA負荷とする。
#
# CA負荷が高いほど、
# 応募意思確認から推薦までの日数が
# 確率的に長くなりやすい構造とする。
#
# これにより、
#
# H1：担当者負荷
# H5：プロセス長期化
#
# を後から分析できる。
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
# self_entry → application移行確率
# =========================================================
#
# 【変更前】
#
# 小規模テスト修正後は、
# 同職種経験・skill gapにより
# application移行確率を変えていた。
#
#
# 【問題点】
#
# この考え方自体には問題がない。
#
#
# 【修正仕様】
#
# 分析用データでも維持する。
#
# self_entryでは未経験応募そのものは許容し、
# 正式なapplication化の段階で
# スキルによるスクリーニングを効かせる。
# =========================================================

def get_self_entry_conversion_probability(
    candidate_id,
    job,
):

    required_skill_level = int(
        job[
            "required_skill_level"
        ]
    )


    # candidate_skill = (
    #     get_candidate_skill(
    #         candidate_id,
    #         job.name,
    #     )
    #     if False
    #     else None
    # )

    # job.nameではなくoccupation_idで取得する
    candidate_skill = (
        get_candidate_skill(
            candidate_id,
            job[
                "occupation_id"
            ],
        )
    )


    # -----------------------------------------------------
    # 同職種経験なし
    # -----------------------------------------------------

    if candidate_skill is None:

        if (
            required_skill_level
            <=
            2
        ):

            return 0.45

        return 0.15


    # -----------------------------------------------------
    # 同職種経験あり
    # -----------------------------------------------------

    skill_gap = (
        candidate_skill
        -
        required_skill_level
    )


    if skill_gap >= 0:

        return 0.80

    elif skill_gap == -1:

        return 0.65

    elif skill_gap == -2:

        return 0.40

    else:

        return 0.20


# =========================================================
# CAが企業推薦へ進める確率
# =========================================================

def get_recommendation_probability(
    candidate_skill,
    required_skill_level,
):

    # 同職種経験なし
    if candidate_skill is None:

        if (
            required_skill_level
            <=
            2
        ):

            return 0.45

        return 0.10


    skill_gap = (
        candidate_skill
        -
        required_skill_level
    )


    if skill_gap >= 0:

        return 0.95

    elif skill_gap == -1:

        return 0.82

    elif skill_gap == -2:

        return 0.55

    else:

        return 0.35


# =========================================================
# 企業側の推薦通過確率
# =========================================================
#
# これは企業側のスクリーニングを表すため、
# 主にskill適合度を使用する。
#
# 給与条件は候補者側の受諾・辞退で扱うため、
# ここでは直接使用しない。
# =========================================================

def get_acceptance_probability(
    candidate_skill,
    required_skill_level,
):

    if candidate_skill is None:

        if (
            required_skill_level
            <=
            2
        ):

            return 0.40

        return 0.15


    skill_gap = (
        candidate_skill
        -
        required_skill_level
    )


    if skill_gap >= 0:

        return 0.82

    elif skill_gap == -1:

        return 0.62

    elif skill_gap == -2:

        return 0.38

    else:

        return 0.22


# =========================================================
# 修正① 推薦リードタイム生成
# =========================================================
#
# 【変更前】
#
# 2025：
# 0～4日
#
# 2026：
# 1～7日
#
# と、yearから直接日数分布を変えていた。
#
#
# 【問題点】
#
# 「2026年だから遅い」という結果を
# 直接作ってしまう。
#
#
# 【修正仕様】
#
# 基本リードタイム
# +
# application_source差
# +
# CA負荷による追加遅延
#
# とする。
#
# self_entryでは、求人サイト応募後に
# CAが確認する工程があるため、
# CA紹介より少し時間がかかりやすい。
#
# CA負荷が高い月では、
# さらに0～数日の追加遅延が発生しやすい。
#
# yearそのものは使用しない。
# =========================================================

def generate_recommendation_delay(
    intent_confirmed_date,
    application_source,
):

    # -----------------------------------------------------
    # 基本日数
    # -----------------------------------------------------

    base_delay = int(
        rng.choice(
            [
                0,
                1,
                2,
                3,
            ],
            p=[
                0.20,
                0.40,
                0.30,
                0.10,
            ],
        )
    )


    # -----------------------------------------------------
    # self_entryはCA確認工程があるため、
    # 少しだけ追加時間がかかる場合がある。
    # -----------------------------------------------------

    source_delay = 0

    if (
        application_source
        ==
        "self_entry"
    ):

        source_delay = int(
            rng.choice(
                [
                    0,
                    1,
                ],
                p=[
                    0.60,
                    0.40,
                ],
            )
        )


    # -----------------------------------------------------
    # CA負荷による追加日数
    # -----------------------------------------------------

    workload_ratio = (
        get_ca_workload_ratio(
            intent_confirmed_date
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
            5.0
        )
    )


    # 極端な値を防ぐ
    workload_delay = min(
        workload_delay,
        5,
    )


    recommendation_delay = (
        base_delay
        +
        source_delay
        +
        workload_delay
    )


    # 最大8日程度
    return int(
        min(
            recommendation_delay,
            8,
        )
    )


# =========================================================
# 修正② 推薦前辞退確率
# =========================================================
#
# 【変更前】
#
# 推薦前辞退の基礎確率5%に対し、
#
# ・給与不足
# ・推薦遅延
#
# で最大65%まで上昇させていた。
#
#
# 【問題点】
#
# 実務感として、
# 応募意思確認後すぐの推薦前辞退は
# それほど高くない。
#
# 一方、
#
# ・推薦後
# ・職場見学後
#
# の辞退は一定数発生する。
#
#
# 【修正仕様】
#
# 推薦前辞退は低めにする。
#
# 基本：約2%
#
# 給与不足・長い推薦待ちがある場合だけ
# 数ポイント～十数ポイント上昇。
#
# 後続の
#
# generate_workplace_visits.py
# generate_placements.py
#
# で、
#
# post_recommendation
# post_visit
#
# の辞退を追加する。
# =========================================================

def get_pre_recommendation_withdrawal_probability(
    wage_shortfall_rate,
    recommendation_delay,
):

    probability = 0.02


    # -----------------------------------------------------
    # 給与不足
    # -----------------------------------------------------

    if wage_shortfall_rate >= 0.15:

        probability += 0.10

    elif wage_shortfall_rate >= 0.10:

        probability += 0.06

    elif wage_shortfall_rate >= 0.05:

        probability += 0.03


    # -----------------------------------------------------
    # 推薦待ち時間
    # -----------------------------------------------------

    if recommendation_delay >= 7:

        probability += 0.08

    elif recommendation_delay >= 5:

        probability += 0.05

    elif recommendation_delay >= 3:

        probability += 0.02


    return float(
        np.clip(
            probability,
            0.01,
            0.30,
        )
    )


# =========================================================
# 推薦前辞退理由
# =========================================================

def select_pre_recommendation_withdrawal_reason(
    wage_shortfall_rate,
    recommendation_delay,
):

    wage_issue = (
        wage_shortfall_rate
        >=
        0.10
    )

    delay_issue = (
        recommendation_delay
        >=
        5
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
                0.45,
                0.45,
                0.10,
            ],
        )


    if wage_issue:

        return rng.choice(
            [
                "wage",
                "other",
            ],
            p=[
                0.80,
                0.20,
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
# 応募候補を格納
# =========================================================

application_candidates = []


# =========================================================
# 1. 求人サイト経由
# =========================================================

for _, entry in (
    job_entries.iterrows()
):

    candidate_id = (
        entry[
            "candidate_id"
        ]
    )

    job_id = (
        entry[
            "job_id"
        ]
    )

    entry_date = (
        entry[
            "entry_date"
        ]
    )


    job = (
        job_lookup.loc[
            job_id
        ]
    )


    # =====================================================
    # self_entry → application移行判定
    # =====================================================

    conversion_probability = (
        get_self_entry_conversion_probability(
            candidate_id,
            job,
        )
    )


    converts_to_application = (
        rng.random()
        <
        conversion_probability
    )


    if not converts_to_application:
        continue


    # =====================================================
    # 応募意思確認日
    # =====================================================

    intent_delay = int(
        rng.integers(
            1,
            5,
        )
    )


    intent_confirmed_date = (
        entry_date
        +
        pd.Timedelta(
            days=intent_delay
        )
    )


    candidate_row = (
        candidate_lookup.loc[
            candidate_id
        ]
    )


    # 求職終了後ならapplication化しない
    if pd.notna(
        candidate_row[
            "search_end_date"
        ]
    ):

        if (
            intent_confirmed_date
            >
            candidate_row[
                "search_end_date"
            ]
        ):

            continue


    if (
        intent_confirmed_date
        >
        DATA_END_DATE
    ):

        continue


    ca_id = (
        get_candidate_ca(
            candidate_id,
            intent_confirmed_date,
        )
    )


    if ca_id is None:
        continue


    application_candidates.append(
        {
            "candidate_id":
                candidate_id,

            "job_id":
                job_id,

            "ca_id":
                ca_id,

            "application_source":
                "self_entry",

            "source_entry_id":
                entry[
                    "entry_id"
                ],

            "source_introduction_id":
                None,

            "intent_confirmed_date":
                intent_confirmed_date,
        }
    )


# =========================================================
# 2. CA求人紹介経由
# =========================================================

introduction_source = (
    job_introductions.merge(
        candidate_activities[
            [
                "activity_id",
                "candidate_id",
                "activity_date",
                "ca_id",
            ]
        ],
        on="activity_id",
        how="left",
    )
)


# apply回答のみapplication候補
introduction_source = (
    introduction_source[
        introduction_source[
            "candidate_response"
        ]
        ==
        "apply"
    ]
)


for _, introduction in (
    introduction_source.iterrows()
):

    candidate_id = (
        introduction[
            "candidate_id"
        ]
    )

    job_id = (
        introduction[
            "job_id"
        ]
    )


    # 紹介時に応募意向があるため、
    # 当日～翌日に意思確認する。
    intent_delay = int(
        rng.integers(
            0,
            2,
        )
    )


    intent_confirmed_date = (
        introduction[
            "activity_date"
        ]
        +
        pd.Timedelta(
            days=intent_delay
        )
    )


    if (
        intent_confirmed_date
        >
        DATA_END_DATE
    ):

        continue


    candidate_row = (
        candidate_lookup.loc[
            candidate_id
        ]
    )


    # -----------------------------------------------------
    # 修正③ CA紹介経路でも求職終了日を確認
    # -----------------------------------------------------
    #
    # 【変更前】
    #
    # self_entryでは確認していたが、
    # ca_introductionではsearch_end_dateを
    # 確認していなかった。
    #
    #
    # 【修正仕様】
    #
    # 両経路で同じ候補者ライフサイクル制約を適用する。
    # -----------------------------------------------------

    if pd.notna(
        candidate_row[
            "search_end_date"
        ]
    ):

        if (
            intent_confirmed_date
            >
            candidate_row[
                "search_end_date"
            ]
        ):

            continue


    # 紹介activityのCAが
    # intent時点でも稼働していれば使用。
    source_ca_id = (
        introduction[
            "ca_id"
        ]
    )


    if is_ca_active(
        source_ca_id,
        intent_confirmed_date,
    ):

        ca_id = (
            source_ca_id
        )

    else:

        ca_id = (
            get_candidate_ca(
                candidate_id,
                intent_confirmed_date,
            )
        )


    if ca_id is None:
        continue


    application_candidates.append(
        {
            "candidate_id":
                candidate_id,

            "job_id":
                job_id,

            "ca_id":
                ca_id,

            "application_source":
                "ca_introduction",

            "source_entry_id":
                None,

            "source_introduction_id":
                introduction[
                    "introduction_id"
                ],

            "intent_confirmed_date":
                intent_confirmed_date,
        }
    )


# =========================================================
# DataFrame化
# =========================================================

application_candidates = (
    pd.DataFrame(
        application_candidates
    )
)


assert (
    len(
        application_candidates
    )
    >
    0
)


# =========================================================
# candidate × job 重複を除く
# =========================================================
#
# self_entryとCA紹介の両方がある場合、
# 最初に応募意思確認された経路を採用する。
# =========================================================

application_candidates = (
    application_candidates
    .sort_values(
        [
            "intent_confirmed_date",
            "application_source",
        ]
    )
    .drop_duplicates(
        subset=[
            "candidate_id",
            "job_id",
        ],
        keep="first",
    )
    .reset_index(
        drop=True
    )
)


# =========================================================
# 応募案件詳細生成
# =========================================================

application_data = []

review_data = []

used_entry_ids = []

application_counter = 1


for _, application in (
    application_candidates.iterrows()
):

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

    application_source = (
        application[
            "application_source"
        ]
    )

    intent_confirmed_date = (
        application[
            "intent_confirmed_date"
        ]
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
    # 候補者情報
    # =====================================================

    candidate_row = (
        candidate_lookup.loc[
            candidate_id
        ]
    )


    # =====================================================
    # 応募意思確認時点の希望条件
    # =====================================================

    preference = (
        get_active_preference(
            candidate_id,
            intent_confirmed_date,
        )
    )


    if preference is None:
        continue


    # =====================================================
    # H2 給与条件
    # =====================================================

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


    wage_gap_ratio = (
        offered_wage
        -
        desired_wage
    ) / desired_wage


    # 提示時給が希望時給を下回る割合。
    #
    # SQLマートのwage_shortfall_rateと
    # 同じ考え方。
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
    # H3 スキル情報
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

        same_occupation_experience = False

    else:

        skill_gap = (
            candidate_skill
            -
            required_skill_level
        )

        same_occupation_experience = True


    # =====================================================
    # H5 推薦リードタイム
    # =====================================================

    recommendation_delay = (
        generate_recommendation_delay(
            intent_confirmed_date=(
                intent_confirmed_date
            ),
            application_source=(
                application_source
            ),
        )
    )


    planned_recommendation_date = (
        intent_confirmed_date
        +
        pd.Timedelta(
            days=recommendation_delay
        )
    )


    ca_workload_ratio = (
        get_ca_workload_ratio(
            intent_confirmed_date
        )
    )


    # =====================================================
    # 候補者の元々の求職終了日との整合
    # =====================================================

    candidate_search_end_date = (
        candidate_row[
            "search_end_date"
        ]
    )


    search_ends_before_recommendation = (
        pd.notna(
            candidate_search_end_date
        )
        and
        (
            candidate_search_end_date
            <
            planned_recommendation_date
        )
    )


    # =====================================================
    # 修正④ 推薦前辞退
    # =====================================================

    pre_withdrawal_probability = (
        get_pre_recommendation_withdrawal_probability(
            wage_shortfall_rate=(
                wage_shortfall_rate
            ),
            recommendation_delay=(
                recommendation_delay
            ),
        )
    )


    withdraws_before_recommendation = (
        rng.random()
        <
        pre_withdrawal_probability
    )


    # 元々の求職終了日が推薦予定日より前なら、
    # application開始後に求職終了したものとして
    # 推薦前辞退として扱う。
    if search_ends_before_recommendation:

        withdraws_before_recommendation = True


    # =====================================================
    # 推薦前辞退した場合
    # =====================================================

    if withdraws_before_recommendation:

        # -------------------------------------------------
        # 辞退日
        # -------------------------------------------------

        if search_ends_before_recommendation:

            withdrawal_date = (
                candidate_search_end_date
            )

        elif recommendation_delay == 0:

            withdrawal_date = (
                intent_confirmed_date
            )

        else:

            withdrawal_delay = int(
                rng.integers(
                    0,
                    recommendation_delay + 1,
                )
            )

            withdrawal_date = (
                intent_confirmed_date
                +
                pd.Timedelta(
                    days=withdrawal_delay
                )
            )


        withdrawal_date = min(
            withdrawal_date,
            DATA_END_DATE,
        )


        # -------------------------------------------------
        # 辞退理由
        # -------------------------------------------------

        withdrawal_reason = (
            select_pre_recommendation_withdrawal_reason(
                wage_shortfall_rate=(
                    wage_shortfall_rate
                ),
                recommendation_delay=(
                    recommendation_delay
                ),
            )
        )


        # -------------------------------------------------
        # 辞退ステージ
        # -------------------------------------------------

        withdrawal_stage = (
            "pre_recommendation"
        )


        recommendation_date = (
            pd.NaT
        )

        recommendation_result = (
            None
        )

        status = (
            "withdrawn"
        )


    # =====================================================
    # 推薦前辞退しなかった場合
    # =====================================================

    else:

        withdrawal_date = (
            pd.NaT
        )

        withdrawal_reason = (
            None
        )

        withdrawal_stage = (
            None
        )


        # =================================================
        # CAが企業推薦まで進めるか
        # =================================================

        recommendation_probability = (
            get_recommendation_probability(
                candidate_skill,
                required_skill_level,
            )
        )


        is_recommended = (
            rng.random()
            <
            recommendation_probability
        )


        # =================================================
        # 推薦対象外
        # =================================================

        if not is_recommended:

            recommendation_date = (
                pd.NaT
            )

            recommendation_result = (
                None
            )

            status = (
                "screened_out"
            )


        # =================================================
        # 推薦予定
        # =================================================

        else:

            recommendation_date = (
                planned_recommendation_date
            )


            # =============================================
            # DATA_END_DATEを超える場合は右打ち切り
            # =============================================

            if (
                recommendation_date
                >
                DATA_END_DATE
            ):

                recommendation_date = (
                    pd.NaT
                )

                recommendation_result = (
                    None
                )

                status = (
                    "confirmed"
                )


            else:

                # =========================================
                # 企業側の推薦結果
                # =========================================

                acceptance_probability = (
                    get_acceptance_probability(
                        candidate_skill,
                        required_skill_level,
                    )
                )


                recommendation_accepted = (
                    rng.random()
                    <
                    acceptance_probability
                )


                if recommendation_accepted:

                    recommendation_result = (
                        "accepted"
                    )

                    status = (
                        "recommended"
                    )


                else:

                    recommendation_result = (
                        "rejected"
                    )

                    status = (
                        "rejected"
                    )


    # =====================================================
    # Application ID
    # =====================================================

    application_id = (
        f"APP{application_counter:06d}"
    )


    application_data.append(
        [
            application_id,
            job_id,
            candidate_id,
            application[
                "ca_id"
            ],
            application_source,
            application[
                "source_entry_id"
            ],
            application[
                "source_introduction_id"
            ],
            intent_confirmed_date,
            recommendation_date,
            recommendation_result,
            withdrawal_date,
            withdrawal_reason,
            withdrawal_stage,
            status,
        ]
    )


    # =====================================================
    # Review用データ
    # =====================================================

    review_data.append(
        [
            application_id,
            job_id,
            candidate_id,
            application_source,
            intent_confirmed_date,
            desired_wage,
            offered_wage,
            wage_gap_ratio,
            wage_shortfall_rate,
            same_occupation_experience,
            candidate_skill,
            required_skill_level,
            skill_gap,
            ca_workload_ratio,
            recommendation_delay,
            pre_withdrawal_probability,
            withdrawal_stage,
            recommendation_result,
            status,
        ]
    )


    if pd.notna(
        application[
            "source_entry_id"
        ]
    ):

        used_entry_ids.append(
            application[
                "source_entry_id"
            ]
        )


    application_counter += 1


# =========================================================
# DataFrame化
# =========================================================

applications = pd.DataFrame(
    application_data,
    columns=[
        "application_id",
        "job_id",
        "candidate_id",
        "ca_id",
        "application_source",
        "source_entry_id",
        "source_introduction_id",
        "intent_confirmed_date",
        "recommendation_date",
        "recommendation_result",
        "withdrawal_date",
        "withdrawal_reason",
        "withdrawal_stage",
        "status",
    ],
)


applications_review = pd.DataFrame(
    review_data,
    columns=[
        "application_id",
        "job_id",
        "candidate_id",
        "application_source",
        "intent_confirmed_date",
        "desired_hourly_wage",
        "offered_hourly_wage",
        "wage_gap_ratio",
        "wage_shortfall_rate",
        "same_occupation_experience",
        "candidate_skill_level",
        "required_skill_level",
        "skill_gap",
        "ca_workload_ratio",
        "intent_to_recommend_days",
        "pre_recommendation_withdrawal_probability",
        "withdrawal_stage",
        "recommendation_result",
        "status",
    ],
)


assert (
    len(
        applications
    )
    >
    0
)


# =========================================================
# データ品質チェック
# =========================================================

# ---------------------------------------------------------
# ID
# ---------------------------------------------------------

assert applications[
    "application_id"
].is_unique


# candidate × jobは1回のみ
assert not applications.duplicated(
    subset=[
        "candidate_id",
        "job_id",
    ]
).any()


# ---------------------------------------------------------
# 外部キー
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# CA
# ---------------------------------------------------------

ca_master = recruiters[
    recruiters[
        "role_type"
    ]
    ==
    "CA"
]


assert applications[
    "ca_id"
].isin(
    ca_master[
        "recruiter_id"
    ]
).all()


# =========================================================
# ステータス品質チェック
# =========================================================

assert applications[
    "status"
].isin(
    [
        "confirmed",
        "screened_out",
        "withdrawn",
        "recommended",
        "rejected",
    ]
).all()


# ---------------------------------------------------------
# screened_out
# ---------------------------------------------------------

screened_out_rows = (
    applications[
        applications[
            "status"
        ]
        ==
        "screened_out"
    ]
)


assert screened_out_rows[
    "recommendation_date"
].isna().all()


assert screened_out_rows[
    "recommendation_result"
].isna().all()


assert screened_out_rows[
    "withdrawal_date"
].isna().all()


assert screened_out_rows[
    "withdrawal_stage"
].isna().all()


# ---------------------------------------------------------
# confirmed
# ---------------------------------------------------------

confirmed_rows = (
    applications[
        applications[
            "status"
        ]
        ==
        "confirmed"
    ]
)


assert confirmed_rows[
    "recommendation_date"
].isna().all()


assert confirmed_rows[
    "recommendation_result"
].isna().all()


assert confirmed_rows[
    "withdrawal_date"
].isna().all()


assert confirmed_rows[
    "withdrawal_stage"
].isna().all()


# ---------------------------------------------------------
# withdrawn
# ---------------------------------------------------------

withdrawn_status_rows = (
    applications[
        applications[
            "status"
        ]
        ==
        "withdrawn"
    ]
)


assert withdrawn_status_rows[
    "withdrawal_date"
].notna().all()


assert withdrawn_status_rows[
    "withdrawal_stage"
].notna().all()


# 現段階ではapplications生成時に作られる辞退は
# pre_recommendationのみ。
#
# 後続スクリプトで、
#
# post_recommendation
# post_visit
#
# を追加する。
assert withdrawn_status_rows[
    "withdrawal_stage"
].eq(
    "pre_recommendation"
).all()


assert withdrawn_status_rows[
    "recommendation_date"
].isna().all()


# ---------------------------------------------------------
# recommended
# ---------------------------------------------------------

recommended_status_rows = (
    applications[
        applications[
            "status"
        ]
        ==
        "recommended"
    ]
)


assert (
    recommended_status_rows[
        "recommendation_result"
    ]
    ==
    "accepted"
).all()


assert recommended_status_rows[
    "recommendation_date"
].notna().all()


# ---------------------------------------------------------
# rejected
# ---------------------------------------------------------

rejected_status_rows = (
    applications[
        applications[
            "status"
        ]
        ==
        "rejected"
    ]
)


assert (
    rejected_status_rows[
        "recommendation_result"
    ]
    ==
    "rejected"
).all()


# =========================================================
# 応募経路とSource ID
# =========================================================

assert applications[
    "application_source"
].isin(
    [
        "self_entry",
        "ca_introduction",
    ]
).all()


self_entry_rows = (
    applications[
        applications[
            "application_source"
        ]
        ==
        "self_entry"
    ]
)


assert self_entry_rows[
    "source_entry_id"
].notna().all()


assert self_entry_rows[
    "source_introduction_id"
].isna().all()


assert self_entry_rows[
    "source_entry_id"
].isin(
    job_entries[
        "entry_id"
    ]
).all()


introduction_rows = (
    applications[
        applications[
            "application_source"
        ]
        ==
        "ca_introduction"
    ]
)


assert introduction_rows[
    "source_entry_id"
].isna().all()


assert introduction_rows[
    "source_introduction_id"
].notna().all()


assert introduction_rows[
    "source_introduction_id"
].isin(
    job_introductions[
        "introduction_id"
    ]
).all()


# =========================================================
# 日付整合性
# =========================================================

recommended_rows = (
    applications[
        applications[
            "recommendation_date"
        ].notna()
    ]
)


assert (
    recommended_rows[
        "recommendation_date"
    ]
    >=
    recommended_rows[
        "intent_confirmed_date"
    ]
).all()


withdrawn_rows = (
    applications[
        applications[
            "withdrawal_date"
        ].notna()
    ]
)


assert (
    withdrawn_rows[
        "withdrawal_date"
    ]
    >=
    withdrawn_rows[
        "intent_confirmed_date"
    ]
).all()


assert (
    applications[
        "intent_confirmed_date"
    ]
    <=
    DATA_END_DATE
).all()


assert (
    recommended_rows[
        "recommendation_date"
    ]
    <=
    DATA_END_DATE
).all()


assert (
    withdrawn_rows[
        "withdrawal_date"
    ]
    <=
    DATA_END_DATE
).all()


# =========================================================
# 求職期間との整合性
# =========================================================

application_candidate_check = (
    applications.merge(
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
    application_candidate_check[
        "intent_confirmed_date"
    ]
    >=
    application_candidate_check[
        "registration_date"
    ]
).all()


ended_application_check = (
    application_candidate_check[
        application_candidate_check[
            "search_end_date"
        ].notna()
    ]
)


assert (
    ended_application_check[
        "intent_confirmed_date"
    ]
    <=
    ended_application_check[
        "search_end_date"
    ]
).all()


# 推薦日が存在する場合も、
# 元々の求職終了日を超えないこと。
ended_recommended_check = (
    application_candidate_check[
        application_candidate_check[
            "search_end_date"
        ].notna()
        &
        application_candidate_check[
            "recommendation_date"
        ].notna()
    ]
)


assert (
    ended_recommended_check[
        "recommendation_date"
    ]
    <=
    ended_recommended_check[
        "search_end_date"
    ]
).all()


# =========================================================
# Source日付との整合性
# =========================================================

# ---------------------------------------------------------
# self_entry
# ---------------------------------------------------------

self_entry_date_check = (
    self_entry_rows.merge(
        job_entries[
            [
                "entry_id",
                "entry_date",
            ]
        ],
        left_on="source_entry_id",
        right_on="entry_id",
        how="left",
    )
)


assert (
    self_entry_date_check[
        "intent_confirmed_date"
    ]
    >=
    self_entry_date_check[
        "entry_date"
    ]
).all()


# ---------------------------------------------------------
# ca_introduction
# ---------------------------------------------------------

introduction_date_source = (
    job_introductions.merge(
        candidate_activities[
            [
                "activity_id",
                "activity_date",
            ]
        ],
        on="activity_id",
        how="left",
    )
    [
        [
            "introduction_id",
            "activity_date",
        ]
    ]
)


introduction_date_check = (
    introduction_rows.merge(
        introduction_date_source,
        left_on=(
            "source_introduction_id"
        ),
        right_on=(
            "introduction_id"
        ),
        how="left",
    )
)


assert (
    introduction_date_check[
        "intent_confirmed_date"
    ]
    >=
    introduction_date_check[
        "activity_date"
    ]
).all()


# =========================================================
# job_entriesステータス更新
# =========================================================
#
# applicationへ進んだentryはconverted。
# 進まなかったentryはdeclined。
#
# ここでのdeclinedは、
# 求人への興味は示したが正式応募案件には
# 進まなかったことを表す。
# =========================================================

job_entries[
    "status"
] = np.where(
    job_entries[
        "entry_id"
    ].isin(
        used_entry_ids
    ),
    "converted",
    "declined",
)


assert job_entries[
    "status"
].isin(
    [
        "converted",
        "declined",
    ]
).all()


# =========================================================
# CSV出力
# =========================================================
#
# 【変更前】
#
# applications_test.csv
# job_entries_test.csv
#
#
# 【修正仕様】
#
# applications.csv
# job_entries.csv
#
# 分析用正式データとして出力する。
# =========================================================

applications.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig",
)


job_entries.to_csv(
    OUTPUT_DIR
    / "job_entries.csv",
    index=False,
    encoding="utf-8-sig",
)


applications_review.to_csv(
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
# applications全件をprintしていた。
#
#
# 【問題点】
#
# 2,000～3,000件規模では
# 全件表示は確認しづらい。
#
#
# 【修正仕様】
#
# 件数・分布・統計量・サンプルだけを表示する。
# =========================================================

print(
    "分析用応募案件データを生成しました。"
)

print()

print(
    f"応募案件数: "
    f"{len(applications):,}"
)


# =========================================================
# 応募経路
# =========================================================

print()
print(
    "【応募経路別件数】"
)

print(
    applications[
        "application_source"
    ].value_counts()
)


print()
print(
    "【応募経路別割合】"
)

print(
    applications[
        "application_source"
    ].value_counts(
        normalize=True
    )
)


# =========================================================
# ステータス
# =========================================================

print()
print(
    "【応募案件ステータス】"
)

print(
    applications[
        "status"
    ].value_counts(
        dropna=False
    )
)


print()
print(
    "【推薦結果】"
)

print(
    applications[
        "recommendation_result"
    ].value_counts(
        dropna=False
    )
)


# =========================================================
# 辞退
# =========================================================

print()
print(
    "【辞退ステージ】"
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
    "【推薦前辞退率】"
)

print(
    (
        applications[
            "withdrawal_stage"
        ]
        ==
        "pre_recommendation"
    ).mean()
)


# =========================================================
# H2 給与
# =========================================================

print()
print(
    "【給与不足率の基本統計量】"
)

print(
    applications_review[
        "wage_shortfall_rate"
    ].describe()
)


applications_review[
    "application_year"
] = (
    applications_review[
        "intent_confirmed_date"
    ].dt.year
)


print()
print(
    "【応募年別給与不足率】"
)

print(
    applications_review
    .groupby(
        "application_year"
    )[
        "wage_shortfall_rate"
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
# H3 スキル
# =========================================================

print()
print(
    "【応募経路 × 同職種経験有無】"
)

print(
    pd.crosstab(
        applications_review[
            "application_source"
        ],
        applications_review[
            "same_occupation_experience"
        ],
        dropna=False,
    )
)


print()
print(
    "【応募年別同職種経験率】"
)

print(
    applications_review
    .groupby(
        "application_year"
    )[
        "same_occupation_experience"
    ]
    .mean()
)


print()
print(
    "【skill_gapの基本統計量】"
)

print(
    applications_review[
        "skill_gap"
    ].describe()
)


# =========================================================
# H1 / H5 CA負荷・推薦リードタイム
# =========================================================

print()
print(
    "【CA負荷比率の基本統計量】"
)

print(
    applications_review[
        "ca_workload_ratio"
    ].describe()
)


print()
print(
    "【応募年別：応募→推薦予定日数】"
)

print(
    applications_review
    .groupby(
        "application_year"
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


# =========================================================
# job_entries更新結果
# =========================================================

print()
print(
    "【求人エントリー更新後ステータス】"
)

print(
    job_entries[
        "status"
    ].value_counts()
)


# =========================================================
# application数の目安確認
# =========================================================
#
# ここでは件数が2,000～3,000件に
# 必ず入るassertは置かない。
#
# 仮説結果とは関係のない
# 「分析可能なデータ量」の確認として表示する。
#
# 極端に少ない / 多い場合のみ、
# 全生成後にファネル件数設計を見直す。
# =========================================================

print()
print(
    "【分析用応募件数目安】"
)

if (
    2000
    <=
    len(applications)
    <=
    3000
):

    print(
        "目標レンジ "
        "2,000～3,000件に入っています。"
    )

else:

    print(
        "目標レンジ "
        "2,000～3,000件の外です。"
    )

    print(
        "全スクリプト実行後に、"
        "統計結果ではなくファネル件数設計として確認します。"
    )


# =========================================================
# サンプル表示
# =========================================================

print()
print(
    "【applicationsサンプル：先頭20件】"
)

print(
    applications
    .sort_values(
        "intent_confirmed_date"
    )
    .head(
        20
    )
)


print()
print(
    "【applications_reviewサンプル：先頭20件】"
)

print(
    applications_review
    .sort_values(
        "intent_confirmed_date"
    )
    .head(
        20
    )
)