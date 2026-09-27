-- =========================================================
-- 応募案件分析マート
-- mart_application_analysis
-- =========================================================
-- 【このマートの粒度】
-- 1行 = 1application　applicationsテーブルを基準として、
-- ・求人条件
-- ・候補者希望条件
-- ・給与ミスマッチ
-- ・スキルミスマッチ
-- ・企業推薦
-- ・辞退
-- ・職場見学
-- ・placement
-- ・各工程のリードタイム
-- を1行へまとめる。
--
-- 【主な用途】
-- H2：
-- 給与ミスマッチと
-- 推薦・辞退・placementの関係
--
-- H3：
-- スキルミスマッチと
-- 推薦・職場見学・placementの関係
--
-- H5：
-- 選考リードタイムと
-- 各段階の辞退との関係
--
-- H6：
-- work_styleと選考結果の関係
--
-- 【重要】
-- mart_job_analysis
--     1行 = 1求人
--
-- mart_application_analysis
--     1行 = 1応募案件
--
-- と粒度が異なる。
--
-- 求人全体の充足率を見る場合はjob mart、候補者×求人のマッチングを見る場合はapplication martを使用する。
-- =========================================================

-- =========================================================
-- 既存VIEW削除
-- =========================================================
-- SQLを何度でも再実行できるように、
-- 同名VIEWが存在する場合は先に削除する。
-- rawテーブルを削除する処理ではない。
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
-- 1候補者 × 1職種
-- について複数の職歴を持つ可能性がある。
--
-- そのままapplicationsへJOINすると、
-- 1applicationが複数行へ増えてしまう。
--
-- そこで、
-- candidate_id
-- occupation_id
-- ごとにMAX(skill_level)を取得し、　1候補者 × 1職種 = 1行　へ集約する。
--
-- 今回は「その候補者がその職種で持っている最大スキルレベル」を代表値として使用する。
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
-- CTE② application時点の希望条件
-- application_preference
-- =========================================================
-- candidate_preferencesは、候補者1人につき複数レコードを持つ可能性がある。
--
-- 例えば、
-- 登録時希望条件
-- ↓
-- 求職途中で希望条件更新
-- というケース。
--
-- 【重要】
-- applicationの分析では、「現在の希望条件」ではなく、
-- intent_confirmed_date時点で有効だった希望条件を使用する。
--
-- さらに、万一有効期間が重複していても、1applicationが複数行にならないように、
-- effective_fromが最も新しい1件のみ取得する。
--
-- これによって、mart_application_analysis　1行 = 1application の粒度を保証しやすくする。
-- =========================================================

application_preference AS (
    SELECT
        a.application_id,
        cp.candidate_preference_id,
        cp.preferred_occupation_id,
        cp.preferred_location_id,
        cp.desired_hourly_wage,
        cp.preferred_work_style
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
--
-- 現在の生成仕様では　1applicationにつき職場見学は最大1件。
--　ただし、将来的に複数回見学へ拡張してもマート粒度を壊さないよう、
-- application単位へ集約してからJOINする。
-- =========================================================

visit_agg AS (
    SELECT
        application_id,
        -- ---------------------------------------------
        -- 職場見学レコード数
        -- ---------------------------------------------
        COUNT(*) AS visit_count,
        -- ---------------------------------------------
        -- 最初の職場見学設定日
        -- ---------------------------------------------
        MIN(
            scheduled_date
        ) AS first_scheduled_date,
        -- ---------------------------------------------
        -- 実際に実施された最初の職場見学日
        -- ---------------------------------------------
        -- scheduled / cancelledの場合は
        -- visit_dateがNULLなので対象外。
        -- ---------------------------------------------
        MIN(
            CASE
                WHEN visit_status = 'completed'
                THEN visit_date
            END
        ) AS first_visit_date,

        -- ---------------------------------------------
        -- 見学設定済みフラグ
        -- ---------------------------------------------
        MAX(
            CASE
                WHEN scheduled_date IS NOT NULL
                THEN 1
                ELSE 0
            END
        ) AS visit_scheduled_flag,
        -- ---------------------------------------------
        -- 見学完了フラグ
        -- ---------------------------------------------
        MAX(
            CASE
                WHEN visit_status = 'completed'
                THEN 1
                ELSE 0
            END
        ) AS visit_completed_flag,
        -- ---------------------------------------------
        -- 見学キャンセルフラグ
        -- ---------------------------------------------
        MAX(
            CASE
                WHEN visit_status = 'cancelled'
                THEN 1
                ELSE 0
            END
        ) AS visit_cancelled_flag,
        -- ---------------------------------------------
        -- 見学後、次工程へ進んだフラグ
        -- ---------------------------------------------
        MAX(
            CASE
                WHEN
                    visit_status = 'completed'
                    AND result = 'continue'
                THEN 1
                ELSE 0
            END
        ) AS visit_continue_flag
    FROM workplace_visits
    GROUP BY
        application_id
),

-- =========================================================
-- CTE④ placement集計
-- placement_agg
-- =========================================================
--
-- 現在は　1applicationにつきplacement最大1件　だが、
-- マート粒度を確実に1applicationへ保つため、application単位へ集約する。
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
        -- 就業開始予定日
        -- ---------------------------------------------
        MIN(
            start_date
        ) AS start_date,
        -- ---------------------------------------------
        -- 最終合意時給
        -- ---------------------------------------------
        MAX(
            agreed_hourly_wage
        ) AS agreed_hourly_wage,
        -- ---------------------------------------------
        -- placementの状態
        -- ---------------------------------------------
        -- started　/　planned　のいずれか。
        -- ---------------------------------------------
        MAX(
            status
        ) AS placement_status,
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
    a.candidate_id,
    a.ca_id,
    -- ---------------------------------------------
    -- 応募経路
    -- ---------------------------------------------
    -- self_entry
    -- ca_introduction
    -- ---------------------------------------------
    a.application_source,
    -- self_entryの場合に使用
    a.source_entry_id,
    -- ca_introductionの場合に使用
    a.source_introduction_id,
    -- =====================================================
    -- 2. applicationライフサイクル
    -- =====================================================

    a.intent_confirmed_date,
    a.recommendation_date,
    a.recommendation_result,
    a.withdrawal_date,
    a.withdrawal_reason,
	
    -- =====================================================
    -- 修正① withdrawal_stage追加
    -- =====================================================
    -- 現在の正式版では辞退を
    -- pre_recommendation
    -- post_recommendation
    -- post_visit
    -- に分けている。
    --
    -- H5では重要な分析軸となる。
    -- =====================================================

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
    strftime(
        '%Y-%m',
        a.intent_confirmed_date
    ) AS application_month,

    -- =====================================================
    -- 修正② 30日観察可能フラグ
    -- =====================================================
    -- intent_confirmed_dateから30日後まで
    -- DATA_END_DATE内で観察可能か判定する。
    --
    -- 1：　30日間観察可能
    -- 0：　観察期間終了により右打ち切り
    --
    -- この30日は、「30日以内に必ずplacementすべき」という統計的なルールではない。
    -- application単位で同じ観察期間を確保するための業務上の観察窓として利用する。
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
    -- 3. 求人属性
    -- =====================================================

    j.open_date,
    j.close_date,
    j.status AS job_status,
    j.client_id,
    j.ra_id,

    -- =====================================================
    -- 4. 求人職種
    -- =====================================================

    j.occupation_id,
    o.occupation_name,
    o.occupation_group,

    -- =====================================================
    -- 5. 求人勤務地
    -- =====================================================

    j.location_id,
    jl.prefecture_name
        AS job_prefecture_name,

    jl.area_group
        AS job_area_group,

    -- =====================================================
    -- 6. 求人条件
    -- =====================================================

    j.required_slots,
    j.offered_hourly_wage,
    j.required_skill_level,
    j.work_style,

    -- =====================================================
    -- 7. application時点の候補者希望条件
    -- =====================================================

    ap.preferred_occupation_id,

    po.occupation_name
        AS preferred_occupation_name,

    po.occupation_group
        AS preferred_occupation_group,

    ap.preferred_location_id,

    pl.prefecture_name
        AS preferred_prefecture_name,

    pl.area_group
        AS preferred_area_group,

    ap.desired_hourly_wage,

    ap.preferred_work_style,

    -- =====================================================
    -- 8. 求人条件との単純一致フラグ
    -- =====================================================
    -- 後の多変量分析で、
    -- ・希望職種一致
    -- ・希望勤務地一致
    -- ・勤務形態一致
    -- をコントロール変数として利用できる。
    -- =====================================================

    -- ---------------------------------------------
    -- 希望職種と求人職種の完全一致
    -- ---------------------------------------------

    CASE
        WHEN ap.preferred_occupation_id IS NULL
        THEN NULL
        WHEN
            ap.preferred_occupation_id
            =
            j.occupation_id
        THEN 1
        ELSE 0
    END AS preferred_occupation_match_flag,

    -- ---------------------------------------------
    -- 希望勤務地と求人勤務地の完全一致
    -- ---------------------------------------------
    CASE
        WHEN ap.preferred_location_id IS NULL
        THEN NULL
        WHEN
            ap.preferred_location_id
            =
            j.location_id
        THEN 1
        ELSE 0
    END AS preferred_location_match_flag,

    -- ---------------------------------------------
    -- 希望勤務形態と求人勤務形態の一致
    -- ---------------------------------------------
    -- H6分析でも利用できる。
    -- ---------------------------------------------

    CASE
        WHEN ap.preferred_work_style IS NULL
        THEN NULL
        WHEN
            ap.preferred_work_style
            =
            j.work_style
        THEN 1
        ELSE 0
    END AS work_style_match_flag,

    -- =====================================================
    -- 9. H2 給与ミスマッチ
    -- =====================================================
    -- ---------------------------------------------
    -- wage_gap
    -- ---------------------------------------------
    -- 定義：　求人提示時給 - 候補者希望時給
    --
    -- 正：　提示時給 >= 希望時給
    -- 負：　提示時給 < 希望時給
    -- ---------------------------------------------

    CASE
        WHEN ap.desired_hourly_wage IS NOT NULL
        THEN
            j.offered_hourly_wage
            -
            ap.desired_hourly_wage
    END AS wage_gap,

    -- ---------------------------------------------
    -- wage_gap_rate
    -- ---------------------------------------------
    -- 求人提示時給 - 希望時給
    -- --------------------------
    -- 希望時給
    -- 例：
    -- 希望2000円
    -- 提示1800円
    --
    -- → -0.100
    -- つまり10%不足。
    -- ---------------------------------------------

    CASE
        WHEN
            ap.desired_hourly_wage IS NOT NULL
            AND ap.desired_hourly_wage > 0
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
    END AS wage_gap_rate,

    -- =====================================================
    -- 修正③ wage_shortfall_rate
    -- =====================================================
    -- H2分析では、
    -- 「希望額に対して求人提示額が何%不足しているか」
    -- を正の数で表した方が直感的。
    --
    -- 定義：
    -- MAX(
    --     希望時給 - 提示時給,
    --     0
    -- )
    -- ------------------------
    -- 希望時給
    --
    -- 例：
    -- 希望2000
    -- 提示1800
    --
    -- → 0.10
    --
    -- 希望1800
    -- 提示2000
    --
    -- → 0.00
    --
    -- =====================================================

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
    -- 10. H3 スキルミスマッチ
    -- =====================================================


    -- ---------------------------------------------
    -- 同職種経験が存在するか
    -- ---------------------------------------------
    --
    -- candidate_skillがNULLの場合、
    -- 「skill不足」ではなく
    -- 「同職種経験なし」
    -- という別状態として扱う。
    --
    -- これは非常に重要。
    -- ---------------------------------------------

    CASE

        WHEN cs.candidate_skill_level IS NOT NULL
        THEN 1

        ELSE 0

    END AS same_occupation_experience_flag,


    -- ---------------------------------------------
    -- 同職種での最大skill
    -- ---------------------------------------------

    cs.candidate_skill_level,


    -- ---------------------------------------------
    -- skill_gap
    -- ---------------------------------------------
    --
    -- candidate_skill
    -- -
    -- required_skill
    --
    --
    -- 同職種経験がない場合はNULL。
    --
    -- -3などの仮の値を入れない。
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
    -- skill_requirement_met_flag
    -- ---------------------------------------------
    --
    -- 同職種経験が存在する場合のみ、
    -- required_skillを満たしているか判定する。
    --
    -- 同職種経験なしの場合はNULL。
    --
    -- 「経験なし」と
    -- 「経験はあるがskill不足」を
    -- 混同しないため。
    -- ---------------------------------------------

    CASE

        WHEN cs.candidate_skill_level IS NULL
        THEN NULL

        WHEN
            cs.candidate_skill_level
            >=
            j.required_skill_level
        THEN 1

        ELSE 0

    END AS skill_requirement_met_flag,


    -- =====================================================
    -- 修正④ H3分析用skillグループ
    -- =====================================================
    --
    -- 後のEDAやロジスティック回帰で使いやすいよう、
    -- skill状態をカテゴリ化する。
    --
    --
    -- no_same_occ_exp
    --     同職種経験なし
    --
    -- gap_le_minus2
    --     要求skillより2以上低い
    --
    -- gap_minus1
    --     要求skillより1低い
    --
    -- gap_ge_0
    --     要求skill以上
    -- =====================================================

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
    -- 11. 応募 → 推薦
    -- =====================================================


    -- ---------------------------------------------
    -- 応募意思確認 → 企業推薦までの日数
    -- ---------------------------------------------
    --
    -- 実際に推薦された案件だけ値を持つ。
    --
    -- screened_outやpre-recommendation withdrawalに
    -- 0日を入れない。
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
    -- 実際に推薦されたか
    -- ---------------------------------------------

    CASE

        WHEN a.recommendation_date IS NOT NULL
        THEN 1

        ELSE 0

    END AS recommended_flag,


    -- ---------------------------------------------
    -- 推薦通過したか
    -- ---------------------------------------------

    CASE

        WHEN a.recommendation_result = 'accepted'
        THEN 1

        ELSE 0

    END AS recommendation_accepted_flag,


    -- =====================================================
    -- 12. application状態
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


    -- ---------------------------------------------
    -- 企業側等で不成立
    -- ---------------------------------------------

    CASE

        WHEN a.status = 'rejected'
        THEN 1

        ELSE 0

    END AS rejected_flag,


    -- =====================================================
    -- 13. 辞退
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
    -- 応募意思確認 → 辞退までの日数
    -- ---------------------------------------------

    CASE

        WHEN a.withdrawal_date IS NOT NULL

        THEN

            ROUND(
                julianday(
                    a.withdrawal_date
                )
                -
                julianday(
                    a.intent_confirmed_date
                ),
                1
            )

        ELSE NULL

    END AS intent_to_withdrawal_days,


    -- =====================================================
    -- 修正⑤ 辞退ステージ別フラグ
    -- =====================================================


    -- ---------------------------------------------
    -- 推薦前辞退
    -- ---------------------------------------------

    CASE

        WHEN
            a.status = 'withdrawn'
            AND
            a.withdrawal_stage
            =
            'pre_recommendation'

        THEN 1

        ELSE 0

    END AS pre_recommendation_withdrawal_flag,


    -- ---------------------------------------------
    -- 推薦後・職場見学前辞退
    -- ---------------------------------------------

    CASE

        WHEN
            a.status = 'withdrawn'
            AND
            a.withdrawal_stage
            =
            'post_recommendation'

        THEN 1

        ELSE 0

    END AS post_recommendation_withdrawal_flag,


    -- ---------------------------------------------
    -- 職場見学後辞退
    -- ---------------------------------------------

    CASE

        WHEN
            a.status = 'withdrawn'
            AND
            a.withdrawal_stage
            =
            'post_visit'

        THEN 1

        ELSE 0

    END AS post_visit_withdrawal_flag,


    -- =====================================================
    -- 修正⑥ accepted_other_job分離
    -- =====================================================
    --
    -- 他求人でplacementした結果、
    -- 並行選考を終了した案件。
    --
    -- H2・H5で、
    -- 対象求人の給与やプロセスが原因の辞退と
    -- 混ぜないために個別フラグを作る。
    -- =====================================================

    CASE

        WHEN
            a.status = 'withdrawn'
            AND
            a.withdrawal_reason
            =
            'accepted_other_job'

        THEN 1

        ELSE 0

    END AS accepted_other_job_withdrawal_flag,


    -- ---------------------------------------------
    -- H2 / H5分析対象となる辞退
    -- ---------------------------------------------
    --
    -- accepted_other_jobを除いた辞退。
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


    -- ---------------------------------------------
    -- process_delayが記録された辞退
    -- ---------------------------------------------

    CASE

        WHEN
            a.status = 'withdrawn'
            AND
            a.withdrawal_reason
            =
            'process_delay'

        THEN 1

        ELSE 0

    END AS process_delay_withdrawal_flag,


    -- ---------------------------------------------
    -- wageが記録された辞退
    -- ---------------------------------------------

    CASE

        WHEN
            a.status = 'withdrawn'
            AND
            a.withdrawal_reason
            =
            'wage'

        THEN 1

        ELSE 0

    END AS wage_withdrawal_flag,


    -- =====================================================
    -- 14. 職場見学
    -- =====================================================

    COALESCE(
        v.visit_count,
        0
    ) AS visit_count,


    v.first_scheduled_date,

    v.first_visit_date,


    COALESCE(
        v.visit_scheduled_flag,
        0
    ) AS visit_scheduled_flag,


    COALESCE(
        v.visit_completed_flag,
        0
    ) AS visit_completed_flag,


    COALESCE(
        v.visit_cancelled_flag,
        0
    ) AS visit_cancelled_flag,


    COALESCE(
        v.visit_continue_flag,
        0
    ) AS visit_continue_flag,


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
    -- 見学設定 → 実施までの日数
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


    -- ---------------------------------------------
    -- 応募意思確認 → 職場見学実施までの日数
    -- ---------------------------------------------

    CASE

        WHEN v.first_visit_date IS NOT NULL

        THEN

            ROUND(
                julianday(
                    v.first_visit_date
                )
                -
                julianday(
                    a.intent_confirmed_date
                ),
                1
            )

        ELSE NULL

    END AS intent_to_visit_days,


    -- =====================================================
    -- 15. placement
    -- =====================================================

    COALESCE(
        p.placed_flag,
        0
    ) AS placed_flag,


    p.decision_date,

    p.start_date,

    p.agreed_hourly_wage,

    p.placement_status,


    -- ---------------------------------------------
    -- 応募意思確認 → placementまでの日数
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

    END AS intent_to_decision_days,


    -- ---------------------------------------------
    -- 職場見学 → placementまでの日数
    -- ---------------------------------------------

    CASE

        WHEN
            p.decision_date IS NOT NULL
            AND
            v.first_visit_date IS NOT NULL

        THEN

            ROUND(
                julianday(
                    p.decision_date
                )
                -
                julianday(
                    v.first_visit_date
                ),
                1
            )

        ELSE NULL

    END AS visit_to_decision_days,


    -- ---------------------------------------------
    -- 求人公開 → placementまでの日数
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
                    j.open_date
                ),
                1
            )

        ELSE NULL

    END AS open_to_decision_days,


    -- =====================================================
    -- 16. 求人60日観察可能フラグ
    -- =====================================================
    --
    -- mart_job_analysisと同じ定義。
    --
    -- 求人公開後60日まで
    -- DATA_END_DATE内で観察できる場合のみ1。
    -- =====================================================

    CASE

        WHEN
            date(
                j.open_date,
                '+60 day'
            )
            <=
            date(
                '2026-09-30'
            )

        THEN 1

        ELSE 0

    END AS job_60d_observed_flag,


    -- =====================================================
    -- 修正⑦ 60日以内placementフラグ
    -- =====================================================
    --
    -- 【変更前】
    --
    -- placementしていない案件はすべて0。
    --
    --
    -- 【問題点】
    --
    -- 求人公開から60日経っていない場合、
    -- 「60日以内placementしなかった」とは
    -- まだ判断できない。
    --
    --
    -- 【修正仕様】
    --
    -- job_60d_observed_flag = 0
    -- 相当の場合はNULL。
    --
    -- 観察可能求人のみ、
    --
    -- 1 = 60日以内placement
    -- 0 = 60日以内placementなし
    --
    -- とする。
    -- =====================================================

    CASE

        WHEN
            date(
                j.open_date,
                '+60 day'
            )
            >
            date(
                '2026-09-30'
            )

        THEN NULL


        WHEN
            p.decision_date IS NOT NULL
            AND
            (
                julianday(
                    p.decision_date
                )
                -
                julianday(
                    j.open_date
                )
            ) <= 60

        THEN 1


        ELSE 0

    END AS placed_within_60d_flag


-- =========================================================
-- 基準テーブル
-- =========================================================
--
-- applicationsがこのマートの基準。
--
-- つまり、
--
-- applicationsに存在する案件は
-- 原則として1行ずつ残す。
-- =========================================================

FROM applications a


-- =========================================================
-- 求人
-- =========================================================
--
-- applicationにjob_idは必須なので、
-- INNER JOINを使用。
--
-- build_sqlite_db.pyの参照整合性チェックにより、
-- applications.job_idは必ずjobsに存在する前提。
-- =========================================================

INNER JOIN jobs j
    ON
        a.job_id
        =
        j.job_id


-- =========================================================
-- 求人職種マスタ
-- =========================================================

LEFT JOIN occupations o
    ON
        j.occupation_id
        =
        o.occupation_id


-- =========================================================
-- 求人勤務地マスタ
-- =========================================================

LEFT JOIN locations jl
    ON
        j.location_id
        =
        jl.location_id


-- =========================================================
-- application時点希望条件
-- =========================================================

LEFT JOIN application_preference ap
    ON
        a.application_id
        =
        ap.application_id


-- =========================================================
-- 希望職種マスタ
-- =========================================================

LEFT JOIN occupations po
    ON
        ap.preferred_occupation_id
        =
        po.occupation_id


-- =========================================================
-- 希望勤務地マスタ
-- =========================================================

LEFT JOIN locations pl
    ON
        ap.preferred_location_id
        =
        pl.location_id


-- =========================================================
-- 候補者スキル
-- =========================================================
--
-- 「応募した求人と同じoccupation」の
-- candidate_skillのみ取得する。
--
-- 別職種のskillはここでは利用しない。
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