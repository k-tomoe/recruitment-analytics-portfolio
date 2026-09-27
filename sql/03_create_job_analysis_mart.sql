-- =========================================================
-- 求人分析マート
-- mart_job_analysis
-- =========================================================
-- 【このマートの粒度】
-- 1行 = 1求人 jobsテーブルを基準にして、
-- ・求人エントリー
-- ・応募
-- ・企業推薦
-- ・辞退
-- ・職場見学
-- ・就業決定
-- を求人単位へ集約する。
--
-- 【主な用途】
-- H1：
-- 求人数 / 募集枠数 / 応募数 / placement数 /
-- 60日以内充足率
--
-- H4：
-- 職種構成 / required_skill_level /
-- 求人条件別の充足状況
--
-- H5：
-- 応募→推薦 /
-- 推薦→職場見学 /
-- 応募→就業決定
-- のリードタイム
--
-- 【重要】
-- このマートは「求人単位」の分析用。
-- 候補者単位・応募単位の給与差やskill_gap分析は、mart_application_analysisで行う。
-- =========================================================


-- =========================================================
-- 既存VIEW削除
-- =========================================================
-- CREATE VIEWを再実行できるように、同名VIEWが存在する場合は先に削除する。
-- 元テーブルのデータを削除する処理ではない。
-- =========================================================

DROP VIEW IF EXISTS mart_job_analysis;

-- =========================================================
-- VIEW作成
-- =========================================================
CREATE VIEW mart_job_analysis AS
-- =========================================================
-- CTE① 求人エントリー集計
-- entry_agg
-- =========================================================
-- job_entriesを1行 = 1求人へ集約する。
-- job_entries自体は 1行 = 1候補者 × 1求人へのエントリー
-- なので、求人別のエントリー数をここで作る。
-- =========================================================

WITH entry_agg AS (
    SELECT
        job_id,
        -- ---------------------------------------------
        -- 求人サイト上で興味を示した総件数
        -- ---------------------------------------------
        COUNT(*) AS entry_count,
        -- ---------------------------------------------
        -- self_entryから正式applicationへ登録された件数
        -- 応募意思確認がとれたもの
        -- ---------------------------------------------
        SUM(
            CASE
                WHEN status = 'converted'
                THEN 1
                ELSE 0
            END
        ) AS converted_entry_count
    FROM job_entries
    GROUP BY
        job_id
),
-- =========================================================
-- CTE② 応募案件集計
-- application_agg
-- =========================================================
-- applicationsは1行 = 1候補者 × 1求人の正式応募案件
-- なので、求人別の選考ファネルをここで集約する。
-- =========================================================

application_agg AS (
    SELECT
        job_id,
        -- ---------------------------------------------
        -- 正式application総数
        -- ---------------------------------------------
        COUNT(*) AS application_count,
        -- ---------------------------------------------
        -- 応募経路別件数
        -- ---------------------------------------------
        -- self_entry　= 求人サイトから自発応募
        -- ca_introduction = CA紹介経由
        -- 求人ごとにどちらの経路が多いかを確認できるようにする。
        -- ---------------------------------------------
        SUM(
            CASE
                WHEN application_source = 'self_entry'
                THEN 1
                ELSE 0
            END
        ) AS self_entry_application_count,


        SUM(
            CASE
                WHEN application_source = 'ca_introduction'
                THEN 1
                ELSE 0
            END
        ) AS ca_introduction_application_count,

        -- ---------------------------------------------
        -- 実際に企業推薦された件数
        -- ---------------------------------------------
        -- recommendation_dateが存在する
        -- =
        -- CAスクリーニングを通り、
        -- 実際に企業へ推薦された案件。
        --
        -- screened_outや、
        -- 推薦前辞退は含まれない。
        -- ---------------------------------------------

        SUM(
            CASE
                WHEN recommendation_date IS NOT NULL
                THEN 1
                ELSE 0
            END
        ) AS recommendation_count,

        -- ---------------------------------------------
        -- 企業推薦通過件数
        -- ---------------------------------------------
        -- acceptedになった案件のみ。
        --
        -- この後、
        -- post_recommendation辞退や
        -- workplace_visitへ進む可能性がある。
        -- ---------------------------------------------

        SUM(
            CASE
                WHEN recommendation_result = 'accepted'
                THEN 1
                ELSE 0
            END
        ) AS recommendation_accepted_count,

        -- =================================================
        -- 修正① 辞退を3段階で分離
        -- =================================================
        --
        -- 【変更前】
        --
        -- status = withdrawn をすべてwithdrawal_countとしていた。
        --
        -- 【問題点】
        --
        -- 現在は辞退を、
        --
        -- pre_recommendation
        -- post_recommendation
        -- post_visit
        --
        -- の3段階へ分けている。
        --
        -- H5では、
        -- どの工程で辞退したのかが重要なので、
        -- まとめてしまうと情報が失われる。
        -- =================================================


        -- ---------------------------------------------
        -- 推薦前辞退
        -- ---------------------------------------------

        SUM(
            CASE
                WHEN
                    status = 'withdrawn'
                    AND withdrawal_stage = 'pre_recommendation'
                THEN 1
                ELSE 0
            END
        ) AS pre_recommendation_withdrawal_count,


        -- ---------------------------------------------
        -- 推薦後・職場見学前辞退
        -- ---------------------------------------------

        SUM(
            CASE
                WHEN
                    status = 'withdrawn'
                    AND withdrawal_stage = 'post_recommendation'
                THEN 1
                ELSE 0
            END
        ) AS post_recommendation_withdrawal_count,


        -- ---------------------------------------------
        -- 職場見学後辞退
        -- ---------------------------------------------

        SUM(
            CASE
                WHEN
                    status = 'withdrawn'
                    AND withdrawal_stage = 'post_visit'
                THEN 1
                ELSE 0
            END
        ) AS post_visit_withdrawal_count,


        -- ---------------------------------------------
        -- 辞退総数
        -- ---------------------------------------------
        --
        -- 3ステージすべてを含む。
        --
        -- ファネル全体の件数確認には使えるが、
        -- H5の詳細分析ではステージ別件数を使う。
        -- ---------------------------------------------

        SUM(
            CASE
                WHEN status = 'withdrawn'
                THEN 1
                ELSE 0
            END
        ) AS withdrawal_count,


        -- =================================================
        -- 修正② accepted_other_jobを分離
        -- =================================================
        --
        -- placementした候補者が
        -- 同時進行していた別求人を終了した場合、
        --
        -- withdrawal_reason = accepted_other_job
        --
        -- としている。
        --
        -- これは
        --
        -- ・給与不足
        -- ・プロセス遅延
        --
        -- による辞退とは意味が異なる。
        --
        -- したがってH5分析では、
        -- 通常の辞退から分けて扱えるよう
        -- 個別件数を持たせる。
        -- =================================================

        SUM(
            CASE
                WHEN
                    status = 'withdrawn'
                    AND withdrawal_reason = 'accepted_other_job'
                THEN 1
                ELSE 0
            END
        ) AS accepted_other_job_withdrawal_count,


        -- ---------------------------------------------
        -- H5分析用辞退件数
        -- ---------------------------------------------
        --
        -- accepted_other_jobを除いた辞退。
        --
        -- process_delay / wage / other
        -- など、対象求人の選考プロセス内で
        -- 発生した辞退を確認するときに使う。
        -- ---------------------------------------------

        SUM(
            CASE
                WHEN
                    status = 'withdrawn'
                    AND (
                        withdrawal_reason IS NULL
                        OR withdrawal_reason <> 'accepted_other_job'
                    )
                THEN 1
                ELSE 0
            END
        ) AS process_withdrawal_count,


        -- ---------------------------------------------
        -- CA判断による推薦対象外
        -- ---------------------------------------------
        --
        -- intent確認までは行われたが、
        -- skill等を確認した結果、
        -- 企業推薦へ進めなかった案件。
        -- ---------------------------------------------

        SUM(
            CASE
                WHEN status = 'screened_out'
                THEN 1
                ELSE 0
            END
        ) AS screened_out_count,


        -- ---------------------------------------------
        -- 観察期間終了時点で処理中
        -- ---------------------------------------------
        --
        -- recommendation予定はあるが、
        -- DATA_END_DATEまでに結果を観察できなかった案件。
        --
        -- 「失敗」として扱わないことが重要。
        -- ---------------------------------------------

        SUM(
            CASE
                WHEN status = 'confirmed'
                THEN 1
                ELSE 0
            END
        ) AS confirmed_count,


        -- ---------------------------------------------
        -- 応募意思確認 → 企業推薦までの日数
        -- ---------------------------------------------
        --
        -- recommendation_dateが存在する案件だけが分母。
        --
        -- screened_outや推薦前辞退を
        -- 無理に0日として入れない。
        -- ---------------------------------------------

        AVG(
            CASE
                WHEN recommendation_date IS NOT NULL
                THEN
                    julianday(recommendation_date)
                    -
                    julianday(intent_confirmed_date)
            END
        ) AS avg_intent_to_recommend_days
    FROM applications
    GROUP BY
        job_id
),


-- =========================================================
-- CTE③ 職場見学集計
-- visit_agg
-- =========================================================
-- workplace_visitsは　1行 = 1applicationの職場見学
-- 現在の仕様では 1application　につき最大1件。
-- applicationsと結合し、job_id単位へ集約する。
-- =========================================================

visit_agg AS (
    SELECT
        a.job_id,
        -- ---------------------------------------------
        -- 職場見学レコード総数
        -- ---------------------------------------------
        -- completed
        -- scheduled
        -- cancelled
        --
        -- のすべてを含む。
        -- 推薦後に見学設定前で辞退した案件は
        -- workplace_visits自体が作られないので
        -- この件数には含まれない。
        -- ---------------------------------------------

        COUNT(
            w.visit_id
        ) AS visit_count,
        -- ---------------------------------------------
        -- 実施済み職場見学
        -- ---------------------------------------------
        SUM(
            CASE
                WHEN w.visit_status = 'completed'
                THEN 1
                ELSE 0
            END
        ) AS completed_visit_count,

        -- ---------------------------------------------
        -- 観察終了時点で見学予定
        -- ---------------------------------------------

        SUM(
            CASE
                WHEN w.visit_status = 'scheduled'
                THEN 1
                ELSE 0
            END
        ) AS scheduled_visit_count,


        -- ---------------------------------------------
        -- 設定後キャンセル
        -- ---------------------------------------------
        -- 現在のロジックでは主に
        -- post_recommendation withdrawalによる
        -- 見学キャンセル。
        -- ---------------------------------------------

        SUM(
            CASE
                WHEN w.visit_status = 'cancelled'
                THEN 1
                ELSE 0
            END
        ) AS cancelled_visit_count,

        -- ---------------------------------------------
        -- 推薦 → 職場見学設定までの日数
        -- ---------------------------------------------
        -- scheduled_dateが存在する案件のみ対象。
        -- 推薦後、見学設定前に辞退した案件は
        -- この平均には含まれない。
        -- ---------------------------------------------

        AVG(
            CASE
                WHEN
                    w.scheduled_date IS NOT NULL
                    AND
                    a.recommendation_date IS NOT NULL

                THEN
                    julianday(w.scheduled_date)
                    -
                    julianday(a.recommendation_date)
            END
        ) AS avg_recommend_to_schedule_days


    FROM applications a


    LEFT JOIN workplace_visits w
        ON
            a.application_id
            =
            w.application_id


    GROUP BY
        a.job_id
),


-- =========================================================
-- CTE④ 就業決定集計
-- placement_agg
-- =========================================================
-- placementsは　1行 = 1最終就業決定
-- applicationsを経由してjob_idを取得し、求人単位へ集約する。
-- =========================================================

placement_agg AS (
    SELECT
        a.job_id,
        -- ---------------------------------------------
        -- 最終就業決定数
        -- ---------------------------------------------
        COUNT(
            p.placement_id
        ) AS placement_count,

        -- ---------------------------------------------
        -- 求人公開から60日以内のplacement数
        -- ---------------------------------------------
        --
        -- decision_date - open_date <= 60
        --
        -- で判定する。
        --
        -- このCTEでは一旦件数を集計する。
        --
        -- ただし求人自体が60日観察できているかは、
        -- 最終SELECT側の
        -- job_60d_observed_flag
        -- で別途判定する。
        -- ---------------------------------------------

        SUM(
            CASE
                WHEN
                    p.decision_date IS NOT NULL
                    AND
                    (
                        julianday(p.decision_date)
                        -
                        julianday(j.open_date)
                    ) <= 60
                THEN 1
                ELSE 0
            END
        ) AS placement_60d_count,
        -- ---------------------------------------------
        -- 応募意思確認 → 就業決定までの日数
        -- ---------------------------------------------
        --
        -- placementした案件だけが対象。
        --
        -- これは「placementまで到達した案件の
        -- 平均リードタイム」であり、
        -- 全applicationの平均ではない。
        -- ---------------------------------------------

        AVG(
            CASE
                WHEN p.decision_date IS NOT NULL
                THEN
                    julianday(p.decision_date)
                    -
                    julianday(a.intent_confirmed_date)
            END
        ) AS avg_intent_to_decision_days
    FROM applications a
    JOIN jobs j
        ON
            a.job_id
            =
            j.job_id
    LEFT JOIN placements p
        ON
            a.application_id
            =
            p.application_id
    GROUP BY
        a.job_id
)


-- =========================================================
-- 最終SELECT
-- =========================================================
--
-- jobsを起点としてLEFT JOINする。
--
-- そのため、
--
-- エントリー0件
-- application 0件
-- placement 0件
-- の求人もマートから消えない。
-- =========================================================

SELECT
    -- =====================================================
    -- 1. 求人基本情報
    -- =====================================================
    j.job_id,
    j.client_id,
    j.ra_id,
    j.open_date,
    j.close_date,
    j.status AS job_status,
    -- ---------------------------------------------
    -- 公開年
    -- ---------------------------------------------
    -- SQLiteのstrftimeは文字列を返す。
    -- 例：
    -- '2025'
    -- '2026'
    -- ---------------------------------------------
    strftime(
        '%Y',
        j.open_date
    ) AS open_year,
    -- ---------------------------------------------
    -- 公開年月
    -- ---------------------------------------------
    -- 月次集計用。
    -- 例：
    -- 2025-04
    -- ---------------------------------------------
    strftime(
        '%Y-%m',
        j.open_date
    ) AS open_month,
    -- =====================================================
    -- 2. 職種
    -- =====================================================
    j.occupation_id,
    o.occupation_name,
    o.occupation_group,
    -- =====================================================
    -- 3. 勤務地
    -- =====================================================
    j.location_id,
    l.prefecture_name,
    l.area_group,
    -- =====================================================
    -- 4. 求人条件
    -- =====================================================
    j.required_slots,
    j.offered_hourly_wage,
    j.required_skill_level,
    j.work_style,
    -- =====================================================
    -- 5. 60日観察可能フラグ
    -- =====================================================
    -- open_date + 60日 <= DATA_END_DATE
    -- の求人だけ、
    -- 60日KPIを完全に観察できる。
    --
    -- 重要：
    -- close_dateはこの判定に使わない。
    --
    -- 求人が30日でcloseしていても、
    -- DATA_END_DATEまでopen_date+60日を観察できれば、
    -- 60日以内placementの結果は確認できるため。
    --
    -- 1 = 60日間観察可能
    -- 0 = 右打ち切り
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
    -- 6. 求人エントリー
    -- =====================================================
    COALESCE(
        e.entry_count,
        0
    ) AS entry_count,

    COALESCE(
        e.converted_entry_count,
        0
    ) AS converted_entry_count,

    -- =====================================================
    -- 7. application
    -- =====================================================
    COALESCE(
        a.application_count,
        0
    ) AS application_count,

    COALESCE(
        a.self_entry_application_count,
        0
    ) AS self_entry_application_count,

    COALESCE(
        a.ca_introduction_application_count,
        0
    ) AS ca_introduction_application_count,

    COALESCE(
        a.recommendation_count,
        0
    ) AS recommendation_count,

    COALESCE(
        a.recommendation_accepted_count,
        0
    ) AS recommendation_accepted_count,

    -- =====================================================
    -- 8. 辞退
    -- =====================================================
    COALESCE(
        a.withdrawal_count,
        0
    ) AS withdrawal_count,

    COALESCE(
        a.pre_recommendation_withdrawal_count,
        0
    ) AS pre_recommendation_withdrawal_count,

    COALESCE(
        a.post_recommendation_withdrawal_count,
        0
    ) AS post_recommendation_withdrawal_count,

    COALESCE(
        a.post_visit_withdrawal_count,
        0
    ) AS post_visit_withdrawal_count,

    COALESCE(
        a.accepted_other_job_withdrawal_count,
        0
    ) AS accepted_other_job_withdrawal_count,

    COALESCE(
        a.process_withdrawal_count,
        0
    ) AS process_withdrawal_count,

    -- =====================================================
    -- 9. CAスクリーニング / 右打ち切り
    -- =====================================================
    COALESCE(
        a.screened_out_count,
        0
    ) AS screened_out_count,

    COALESCE(
        a.confirmed_count,
        0
    ) AS confirmed_count,

    -- =====================================================
    -- 10. 職場見学
    -- =====================================================
    COALESCE(
        v.visit_count,
        0
    ) AS visit_count,

    COALESCE(
        v.completed_visit_count,
        0
    ) AS completed_visit_count,

    COALESCE(
        v.scheduled_visit_count,
        0
    ) AS scheduled_visit_count,

    COALESCE(
        v.cancelled_visit_count,
        0
    ) AS cancelled_visit_count,

    -- =====================================================
    -- 11. placement
    -- =====================================================
    COALESCE(
        p.placement_count,
        0
    ) AS placement_count,

    -- =====================================================
    -- 修正③ 60日以内placement件数
    -- =====================================================
    -- 【変更前】
    -- 60日未観察の求人でも、
    -- 現時点までのplacement件数が
    -- 0などの数値として表示されていた。
    --
    -- 【問題点】
    -- 例えば9月20日公開求人は、
    -- まだ10日しか観察していない。
    --
    -- placement_60d_count = 0
    -- と表示すると、「60日観察して0件」と誤読する可能性がある。
    --
    -- 【修正仕様】
    -- 60日観察可能求人だけ数値を返す。
    -- 未観察求人はNULL。
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

        THEN
            COALESCE(
                p.placement_60d_count,
                0
            )

        ELSE NULL

    END AS placement_60d_count,


    -- =====================================================
    -- 12. 60日以内募集枠充足率
    -- =====================================================
    --
    -- 定義：
    --
    -- 60日以内placement数
    -- ----------------------
    -- required_slots
    --
    --
    -- 例：
    --
    -- required_slots = 2
    -- placement_60d_count = 1
    --
    -- → 0.500
    --
    --
    -- job_60d_observed_flag = 0なら
    -- NULL。
    --
    --
    -- MIN(
    --     placement_60d_count,
    --     required_slots
    -- )
    --
    -- とすることで、
    -- 念のため100%を超えないようにする。
    --
    -- NULLIF(required_slots, 0)は
    -- 万一0件求人が存在した場合の
    -- 0除算防止。
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
        THEN
            ROUND(
                1.0
                *
                MIN(
                    COALESCE(
                        p.placement_60d_count,
                        0
                    ),
                    j.required_slots
                )
                /
                NULLIF(
                    j.required_slots,
                    0
                ),
                3
            )
        ELSE NULL
    END AS fill_rate_60d,
    -- =====================================================
    -- 13. リードタイム
    -- =====================================================
    -- ---------------------------------------------
    -- 応募意思確認 → 企業推薦
    -- ---------------------------------------------
    ROUND(
        a.avg_intent_to_recommend_days,
        2
    ) AS avg_intent_to_recommend_days,

    -- ---------------------------------------------
    -- 企業推薦 → 職場見学設定
    -- ---------------------------------------------
    ROUND(
        v.avg_recommend_to_schedule_days,
        2
    ) AS avg_recommend_to_schedule_days,

    -- ---------------------------------------------
    -- 応募意思確認 → placement
    -- ---------------------------------------------
    ROUND(
        p.avg_intent_to_decision_days,
        2
    ) AS avg_intent_to_decision_days

-- =========================================================
-- 基準テーブル
-- =========================================================
FROM jobs j
-- =========================================================
-- 職種マスタ
-- =========================================================
LEFT JOIN occupations o
    ON
        j.occupation_id
        =
        o.occupation_id
-- =========================================================
-- 勤務地マスタ
-- =========================================================
LEFT JOIN locations l
    ON
        j.location_id
        =
        l.location_id
-- =========================================================
-- エントリー集計
-- =========================================================
LEFT JOIN entry_agg e
    ON
        j.job_id
        =
        e.job_id
-- =========================================================
-- application集計
-- =========================================================
LEFT JOIN application_agg a
    ON
        j.job_id
        =
        a.job_id
-- =========================================================
-- 職場見学集計
-- =========================================================
LEFT JOIN visit_agg v
    ON
        j.job_id
        =
        v.job_id
-- =========================================================
-- placement集計
-- =========================================================
LEFT JOIN placement_agg p
    ON
        j.job_id
        =
        p.job_id
;