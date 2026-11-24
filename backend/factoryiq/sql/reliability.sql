WITH intervals AS (
    SELECT equipment_id,unnest(range_agg(tstzrange(started_at,ended_at))) AS span
    FROM downtime_events GROUP BY equipment_id
),
episodes AS (
    SELECT equipment_id,lower(span) AS started_at,upper(span) AS ended_at,
           lag(lower(span)) OVER (PARTITION BY equipment_id ORDER BY lower(span)) AS previous_start
    FROM intervals
)
SELECT e.code AS equipment,count(*) AS recorded_failures,
       round(avg(extract(epoch FROM f.started_at-f.previous_start))/3600,2) AS avg_start_to_start_hours,
       round(avg(extract(epoch FROM f.ended_at-f.started_at))/60,2) AS avg_repair_minutes
FROM episodes f JOIN equipment e ON e.id=f.equipment_id GROUP BY e.id ORDER BY e.code
