SELECT s.name AS supplier,count(*) AS inspections,count(*) FILTER (WHERE NOT i.passed) AS rejected,
       round(100.0*count(*) FILTER (WHERE NOT i.passed)/count(*),2) AS defect_rate
FROM quality_inspections i JOIN parts p ON p.id=i.part_id JOIN suppliers s ON s.id=p.supplier_id
GROUP BY s.id ORDER BY defect_rate DESC,inspections DESC,s.name
