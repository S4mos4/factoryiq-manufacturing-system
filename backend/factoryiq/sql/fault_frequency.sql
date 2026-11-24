SELECT e.code AS equipment,s.fault_code,count(*) AS occurrences,max(s.occurred_at) AS latest
FROM sorter_fault_events s JOIN equipment e ON e.id=s.equipment_id
WHERE s.fault_code IS NOT NULL AND s.occurred_at>=:start AND s.occurred_at<:end
  AND (CAST(:machine AS integer) IS NULL OR s.equipment_id=:machine)
GROUP BY e.code,s.fault_code ORDER BY occurrences DESC,e.code,s.fault_code
