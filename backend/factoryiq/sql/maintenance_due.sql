SELECT equipment,title,kind,scheduled_on,due_on,status,overdue
FROM maintenance_queue WHERE status<>'complete'
ORDER BY overdue DESC,due_on,equipment,id
