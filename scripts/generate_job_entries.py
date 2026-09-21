from pathlib import Path

import numpy as np
import pandas as pd


# =========================================================
# 基本設定
# =========================================================

OUTPUT_DIR = Path("data/raw")
REVIEW_DIR = Path("data/review")

REVIEW_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

rng = np.random.default_rng(45)

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

candidate_preferences = pd.read_csv(
    OUTPUT_DIR / "candidate_preferences_test.csv",
    parse_dates=[
        "effective_from",
        "effective_to",
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
# 職種・勤務地の補助辞書
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
# 指定日に有効な希望条件を取得する関数
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
# エントリーデータ生成
# =========================================================

entry_data = []

# 後で中身を確認するためのデータ
review_data = []

entry_counter = 1


for _, candidate in candidates.iterrows():

    candidate_id = candidate["candidate_id"]

    registration_date = candidate[
        "registration_date"
    ]


    # -----------------------------------------------------
    # 求職可能期間の終了日
    # -----------------------------------------------------

    if pd.notna(
        candidate["search_end_date"]
    ):

        search_limit_date = candidate[
            "search_end_date"
        ]

    else:

        search_limit_date = DATA_END_DATE


    for _, job in jobs.iterrows():

        job_id = job["job_id"]

        open_date = job[
            "open_date"
        ]

        close_date = job[
            "close_date"
        ]


        # =================================================
        # 修正① エントリー可能期間
        # =================================================
        #
        # 【変更前】
        # 求人公開後45日以内、
        # 求職期間内、
        # データ観察期間内であれば
        # エントリー可能としていた。
        #
        # 変更前コード：
        #
        # entry_window_start = max(
        #     registration_date,
        #     open_date,
        # )
        #
        # entry_window_end = min(
        #     open_date
        #     + pd.Timedelta(days=45),
        #     search_limit_date,
        #     DATA_END_DATE,
        # )
        #
        #
        # 【問題点】
        # generate_jobs.pyの修正により、
        # 多くの求人にclose_dateが設定されるようになった。
        #
        # しかしjob_entries側でclose_dateを考慮しないと、
        # すでに掲載終了している求人についても、
        # 求人公開後45日以内であれば
        # エントリーが生成される可能性がある。
        #
        #
        # 【修正仕様】
        # 求人サイトからのエントリーは、
        # 以下すべてを満たす期間内だけ生成する。
        #
        # ・候補者登録日以降
        # ・求人公開日以降
        # ・求人公開後45日以内
        # ・候補者の求職終了日以前
        # ・DATA_END_DATE以前
        # ・close_dateが存在する場合はclose_date以前
        #
        # 長期OPEN求人などclose_dateがNULLの場合は、
        # close_dateによる制限は行わない。
        #
        # -------------------------------------------------
        # 変更後コード
        # -------------------------------------------------

        # エントリー開始日は、
        # 「候補者登録日」と「求人公開日」の遅い方
        entry_window_start = max(
            registration_date,
            open_date,
        )


        # まず、close_date以外の条件から
        # エントリー可能終了日を設定
        entry_window_end = min(
            open_date
            + pd.Timedelta(
                days=45
            ),
            search_limit_date,
            DATA_END_DATE,
        )


        # 求人が期間内にクローズしている場合は、
        # close_dateもエントリー可能期間の上限にする
        if pd.notna(
            close_date
        ):

            entry_window_end = min(
                entry_window_end,
                close_date,
            )


        # エントリー可能期間が存在しない場合
        if (
            entry_window_start
            > entry_window_end
        ):
            continue


        # =================================================
        # エントリー候補日を生成
        # =================================================

        available_days = (
            entry_window_end
            - entry_window_start
        ).days

        entry_offset = int(
            rng.integers(
                0,
                available_days + 1,
            )
        )

        entry_date = (
            entry_window_start
            + pd.Timedelta(
                days=entry_offset
            )
        )


        # =================================================
        # その時点の希望条件
        # =================================================

        preference = get_active_preference(
            candidate_id,
            entry_date,
        )

        if preference is None:
            continue


        # =================================================
        # マッチ度を計算
        # =================================================

        entry_probability = 0.03


        # -------------------------------------------------
        # 1. 職種
        # -------------------------------------------------

        preferred_occupation_id = (
            preference[
                "preferred_occupation_id"
            ]
        )

        job_occupation_id = (
            job["occupation_id"]
        )

        exact_occupation_match = (
            preferred_occupation_id
            == job_occupation_id
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

            entry_probability += 0.35

        elif same_occupation_group:

            entry_probability += 0.08


        # -------------------------------------------------
        # 2. 勤務地
        # -------------------------------------------------

        preferred_location_id = (
            preference[
                "preferred_location_id"
            ]
        )

        job_location_id = (
            job["location_id"]
        )

        exact_location_match = (
            preferred_location_id
            == job_location_id
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

            entry_probability += 0.15

        elif same_area_group:

            entry_probability += 0.06


        # -------------------------------------------------
        # 3. 時給
        # -------------------------------------------------

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
            - desired_wage
        ) / desired_wage


        if wage_gap_ratio >= 0:

            entry_probability += 0.15

        elif wage_gap_ratio >= -0.05:

            entry_probability += 0.10

        elif wage_gap_ratio >= -0.10:

            entry_probability += 0.04

        elif wage_gap_ratio < -0.20:

            entry_probability -= 0.03


        # -------------------------------------------------
        # 4. 勤務形態
        # -------------------------------------------------

        preferred_work_style = (
            preference[
                "preferred_work_style"
            ]
        )

        job_work_style = (
            job["work_style"]
        )

        work_style_match = (
            preferred_work_style
            == job_work_style
        )


        # 仮説6を強く効かせないため、
        # 勤務形態の効果は小さくする
        if work_style_match:

            entry_probability += 0.04


        # -------------------------------------------------
        # 確率を0～0.80に収める
        # -------------------------------------------------

        entry_probability = float(
            np.clip(
                entry_probability,
                0,
                0.80,
            )
        )


        # =================================================
        # 実際にエントリーするか抽選
        # =================================================

        does_enter = (
            rng.random()
            < entry_probability
        )


        if not does_enter:
            continue


        # =================================================
        # job_entriesへ追加
        # =================================================

        entry_id = (
            f"ENT{entry_counter:05d}"
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
        # 確認用データ
        # =================================================

        review_data.append(
            [
                entry_id,
                candidate_id,
                job_id,
                entry_date,
                preferred_occupation_id,
                job_occupation_id,
                exact_occupation_match,
                preferred_location_id,
                job_location_id,
                exact_location_match,
                desired_wage,
                offered_wage,
                round(
                    wage_gap_ratio,
                    3,
                ),
                preferred_work_style,
                job_work_style,
                work_style_match,
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


# =========================================================
# データ品質チェック
# =========================================================

assert job_entries[
    "entry_id"
].is_unique


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


# candidate × job は1回だけ
assert not job_entries.duplicated(
    subset=[
        "candidate_id",
        "job_id",
    ]
).any()


# =========================================================
# 求人公開期間との整合性
# =========================================================

entry_check = job_entries.merge(
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


# 求人公開日より前に
# エントリーしていないことを確認
assert (
    entry_check[
        "entry_date"
    ]
    >=
    entry_check[
        "open_date"
    ]
).all()


# =========================================================
# 修正①に対する追加品質チェック
# =========================================================
#
# close_dateが存在する求人では、
# 求人終了後にエントリーしていないことを確認する。

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


# 求人公開後45日を超えて
# エントリーしていないことを確認
assert (
    entry_check[
        "entry_date"
    ]
    <=
    (
        entry_check[
            "open_date"
        ]
        + pd.Timedelta(
            days=45
        )
    )
).all()


# =========================================================
# 求職者登録日との整合性
# =========================================================

entry_check = entry_check.merge(
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


# 求職者登録日より前に
# エントリーしていないことを確認
assert (
    entry_check[
        "entry_date"
    ]
    >=
    entry_check[
        "registration_date"
    ]
).all()


# 求職終了日が存在する場合、
# 求職終了後にエントリーしていないことを確認
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


# DATA_END_DATEを超えていないこと
assert (
    job_entries[
        "entry_date"
    ]
    <= DATA_END_DATE
).all()


# =========================================================
# Raw CSV出力
# =========================================================

job_entries.to_csv(
    OUTPUT_DIR
    / "job_entries_test.csv",
    index=False,
    encoding="utf-8-sig",
)


# =========================================================
# 確認用CSV
# =========================================================

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
        "preferred_location_id",
        "job_location_id",
        "location_exact_match",
        "desired_hourly_wage",
        "offered_hourly_wage",
        "wage_gap_ratio",
        "preferred_work_style",
        "job_work_style",
        "work_style_match",
        "entry_probability",
    ],
)


job_entries_review.to_csv(
    REVIEW_DIR
    / "job_entries_review.csv",
    index=False,
    encoding="utf-8-sig",
)


# =========================================================
# 内容確認
# =========================================================

print(job_entries)

print()
print(
    "求人エントリーテストデータを生成しました。"
)

print(
    f"件数: {len(job_entries)}"
)


print()
print("求職者ごとのエントリー件数")

print(
    job_entries[
        "candidate_id"
    ].value_counts().sort_index()
)


print()
print("求人ごとのエントリー件数")

print(
    job_entries[
        "job_id"
    ].value_counts().sort_index()
)


print()
print("マッチ条件の確認")

print(
    job_entries_review[
        [
            "occupation_exact_match",
            "location_exact_match",
            "work_style_match",
        ]
    ].mean()
)


print()
print("平均エントリー確率")

print(
    job_entries_review[
        "entry_probability"
    ].mean()
)


# =========================================================
# 修正①の内容確認
# =========================================================

print()
print(
    "終了済み求人へのエントリー件数"
)

print(
    len(
        closed_job_entries
    )
)


print()
print(
    "求人公開日・終了日・エントリー日の確認"
)

print(
    entry_check[
        [
            "entry_id",
            "candidate_id",
            "job_id",
            "registration_date",
            "open_date",
            "close_date",
            "entry_date",
            "search_end_date",
        ]
    ].sort_values(
        "entry_date"
    )
)