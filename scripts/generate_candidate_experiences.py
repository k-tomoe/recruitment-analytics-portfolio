from pathlib import Path

import numpy as np
import pandas as pd


# =========================================================
# 基本設定
# =========================================================

OUTPUT_DIR = Path("data/raw")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 分析用データの正式ファイル名
OUTPUT_FILE = OUTPUT_DIR / "candidate_experiences.csv"

# 分析結果を見てseedを変更しないよう固定する
SEED = 42
rng = np.random.default_rng(SEED)


# =========================================================
# 元データ読み込み
# =========================================================
#
# 【変更前】
#
# candidates = pd.read_csv(
#     OUTPUT_DIR / "candidates_test.csv",
#     ...
# )
#
#
# 【問題点】
#
# 小規模テスト用の *_test.csv を参照していた。
#
#
# 【修正仕様】
#
# 分析用データ生成では、
# generate_candidates.py が出力する
# candidates.csv を入力とする。
# =========================================================

candidates = pd.read_csv(
    OUTPUT_DIR / "candidates.csv",
    parse_dates=[
        "registration_date",
        "search_end_date",
    ],
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

assert candidates[
    "registration_date"
].notna().all()

assert occupations[
    "occupation_id"
].is_unique


# =========================================================
# 職種ごとの基本スキル水準
# =========================================================
#
# 候補者側のスキル水準は、
# 2025年 / 2026年で意図的に変えない。
#
# H3「スキルミスマッチ」は、
# 後続の generate_jobs.py で
# 2026年の求人要求スキルをやや高度化させることで
# 発生させる。
#
# これにより、
#
# 「2026年だから候補者スキルを下げた」
#
# という直接的な生成を避ける。
# =========================================================

occupation_skill_base = {
    "OCC001": 1,  # 一般事務
    "OCC002": 1,  # データ入力
    "OCC003": 2,  # コールセンター
    "OCC004": 3,  # 医薬翻訳
    "OCC005": 3,  # 品質管理（QC）
    "OCC006": 3,  # DM（データマネジメント）
    "OCC007": 3,  # CRC
    "OCC008": 4,  # CRA
    "OCC009": 4,  # 統計解析
    "OCC010": 4,  # 薬事
}


# =========================================================
# 職歴職種の生成方法
# =========================================================
#
# 【変更前】
#
# 小規模テスト修正後は、
#
# ・最初の職歴を市場分布から生成
# ・2件目以降は65%程度で同じ職種グループ
# ・残りはキャリアチェンジ
#
# としていた。
#
#
# 【問題点】
#
# このロジック自体には、
# 小規模EDAで重大な問題は確認されなかった。
#
# 分析用データでは候補者数が約1,950人になるため、
# 小規模データ特有の職種不足も大幅に緩和される。
#
#
# 【修正仕様】
#
# 職種選択ロジックは基本的に維持する。
#
# 重要なのは、
# 求人職種へ候補者職歴を意図的に合わせず、
# 同職種経験なし・skill gapの両方が
# 自然に発生する状態を残すことである。
# =========================================================

occupation_ids = list(
    occupation_skill_base.keys()
)


# ---------------------------------------------------------
# 候補者市場における職歴職種の基礎分布
# ---------------------------------------------------------
#
# 合計 = 1.00
#
# 一般職をやや多めにしつつ、
# 医薬専門職経験者も一定数存在させる。
#
# この分布は登録年によって変更しない。
# ---------------------------------------------------------

occupation_probs = [
    0.18,  # OCC001 一般事務
    0.14,  # OCC002 データ入力
    0.12,  # OCC003 コールセンター
    0.08,  # OCC004 医薬翻訳
    0.11,  # OCC005 QC
    0.11,  # OCC006 DM
    0.08,  # OCC007 CRC
    0.06,  # OCC008 CRA
    0.06,  # OCC009 統計解析
    0.06,  # OCC010 薬事
]


assert np.isclose(
    sum(occupation_probs),
    1.0,
)


# occupation_id → occupation_group
occupation_group_map = dict(
    zip(
        occupations["occupation_id"],
        occupations["occupation_group"],
    )
)


# 全職種にoccupation_groupが存在することを確認
assert all(
    occupation_id
    in occupation_group_map
    for occupation_id
    in occupation_ids
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
    #
    # 約65%は同じ職種グループ内で転職する。
    #
    # 例：
    # 医薬専門職 → 別の医薬専門職
    #
    # 残りでは異なる職種グループへの転職も許容する。
    # -----------------------------------------------------

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

        if len(
            same_group_occupations
        ) > 0:

            return rng.choice(
                same_group_occupations
            )


    # -----------------------------------------------------
    # キャリアチェンジ
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
    # 1人あたり職歴件数
    # =====================================================
    #
    # 【変更前】
    #
    # 小規模テスト修正後：
    #
    # 1件 35%
    # 2件 45%
    # 3件 20%
    #
    #
    # 【問題点】
    #
    # 分析用データでは約1,950人存在するため、
    # この分布でも十分な職歴件数を確保できる。
    #
    #
    # 【修正仕様】
    #
    # 分布はそのまま維持する。
    #
    # 候補者数を増やしたからといって、
    # 1人あたり職歴件数まで不自然に増やさない。
    # =====================================================

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


    # -----------------------------------------------------
    # 職歴生成対象期間
    # -----------------------------------------------------
    #
    # 年齢属性は現在持っていないため、
    # 登録日から最大8年前までを職歴生成範囲とする。
    # -----------------------------------------------------

    earliest_start = (
        registration_date
        - pd.DateOffset(
            years=8
        )
    )


    previous_end_date = None

    previous_occupation_id = None


    for _ in range(
        n_experiences
    ):

        # -------------------------------------------------
        # 職種
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

            # 最低180日程度の経験期間を確保できるよう、
            # 開始日の上限を調整する。
            latest_start_offset = max(
                1,
                available_days - 180,
            )

            start_offset = int(
                rng.integers(
                    0,
                    latest_start_offset,
                )
            )

            start_date = (
                earliest_start
                + pd.Timedelta(
                    days=start_offset
                )
            )

        else:

            # 転職間の空白期間
            gap_days = int(
                rng.integers(
                    15,
                    121,
                )
            )

            start_date = (
                previous_end_date
                + pd.Timedelta(
                    days=gap_days
                )
            )


        # -------------------------------------------------
        # 職歴終了日
        # -------------------------------------------------

        max_duration_days = (
            registration_date
            - start_date
        ).days


        # 最低6か月程度の職歴を確保できない場合、
        # それ以上の職歴生成を終了する。
        if max_duration_days < 180:
            break


        duration_days = int(
            rng.integers(
                180,
                min(
                    1461,
                    max_duration_days + 1,
                ),
            )
        )


        end_date = (
            start_date
            + pd.Timedelta(
                days=duration_days
            )
        )


        if end_date > registration_date:

            end_date = registration_date


        # -------------------------------------------------
        # スキルレベル
        # ---------------------------------------------------------
        #
        # 【変更前】
        #
        # 職種ごとのbase_skillに対して、
        # -1 / 0 / +1 のランダム補正。
        #
        #
        # 【問題点】
        #
        # 小規模テストでは、
        # この生成方法自体に大きな不整合はなかった。
        #
        #
        # 【修正仕様】
        #
        # 分析用データでも維持する。
        #
        # 特に登録年による補正は行わない。
        #
        # H3では候補者スキルそのものを2026年に
        # 意図的に悪化させず、
        # 求人要求スキルとの相対差を分析する。
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


        skill_level = int(
            np.clip(
                (
                    base_skill
                    + skill_adjustment
                ),
                1,
                5,
            )
        )


        # -------------------------------------------------
        # レコード追加
        # -------------------------------------------------

        candidate_experience_id = (
            f"EXP{experience_counter:06d}"
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

# ---------------------------------------------------------
# ID
# ---------------------------------------------------------

assert candidate_experiences[
    "candidate_experience_id"
].is_unique


# ---------------------------------------------------------
# 外部キー
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# スキル
# ---------------------------------------------------------

assert candidate_experiences[
    "skill_level"
].between(
    1,
    5,
).all()


# ---------------------------------------------------------
# 職歴期間
# ---------------------------------------------------------

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


# 職歴終了日が登録日より後にならない
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
# 全候補者に最低1件の職歴が存在すること
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
# 前職終了
# ↓
# 15～120日程度
# ↓
# 次職開始
#
# という順序で生成しているため、
# 同一候補者の職歴期間が重なっていないことを確認する。
# =========================================================

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
# 分析用データに対する追加品質チェック
# =========================================================
#
# 【変更前】
#
# 10人規模だったため、
# 個々の職歴をコンソールへ表示して確認していた。
#
#
# 【問題点】
#
# 約1,950人では数千行の職歴が生成されるため、
# 全件printしても確認しづらい。
#
#
# 【修正仕様】
#
# 以下の分布を要約して確認する。
#
# ・候補者ごとの職歴件数
# ・職種分布
# ・職種グループ分布
# ・skill_level分布
# ・登録年別skill分布
#
# 2025 / 2026で候補者スキルを
# 意図的に変えていないことも確認可能にする。
# =========================================================


# ---------------------------------------------------------
# 候補者ごとの職歴件数
# ---------------------------------------------------------

experience_count_per_candidate = (
    candidate_experiences
    .groupby(
        "candidate_id"
    )
    .size()
)


assert experience_count_per_candidate.min() >= 1

assert experience_count_per_candidate.max() <= 3


# ---------------------------------------------------------
# 職種情報を追加した確認用DataFrame
# ---------------------------------------------------------

experience_occupation_check = (
    candidate_experiences.merge(
        occupations[
            [
                "occupation_id",
                "occupation_name",
                "occupation_group",
            ]
        ],
        on="occupation_id",
        how="left",
    )
)


assert experience_occupation_check[
    "occupation_name"
].notna().all()


assert experience_occupation_check[
    "occupation_group"
].notna().all()


# ---------------------------------------------------------
# 登録年を付与
# ---------------------------------------------------------

experience_year_check = (
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


experience_year_check[
    "registration_year"
] = (
    experience_year_check[
        "registration_date"
    ].dt.year
)


# =========================================================
# CSV出力
# =========================================================
#
# 【変更前】
#
# candidate_experiences_test.csv
#
#
# 【問題点】
#
# 小規模テスト用名称のままだった。
#
#
# 【修正仕様】
#
# 分析用データとして、
# candidate_experiences.csv
# を出力する。
# =========================================================

candidate_experiences.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig",
)


# =========================================================
# 内容確認
# =========================================================

print(
    "分析用候補者職歴データを生成しました。"
)

print()

print(
    f"候補者数: "
    f"{candidates['candidate_id'].nunique():,}"
)

print(
    f"職歴件数: "
    f"{len(candidate_experiences):,}"
)

print(
    "1人あたり平均職歴件数: "
    f"{experience_count_per_candidate.mean():.2f}"
)


# ---------------------------------------------------------
# 職歴件数分布
# ---------------------------------------------------------

print()
print(
    "【候補者ごとの職歴件数分布】"
)

print(
    experience_count_per_candidate
    .value_counts()
    .sort_index()
)


# ---------------------------------------------------------
# スキル分布
# ---------------------------------------------------------

print()
print(
    "【スキルレベル分布】"
)

print(
    candidate_experiences[
        "skill_level"
    ]
    .value_counts()
    .sort_index()
)


# ---------------------------------------------------------
# 職種別分布
# ---------------------------------------------------------

print()
print(
    "【職種別職歴件数】"
)

print(
    experience_occupation_check
    .groupby(
        [
            "occupation_id",
            "occupation_name",
        ]
    )
    .size()
    .sort_index()
)


# ---------------------------------------------------------
# 職種グループ別分布
# ---------------------------------------------------------

print()
print(
    "【職種グループ別職歴件数】"
)

print(
    experience_occupation_check[
        "occupation_group"
    ]
    .value_counts()
)


# ---------------------------------------------------------
# 登録年別の平均スキル
# ---------------------------------------------------------
#
# 候補者側のスキルを年によって
# 意図的に変えていないことを確認するための参考値。
#
# ランダム性により多少の差が発生すること自体は正常。
# ---------------------------------------------------------

print()
print(
    "【登録年別スキルレベル】"
)

print(
    experience_year_check
    .groupby(
        "registration_year"
    )[
        "skill_level"
    ]
    .agg(
        [
            "count",
            "mean",
            "median",
        ]
    )
)


# ---------------------------------------------------------
# 先頭20件だけサンプル表示
# ---------------------------------------------------------

print()
print(
    "【職歴サンプル：先頭20件】"
)

print(
    experience_occupation_check[
        [
            "candidate_id",
            "occupation_id",
            "occupation_name",
            "occupation_group",
            "start_date",
            "end_date",
            "skill_level",
        ]
    ]
    .sort_values(
        [
            "candidate_id",
            "start_date",
        ]
    )
    .head(20)
)