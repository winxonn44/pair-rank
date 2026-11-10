-- Metrics on simulated sessions, in the app's own schema. Each query is checked
-- against an independent pandas version (scripts/pandas_metrics.py).
-- sim_truth holds what only a simulation knows: where each place truly belongs.

-- name: questions_per_insertion
-- Completed insertions only. Long insertions are more likely to be abandoned, so
-- under a nonzero quit rate these run slightly below the no-abandonment figures.
SELECT
    strategy,
    count(*)                                                   AS insertions,
    sum(n_questions)                                           AS total_questions,
    avg(n_questions)::float8                                   AS mean_questions,
    stddev_samp(n_questions)::float8                           AS sd_questions,
    percentile_disc(0.5) WITHIN GROUP (ORDER BY n_questions)   AS p50_questions,
    percentile_disc(0.95) WITHIN GROUP (ORDER BY n_questions)  AS p95_questions,
    max(n_questions)                                           AS max_questions
FROM ranking_insertion
WHERE status = 'done'
GROUP BY strategy
ORDER BY strategy;

-- name: error_by_strategy
WITH errors AS (
    SELECT i.strategy, abs(i.final_position - t.true_slot) AS error
    FROM ranking_insertion AS i
    JOIN sim_truth AS t ON t.insertion_id = i.id
    WHERE i.status = 'done'
)
SELECT
    strategy,
    count(*)                                             AS insertions,
    sum(error)                                           AS total_error,
    avg(error)::float8                                   AS mean_error,
    avg((error = 0)::int)::float8                        AS exact_rate,
    avg((error <= 1)::int)::float8                       AS within_one_rate,
    percentile_disc(0.95) WITHIN GROUP (ORDER BY error)  AS p95_error,
    max(error)                                           AS max_error
FROM errors
GROUP BY strategy
ORDER BY strategy;

-- name: contradiction_rate
-- "Better than position j" means the slot is at or above j; "worse than position k"
-- means it is below k. Both can only be true if k < j, so a completed insertion
-- contradicts itself when its highest "worse" is at or past its lowest "better".
WITH bounds AS (
    SELECT
        insertion_id,
        min(ref_position) FILTER (WHERE answer = 'better') AS lowest_better,
        max(ref_position) FILTER (WHERE answer = 'worse')  AS highest_worse
    FROM ranking_comparison
    GROUP BY insertion_id
)
SELECT
    i.strategy,
    count(*)                                                   AS insertions,
    count(*) FILTER (WHERE b.highest_worse >= b.lowest_better) AS contradicted,
    (count(*) FILTER (WHERE b.highest_worse >= b.lowest_better))::float8
        / count(*)                                             AS contradiction_rate
FROM ranking_insertion AS i
JOIN bounds AS b ON b.insertion_id = i.id
WHERE i.status = 'done'
GROUP BY i.strategy
ORDER BY i.strategy;

-- name: abandonment_funnel
SELECT
    strategy,
    count(*)                                      AS started,
    count(*) FILTER (WHERE n_questions > 0)       AS answered_first,
    count(*) FILTER (WHERE status = 'done')       AS done,
    count(*) FILTER (WHERE status = 'abandoned')  AS abandoned,
    (count(*) FILTER (WHERE status = 'done'))::float8 / count(*) AS completion_rate
FROM ranking_insertion
GROUP BY strategy
ORDER BY strategy;

-- name: dropoff_by_question
-- An insertion was asked question q if it answered it, or quit while looking at it.
WITH asked AS (
    SELECT
        i.strategy,
        g.q,
        (i.status = 'abandoned' AND g.q = i.n_questions) AS quit
    FROM ranking_insertion AS i
    CROSS JOIN LATERAL generate_series(
        0,
        CASE WHEN i.status = 'abandoned' THEN i.n_questions ELSE i.n_questions - 1 END
    ) AS g(q)
),
by_question AS (
    SELECT strategy, q, count(*) AS asked, count(*) FILTER (WHERE quit) AS quit_here
    FROM asked
    GROUP BY strategy, q
)
SELECT
    strategy,
    q,
    asked,
    quit_here,
    quit_here::float8 / asked                                        AS hazard,
    (sum(quit_here) OVER (PARTITION BY strategy ORDER BY q))::bigint AS cumulative_quits
FROM by_question
ORDER BY strategy, q;

-- name: error_by_session_position
-- Does error build up as a session goes on? Position is each user's kth attempt.
WITH numbered AS (
    SELECT
        i.strategy,
        i.status,
        i.final_position,
        i.id,
        row_number() OVER (PARTITION BY i.list_id ORDER BY i.id) AS session_position
    FROM ranking_insertion AS i
)
SELECT
    n.strategy,
    n.session_position,
    count(*)                                    AS insertions,
    avg(abs(n.final_position - t.true_slot))::float8 AS mean_error
FROM numbered AS n
JOIN sim_truth AS t ON t.insertion_id = n.id
WHERE n.status = 'done'
GROUP BY n.strategy, n.session_position
ORDER BY n.strategy, n.session_position;

-- name: per_user_ab
-- The user is the unit of analysis: one mean per user, then Welch's t against binary.
WITH user_means AS (
    SELECT i.strategy, i.list_id, avg(abs(i.final_position - t.true_slot))::float8 AS mean_error
    FROM ranking_insertion AS i
    JOIN sim_truth AS t ON t.insertion_id = i.id
    WHERE i.status = 'done'
    GROUP BY i.strategy, i.list_id
),
arms AS (
    SELECT strategy, count(*) AS users, avg(mean_error) AS mean, var_samp(mean_error) AS variance
    FROM user_means
    GROUP BY strategy
)
SELECT
    treatment.strategy                                             AS strategy,
    treatment.users                                                AS users,
    control.mean                                                   AS control_mean_error,
    treatment.mean                                                 AS treatment_mean_error,
    treatment.mean - control.mean                                  AS difference,
    sqrt(treatment.variance / treatment.users + control.variance / control.users) AS standard_error,
    (treatment.mean - control.mean)
        / sqrt(treatment.variance / treatment.users + control.variance / control.users) AS welch_t
FROM arms AS treatment
CROSS JOIN arms AS control
WHERE control.strategy = 'binary' AND treatment.strategy <> 'binary'
ORDER BY treatment.strategy;

-- name: list_integrity
-- After every insertion, a list must be exactly positions 0..n-1 at the right version.
WITH per_list AS (
    SELECT
        l.id,
        l.version,
        count(e.id)                      AS entries,
        min(e.position)                  AS first_position,
        max(e.position)                  AS last_position,
        count(DISTINCT e.position)       AS distinct_positions
    FROM ranking_ranklist AS l
    JOIN ranking_listentry AS e ON e.list_id = l.id
    GROUP BY l.id, l.version
),
completed AS (
    SELECT list_id, count(*) FILTER (WHERE status = 'done') AS done
    FROM ranking_insertion
    GROUP BY list_id
)
SELECT
    count(*) AS lists,
    count(*) FILTER (
        WHERE p.first_position <> 0
           OR p.last_position <> p.entries - 1
           OR p.distinct_positions <> p.entries
    ) AS not_contiguous,
    count(*) FILTER (WHERE p.version <> c.done) AS wrong_version
FROM per_list AS p
JOIN completed AS c ON c.list_id = p.id;
