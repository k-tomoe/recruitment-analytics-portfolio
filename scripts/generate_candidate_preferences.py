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
# 希望条件データ生成
# =========================================================

preference_data = []

preference_counter = 1


for _, candidate in candidates.iterrows():

    candidate_id = candidate["candidate_id"]
    registration_date = candidate["registration_date"]

    # 求職終了済みならその日まで、
    # 求職中ならデータ期間末までを有効期間とする
    if pd.notna(candidate["search_end_date"]):
        search_limit_date = candidate["search_end_date"]
    else:
        search_limit_date = DATA_END_DATE


    # =====================================================
    # この候補者の職歴を取得
    # =====================================================

    candidate_exp = candidate_experiences[
        candidate_experiences["candidate_id"]
        == candidate_id
    ].copy()

    candidate_exp = candidate_exp.sort_values(
        "end_date",
        ascending=False,
    )


    # =====================================================
    # 希望職種
    # =====================================================

    # 80％は経験職種から選択
    # 20％は別職種へのキャリアチェンジ
    if rng.random() < 0.80:

        preferred_occupation_id = (
            candidate_exp.iloc[0]["occupation_id"]
        )

    else:

        preferred_occupation_id = rng.choice(
            list(base_hourly_wage.keys())
        )


    # =====================================================
    # 希望職種に対するスキルレベル
    # =====================================================

    matching_experience = candidate_exp[
        candidate_exp["occupation_id"]
        == preferred_occupation_id
    ]

    if len(matching_experience) > 0:

        candidate_skill_level = int(
            matching_experience[
                "skill_level"
            ].max()
        )

    else:

        # 未経験職種の場合
        candidate_skill_level = int(
            rng.choice(
                [1, 2],
                p=[0.70, 0.30],
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
    if registration_date.year >= 2026:
        desired_hourly_wage *= 1.08

    # 50円単位に丸める
    desired_hourly_wage = int(
        round(
            desired_hourly_wage / 50
        ) * 50
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
                - pd.Timedelta(days=1),
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
    candidates["candidate_id"]
).all()

assert candidate_preferences[
    "preferred_location_id"
].isin(
    locations["location_id"]
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


# 有効終了日がある場合、
# 有効開始日以降であること
valid_periods = candidate_preferences[
    candidate_preferences[
        "effective_to"
    ].notna()
]

assert (
    valid_periods["effective_to"]
    >=
    valid_periods["effective_from"]
).all()


# 候補者ごとに現在有効な希望条件は最大1件
current_counts = (
    candidate_preferences[
        candidate_preferences[
            "effective_to"
        ].isna()
    ]
    .groupby("candidate_id")
    .size()
)

assert (
    current_counts <= 1
).all()


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

print(candidate_preferences)

print()
print("希望条件テストデータを生成しました。")
print(
    f"件数: {len(candidate_preferences)}"
)

print()
print("求職者ごとの希望条件件数")
print(
    candidate_preferences[
        "candidate_id"
    ].value_counts().sort_index()
)

print()
print("希望勤務形態")
print(
    candidate_preferences[
        "preferred_work_style"
    ].value_counts()
)

print()
print("希望時給の基本統計量")
print(
    candidate_preferences[
        "desired_hourly_wage"
    ].describe()
)