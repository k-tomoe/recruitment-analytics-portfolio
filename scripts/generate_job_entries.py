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


# このスクリプト専用の乱数シード
#
# 分析結果を確認した後で、
# 都合のよいseedへ変更しない。
SEED = 45
rng = np.random.default_rng(
    SEED
)


DATA_END_DATE = pd.Timestamp(
    "2026-09-30"
)


# 分析用正式ファイル
OUTPUT_FILE = (
    OUTPUT_DIR
    / "job_entries.csv"
)

REVIEW_FILE = (
    REVIEW_DIR
    / "job_entries_review.csv"
)


# =========================================================
# 元データ読み込み
# =========================================================
#
# 【変更前】
#
# candidates_test.csv
# candidate_preferences_test.csv
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
# 分析用データ生成では、
#
# candidates.csv
# candidate_preferences.csv
# jobs.csv
#
# を利用する。
# =========================================================

candidates = pd.read_csv(
    OUTPUT_DIR / "candidates.csv",
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

jobs = pd.read_csv(
    OUTPUT_DIR / "jobs.csv",
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
# 入力データ品質確認
# =========================================================

assert candidates[
    "candidate_id"
].is_unique

assert jobs[
    "job_id"
].is_unique

assert candidate_preferences[
    "candidate_id"
].isin(
    candidates[
        "candidate_id"
    ]
).all()


# =========================================================
# 職種・勤務地の補助辞書
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
# 候補者ごとの希望条件を事前にまとめる
# =========================================================
#
# 【変更前】
#
# get_active_preference()のたびに、
# candidate_preferences全体をfilterしていた。
#
#
# 【問題点】
#
# 小規模データでは問題ないが、
# 1,950候補者 × 多数求人になると
# 同じDataFrame検索を何度も行うことになる。
#
#
# 【修正仕様】
#
# candidate_idごとに希望条件を事前に分割し、
# 必要な候補者だけ検索する。
#
# これにより処理量を抑える。
# =========================================================

preferences_by_candidate = {
    candidate_id: group.sort_values(
        "effective_from"
    ).copy()
    for candidate_id, group
    in candidate_preferences.groupby(
        "candidate_id"
    )
}


# =========================================================
# 指定日に有効な希望条件を取得する関数
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


    preference_rows = candidate_pref[
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


    if len(
        preference_rows
    ) == 0:

        return None


    return preference_rows.iloc[0]


# =========================================================
# 修正① 検討求人件数
# =========================================================
#
# 【変更前】
#
# 候補者 × 全求人
#
# のすべての組み合わせについて、
# エントリー確率を計算していた。
#
#
# 【問題点】
#
# 分析用データでは、
#
# 候補者：約1,950人
# 求人：約800件
#
# となるため、
#
# 1,950 × 800
# = 約156万組
#
# が対象となる。
#
# すべての求人に対して候補者が
# エントリー判断をするのは業務的にも不自然であり、
# job_entriesが過剰に増える原因となる。
#
#
# 【修正仕様】
#
# まず候補者の求職期間と
# 求人のエントリー可能期間が重なる求人を抽出する。
#
# その中から候補者ごとに、
# おおむね4～16求人程度を
# 「実際に検討した求人」としてサンプリングする。
#
# 検討求人件数はPoisson分布を利用し、
# 平均9件程度とする。
#
# その後、職種・勤務地・給与条件によって
# 実際にself entryするかを確率的に決定する。
#
# job_entriesは「閲覧」ではなく
# 実際の求人エントリーなので、
# 検討しただけの求人はCSVへ保存しない。
# =========================================================

MIN_CONSIDERED_JOBS = 4
MAX_CONSIDERED_JOBS = 16
MEAN_CONSIDERED_JOBS = 9


# =========================================================
# エントリー確率を計算する関数
# =========================================================
#
# 【変更前】
#
# 基礎確率 = 0.03
#
# exact occupation +0.35
# same group      +0.08
#
# exact location  +0.15
# same area       +0.06
#
# 給与条件         +0.15等
#
# work style一致  +0.04
#
#
# 【問題点】
#
# 分析用規模では、
# 全求人を対象とするとエントリー件数が
# 過剰になりやすい。
#
# またH6では勤務形態による明確な差を
# 生成段階から作り込みたくない。
#
#
# 【修正仕様】
#
# 検討求人を限定したうえで、
# エントリー確率を次の要素から計算する。
#
# ・職種適合
# ・勤務地適合
# ・給与条件
#
# work_styleは確認用には保持するが、
# entry_probabilityへ直接加点しない。
#
# H6は後のPython分析で探索する。
# =========================================================

def calculate_entry_probability(
    preference,
    job,
):

    # 基礎確率
    entry_probability = 0.06


    # -----------------------------------------------------
    # 1. 職種
    # -----------------------------------------------------

    preferred_occupation_id = (
        preference[
            "preferred_occupation_id"
        ]
    )

    job_occupation_id = (
        job[
            "occupation_id"
        ]
    )


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

        entry_probability += 0.28

    elif same_occupation_group:

        entry_probability += 0.08


    # -----------------------------------------------------
    # 2. 勤務地
    # -----------------------------------------------------

    preferred_location_id = (
        preference[
            "preferred_location_id"
        ]
    )

    job_location_id = (
        job[
            "location_id"
        ]
    )


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

        entry_probability += 0.10

    elif same_area_group:

        entry_probability += 0.04


    # -----------------------------------------------------
    # 3. 給与
    # -----------------------------------------------------

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


    if wage_gap_ratio >= 0:

        entry_probability += 0.12

    elif wage_gap_ratio >= -0.05:

        entry_probability += 0.08

    elif wage_gap_ratio >= -0.10:

        entry_probability += 0.03

    elif wage_gap_ratio < -0.20:

        entry_probability -= 0.03


    # -----------------------------------------------------
    # 4. 勤務形態
    # -----------------------------------------------------
    #
    # 【変更前】
    #
    # work_styleが一致すると+0.04
    #
    #
    # 【問題点】
    #
    # H6を支持されなかった仮説として探索するため、
    # 勤務形態そのものに明確な効果を
    # 生成段階から入れない方がよい。
    #
    #
    # 【修正仕様】
    #
    # work_style_matchは確認用に算出するが、
    # entry_probabilityには加えない。
    # -----------------------------------------------------

    preferred_work_style = (
        preference[
            "preferred_work_style"
        ]
    )

    job_work_style = (
        job[
            "work_style"
        ]
    )


    work_style_match = (
        preferred_work_style
        ==
        job_work_style
    )


    # -----------------------------------------------------
    # 5. 確率範囲
    # -----------------------------------------------------

    entry_probability = float(
        np.clip(
            entry_probability,
            0.01,
            0.65,
        )
    )


    return {
        "entry_probability":
            entry_probability,

        "preferred_occupation_id":
            preferred_occupation_id,

        "job_occupation_id":
            job_occupation_id,

        "exact_occupation_match":
            exact_occupation_match,

        "same_occupation_group":
            same_occupation_group,

        "preferred_location_id":
            preferred_location_id,

        "job_location_id":
            job_location_id,

        "exact_location_match":
            exact_location_match,

        "same_area_group":
            same_area_group,

        "desired_wage":
            desired_wage,

        "offered_wage":
            offered_wage,

        "wage_gap_ratio":
            wage_gap_ratio,

        "preferred_work_style":
            preferred_work_style,

        "job_work_style":
            job_work_style,

        "work_style_match":
            work_style_match,
    }


# =========================================================
# エントリーデータ生成
# =========================================================

entry_data = []

review_data = []

entry_counter = 1


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


    # -----------------------------------------------------
    # 求職可能期間終了
    # -----------------------------------------------------

    if pd.notna(
        candidate[
            "search_end_date"
        ]
    ):

        search_limit_date = min(
            candidate[
                "search_end_date"
            ],
            DATA_END_DATE,
        )

    else:

        search_limit_date = (
            DATA_END_DATE
        )


    # =====================================================
    # 修正① この候補者が検討可能な求人を抽出
    # =====================================================
    #
    # 求人のentry可能期間は、
    #
    # open_date
    # ～
    # open_date + 45日
    #
    # とする。
    #
    # close_dateが存在する場合は
    # close_dateまで。
    #
    # この期間と候補者求職期間が
    # 1日以上重なる求人だけを候補とする。
    # =====================================================

    possible_jobs = jobs[
        (
            jobs[
                "open_date"
            ]
            <=
            search_limit_date
        )
        &
        (
            (
                jobs[
                    "open_date"
                ]
                +
                pd.Timedelta(
                    days=45
                )
            )
            >=
            registration_date
        )
        &
        (
            jobs[
                "close_date"
            ].isna()
            |
            (
                jobs[
                    "close_date"
                ]
                >=
                registration_date
            )
        )
    ].copy()


    if len(
        possible_jobs
    ) == 0:

        continue


    # =====================================================
    # 検討求人件数
    # =====================================================

    n_considered_jobs = int(
        rng.poisson(
            MEAN_CONSIDERED_JOBS
        )
    )


    n_considered_jobs = int(
        np.clip(
            n_considered_jobs,
            MIN_CONSIDERED_JOBS,
            MAX_CONSIDERED_JOBS,
        )
    )


    n_considered_jobs = min(
        n_considered_jobs,
        len(
            possible_jobs
        ),
    )


    # 候補求人の中から、
    # 実際に検討する求人を重複なしで抽出
    considered_job_indices = (
        rng.choice(
            possible_jobs.index.to_numpy(),
            size=n_considered_jobs,
            replace=False,
        )
    )


    considered_jobs = (
        possible_jobs.loc[
            considered_job_indices
        ]
    )


    # =====================================================
    # 検討求人ごとにエントリー判定
    # =====================================================

    for _, job in considered_jobs.iterrows():

        job_id = (
            job[
                "job_id"
            ]
        )

        open_date = (
            job[
                "open_date"
            ]
        )

        close_date = (
            job[
                "close_date"
            ]
        )


        # -------------------------------------------------
        # エントリー可能開始日
        # -------------------------------------------------

        entry_window_start = max(
            registration_date,
            open_date,
        )


        # -------------------------------------------------
        # エントリー可能終了日
        # -------------------------------------------------

        entry_window_end = min(
            (
                open_date
                +
                pd.Timedelta(
                    days=45
                )
            ),
            search_limit_date,
            DATA_END_DATE,
        )


        if pd.notna(
            close_date
        ):

            entry_window_end = min(
                entry_window_end,
                close_date,
            )


        if (
            entry_window_start
            >
            entry_window_end
        ):

            continue


        # =================================================
        # エントリー候補日
        # =================================================

        available_days = (
            entry_window_end
            -
            entry_window_start
        ).days


        entry_offset = int(
            rng.integers(
                0,
                available_days + 1,
            )
        )


        entry_date = (
            entry_window_start
            +
            pd.Timedelta(
                days=entry_offset
            )
        )


        # =================================================
        # その時点で有効な希望条件
        # =================================================

        preference = (
            get_active_preference(
                candidate_id,
                entry_date,
            )
        )


        if preference is None:
            continue


        # =================================================
        # エントリー確率
        # =================================================

        match_result = (
            calculate_entry_probability(
                preference,
                job,
            )
        )


        entry_probability = (
            match_result[
                "entry_probability"
            ]
        )


        # =================================================
        # エントリー抽選
        # =================================================

        does_enter = (
            rng.random()
            <
            entry_probability
        )


        if not does_enter:
            continue


        # =================================================
        # job_entriesへ追加
        # =================================================

        entry_id = (
            f"ENT{entry_counter:06d}"
        )


        entry_data.append(
            [
                entry_id,
                candidate_id,
                job_id,
                entry_date,
                "job_site",
                "pending",
            ]
        )


        # =================================================
        # review用データ
        # =================================================

        review_data.append(
            [
                entry_id,
                candidate_id,
                job_id,
                entry_date,

                match_result[
                    "preferred_occupation_id"
                ],

                match_result[
                    "job_occupation_id"
                ],

                match_result[
                    "exact_occupation_match"
                ],

                match_result[
                    "same_occupation_group"
                ],

                match_result[
                    "preferred_location_id"
                ],

                match_result[
                    "job_location_id"
                ],

                match_result[
                    "exact_location_match"
                ],

                match_result[
                    "same_area_group"
                ],

                match_result[
                    "desired_wage"
                ],

                match_result[
                    "offered_wage"
                ],

                round(
                    match_result[
                        "wage_gap_ratio"
                    ],
                    3,
                ),

                match_result[
                    "preferred_work_style"
                ],

                match_result[
                    "job_work_style"
                ],

                match_result[
                    "work_style_match"
                ],

                round(
                    entry_probability,
                    3,
                ),
            ]
        )


        entry_counter += 1


# =========================================================
# DataFrame化
# =========================================================

job_entries = pd.DataFrame(
    entry_data,
    columns=[
        "entry_id",
        "candidate_id",
        "job_id",
        "entry_date",
        "entry_source",
        "status",
    ],
)


job_entries_review = pd.DataFrame(
    review_data,
    columns=[
        "entry_id",
        "candidate_id",
        "job_id",
        "entry_date",
        "preferred_occupation_id",
        "job_occupation_id",
        "occupation_exact_match",
        "same_occupation_group",
        "preferred_location_id",
        "job_location_id",
        "location_exact_match",
        "same_area_group",
        "desired_hourly_wage",
        "offered_hourly_wage",
        "wage_gap_ratio",
        "preferred_work_style",
        "job_work_style",
        "work_style_match",
        "entry_probability",
    ],
)


# =========================================================
# データ品質チェック
# =========================================================

# エントリーが1件以上生成されること
assert len(
    job_entries
) > 0


# ---------------------------------------------------------
# ID
# ---------------------------------------------------------

assert job_entries[
    "entry_id"
].is_unique


# ---------------------------------------------------------
# 外部キー
# ---------------------------------------------------------

assert job_entries[
    "candidate_id"
].isin(
    candidates[
        "candidate_id"
    ]
).all()


assert job_entries[
    "job_id"
].isin(
    jobs[
        "job_id"
    ]
).all()


# ---------------------------------------------------------
# 固定値
# ---------------------------------------------------------

assert job_entries[
    "entry_source"
].eq(
    "job_site"
).all()


assert job_entries[
    "status"
].eq(
    "pending"
).all()


# ---------------------------------------------------------
# candidate × job は1回だけ
# ---------------------------------------------------------

assert not job_entries.duplicated(
    subset=[
        "candidate_id",
        "job_id",
    ]
).any()


# =========================================================
# 求人公開期間との整合性
# =========================================================

entry_check = (
    job_entries.merge(
        jobs[
            [
                "job_id",
                "open_date",
                "close_date",
            ]
        ],
        on="job_id",
        how="left",
    )
)


# 求人公開日以降
assert (
    entry_check[
        "entry_date"
    ]
    >=
    entry_check[
        "open_date"
    ]
).all()


# 求人公開後45日以内
assert (
    entry_check[
        "entry_date"
    ]
    <=
    (
        entry_check[
            "open_date"
        ]
        +
        pd.Timedelta(
            days=45
        )
    )
).all()


# close_dateがある求人では
# close_date以前
closed_job_entries = (
    entry_check[
        entry_check[
            "close_date"
        ].notna()
    ]
)


assert (
    closed_job_entries[
        "entry_date"
    ]
    <=
    closed_job_entries[
        "close_date"
    ]
).all()


# =========================================================
# 候補者求職期間との整合性
# =========================================================

entry_check = (
    entry_check.merge(
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


# 登録日以降
assert (
    entry_check[
        "entry_date"
    ]
    >=
    entry_check[
        "registration_date"
    ]
).all()


# 求職終了日がある場合は
# 求職終了日以前
ended_candidate_entries = (
    entry_check[
        entry_check[
            "search_end_date"
        ].notna()
    ]
)


assert (
    ended_candidate_entries[
        "entry_date"
    ]
    <=
    ended_candidate_entries[
        "search_end_date"
    ]
).all()


# DATA_END_DATE以前
assert (
    job_entries[
        "entry_date"
    ]
    <=
    DATA_END_DATE
).all()


# =========================================================
# 希望条件有効期間との整合性
# =========================================================
#
# reviewデータがあるため、
# すべてのentryについて有効な希望条件が
# 取得できていたことを確認する。
# =========================================================

assert (
    len(
        job_entries
    )
    ==
    len(
        job_entries_review
    )
)


# =========================================================
# Raw CSV出力
# =========================================================
#
# 【変更前】
#
# job_entries_test.csv
#
#
# 【修正仕様】
#
# job_entries.csv
# =========================================================

job_entries.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig",
)


# =========================================================
# 確認用CSV出力
# =========================================================

job_entries_review.to_csv(
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
# job_entries全件、
# candidate別全件、
# job別全件をprintしていた。
#
#
# 【問題点】
#
# 分析用データでは数千行になる可能性があり、
# 全件表示は確認しづらい。
#
#
# 【修正仕様】
#
# 集計・分布・サンプルを中心に確認する。
# =========================================================

print(
    "分析用求人エントリーデータを生成しました。"
)

print()

print(
    f"エントリー件数: "
    f"{len(job_entries):,}"
)


# =========================================================
# 年別件数
# =========================================================

entry_summary = (
    job_entries.merge(
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


entry_summary[
    "job_open_year"
] = (
    entry_summary[
        "open_date"
    ].dt.year
)


entry_summary[
    "entry_year"
] = (
    entry_summary[
        "entry_date"
    ].dt.year
)


print()
print(
    "【求人公開年別エントリー件数】"
)

print(
    entry_summary[
        "job_open_year"
    ]
    .value_counts()
    .sort_index()
)


print()
print(
    "【エントリー年別件数】"
)

print(
    entry_summary[
        "entry_year"
    ]
    .value_counts()
    .sort_index()
)


# =========================================================
# 候補者別エントリー件数
# =========================================================

entries_per_candidate = (
    job_entries
    .groupby(
        "candidate_id"
    )
    .size()
)


print()
print(
    "【エントリーした候補者数】"
)

print(
    entries_per_candidate.index.nunique()
)


print()
print(
    "【エントリー件数 / 候補者】"
)

print(
    entries_per_candidate.describe()
)


# =========================================================
# 求人別エントリー件数
# =========================================================

entries_per_job = (
    job_entries
    .groupby(
        "job_id"
    )
    .size()
)


print()
print(
    "【エントリーが発生した求人数】"
)

print(
    entries_per_job.index.nunique()
)


print()
print(
    "【エントリー件数 / 求人】"
)

print(
    entries_per_job.describe()
)


# =========================================================
# マッチ条件
# =========================================================

print()
print(
    "【エントリー時のマッチ条件割合】"
)

print(
    job_entries_review[
        [
            "occupation_exact_match",
            "same_occupation_group",
            "location_exact_match",
            "same_area_group",
            "work_style_match",
        ]
    ].mean()
)


print()
print(
    "【平均エントリー確率】"
)

print(
    job_entries_review[
        "entry_probability"
    ].mean()
)


print()
print(
    "【給与差率の基本統計量】"
)

print(
    job_entries_review[
        "wage_gap_ratio"
    ].describe()
)


# =========================================================
# 求人終了後エントリー確認
# =========================================================

invalid_closed_entries = (
    closed_job_entries[
        closed_job_entries[
            "entry_date"
        ]
        >
        closed_job_entries[
            "close_date"
        ]
    ]
)


print()
print(
    "【求人終了後エントリー件数】"
)

print(
    len(
        invalid_closed_entries
    )
)


# =========================================================
# サンプル表示
# =========================================================

print()
print(
    "【job_entriesサンプル：先頭20件】"
)

print(
    job_entries
    .sort_values(
        "entry_date"
    )
    .head(
        20
    )
)


print()
print(
    "【reviewサンプル：先頭20件】"
)

print(
    job_entries_review
    .sort_values(
        "entry_date"
    )
    .head(
        20
    )
)