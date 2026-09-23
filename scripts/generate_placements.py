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
    / "placements.csv"
)

REVIEW_FILE = (
    REVIEW_DIR
    / "placements_review.csv"
)

# このスクリプト専用の乱数シード
#
# 分析結果を確認した後で、
# 都合のよいseedへ変更しない。
SEED = 50

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
# workplace_visits_test.csv
# jobs_test.csv
# candidates_test.csv
# candidate_preferences_test.csv
# candidate_experiences_test.csv
#
#
# 【問題点】
#
# 小規模テスト用ファイルを参照していた。
#
# またplacement後の候補者について、
#
# ・candidate_activities
# ・job_entries
# ・job_introductions
# ・applications
# ・workplace_visits
# ・candidate_preferences
#
# に未来日付のレコードが残る可能性があった。
#
#
# 【修正仕様】
#
# 分析用正式ファイルへ切り替える。
#
# さらにplacement後のライフサイクルを
# 最終的に整合させるため、
# 関連イベントテーブルも読み込む。
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

workplace_visits = pd.read_csv(
    OUTPUT_DIR
    / "workplace_visits.csv",
    parse_dates=[
        "scheduled_date",
        "visit_date",
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


# =========================================================
# 入力データの基本品質チェック
# =========================================================

assert applications[
    "application_id"
].is_unique

assert workplace_visits[
    "visit_id"
].is_unique

assert jobs[
    "job_id"
].is_unique

assert candidates[
    "candidate_id"
].is_unique

assert candidate_activities[
    "activity_id"
].is_unique

assert job_entries[
    "entry_id"
].is_unique

assert job_introductions[
    "introduction_id"
].is_unique


# applicationsには、
# 前工程で追加したwithdrawal_stageが必要
assert (
    "withdrawal_stage"
    in
    applications.columns
)


# =========================================================
# 検索高速化用データ
# =========================================================
#
# 【変更前】
#
# DataFrameを都度検索していた。
#
#
# 【問題点】
#
# 数百～数千件の選考を処理するため、
# 同じ検索を繰り返すと処理効率が悪い。
#
#
# 【修正仕様】
#
# job / candidate / skill / preferenceを
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
# H2 給与不足率
# =========================================================

def calculate_wage_shortfall_rate(
    desired_wage,
    offered_wage,
):

    return max(
        (
            desired_wage
            -
            offered_wage
        )
        /
        desired_wage,
        0.0,
    )


# =========================================================
# 修正① post_visit辞退確率
# =========================================================
#
# 【変更前】
#
# 職場見学後にcontinueとなった案件は、
# そのままplacement抽選へ進んでいた。
#
#
# 【問題点】
#
# 実務では、
#
# 職場見学
# ↓
# 候補者が検討
# ↓
# 最終的に辞退
#
# も発生する。
#
# これまでの設計では、
#
# pre_recommendation
# post_recommendation
#
# までは存在したが、
# post_visit辞退が存在しなかった。
#
#
# 【修正仕様】
#
# completed visit
# +
# result = continue
#
# の案件について、
#
# ・給与不足
# ・応募から見学までの総リードタイム
# ・見学から意思決定までの日数
#
# に応じてpost_visit辞退を発生させる。
#
# yearそのものは使用しない。
#
# 条件が悪くても必ず辞退するわけではなく、
# 確率的に生成する。
# =========================================================

def get_post_visit_withdrawal_probability(
    wage_shortfall_rate,
    intent_to_visit_days,
    decision_delay,
):

    probability = 0.06


    # -----------------------------------------------------
    # H2 給与不足
    # -----------------------------------------------------

    if wage_shortfall_rate >= 0.15:

        probability += 0.08

    elif wage_shortfall_rate >= 0.10:

        probability += 0.05

    elif wage_shortfall_rate >= 0.05:

        probability += 0.02


    # -----------------------------------------------------
    # H5 応募→職場見学までの総時間
    # -----------------------------------------------------

    if intent_to_visit_days >= 20:

        probability += 0.08

    elif intent_to_visit_days >= 14:

        probability += 0.05

    elif intent_to_visit_days >= 10:

        probability += 0.02


    # -----------------------------------------------------
    # 見学→最終判断までの待ち時間
    # -----------------------------------------------------

    if decision_delay >= 6:

        probability += 0.05

    elif decision_delay >= 4:

        probability += 0.02


    return float(
        np.clip(
            probability,
            0.04,
            0.35,
        )
    )


# =========================================================
# post_visit辞退理由
# =========================================================

def select_post_visit_withdrawal_reason(
    wage_shortfall_rate,
    intent_to_visit_days,
    decision_delay,
):

    wage_issue = (
        wage_shortfall_rate
        >=
        0.10
    )


    delay_issue = (
        intent_to_visit_days
        >=
        14
        or
        decision_delay
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
                0.40,
                0.40,
                0.20,
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
                0.75,
                0.25,
            ],
        )


    return "other"


# =========================================================
# 修正② 就業決定確率
# =========================================================
#
# 【変更前】
#
# placement_probability = 0.72
#
# から、
#
# ・給与
# ・skill
# ・process_days
#
# を加減算していた。
#
#
# 【問題点】
#
# 基本的な考え方は問題ないが、
# post_visit辞退とplacement判定を
# 同じ処理として扱っていた。
#
#
# 【修正仕様】
#
# まず候補者側のpost_visit辞退を判定する。
#
# 辞退しなかった案件だけについて、
# 企業・候補者双方の最終合意として
# placement確率を評価する。
#
# placementは最終就業決定なので、
# placement後のwithdrawalは生成しない。
# =========================================================

def get_placement_probability(
    wage_shortfall_rate,
    candidate_skill,
    required_skill_level,
    process_days,
):

    probability = 0.70


    # -----------------------------------------------------
    # H2 給与
    # -----------------------------------------------------

    if wage_shortfall_rate == 0:

        probability += 0.07

    elif wage_shortfall_rate <= 0.05:

        probability += 0.02

    elif wage_shortfall_rate <= 0.10:

        probability -= 0.05

    elif wage_shortfall_rate <= 0.15:

        probability -= 0.10

    else:

        probability -= 0.18


    # -----------------------------------------------------
    # H3 スキル
    # -----------------------------------------------------

    if candidate_skill is None:

        if required_skill_level <= 2:

            probability -= 0.10

        else:

            probability -= 0.25

    else:

        skill_gap = (
            candidate_skill
            -
            required_skill_level
        )


        if skill_gap >= 0:

            probability += 0.08

        elif skill_gap == -1:

            probability -= 0.03

        elif skill_gap == -2:

            probability -= 0.10

        else:

            probability -= 0.18


    # -----------------------------------------------------
    # H5 選考総リードタイム
    # -----------------------------------------------------

    if process_days <= 10:

        probability += 0.05

    elif process_days <= 16:

        pass

    elif process_days <= 22:

        probability -= 0.06

    else:

        probability -= 0.12


    return float(
        np.clip(
            probability,
            0.15,
            0.92,
        )
    )


# =========================================================
# applicationを辞退状態へ更新する関数
# =========================================================

def set_application_withdrawal(
    application_id,
    withdrawal_date,
    withdrawal_stage,
    withdrawal_reason,
):

    mask = (
        applications[
            "application_id"
        ]
        ==
        application_id
    )


    applications.loc[
        mask,
        "withdrawal_date",
    ] = withdrawal_date


    applications.loc[
        mask,
        "withdrawal_stage",
    ] = withdrawal_stage


    applications.loc[
        mask,
        "withdrawal_reason",
    ] = withdrawal_reason


    applications.loc[
        mask,
        "status",
    ] = "withdrawn"


# =========================================================
# 修正③ 既存search_end_dateとの最終整合
# =========================================================
#
# 【問題点】
#
# applicationsまではsearch_end_dateを考慮していたが、
# workplace_visitは推薦後に発生するため、
#
# search_end_date
# <
# scheduled_date / visit_date
#
# となる可能性が残る。
#
#
# 【修正仕様】
#
# placement判定前に、
# 元々endedとなっている候補者について
# search_end_date以降のworkplace_visitを整理する。
#
# 推薦後・見学前に求職終了：
# → post_recommendation withdrawal
#
# 見学後・placement前に求職終了：
# → post_visit withdrawal
# =========================================================

invalid_visit_ids = []


for _, visit in (
    workplace_visits.iterrows()
):

    application_id = (
        visit[
            "application_id"
        ]
    )


    application_row = (
        applications[
            applications[
                "application_id"
            ]
            ==
            application_id
        ]
    )


    if len(
        application_row
    ) == 0:

        continue


    application_row = (
        application_row.iloc[0]
    )


    candidate_id = (
        application_row[
            "candidate_id"
        ]
    )


    candidate_row = (
        candidate_lookup.loc[
            candidate_id
        ]
    )


    original_search_end_date = (
        candidate_row[
            "search_end_date"
        ]
    )


    if pd.isna(
        original_search_end_date
    ):

        continue


    # 既に別理由で辞退済みなら変更しない
    if (
        application_row[
            "status"
        ]
        ==
        "withdrawn"
    ):

        continue


    # -----------------------------------------------------
    # 見学設定前に求職終了
    # -----------------------------------------------------

    if (
        original_search_end_date
        <
        visit[
            "scheduled_date"
        ]
    ):

        set_application_withdrawal(
            application_id=(
                application_id
            ),
            withdrawal_date=(
                original_search_end_date
            ),
            withdrawal_stage=(
                "post_recommendation"
            ),
            withdrawal_reason=(
                "other"
            ),
        )

        invalid_visit_ids.append(
            visit[
                "visit_id"
            ]
        )

        continue


    # -----------------------------------------------------
    # scheduled後だが、
    # actual visit前に求職終了
    # -----------------------------------------------------

    if (
        pd.notna(
            visit[
                "visit_date"
            ]
        )
        and
        original_search_end_date
        <
        visit[
            "visit_date"
        ]
    ):

        set_application_withdrawal(
            application_id=(
                application_id
            ),
            withdrawal_date=(
                original_search_end_date
            ),
            withdrawal_stage=(
                "post_recommendation"
            ),
            withdrawal_reason=(
                "other"
            ),
        )

        invalid_visit_ids.append(
            visit[
                "visit_id"
            ]
        )


# search_end_date以降に実施されるはずだった
# visitレコードを削除
if len(
    invalid_visit_ids
) > 0:

    workplace_visits = (
        workplace_visits[
            ~workplace_visits[
                "visit_id"
            ].isin(
                invalid_visit_ids
            )
        ]
        .copy()
    )


# =========================================================
# 職場見学後に企業側で終了した案件を更新
# =========================================================
#
# completed
# +
# result = decline
#
# は候補者辞退ではなく、
# 「見学後に次工程へ進まなかった案件」
# としてapplication statusをrejectedへ更新する。
#
# withdrawal_stageには入れない。
# =========================================================

visit_decline_application_ids = (
    workplace_visits.loc[
        (
            workplace_visits[
                "visit_status"
            ]
            ==
            "completed"
        )
        &
        (
            workplace_visits[
                "result"
            ]
            ==
            "decline"
        ),
        "application_id",
    ]
)


applications.loc[
    applications[
        "application_id"
    ].isin(
        visit_decline_application_ids
    )
    &
    (
        applications[
            "status"
        ]
        ==
        "recommended"
    ),
    "status",
] = "rejected"


# =========================================================
# 就業決定候補を作成
# =========================================================
#
# completed
# +
# result = continue
# +
# applicationがまだwithdrawn/rejectedでない
#
# 案件を対象とする。
# =========================================================

placement_candidates = (
    workplace_visits[
        (
            workplace_visits[
                "visit_status"
            ]
            ==
            "completed"
        )
        &
        (
            workplace_visits[
                "result"
            ]
            ==
            "continue"
        )
    ]
    .merge(
        applications,
        on="application_id",
        how="inner",
    )
)


placement_candidates = (
    placement_candidates[
        placement_candidates[
            "status"
        ]
        ==
        "recommended"
    ]
    .copy()
)


# 求人情報を追加
placement_candidates = (
    placement_candidates.merge(
        jobs[
            [
                "job_id",
                "occupation_id",
                "required_slots",
                "required_skill_level",
                "offered_hourly_wage",
                "open_date",
            ]
        ],
        on="job_id",
        how="left",
    )
)


# =========================================================
# 各案件の予定意思決定日を先に生成
# =========================================================
#
# 【変更前】
#
# visit_date順にplacement判定していた。
#
#
# 【問題点】
#
# 実際の募集枠消化は、
# 見学日よりも最終意思決定日の順で起こる方が自然。
#
#
# 【修正仕様】
#
# 各案件について、
# 見学後1～7日程度で最終意思決定予定日を生成し、
# その日付順でplacement処理する。
# =========================================================

decision_delays = []

planned_decision_dates = []


for _, row in (
    placement_candidates.iterrows()
):

    decision_delay = int(
        rng.integers(
            1,
            8,
        )
    )


    planned_decision_date = (
        row[
            "visit_date"
        ]
        +
        pd.Timedelta(
            days=decision_delay
        )
    )


    decision_delays.append(
        decision_delay
    )

    planned_decision_dates.append(
        planned_decision_date
    )


placement_candidates[
    "decision_delay"
] = (
    decision_delays
)


placement_candidates[
    "planned_decision_date"
] = (
    planned_decision_dates
)


placement_candidates = (
    placement_candidates
    .sort_values(
        [
            "planned_decision_date",
            "visit_date",
            "application_id",
        ]
    )
    .reset_index(
        drop=True
    )
)


# =========================================================
# 就業決定データ生成
# =========================================================

placement_data = []

review_data = []

placement_counter = 1

# 1候補者1placement
placed_candidates = set()

# 求人ごとのplacement人数
job_placement_counts = {}


for _, row in (
    placement_candidates.iterrows()
):

    application_id = (
        row[
            "application_id"
        ]
    )

    candidate_id = (
        row[
            "candidate_id"
        ]
    )

    job_id = (
        row[
            "job_id"
        ]
    )

    visit_date = (
        row[
            "visit_date"
        ]
    )

    intent_confirmed_date = (
        row[
            "intent_confirmed_date"
        ]
    )

    decision_delay = int(
        row[
            "decision_delay"
        ]
    )

    planned_decision_date = (
        row[
            "planned_decision_date"
        ]
    )


    # =====================================================
    # 既に別求人でplacement済みならスキップ
    # =====================================================

    if (
        candidate_id
        in
        placed_candidates
    ):

        continue


    # =====================================================
    # 求人情報
    # =====================================================

    required_slots = int(
        row[
            "required_slots"
        ]
    )

    required_skill_level = int(
        row[
            "required_skill_level"
        ]
    )

    offered_wage = float(
        row[
            "offered_hourly_wage"
        ]
    )


    # =====================================================
    # 希望条件
    # =====================================================
    #
    # 最終判断時点に最も近い条件として、
    # visit_date時点の希望条件を使用する。
    # =====================================================

    preference = (
        get_active_preference(
            candidate_id,
            visit_date,
        )
    )


    if preference is None:
        continue


    desired_wage = float(
        preference[
            "desired_hourly_wage"
        ]
    )


    wage_shortfall_rate = (
        calculate_wage_shortfall_rate(
            desired_wage,
            offered_wage,
        )
    )


    # =====================================================
    # H3 スキル
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

        skill_gap = None

    else:

        skill_gap = (
            candidate_skill
            -
            required_skill_level
        )


    # =====================================================
    # H5 選考日数
    # =====================================================

    intent_to_visit_days = (
        visit_date
        -
        intent_confirmed_date
    ).days


    process_days = (
        planned_decision_date
        -
        intent_confirmed_date
    ).days


    # =====================================================
    # 元々のsearch_end_dateとの整合
    # =====================================================

    original_search_end_date = (
        candidate_lookup.loc[
            candidate_id,
            "search_end_date",
        ]
    )


    # 見学後、
    # 意思決定予定日前に元々の求職終了日が来る場合
    # post_visit withdrawalとして扱う。
    if (
        pd.notna(
            original_search_end_date
        )
        and
        original_search_end_date
        >=
        visit_date
        and
        original_search_end_date
        <
        planned_decision_date
    ):

        set_application_withdrawal(
            application_id=(
                application_id
            ),
            withdrawal_date=(
                original_search_end_date
            ),
            withdrawal_stage=(
                "post_visit"
            ),
            withdrawal_reason=(
                "other"
            ),
        )


        review_data.append(
            [
                application_id,
                candidate_id,
                job_id,
                visit_date,
                planned_decision_date,
                decision_delay,
                desired_wage,
                offered_wage,
                wage_shortfall_rate,
                candidate_skill,
                required_skill_level,
                skill_gap,
                intent_to_visit_days,
                process_days,
                np.nan,
                True,
                np.nan,
                "post_visit_withdrawal_existing_search_end",
            ]
        )

        continue


    # =====================================================
    # 右打ち切り
    # =====================================================
    #
    # 意思決定予定日がDATA_END_DATEより後の場合、
    # 最終結果は観察できていない。
    #
    # ただし、その前に辞退が発生するケースは
    # 次のpost_visit判定で観察可能。
    # =====================================================


    # =====================================================
    # post_visit辞退確率
    # =====================================================

    post_visit_withdrawal_probability = (
        get_post_visit_withdrawal_probability(
            wage_shortfall_rate=(
                wage_shortfall_rate
            ),
            intent_to_visit_days=(
                intent_to_visit_days
            ),
            decision_delay=(
                decision_delay
            ),
        )
    )


    withdraws_after_visit = (
        rng.random()
        <
        post_visit_withdrawal_probability
    )


    # =====================================================
    # post_visit辞退
    # =====================================================

    if withdraws_after_visit:

        withdrawal_delay = int(
            rng.integers(
                1,
                decision_delay + 1,
            )
        )


        withdrawal_date = (
            visit_date
            +
            pd.Timedelta(
                days=withdrawal_delay
            )
        )


        # 観察期間内の辞退のみ記録する
        if (
            withdrawal_date
            <=
            DATA_END_DATE
        ):

            withdrawal_reason = (
                select_post_visit_withdrawal_reason(
                    wage_shortfall_rate=(
                        wage_shortfall_rate
                    ),
                    intent_to_visit_days=(
                        intent_to_visit_days
                    ),
                    decision_delay=(
                        decision_delay
                    ),
                )
            )


            set_application_withdrawal(
                application_id=(
                    application_id
                ),
                withdrawal_date=(
                    withdrawal_date
                ),
                withdrawal_stage=(
                    "post_visit"
                ),
                withdrawal_reason=(
                    withdrawal_reason
                ),
            )


            review_data.append(
                [
                    application_id,
                    candidate_id,
                    job_id,
                    visit_date,
                    planned_decision_date,
                    decision_delay,
                    desired_wage,
                    offered_wage,
                    wage_shortfall_rate,
                    candidate_skill,
                    required_skill_level,
                    skill_gap,
                    intent_to_visit_days,
                    process_days,
                    post_visit_withdrawal_probability,
                    True,
                    np.nan,
                    "post_visit_withdrawal",
                ]
            )

            continue


    # =====================================================
    # 最終意思決定が観察期間外
    # =====================================================

    if (
        planned_decision_date
        >
        DATA_END_DATE
    ):

        review_data.append(
            [
                application_id,
                candidate_id,
                job_id,
                visit_date,
                planned_decision_date,
                decision_delay,
                desired_wage,
                offered_wage,
                wage_shortfall_rate,
                candidate_skill,
                required_skill_level,
                skill_gap,
                intent_to_visit_days,
                process_days,
                post_visit_withdrawal_probability,
                False,
                np.nan,
                "right_censored_before_decision",
            ]
        )

        continue


    # =====================================================
    # 募集枠上限
    # =====================================================

    current_placements = (
        job_placement_counts.get(
            job_id,
            0,
        )
    )


    if (
        current_placements
        >=
        required_slots
    ):

        # 募集枠が既に埋まっているため、
        # 企業側の最終不成立としてrejected扱い。
        applications.loc[
            applications[
                "application_id"
            ]
            ==
            application_id,
            "status",
        ] = "rejected"


        review_data.append(
            [
                application_id,
                candidate_id,
                job_id,
                visit_date,
                planned_decision_date,
                decision_delay,
                desired_wage,
                offered_wage,
                wage_shortfall_rate,
                candidate_skill,
                required_skill_level,
                skill_gap,
                intent_to_visit_days,
                process_days,
                post_visit_withdrawal_probability,
                False,
                0.0,
                "slot_filled",
            ]
        )

        continue


    # =====================================================
    # 最終placement確率
    # =====================================================

    placement_probability = (
        get_placement_probability(
            wage_shortfall_rate=(
                wage_shortfall_rate
            ),
            candidate_skill=(
                candidate_skill
            ),
            required_skill_level=(
                required_skill_level
            ),
            process_days=(
                process_days
            ),
        )
    )


    is_placed = (
        rng.random()
        <
        placement_probability
    )


    # =====================================================
    # 最終不成立
    # =====================================================
    #
    # 候補者辞退ではなく、
    # 最終的な採用・就業合意に至らなかった案件。
    #
    # withdrawal_stageには含めない。
    # =====================================================

    if not is_placed:

        applications.loc[
            applications[
                "application_id"
            ]
            ==
            application_id,
            "status",
        ] = "rejected"


        review_data.append(
            [
                application_id,
                candidate_id,
                job_id,
                visit_date,
                planned_decision_date,
                decision_delay,
                desired_wage,
                offered_wage,
                wage_shortfall_rate,
                candidate_skill,
                required_skill_level,
                skill_gap,
                intent_to_visit_days,
                process_days,
                post_visit_withdrawal_probability,
                False,
                placement_probability,
                "final_rejected",
            ]
        )

        continue


    # =====================================================
    # placement
    # =====================================================

    decision_date = (
        planned_decision_date
    )


    # =====================================================
    # 就業時給
    # =====================================================
    #
    # 基本は求人提示時給。
    #
    # 希望額の方が高い場合には、
    # 差額の0～50%程度を
    # 条件調整できるケースを残す。
    # =====================================================

    agreed_hourly_wage = (
        offered_wage
    )


    if (
        desired_wage
        >
        offered_wage
    ):

        wage_difference = (
            desired_wage
            -
            offered_wage
        )


        adjustment_ratio = (
            rng.uniform(
                0.0,
                0.50,
            )
        )


        agreed_hourly_wage += (
            wage_difference
            *
            adjustment_ratio
        )


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
        +
        pd.Timedelta(
            days=start_delay
        )
    )


    # =====================================================
    # placement status
    # =====================================================
    #
    # placementは最終就業決定済み。
    #
    # DATA_END_DATEまでに就業開始：
    # started
    #
    # 開始予定がDATA_END_DATEより後：
    # planned
    #
    # 「cancelled」は使用しない。
    #
    # placement後辞退は発生させないため。
    # =====================================================

    if (
        start_date
        <=
        DATA_END_DATE
    ):

        placement_status = (
            "started"
        )

    else:

        placement_status = (
            "planned"
        )


    # =====================================================
    # Placement ID
    # =====================================================

    placement_id = (
        f"PLC{placement_counter:06d}"
    )


    placement_data.append(
        [
            placement_id,
            application_id,
            decision_date,
            start_date,
            agreed_hourly_wage,
            placement_status,
        ]
    )


    placed_candidates.add(
        candidate_id
    )


    job_placement_counts[
        job_id
    ] = (
        current_placements
        +
        1
    )


    # applicationをplacementへ更新
    applications.loc[
        applications[
            "application_id"
        ]
        ==
        application_id,
        "status",
    ] = "placed"


    review_data.append(
        [
            application_id,
            candidate_id,
            job_id,
            visit_date,
            planned_decision_date,
            decision_delay,
            desired_wage,
            offered_wage,
            wage_shortfall_rate,
            candidate_skill,
            required_skill_level,
            skill_gap,
            intent_to_visit_days,
            process_days,
            post_visit_withdrawal_probability,
            False,
            placement_probability,
            "placed",
        ]
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


placements_review = pd.DataFrame(
    review_data,
    columns=[
        "application_id",
        "candidate_id",
        "job_id",
        "visit_date",
        "planned_decision_date",
        "decision_delay",
        "desired_hourly_wage",
        "offered_hourly_wage",
        "wage_shortfall_rate",
        "candidate_skill_level",
        "required_skill_level",
        "skill_gap",
        "intent_to_visit_days",
        "intent_to_decision_days",
        "post_visit_withdrawal_probability",
        "post_visit_withdrawal",
        "placement_probability",
        "final_state",
    ],
)


# =========================================================
# placement基本品質チェック
# =========================================================

assert placements[
    "placement_id"
].is_unique


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
].gt(
    0
).all()


# placementは最終決定なので
# cancelledは存在しない。
assert placements[
    "status"
].isin(
    [
        "planned",
        "started",
    ]
).all()


# =========================================================
# placement上流プロセス品質チェック
# =========================================================

# placement_process_check = (
#     placements.merge(
#         applications[
#             [
#                 "application_id",
#                 "candidate_id",
#                 "job_id",
#                 "status",
#                 "recommendation_result",
#                 "withdrawal_stage",
#                 "withdrawal_date",
#                 "intent_confirmed_date",
#             ]
#         ],
#         on="application_id",
#         how="left",
#     )
#     .merge(
#         workplace_visits[
#             [
#                 "application_id",
#                 "visit_status",
#                 "result",
#                 "visit_date",
#             ]
#         ],
#         on="application_id",
#         how="left",
#     )
# )

# =========================================================
# placement上流プロセス品質チェック
# =========================================================
#
# 【修正】
#
# placementsにもstatus列があり、
# applicationsにもstatus列がある。
#
# そのままmergeするとpandasによって
#
# status_x
# status_y
#
# のように自動リネームされ、
# 後続処理で
#
# placement_process_check["status"]
#
# を参照するとKeyErrorになる。
#
# そこでmerge前に、
#
# placements.status
#     → placement_status
#
# applications.status
#     → application_status
#
# と明示的に名前を分ける。
# =========================================================

placement_process_check = (
    placements.rename(
        columns={
            "status":
                "placement_status",
        }
    )
    .merge(
        applications[
            [
                "application_id",
                "candidate_id",
                "job_id",
                "status",
                "recommendation_result",
                "withdrawal_stage",
                "withdrawal_date",
                "intent_confirmed_date",
            ]
        ].rename(
            columns={
                "status":
                    "application_status",
            }
        ),
        on="application_id",
        how="left",
    )
    .merge(
        workplace_visits[
            [
                "application_id",
                "visit_status",
                "result",
                "visit_date",
            ]
        ],
        on="application_id",
        how="left",
    )
)

# 推薦accepted
assert (
    placement_process_check[
        "recommendation_result"
    ]
    ==
    "accepted"
).all()


# completed visit
assert (
    placement_process_check[
        "visit_status"
    ]
    ==
    "completed"
).all()


# visit result continue
assert (
    placement_process_check[
        "result"
    ]
    ==
    "continue"
).all()


# # application status = placed
# assert (
#     placement_process_check[
#         "status"
#     ]
#     ==
#     "placed"
# ).all()

# application status = placed
assert (
    placement_process_check[
        "application_status"
    ]
    ==
    "placed"
).all()

# placement側のstatusは
# planned / startedのみ
assert placement_process_check[
    "placement_status"
].isin(
    [
        "planned",
        "started",
    ]
).all()

# placement後辞退なし
assert placement_process_check[
    "withdrawal_stage"
].isna().all()


assert placement_process_check[
    "withdrawal_date"
].isna().all()


# decision_dateはvisit_date以降
assert (
    placement_process_check[
        "decision_date"
    ]
    >=
    placement_process_check[
        "visit_date"
    ]
).all()


# start_dateはdecision_date以降
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
# 1候補者1placement
# =========================================================

assert not placement_process_check.duplicated(
    subset=[
        "candidate_id"
    ]
).any()


# =========================================================
# 求人募集枠超過チェック
# =========================================================

job_placement_check = (
    placement_process_check
    .groupby(
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
# 修正④ candidates更新
# =========================================================
#
# placementは最終就業決定なので、
#
# status = placed
# search_end_date = decision_date
#
# とする。
# =========================================================

candidate_placements = (
    placement_process_check[
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
        ==
        candidate_id,
        "status",
    ] = "placed"


    candidates.loc[
        candidates[
            "candidate_id"
        ]
        ==
        candidate_id,
        "search_end_date",
    ] = decision_date


# =========================================================
# 修正⑤ placement後ライフサイクル最終整合
# =========================================================
#
# 【変更前】
#
# placements生成後に
# candidates.search_end_dateだけを更新していた。
#
#
# 【問題点】
#
# 下流テーブルは既に生成済みなので、
#
# decision_date
# <
# activity_date
#
# のような未来イベントが残る可能性があった。
#
#
# 【修正仕様】
#
# placementした候補者について、
# decision_dateより後のイベントを整理する。
#
# 1. candidate_activities
# 2. job_entries
# 3. job_introductions
# 4. applications
# 5. workplace_visits
# 6. candidate_preferences
#
# を依存関係を壊さない順番で処理する。
#
# placementに至ったapplication自身は保持する。
#
# placement前から存在していた別applicationで、
# placement日時点でも選考中だったものは、
#
# withdrawal_reason = accepted_other_job
#
# として終了させる。
#
# H5分析ではこの理由を
# process_delay等の辞退とは別に確認できる。
# =========================================================


# candidate_id → placement decision_date
placement_date_map = dict(
    zip(
        candidate_placements[
            "candidate_id"
        ],
        candidate_placements[
            "decision_date"
        ],
    )
)


# placement application ID
placed_application_ids = set(
    placements[
        "application_id"
    ]
)


# =========================================================
# 5-1 candidate_activities
# =========================================================

activity_candidate_decision = (
    candidate_activities[
        "candidate_id"
    ].map(
        placement_date_map
    )
)


keep_activity_mask = (
    activity_candidate_decision.isna()
    |
    (
        candidate_activities[
            "activity_date"
        ]
        <=
        activity_candidate_decision
    )
)


candidate_activities = (
    candidate_activities[
        keep_activity_mask
    ]
    .copy()
)


# =========================================================
# 5-2 job_entries
# =========================================================

entry_candidate_decision = (
    job_entries[
        "candidate_id"
    ].map(
        placement_date_map
    )
)


keep_entry_mask = (
    entry_candidate_decision.isna()
    |
    (
        job_entries[
            "entry_date"
        ]
        <=
        entry_candidate_decision
    )
)


job_entries = (
    job_entries[
        keep_entry_mask
    ]
    .copy()
)


# =========================================================
# 5-3 job_introductions
# =========================================================
#
# introductionはactivityに紐づくため、
# 削除済みactivityを参照するintroductionsを削除する。
# =========================================================

valid_activity_ids = set(
    candidate_activities[
        "activity_id"
    ]
)


job_introductions = (
    job_introductions[
        job_introductions[
            "activity_id"
        ].isin(
            valid_activity_ids
        )
    ]
    .copy()
)


# =========================================================
# 5-4 placement後に開始したapplicationsを削除
# =========================================================

application_decision_dates = (
    applications[
        "candidate_id"
    ].map(
        placement_date_map
    )
)


future_application_mask = (
    application_decision_dates.notna()
    &
    (
        applications[
            "intent_confirmed_date"
        ]
        >
        application_decision_dates
    )
)


future_application_ids = set(
    applications.loc[
        future_application_mask,
        "application_id",
    ]
)


applications = (
    applications[
        ~future_application_mask
    ]
    .copy()
)


# future applicationに紐づくvisitも削除
workplace_visits = (
    workplace_visits[
        ~workplace_visits[
            "application_id"
        ].isin(
            future_application_ids
        )
    ]
    .copy()
)


# =========================================================
# 5-5 placement前から存在した他applicationを終了
# =========================================================

for candidate_id, decision_date in (
    placement_date_map.items()
):

    candidate_application_indices = (
        applications.index[
            (
                applications[
                    "candidate_id"
                ]
                ==
                candidate_id
            )
            &
            (
                ~applications[
                    "application_id"
                ].isin(
                    placed_application_ids
                )
            )
        ]
    )


    for app_index in (
        candidate_application_indices
    ):

        app = (
            applications.loc[
                app_index
            ]
        )


        # ---------------------------------------------
        # 既にdecision_date以前に終了している案件
        # ---------------------------------------------

        already_withdrawn_before_decision = (
            pd.notna(
                app[
                    "withdrawal_date"
                ]
            )
            and
            (
                app[
                    "withdrawal_date"
                ]
                <=
                decision_date
            )
        )


        if already_withdrawn_before_decision:
            continue


        # screened_out / rejectedは
        # 既に終了済みなので変更しない
        if (
            app[
                "status"
            ]
            in
            [
                "screened_out",
                "rejected",
            ]
        ):

            continue


        application_id = (
            app[
                "application_id"
            ]
        )


        # ---------------------------------------------
        # decision_dateまでに
        # 職場見学completed済みか確認
        # ---------------------------------------------

        app_visits = (
            workplace_visits[
                workplace_visits[
                    "application_id"
                ]
                ==
                application_id
            ]
        )


        completed_before_decision = (
            (
                app_visits[
                    "visit_status"
                ]
                ==
                "completed"
            )
            &
            (
                app_visits[
                    "visit_date"
                ].notna()
            )
            &
            (
                app_visits[
                    "visit_date"
                ]
                <=
                decision_date
            )
        ).any()


        # ---------------------------------------------
        # 推薦済みか
        # ---------------------------------------------

        recommended_before_decision = (
            pd.notna(
                app[
                    "recommendation_date"
                ]
            )
            and
            (
                app[
                    "recommendation_date"
                ]
                <=
                decision_date
            )
        )


        # ---------------------------------------------
        # 辞退ステージ決定
        # ---------------------------------------------

        if completed_before_decision:

            withdrawal_stage = (
                "post_visit"
            )

        elif recommended_before_decision:

            withdrawal_stage = (
                "post_recommendation"
            )

        else:

            withdrawal_stage = (
                "pre_recommendation"
            )


        applications.loc[
            app_index,
            "withdrawal_date",
        ] = decision_date


        applications.loc[
            app_index,
            "withdrawal_reason",
        ] = "accepted_other_job"


        applications.loc[
            app_index,
            "withdrawal_stage",
        ] = withdrawal_stage


        applications.loc[
            app_index,
            "status",
        ] = "withdrawn"


        # recommendation_dateがplacement後なら
        # 実際には推薦されていないため消す。
        if (
            pd.notna(
                app[
                    "recommendation_date"
                ]
            )
            and
            (
                app[
                    "recommendation_date"
                ]
                >
                decision_date
            )
        ):

            applications.loc[
                app_index,
                "recommendation_date",
            ] = pd.NaT


            applications.loc[
                app_index,
                "recommendation_result",
            ] = None


# =========================================================
# 5-6 placement後のworkplace_visitを整理
# =========================================================

application_candidate_map = (
    applications[
        [
            "application_id",
            "candidate_id",
        ]
    ]
    .set_index(
        "application_id"
    )[
        "candidate_id"
    ]
    .to_dict()
)


visit_keep_flags = []


for _, visit in (
    workplace_visits.iterrows()
):

    application_id = (
        visit[
            "application_id"
        ]
    )


    candidate_id = (
        application_candidate_map.get(
            application_id
        )
    )


    if candidate_id is None:

        visit_keep_flags.append(
            False
        )

        continue


    decision_date = (
        placement_date_map.get(
            candidate_id
        )
    )


    if decision_date is None:

        visit_keep_flags.append(
            True
        )

        continue


    # placement application自身は保持
    if (
        application_id
        in
        placed_application_ids
    ):

        visit_keep_flags.append(
            True
        )

        continue


    # scheduled_date自体がplacement後なら削除
    if (
        visit[
            "scheduled_date"
        ]
        >
        decision_date
    ):

        visit_keep_flags.append(
            False
        )

        continue


    # completed visitがplacement後なら削除
    if (
        pd.notna(
            visit[
                "visit_date"
            ]
        )
        and
        (
            visit[
                "visit_date"
            ]
            >
            decision_date
        )
    ):

        visit_keep_flags.append(
            False
        )

        continue


    # placement前にscheduledされたが
    # まだ実施していなかった場合、
    # accepted_other_jobによるcancelledへ変更
    if (
        visit[
            "visit_status"
        ]
        ==
        "scheduled"
    ):

        workplace_visits.loc[
            visit.name,
            "visit_status",
        ] = "cancelled"


        workplace_visits.loc[
            visit.name,
            "visit_date",
        ] = pd.NaT


        workplace_visits.loc[
            visit.name,
            "result",
        ] = None


    visit_keep_flags.append(
        True
    )


workplace_visits = (
    workplace_visits.loc[
        visit_keep_flags
    ]
    .copy()
)


# =========================================================
# 5-7 candidate_preferencesをplacement日で終了
# =========================================================
#
# placement後に開始する希望条件は削除。
#
# placement日時点で有効だった希望条件は、
# effective_to = decision_date
# とする。
# =========================================================

preferences_to_drop = []


for pref_index, preference in (
    candidate_preferences.iterrows()
):

    candidate_id = (
        preference[
            "candidate_id"
        ]
    )


    decision_date = (
        placement_date_map.get(
            candidate_id
        )
    )


    if decision_date is None:
        continue


    # placement後に開始する希望条件
    if (
        preference[
            "effective_from"
        ]
        >
        decision_date
    ):

        preferences_to_drop.append(
            pref_index
        )

        continue


    # placement日時点以降まで有効な希望条件を
    # placement日で終了
    if (
        pd.isna(
            preference[
                "effective_to"
            ]
        )
        or
        (
            preference[
                "effective_to"
            ]
            >
            decision_date
        )
    ):

        candidate_preferences.loc[
            pref_index,
            "effective_to",
        ] = decision_date


candidate_preferences = (
    candidate_preferences.drop(
        index=preferences_to_drop
    )
    .copy()
)


# =========================================================
# 5-8 job_entries status再計算
# =========================================================
#
# applicationsをライフサイクル調整したため、
# converted / declinedをもう一度計算する。
# =========================================================

remaining_source_entry_ids = set(
    applications[
        "source_entry_id"
    ]
    .dropna()
)


job_entries[
    "status"
] = np.where(
    job_entries[
        "entry_id"
    ].isin(
        remaining_source_entry_ids
    ),
    "converted",
    "declined",
)


# =========================================================
# 修正⑥ 最終ライフサイクル品質チェック
# =========================================================
#
# placement後に、
#
# ・candidate_activity
# ・job_entry
# ・job_introduction
# ・application開始
# ・workplace_visit
#
# が存在しないことを確認する。
# =========================================================


# ---------------------------------------------------------
# candidate_activities
# ---------------------------------------------------------

activity_lifecycle_check = (
    candidate_activities[
        [
            "candidate_id",
            "activity_date",
        ]
    ].copy()
)


activity_lifecycle_check[
    "decision_date"
] = (
    activity_lifecycle_check[
        "candidate_id"
    ].map(
        placement_date_map
    )
)


placed_activity_check = (
    activity_lifecycle_check[
        activity_lifecycle_check[
            "decision_date"
        ].notna()
    ]
)


assert (
    placed_activity_check[
        "activity_date"
    ]
    <=
    placed_activity_check[
        "decision_date"
    ]
).all()


# ---------------------------------------------------------
# job_entries
# ---------------------------------------------------------

entry_lifecycle_check = (
    job_entries[
        [
            "candidate_id",
            "entry_date",
        ]
    ].copy()
)


entry_lifecycle_check[
    "decision_date"
] = (
    entry_lifecycle_check[
        "candidate_id"
    ].map(
        placement_date_map
    )
)


placed_entry_check = (
    entry_lifecycle_check[
        entry_lifecycle_check[
            "decision_date"
        ].notna()
    ]
)


assert (
    placed_entry_check[
        "entry_date"
    ]
    <=
    placed_entry_check[
        "decision_date"
    ]
).all()


# ---------------------------------------------------------
# job_introductions
# ---------------------------------------------------------

introduction_lifecycle_check = (
    job_introductions.merge(
        candidate_activities[
            [
                "activity_id",
                "candidate_id",
                "activity_date",
            ]
        ],
        on="activity_id",
        how="left",
    )
)


assert introduction_lifecycle_check[
    "candidate_id"
].notna().all()


introduction_lifecycle_check[
    "decision_date"
] = (
    introduction_lifecycle_check[
        "candidate_id"
    ].map(
        placement_date_map
    )
)


placed_introduction_check = (
    introduction_lifecycle_check[
        introduction_lifecycle_check[
            "decision_date"
        ].notna()
    ]
)


assert (
    placed_introduction_check[
        "activity_date"
    ]
    <=
    placed_introduction_check[
        "decision_date"
    ]
).all()


# ---------------------------------------------------------
# applications
# ---------------------------------------------------------

application_lifecycle_check = (
    applications[
        [
            "application_id",
            "candidate_id",
            "intent_confirmed_date",
        ]
    ].copy()
)


application_lifecycle_check[
    "decision_date"
] = (
    application_lifecycle_check[
        "candidate_id"
    ].map(
        placement_date_map
    )
)


placed_application_check = (
    application_lifecycle_check[
        application_lifecycle_check[
            "decision_date"
        ].notna()
    ]
)


assert (
    placed_application_check[
        "intent_confirmed_date"
    ]
    <=
    placed_application_check[
        "decision_date"
    ]
).all()


# ---------------------------------------------------------
# candidate_preferences
# ---------------------------------------------------------

preference_lifecycle_check = (
    candidate_preferences[
        [
            "candidate_id",
            "effective_from",
            "effective_to",
        ]
    ].copy()
)


preference_lifecycle_check[
    "decision_date"
] = (
    preference_lifecycle_check[
        "candidate_id"
    ].map(
        placement_date_map
    )
)


placed_preference_check = (
    preference_lifecycle_check[
        preference_lifecycle_check[
            "decision_date"
        ].notna()
    ]
)


assert (
    placed_preference_check[
        "effective_from"
    ]
    <=
    placed_preference_check[
        "decision_date"
    ]
).all()


placed_preference_with_end = (
    placed_preference_check[
        placed_preference_check[
            "effective_to"
        ].notna()
    ]
)


assert (
    placed_preference_with_end[
        "effective_to"
    ]
    <=
    placed_preference_with_end[
        "decision_date"
    ]
).all()


# =========================================================
# withdrawal_stage最終品質チェック
# =========================================================

assert applications[
    "withdrawal_stage"
].dropna().isin(
    [
        "pre_recommendation",
        "post_recommendation",
        "post_visit",
    ]
).all()


# placed applicationにはwithdrawalなし
final_placed_application_rows = (
    applications[
        applications[
            "status"
        ]
        ==
        "placed"
    ]
)


assert final_placed_application_rows[
    "withdrawal_stage"
].isna().all()


assert final_placed_application_rows[
    "withdrawal_date"
].isna().all()


# =========================================================
# candidates最終品質チェック
# =========================================================

placed_candidate_rows = (
    candidates[
        candidates[
            "status"
        ]
        ==
        "placed"
    ]
)


assert placed_candidate_rows[
    "search_end_date"
].notna().all()


assert (
    placed_candidate_rows[
        "search_end_date"
    ]
    <=
    DATA_END_DATE
).all()


# =========================================================
# CSV出力
# =========================================================
#
# 【変更前】
#
# placements_test.csv
# applications_test.csv
# candidates_test.csv
#
#
# 【修正仕様】
#
# placements.csvを出力。
#
# 加えて、
# placement後ライフサイクル調整を反映した
# 各rawテーブルを正式ファイルへ上書きする。
# =========================================================

placements.to_csv(
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


candidates.to_csv(
    OUTPUT_DIR
    / "candidates.csv",
    index=False,
    encoding="utf-8-sig",
)


candidate_activities.to_csv(
    OUTPUT_DIR
    / "candidate_activities.csv",
    index=False,
    encoding="utf-8-sig",
)


job_entries.to_csv(
    OUTPUT_DIR
    / "job_entries.csv",
    index=False,
    encoding="utf-8-sig",
)


job_introductions.to_csv(
    OUTPUT_DIR
    / "job_introductions.csv",
    index=False,
    encoding="utf-8-sig",
)


workplace_visits.to_csv(
    OUTPUT_DIR
    / "workplace_visits.csv",
    index=False,
    encoding="utf-8-sig",
)


candidate_preferences.to_csv(
    OUTPUT_DIR
    / "candidate_preferences.csv",
    index=False,
    encoding="utf-8-sig",
)


placements_review.to_csv(
    REVIEW_FILE,
    index=False,
    encoding="utf-8-sig",
)


# =========================================================
# 内容確認
# =========================================================

print(
    "分析用就業決定データを生成しました。"
)

print()

print(
    f"placement件数: "
    f"{len(placements):,}"
)


# =========================================================
# placement status
# =========================================================

print()
print(
    "【就業ステータス】"
)

print(
    placements[
        "status"
    ].value_counts()
)


# =========================================================
# placement率目安
# =========================================================

if len(
    applications
) > 0:

    overall_placement_rate = (
        len(
            placements
        )
        /
        len(
            applications
        )
    )

else:

    overall_placement_rate = (
        np.nan
    )


print()
print(
    "【application全体に対するplacement率】"
)

print(
    f"{overall_placement_rate:.1%}"
)


print()
print(
    "【placement件数目安】"
)

if (
    200
    <=
    len(
        placements
    )
    <=
    300
):

    print(
        "目標目安200～300件に入っています。"
    )

else:

    print(
        "目標目安200～300件の外です。"
    )

    print(
        "最終生成後、統計結果ではなく"
        "分析可能なファネル件数として確認します。"
    )


# =========================================================
# 辞退ステージ
# =========================================================

print()
print(
    "【辞退ステージ別件数】"
)

print(
    applications[
        "withdrawal_stage"
    ].value_counts(
        dropna=False
    )
)


# accepted_other_jobは、
# process_delay分析では別途扱うことができる。
print()
print(
    "【辞退理由別件数】"
)

print(
    applications[
        "withdrawal_reason"
    ].value_counts(
        dropna=False
    )
)


# =========================================================
# application status
# =========================================================

print()
print(
    "【応募案件ステータス更新後】"
)

print(
    applications[
        "status"
    ].value_counts()
)


# =========================================================
# candidate status
# =========================================================

print()
print(
    "【求職者ステータス更新後】"
)

print(
    candidates[
        "status"
    ].value_counts()
)


# =========================================================
# 求人別placement数
# =========================================================

print()
print(
    "【求人別placement件数の基本統計量】"
)

if len(
    placement_process_check
) > 0:

    print(
        placement_process_check
        .groupby(
            "job_id"
        )
        .size()
        .describe()
    )

else:

    print(
        "placementなし"
    )


# =========================================================
# H2 給与
# =========================================================

print()
print(
    "【placement候補の給与不足率】"
)

print(
    placements_review[
        "wage_shortfall_rate"
    ].describe()
)


# =========================================================
# H3 スキル
# =========================================================

print()
print(
    "【placement候補のskill_gap】"
)

print(
    placements_review[
        "skill_gap"
    ].describe()
)


# =========================================================
# H5 プロセス
# =========================================================

print()
print(
    "【応募→最終意思決定予定日数】"
)

print(
    placements_review[
        "intent_to_decision_days"
    ].describe()
)


# =========================================================
# post_visit withdrawal
# =========================================================

post_visit_withdrawal_count = (
    (
        applications[
            "withdrawal_stage"
        ]
        ==
        "post_visit"
    ).sum()
)


completed_continue_count = (
    (
        workplace_visits[
            "visit_status"
        ]
        ==
        "completed"
    )
    &
    (
        workplace_visits[
            "result"
        ]
        ==
        "continue"
    )
).sum()


print()
print(
    "【職場見学後辞退】"
)

print(
    f"completed + continue件数: "
    f"{completed_continue_count:,}"
)

print(
    f"post_visit辞退件数: "
    f"{post_visit_withdrawal_count:,}"
)


if (
    completed_continue_count
    >
    0
):

    print(
        "post_visit辞退率: "
        f"{post_visit_withdrawal_count / completed_continue_count:.1%}"
    )


# =========================================================
# 最終ライフサイクル確認
# =========================================================

print()
print(
    "【placement後の未来イベント確認】"
)

print(
    "candidate_activities: "
    f"{len(placed_activity_check):,}件を検査 → OK"
)

print(
    "job_entries: "
    f"{len(placed_entry_check):,}件を検査 → OK"
)

print(
    "job_introductions: "
    f"{len(placed_introduction_check):,}件を検査 → OK"
)

print(
    "applications: "
    f"{len(placed_application_check):,}件を検査 → OK"
)

print(
    "candidate_preferences: "
    f"{len(placed_preference_check):,}件を検査 → OK"
)


# =========================================================
# サンプル
# =========================================================

print()
print(
    "【placementsサンプル：先頭20件】"
)

print(
    placements
    .sort_values(
        "decision_date"
    )
    .head(
        20
    )
)


print()
print(
    "【placements_reviewサンプル：先頭20件】"
)

print(
    placements_review
    .sort_values(
        "planned_decision_date"
    )
    .head(
        20
    )
)