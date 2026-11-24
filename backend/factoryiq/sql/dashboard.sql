WITH selected AS (
    SELECT * FROM equipment WHERE CAST(:machine AS integer) IS NULL OR id=:machine
),
periods AS (
    SELECT 'current' AS period, CAST(:start AS timestamptz) AS start_at, CAST(:end AS timestamptz) AS end_at
    UNION ALL SELECT 'previous',CAST(:previous AS timestamptz),CAST(:start AS timestamptz)
),
windows AS (
    SELECT p.*, e.id AS equipment_id, greatest(p.start_at,e.commissioned_on::timestamp AT TIME ZONE 'UTC') AS eligible_start
    FROM periods p CROSS JOIN selected e
    WHERE e.commissioned_on::timestamp AT TIME ZONE 'UTC' < p.end_at
),
per_machine AS (
    SELECT w.period,w.equipment_id,
        extract(epoch FROM w.end_at-w.eligible_start)/60 AS calendar_minutes,
        coalesce(sum(extract(epoch FROM upper(merged.span)-lower(merged.span)))/60,0) AS downtime_minutes
    FROM windows w LEFT JOIN LATERAL (
        SELECT unnest(range_agg(tstzrange(greatest(d.started_at,w.eligible_start),least(d.ended_at,w.end_at)))) AS span
        FROM downtime_events d WHERE d.equipment_id=w.equipment_id
            AND d.started_at<w.end_at AND d.ended_at>w.eligible_start
    ) merged ON true
    GROUP BY w.period,w.equipment_id,w.end_at,w.eligible_start
),
uptime AS (
    SELECT period,sum(calendar_minutes) AS eligible,sum(downtime_minutes) AS downtime FROM per_machine GROUP BY period
),
quality AS (
    SELECT p.period,count(i.id) AS inspections,count(i.id) FILTER (WHERE NOT i.passed) AS rejected
    FROM periods p LEFT JOIN (quality_inspections i JOIN production_batches b ON i.batch_id=b.id
        JOIN selected e ON e.id=b.equipment_id) ON i.inspected_at>=p.start_at AND i.inspected_at<p.end_at
    GROUP BY p.period
),
faults AS (
    SELECT p.period,count(*) FILTER (WHERE s.fault_code IS NOT NULL) AS fault_events
    FROM periods p LEFT JOIN (sorter_fault_events s JOIN selected e ON e.id=s.equipment_id)
        ON s.occurred_at>=p.start_at AND s.occurred_at<p.end_at GROUP BY p.period
)
SELECT p.period,
       (SELECT count(*) FROM selected) AS equipment_total,
       (SELECT count(*) FROM selected WHERE status='operational') AS equipment_operational,
       (SELECT count(*) FROM selected WHERE status='maintenance') AS equipment_maintenance,
       coalesce(round(u.downtime,2),0) AS downtime_minutes,
       round(100*(1-u.downtime/nullif(u.eligible,0)),2) AS availability,
       q.inspections, q.rejected,
       round(100.0*q.rejected/nullif(q.inspections,0),2) AS defect_rate,
       round(100.0*(q.inspections-q.rejected)/nullif(q.inspections,0),2) AS pass_rate,
       (SELECT count(*) FROM inventory_availability WHERE available>0) AS stocked_parts,
       (SELECT count(*) FROM inventory_availability) AS total_parts,
       (SELECT count(*) FROM inventory_availability WHERE low_stock) AS low_stock,
       (SELECT count(*) FROM non_conformance_reports n JOIN selected e ON e.id=n.equipment_id WHERE n.status<>'closed') AS open_reports,
       (SELECT count(*) FROM maintenance_queue m JOIN selected e ON e.id=m.equipment_id WHERE overdue) AS overdue_orders,
       f.fault_events
FROM periods p LEFT JOIN uptime u USING(period) JOIN quality q USING(period) JOIN faults f USING(period)
