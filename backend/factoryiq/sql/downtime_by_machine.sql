WITH intervals AS (
    SELECT d.equipment_id,
           range_agg(tstzrange(greatest(d.started_at,CAST(:start AS timestamptz)),
                               least(d.ended_at,CAST(:end AS timestamptz)))) AS spans
    FROM downtime_events d
    WHERE d.started_at<:end AND d.ended_at>:start
      AND (CAST(:machine AS integer) IS NULL OR d.equipment_id=:machine)
    GROUP BY d.equipment_id
)
SELECT e.code AS equipment,e.name,
       round(sum(extract(epoch FROM upper(span)-lower(span)))/60,2) AS downtime_minutes
FROM intervals i JOIN equipment e ON e.id=i.equipment_id CROSS JOIN LATERAL unnest(i.spans) AS span
GROUP BY e.id ORDER BY downtime_minutes DESC,e.code
