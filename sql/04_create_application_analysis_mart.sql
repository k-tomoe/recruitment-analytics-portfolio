DROP VIEW IF EXISTS mart_application_analysis;

CREATE VIEW mart_application_analysis AS

WITH candidate_skill AS (
    SELECT
        candidate_id,
        occupation_id,
        MAX(skill_level) AS candidate_skill_level
    FROM candidate_experiences
    GROUP BY
        candidate_id,
        occupation_id
),

visit_agg AS (
    SELECT
        application_id,

        COUNT(*) AS visit_count,

        MIN(scheduled_date) AS first_scheduled_date,

        MIN(
            CASE
                WHEN visit_status = 'completed'
                THEN visit_date
            END
        ) AS first_visit_date,

        MAX(
            CASE
                WHEN visit_status = 'cancelled'
                THEN 1
                ELSE 0
            END
        ) AS visit_cancelled_flag,

        MAX(
            CASE
                WHEN visit_status = 'completed'
                     AND result = 'continue'
                THEN 1
                ELSE 0
            END
        ) AS visit_continue_flag

    FROM workplace_visits

    GROUP BY application_id
),

placement_agg AS (
    SELECT
        application_id,
        MIN(decision_date) AS decision_date,
        MIN(start_date) AS start_date,
        MAX(agreed_hourly_wage) AS agreed_hourly_wage,
        1 AS placed_flag
    FROM placements
    GROUP BY application_id
)

SELECT
    a.application_id,
    a.job_id,
    a.candidate_id,
    a.ca_id,

    a.application_source,
    a.source_entry_id,
    a.source_introduction_id,

    a.intent_confirmed_date,
    a.recommendation_date,
    a.recommendation_result,
    a.withdrawal_date,
    a.withdrawal_reason,
    a.status AS application_status,

    strftime(
        '%Y',
        a.intent_confirmed_date
    ) AS application_year,

    strftime(
        '%Y-%m',
        a.intent_confirmed_date
    ) AS application_month,

    -- ================================================
    -- 求人属性
    -- ================================================

    j.open_date,
    j.client_id,
    j.ra_id,

    j.occupation_id,
    o.occupation_name,
    o.occupation_group,

    j.location_id,

    j.required_slots,
    j.offered_hourly_wage,
    j.required_skill_level,
    j.work_style,

    -- ================================================
    -- 応募意思確認時点の希望条件
    -- ================================================

    cp.preferred_occupation_id,
    cp.preferred_location_id,
    cp.desired_hourly_wage,
    cp.preferred_work_style,

    -- ================================================
    -- 給与ミスマッチ
    -- ================================================

    j.offered_hourly_wage
        - cp.desired_hourly_wage
        AS wage_gap,

    ROUND(
        1.0
        * (
            j.offered_hourly_wage
            - cp.desired_hourly_wage
        )
        / cp.desired_hourly_wage,
        3
    ) AS wage_gap_rate,

    CASE
        WHEN j.offered_hourly_wage
             >= cp.desired_hourly_wage
        THEN 1
        ELSE 0
    END AS wage_requirement_met_flag,

    -- ================================================
    -- スキルミスマッチ
    -- ================================================

    cs.candidate_skill_level,

    cs.candidate_skill_level
        - j.required_skill_level
        AS skill_gap,

    CASE
        WHEN cs.candidate_skill_level
             >= j.required_skill_level
        THEN 1
        ELSE 0
    END AS skill_requirement_met_flag,

    -- ================================================
    -- 応募→推薦
    -- ================================================

    CASE
        WHEN a.recommendation_date IS NOT NULL
        THEN ROUND(
            julianday(a.recommendation_date)
            - julianday(a.intent_confirmed_date),
            1
        )
    END AS intent_to_recommend_days,

    CASE
        WHEN a.recommendation_date IS NOT NULL
        THEN 1
        ELSE 0
    END AS recommended_flag,

    CASE
        WHEN a.recommendation_result = 'accepted'
        THEN 1
        ELSE 0
    END AS recommendation_accepted_flag,

    -- ================================================
    -- 辞退
    -- ================================================

    CASE
        WHEN a.withdrawal_date IS NOT NULL
        THEN 1
        ELSE 0
    END AS withdrawal_flag,

    CASE
        WHEN a.withdrawal_date IS NOT NULL
        THEN ROUND(
            julianday(a.withdrawal_date)
            - julianday(a.intent_confirmed_date),
            1
        )
    END AS intent_to_withdrawal_days,

    -- ================================================
    -- 職場見学
    -- ================================================

    COALESCE(
        v.visit_count,
        0
    ) AS visit_count,

    v.first_scheduled_date,
    v.first_visit_date,

    COALESCE(
        v.visit_cancelled_flag,
        0
    ) AS visit_cancelled_flag,

    COALESCE(
        v.visit_continue_flag,
        0
    ) AS visit_continue_flag,

    CASE
        WHEN
            a.recommendation_date IS NOT NULL
            AND v.first_scheduled_date IS NOT NULL
        THEN ROUND(
            julianday(v.first_scheduled_date)
            - julianday(a.recommendation_date),
            1
        )
    END AS recommend_to_schedule_days,

    CASE
        WHEN
            v.first_scheduled_date IS NOT NULL
            AND v.first_visit_date IS NOT NULL
        THEN ROUND(
            julianday(v.first_visit_date)
            - julianday(v.first_scheduled_date),
            1
        )
    END AS schedule_to_visit_days,

    -- ================================================
    -- 就業決定
    -- ================================================

    COALESCE(
        p.placed_flag,
        0
    ) AS placed_flag,

    p.decision_date,
    p.start_date,
    p.agreed_hourly_wage,

    CASE
        WHEN p.decision_date IS NOT NULL
        THEN ROUND(
            julianday(p.decision_date)
            - julianday(a.intent_confirmed_date),
            1
        )
    END AS intent_to_decision_days,

    CASE
        WHEN p.decision_date IS NOT NULL
        THEN ROUND(
            julianday(p.decision_date)
            - julianday(j.open_date),
            1
        )
    END AS open_to_decision_days,

    CASE
        WHEN
            p.decision_date IS NOT NULL
            AND (
                julianday(p.decision_date)
                - julianday(j.open_date)
            ) <= 60
        THEN 1
        ELSE 0
    END AS placed_within_60d_flag

FROM applications a

INNER JOIN jobs j
    ON a.job_id = j.job_id

LEFT JOIN occupations o
    ON j.occupation_id = o.occupation_id

LEFT JOIN candidate_preferences cp
    ON a.candidate_id = cp.candidate_id

    AND a.intent_confirmed_date
        >= cp.effective_from

    AND (
        cp.effective_to IS NULL
        OR
        a.intent_confirmed_date
        <= cp.effective_to
    )

LEFT JOIN candidate_skill cs
    ON a.candidate_id = cs.candidate_id
    AND j.occupation_id = cs.occupation_id

LEFT JOIN visit_agg v
    ON a.application_id = v.application_id

LEFT JOIN placement_agg p
    ON a.application_id = p.application_id;