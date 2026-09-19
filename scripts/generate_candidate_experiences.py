from pathlib import Path

import numpy as np
import pandas as pd


# =========================================================
# 基本設定
# =========================================================

OUTPUT_DIR = Path("data/raw")

rng = np.random.default_rng(42)


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

occupations = pd.read_csv(
    OUTPUT_DIR / "occupations.csv"
)


# =========================================================
# 職種ごとの基本スキル水準
# =========================================================

occupation_skill_base = {
    "OCC001": 1,  # 一般事務
    "OCC002": 1,  # データ入力
    "OCC003": 2,  # コールセンター
    "OCC004": 3,  # 医薬翻訳
    "OCC005": 3,  # 品質管理（QC）
    "OCC006": 3,  # DM
    "OCC007": 3,  # CRC
    "OCC008": 4,  # CRA
    "OCC009": 4,  # 統計解析
    "OCC010": 4,  # 薬事
}


# =========================================================
# 職歴データ生成
# =========================================================

experience_data = []

experience_counter = 1


for _, candidate in candidates.iterrows():

    candidate_id = candidate["candidate_id"]
    registration_date = candidate["registration_date"]

    # 1人あたり1～2件の職歴
    n_experiences = rng.choice(
        [1, 2],
        p=[0.65, 0.35],
    )

    # 登録日時点の年齢情報を持っていないため、
    # ここでは最大8年前までの職歴を作る
    earliest_start = (
        registration_date
        - pd.DateOffset(years=8)
    )

    previous_end_date = None

    for experience_no in range(n_experiences):

        # -----------------------------------------------------
        # 職種
        # -----------------------------------------------------

        occupation_id = rng.choice(
            list(occupation_skill_base.keys())
        )


        # -----------------------------------------------------
        # 職歴開始日
        # -----------------------------------------------------

        if previous_end_date is None:

            available_days = (
                registration_date
                - earliest_start
            ).days

            start_offset = rng.integers(
                0,
                max(1, available_days - 180),
            )

            start_date = (
                earliest_start
                + pd.Timedelta(
                    days=int(start_offset)
                )
            )

        else:

            gap_days = rng.integers(
                15,
                121,
            )

            start_date = (
                previous_end_date
                + pd.Timedelta(
                    days=int(gap_days)
                )
            )


        # -----------------------------------------------------
        # 職歴終了日
        # -----------------------------------------------------

        max_duration_days = (
            registration_date
            - start_date
        ).days

        if max_duration_days < 180:
            break

        duration_days = rng.integers(
            180,
            min(
                1461,
                max_duration_days + 1,
            ),
        )

        end_date = (
            start_date
            + pd.Timedelta(
                days=int(duration_days)
            )
        )

        if end_date > registration_date:
            end_date = registration_date


        # -----------------------------------------------------
        # スキルレベル
        # -----------------------------------------------------

        base_skill = occupation_skill_base[
            occupation_id
        ]

        skill_adjustment = rng.choice(
            [-1, 0, 1],
            p=[0.20, 0.60, 0.20],
        )

        skill_level = (
            base_skill
            + skill_adjustment
        )

        skill_level = int(
            np.clip(
                skill_level,
                1,
                5,
            )
        )


        # -----------------------------------------------------
        # レコード追加
        # -----------------------------------------------------

        candidate_experience_id = (
            f"EXP{experience_counter:05d}"
        )

        experience_data.append(
            [
                candidate_experience_id,
                candidate_id,
                occupation_id,
                start_date,
                end_date,
                skill_level,
            ]
        )

        experience_counter += 1
        previous_end_date = end_date


# =========================================================
# DataFrame化
# =========================================================

candidate_experiences = pd.DataFrame(
    experience_data,
    columns=[
        "candidate_experience_id",
        "candidate_id",
        "occupation_id",
        "start_date",
        "end_date",
        "skill_level",
    ],
)


# =========================================================
# データ品質チェック
# =========================================================

assert candidate_experiences[
    "candidate_experience_id"
].is_unique

assert candidate_experiences[
    "candidate_id"
].isin(
    candidates["candidate_id"]
).all()

assert candidate_experiences[
    "occupation_id"
].isin(
    occupations["occupation_id"]
).all()

assert candidate_experiences[
    "skill_level"
].between(
    1,
    5,
).all()

assert (
    candidate_experiences["end_date"]
    >=
    candidate_experiences["start_date"]
).all()


# 登録日より後の職歴がないことを確認
check_df = candidate_experiences.merge(
    candidates[
        [
            "candidate_id",
            "registration_date",
        ]
    ],
    on="candidate_id",
    how="left",
)

assert (
    check_df["end_date"]
    <=
    check_df["registration_date"]
).all()


# =========================================================
# CSV出力
# =========================================================

candidate_experiences.to_csv(
    OUTPUT_DIR
    / "candidate_experiences_test.csv",
    index=False,
    encoding="utf-8-sig",
)


# =========================================================
# 内容確認
# =========================================================

print(candidate_experiences)

print()
print("職歴テストデータを生成しました。")
print(
    f"件数: {len(candidate_experiences)}"
)

print()
print("求職者ごとの職歴件数")
print(
    candidate_experiences[
        "candidate_id"
    ].value_counts().sort_index()
)

print()
print("スキルレベル分布")
print(
    candidate_experiences[
        "skill_level"
    ].value_counts().sort_index()
)