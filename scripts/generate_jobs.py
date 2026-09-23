from pathlib import Path

import numpy as np
import pandas as pd


# =========================================================
# 基本設定
# =========================================================

OUTPUT_DIR = Path("data/raw")
OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

OUTPUT_FILE = (
    OUTPUT_DIR
    / "jobs.csv"
)

# このスクリプト専用の乱数シード
#
# 分析結果を見た後で都合のよいseedへ変更しない。
SEED = 44
rng = np.random.default_rng(
    SEED
)

# 合成データの観察終了日
DATA_END_DATE = pd.Timestamp(
    "2026-09-30"
)


# =========================================================
# 修正① 分析用求人件数
# =========================================================
#
# 【変更前】
#
# N_JOBS_2025 = 10
# N_JOBS_2026 = 10
#
#
# 【問題点】
#
# 小規模テストでは、
# 生成処理の接続確認を目的として
# 各年10求人としていた。
#
# 統計分析では、
#
# ・求人構成比
# ・要求スキル
# ・給与条件
# ・60日以内充足率
# ・職種別比較
#
# などを分析するため、
# より十分な求人件数が必要となる。
#
#
# 【修正仕様】
#
# 候補者側と同じ9か月同士を比較する。
#
# 2025-04～12：350求人
# 2026-01～09：450求人
#
# 求人需要増加率：
#
# 450 / 350 - 1
# ≒ +28.6%
#
# 一方、候補者供給は約+11.8%であるため、
#
# 求人需要の伸び
# >
# 候補者供給の伸び
#
# というH1の背景構造を作る。
#
# ただし、この求人増加だけを理由に
# placement結果を直接変更することはしない。
# =========================================================

N_JOBS_2025 = 350
N_JOBS_2026 = 450


# =========================================================
# 年度別求人生成期間
# =========================================================
#
# 【変更前】
#
# 2025：
# 2025-04-01 ～ 2025-09-30
#
# 2026：
# 2026-04-01 ～ 2026-09-30
#
#
# 【問題点】
#
# 候補者側では現在、
#
# 2025-04～12
# 2026-01～09
#
# の同じ9か月を比較する設計としている。
#
# 求人だけ6か月比較にすると、
# H1の需要・供給比較期間が一致しない。
#
#
# 【修正仕様】
#
# 2025：2025-04-01 ～ 2025-12-31
# 2026：2026-01-01 ～ 2026-09-30
#
# とし、両年とも9か月で比較する。
# =========================================================

JOB_PERIODS = {
    2025: {
        "start_date":
            pd.Timestamp("2025-04-01"),
        "end_date":
            pd.Timestamp("2025-12-31"),
    },
    2026: {
        "start_date":
            pd.Timestamp("2026-01-01"),
        "end_date":
            pd.Timestamp("2026-09-30"),
    },
}


# =========================================================
# マスタ読み込み
# =========================================================

clients = pd.read_csv(
    OUTPUT_DIR / "clients.csv"
)

recruiters = pd.read_csv(
    OUTPUT_DIR / "recruiters.csv",
    parse_dates=[
        "join_date",
        "leave_date",
    ],
)

occupations = pd.read_csv(
    OUTPUT_DIR / "occupations.csv"
)

locations = pd.read_csv(
    OUTPUT_DIR / "locations.csv"
)


# =========================================================
# 入力マスタの基本確認
# =========================================================

assert clients[
    "client_id"
].is_unique

assert recruiters[
    "recruiter_id"
].is_unique

assert occupations[
    "occupation_id"
].is_unique

assert locations[
    "location_id"
].is_unique


# RAが存在することを確認
assert (
    recruiters[
        "role_type"
    ]
    ==
    "RA"
).any()


# =========================================================
# 職種ごとの求人提示時給の基準
# =========================================================
#
# H2では、
#
# 候補者希望時給：
# 2026年 約+8%
#
# 求人提示時給：
# 2026年 約+3%
#
# とする。
#
# これにより2026年には
# wage_shortfall_rateが
# 結果として高まりやすくなる。
#
# ただし、求人ごとのノイズを残すため、
# 2026年の全求人が給与不足になるわけではない。
# =========================================================

base_offered_wage = {
    "OCC001": 1500,  # 一般事務
    "OCC002": 1400,  # データ入力
    "OCC003": 1600,  # コールセンター
    "OCC004": 2100,  # 医薬翻訳
    "OCC005": 2000,  # 品質管理（QC）
    "OCC006": 2200,  # DM
    "OCC007": 2100,  # CRC
    "OCC008": 2850,  # CRA
    "OCC009": 3000,  # 統計解析
    "OCC010": 2650,  # 薬事
}


# =========================================================
# 職種ごとの基本必要スキル
# =========================================================

base_required_skill = {
    "OCC001": 1,
    "OCC002": 1,
    "OCC003": 2,
    "OCC004": 3,
    "OCC005": 3,
    "OCC006": 3,
    "OCC007": 3,
    "OCC008": 4,
    "OCC009": 4,
    "OCC010": 4,
}


occupation_ids = list(
    base_offered_wage.keys()
)


# =========================================================
# 修正② 年度別の求人職種構成
# =========================================================
#
# 【変更前】
#
# 2025年と2026年で、
# 2026年に専門職割合をかなり大きく増やしていた。
#
#
# 【問題点】
#
# H4は「一部支持」として分析する予定であり、
# 求人ポートフォリオ変化だけで結果が
# ほぼ決まるほど強い変化にはしたくない。
#
#
# 【修正仕様】
#
# 2026年では、
#
# ・一般事務系をやや減少
# ・CRA、統計解析、薬事などをやや増加
#
# とする。
#
# ただし両年ですべての職種が存在する
# 重なりのある分布とする。
# =========================================================

occupation_probs_2025 = [
    0.17,  # OCC001 一般事務
    0.13,  # OCC002 データ入力
    0.13,  # OCC003 コールセンター
    0.08,  # OCC004 医薬翻訳
    0.10,  # OCC005 QC
    0.10,  # OCC006 DM
    0.08,  # OCC007 CRC
    0.07,  # OCC008 CRA
    0.07,  # OCC009 統計解析
    0.07,  # OCC010 薬事
]

occupation_probs_2026 = [
    0.14,  # OCC001 一般事務
    0.10,  # OCC002 データ入力
    0.12,  # OCC003 コールセンター
    0.09,  # OCC004 医薬翻訳
    0.10,  # OCC005 QC
    0.11,  # OCC006 DM
    0.09,  # OCC007 CRC
    0.09,  # OCC008 CRA
    0.08,  # OCC009 統計解析
    0.08,  # OCC010 薬事
]


assert np.isclose(
    sum(occupation_probs_2025),
    1.0,
)

assert np.isclose(
    sum(occupation_probs_2026),
    1.0,
)


# =========================================================
# 勤務地分布
# =========================================================

location_ids = [
    "LOC001",
    "LOC002",
    "LOC003",
    "LOC004",
    "LOC005",
    "LOC006",
    "LOC007",
    "LOC008",
]

location_probs = [
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
    sum(location_probs),
    1.0,
)


assert set(
    location_ids
).issubset(
    set(
        locations[
            "location_id"
        ]
    )
)


# =========================================================
# H6 勤務形態
# =========================================================
#
# 【変更前】
#
# onsite 55%
# hybrid 35%
# remote 10%
#
#
# 【問題点】
#
# 特に問題は確認されていない。
#
#
# 【修正仕様】
#
# 2025 / 2026で同じ基礎分布を維持する。
#
# work_styleそのものを、
# placement・withdrawalなどの確率へ
# 直接利用しない。
#
# そのため、後の分析で勤務形態別の差が
# 明確に確認されなければ、
# H6を支持されなかった仮説として扱える。
# =========================================================

work_styles = [
    "onsite",
    "hybrid",
    "remote",
]

work_style_probs = [
    0.55,
    0.35,
    0.10,
]


# =========================================================
# 年度別の募集枠数分布
# =========================================================
#
# 【変更前】
#
# 2025：
# 1～3枠
# 平均約1.5
#
# 2026：
# 1～4枠
# 平均約1.9
#
#
# 【問題点】
#
# 求人数自体が2026年に約29%増えるため、
# 募集枠まで急激に増やすとH1の需要差が
# 過度に強くなりやすい。
#
#
# 【修正仕様】
#
# 2025平均：約1.7枠
# 2026平均：約1.8枠
#
# とし、2026年は募集枠数も
# やや増える程度にする。
# =========================================================

slot_values = [
    1,
    2,
    3,
    4,
]

slot_probs_2025 = [
    0.50,
    0.33,
    0.14,
    0.03,
]

slot_probs_2026 = [
    0.45,
    0.34,
    0.16,
    0.05,
]


# =========================================================
# 求人公開日を生成する関数
# =========================================================

def generate_open_date(
    year,
):

    period = JOB_PERIODS[
        year
    ]

    start_date = (
        period[
            "start_date"
        ]
    )

    end_date = (
        period[
            "end_date"
        ]
    )

    total_days = (
        end_date
        - start_date
    ).days

    open_offset = int(
        rng.integers(
            0,
            total_days + 1,
        )
    )

    return (
        start_date
        + pd.Timedelta(
            days=open_offset
        )
    )


# =========================================================
# RA担当者を選択する関数
# =========================================================
#
# 【変更前】
#
# 求人公開期間のstart_date時点で
# 在籍しているRAを抽出していた。
#
#
# 【問題点】
#
# 例えば2026年4月に新規RAが着任しても、
# 2026年のstart_dateが1月の場合、
# 4月以降の求人にも新RAが割り当てられない。
#
#
# 【修正仕様】
#
# 各求人の実際のopen_date時点で
# 在籍しているRAから担当者を選択する。
# =========================================================

def select_active_ra(
    open_date,
):

    active_ra = recruiters[
        (
            recruiters[
                "role_type"
            ]
            ==
            "RA"
        )
        &
        (
            recruiters[
                "join_date"
            ]
            <=
            open_date
        )
        &
        (
            recruiters[
                "leave_date"
            ].isna()
            |
            (
                recruiters[
                    "leave_date"
                ]
                >=
                open_date
            )
        )
    ]


    assert len(
        active_ra
    ) > 0


    return rng.choice(
        active_ra[
            "recruiter_id"
        ]
    )


# =========================================================
# 必要スキルレベルを生成する関数
# =========================================================
#
# H3では、
# 候補者側スキルを2026年だけ下げず、
# 求人側の要求水準をやや高度化する。
#
# これにより、
#
# 求人要求スキル上昇
# ↓
# 候補者とのskill gap拡大
#
# という構造を作る。
# =========================================================

def generate_required_skill_level(
    occupation_id,
    year,
):

    required_skill_level = (
        base_required_skill[
            occupation_id
        ]
    )


    # -----------------------------------------------------
    # 求人ごとの個体差
    # -----------------------------------------------------

    skill_adjustment = int(
        rng.choice(
            [
                -1,
                0,
                1,
            ],
            p=[
                0.10,
                0.70,
                0.20,
            ],
        )
    )


    required_skill_level += (
        skill_adjustment
    )


    # -----------------------------------------------------
    # 2026年の要求高度化
    # -----------------------------------------------------
    #
    # すべての求人を一律+1にはしない。
    #
    # 約30%の求人で追加的に要求水準を
    # 1段階上げる。
    #
    # そのため2025/2026の分布には
    # 十分な重なりが残る。
    # -----------------------------------------------------

    if year == 2026:

        if rng.random() < 0.30:

            required_skill_level += 1


    required_skill_level = int(
        np.clip(
            required_skill_level,
            1,
            5,
        )
    )


    return required_skill_level


# =========================================================
# 求人提示時給を生成する関数
# =========================================================

def generate_offered_hourly_wage(
    occupation_id,
    required_skill_level,
    year,
):

    offered_hourly_wage = (
        base_offered_wage[
            occupation_id
        ]
    )


    # -----------------------------------------------------
    # 求人要求スキルによる調整
    # -----------------------------------------------------

    offered_hourly_wage += (
        required_skill_level
        - 3
    ) * 100


    # -----------------------------------------------------
    # 求人ごとのばらつき
    # -----------------------------------------------------

    offered_hourly_wage += (
        rng.normal(
            loc=0,
            scale=80,
        )
    )


    # -----------------------------------------------------
    # H2：2026年の提示時給
    # -----------------------------------------------------
    #
    # 候補者希望時給は約+8%、
    # 求人提示時給は約+3%とする。
    #
    # 給与不足を直接生成するのではなく、
    # 希望側・提示側の伸び率差によって
    # 結果としてミスマッチが生じる。
    # -----------------------------------------------------

    if year == 2026:

        offered_hourly_wage *= (
            1.03
        )


    # 50円単位へ丸める
    offered_hourly_wage = int(
        round(
            offered_hourly_wage
            / 50
        )
        * 50
    )


    # 最低値
    offered_hourly_wage = max(
        offered_hourly_wage,
        1200,
    )


    return offered_hourly_wage


# =========================================================
# 求人終了日を生成する関数
# =========================================================
#
# 小規模テストで修正済みのロジックを
# 分析用データでも維持する。
#
# short：
# 15%
# 60～90日
#
# standard：
# 70%
# 90～180日
#
# long_open：
# 15%
# 観察期間中はcloseなし
# =========================================================

def generate_close_information(
    open_date,
):

    job_duration_type = rng.choice(
        [
            "short",
            "standard",
            "long_open",
        ],
        p=[
            0.15,
            0.70,
            0.15,
        ],
    )


    if job_duration_type == "short":

        open_days = int(
            rng.integers(
                60,
                91,
            )
        )

        calculated_close_date = (
            open_date
            + pd.Timedelta(
                days=open_days
            )
        )


    elif (
        job_duration_type
        ==
        "standard"
    ):

        open_days = int(
            rng.integers(
                90,
                181,
            )
        )

        calculated_close_date = (
            open_date
            + pd.Timedelta(
                days=open_days
            )
        )


    else:

        calculated_close_date = (
            pd.NaT
        )


    # -----------------------------------------------------
    # 観察終了日時点の状態
    # -----------------------------------------------------

    if pd.isna(
        calculated_close_date
    ):

        close_date = pd.NaT
        status = "open"


    elif (
        calculated_close_date
        <=
        DATA_END_DATE
    ):

        close_date = (
            calculated_close_date
        )

        status = "closed"


    else:

        # 将来のclose_dateは記録しない
        close_date = pd.NaT
        status = "open"


    return (
        close_date,
        status,
    )


# =========================================================
# 求人生成関数
# =========================================================

def generate_jobs(
    year,
    n_jobs,
    occupation_probs,
    start_counter,
):

    job_data = []


    for i in range(
        n_jobs
    ):

        job_id = (
            f"JOB{start_counter + i:05d}"
        )


        # ---------------------------------------------
        # 求人公開日
        # ---------------------------------------------

        open_date = (
            generate_open_date(
                year
            )
        )


        # ---------------------------------------------
        # クライアント
        # ---------------------------------------------

        client_id = rng.choice(
            clients[
                "client_id"
            ]
        )


        # ---------------------------------------------
        # RA担当者
        # ---------------------------------------------
        #
        # 実際のopen_date時点で
        # 在籍しているRAから選ぶ。
        # ---------------------------------------------

        ra_id = (
            select_active_ra(
                open_date
            )
        )


        # ---------------------------------------------
        # 職種
        # ---------------------------------------------

        occupation_id = rng.choice(
            occupation_ids,
            p=occupation_probs,
        )


        # ---------------------------------------------
        # 勤務地
        # ---------------------------------------------

        location_id = rng.choice(
            location_ids,
            p=location_probs,
        )


        # ---------------------------------------------
        # 募集枠数
        # ---------------------------------------------

        if year == 2025:

            required_slots = int(
                rng.choice(
                    slot_values,
                    p=(
                        slot_probs_2025
                    ),
                )
            )

        else:

            required_slots = int(
                rng.choice(
                    slot_values,
                    p=(
                        slot_probs_2026
                    ),
                )
            )


        # ---------------------------------------------
        # 必要スキルレベル
        # ---------------------------------------------

        required_skill_level = (
            generate_required_skill_level(
                occupation_id=(
                    occupation_id
                ),
                year=year,
            )
        )


        # ---------------------------------------------
        # 提示時給
        # ---------------------------------------------

        offered_hourly_wage = (
            generate_offered_hourly_wage(
                occupation_id=(
                    occupation_id
                ),
                required_skill_level=(
                    required_skill_level
                ),
                year=year,
            )
        )


        # ---------------------------------------------
        # 勤務形態
        # ---------------------------------------------

        work_style = rng.choice(
            work_styles,
            p=work_style_probs,
        )


        # ---------------------------------------------
        # 求人終了日・状態
        # ---------------------------------------------

        (
            close_date,
            status,
        ) = generate_close_information(
            open_date
        )


        # ---------------------------------------------
        # レコード追加
        # ---------------------------------------------

        job_data.append(
            [
                job_id,
                client_id,
                ra_id,
                open_date,
                close_date,
                occupation_id,
                location_id,
                required_slots,
                offered_hourly_wage,
                required_skill_level,
                work_style,
                status,
            ]
        )


    return job_data


# =========================================================
# 2025年・2026年求人生成
# =========================================================

jobs_2025 = generate_jobs(
    year=2025,
    n_jobs=N_JOBS_2025,
    occupation_probs=(
        occupation_probs_2025
    ),
    start_counter=1,
)


jobs_2026 = generate_jobs(
    year=2026,
    n_jobs=N_JOBS_2026,
    occupation_probs=(
        occupation_probs_2026
    ),
    start_counter=(
        N_JOBS_2025
        + 1
    ),
)


# =========================================================
# DataFrame化
# =========================================================

jobs = pd.DataFrame(
    (
        jobs_2025
        +
        jobs_2026
    ),
    columns=[
        "job_id",
        "client_id",
        "ra_id",
        "open_date",
        "close_date",
        "occupation_id",
        "location_id",
        "required_slots",
        "offered_hourly_wage",
        "required_skill_level",
        "work_style",
        "status",
    ],
)


# =========================================================
# データ品質チェック
# =========================================================

# ---------------------------------------------------------
# ID
# ---------------------------------------------------------

assert jobs[
    "job_id"
].is_unique


assert len(
    jobs
) == (
    N_JOBS_2025
    +
    N_JOBS_2026
)


# ---------------------------------------------------------
# 外部キー
# ---------------------------------------------------------

assert jobs[
    "client_id"
].isin(
    clients[
        "client_id"
    ]
).all()


assert jobs[
    "ra_id"
].isin(
    recruiters[
        "recruiter_id"
    ]
).all()


assert jobs[
    "occupation_id"
].isin(
    occupations[
        "occupation_id"
    ]
).all()


assert jobs[
    "location_id"
].isin(
    locations[
        "location_id"
    ]
).all()


# ---------------------------------------------------------
# 数値
# ---------------------------------------------------------

assert jobs[
    "required_slots"
].ge(
    1
).all()


assert jobs[
    "offered_hourly_wage"
].gt(
    0
).all()


assert jobs[
    "required_skill_level"
].between(
    1,
    5,
).all()


# ---------------------------------------------------------
# カテゴリ
# ---------------------------------------------------------

assert jobs[
    "work_style"
].isin(
    work_styles
).all()


assert jobs[
    "status"
].isin(
    [
        "open",
        "closed",
    ]
).all()


# =========================================================
# 求人公開期間品質チェック
# =========================================================

closed_jobs = jobs[
    jobs[
        "close_date"
    ].notna()
]


# closeはopenより後
assert (
    closed_jobs[
        "close_date"
    ]
    >
    closed_jobs[
        "open_date"
    ]
).all()


# closedならclose_date必須
assert jobs.loc[
    jobs[
        "status"
    ]
    ==
    "closed",
    "close_date",
].notna().all()


# openならclose_date NULL
assert jobs.loc[
    jobs[
        "status"
    ]
    ==
    "open",
    "close_date",
].isna().all()


# 観察期間終了日を超える
# close_dateを持たない
assert (
    closed_jobs[
        "close_date"
    ]
    <=
    DATA_END_DATE
).all()


# =========================================================
# 修正① 年度・公開期間の品質チェック
# =========================================================

jobs_check = jobs.copy()


jobs_check[
    "year"
] = (
    jobs_check[
        "open_date"
    ].dt.year
)


assert (
    jobs_check[
        "year"
    ].value_counts()[
        2025
    ]
    ==
    N_JOBS_2025
)


assert (
    jobs_check[
        "year"
    ].value_counts()[
        2026
    ]
    ==
    N_JOBS_2026
)


# 2025求人は4～12月
assert (
    jobs.loc[
        jobs[
            "open_date"
        ].dt.year
        ==
        2025,
        "open_date",
    ]
    >=
    pd.Timestamp(
        "2025-04-01"
    )
).all()


assert (
    jobs.loc[
        jobs[
            "open_date"
        ].dt.year
        ==
        2025,
        "open_date",
    ]
    <=
    pd.Timestamp(
        "2025-12-31"
    )
).all()


# 2026求人は1～9月
assert (
    jobs.loc[
        jobs[
            "open_date"
        ].dt.year
        ==
        2026,
        "open_date",
    ]
    >=
    pd.Timestamp(
        "2026-01-01"
    )
).all()


assert (
    jobs.loc[
        jobs[
            "open_date"
        ].dt.year
        ==
        2026,
        "open_date",
    ]
    <=
    pd.Timestamp(
        "2026-09-30"
    )
).all()


# =========================================================
# 修正③ RA在籍期間との整合性
# =========================================================

ra_check = (
    jobs.merge(
        recruiters[
            [
                "recruiter_id",
                "role_type",
                "join_date",
                "leave_date",
            ]
        ],
        left_on="ra_id",
        right_on="recruiter_id",
        how="left",
    )
)


# RA以外が割り当てられていない
assert (
    ra_check[
        "role_type"
    ]
    ==
    "RA"
).all()


# 求人公開日時点で着任済み
assert (
    ra_check[
        "open_date"
    ]
    >=
    ra_check[
        "join_date"
    ]
).all()


# 離任済みなら、
# 求人公開日は離任日以前
left_ra_check = (
    ra_check[
        ra_check[
            "leave_date"
        ].notna()
    ]
)


assert (
    left_ra_check[
        "open_date"
    ]
    <=
    left_ra_check[
        "leave_date"
    ]
).all()


# =========================================================
# 求人公開日数（確認用）
# =========================================================

jobs_check[
    "open_days"
] = (
    jobs_check[
        "close_date"
    ]
    -
    jobs_check[
        "open_date"
    ]
).dt.days


# =========================================================
# 60日観察可能フラグ（確認用）
# =========================================================
#
# SQLマートでも作成するが、
# 生成段階でも件数を確認できるようにする。
#
# close_dateではなく、
#
# open_date + 60日
# <= DATA_END_DATE
#
# で判定する。
#
# 求人が早期closeしていても、
# 公開後60日時点までデータ期間が存在すれば
# 60日観察可能とする。
# =========================================================

jobs_check[
    "job_60d_observed_flag"
] = (
    (
        jobs_check[
            "open_date"
        ]
        +
        pd.Timedelta(
            days=60
        )
    )
    <=
    DATA_END_DATE
).astype(
    int
)


# =========================================================
# CSV出力
# =========================================================
#
# 【変更前】
#
# jobs_test.csv
#
#
# 【修正仕様】
#
# jobs.csv
#
# 分析用正式データとして出力する。
# =========================================================

jobs.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig",
)


# =========================================================
# 内容確認
# =========================================================
#
# 【変更前】
#
# 20件のみだったため
# 全求人をprintしていた。
#
#
# 【問題点】
#
# 800件では全件表示は確認しづらい。
#
#
# 【修正仕様】
#
# 件数・分布・統計量と、
# 一部サンプルのみ表示する。
# =========================================================

print(
    "分析用求人データを生成しました。"
)

print()

print(
    f"求人総数: "
    f"{len(jobs):,}"
)


# =========================================================
# H1確認
# =========================================================

print()
print(
    "【年度別求人件数】"
)

print(
    jobs_check[
        "year"
    ]
    .value_counts()
    .sort_index()
)


job_growth_rate = (
    N_JOBS_2026
    /
    N_JOBS_2025
    -
    1
)


print()
print(
    "【求人件数増加率】"
)

print(
    f"2025 → 2026: "
    f"{job_growth_rate:.1%}"
)


print()
print(
    "【年度別募集枠】"
)

print(
    jobs_check
    .groupby(
        "year"
    )
    .agg(
        job_count=(
            "job_id",
            "count",
        ),
        total_slots=(
            "required_slots",
            "sum",
        ),
        avg_slots=(
            "required_slots",
            "mean",
        ),
    )
)


# =========================================================
# 月別求人件数
# =========================================================

jobs_check[
    "open_month"
] = (
    jobs_check[
        "open_date"
    ].dt.to_period(
        "M"
    )
)


print()
print(
    "【月別求人件数】"
)

print(
    jobs_check[
        "open_month"
    ]
    .value_counts()
    .sort_index()
)


# =========================================================
# H2確認
# =========================================================

print()
print(
    "【年度別提示時給】"
)

print(
    jobs_check
    .groupby(
        "year"
    )[
        "offered_hourly_wage"
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


# =========================================================
# H3確認
# =========================================================

print()
print(
    "【年度別必要スキルレベル】"
)

print(
    jobs_check
    .groupby(
        "year"
    )[
        "required_skill_level"
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
    "【年度×必要スキルレベル】"
)

print(
    pd.crosstab(
        jobs_check[
            "year"
        ],
        jobs_check[
            "required_skill_level"
        ],
    )
)


# =========================================================
# H4確認
# =========================================================

print()
print(
    "【年度×職種件数】"
)

print(
    pd.crosstab(
        jobs_check[
            "year"
        ],
        jobs_check[
            "occupation_id"
        ],
    )
)


print()
print(
    "【年度×職種構成比】"
)

print(
    pd.crosstab(
        jobs_check[
            "year"
        ],
        jobs_check[
            "occupation_id"
        ],
        normalize="index",
    )
)


# 職種グループを追加して確認
jobs_occupation_check = (
    jobs_check.merge(
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


print()
print(
    "【年度×職種グループ件数】"
)

print(
    pd.crosstab(
        jobs_occupation_check[
            "year"
        ],
        jobs_occupation_check[
            "occupation_group"
        ],
    )
)


print()
print(
    "【年度×職種グループ構成比】"
)

print(
    pd.crosstab(
        jobs_occupation_check[
            "year"
        ],
        jobs_occupation_check[
            "occupation_group"
        ],
        normalize="index",
    )
)


# =========================================================
# H6確認
# =========================================================

print()
print(
    "【年度×勤務形態】"
)

print(
    pd.crosstab(
        jobs_check[
            "year"
        ],
        jobs_check[
            "work_style"
        ],
    )
)


# =========================================================
# 求人状態確認
# =========================================================

print()
print(
    "【年度×求人ステータス】"
)

print(
    pd.crosstab(
        jobs_check[
            "year"
        ],
        jobs_check[
            "status"
        ],
    )
)


print()
print(
    "【60日観察可能求人件数】"
)

print(
    pd.crosstab(
        jobs_check[
            "year"
        ],
        jobs_check[
            "job_60d_observed_flag"
        ],
    )
)


print()
print(
    "【終了済み求人の公開期間】"
)

print(
    jobs_check.loc[
        jobs_check[
            "close_date"
        ].notna(),
        "open_days",
    ].describe()
)


# =========================================================
# RA負荷確認用
# =========================================================

print()
print(
    "【RA担当求人件数】"
)

print(
    jobs[
        "ra_id"
    ]
    .value_counts()
    .sort_index()
)


# =========================================================
# サンプル表示
# =========================================================

print()
print(
    "【求人サンプル：先頭20件】"
)

print(
    jobs.sort_values(
        "open_date"
    ).head(
        20
    )
)