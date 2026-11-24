SELECT date_bin(make_interval(secs=>:bucket),observed_at,'2000-01-01T00:00:00Z'::timestamptz) AS observed_at,
       avg(temperature_c) AS temperature_c,avg(vibration_g) AS vibration_g,avg(rpm) AS rpm,
       avg(current_a) AS current_a,avg(voltage_v) AS voltage_v,avg(power_w) AS power_w,
       sum(produced) AS produced,count(*) AS samples
FROM iot_readings
WHERE device_id=:device AND observed_at>:start AND observed_at<=:end
GROUP BY 1 ORDER BY 1
