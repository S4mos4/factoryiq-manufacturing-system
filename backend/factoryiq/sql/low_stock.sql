SELECT sku,name,supplier,available,reorder_point,reorder_point-available AS shortage
FROM inventory_availability WHERE low_stock ORDER BY shortage DESC,sku
