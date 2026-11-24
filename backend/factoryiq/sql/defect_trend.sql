WITH days AS (
    SELECT generate_series(CAST(:start AS timestamptz),CAST(:end AS timestamptz)-interval '1 day',interval '1 day') AS day
),
counts AS (
    SELECT date_trunc('day',i.inspected_at,'UTC') AS day,count(*) AS inspections,
           count(*) FILTER (WHERE NOT i.passed) AS defects
    FROM quality_inspections i JOIN production_batches b ON b.id=i.batch_id
    WHERE i.inspected_at>=:start AND i.inspected_at<:end
      AND (CAST(:machine AS integer) IS NULL OR b.equipment_id=:machine)
    GROUP BY 1
),
daily AS (
    SELECT (days.day AT TIME ZONE 'UTC')::date AS day,
           coalesce(c.inspections,0) AS inspections,coalesce(c.defects,0) AS defects
    FROM days LEFT JOIN counts c USING(day)
)
SELECT day,inspections,defects,round(100.0*defects/nullif(inspections,0),2) AS defect_rate,
       round(100.0*sum(defects) OVER week/nullif(sum(inspections) OVER week,0),2) AS rolling_rate
FROM daily WINDOW week AS (ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) ORDER BY day
