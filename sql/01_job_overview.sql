SELECT
    occupation_id,
    COUNT(*) AS job_count,
    AVG(offered_hourly_wage) AS avg_wage,
    AVG(required_skill_level) AS avg_skill
FROM jobs
GROUP BY occupation_id
ORDER BY occupation_id
;