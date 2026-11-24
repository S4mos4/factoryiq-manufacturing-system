WITH sample AS (
    SELECT observed_at, temperature_c,vibration_g,current_a
    FROM iot_readings
    WHERE device_id=:device AND observed_at>now()-interval '30 minutes'
), points AS (
    SELECT observed_at, v.metric, v.value
    FROM sample CROSS JOIN LATERAL
       (VALUES ('temperature_c',temperature_c),('vibration_g',vibration_g),('current_a',current_a)) v(metric,value)
    WHERE v.value IS NOT NULL
), signals AS (
    SELECT *, count(*) OVER baseline AS points,
           avg(value) OVER baseline AS moving_average,
           stddev_samp(value) OVER baseline AS stddev,
           lag(value) OVER ordered AS prior_value,
           lag(observed_at) OVER ordered AS prior_at
    FROM points
    WINDOW ordered AS (PARTITION BY metric ORDER BY observed_at),
           baseline AS (PARTITION BY metric ORDER BY observed_at ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING)
), latest AS (
    SELECT DISTINCT ON(metric) *,
      (value-prior_value)/nullif(extract(epoch FROM observed_at-prior_at),0) AS per_second,
      (value-moving_average)/nullif(stddev,0) AS z_score
    FROM signals ORDER BY metric,observed_at DESC
)
SELECT l.metric,l.value,l.observed_at,l.points,l.moving_average,l.stddev,l.per_second,l.z_score,
       t.warning,t.critical,
       CASE WHEN l.observed_at<now()-interval '12 seconds' THEN 'stale'
            WHEN value>=t.critical THEN 'critical threshold'
            WHEN value>=t.warning THEN 'warning threshold'
            WHEN l.observed_at-l.prior_at<=interval '12 seconds'
                 AND abs(per_second)>=CASE l.metric WHEN 'temperature_c' THEN 1 WHEN 'vibration_g' THEN 0.25 ELSE 1.5 END
                 THEN 'rapid change'
            WHEN l.points<8 THEN 'building baseline'
            WHEN abs(z_score)>=3.5 AND abs(value-moving_average)>=
                 CASE l.metric WHEN 'temperature_c' THEN 1.5 WHEN 'vibration_g' THEN 0.12 ELSE 0.8 END
                 THEN 'statistical anomaly'
            ELSE 'normal' END AS assessment
FROM latest l LEFT JOIN iot_thresholds t ON t.device_id=:device AND t.metric=l.metric
ORDER BY l.metric
