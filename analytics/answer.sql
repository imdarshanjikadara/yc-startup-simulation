-- Shiptivity analytics: Kanban board release (2018-06-02)
-- Run with: sqlite3 shiptivity.db < answer.sql
-- Timestamps are Unix epoch seconds (UTC). Each query is tagged with "-- @query: <name>"
-- so scripts/generate_charts.py can run the exact same SQL to draw the graphs.


-- PART 1: Create a SQL query that maps out the daily average users before and after the feature change

-- 1a. Daily active users for every calendar day, tagged before/after the release.
--     A recursive calendar fills in days with zero logins so they still count toward the averages.
-- @query: daily_active_users
WITH RECURSIVE
bounds AS (
    SELECT date(MIN(login_timestamp), 'unixepoch') AS first_day,
           date(MAX(login_timestamp), 'unixepoch') AS last_day
    FROM login_history
),
calendar(day) AS (
    SELECT first_day FROM bounds
    UNION ALL
    SELECT date(day, '+1 day') FROM calendar, bounds WHERE day < last_day
),
dau AS (
    SELECT date(login_timestamp, 'unixepoch') AS day,
           COUNT(DISTINCT user_id)             AS active_users
    FROM login_history
    GROUP BY day
)
SELECT calendar.day,
       COALESCE(dau.active_users, 0)                                  AS active_users,
       CASE WHEN calendar.day < '2018-06-02' THEN 'before' ELSE 'after' END AS period
FROM calendar
LEFT JOIN dau ON dau.day = calendar.day
ORDER BY calendar.day;

-- 1b. Average daily active users before vs. after the release (zero-login days included).
-- @query: avg_dau_before_after
WITH RECURSIVE
bounds AS (
    SELECT date(MIN(login_timestamp), 'unixepoch') AS first_day,
           date(MAX(login_timestamp), 'unixepoch') AS last_day
    FROM login_history
),
calendar(day) AS (
    SELECT first_day FROM bounds
    UNION ALL
    SELECT date(day, '+1 day') FROM calendar, bounds WHERE day < last_day
),
dau AS (
    SELECT date(login_timestamp, 'unixepoch') AS day,
           COUNT(DISTINCT user_id)             AS active_users
    FROM login_history
    GROUP BY day
)
SELECT CASE WHEN calendar.day < '2018-06-02' THEN 'before' ELSE 'after' END AS period,
       COUNT(*)                                          AS days,
       ROUND(AVG(COALESCE(dau.active_users, 0)), 2)      AS avg_daily_active_users,
       MAX(COALESCE(dau.active_users, 0))                AS peak_daily_active_users
FROM calendar
LEFT JOIN dau ON dau.day = calendar.day
GROUP BY period
ORDER BY period DESC;

-- 1c. Same comparison over a like-for-like 30-day window either side of the release,
--     which removes the slow ramp-up of early 2018 from the "before" number.
-- @query: avg_dau_30d_window
SELECT CASE WHEN day < '2018-06-02' THEN 'before (2018-05-03 .. 2018-06-01)'
            ELSE 'after (2018-06-02 .. 2018-07-01)' END AS period,
       ROUND(AVG(active_users), 2)                      AS avg_daily_active_users
FROM (
    SELECT date(login_timestamp, 'unixepoch') AS day,
           COUNT(DISTINCT user_id)             AS active_users
    FROM login_history
    WHERE date(login_timestamp, 'unixepoch') BETWEEN '2018-05-03' AND '2018-07-01'
    GROUP BY day
)
GROUP BY period
ORDER BY period DESC;


-- PART 2: Create a SQL query that indicates the number of status changes by card

-- 2a. Number of status changes per card. The first history row for each card
--     (oldStatus IS NULL) is the card being created, so it is not counted as a change.
--     Cards that were never moved are kept with a count of 0.
-- @query: status_changes_by_card
SELECT card.id                                  AS card_id,
       card.name                                AS card_name,
       card.status                              AS current_status,
       COUNT(history.id)                        AS status_changes
FROM card
LEFT JOIN card_change_history AS history
       ON history.cardID = card.id
      AND history.oldStatus IS NOT NULL
      AND history.oldStatus <> history.newStatus
GROUP BY card.id, card.name, card.status
ORDER BY status_changes DESC, card.id;

-- 2b. Number of status changes per day (all cards), split by type of move.
-- @query: status_changes_daily
SELECT date(timestamp, 'unixepoch')                                              AS day,
       COUNT(*)                                                                  AS status_changes,
       SUM(oldStatus = 'backlog'     AND newStatus = 'in-progress')              AS backlog_to_in_progress,
       SUM(oldStatus = 'in-progress' AND newStatus = 'complete')                 AS in_progress_to_complete,
       SUM((oldStatus = 'in-progress' AND newStatus = 'backlog')
        OR (oldStatus = 'complete'    AND newStatus = 'in-progress'))            AS moved_backwards
FROM card_change_history
WHERE oldStatus IS NOT NULL
  AND oldStatus <> newStatus
GROUP BY day
ORDER BY day;

-- 2c. Number of status changes by card per day (one row per card per day it moved).
-- @query: status_changes_by_card_daily
SELECT date(timestamp, 'unixepoch') AS day,
       cardID                       AS card_id,
       COUNT(*)                     AS status_changes
FROM card_change_history
WHERE oldStatus IS NOT NULL
  AND oldStatus <> newStatus
GROUP BY day, cardID
ORDER BY day, cardID;
