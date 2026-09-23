from pathlib import Path

import numpy as np
import pandas as pd


# =========================================================
# 基本設定
# =========================================================

OUTPUT_DIR = Path("data/raw")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 分析用データの正式ファイル名
OUTPUT_FILE = OUTPUT_DIR / "candidate_preferences.csv"

# このスクリプト専用の乱数シード
#
# 分析結果を見てseedを変更しないよう固定する。
SEED = 43
rng = np.random.default_rng(SEED)

DATA_END_DATE = pd.Timestamp("2026-09-30")


# =========================================================
# 元データ読み込み
# =========================================================
#
# 【変更前】
#
# candidates_test.csv
# candidate_experiences_test.csv
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
# candidate_experiences.csv
#
# を入力とする。
# =========================================================

candidates = pd.read_csv(
    OUTPUT_DIR / "candidates.csv",
    parse_dates=[
        "registration_date",
        "search_end_date",
    ],
)

candidate_experiences = pd.read_csv(
    OUTPUT_DIR / "candidate_experiences.csv",
    parse_dates=[
        "start_date",
        "end_date",
    ],
)

locations = pd.read_csv(
    OUTPUT_DIR / "locations.csv"
)

occupations = pd.read_csv(
    OUTPUT_DIR / "occupations.csv"
)


# =========================================================
# 入力データの基本確認
# =========================================================

assert len(candidates) > 0

assert candidates[
    "candidate_id"
].is_unique

assert candidate_experiences[
    "candidate_id"
].isin(
    candidates["candidate_id"]
).all()

assert locations[
    "location_id"
].is_unique

assert occupations[
    "occupation_id"
].is_unique


# =========================================================
# 職種ごとの希望時給の基準値
# =========================================================
#
# 希望時給は、
#
# 職種基準
# + スキル水準
# + 個人差
# + 市場時点による補正
#
# から生成する。
#
# H2では2026年に候補者希望時給の上昇が
# 求人提示時給の上昇より大きくなる構造を作る。
# =========================================================

base_hourly_wage = {
    "OCC001": 1600,  # 一般事務
    "OCC002": 1500,  # データ入力
    "OCC003": 1700,  # コールセンター
    "OCC004": 2200,  # 医薬翻訳
    "OCC005": 2100,  # 品質管理（QC）
    "OCC006": 2300,  # DM
    "OCC007": 2200,  # CRC
    "OCC008": 3000,  # CRA
    "OCC009": 3200,  # 統計解析
    "OCC010": 2800,  # 薬事
}


# =========================================================
# 希望勤務地の出現確率
# =========================================================

location_ids = [
    "LOC001",  # 東京
    "LOC002",  # 神奈川
    "LOC003",  # 埼玉
    "LOC004",  # 千葉
    "LOC005",  # 群馬
    "LOC006",  # 大阪
    "LOC007",  # 愛知
    "LOC008",  # 福岡
]

location_probabilities = [
    0.40,
    0.15,
    0.10,
    0.10,
    0.05,
    0.10,
    0.05,
    0.05,
]


assert np.isclose(
    sum(location_probabilities),
    1.0,
)


assert set(
    location_ids
).issubset(
    set(locations["location_id"])
)


# =========================================================
# 希望勤務形態の生成確率
# =========================================================
#
# 【変更前】
#
# onsite 50%
# hybrid 35%
# remote 15%
#
#
# 【問題点】
#
# 特に問題は確認されていない。
#
#
# 【修正仕様】
#
# この分布を分析用データでも維持する。
#
# H6「リモート可否」は支持されなかった仮説として
# 分析する予定であるため、
#
# ・登録年
# ・スキル
# ・給与
# ・placement結果
#
# などによって勤務形態希望の確率を変えない。
#
# つまりwork_style自体に結果を直接作り込まない。
# =========================================================

work_styles = [
    "onsite",
    "hybrid",
    "remote",
]

work_style_probabilities = [
    0.50,
    0.35,
    0.15,
]


# =========================================================
# 職種グループ辞書
# =========================================================

occupation_group_map = dict(
    zip(
        occupations["occupation_id"],
        occupations["occupation_group"],
    )
)

occupation_ids = list(
    base_hourly_wage.keys()
)


assert all(
    occupation_id
    in occupation_group_map
    for occupation_id
    in occupation_ids
)


# =========================================================
# キャリアチェンジ先職種を選択する関数
# =========================================================
#
# 【変更前】
#
# ・80%は直近経験職種
# ・20%はキャリアチェンジ
# ・キャリアチェンジの70%は同一group
#
#
# 【問題点】
#
# 小規模EDAでは大きな不整合は確認されなかった。
#
#
# 【修正仕様】
#
# 基本ロジックを維持する。
#
# 求人側へ希望職種を意図的に合わせず、
# 同職種経験あり・なしの両方が自然に発生する状態を残す。
# =========================================================

def select_career_change_occupation(
    current_occupation_id,
):

    current_group = (
        occupation_group_map[
            current_occupation_id
        ]
    )

    # -----------------------------------------------------
    # 70%は同一職種グループ内での転換
    # -----------------------------------------------------

    if rng.random() < 0.70:

        same_group_candidates = [
            occupation_id
            for occupation_id
            in occupation_ids
            if (
                occupation_group_map[
                    occupation_id
                ]
                == current_group
                and
                occupation_id
                != current_occupation_id
            )
        ]

        if len(
            same_group_candidates
        ) > 0:

            return rng.choice(
                same_group_candidates
            )

    # -----------------------------------------------------
    # 別グループを含むキャリアチェンジ
    # -----------------------------------------------------

    other_occupations = [
        occupation_id
        for occupation_id
        in occupation_ids
        if (
            occupation_id
            != current_occupation_id
        )
    ]

    return rng.choice(
        other_occupations
    )


# =========================================================
# 希望時給を生成する関数
# =========================================================
#
# 【変更前】
#
# 希望時給の計算をforループ内へ直接記述していた。
#
#
# 【問題点】
#
# 分析用データでは、
#
# ・初回希望条件
# ・更新後希望条件
#
# の双方で時給ロジックを利用するため、
# 処理を関数化した方が定義が明確になる。
#
#
# 【修正仕様】
#
# 指定した職種・スキル・基準日時点の希望時給を生成する。
#
# 2026年時点では市場上昇として約8%を加える。
# =========================================================

def generate_desired_hourly_wage(
    occupation_id,
    skill_level,
    reference_date,
):

    desired_hourly_wage = (
        base_hourly_wage[
            occupation_id
        ]
    )

    # スキルによる調整
    desired_hourly_wage += (
        skill_level - 3
    ) * 150

    # 個人差
    desired_hourly_wage += rng.normal(
        loc=0,
        scale=100,
    )

    # -----------------------------------------------------
    # H2：2026年の希望時給水準
    # -----------------------------------------------------
    #
    # 2026年時点では約8%上昇。
    #
    # 求人提示時給側では後続のgenerate_jobs.pyで
    # 約3%程度の上昇とする予定。
    #
    # この差によって給与不足率が
    # 結果として拡大しやすくなる。
    # -----------------------------------------------------

    if reference_date.year >= 2026:

        desired_hourly_wage *= 1.08

    # 50円単位
    desired_hourly_wage = int(
        round(
            desired_hourly_wage
            / 50
        )
        * 50
    )

    # 極端に低い希望時給を防ぐ
    desired_hourly_wage = max(
        desired_hourly_wage,
        1200,
    )

    return desired_hourly_wage


# =========================================================
# 希望条件データ生成
# =========================================================

preference_data = []

preference_counter = 1


for _, candidate in candidates.iterrows():

    candidate_id = candidate[
        "candidate_id"
    ]

    registration_date = candidate[
        "registration_date"
    ]


    # -----------------------------------------------------
    # 求職可能期間
    # -----------------------------------------------------

    if pd.notna(
        candidate["search_end_date"]
    ):

        search_limit_date = min(
            candidate["search_end_date"],
            DATA_END_DATE,
        )

    else:

        search_limit_date = (
            DATA_END_DATE
        )


    # =====================================================
    # この候補者の職歴
    # =====================================================

    candidate_exp = candidate_experiences[
        candidate_experiences[
            "candidate_id"
        ]
        == candidate_id
    ].copy()


    candidate_exp = (
        candidate_exp.sort_values(
            "end_date",
            ascending=False,
        )
    )


    # generate_candidate_experiences.pyで
    # 全候補者に最低1件を保証しているため、
    # ここでは異常として扱う。
    assert len(candidate_exp) > 0


    # =====================================================
    # 希望職種
    # =====================================================

    latest_occupation_id = (
        candidate_exp.iloc[0][
            "occupation_id"
        ]
    )


    # 80%は直近経験職種を希望
    if rng.random() < 0.80:

        preferred_occupation_id = (
            latest_occupation_id
        )

    # 20%はキャリアチェンジ
    else:

        preferred_occupation_id = (
            select_career_change_occupation(
                latest_occupation_id
            )
        )


    # =====================================================
    # 希望職種に対する候補者スキル
    # =====================================================

    matching_experience = candidate_exp[
        candidate_exp[
            "occupation_id"
        ]
        == preferred_occupation_id
    ]


    if len(
        matching_experience
    ) > 0:

        candidate_skill_level = int(
            matching_experience[
                "skill_level"
            ].max()
        )

    else:

        # 未経験職種を希望した場合は、
        # 便宜上1～2程度の初級水準とする。
        #
        # ただしapplication分析では、
        # 同職種経験がないこと自体を
        # same_occupation_experience_flagで区別する。
        candidate_skill_level = int(
            rng.choice(
                [
                    1,
                    2,
                ],
                p=[
                    0.70,
                    0.30,
                ],
            )
        )


    # =====================================================
    # 初回希望時給
    # =====================================================
    #
    # 【変更前】
    #
    # registration_date.year >= 2026
    # の場合のみ1.08倍としていた。
    #
    #
    # 【問題点】
    #
    # 初回希望については問題ないが、
    # 2025年登録者が2026年に希望条件を更新した場合でも、
    # 更新時点の市場上昇が反映されなかった。
    #
    #
    # 【修正仕様】
    #
    # 初回希望はregistration_dateを基準日として計算する。
    #
    # 後続の更新が2026年に発生した場合は、
    # update_dateを基準として更新時点の市場水準を反映する。
    # =====================================================

    desired_hourly_wage = (
        generate_desired_hourly_wage(
            occupation_id=(
                preferred_occupation_id
            ),
            skill_level=(
                candidate_skill_level
            ),
            reference_date=(
                registration_date
            ),
        )
    )


    # =====================================================
    # 希望勤務地
    # =====================================================

    preferred_location_id = rng.choice(
        location_ids,
        p=location_probabilities,
    )


    # =====================================================
    # 希望勤務形態
    # =====================================================

    preferred_work_style = rng.choice(
        work_styles,
        p=work_style_probabilities,
    )


    # =====================================================
    # 希望条件を更新するか
    # =====================================================

    search_period_days = (
        search_limit_date
        - registration_date
    ).days


    has_update = (
        search_period_days >= 90
        and
        rng.random() < 0.30
    )


    if has_update:

        # -------------------------------------------------
        # 更新日
        # -------------------------------------------------

        update_days = int(
            rng.integers(
                60,
                min(
                    181,
                    search_period_days + 1,
                ),
            )
        )


        update_date = (
            registration_date
            + pd.Timedelta(
                days=update_days
            )
        )


        # -------------------------------------------------
        # 1件目の希望条件
        # -------------------------------------------------

        first_preference_id = (
            f"PRE{preference_counter:06d}"
        )


        preference_data.append(
            [
                first_preference_id,
                candidate_id,
                registration_date,
                update_date
                - pd.Timedelta(
                    days=1
                ),
                preferred_occupation_id,
                preferred_location_id,
                desired_hourly_wage,
                preferred_work_style,
            ]
        )


        preference_counter += 1


        # =================================================
        # 修正② 更新後希望時給
        # =================================================
        #
        # 【変更前】
        #
        # desired_hourly_wage
        # × 1.03～1.07
        #
        #
        # 【問題点】
        #
        # 2025年登録者が2026年に更新しても、
        # 2026年の市場時給上昇8%が反映されない。
        #
        #
        # 【修正仕様】
        #
        # 更新日時点の市場水準を再計算したうえで、
        # 求職活動中の条件見直しとして
        # 0～5%程度の追加調整を行う。
        #
        # これにより更新者全員が必ず大幅値上げする
        # 決定論的な処理は避ける。
        # =================================================

        updated_market_wage = (
            generate_desired_hourly_wage(
                occupation_id=(
                    preferred_occupation_id
                ),
                skill_level=(
                    candidate_skill_level
                ),
                reference_date=(
                    update_date
                ),
            )
        )


        updated_hourly_wage = (
            updated_market_wage
            * rng.uniform(
                1.00,
                1.05,
            )
        )


        updated_hourly_wage = int(
            round(
                updated_hourly_wage
                / 50
            )
            * 50
        )


        updated_hourly_wage = max(
            updated_hourly_wage,
            1200,
        )


        second_preference_id = (
            f"PRE{preference_counter:06d}"
        )


        # 求職中の場合は現在有効なのでNULL
        if pd.isna(
            candidate["search_end_date"]
        ):

            second_effective_to = pd.NaT

        else:

            second_effective_to = (
                search_limit_date
            )


        preference_data.append(
            [
                second_preference_id,
                candidate_id,
                update_date,
                second_effective_to,
                preferred_occupation_id,
                preferred_location_id,
                updated_hourly_wage,
                preferred_work_style,
            ]
        )


        preference_counter += 1


    else:

        # =================================================
        # 希望条件を更新しない場合
        # =================================================

        preference_id = (
            f"PRE{preference_counter:06d}"
        )


        if pd.isna(
            candidate["search_end_date"]
        ):

            effective_to = pd.NaT

        else:

            effective_to = (
                search_limit_date
            )


        preference_data.append(
            [
                preference_id,
                candidate_id,
                registration_date,
                effective_to,
                preferred_occupation_id,
                preferred_location_id,
                desired_hourly_wage,
                preferred_work_style,
            ]
        )


        preference_counter += 1


# =========================================================
# DataFrame化
# =========================================================

candidate_preferences = pd.DataFrame(
    preference_data,
    columns=[
        "candidate_preference_id",
        "candidate_id",
        "effective_from",
        "effective_to",
        "preferred_occupation_id",
        "preferred_location_id",
        "desired_hourly_wage",
        "preferred_work_style",
    ],
)


# =========================================================
# データ品質チェック
# =========================================================

assert candidate_preferences[
    "candidate_preference_id"
].is_unique


assert candidate_preferences[
    "candidate_id"
].isin(
    candidates[
        "candidate_id"
    ]
).all()


assert candidate_preferences[
    "preferred_location_id"
].isin(
    locations[
        "location_id"
    ]
).all()


assert candidate_preferences[
    "preferred_occupation_id"
].isin(
    occupation_ids
).all()


assert candidate_preferences[
    "desired_hourly_wage"
].gt(0).all()


assert candidate_preferences[
    "preferred_work_style"
].isin(
    work_styles
).all()


# =========================================================
# 有効期間の品質チェック
# =========================================================

valid_periods = (
    candidate_preferences[
        candidate_preferences[
            "effective_to"
        ].notna()
    ]
)


assert (
    valid_periods[
        "effective_to"
    ]
    >=
    valid_periods[
        "effective_from"
    ]
).all()


# =========================================================
# 候補者登録日との整合性
# =========================================================

preference_check = (
    candidate_preferences.merge(
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


# 希望条件開始日は登録日以降
assert (
    preference_check[
        "effective_from"
    ]
    >=
    preference_check[
        "registration_date"
    ]
).all()


# 全希望条件開始日はデータ期間内
assert (
    preference_check[
        "effective_from"
    ]
    <=
    DATA_END_DATE
).all()


# 求職終了済み候補者では、
# 希望条件終了日がsearch_end_dateを超えない
ended_preference_check = (
    preference_check[
        preference_check[
            "search_end_date"
        ].notna()
        &
        preference_check[
            "effective_to"
        ].notna()
    ]
)


assert (
    ended_preference_check[
        "effective_to"
    ]
    <=
    ended_preference_check[
        "search_end_date"
    ]
).all()


# =========================================================
# 希望条件期間の重複チェック
# =========================================================

preference_order_check = (
    candidate_preferences
    .sort_values(
        [
            "candidate_id",
            "effective_from",
        ]
    )
    .copy()
)


preference_order_check[
    "previous_effective_to"
] = (
    preference_order_check
    .groupby(
        "candidate_id"
    )[
        "effective_to"
    ]
    .shift(1)
)


subsequent_preferences = (
    preference_order_check[
        preference_order_check[
            "previous_effective_to"
        ].notna()
    ]
)


assert (
    subsequent_preferences[
        "effective_from"
    ]
    >
    subsequent_preferences[
        "previous_effective_to"
    ]
).all()


# =========================================================
# 候補者ごとに現在有効な希望条件は最大1件
# =========================================================

current_counts = (
    candidate_preferences[
        candidate_preferences[
            "effective_to"
        ].isna()
    ]
    .groupby(
        "candidate_id"
    )
    .size()
)


assert (
    current_counts <= 1
).all()


# =========================================================
# 全候補者に最低1件の希望条件
# =========================================================

candidates_with_preferences = set(
    candidate_preferences[
        "candidate_id"
    ]
)


assert set(
    candidates[
        "candidate_id"
    ]
).issubset(
    candidates_with_preferences
)


# =========================================================
# 1人あたり希望条件件数
# =========================================================

preference_count_per_candidate = (
    candidate_preferences
    .groupby(
        "candidate_id"
    )
    .size()
)


assert (
    preference_count_per_candidate
    .between(
        1,
        2,
    )
    .all()
)


# =========================================================
# CSV出力
# =========================================================
#
# 【変更前】
#
# candidate_preferences_test.csv
#
#
# 【修正仕様】
#
# candidate_preferences.csv
# =========================================================

candidate_preferences.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig",
)


# =========================================================
# 分析確認用データ
# =========================================================

# ---------------------------------------------------------
# 最新職歴
# ---------------------------------------------------------

latest_experience = (
    candidate_experiences
    .sort_values(
        [
            "candidate_id",
            "end_date",
        ],
        ascending=[
            True,
            False,
        ],
    )
    .drop_duplicates(
        subset=[
            "candidate_id"
        ],
        keep="first",
    )
    [
        [
            "candidate_id",
            "occupation_id",
        ]
    ]
    .rename(
        columns={
            "occupation_id":
                "latest_experience_occupation_id",
        }
    )
)


# ---------------------------------------------------------
# 初回希望条件
# ---------------------------------------------------------

preference_review = (
    candidate_preferences
    .sort_values(
        [
            "candidate_id",
            "effective_from",
        ]
    )
    .drop_duplicates(
        subset=[
            "candidate_id"
        ],
        keep="first",
    )
    .merge(
        latest_experience,
        on="candidate_id",
        how="left",
    )
    .merge(
        candidates[
            [
                "candidate_id",
                "registration_date",
            ]
        ],
        on="candidate_id",
        how="left",
    )
)


preference_review[
    "registration_year"
] = (
    preference_review[
        "registration_date"
    ].dt.year
)


preference_review[
    "same_as_latest_experience"
] = (
    preference_review[
        "preferred_occupation_id"
    ]
    ==
    preference_review[
        "latest_experience_occupation_id"
    ]
)


preference_review[
    "latest_experience_group"
] = (
    preference_review[
        "latest_experience_occupation_id"
    ].map(
        occupation_group_map
    )
)


preference_review[
    "preferred_occupation_group"
] = (
    preference_review[
        "preferred_occupation_id"
    ].map(
        occupation_group_map
    )
)


preference_review[
    "same_occupation_group"
] = (
    preference_review[
        "latest_experience_group"
    ]
    ==
    preference_review[
        "preferred_occupation_group"
    ]
)


# =========================================================
# 内容確認
# =========================================================
#
# 【変更前】
#
# candidate_preferences全件や、
# candidate_idごとの全件をprintしていた。
#
#
# 【問題点】
#
# 約1,950人では出力量が大きく、
# 品質確認として読みづらい。
#
#
# 【修正仕様】
#
# 集計値と先頭サンプルのみ表示する。
# =========================================================

print(
    "分析用希望条件データを生成しました。"
)

print()

print(
    f"候補者数: "
    f"{candidates['candidate_id'].nunique():,}"
)

print(
    f"希望条件件数: "
    f"{len(candidate_preferences):,}"
)


print()
print(
    "【候補者ごとの希望条件件数分布】"
)

print(
    preference_count_per_candidate
    .value_counts()
    .sort_index()
)


print()
print(
    "【希望勤務形態】"
)

print(
    candidate_preferences[
        "preferred_work_style"
    ]
    .value_counts()
)


print()
print(
    "【希望時給の基本統計量】"
)

print(
    candidate_preferences[
        "desired_hourly_wage"
    ]
    .describe()
)


print()
print(
    "【登録年別の初回希望時給】"
)

print(
    preference_review
    .groupby(
        "registration_year"
    )[
        "desired_hourly_wage"
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
    "【直近経験職種と希望職種が一致する割合】"
)

print(
    preference_review[
        "same_as_latest_experience"
    ].mean()
)


print()
print(
    "【直近経験職種と希望職種が"
    "同一職種グループの割合】"
)

print(
    preference_review[
        "same_occupation_group"
    ].mean()
)


print()
print(
    "【希望職種別件数】"
)

print(
    candidate_preferences[
        "preferred_occupation_id"
    ]
    .value_counts()
    .sort_index()
)


print()
print(
    "【希望条件サンプル：先頭20件】"
)

print(
    candidate_preferences
    .sort_values(
        [
            "candidate_id",
            "effective_from",
        ]
    )
    .head(20)
)