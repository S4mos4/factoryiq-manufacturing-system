from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints, field_validator, model_validator

from ..common import Input

DeviceId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{2,39}$")]
Fault = Literal["overheat", "vibration", "jam", "overcurrent", "shutdown", "sensor_disconnected"]
SimFault = Literal["normal", "overheat", "vibration", "jam", "overcurrent", "shutdown",
                   "sensor_disconnected", "communication_failure"]
Metric = Literal["temperature_c", "vibration_g", "rpm", "current_a", "voltage_v", "power_w"]
METRICS = ("temperature_c", "vibration_g", "rpm", "current_a", "voltage_v", "power_w")
TIMEOUT_SECONDS = 12
TOPIC_PREFIX = "factoryiq/device"
MAX_PAYLOAD = 4096
SIMULATED_STATIONS = (
    ("sim-conveyor", "EQ-103", "Feed conveyor", 1, 0.85),
    ("sim-sorter", "EQ-105", "Vision sorter", 2, 1.00),
    ("sim-robot", "EQ-104", "Robot assembly", 3, 1.25),
    ("sim-hydraulic", "EQ-109", "Hydraulic press", 4, 1.25),
    ("sim-line", "EQ-115", "Line outfeed", 5, 1.00),
    ("sim-motor", "EQ-101", "Drive motor", 6, None),
)


class Heartbeat(Input):
    schema_version: Literal[1]
    device_id: DeviceId
    observed_at: AwareDatetime

    @field_validator("observed_at")
    @classmethod
    def reject_future(cls, stamp):
        if stamp > datetime.now(UTC) + timedelta(seconds=10):
            raise ValueError("Timestamp exceeds the allowed clock skew.")
        return stamp.astimezone(UTC)


class Reading(Heartbeat):
    message_id: UUID
    interval_seconds: Annotated[int, Field(strict=True, ge=1, le=60)]
    run_seconds: Annotated[int, Field(strict=True, ge=0, le=60)] | None = None
    status: Literal["running", "idle", "fault", "stopped", "unknown"]
    temperature_c: Annotated[float, Field(ge=-80, le=250, allow_inf_nan=False)] | None = None
    vibration_g: Annotated[float, Field(ge=0, le=50, allow_inf_nan=False)] | None = None
    rpm: Annotated[float, Field(ge=0, le=50000, allow_inf_nan=False)] | None = None
    current_a: Annotated[float, Field(ge=0, le=500, allow_inf_nan=False)] | None = None
    voltage_v: Annotated[float, Field(ge=0, le=1000, allow_inf_nan=False)] | None = None
    power_w: Annotated[float, Field(ge=0, le=500000, allow_inf_nan=False)] | None = None
    produced: Annotated[int, Field(strict=True, ge=0, le=100000)] | None = None
    good: Annotated[int, Field(strict=True, ge=0, le=100000)] | None = None
    fault: Fault | None = None

    @model_validator(mode="after")
    def validate_interval(self):
        if self.run_seconds is not None and self.run_seconds > self.interval_seconds:
            raise ValueError("Run seconds cannot exceed the sample interval.")
        if self.good is not None and (self.produced is None or self.good > self.produced):
            raise ValueError("Good count cannot exceed production count.")
        return self
