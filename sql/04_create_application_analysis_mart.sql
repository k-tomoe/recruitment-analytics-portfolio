-- =========================================================
-- 応募案件分析マート
-- mart_application_analysis
-- =========================================================
-- 【このマートの粒度】
-- 1行 = 1application
--
-- applicationsテーブルを基準として、
-- ・応募案件の基本情報
-- ・給与ミスマッチ
-- ・スキルミスマッチ
-- ・企業推薦
-- ・辞退
-- ・職場見学
-- ・placement
-- ・主要な選考リードタイム
-- を1行へまとめる。
--
-- 【主な用途】
-- ・応募案件単位の選考状況の確認
-- ・給与条件のミスマッチ分析
-- ・経験・スキルのミスマッチ分析
-- ・推薦 / 辞退 / 職場見学 / placementの状況確認
-- ・主要な選考工程のリードタイム分析
--
-- 【重要】
-- mart_job_analysis
--     1行 = 1求人
--
-- mart_application_analysis
--     1行 = 1応募案件
--
-- 求人全体の活動量・充足率はjob mart、
-- 候補者 × 求人のマッチングや選考結果は
-- application martで分析する。
-- =========================================================


-- =========================================================
-- 既存VIEW削除
-- =========================================================
-- CREATE VIEWを再実行できるように、
-- 同名VIEWが存在する場合は先に削除する。
-- 元テーブルのデータを削除する処理ではない。
-- =========================================================

DROP VIEW IF EXISTS mart_application_analysis;


-- =========================================================
-- VIEW作成
-- =========================================================

CREATE VIEW mart_application_analysis AS


-- =========================================================
-- CTE① 候補者の職種別スキル
-- candidate_skill
-- =========================================================
-- candidate_experiencesは、
-- 1候補者 × 1職種について
-- 複数の職歴を持つ可能性がある。
--
-- そのままapplicationsへJOINすると、
-- 1applicationが複数行へ増える可能性があるため、
-- candidate_id × occupation_idごとに集約する。
--
-- 今回は、
-- 「その候補者がその職種で持つ最大skill_level」
-- を代表値として使用する。
-- =========================================================

WITH candidate_skill AS (

    SELECT
        candidate_id,
        occupation_id,
        MAX(
            skill_level
        ) AS candidate_skill_level

    FROM candidate_experiences

    GROUP BY
        candidate_id,
        occupation_id
),


-- =========================================================
-- CTE② application時点の希望給与
-- application_preference
-- =========================================================
-- candidate_preferencesは、
-- 候補者1人につき複数レコードを持つ可能性がある。
--
-- application分析では現在の希望条件ではなく、
-- intent_confirmed_date時点で有効だった
-- 希望給与を使用する。
--
-- 有効期間が重複している場合でも
-- 1applicationが複数行にならないよう、
-- effective_fromが最も新しい1件を取得する。
-- =========================================================

application_preference AS (

    SELECT
        a.application_id,
        cp.desired_hourly_wage

    FROM applications a

    LEFT JOIN candidate_preferences cp
        ON cp.candidate_preference_id = (

            SELECT
                cp2.candidate_preference_id

            FROM candidate_preferences cp2

            WHERE
                cp2.candidate_id
                =
                a.candidate_id

                AND

                cp2.effective_from
                <=
                a.intent_confirmed_date

                AND (
                    cp2.effective_to IS NULL
                    OR
                    a.intent_confirmed_date
                    <=
                    cp2.effective_to
                )

            ORDER BY
                cp2.effective_from DESC,
                cp2.candidate_preference_id DESC

            LIMIT 1
        )
),


-- =========================================================
-- CTE③ 職場見学集計
-- visit_agg
-- =========================================================
-- 現在の生成仕様では
-- 1applicationにつき職場見学は最大1件。
--
-- 将来的に複数回見学となった場合でも
-- マート粒度を1applicationに保てるよう、
-- application単位へ集約してからJOINする。
-- =========================================================

visit_agg AS (

    SELECT
        application_id,

        -- ---------------------------------------------
        -- 最初の職場見学設定日
        -- ---------------------------------------------

        MIN(
            scheduled_date
        ) AS first_scheduled_date,


        -- ---------------------------------------------
        -- 実際に実施された最初の職場見学日
        -- ---------------------------------------------

        MIN(
            CASE
                WHEN visit_status = 'completed'
                THEN visit_date
            END
        ) AS first_visit_date,


        -- ---------------------------------------------
        -- 職場見学完了フラグ
        -- ---------------------------------------------

        MAX(
            CASE
                WHEN visit_status = 'completed'
                THEN 1
                ELSE 0
            END
        ) AS visit_completed_flag


    FROM workplace_visits

    GROUP BY
        application_id
),


-- =========================================================
-- CTE④ placement集計
-- placement_agg
-- =========================================================
-- 現在は1applicationにつきplacement最大1件だが、
-- マート粒度を1applicationへ保つため、
-- application単位へ集約する。
-- =========================================================

placement_agg AS (

    SELECT
        application_id,

        -- ---------------------------------------------
        -- 最終就業決定日
        -- ---------------------------------------------

        MIN(
            decision_date
        ) AS decision_date,


        -- ---------------------------------------------
        -- placementしたことを表すフラグ
        -- ---------------------------------------------

        1 AS placed_flag


    FROM placements

    GROUP BY
        application_id
)


-- =========================================================
-- 最終SELECT
-- =========================================================

SELECT

    -- =====================================================
    -- 1. application基本情報
    -- =====================================================

    a.application_id,

    a.job_id,

    a.application_source,

    a.withdrawal_stage,

    a.status AS application_status,


    -- ---------------------------------------------
    -- application年
    -- ---------------------------------------------

    strftime(
        '%Y',
        a.intent_confirmed_date
    ) AS application_year,


    -- ---------------------------------------------
    -- application年月
    -- ---------------------------------------------
    -- 月次・分析対象期間の抽出に利用する。
    --
    -- 例：
    -- 2025-04
    -- ---------------------------------------------

    strftime(
        '%Y-%m',
        a.intent_confirmed_date
    ) AS application_month,


    -- =====================================================
    -- 2. 30日観察可能フラグ
    -- =====================================================
    -- intent_confirmed_dateから30日後までを
    -- DATA_END_DATE内で観察可能か判定する。
    --
    -- 1 = 30日間観察可能
    -- 0 = 右打ち切り
    --
    -- この30日は、
    -- 「30日以内にplacementすべき」
    -- という意味ではなく、
    -- application間で観察期間を揃えるための
    -- 分析上の観察窓。
    -- =====================================================

    CASE
        WHEN
            date(
                a.intent_confirmed_date,
                '+30 day'
            )
            <=
            date(
                '2026-09-30'
            )
        THEN 1
        ELSE 0
    END AS application_30d_observed_flag,


    -- =====================================================
    -- 3. 給与ミスマッチ
    -- =====================================================


    -- ---------------------------------------------
    -- wage_gap
    -- ---------------------------------------------
    -- 定義：
    -- 求人提示時給 - 候補者希望時給
    --
    -- 正：
    -- 提示時給 >= 希望時給
    --
    -- 負：
    -- 提示時給 < 希望時給
    -- ---------------------------------------------

    CASE
        WHEN ap.desired_hourly_wage IS NOT NULL
        THEN
            j.offered_hourly_wage
            -
            ap.desired_hourly_wage
        ELSE NULL
    END AS wage_gap,


    -- ---------------------------------------------
    -- wage_gap_rate
    -- ---------------------------------------------
    -- 定義：
    --
    -- 求人提示時給 - 希望時給
    -- --------------------------
    -- 希望時給
    --
    -- 例：
    -- 希望2000円
    -- 提示1800円
    --
    -- → -0.100
    -- ---------------------------------------------

    CASE
        WHEN
            ap.desired_hourly_wage IS NOT NULL
            AND
            ap.desired_hourly_wage > 0

        THEN
            ROUND(
                1.0
                *
                (
                    j.offered_hourly_wage
                    -
                    ap.desired_hourly_wage
                )
                /
                ap.desired_hourly_wage,
                3
            )

        ELSE NULL
    END AS wage_gap_rate,


    -- ---------------------------------------------
    -- wage_shortfall_rate
    -- ---------------------------------------------
    -- 希望額に対して求人提示額が
    -- 何%不足しているかを正の数で表す。
    --
    -- 定義：
    --
    -- MAX(
    --     希望時給 - 提示時給,
    --     0
    -- )
    -- ------------------------
    -- 希望時給
    --
    -- 例：
    -- 希望2000円
    -- 提示1800円
    -- → 0.100
    --
    -- 希望1800円
    -- 提示2000円
    -- → 0.000
    -- ---------------------------------------------

    CASE
        WHEN
            ap.desired_hourly_wage IS NULL
            OR
            ap.desired_hourly_wage <= 0

        THEN NULL


        WHEN
            j.offered_hourly_wage
            >=
            ap.desired_hourly_wage

        THEN 0.0


        ELSE
            ROUND(
                1.0
                *
                (
                    ap.desired_hourly_wage
                    -
                    j.offered_hourly_wage
                )
                /
                ap.desired_hourly_wage,
                3
            )

    END AS wage_shortfall_rate,


    -- ---------------------------------------------
    -- 希望給与を満たしているか
    -- ---------------------------------------------
    -- 1 = 求人提示時給 >= 希望時給
    -- 0 = 求人提示時給 < 希望時給
    -- NULL = 希望時給不明
    -- ---------------------------------------------

    CASE
        WHEN ap.desired_hourly_wage IS NULL
        THEN NULL

        WHEN
            j.offered_hourly_wage
            >=
            ap.desired_hourly_wage
        THEN 1

        ELSE 0

    END AS wage_requirement_met_flag,


    -- =====================================================
    -- 4. スキル・経験ミスマッチ
    -- =====================================================


    -- ---------------------------------------------
    -- 同職種経験が存在するか
    -- ---------------------------------------------
    -- candidate_skill_levelがNULLの場合は
    -- 「skill不足」ではなく、
    -- 「同職種経験なし」として扱う。
    -- ---------------------------------------------

    CASE
        WHEN cs.candidate_skill_level IS NOT NULL
        THEN 1
        ELSE 0
    END AS same_occupation_experience_flag,


    -- ---------------------------------------------
    -- skill_gap
    -- ---------------------------------------------
    -- 定義：
    --
    -- candidate_skill_level
    -- -
    -- required_skill_level
    --
    -- 同職種経験がない場合はNULL。
    -- ---------------------------------------------

    CASE
        WHEN cs.candidate_skill_level IS NOT NULL

        THEN
            cs.candidate_skill_level
            -
            j.required_skill_level

        ELSE NULL

    END AS skill_gap,


    -- ---------------------------------------------
    -- skill_match_group
    -- ---------------------------------------------
    -- no_same_occ_exp
    --     同職種経験なし
    --
    -- gap_le_minus2
    --     required skillより2以上低い
    --
    -- gap_minus1
    --     required skillより1低い
    --
    -- gap_ge_0
    --     required skill以上
    -- ---------------------------------------------

    CASE
        WHEN cs.candidate_skill_level IS NULL
        THEN 'no_same_occ_exp'


        WHEN
            (
                cs.candidate_skill_level
                -
                j.required_skill_level
            ) <= -2

        THEN 'gap_le_minus2'


        WHEN
            (
                cs.candidate_skill_level
                -
                j.required_skill_level
            ) = -1

        THEN 'gap_minus1'


        ELSE 'gap_ge_0'

    END AS skill_match_group,


    -- =====================================================
    -- 5. 応募 → 推薦
    -- =====================================================


    -- ---------------------------------------------
    -- 応募意思確認 → 企業推薦までの日数
    -- ---------------------------------------------
    -- 実際に推薦された案件だけ値を持つ。
    --
    -- screened_outや推薦前辞退には
    -- 0日を入れずNULLとする。
    -- ---------------------------------------------

    CASE
        WHEN a.recommendation_date IS NOT NULL

        THEN
            ROUND(
                julianday(
                    a.recommendation_date
                )
                -
                julianday(
                    a.intent_confirmed_date
                ),
                1
            )

        ELSE NULL

    END AS intent_to_recommend_days,


    -- ---------------------------------------------
    -- 実際に企業推薦されたか
    -- ---------------------------------------------

    CASE
        WHEN a.recommendation_date IS NOT NULL
        THEN 1
        ELSE 0
    END AS recommended_flag,


    -- =====================================================
    -- 6. application状態
    -- =====================================================


    -- ---------------------------------------------
    -- CAスクリーニングで終了
    -- ---------------------------------------------

    CASE
        WHEN a.status = 'screened_out'
        THEN 1
        ELSE 0
    END AS screened_out_flag,


    -- ---------------------------------------------
    -- 観察期間終了時点で処理中
    -- ---------------------------------------------

    CASE
        WHEN a.status = 'confirmed'
        THEN 1
        ELSE 0
    END AS confirmed_flag,


    -- =====================================================
    -- 7. 辞退
    -- =====================================================


    -- ---------------------------------------------
    -- 何らかの辞退
    -- ---------------------------------------------

    CASE
        WHEN a.status = 'withdrawn'
        THEN 1
        ELSE 0
    END AS withdrawal_flag,


    -- ---------------------------------------------
    -- 分析対象となる選考途中辞退
    -- ---------------------------------------------
    -- 他求人での就業決定による
    -- accepted_other_jobを除いた辞退。
    --
    -- 給与条件や選考プロセスとの関係を
    -- 分析するときに使用する。
    -- ---------------------------------------------

    CASE
        WHEN
            a.status = 'withdrawn'
            AND (
                a.withdrawal_reason IS NULL
                OR
                a.withdrawal_reason
                <>
                'accepted_other_job'
            )

        THEN 1
        ELSE 0

    END AS process_withdrawal_flag,


    -- =====================================================
    -- 8. 職場見学
    -- =====================================================


    -- ---------------------------------------------
    -- 職場見学完了フラグ
    -- ---------------------------------------------

    COALESCE(
        v.visit_completed_flag,
        0
    ) AS visit_completed_flag,


    -- ---------------------------------------------
    -- 推薦 → 職場見学設定までの日数
    -- ---------------------------------------------

    CASE
        WHEN
            a.recommendation_date IS NOT NULL
            AND
            v.first_scheduled_date IS NOT NULL

        THEN
            ROUND(
                julianday(
                    v.first_scheduled_date
                )
                -
                julianday(
                    a.recommendation_date
                ),
                1
            )

        ELSE NULL

    END AS recommend_to_schedule_days,


    -- ---------------------------------------------
    -- 職場見学設定 → 実施までの日数
    -- ---------------------------------------------

    CASE
        WHEN
            v.first_scheduled_date IS NOT NULL
            AND
            v.first_visit_date IS NOT NULL

        THEN
            ROUND(
                julianday(
                    v.first_visit_date
                )
                -
                julianday(
                    v.first_scheduled_date
                ),
                1
            )

        ELSE NULL

    END AS schedule_to_visit_days,


    -- =====================================================
    -- 9. placement
    -- =====================================================


    -- ---------------------------------------------
    -- placementしたか
    -- ---------------------------------------------

    COALESCE(
        p.placed_flag,
        0
    ) AS placed_flag,


    -- ---------------------------------------------
    -- 応募意思確認 → placementまでの日数
    -- ---------------------------------------------
    -- placementしたapplicationのみ値を持つ。
    -- ---------------------------------------------

    CASE
        WHEN p.decision_date IS NOT NULL

        THEN
            ROUND(
                julianday(
                    p.decision_date
                )
                -
                julianday(
                    a.intent_confirmed_date
                ),
                1
            )

        ELSE NULL

    END AS intent_to_decision_days


-- =========================================================
-- 基準テーブル
-- =========================================================
-- applicationsがこのマートの基準。
--
-- applicationsに存在する案件を
-- 原則として1行ずつ残す。
-- =========================================================

FROM applications a


-- =========================================================
-- 求人
-- =========================================================
-- 給与ミスマッチ・skill_gapの計算に
-- 求人条件が必要なためJOINする。
--
-- applicationにjob_idは必須なので、
-- INNER JOINを使用する。
-- =========================================================

INNER JOIN jobs j
    ON
        a.job_id
        =
        j.job_id


-- =========================================================
-- application時点の希望給与
-- =========================================================

LEFT JOIN application_preference ap
    ON
        a.application_id
        =
        ap.application_id


-- =========================================================
-- 候補者スキル
-- =========================================================
-- 応募求人と同じoccupationの
-- candidate_skillのみ取得する。
-- =========================================================

LEFT JOIN candidate_skill cs
    ON
        a.candidate_id
        =
        cs.candidate_id

        AND

        j.occupation_id
        =
        cs.occupation_id


-- =========================================================
-- 職場見学
-- =========================================================

LEFT JOIN visit_agg v
    ON
        a.application_id
        =
        v.application_id


-- =========================================================
-- placement
-- =========================================================

LEFT JOIN placement_agg p
    ON
        a.application_id
        =
        p.application_id
;