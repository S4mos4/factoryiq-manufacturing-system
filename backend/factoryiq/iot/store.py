from datetime import UTC, datetime, timedelta

from ..db import engine, one, query, rows
from .protocol import METRICS, SIMULATED_STATIONS, TIMEOUT_SECONDS


def provision_simulation():
    with engine().begin() as conn:
        for device,code,name,position,cycle in SIMULATED_STATIONS:
            query(conn,"""INSERT INTO iot_devices(id,equipment_id,station_name,station_order,simulated,ideal_cycle_seconds)
                          SELECT :device,id,:name,:position,true,:cycle FROM equipment WHERE code=:code
                          ON CONFLICT (id) DO NOTHING""",device=device,code=code,name=name,position=position,cycle=cycle)
            query(conn,"""INSERT INTO iot_thresholds(device_id,metric,warning,critical)
                          SELECT id,m,w,c FROM iot_devices CROSS JOIN
                          (VALUES ('temperature_c',65,80),('vibration_g',1.8,3.2),('current_a',14,19)) AS defaults(m,w,c)
                          WHERE id=:device ON CONFLICT DO NOTHING""",device=device)


def record_alarm_history(conn, alarm_id, action, actor=None):
    query(conn,"INSERT INTO iot_alarm_history (alarm_id,action,actor_id) VALUES (:id,:action,:actor)",
          id=alarm_id,action=action,actor=actor)


def reconcile_alarms(conn, device, stamp, scope, signals, consecutive=2):
    active = {entry["code"]:entry for entry in rows(conn,"""SELECT id,code,severity,clear_count
             FROM iot_alarms WHERE device_id=:id AND resolved_at IS NULL AND code LIKE :prefix FOR UPDATE""",
             id=device["id"],prefix=scope+"%")}
    for code,severity in signals.items():
        prior = active.pop(code,None)
        if prior is None:
            alarm = query(conn,"""INSERT INTO iot_alarms (device_id,code,severity,first_at,last_at,work_order_id)
                       VALUES (:id,:code,:severity,:stamp,:stamp,
                       (SELECT id FROM maintenance_queue WHERE equipment_id=:equipment AND status<>'complete'
                        ORDER BY due_on,id LIMIT 1)) RETURNING id""",id=device["id"],equipment=device["equipment_id"],
                       code=code,severity=severity,stamp=stamp).scalar_one()
            record_alarm_history(conn,alarm,"opened")
        else:
            escalated = severity=="critical" and prior["severity"]=="warning"
            query(conn,"""UPDATE iot_alarms SET last_at=greatest(last_at,:stamp),clear_count=0,
                          severity=CASE WHEN :escalated THEN 'critical' ELSE severity END WHERE id=:id""",
                  stamp=stamp,id=prior["id"],escalated=escalated)
            if escalated:
                record_alarm_history(conn,prior["id"],"escalated")
    for code,prior in active.items():
        # A missing sensor sample cannot demonstrate recovery.
        if code in signals.missing:
            continue
        if prior["clear_count"]+1 >= consecutive:
            query(conn,"UPDATE iot_alarms SET resolved_at=greatest(first_at,:stamp) WHERE id=:id",
                  id=prior["id"],stamp=stamp)
            record_alarm_history(conn,prior["id"],"resolved")
        else:
            query(conn,"UPDATE iot_alarms SET clear_count=clear_count+1 WHERE id=:id",id=prior["id"])


class Signals(dict):
    def __init__(self, values=(), missing=()):
        super().__init__(values)
        self.missing = set(missing)


def save_reading(message):
    with engine().begin() as conn:
        device = one(conn,"SELECT * FROM iot_devices WHERE id=:id FOR UPDATE",id=message.device_id)
        if device is None:
            return "unknown_device"
        if one(conn,"""SELECT 1 FROM iot_readings WHERE device_id=:id AND
                       (message_id=:message OR observed_at=:stamp) LIMIT 1""",
               id=message.device_id,message=message.message_id,stamp=message.observed_at):
            return "duplicate"
        start = message.observed_at - timedelta(seconds=message.interval_seconds)
        if one(conn,"""SELECT 1 FROM iot_readings WHERE device_id=:id AND observed_at>:start
                       AND observed_at<:limit AND observed_at-make_interval(secs=>interval_seconds)<:stamp LIMIT 1""",
               id=message.device_id,start=start,limit=message.observed_at+timedelta(seconds=60),
               stamp=message.observed_at):
            return "overlap"
        query(conn,"""INSERT INTO iot_readings (device_id,observed_at,message_id,interval_seconds,run_seconds,status,
                      temperature_c,vibration_g,rpm,current_a,voltage_v,power_w,produced,good,fault)
                      VALUES (:device_id,:observed_at,:message_id,:interval_seconds,:run_seconds,:status,
                              :temperature_c,:vibration_g,:rpm,:current_a,:voltage_v,:power_w,:produced,:good,:fault)""",
              **message.model_dump(exclude={"schema_version"}))
        if device["last_reading_at"] and message.observed_at <= device["last_reading_at"]:
            return "accepted"
        query(conn,"UPDATE iot_devices SET last_reading_at=:stamp WHERE id=:id",
              stamp=message.observed_at,id=message.device_id)
        thresholds = rows(conn,"SELECT metric,warning,critical FROM iot_thresholds WHERE device_id=:id",id=message.device_id)
        signals = Signals(missing=("threshold:"+metric for metric in METRICS if getattr(message,metric) is None))
        for rule in thresholds:
            value = getattr(message,rule["metric"])
            if value is not None and value >= rule["warning"]:
                signals["threshold:"+rule["metric"]] = "critical" if value >= rule["critical"] else "warning"
        reconcile_alarms(conn,device,message.observed_at,"threshold:",signals)
        reconcile_alarms(conn,device,message.observed_at,"fault:",
                         Signals({f"fault:{message.fault}":"critical"} if message.fault else {}),consecutive=1)
        return "accepted"


def set_connectivity(conn, device, online, at):
    query(conn,"UPDATE iot_devices SET connected=:online WHERE id=:id",id=device["id"],online=online)
    query(conn,"INSERT INTO iot_connections (device_id,online,changed_at) VALUES (:id,:online,:at)",
          id=device["id"],online=online,at=at)
    reconcile_alarms(conn,device,at,"link:",Signals({} if online else {"link:offline":"warning"}),consecutive=1)


def save_heartbeat(message):
    with engine().begin() as conn:
        device = one(conn,"SELECT * FROM iot_devices WHERE id=:id FOR UPDATE",id=message.device_id)
        if device is None:
            return "unknown_device"
        at = datetime.now(UTC)
        if (device["last_heartbeat_at"] and message.observed_at <= device["last_heartbeat_at"]) or (
                at-message.observed_at > timedelta(seconds=TIMEOUT_SECONDS)):
            return "stale"
        query(conn,"UPDATE iot_devices SET last_heartbeat_at=:stamp WHERE id=:id",stamp=message.observed_at,id=message.device_id)
        if not device["connected"]:
            set_connectivity(conn,device,True,at)
        return "accepted"


def expire_connections():
    with engine().begin() as conn:
        at = datetime.now(UTC)
        for device in rows(conn,"""SELECT * FROM iot_devices WHERE connected AND last_heartbeat_at < :cutoff
                                   ORDER BY id FOR UPDATE SKIP LOCKED""",cutoff=at-timedelta(seconds=TIMEOUT_SECONDS)):
            set_connectivity(conn,device,False,at)
