from pathlib import Path

import numpy as np
import pandas as pd


# =========================================================
# 基本設定
# =========================================================

OUTPUT_DIR = Path("data/raw")

# このスクリプト専用の乱数シード
rng = np.random.default_rng(43)

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

candidate_experiences = pd.read_csv(
    OUTPUT_DIR / "candidate_experiences_test.csv",
    parse_dates=[
        "start_date",
        "end_date",
    ],
)

locations = pd.read_csv(
    OUTPUT_DIR / "locations.csv"
)

# 修正①で職種グループを利用するため追加
occupations = pd.read_csv(
    OUTPUT_DIR / "occupations.csv"
)


# =========================================================
# 職種ごとの希望時給の基準値
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


# =========================================================
# 修正① 職種グループ辞書
# =========================================================
#
# 【変更前】
# キャリアチェンジ時には、
# 10職種の中から完全ランダムに希望職種を選択していた。
#
# 【問題点】
# 完全ランダムにすると、
#
# ・経験職種と同じ職種が再び選ばれ、
#   実際にはキャリアチェンジにならない
#
# ・一般事務からCRAなど、
#   大きく離れた職種転換が同じ確率で発生する
#
# という状態になる。
#
# candidate_experiences.pyでは、
# 職歴について同一occupation_group内の
# キャリア継続をある程度表現するよう修正したため、
# 希望職種についても一定の整合性を持たせる。
#
# 【修正仕様】
# ・80%：直近経験職種を希望
#
# ・残り20%：キャリアチェンジ
#       ├─ 70%：同一occupation_group内の別職種
#       └─ 30%：別グループを含む別職種
#
# ・キャリアチェンジの場合は、
#   原則として直近経験職種そのものは選択しない
#
# ・完全に職歴へ固定せず、
#   未経験職種への希望も一定数残す
#
# ---------------------------------------------------------
# 変更後コード
# ---------------------------------------------------------

occupation_group_map = dict(
    zip(
        occupations["occupation_id"],
        occupations["occupation_group"],
    )
)

occupation_ids = list(
    base_hourly_wage.keys()
)


# =========================================================
# キャリアチェンジ先職種を選択する関数
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


    # 求職終了済みならその日まで、
    # 求職中ならデータ期間末までを有効期間とする
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
    # この候補者の職歴を取得
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


    # candidate_experiences.pyでは
    # 全候補者に最低1件の職歴を保証しているが、
    # 念のためここでも確認する
    if len(candidate_exp) == 0:
        continue


    # =====================================================
    # 修正① 希望職種
    # =====================================================
    #
    # 【変更前】
    #
    # # 80％は経験職種から選択
    # # 20％は別職種へのキャリアチェンジ
    #
    # if rng.random() < 0.80:
    #
    #     preferred_occupation_id = (
    #         candidate_exp.iloc[0]["occupation_id"]
    #     )
    #
    # else:
    #
    #     preferred_occupation_id = rng.choice(
    #         list(base_hourly_wage.keys())
    #     )
    #
    #
    # 【問題点】
    # キャリアチェンジ側でも現在の経験職種が
    # 再度選ばれる可能性がある。
    #
    # また、経験領域とはまったく関係のない職種への
    # 転換が同じ確率で発生していた。
    #
    #
    # 【修正仕様】
    # ・80%は直近経験職種をそのまま希望
    # ・20%はキャリアチェンジ
    # ・キャリアチェンジの70%程度は
    #   同一occupation_group内の別職種
    # ・残りは異なる領域への転換も許容
    #
    # -----------------------------------------------------
    # 変更後コード
    # -----------------------------------------------------

    latest_occupation_id = (
        candidate_exp.iloc[0][
            "occupation_id"
        ]
    )


    if rng.random() < 0.80:

        preferred_occupation_id = (
            latest_occupation_id
        )

    else:

        preferred_occupation_id = (
            select_career_change_occupation(
                latest_occupation_id
            )
        )


    # =====================================================
    # 希望職種に対するスキルレベル
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

        # 未経験職種の場合
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
    # 希望時給
    # =====================================================

    desired_hourly_wage = (
        base_hourly_wage[
            preferred_occupation_id
        ]
    )


    # スキルによる調整
    desired_hourly_wage += (
        candidate_skill_level - 3
    ) * 150


    # 個人差
    desired_hourly_wage += rng.normal(
        loc=0,
        scale=100,
    )


    # 2026年は希望時給水準を8％程度上昇
    #
    # 仮説2：
    # 求人提示時給の上昇よりも
    # 候補者希望時給の上昇をやや大きくし、
    # 給与条件ミスマッチが拡大する構造を作る。
    if (
        registration_date.year
        >= 2026
    ):

        desired_hourly_wage *= 1.08


    # 50円単位に丸める
    desired_hourly_wage = int(
        round(
            desired_hourly_wage
            / 50
        )
        * 50
    )


    # 最低時給を設定
    desired_hourly_wage = max(
        desired_hourly_wage,
        1200,
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
        [
            "onsite",
            "hybrid",
            "remote",
        ],
        p=[
            0.50,
            0.35,
            0.15,
        ],
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
        and rng.random() < 0.30
    )


    if has_update:

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
        # 1件目
        # -------------------------------------------------

        first_preference_id = (
            f"PRE{preference_counter:05d}"
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


        # -------------------------------------------------
        # 更新後は希望時給を少し上げる
        # -------------------------------------------------

        updated_hourly_wage = int(
            round(
                (
                    desired_hourly_wage
                    * rng.uniform(
                        1.03,
                        1.07,
                    )
                )
                / 50
            )
            * 50
        )


        second_preference_id = (
            f"PRE{preference_counter:05d}"
        )


        # 求職中なら現在の希望条件なので終了日はNULL
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
            f"PRE{preference_counter:05d}"
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
    base_hourly_wage.keys()
).all()


assert candidate_preferences[
    "desired_hourly_wage"
].gt(0).all()


assert candidate_preferences[
    "preferred_work_style"
].isin(
    [
        "onsite",
        "hybrid",
        "remote",
    ]
).all()


# =========================================================
# 有効期間の品質チェック
# =========================================================

# 有効終了日がある場合、
# 有効開始日以降であること
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


# 希望条件の有効開始日は
# 登録日より前にならない
assert (
    preference_check[
        "effective_from"
    ]
    >=
    preference_check[
        "registration_date"
    ]
).all()


# 求職終了済み候補者では、
# 希望条件の終了日が求職終了日を超えない
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
#
# 同一候補者について、
# 1件目のeffective_toの翌日から
# 2件目が始まる構造になっていることを確認する。

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
# 全候補者に最低1件の希望条件が存在
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
# CSV出力
# =========================================================

candidate_preferences.to_csv(
    OUTPUT_DIR
    / "candidate_preferences_test.csv",
    index=False,
    encoding="utf-8-sig",
)


# =========================================================
# 内容確認
# =========================================================

print(
    candidate_preferences
)

print()

print(
    "希望条件テストデータを生成しました。"
)

print(
    f"件数: {len(candidate_preferences)}"
)


print()
print(
    "求職者ごとの希望条件件数"
)

print(
    candidate_preferences[
        "candidate_id"
    ].value_counts().sort_index()
)


print()
print(
    "希望勤務形態"
)

print(
    candidate_preferences[
        "preferred_work_style"
    ].value_counts()
)


print()
print(
    "希望時給の基本統計量"
)

print(
    candidate_preferences[
        "desired_hourly_wage"
    ].describe()
)


# =========================================================
# 修正①の内容確認
# =========================================================

# 最新職歴との関係を確認する
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


print()
print(
    "直近経験職種と希望職種が一致する割合"
)

print(
    preference_review[
        "same_as_latest_experience"
    ].mean()
)


print()
print(
    "直近経験職種と希望職種が"
    "同一職種グループの割合"
)

print(
    preference_review[
        "same_occupation_group"
    ].mean()
)


print()
print(
    "直近経験職種と希望職種の確認"
)

print(
    preference_review[
        [
            "candidate_id",
            "latest_experience_occupation_id",
            "preferred_occupation_id",
            "same_as_latest_experience",
            "latest_experience_group",
            "preferred_occupation_group",
            "same_occupation_group",
        ]
    ].sort_values(
        "candidate_id"
    )
)