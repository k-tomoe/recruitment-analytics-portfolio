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
# 修正① 職歴職種の生成方法
# =========================================================
#
# 【変更前】
# 各職歴について、
# 10職種から完全ランダムにoccupation_idを選択していた。
#
# 変更前コード：
#
# occupation_id = rng.choice(
#     list(occupation_skill_base.keys())
# )
#
#
# 【問題点】
# 初回EDAでは、application 28件のうち18件で
# candidate_skill_levelがNULLとなった。
#
# 現在の分析定義では、
# 求人と同じoccupation_idの職歴が存在しない場合、
# candidate_skill_levelがNULLとなる。
#
# 10人程度の小規模テストで、
# 1人1～2件の職歴を10職種から完全ランダム生成すると、
# 職歴が職種全体へ散らばりやすく、
# 専門職求人に対応できる候補者が不足しやすい。
#
# また、同一人物の複数職歴が
# 毎回まったく無関係な職種になる可能性も高く、
# キャリア履歴としてやや不自然になる。
#
#
# 【修正仕様】
# ・最初の職歴は、候補者市場を想定した職種分布から生成する
# ・一般職をやや多く、専門職は一定数存在する分布とする
# ・2件目以降は65%程度の確率で、
#   前職と同じoccupation_groupの職種を選ぶ
# ・残り35%では別職種へのキャリアチェンジも許容する
# ・完全に求人職種へ合わせるわけではなく、
#   スキルミスマッチや未経験応募が残るようランダム性を維持する
#
# ---------------------------------------------------------
# 変更後コード
# ---------------------------------------------------------

occupation_ids = list(
    occupation_skill_base.keys()
)


# 候補者側の職歴分布
#
# 求人需要に完全一致させず、
# 一般職をやや多めにしながら
# 専門職経験者も一定数存在するようにする。
occupation_probs = [
    0.18,  # 一般事務
    0.14,  # データ入力
    0.12,  # コールセンター
    0.08,  # 医薬翻訳
    0.11,  # QC
    0.11,  # DM
    0.08,  # CRC
    0.06,  # CRA
    0.06,  # 統計解析
    0.06,  # 薬事
]


# occupation_id → occupation_group
occupation_group_map = dict(
    zip(
        occupations["occupation_id"],
        occupations["occupation_group"],
    )
)


# =========================================================
# 職種を選択する関数
# =========================================================

def select_occupation(
    previous_occupation_id=None,
):

    # -----------------------------------------------------
    # 最初の職歴
    # -----------------------------------------------------

    if previous_occupation_id is None:

        return rng.choice(
            occupation_ids,
            p=occupation_probs,
        )


    # -----------------------------------------------------
    # 2件目以降
    # -----------------------------------------------------

    # 65%程度は前職と同じ職種グループを選ぶ。
    #
    # 同じ専門領域内で職種が変わるような
    # キャリア形成を表現する。
    stay_in_same_group = (
        rng.random() < 0.65
    )


    if stay_in_same_group:

        previous_group = (
            occupation_group_map[
                previous_occupation_id
            ]
        )


        same_group_occupations = [
            occupation_id
            for occupation_id
            in occupation_ids
            if (
                occupation_group_map[
                    occupation_id
                ]
                == previous_group
            )
        ]


        # 同一グループに職種が存在する場合
        if len(
            same_group_occupations
        ) > 0:

            return rng.choice(
                same_group_occupations
            )


    # -----------------------------------------------------
    # 別グループへのキャリアチェンジ
    # -----------------------------------------------------

    return rng.choice(
        occupation_ids,
        p=occupation_probs,
    )


# =========================================================
# 職歴データ生成
# =========================================================

experience_data = []

experience_counter = 1


for _, candidate in candidates.iterrows():

    candidate_id = candidate[
        "candidate_id"
    ]

    registration_date = candidate[
        "registration_date"
    ]


    # =====================================================
    # 修正② 1人あたり職歴件数
    # =====================================================
    #
    # 【変更前】
    #
    # n_experiences = rng.choice(
    #     [1, 2],
    #     p=[0.65, 0.35],
    # )
    #
    #
    # 【問題点】
    # 小規模テストでは10人しかいないため、
    # 全体でも10～20件程度の職歴しか生成されず、
    # 10種類あるoccupation_idに対して
    # 同職種経験者が極端に不足する可能性が高かった。
    #
    #
    # 【修正仕様】
    # ・1人あたり1～3件の職歴を生成する
    # ・1～2件を中心としつつ、
    #   一部候補者は3件の職歴を持つ
    # ・8年間という職歴生成範囲は変更しない
    #
    # -----------------------------------------------------
    # 変更後コード
    # -----------------------------------------------------

    n_experiences = int(
        rng.choice(
            [
                1,
                2,
                3,
            ],
            p=[
                0.35,
                0.45,
                0.20,
            ],
        )
    )


    # 登録日時点の年齢情報を持っていないため、
    # ここでは最大8年前までの職歴を作る
    earliest_start = (
        registration_date
        - pd.DateOffset(
            years=8
        )
    )


    previous_end_date = None

    previous_occupation_id = None


    for experience_no in range(
        n_experiences
    ):

        # -------------------------------------------------
        # 修正① 職種
        # -------------------------------------------------

        occupation_id = (
            select_occupation(
                previous_occupation_id
            )
        )


        # -------------------------------------------------
        # 職歴開始日
        # -------------------------------------------------

        if previous_end_date is None:

            available_days = (
                registration_date
                - earliest_start
            ).days


            start_offset = rng.integers(
                0,
                max(
                    1,
                    available_days - 180,
                ),
            )


            start_date = (
                earliest_start
                + pd.Timedelta(
                    days=int(
                        start_offset
                    )
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
                    days=int(
                        gap_days
                    )
                )
            )


        # -------------------------------------------------
        # 職歴終了日
        # -------------------------------------------------

        max_duration_days = (
            registration_date
            - start_date
        ).days


        # 最低6か月程度の職歴を確保できない場合は
        # それ以上の職歴生成を終了する
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
                days=int(
                    duration_days
                )
            )
        )


        if end_date > registration_date:

            end_date = registration_date


        # -------------------------------------------------
        # スキルレベル
        # -------------------------------------------------

        base_skill = (
            occupation_skill_base[
                occupation_id
            ]
        )


        skill_adjustment = rng.choice(
            [
                -1,
                0,
                1,
            ],
            p=[
                0.20,
                0.60,
                0.20,
            ],
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


        # -------------------------------------------------
        # レコード追加
        # -------------------------------------------------

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

        previous_occupation_id = (
            occupation_id
        )


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
    candidates[
        "candidate_id"
    ]
).all()


assert candidate_experiences[
    "occupation_id"
].isin(
    occupations[
        "occupation_id"
    ]
).all()


assert candidate_experiences[
    "skill_level"
].between(
    1,
    5,
).all()


assert (
    candidate_experiences[
        "end_date"
    ]
    >=
    candidate_experiences[
        "start_date"
    ]
).all()


# =========================================================
# 登録日との整合性
# =========================================================

check_df = (
    candidate_experiences.merge(
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


# 登録日より後の職歴がないことを確認
assert (
    check_df[
        "end_date"
    ]
    <=
    check_df[
        "registration_date"
    ]
).all()


# 職歴開始日も登録日以前
assert (
    check_df[
        "start_date"
    ]
    <=
    check_df[
        "registration_date"
    ]
).all()


# =========================================================
# 求職者ごとに最低1件の職歴が存在すること
# =========================================================

candidate_with_experience = set(
    candidate_experiences[
        "candidate_id"
    ]
)


assert set(
    candidates[
        "candidate_id"
    ]
).issubset(
    candidate_with_experience
)


# =========================================================
# 職歴期間の重複チェック
# =========================================================
#
# 今回の生成ロジックでは、
#
# 前職終了
# ↓
# 15～120日の空白期間
# ↓
# 次職開始
#
# としているため、
# 同一候補者の職歴期間が重ならないことを確認する。

experience_order_check = (
    candidate_experiences
    .sort_values(
        [
            "candidate_id",
            "start_date",
        ]
    )
    .copy()
)


experience_order_check[
    "previous_end_date"
] = (
    experience_order_check
    .groupby(
        "candidate_id"
    )[
        "end_date"
    ]
    .shift(1)
)


overlap_check = (
    experience_order_check[
        experience_order_check[
            "previous_end_date"
        ].notna()
    ]
)


assert (
    overlap_check[
        "start_date"
    ]
    >
    overlap_check[
        "previous_end_date"
    ]
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

print(
    candidate_experiences
)

print()

print(
    "職歴テストデータを生成しました。"
)

print(
    f"件数: {len(candidate_experiences)}"
)


print()
print(
    "求職者ごとの職歴件数"
)

print(
    candidate_experiences[
        "candidate_id"
    ].value_counts().sort_index()
)


print()
print(
    "スキルレベル分布"
)

print(
    candidate_experiences[
        "skill_level"
    ].value_counts().sort_index()
)


# =========================================================
# 修正①・②の内容確認
# =========================================================

print()
print(
    "職種別職歴件数"
)

print(
    candidate_experiences[
        "occupation_id"
    ].value_counts().sort_index()
)


# occupation_nameが存在する場合は、
# 確認しやすいよう名称付きでも表示
experience_occupation_check = (
    candidate_experiences.merge(
        occupations,
        on="occupation_id",
        how="left",
    )
)


print()
print(
    "職種グループ別職歴件数"
)

print(
    experience_occupation_check[
        "occupation_group"
    ].value_counts()
)


print()
print(
    "求職者別の職歴遷移"
)

print(
    experience_occupation_check[
        [
            "candidate_id",
            "occupation_id",
            "occupation_group",
            "start_date",
            "end_date",
            "skill_level",
        ]
    ].sort_values(
        [
            "candidate_id",
            "start_date",
        ]
    )
)