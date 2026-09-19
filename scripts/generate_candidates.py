from pathlib import Path

import numpy as np
import pandas as pd


# =========================================================
# 基本設定
# =========================================================

OUTPUT_DIR = Path("data/raw")

N_CANDIDATES = 10

# 乱数生成器
# 同じシードを使うことで、同じテストデータを再現できる
rng = np.random.default_rng(42)


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
# 2025年1～3月はウォームアップ期間として含める
start_date = pd.Timestamp("2025-01-01")
end_date = pd.Timestamp("2026-09-30")

total_days = (
    end_date - start_date
).days


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

    random_days = rng.integers(
        0,
        total_days + 1,
    )

    registration_date = (
        start_date
        + pd.Timedelta(
            days=int(random_days)
        )
    )


    # -----------------------------------------------------
    # 求職ステータス
    # -----------------------------------------------------

    # 現段階では placed は生成しない。
    # placements生成後に就業決定者をplacedへ更新する。
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

        # データ期間末直前の登録者など、
        # 十分な求職期間を確保できない場合はsearchingへ戻す
        else:

            status = "searching"
            search_end_date = pd.NaT

    else:

        search_end_date = pd.NaT


    # -----------------------------------------------------
    # CA担当者を割り当てるか
    # -----------------------------------------------------

    # 登録時点ではまだCA未割当の候補者も存在する
    has_ca = (
        rng.random() < 0.70
    )


    if has_ca:

        # 登録日時点で在籍しているCAだけを抽出
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

        # 念のため在籍CAが存在する場合のみ割当
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

# 求職者IDが一意
assert candidates[
    "candidate_id"
].is_unique


# 必須項目がNULLでない
assert candidates[
    "candidate_id"
].notna().all()

assert candidates[
    "registration_date"
].notna().all()

assert candidates[
    "status"
].notna().all()


# ステータスが想定値のみ
assert candidates[
    "status"
].isin(
    [
        "searching",
        "ended",
    ]
).all()


# endedなら求職終了日が必須
assert candidates.loc[
    candidates["status"] == "ended",
    "search_end_date",
].notna().all()


# searchingなら求職終了日はNULL
assert candidates.loc[
    candidates["status"] == "searching",
    "search_end_date",
].isna().all()


# 求職終了日は登録日以降
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


# CA IDが入っている場合、
# recruitersに存在するCAであること
assigned_candidates = candidates[
    candidates["ca_id"].notna()
]

ca_master = recruiters[
    recruiters["role_type"] == "CA"
]

assert assigned_candidates[
    "ca_id"
].isin(
    ca_master[
        "recruiter_id"
    ]
).all()


# CAの着任日前に担当していないことを確認
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

assert (
    candidate_ca_check[
        "registration_date"
    ]
    >=
    candidate_ca_check[
        "join_date"
    ]
).all()


# 離任済みCAの場合は、
# 登録日が離任日以前であること
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
# CSV出力
# =========================================================

candidates.to_csv(
    OUTPUT_DIR / "candidates_test.csv",
    index=False,
    encoding="utf-8-sig",
)


# =========================================================
# 内容確認
# =========================================================

print(candidates)

print()
print(
    "求職者テストデータを生成しました。"
)

print(
    f"件数: {len(candidates)}"
)

print()
print("ステータス別件数")

print(
    candidates[
        "status"
    ].value_counts()
)

print()
print("CA割当状況")

print(
    candidates[
        "ca_id"
    ].notna().value_counts()
)

print()
print("CA未割当件数")

print(
    candidates[
        "ca_id"
    ].isna().sum()
)

print()
print("CA担当者別件数")

print(
    candidates[
        "ca_id"
    ].value_counts(
        dropna=False
    )
)