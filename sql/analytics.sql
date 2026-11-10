-- Product metrics on the app's own tables. Nothing here needs simulated truth, so
-- the same queries work on the running app. A5 adds per-arm experiment metrics.

-- name: funnel_by_day
SELECT
    (started_at AT TIME ZONE 'UTC')::date                 AS day,
    count(*)                                              AS started,
    count(*) FILTER (WHERE status = 'done')               AS done,
    count(*) FILTER (WHERE status = 'abandoned')          AS abandoned,
    count(*) FILTER (WHERE status = 'open')               AS still_open,
    (count(*) FILTER (WHERE status = 'done'))::float8 / count(*) AS completion_rate
FROM ranking_insertion
GROUP BY day
ORDER BY day;

-- name: contradictions_by_user
-- Which users contradict themselves most? Quartile 4 is the least consistent.
WITH bounds AS (
    SELECT
        insertion_id,
        min(ref_position) FILTER (WHERE answer = 'better') AS lowest_better,
        max(ref_position) FILTER (WHERE answer = 'worse')  AS highest_worse
    FROM ranking_comparison
    GROUP BY insertion_id
),
per_user AS (
    SELECT
        l.owner_id,
        count(*) AS insertions,
        avg((COALESCE(b.highest_worse >= b.lowest_better, false))::int)::float8 AS contradiction_rate
    FROM ranking_insertion AS i
    JOIN ranking_ranklist AS l ON l.id = i.list_id
    JOIN bounds AS b ON b.insertion_id = i.id
    WHERE i.status = 'done'
    GROUP BY l.owner_id
)
SELECT
    owner_id,
    insertions,
    contradiction_rate,
    ntile(4) OVER (ORDER BY contradiction_rate, owner_id) AS quartile
FROM per_user
ORDER BY contradiction_rate DESC, owner_id;

-- name: place_percentile_across_lists
-- Where each place tends to land: its percent rank within each list, averaged.
WITH ranked AS (
    SELECT
        place_id,
        1 - percent_rank() OVER (PARTITION BY list_id ORDER BY position) AS percentile
    FROM ranking_listentry
)
SELECT
    p.id                       AS place_id,
    p.name,
    p.city,
    count(*)                   AS lists,
    avg(r.percentile)::float8  AS mean_percentile
FROM ranked AS r
JOIN ranking_place AS p ON p.id = r.place_id
GROUP BY p.id, p.name, p.city
ORDER BY mean_percentile DESC, p.id;
