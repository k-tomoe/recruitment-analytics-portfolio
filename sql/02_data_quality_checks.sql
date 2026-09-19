-- 1. jobsテーブル内の求人ID重複チェック
SELECT
    job_id,
    COUNT(*) AS cnt
FROM jobs
GROUP BY job_id
HAVING COUNT(*) > 1;

-- 2. 求職者テーブルの求職者ID重複チェック
SELECT
    candidate_id,
    COUNT(*) AS cnt
FROM candidates
GROUP BY candidate_id
HAVING COUNT(*) > 1;


-- 3. 募集枠を超える就業決定がないか
SELECT
    j.job_id,
    j.required_slots,
    COUNT(p.placement_id) AS placement_count
FROM jobs j
LEFT JOIN applications a
    ON j.job_id = a.job_id
LEFT JOIN placements p
    ON a.application_id = p.application_id
GROUP BY
    j.job_id,
    j.required_slots
HAVING COUNT(p.placement_id) > j.required_slots;


-- 4. 推薦日前に職場見学設定されていないか
SELECT
    w.visit_id,
    a.recommendation_date,
    w.scheduled_date
FROM workplace_visits w
JOIN applications a
    ON w.application_id = a.application_id
WHERE w.scheduled_date < a.recommendation_date;


-- 5. 就業決定日が応募意思確認日より前ではないか
SELECT
    p.placement_id,
    a.intent_confirmed_date,
    p.decision_date
FROM placements p
JOIN applications a
    ON p.application_id = a.application_id
WHERE p.decision_date < a.intent_confirmed_date;