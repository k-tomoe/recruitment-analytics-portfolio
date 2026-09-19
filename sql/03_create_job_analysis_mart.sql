DROP VIEW IF EXISTS mart_job_analysis;

CREATE VIEW mart_job_analysis AS

WITH entry_agg AS (
    SELECT
        job_id,
        COUNT(*) AS entry_count,
        SUM(
            CASE
                WHEN status = 'converted' THEN 1
                ELSE 0
            END
        ) AS converted_entry_count
    FROM job_entries
    GROUP BY job_id
),

application_agg AS (
    SELECT
        job_id,
        COUNT(*) AS application_count,
        SUM(
            CASE
                WHEN recommendation_date IS NOT NULL THEN 1
                ELSE 0
            END
        ) AS recommendation_count,
        SUM(
            CASE
                WHEN recommendation_result = 'accepted' THEN 1
                ELSE 0
            END
        ) AS recommendation_accepted_count,
        SUM(
            CASE
                WHEN status = 'withdrawn' THEN 1
                ELSE 0
            END
        ) AS withdrawal_count,
        AVG(
            CASE
                WHEN recommendation_date IS NOT NULL
                THEN julianday(recommendation_date)
                   - julianday(intent_confirmed_date)
            END
        ) AS avg_intent_to_recommend_days
    FROM applications
    GROUP BY job_id
),

visit_agg AS (
    SELECT
        a.job_id,

        COUNT(w.visit_id) AS visit_count,

        SUM(
            CASE
                WHEN w.visit_status = 'completed' THEN 1
                ELSE 0
            END
        ) AS completed_visit_count,

        SUM(
            CASE
                WHEN w.visit_status = 'cancelled' THEN 1
                ELSE 0
            END
        ) AS cancelled_visit_count,

        AVG(
            CASE
                WHEN w.scheduled_date IS NOT NULL
                THEN julianday(w.scheduled_date)
                   - julianday(a.recommendation_date)
            END
        ) AS avg_recommend_to_schedule_days

    FROM applications a

    LEFT JOIN workplace_visits w
        ON a.application_id = w.application_id

    GROUP BY a.job_id
),

placement_agg AS (
    SELECT
        a.job_id,

        COUNT(p.placement_id) AS placement_count,

        SUM(
            CASE
                WHEN julianday(p.decision_date)
                   - julianday(j.open_date) <= 60
                THEN 1
                ELSE 0
            END
        ) AS placement_60d_count,

        AVG(
            CASE
                WHEN p.decision_date IS NOT NULL
                THEN julianday(p.decision_date)
                   - julianday(a.intent_confirmed_date)
            END
        ) AS avg_intent_to_decision_days

    FROM applications a

    JOIN jobs j
        ON a.job_id = j.job_id

    LEFT JOIN placements p
        ON a.application_id = p.application_id

    GROUP BY a.job_id
)

SELECT
    j.job_id,
    j.client_id,
    j.ra_id,
    j.open_date,

    strftime('%Y', j.open_date) AS open_year,
    strftime('%Y-%m', j.open_date) AS open_month,

    j.occupation_id,
    o.occupation_name,
    o.occupation_group,

    j.location_id,
    l.prefecture_name,
    l.area_group,

    j.required_slots,
    j.offered_hourly_wage,
    j.required_skill_level,
    j.work_style,

    COALESCE(e.entry_count, 0) AS entry_count,
    COALESCE(e.converted_entry_count, 0) AS converted_entry_count,

    COALESCE(a.application_count, 0) AS application_count,
    COALESCE(a.recommendation_count, 0) AS recommendation_count,
    COALESCE(a.recommendation_accepted_count, 0) AS recommendation_accepted_count,
    COALESCE(a.withdrawal_count, 0) AS withdrawal_count,

    COALESCE(v.visit_count, 0) AS visit_count,
    COALESCE(v.completed_visit_count, 0) AS completed_visit_count,
    COALESCE(v.cancelled_visit_count, 0) AS cancelled_visit_count,

    COALESCE(p.placement_count, 0) AS placement_count,
    COALESCE(p.placement_60d_count, 0) AS placement_60d_count,

    ROUND(
        1.0 * COALESCE(p.placement_60d_count, 0)
        / j.required_slots,
        3
    ) AS fill_rate_60d,

    ROUND(
        a.avg_intent_to_recommend_days,
        2
    ) AS avg_intent_to_recommend_days,

    ROUND(
        v.avg_recommend_to_schedule_days,
        2
    ) AS avg_recommend_to_schedule_days,

    ROUND(
        p.avg_intent_to_decision_days,
        2
    ) AS avg_intent_to_decision_days

FROM jobs j

LEFT JOIN occupations o
    ON j.occupation_id = o.occupation_id

LEFT JOIN locations l
    ON j.location_id = l.location_id

LEFT JOIN entry_agg e
    ON j.job_id = e.job_id

LEFT JOIN application_agg a
    ON j.job_id = a.job_id

LEFT JOIN visit_agg v
    ON j.job_id = v.job_id

LEFT JOIN placement_agg p
    ON j.job_id = p.job_id;