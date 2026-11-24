CREATE TABLE iot_devices (
    id text PRIMARY KEY CHECK (id ~ '^[a-z0-9][a-z0-9-]{2,39}$'),
    equipment_id integer NOT NULL REFERENCES equipment(id),
    station_name text NOT NULL,
    station_order integer NOT NULL,
    simulated boolean NOT NULL,
    ideal_cycle_seconds double precision CHECK (ideal_cycle_seconds > 0 AND ideal_cycle_seconds < 86400),
    connected boolean NOT NULL DEFAULT false,
    last_heartbeat_at timestamptz,
    last_reading_at timestamptz
);
CREATE TABLE iot_connections (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    device_id text NOT NULL REFERENCES iot_devices(id),
    online boolean NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX iot_connections_device_time ON iot_connections(device_id,changed_at DESC);
CREATE TABLE iot_readings (
    device_id text NOT NULL REFERENCES iot_devices(id),
    observed_at timestamptz NOT NULL,
    message_id uuid NOT NULL,
    interval_seconds integer NOT NULL CHECK (interval_seconds BETWEEN 1 AND 60),
    run_seconds integer CHECK (run_seconds BETWEEN 0 AND interval_seconds),
    status text NOT NULL CHECK (status IN ('running','idle','fault','stopped','unknown')),
    temperature_c double precision CHECK (temperature_c BETWEEN -80 AND 250),
    vibration_g double precision CHECK (vibration_g BETWEEN 0 AND 50),
    rpm double precision CHECK (rpm BETWEEN 0 AND 50000),
    current_a double precision CHECK (current_a BETWEEN 0 AND 500),
    voltage_v double precision CHECK (voltage_v BETWEEN 0 AND 1000),
    power_w double precision CHECK (power_w BETWEEN 0 AND 500000),
    produced integer CHECK (produced BETWEEN 0 AND 100000),
    good integer CHECK (good BETWEEN 0 AND produced),
    fault text CHECK (fault IN ('overheat','vibration','jam','overcurrent','shutdown','sensor_disconnected')),
    PRIMARY KEY (device_id,observed_at),
    UNIQUE (device_id,message_id),
    CHECK (good IS NULL OR produced IS NOT NULL)
);
CREATE INDEX iot_readings_time_brin ON iot_readings USING brin(observed_at);
CREATE TABLE iot_thresholds (
    device_id text NOT NULL REFERENCES iot_devices(id),
    metric text NOT NULL CHECK (metric IN ('temperature_c','vibration_g','rpm','current_a','voltage_v','power_w')),
    warning double precision NOT NULL,
    critical double precision NOT NULL,
    PRIMARY KEY (device_id,metric),
    CHECK (warning >= 0 AND warning < critical AND critical < 1000000)
);
CREATE TABLE iot_alarms (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    device_id text NOT NULL REFERENCES iot_devices(id),
    code text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('warning','critical')),
    first_at timestamptz NOT NULL,
    last_at timestamptz NOT NULL,
    resolved_at timestamptz,
    acknowledged_at timestamptz,
    acknowledged_by integer REFERENCES users(id),
    work_order_id integer REFERENCES maintenance_work_orders(id),
    clear_count integer NOT NULL DEFAULT 0,
    CHECK (last_at >= first_at AND (resolved_at IS NULL OR resolved_at >= first_at)),
    CHECK ((acknowledged_at IS NULL) = (acknowledged_by IS NULL))
);
CREATE UNIQUE INDEX iot_active_alarm ON iot_alarms(device_id,code) WHERE resolved_at IS NULL;
CREATE INDEX iot_alarms_device_time ON iot_alarms(device_id,first_at DESC);
CREATE TABLE iot_alarm_history (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    alarm_id bigint NOT NULL REFERENCES iot_alarms(id),
    action text NOT NULL CHECK (action IN ('opened','escalated','acknowledged','resolved')),
    at timestamptz NOT NULL DEFAULT now(),
    actor_id integer REFERENCES users(id)
);
CREATE INDEX iot_alarm_history_id ON iot_alarm_history(alarm_id,id);
CREATE TABLE iot_simulation_controls (
    device_id text PRIMARY KEY REFERENCES iot_devices(id),
    fault text NOT NULL CHECK (fault IN ('normal','overheat','vibration','jam','overcurrent','shutdown','sensor_disconnected','communication_failure')),
    expires_at timestamptz NOT NULL
);
