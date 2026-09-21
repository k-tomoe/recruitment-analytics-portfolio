from pathlib import Path

import numpy as np
import pandas as pd


# =========================================================
# 基本設定
# =========================================================

OUTPUT_DIR = Path("data/raw")

rng = np.random.default_rng(48)

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

candidate_preferences = pd.read_csv(
    OUTPUT_DIR / "candidate_preferences_test.csv",
    parse_dates=[
        "effective_from",
        "effective_to",
    ],
)

candidate_activities = pd.read_csv(
    OUTPUT_DIR / "candidate_activities_test.csv",
    parse_dates=[
        "activity_date",
    ],
)

job_entries = pd.read_csv(
    OUTPUT_DIR / "job_entries_test.csv",
    parse_dates=[
        "entry_date",
    ],
)

job_introductions = pd.read_csv(
    OUTPUT_DIR / "job_introductions_test.csv"
)

jobs = pd.read_csv(
    OUTPUT_DIR / "jobs_test.csv",
    parse_dates=[
        "open_date",
        "close_date",
    ],
)

recruiters = pd.read_csv(
    OUTPUT_DIR / "recruiters.csv",
    parse_dates=[
        "join_date",
        "leave_date",
    ],
)


# =========================================================
# 指定日時点の希望条件を取得
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
# 求職者の職種別スキルを取得
# =========================================================

def get_candidate_skill(
    candidate_id,
    occupation_id,
):

    matching_rows = candidate_experiences[
        (
            candidate_experiences["candidate_id"]
            == candidate_id
        )
        &
        (
            candidate_experiences["occupation_id"]
            == occupation_id
        )
    ]

    if len(matching_rows) == 0:
        return None

    return int(
        matching_rows[
            "skill_level"
        ].max()
    )


# =========================================================
# 求職者の担当CAを取得
# =========================================================

def get_candidate_ca(
    candidate_id,
    target_date,
):

    candidate_row = candidates[
        candidates["candidate_id"]
        == candidate_id
    ].iloc[0]


    # ---------------------------------------------
    # candidatesに担当CAがある場合
    # ---------------------------------------------

    if pd.notna(
        candidate_row["ca_id"]
    ):

        return candidate_row["ca_id"]


    # ---------------------------------------------
    # 候補者対応履歴からCAを取得
    # ---------------------------------------------

    activities = candidate_activities[
        candidate_activities["candidate_id"]
        == candidate_id
    ].sort_values(
        "activity_date"
    )


    if len(activities) > 0:

        return activities.iloc[0][
            "ca_id"
        ]


    # ---------------------------------------------
    # 対応履歴もない場合、
    # その時点で稼働中のCAから割当
    # ---------------------------------------------

    active_ca = recruiters[
        (
            recruiters["role_type"]
            == "CA"
        )
        &
        (
            recruiters["join_date"]
            <= target_date
        )
        &
        (
            recruiters["leave_date"].isna()
            |
            (
                recruiters["leave_date"]
                >= target_date
            )
        )
    ]


    if len(active_ca) == 0:
        return None


    return rng.choice(
        active_ca["recruiter_id"]
    )


# =========================================================
# 修正① self_entryから応募案件へ進む確率
# =========================================================
#
# 【変更前】
# 求人サイトでエントリーした候補者について、
# スキルや同職種経験に関係なく、
# 一律70%の確率で応募意思確認済みの
# applicationへ移行させていた。
#
# 変更前コード：
#
# converts_to_application = (
#     rng.random() < 0.70
# )
#
#
# 【問題点】
# 初回EDAではself_entry 20件中15件で、
# 求人職種と同じ職種の経験を確認できなかった。
#
# 求人サイト上で候補者が興味を示すこと自体は
# 未経験職種でも十分発生し得る。
#
# 一方、CAが候補者と応募意思を確認し、
# 正式な応募案件として扱う段階では、
# 求人の要求スキルや候補者経験を確認するため、
# 専門性の高い求人について未経験者が
# 高確率でapplicationへ進む状態は不自然である。
#
#
# 【修正仕様】
# self_entryからapplicationへ進む確率を、
# 同職種経験とスキル適合度によって変更する。
#
# 同職種経験あり：
# ・要求スキル以上        → 80%
# ・1段階不足             → 65%
# ・2段階不足             → 40%
# ・3段階以上不足         → 20%
#
# 同職種経験なし：
# ・要求スキル1～2        → 45%
# ・要求スキル3以上       → 15%
#
# 未経験者のエントリー自体は禁止せず、
# applicationへの移行確率のみ下げる。
#
# ---------------------------------------------------------
# 変更後コード
# ---------------------------------------------------------

def get_self_entry_conversion_probability(
    candidate_id,
    job,
):

    required_skill_level = int(
        job["required_skill_level"]
    )

    candidate_skill = get_candidate_skill(
        candidate_id,
        job["occupation_id"],
    )


    # 同職種経験なし
    if candidate_skill is None:

        # 未経験でも比較的応募可能な求人
        if required_skill_level <= 2:
            return 0.45

        # 専門性の高い求人
        return 0.15


    # 同職種経験あり
    skill_gap = (
        candidate_skill
        - required_skill_level
    )


    if skill_gap >= 0:
        return 0.80

    elif skill_gap == -1:
        return 0.65

    elif skill_gap == -2:
        return 0.40

    else:
        return 0.20


# =========================================================
# 修正② CAが企業推薦へ進める確率
# =========================================================
#
# 【変更前】
# 同職種経験が存在しない候補者を、
# 内部的に
#
# skill_gap = -3
#
# として扱っていた。
#
# 【問題点】
# SQL分析マートでは、同職種経験がない場合は
# candidate_skill_level / skill_gap をNULLとしている。
#
# 一方、生成ロジック内部ではskill_gap=-3としていたため、
# 「実際にスキルが3段階不足しているケース」と
# 「同職種経験そのものが存在しないケース」が
# 同一視されていた。
#
#
# 【修正仕様】
# 同職種経験なしはskill_gapへ無理に数値化せず、
# candidate_skill is None として独立して扱う。
#
# 同職種経験がある場合のみskill_gapを計算する。
#
# ---------------------------------------------------------
# 変更後コード
# ---------------------------------------------------------

def get_recommendation_probability(
    candidate_skill,
    required_skill_level,
):

    # 同職種経験なし
    if candidate_skill is None:

        if required_skill_level <= 2:
            return 0.45

        return 0.10


    skill_gap = (
        candidate_skill
        - required_skill_level
    )


    if skill_gap >= 0:
        return 0.95

    elif skill_gap == -1:
        return 0.82

    elif skill_gap == -2:
        return 0.55

    else:
        return 0.35


# =========================================================
# 企業側の推薦通過確率
# =========================================================

def get_acceptance_probability(
    candidate_skill,
    required_skill_level,
):

    # 同職種経験なし
    if candidate_skill is None:

        if required_skill_level <= 2:
            return 0.40

        return 0.15


    skill_gap = (
        candidate_skill
        - required_skill_level
    )


    if skill_gap >= 0:
        return 0.82

    elif skill_gap == -1:
        return 0.62

    elif skill_gap == -2:
        return 0.38

    else:
        return 0.22


# =========================================================
# 応募候補を格納
# =========================================================

application_candidates = []


# =========================================================
# 1. 求人サイト経由
# =========================================================

for _, entry in job_entries.iterrows():

    candidate_id = entry[
        "candidate_id"
    ]

    job_id = entry[
        "job_id"
    ]

    entry_date = entry[
        "entry_date"
    ]


    # =====================================================
    # 修正①
    # スキル条件を考慮して応募案件化確率を決定
    # =====================================================

    job = jobs[
        jobs["job_id"]
        == job_id
    ].iloc[0]


    conversion_probability = (
        get_self_entry_conversion_probability(
            candidate_id,
            job,
        )
    )


    converts_to_application = (
        rng.random()
        < conversion_probability
    )


    if not converts_to_application:
        continue


    # ---------------------------------------------
    # 応募意思確認までの日数
    # ---------------------------------------------

    intent_delay = int(
        rng.integers(
            1,
            5,
        )
    )

    intent_confirmed_date = (
        entry_date
        + pd.Timedelta(
            days=intent_delay
        )
    )


    # ---------------------------------------------
    # 求職終了後なら応募案件にしない
    # ---------------------------------------------

    candidate_row = candidates[
        candidates["candidate_id"]
        == candidate_id
    ].iloc[0]


    if pd.notna(
        candidate_row[
            "search_end_date"
        ]
    ):

        if (
            intent_confirmed_date
            >
            candidate_row[
                "search_end_date"
            ]
        ):
            continue


    if (
        intent_confirmed_date
        > DATA_END_DATE
    ):
        continue


    ca_id = get_candidate_ca(
        candidate_id,
        intent_confirmed_date,
    )


    if ca_id is None:
        continue


    application_candidates.append(
        {
            "candidate_id":
                candidate_id,

            "job_id":
                job_id,

            "ca_id":
                ca_id,

            "application_source":
                "self_entry",

            "source_entry_id":
                entry["entry_id"],

            "source_introduction_id":
                None,

            "intent_confirmed_date":
                intent_confirmed_date,
        }
    )


# =========================================================
# 2. CA求人紹介経由
# =========================================================

introduction_source = (
    job_introductions.merge(
        candidate_activities[
            [
                "activity_id",
                "candidate_id",
                "activity_date",
                "ca_id",
            ]
        ],
        on="activity_id",
        how="left",
    )
)


# apply回答のみ応募案件候補
introduction_source = (
    introduction_source[
        introduction_source[
            "candidate_response"
        ]
        == "apply"
    ]
)


for _, introduction in (
    introduction_source.iterrows()
):

    candidate_id = introduction[
        "candidate_id"
    ]

    job_id = introduction[
        "job_id"
    ]


    # 紹介時点で応募意思がかなり明確なので
    # 当日～翌日に確認
    intent_delay = int(
        rng.integers(
            0,
            2,
        )
    )

    intent_confirmed_date = (
        introduction[
            "activity_date"
        ]
        + pd.Timedelta(
            days=intent_delay
        )
    )


    if (
        intent_confirmed_date
        > DATA_END_DATE
    ):
        continue


    application_candidates.append(
        {
            "candidate_id":
                candidate_id,

            "job_id":
                job_id,

            "ca_id":
                introduction[
                    "ca_id"
                ],

            "application_source":
                "ca_introduction",

            "source_entry_id":
                None,

            "source_introduction_id":
                introduction[
                    "introduction_id"
                ],

            "intent_confirmed_date":
                intent_confirmed_date,
        }
    )


# =========================================================
# DataFrame化
# =========================================================

application_candidates = pd.DataFrame(
    application_candidates
)


# =========================================================
# 同一 candidate × job の重複を除く
# =========================================================

if len(application_candidates) > 0:

    application_candidates = (
        application_candidates
        .sort_values(
            "intent_confirmed_date"
        )
        .drop_duplicates(
            subset=[
                "candidate_id",
                "job_id",
            ],
            keep="first",
        )
        .reset_index(
            drop=True
        )
    )


# =========================================================
# 応募案件詳細を生成
# =========================================================

application_data = []

used_entry_ids = []

application_counter = 1


for _, application in (
    application_candidates.iterrows()
):

    candidate_id = application[
        "candidate_id"
    ]

    job_id = application[
        "job_id"
    ]

    intent_confirmed_date = (
        application[
            "intent_confirmed_date"
        ]
    )


    # =====================================================
    # 求人情報
    # =====================================================

    job = jobs[
        jobs["job_id"]
        == job_id
    ].iloc[0]


    # =====================================================
    # 応募意思確認時点の希望条件
    # =====================================================

    preference = get_active_preference(
        candidate_id,
        intent_confirmed_date,
    )


    # 希望条件が取得できない場合は
    # 安全のため応募案件を作らない
    if preference is None:
        continue


    # =====================================================
    # 給与条件ギャップ
    # =====================================================

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


    # =====================================================
    # 修正② スキル情報
    # =====================================================
    #
    # 変更前：
    #
    # if candidate_skill is None:
    #     skill_gap = -3
    #
    # else:
    #     skill_gap = (
    #         candidate_skill
    #         - required_skill_level
    #     )
    #
    # 変更後：
    # 同職種経験がない場合はcandidate_skill=Noneのままとし、
    # skill_gapへ便宜的な数値を代入しない。

    required_skill_level = int(
        job[
            "required_skill_level"
        ]
    )

    candidate_skill = (
        get_candidate_skill(
            candidate_id,
            job[
                "occupation_id"
            ],
        )
    )


    if candidate_skill is None:

        skill_gap = None

    else:

        skill_gap = (
            candidate_skill
            - required_skill_level
        )


    # =====================================================
    # 推薦までの日数
    # 仮説5：2026年は長期化
    # =====================================================

    if (
        intent_confirmed_date.year
        == 2025
    ):

        recommendation_delay = int(
            rng.choice(
                [
                    0,
                    1,
                    2,
                    3,
                    4,
                ],
                p=[
                    0.15,
                    0.30,
                    0.30,
                    0.15,
                    0.10,
                ],
            )
        )

    else:

        recommendation_delay = int(
            rng.choice(
                [
                    1,
                    2,
                    3,
                    4,
                    5,
                    6,
                    7,
                ],
                p=[
                    0.08,
                    0.15,
                    0.20,
                    0.20,
                    0.15,
                    0.12,
                    0.10,
                ],
            )
        )


    planned_recommendation_date = (
        intent_confirmed_date
        + pd.Timedelta(
            days=recommendation_delay
        )
    )


    # =====================================================
    # 推薦前辞退確率
    # =====================================================

    withdrawal_probability = 0.05


    # 給与条件が悪いほど辞退しやすい
    if wage_gap_ratio < -0.15:
        withdrawal_probability += 0.20

    elif wage_gap_ratio < -0.10:
        withdrawal_probability += 0.12

    elif wage_gap_ratio < -0.05:
        withdrawal_probability += 0.05


    # 推薦に時間がかかるほど離脱しやすい
    if recommendation_delay >= 6:
        withdrawal_probability += 0.18

    elif recommendation_delay >= 4:
        withdrawal_probability += 0.10

    elif recommendation_delay >= 2:
        withdrawal_probability += 0.03


    withdrawal_probability = float(
        np.clip(
            withdrawal_probability,
            0,
            0.65,
        )
    )


    withdraws = (
        rng.random()
        < withdrawal_probability
    )


    # =====================================================
    # 推薦前辞退
    # =====================================================

    if withdraws:

        if recommendation_delay == 0:

            withdrawal_delay = 0

        else:

            withdrawal_delay = int(
                rng.integers(
                    0,
                    recommendation_delay + 1,
                )
            )


        withdrawal_date = (
            intent_confirmed_date
            + pd.Timedelta(
                days=withdrawal_delay
            )
        )


        # 主な辞退理由を設定
        if (
            wage_gap_ratio < -0.10
            and recommendation_delay >= 4
        ):

            withdrawal_reason = rng.choice(
                [
                    "wage",
                    "process_delay",
                ]
            )

        elif wage_gap_ratio < -0.10:

            withdrawal_reason = "wage"

        elif recommendation_delay >= 4:

            withdrawal_reason = (
                "process_delay"
            )

        else:

            withdrawal_reason = "other"


        recommendation_date = pd.NaT

        recommendation_result = None

        status = "withdrawn"


    # =====================================================
    # 辞退しなかった場合
    # =====================================================

    else:

        withdrawal_date = pd.NaT
        withdrawal_reason = None


        # =================================================
        # 修正③
        # CAが実際に企業推薦まで進める確率
        # =================================================

        recommendation_probability = (
            get_recommendation_probability(
                candidate_skill,
                required_skill_level,
            )
        )


        is_recommended = (
            rng.random()
            < recommendation_probability
        )


        # =================================================
        # 修正③ 推薦対象外
        # =================================================
        #
        # 【変更前】
        # CAが企業推薦まで進めないと判定した案件でも、
        #
        # status = "confirmed"
        #
        # のまま残していた。
        #
        # 【問題点】
        # 初回EDAでは28件中11件がconfirmedであり、
        #
        # ・CA判断による推薦見送り
        # ・本当に処理中の案件
        # ・データ期間末で観察できていない案件
        #
        # が区別できなかった。
        #
        #
        # 【修正仕様】
        # CAが推薦対象外と判断した案件は
        #
        # status = "screened_out"
        #
        # とする。
        #
        # 一方、推薦する予定だったものの
        # recommendation_dateがDATA_END_DATEを超える場合は、
        # 本当に観察途中であるため
        # status = "confirmed"
        # のまま残す。
        #
        # -------------------------------------------------

        if not is_recommended:

            recommendation_date = pd.NaT

            recommendation_result = None

            status = "screened_out"


        # ---------------------------------------------
        # 推薦された場合
        # ---------------------------------------------

        else:

            recommendation_date = (
                planned_recommendation_date
            )


            # データ観察終了後に推薦予定の場合
            if (
                recommendation_date
                > DATA_END_DATE
            ):

                recommendation_date = pd.NaT

                recommendation_result = None

                # 本当にまだ処理中なのでconfirmed
                status = "confirmed"


            else:

                # -------------------------------------
                # 企業側の推薦通過確率
                # -------------------------------------

                acceptance_probability = (
                    get_acceptance_probability(
                        candidate_skill,
                        required_skill_level,
                    )
                )


                recommendation_accepted = (
                    rng.random()
                    < acceptance_probability
                )


                if recommendation_accepted:

                    recommendation_result = (
                        "accepted"
                    )

                    status = "recommended"

                else:

                    recommendation_result = (
                        "rejected"
                    )

                    status = "rejected"


    # =====================================================
    # Application ID
    # =====================================================

    application_id = (
        f"APP{application_counter:05d}"
    )


    application_data.append(
        [
            application_id,
            job_id,
            candidate_id,
            application[
                "ca_id"
            ],
            application[
                "application_source"
            ],
            application[
                "source_entry_id"
            ],
            application[
                "source_introduction_id"
            ],
            intent_confirmed_date,
            recommendation_date,
            recommendation_result,
            withdrawal_date,
            withdrawal_reason,
            status,
        ]
    )


    if pd.notna(
        application[
            "source_entry_id"
        ]
    ):

        used_entry_ids.append(
            application[
                "source_entry_id"
            ]
        )


    application_counter += 1


# =========================================================
# DataFrame化
# =========================================================

applications = pd.DataFrame(
    application_data,
    columns=[
        "application_id",
        "job_id",
        "candidate_id",
        "ca_id",
        "application_source",
        "source_entry_id",
        "source_introduction_id",
        "intent_confirmed_date",
        "recommendation_date",
        "recommendation_result",
        "withdrawal_date",
        "withdrawal_reason",
        "status",
    ],
)


# =========================================================
# データ品質チェック
# =========================================================

assert applications[
    "application_id"
].is_unique


assert not applications.duplicated(
    subset=[
        "candidate_id",
        "job_id",
    ]
).any()


assert applications[
    "job_id"
].isin(
    jobs["job_id"]
).all()


assert applications[
    "candidate_id"
].isin(
    candidates[
        "candidate_id"
    ]
).all()


# CAのみが担当
ca_master = recruiters[
    recruiters[
        "role_type"
    ]
    == "CA"
]

assert applications[
    "ca_id"
].isin(
    ca_master[
        "recruiter_id"
    ]
).all()


# =========================================================
# 修正③ ステータス品質チェック
# =========================================================

assert applications[
    "status"
].isin(
    [
        "confirmed",
        "screened_out",
        "withdrawn",
        "recommended",
        "rejected",
    ]
).all()


# screened_outでは
# 推薦日・推薦結果・辞退日は存在しない
screened_out_rows = applications[
    applications[
        "status"
    ]
    == "screened_out"
]

assert screened_out_rows[
    "recommendation_date"
].isna().all()

assert screened_out_rows[
    "recommendation_result"
].isna().all()

assert screened_out_rows[
    "withdrawal_date"
].isna().all()


# confirmedは本当に観察途中の案件なので、
# 推薦日・推薦結果・辞退日はまだ存在しない
confirmed_rows = applications[
    applications[
        "status"
    ]
    == "confirmed"
]

assert confirmed_rows[
    "recommendation_date"
].isna().all()

assert confirmed_rows[
    "recommendation_result"
].isna().all()

assert confirmed_rows[
    "withdrawal_date"
].isna().all()


# withdrawnでは辞退日が必要
withdrawn_status_rows = applications[
    applications[
        "status"
    ]
    == "withdrawn"
]

assert withdrawn_status_rows[
    "withdrawal_date"
].notna().all()

assert withdrawn_status_rows[
    "recommendation_date"
].isna().all()


# recommendedでは推薦結果accepted
recommended_status_rows = applications[
    applications[
        "status"
    ]
    == "recommended"
]

assert (
    recommended_status_rows[
        "recommendation_result"
    ]
    == "accepted"
).all()


# rejectedでは推薦結果rejected
rejected_status_rows = applications[
    applications[
        "status"
    ]
    == "rejected"
]

assert (
    rejected_status_rows[
        "recommendation_result"
    ]
    == "rejected"
).all()


# =========================================================
# 応募経路とSource IDの整合性
# =========================================================

self_entry_rows = applications[
    applications[
        "application_source"
    ]
    == "self_entry"
]

assert self_entry_rows[
    "source_entry_id"
].notna().all()

assert self_entry_rows[
    "source_introduction_id"
].isna().all()


introduction_rows = applications[
    applications[
        "application_source"
    ]
    == "ca_introduction"
]

assert introduction_rows[
    "source_entry_id"
].isna().all()

assert introduction_rows[
    "source_introduction_id"
].notna().all()


# =========================================================
# 日付整合性
# =========================================================

recommended_rows = applications[
    applications[
        "recommendation_date"
    ].notna()
]

assert (
    recommended_rows[
        "recommendation_date"
    ]
    >=
    recommended_rows[
        "intent_confirmed_date"
    ]
).all()


withdrawn_rows = applications[
    applications[
        "withdrawal_date"
    ].notna()
]

assert (
    withdrawn_rows[
        "withdrawal_date"
    ]
    >=
    withdrawn_rows[
        "intent_confirmed_date"
    ]
).all()


# 応募意思確認日は観察終了日以前
assert (
    applications[
        "intent_confirmed_date"
    ]
    <= DATA_END_DATE
).all()


# =========================================================
# job_entriesのステータス更新
# =========================================================

job_entries["status"] = np.where(
    job_entries[
        "entry_id"
    ].isin(
        used_entry_ids
    ),
    "converted",
    "declined",
)


# =========================================================
# CSV出力
# =========================================================

applications.to_csv(
    OUTPUT_DIR
    / "applications_test.csv",
    index=False,
    encoding="utf-8-sig",
)


# job_entriesも更新
job_entries.to_csv(
    OUTPUT_DIR
    / "job_entries_test.csv",
    index=False,
    encoding="utf-8-sig",
)


# =========================================================
# 内容確認
# =========================================================

print(applications)

print()
print(
    "応募案件テストデータを生成しました。"
)

print(
    f"件数: {len(applications)}"
)


print()
print("応募経路別件数")

print(
    applications[
        "application_source"
    ].value_counts()
)


print()
print("応募案件ステータス")

print(
    applications[
        "status"
    ].value_counts(
        dropna=False
    )
)


print()
print("推薦結果")

print(
    applications[
        "recommendation_result"
    ].value_counts(
        dropna=False
    )
)


print()
print("求人エントリーの更新後ステータス")

print(
    job_entries[
        "status"
    ].value_counts()
)


# =========================================================
# 修正内容の確認
# =========================================================

print()
print(
    "self_entry件数 / "
    "CA紹介件数"
)

print(
    applications[
        "application_source"
    ].value_counts()
)


print()
print(
    "screened_out件数"
)

print(
    (
        applications[
            "status"
        ]
        == "screened_out"
    ).sum()
)


print()
print(
    "confirmed件数"
)

print(
    (
        applications[
            "status"
        ]
        == "confirmed"
    ).sum()
)


# =========================================================
# 同職種経験有無 × 応募経路を確認
# ※ CSVには追加せず、確認用のみ
# =========================================================

application_skill_check = []


for _, row in applications.iterrows():

    job = jobs[
        jobs["job_id"]
        == row["job_id"]
    ].iloc[0]

    candidate_skill = (
        get_candidate_skill(
            row["candidate_id"],
            job["occupation_id"],
        )
    )

    application_skill_check.append(
        {
            "application_id":
                row["application_id"],

            "application_source":
                row["application_source"],

            "status":
                row["status"],

            "required_skill_level":
                int(
                    job[
                        "required_skill_level"
                    ]
                ),

            "same_occupation_experience":
                candidate_skill
                is not None,

            "candidate_skill_level":
                candidate_skill,
        }
    )


application_skill_check = pd.DataFrame(
    application_skill_check
)


print()
print(
    "応募経路 × 同職種経験有無"
)

print(
    pd.crosstab(
        application_skill_check[
            "application_source"
        ],
        application_skill_check[
            "same_occupation_experience"
        ],
        dropna=False,
    )
)


print()
print(
    "応募案件のスキル確認"
)

print(
    application_skill_check.sort_values(
        [
            "application_source",
            "required_skill_level",
        ]
    )
)