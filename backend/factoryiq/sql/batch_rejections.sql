SELECT b.code AS batch,p.sku,e.code AS equipment,count(*) AS inspections,
       count(*) FILTER (WHERE NOT i.passed) AS rejected,
       round(100.0*count(*) FILTER (WHERE NOT i.passed)/count(*),2) AS rejection_rate
FROM quality_inspections i JOIN production_batches b ON b.id=i.batch_id
JOIN parts p ON p.id=b.part_id JOIN equipment e ON e.id=b.equipment_id
GROUP BY b.id,p.id,e.id ORDER BY rejection_rate DESC,inspections DESC,b.code
