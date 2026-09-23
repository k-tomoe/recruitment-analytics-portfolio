from pathlib import Path

import numpy as np
import pandas as pd


# =========================================================
# 基本設定
# =========================================================

OUTPUT_DIR = Path("data/raw")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 分析用データでは、
# 小規模テスト用の *_test.csv ではなく、
# 正式な分析用ファイル名を使用する。
OUTPUT_FILE = OUTPUT_DIR / "candidates.csv"

# データ観察終了日
DATA_END_DATE = pd.Timestamp("2026-09-30")

# 乱数生成器
#
# 分析結果を見て都合のよい乱数へ変更しないよう、
# 分析用データではseedを固定する。
SEED = 42
rng = np.random.default_rng(SEED)


# =========================================================
# 担当者マスタを読み込む
# =========================================================

recruiters = pd.read_csv(
    OUTPUT_DIR / "recruiters.csv",
    parse_dates=[
        "join_date",
        "leave_date",
    ],
)


# =========================================================
# 求職者データ生成期間
# =========================================================

# 2025年4月からの分析に備えて、
# 2025年1～3月はウォームアップ期間として含める。
start_date = pd.Timestamp("2025-01-01")
end_date = DATA_END_DATE


# =========================================================
# 修正① 候補者数と登録月の生成方法
# =========================================================
#
# 【変更前】
#
# N_CANDIDATES = 10
#
# registration_months_test = [
#     "2025-02",
#     "2025-04",
#     "2025-05",
#     "2025-07",
#     "2025-09",
#     "2026-02",
#     "2026-04",
#     "2026-05",
#     "2026-07",
#     "2026-09",
# ]
#
#
# 【問題点】
#
# 小規模テストでは、
# 生成処理が正常に接続できることを確認する目的で、
# 候補者を10人に固定していた。
#
# しかし統計分析では、
#
# ・年次差の検定
# ・信頼区間
# ・効果量
# ・相関分析
# ・ロジスティック回帰
#
# などを実施するため、十分な候補者数が必要となる。
#
# また、
#
# 「2025年850人」
# 「2026年950人」
#
# と単純に暦年で比較すると、
# 2025年は12か月、
# 2026年は9か月しか観察していないため、
# 月当たりの候補者供給量を適切に比較できない。
#
#
# 【修正仕様】
#
# 分析対象期間を同じ9か月で比較する。
#
# 2025年4～12月：850人
# 2026年1～9月 ：950人
#
# → 2026年の候補者供給は約+11.8%
#
# さらに、
# 2025年4月の分析開始前から求職者が存在する状態を作るため、
# 2025年1～3月に150人をウォームアップ候補者として生成する。
#
# 合計候補者数：
#
# 150 + 850 + 950
# = 1,950人
#
# 月ごとの人数は完全均等にはせず、
# 小さなばらつきを持たせる。
# =========================================================


# ---------------------------------------------------------
# ウォームアップ期間
# 2025年1～3月
# 合計150人
# ---------------------------------------------------------

warmup_monthly_counts = {
    "2025-01": 45,
    "2025-02": 50,
    "2025-03": 55,
}


# ---------------------------------------------------------
# 2025年分析対象期間
# 2025年4～12月
# 合計850人
# ---------------------------------------------------------

analysis_2025_monthly_counts = {
    "2025-04": 90,
    "2025-05": 92,
    "2025-06": 94,
    "2025-07": 95,
    "2025-08": 96,
    "2025-09": 95,
    "2025-10": 94,
    "2025-11": 97,
    "2025-12": 97,
}


# ---------------------------------------------------------
# 2026年分析対象期間
# 2026年1～9月
# 合計950人
# ---------------------------------------------------------

analysis_2026_monthly_counts = {
    "2026-01": 100,
    "2026-02": 103,
    "2026-03": 105,
    "2026-04": 107,
    "2026-05": 108,
    "2026-06": 109,
    "2026-07": 106,
    "2026-08": 105,
    "2026-09": 107,
}


# ---------------------------------------------------------
# 月別設定を統合
# ---------------------------------------------------------

monthly_registration_counts = {
    **warmup_monthly_counts,
    **analysis_2025_monthly_counts,
    **analysis_2026_monthly_counts,
}


# 候補者総数
N_CANDIDATES = sum(
    monthly_registration_counts.values()
)


# =========================================================
# 登録月リストを作成
# =========================================================

registration_months = []

for month, count in monthly_registration_counts.items():

    registration_months.extend(
        [month] * count
    )


# 候補者IDと登録月に不要な規則性が出ないよう、
# 月リストをランダムに並べ替える。
#
# 例：
# CAN00001～CAN00090がすべて2025-04
# のような人工的な並びを避ける。
rng.shuffle(
    registration_months
)


# 設定した月別人数の合計と
# 候補者総数が一致していることを確認
assert (
    len(registration_months)
    == N_CANDIDATES
)


# =========================================================
# 求職者データ生成
# =========================================================

candidate_data = []


for i in range(1, N_CANDIDATES + 1):

    # -----------------------------------------------------
    # 求職者ID
    # -----------------------------------------------------

    candidate_id = f"CAN{i:05d}"


    # -----------------------------------------------------
    # 登録日
    # -----------------------------------------------------

    registration_month = (
        registration_months[
            i - 1
        ]
    )

    # 例：
    # "2025-04" → 2025-04-01
    month_start = pd.Timestamp(
        f"{registration_month}-01"
    )

    # その月の最終日
    month_end = (
        month_start
        + pd.offsets.MonthEnd(0)
    )

    # データ観察終了日を超えないようにする
    month_end = min(
        month_end,
        end_date,
    )

    # 月初から月末までの日数
    days_in_range = (
        month_end
        - month_start
    ).days

    # 月内の具体的な登録日はランダムにする。
    #
    # 月別人数そのものは制御するが、
    # 日単位ではランダム性を残す。
    random_days = int(
        rng.integers(
            0,
            days_in_range + 1,
        )
    )

    registration_date = (
        month_start
        + pd.Timedelta(
            days=random_days
        )
    )


    # -----------------------------------------------------
    # 求職ステータス
    # -----------------------------------------------------
    #
    # 【変更前】
    #
    # 小規模テストでも
    # searching 75%
    # ended     25%
    # としていた。
    #
    # 【問題点】
    #
    # この部分については、
    # 小規模テストで大きな不整合は確認されなかった。
    #
    # 【修正仕様】
    #
    # 分析用データでも同じ比率を維持する。
    #
    # placedはここでは生成せず、
    # placements生成後に更新する。
    # -----------------------------------------------------

    status = rng.choice(
        [
            "searching",
            "ended",
        ],
        p=[
            0.75,
            0.25,
        ],
    )


    # -----------------------------------------------------
    # 求職終了日
    # -----------------------------------------------------

    if status == "ended":

        max_search_days = (
            end_date
            - registration_date
        ).days

        # 最低14日程度の求職期間を確保できる場合
        if max_search_days >= 14:

            # 最短14日
            # 最長180日程度
            search_days = int(
                rng.integers(
                    14,
                    min(
                        181,
                        max_search_days + 1,
                    ),
                )
            )

            search_end_date = (
                registration_date
                + pd.Timedelta(
                    days=search_days
                )
            )

        else:

            # データ期間末直前に登録した候補者は、
            # 十分な求職期間を観察できないため
            # endedにはせずsearchingとして扱う。
            status = "searching"
            search_end_date = pd.NaT

    else:

        search_end_date = pd.NaT


    # -----------------------------------------------------
    # CA担当者を割り当てるか
    # -----------------------------------------------------
    #
    # 【変更前】
    #
    # CA割当率 = 70%
    #
    # 【問題点】
    #
    # 小規模EDAでは、
    # CA割当率自体に重大な問題は確認されなかった。
    #
    # 【修正仕様】
    #
    # 分析用データでも70%を維持する。
    #
    # CA未割当候補者を残すことで、
    # self_entry中心で活動する候補者も表現する。
    # -----------------------------------------------------

    has_ca = (
        rng.random() < 0.70
    )


    if has_ca:

        # 登録日時点で在籍しているCAのみ抽出
        active_ca = recruiters[
            (
                recruiters["role_type"]
                == "CA"
            )
            &
            (
                recruiters["join_date"]
                <= registration_date
            )
            &
            (
                recruiters["leave_date"].isna()
                |
                (
                    recruiters["leave_date"]
                    >= registration_date
                )
            )
        ]

        if len(active_ca) > 0:

            ca_id = rng.choice(
                active_ca[
                    "recruiter_id"
                ]
            )

        else:

            ca_id = None

    else:

        ca_id = None


    # -----------------------------------------------------
    # 1行追加
    # -----------------------------------------------------

    candidate_data.append(
        [
            candidate_id,
            ca_id,
            registration_date,
            search_end_date,
            status,
        ]
    )


# =========================================================
# DataFrameへ変換
# =========================================================

candidates = pd.DataFrame(
    candidate_data,
    columns=[
        "candidate_id",
        "ca_id",
        "registration_date",
        "search_end_date",
        "status",
    ],
)


# =========================================================
# データ品質チェック
# =========================================================

# ---------------------------------------------------------
# ID
# ---------------------------------------------------------

assert candidates[
    "candidate_id"
].is_unique


# ---------------------------------------------------------
# 必須項目
# ---------------------------------------------------------

assert candidates[
    "candidate_id"
].notna().all()

assert candidates[
    "registration_date"
].notna().all()

assert candidates[
    "status"
].notna().all()


# ---------------------------------------------------------
# ステータス
# ---------------------------------------------------------

assert candidates[
    "status"
].isin(
    [
        "searching",
        "ended",
    ]
).all()


# endedなら求職終了日必須
assert candidates.loc[
    candidates["status"] == "ended",
    "search_end_date",
].notna().all()


# searchingなら求職終了日はNULL
assert candidates.loc[
    candidates["status"] == "searching",
    "search_end_date",
].isna().all()


# ---------------------------------------------------------
# 日付
# ---------------------------------------------------------

ended_candidates = candidates[
    candidates[
        "search_end_date"
    ].notna()
]

assert (
    ended_candidates[
        "search_end_date"
    ]
    >=
    ended_candidates[
        "registration_date"
    ]
).all()


assert (
    candidates[
        "registration_date"
    ]
    >= start_date
).all()


assert (
    candidates[
        "registration_date"
    ]
    <= end_date
).all()


# ---------------------------------------------------------
# CA
# ---------------------------------------------------------

assigned_candidates = candidates[
    candidates["ca_id"].notna()
]


ca_master = recruiters[
    recruiters["role_type"] == "CA"
]


# CA IDがマスタに存在する
assert assigned_candidates[
    "ca_id"
].isin(
    ca_master[
        "recruiter_id"
    ]
).all()


candidate_ca_check = (
    assigned_candidates.merge(
        recruiters[
            [
                "recruiter_id",
                "join_date",
                "leave_date",
            ]
        ],
        left_on="ca_id",
        right_on="recruiter_id",
        how="left",
    )
)


# CA着任日前に担当していない
assert (
    candidate_ca_check[
        "registration_date"
    ]
    >=
    candidate_ca_check[
        "join_date"
    ]
).all()


# 離任済みCAの場合、
# 登録日が離任日以前
left_ca_check = candidate_ca_check[
    candidate_ca_check[
        "leave_date"
    ].notna()
]


assert (
    left_ca_check[
        "registration_date"
    ]
    <=
    left_ca_check[
        "leave_date"
    ]
).all()


# =========================================================
# 修正① 分析用人数に対する品質チェック
# =========================================================

# ウォームアップ期間
warmup_mask = (
    (
        candidates["registration_date"]
        >= pd.Timestamp("2025-01-01")
    )
    &
    (
        candidates["registration_date"]
        <= pd.Timestamp("2025-03-31")
    )
)


# 2025年比較対象期間
analysis_2025_mask = (
    (
        candidates["registration_date"]
        >= pd.Timestamp("2025-04-01")
    )
    &
    (
        candidates["registration_date"]
        <= pd.Timestamp("2025-12-31")
    )
)


# 2026年比較対象期間
analysis_2026_mask = (
    (
        candidates["registration_date"]
        >= pd.Timestamp("2026-01-01")
    )
    &
    (
        candidates["registration_date"]
        <= pd.Timestamp("2026-09-30")
    )
)


# 設計通りの人数になっていることを確認
assert warmup_mask.sum() == 150

assert analysis_2025_mask.sum() == 850

assert analysis_2026_mask.sum() == 950


# 合計1,950人
assert len(candidates) == 1950


# ---------------------------------------------------------
# 全設定月に候補者が存在することを確認
# ---------------------------------------------------------

generated_month_counts = (
    candidates[
        "registration_date"
    ]
    .dt.to_period("M")
    .value_counts()
    .sort_index()
)


expected_month_counts = pd.Series(
    {
        pd.Period(month, freq="M"): count
        for month, count
        in monthly_registration_counts.items()
    }
).sort_index()


assert (
    generated_month_counts
    ==
    expected_month_counts
).all()


# =========================================================
# CSV出力
# =========================================================
#
# 【変更前】
#
# candidates_test.csv
#
# 【問題点】
#
# 今回から小規模テストではなく、
# 統計分析に利用する正式な合成データを生成するため、
# *_test.csv という名称は意味と一致しない。
#
# 【修正仕様】
#
# candidates.csv
# として出力する。
# =========================================================

candidates.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig",
)


# =========================================================
# 内容確認
# =========================================================

print(
    "分析用求職者データを生成しました。"
)

print()

print(
    f"総候補者数: {len(candidates):,}"
)


print()
print(
    "【分析期間別登録者数】"
)

print(
    f"ウォームアップ 2025-01～03: "
    f"{warmup_mask.sum():,}"
)

print(
    f"2025分析対象 2025-04～12: "
    f"{analysis_2025_mask.sum():,}"
)

print(
    f"2026分析対象 2026-01～09: "
    f"{analysis_2026_mask.sum():,}"
)


# 候補者供給増加率
candidate_supply_growth = (
    analysis_2026_mask.sum()
    /
    analysis_2025_mask.sum()
    - 1
)


print()
print(
    "【候補者供給増加率】"
)

print(
    f"2025 → 2026: "
    f"{candidate_supply_growth:.1%}"
)


print()
print(
    "【登録月別件数】"
)

print(
    candidates[
        "registration_date"
    ]
    .dt.to_period("M")
    .value_counts()
    .sort_index()
)


print()
print(
    "【ステータス別件数】"
)

print(
    candidates[
        "status"
    ].value_counts()
)


print()
print(
    "【CA割当状況】"
)

print(
    candidates[
        "ca_id"
    ]
    .notna()
    .value_counts()
)


print()
print(
    "【CA未割当件数】"
)

print(
    candidates[
        "ca_id"
    ]
    .isna()
    .sum()
)


print()
print(
    "【CA担当者別候補者数】"
)

print(
    candidates[
        "ca_id"
    ]
    .value_counts(
        dropna=False
    )
)