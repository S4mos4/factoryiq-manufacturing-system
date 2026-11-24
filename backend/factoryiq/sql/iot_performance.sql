-- The sample interval is [observed_at - interval_seconds, observed_at).
-- Use complete intervals only. Missing observations are reported separately.
WITH samples AS (
    SELECT r.*
    FROM iot_readings r
    WHERE r.device_id=:device AND r.observed_at>:start AND r.observed_at<=:end
      AND r.observed_at-make_interval(secs=>r.interval_seconds)>=:start
), totals AS (
    SELECT count(*) AS samples, sum(interval_seconds) AS observed_seconds,
           sum(interval_seconds) FILTER (WHERE run_seconds IS NOT NULL) AS planned_seconds,
           sum(run_seconds) AS operating_seconds,
           sum(run_seconds) FILTER (WHERE produced IS NOT NULL) AS counted_operating_seconds,
           sum(produced) AS production_count,
           sum(produced) FILTER (WHERE good IS NOT NULL) AS inspected_count,
           sum(good) AS good_count,
           sum(power_w*interval_seconds)/3600000.0 AS energy_kwh,
           sum(interval_seconds) FILTER (WHERE power_w IS NOT NULL) AS energy_seconds,
           sum(interval_seconds) FILTER (WHERE produced IS NOT NULL) AS count_seconds
    FROM samples
), episodes AS (
    SELECT count(*) AS failures,
           avg(extract(epoch FROM resolved_at-first_at)) FILTER (WHERE resolved_at<=:end) AS mttr_seconds
    FROM iot_alarms
    WHERE device_id=:device AND code LIKE 'fault:%' AND first_at>=:start AND first_at<:end
), metrics AS (
    SELECT t.*, episodes.*, t.good_count::double precision/nullif(t.inspected_count,0) AS quality,
           t.operating_seconds::double precision/nullif(t.planned_seconds,0) AS availability,
           CASE WHEN t.counted_operating_seconds=t.operating_seconds THEN
              d.ideal_cycle_seconds*t.production_count/nullif(t.operating_seconds,0) END AS performance
    FROM totals t CROSS JOIN episodes JOIN iot_devices d ON d.id=:device
)
SELECT *,
       CASE WHEN production_count=inspected_count AND planned_seconds=observed_seconds THEN
            100*availability*performance*quality END AS oee_percent,
       availability*100 AS availability_percent, performance*100 AS performance_percent, quality*100 AS quality_percent,
       operating_seconds::double precision/nullif(failures,0) AS mtbf_seconds,
       planned_seconds-operating_seconds AS downtime_seconds,
       production_count*3600.0/nullif(count_seconds,0) AS units_per_hour,
       100*observed_seconds/nullif(extract(epoch FROM CAST(:end AS timestamptz)-CAST(:start AS timestamptz)),0) AS coverage_percent
FROM metrics
