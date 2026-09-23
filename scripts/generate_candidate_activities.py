from pathlib import Path

import numpy as np
import pandas as pd


# =========================================================
# 基本設定
# =========================================================

OUTPUT_DIR = Path("data/raw")

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

OUTPUT_FILE = (
    OUTPUT_DIR
    / "candidate_activities.csv"
)

# このスクリプト専用の乱数シード
#
# 分析結果を確認した後で、
# 都合のよいseedへ変更しない。
SEED = 46
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
#
#
# 【問題点】
#
# 小規模テスト用ファイルを参照していた。
#
#
# 【修正仕様】
#
# 分析用データ生成では
# candidates.csv を利用する。
# =========================================================

candidates = pd.read_csv(
    OUTPUT_DIR / "candidates.csv",
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
# 入力データの基本品質チェック
# =========================================================

assert candidates[
    "candidate_id"
].is_unique

assert recruiters[
    "recruiter_id"
].is_unique

assert candidates[
    "registration_date"
].notna().all()

assert (
    recruiters[
        "role_type"
    ]
    ==
    "CA"
).any()


# =========================================================
# 指定日に稼働中のCAを取得する関数
# =========================================================

def get_active_ca(
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

    return active_ca[
        "recruiter_id"
    ].tolist()


# =========================================================
# 指定CAが活動日時点で稼働中か確認する関数
# =========================================================
#
# 【変更前】
#
# candidatesにca_idが存在すれば、
# そのCAを後続活動でも継続利用する可能性があった。
#
#
# 【問題点】
#
# CAが途中で離任した場合、
# activity_date時点では在籍していないCAが
# 活動担当者になる可能性がある。
#
#
# 【修正仕様】
#
# 小規模テストで修正済みのロジックを維持し、
# activity_dateごとにCA在籍状況を確認する。
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
# 活動日時点の担当CAを取得する関数
# =========================================================

def get_activity_ca(
    current_ca_id,
    target_date,
):

    # 現在の担当CAが
    # activity_date時点でも在籍していれば継続
    if is_ca_active(
        current_ca_id,
        target_date,
    ):

        return (
            current_ca_id
        )


    # 未割当または離任済みの場合は、
    # その日時点の稼働CAから再割当する。
    active_ca_ids = (
        get_active_ca(
            target_date
        )
    )


    if len(
        active_ca_ids
    ) == 0:

        return None


    return rng.choice(
        active_ca_ids
    )


# =========================================================
# 修正① 月別CA負荷を計算
# =========================================================
#
# 【変更前】
#
# 初回連絡・初回面談までの日数を、
#
# 2025年
# 2026年
#
# という年だけで直接分けていた。
#
# 例：
#
# 2025初回連絡：0～3日
# 2026初回連絡：1～5日
#
#
# 【問題点】
#
# これでは
#
# 「2026年だから処理が遅い」
#
# という結果を直接生成している。
#
# H1では、
#
# 求人・候補者需要増加
# ↓
# CA1人あたり負荷上昇
# ↓
# 対応速度への影響
#
# という構造を確認したい。
#
#
# 【修正仕様】
#
# 各月について、
#
# 月内アクティブ候補者数
# ÷
# 月内稼働CA数
#
# を計算し、
#
# CA1人あたりアクティブ候補者数
#
# を負荷指標として利用する。
#
# 2025年4～12月の負荷中央値を
# baseline_loadとし、
#
# workload_ratio
# =
# 当月負荷 / baseline_load
#
# を計算する。
#
# workload_ratioが高いほど、
# 初回連絡・面談までの日数が
# 少し伸びやすくなる。
#
# ただし確率的に生成し、
# workloadが高いから必ず遅れる
# という決定論にはしない。
# =========================================================


# ---------------------------------------------------------
# 分析期間の月一覧
# ---------------------------------------------------------

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


    # -----------------------------------------------------
    # 月内に求職活動可能な候補者
    # -----------------------------------------------------
    #
    # registration_date <= 月末
    #
    # かつ
    #
    # search_end_dateがNULL
    # または
    # search_end_date >= 月初
    # -----------------------------------------------------

    active_candidate_mask = (
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
    )


    active_candidate_count = int(
        active_candidate_mask.sum()
    )


    # -----------------------------------------------------
    # 月末時点の稼働CA
    # -----------------------------------------------------

    active_ca_ids = (
        get_active_ca(
            month_end
        )
    )


    active_ca_count = (
        len(
            active_ca_ids
        )
    )


    assert (
        active_ca_count
        >
        0
    )


    ca_load = (
        active_candidate_count
        /
        active_ca_count
    )


    monthly_ca_workload_data.append(
        [
            month,
            active_candidate_count,
            active_ca_count,
            ca_load,
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


# ---------------------------------------------------------
# 2025年4～12月の負荷中央値を基準にする
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# 月 → workload_ratio の辞書
# ---------------------------------------------------------

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


# =========================================================
# 指定日のCA負荷比率を取得する関数
# =========================================================

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
# 修正② 負荷による追加遅延を生成する関数
# =========================================================
#
# workload_ratio <= 1
# の場合は追加遅延なし。
#
# workload_ratio > 1
# では負荷上昇幅に応じて、
# Poisson分布から追加日数を生成する。
#
# 同じ負荷でも0日のケースを残すことで
# ランダム性を維持する。
# =========================================================

def generate_workload_delay(
    target_date,
    effect_strength,
    max_extra_days,
):

    workload_ratio = (
        get_ca_workload_ratio(
            target_date
        )
    )


    excess_load = max(
        0.0,
        workload_ratio
        - 1.0,
    )


    if (
        excess_load
        <=
        0
    ):

        return 0


    poisson_lambda = (
        excess_load
        *
        effect_strength
    )


    extra_days = int(
        rng.poisson(
            poisson_lambda
        )
    )


    return int(
        min(
            extra_days,
            max_extra_days,
        )
    )


# =========================================================
# 候補者対応履歴を生成
# =========================================================

activity_data = []

activity_counter = 1


for _, candidate in candidates.iterrows():

    candidate_id = (
        candidate[
            "candidate_id"
        ]
    )

    registration_date = (
        candidate[
            "registration_date"
        ]
    )

    search_end_date = (
        candidate[
            "search_end_date"
        ]
    )


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
    # 修正③ 初回連絡日
    # =====================================================
    #
    # 【変更前】
    #
    # 2025：
    # 0～3日
    #
    # 2026：
    # 1～5日
    #
    #
    # 【問題点】
    #
    # 年そのものが遅延原因になっていた。
    #
    #
    # 【修正仕様】
    #
    # 基本的には0～3日程度。
    #
    # そこへ当月のCA負荷が
    # 基準より高い場合のみ、
    # 0～数日の追加遅延を確率的に加える。
    # =====================================================

    base_contact_delay = int(
        rng.integers(
            0,
            4,
        )
    )


    workload_contact_delay = (
        generate_workload_delay(
            target_date=(
                registration_date
            ),
            effect_strength=3.0,
            max_extra_days=4,
        )
    )


    contact_delay = (
        base_contact_delay
        +
        workload_contact_delay
    )


    initial_contact_date = (
        registration_date
        +
        pd.Timedelta(
            days=contact_delay
        )
    )


    # 求職期間終了後または
    # DATA_END_DATE後になる場合は生成しない。
    if (
        initial_contact_date
        >
        activity_limit_date
    ):

        continue


    # =====================================================
    # 初回連絡日時点の担当CA
    # =====================================================

    existing_ca = (
        candidate[
            "ca_id"
        ]
    )


    ca_id = (
        get_activity_ca(
            existing_ca,
            initial_contact_date,
        )
    )


    if ca_id is None:
        continue


    # =====================================================
    # 初回連絡
    # =====================================================

    activity_id = (
        f"ACT{activity_counter:06d}"
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
    # 初回面談へ進むか
    # =====================================================
    #
    # 【変更前】
    #
    # 85%
    #
   #
    # 【修正仕様】
    #
    # 小規模テストで問題はなかったため、
    # 85%を維持する。
    # =====================================================

    has_interview = (
        rng.random()
        <
        0.85
    )


    if not has_interview:
        continue


    # =====================================================
    # 修正④ 初回面談日
    # =====================================================
    #
    # 【変更前】
    #
    # 2025：
    # 1～5日
    #
    # 2026：
    # 2～8日
    #
    #
    # 【修正仕様】
    #
    # 基本1～5日程度。
    #
    # 初回連絡日時点のCA負荷に応じて、
    # 数日の追加遅延を発生させる。
    # =====================================================

    base_interview_delay = int(
        rng.integers(
            1,
            6,
        )
    )


    workload_interview_delay = (
        generate_workload_delay(
            target_date=(
                initial_contact_date
            ),
            effect_strength=4.0,
            max_extra_days=5,
        )
    )


    interview_delay = (
        base_interview_delay
        +
        workload_interview_delay
    )


    initial_interview_date = (
        initial_contact_date
        +
        pd.Timedelta(
            days=interview_delay
        )
    )


    if (
        initial_interview_date
        >
        activity_limit_date
    ):

        continue


    # =====================================================
    # 初回面談日時点のCA
    # =====================================================

    ca_id = (
        get_activity_ca(
            ca_id,
            initial_interview_date,
        )
    )


    if ca_id is None:
        continue


    activity_id = (
        f"ACT{activity_counter:06d}"
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
    #
    # 【変更前】
    #
    # 0回：30%
    # 1回：50%
    # 2回：20%
    #
    #
    # 【修正仕様】
    #
    # 大規模化しても、
    # 候補者1人あたりの活動回数まで
    # 不自然に増やす必要はないため維持する。
    # =====================================================

    n_follow_ups = int(
        rng.choice(
            [
                0,
                1,
                2,
            ],
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

        # -------------------------------------------------
        # 基本フォロー間隔
        # -------------------------------------------------

        base_follow_up_delay = int(
            rng.integers(
                7,
                22,
            )
        )


        # -------------------------------------------------
        # CA負荷による追加遅延
        # -------------------------------------------------
        #
        # follow_upについては、
        # 初回連絡・面談よりも負荷影響を弱くする。
        # -------------------------------------------------

        workload_follow_up_delay = (
            generate_workload_delay(
                target_date=(
                    previous_activity_date
                ),
                effect_strength=2.0,
                max_extra_days=3,
            )
        )


        follow_up_delay = (
            base_follow_up_delay
            +
            workload_follow_up_delay
        )


        follow_up_date = (
            previous_activity_date
            +
            pd.Timedelta(
                days=follow_up_delay
            )
        )


        if (
            follow_up_date
            >
            activity_limit_date
        ):

            break


        # -------------------------------------------------
        # フォロー日時点のCA
        # -------------------------------------------------

        ca_id = (
            get_activity_ca(
                ca_id,
                follow_up_date,
            )
        )


        if ca_id is None:
            break


        activity_id = (
            f"ACT{activity_counter:06d}"
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

assert (
    len(
        candidate_activities
    )
    >
    0
)


# ---------------------------------------------------------
# ID
# ---------------------------------------------------------

assert candidate_activities[
    "activity_id"
].is_unique


# ---------------------------------------------------------
# 外部キー
# ---------------------------------------------------------

assert candidate_activities[
    "candidate_id"
].isin(
    candidates[
        "candidate_id"
    ]
).all()


# ---------------------------------------------------------
# activity_type
# ---------------------------------------------------------

assert candidate_activities[
    "activity_type"
].isin(
    [
        "initial_contact",
        "initial_interview",
        "follow_up",
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


# 登録日前の活動なし
assert (
    activity_check[
        "activity_date"
    ]
    >=
    activity_check[
        "registration_date"
    ]
).all()


# 求職終了後の活動なし
ended_check = (
    activity_check[
        activity_check[
            "search_end_date"
        ].notna()
    ]
)


assert (
    ended_check[
        "activity_date"
    ]
    <=
    ended_check[
        "search_end_date"
    ]
).all()


# DATA_END_DATEを超えない
assert (
    candidate_activities[
        "activity_date"
    ]
    <=
    DATA_END_DATE
).all()


# =========================================================
# CA在籍期間との整合性
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


# CAのみ
assert (
    activity_ca_check[
        "role_type"
    ]
    ==
    "CA"
).all()


# 着任日以降
assert (
    activity_ca_check[
        "activity_date"
    ]
    >=
    activity_ca_check[
        "join_date"
    ]
).all()


# 離任済みの場合は離任日以前
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


# 各候補者の最初の活動はinitial_contact
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
    ==
    "initial_contact"
).all()


# =========================================================
# activity_typeごとの重複品質チェック
# =========================================================

# initial_contactは候補者ごとに最大1件
initial_contact_counts = (
    candidate_activities[
        candidate_activities[
            "activity_type"
        ]
        ==
        "initial_contact"
    ]
    .groupby(
        "candidate_id"
    )
    .size()
)


assert (
    initial_contact_counts
    <=
    1
).all()


# initial_interviewも候補者ごとに最大1件
initial_interview_counts = (
    candidate_activities[
        candidate_activities[
            "activity_type"
        ]
        ==
        "initial_interview"
    ]
    .groupby(
        "candidate_id"
    )
    .size()
)


assert (
    initial_interview_counts
    <=
    1
).all()


# =========================================================
# 分析確認用：対応リードタイム
# =========================================================

initial_contacts = (
    candidate_activities[
        candidate_activities[
            "activity_type"
        ]
        ==
        "initial_contact"
    ]
    [
        [
            "candidate_id",
            "activity_date",
        ]
    ]
    .rename(
        columns={
            "activity_date":
                "initial_contact_date",
        }
    )
)


initial_interviews = (
    candidate_activities[
        candidate_activities[
            "activity_type"
        ]
        ==
        "initial_interview"
    ]
    [
        [
            "candidate_id",
            "activity_date",
        ]
    ]
    .rename(
        columns={
            "activity_date":
                "initial_interview_date",
        }
    )
)


activity_lead_time_check = (
    candidates[
        [
            "candidate_id",
            "registration_date",
        ]
    ]
    .merge(
        initial_contacts,
        on="candidate_id",
        how="left",
    )
    .merge(
        initial_interviews,
        on="candidate_id",
        how="left",
    )
)


activity_lead_time_check[
    "registration_year"
] = (
    activity_lead_time_check[
        "registration_date"
    ].dt.year
)


activity_lead_time_check[
    "registration_to_contact_days"
] = (
    activity_lead_time_check[
        "initial_contact_date"
    ]
    -
    activity_lead_time_check[
        "registration_date"
    ]
).dt.days


activity_lead_time_check[
    "contact_to_interview_days"
] = (
    activity_lead_time_check[
        "initial_interview_date"
    ]
    -
    activity_lead_time_check[
        "initial_contact_date"
    ]
).dt.days


# =========================================================
# CSV出力
# =========================================================
#
# 【変更前】
#
# candidate_activities_test.csv
#
#
# 【修正仕様】
#
# candidate_activities.csv
# =========================================================

candidate_activities.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig",
)


# =========================================================
# 内容確認
# =========================================================
#
# 【変更前】
#
# 全activityをprintしていた。
#
#
# 【問題点】
#
# 分析用データでは数千行になるため、
# 全件表示は確認しづらい。
#
#
# 【修正仕様】
#
# 件数・分布・年次集計・サンプルを表示する。
# =========================================================

print(
    "分析用候補者対応履歴データを生成しました。"
)

print()

print(
    f"活動件数: "
    f"{len(candidate_activities):,}"
)


print()
print(
    "【対応種別別件数】"
)

print(
    candidate_activities[
        "activity_type"
    ].value_counts()
)


# =========================================================
# CA負荷確認
# =========================================================

print()
print(
    "【月別CA負荷】"
)

print(
    monthly_ca_workload[
        [
            "month",
            "active_candidate_count",
            "active_ca_count",
            "active_candidates_per_ca",
            "workload_ratio",
        ]
    ].to_string(
        index=False
    )
)


print()
print(
    "【2025年4～12月の基準CA負荷】"
)

print(
    f"{BASELINE_CA_LOAD:.2f}"
)


# =========================================================
# 年次リードタイム
# =========================================================

print()
print(
    "【登録年別：登録→初回連絡日数】"
)

print(
    activity_lead_time_check
    .groupby(
        "registration_year"
    )[
        "registration_to_contact_days"
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
    "【登録年別：初回連絡→初回面談日数】"
)

print(
    activity_lead_time_check
    .groupby(
        "registration_year"
    )[
        "contact_to_interview_days"
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
# CA担当者別活動件数
# =========================================================

print()
print(
    "【CA担当者別活動件数】"
)

print(
    candidate_activities[
        "ca_id"
    ]
    .value_counts()
    .sort_index()
)


# =========================================================
# 候補者ごとの活動件数
# =========================================================

activities_per_candidate = (
    candidate_activities
    .groupby(
        "candidate_id"
    )
    .size()
)


print()
print(
    "【活動が発生した候補者数】"
)

print(
    activities_per_candidate
    .index
    .nunique()
)


print()
print(
    "【活動件数 / 候補者】"
)

print(
    activities_per_candidate
    .describe()
)


# =========================================================
# サンプル表示
# =========================================================

print()
print(
    "【candidate_activitiesサンプル：先頭20件】"
)

print(
    candidate_activities
    .sort_values(
        [
            "activity_date",
            "candidate_id",
        ]
    )
    .head(
        20
    )
)