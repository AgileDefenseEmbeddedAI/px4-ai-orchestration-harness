"""
Pydantic v2 data models for the PX4 AI Orchestration Harness.

Covers:
  - MIG  (Mission Intent Graph) — the canonical mission representation
  - VAL  (Vehicle Action List)  — per-vehicle action sequence sent to dispatch
  - Plan (Per-Vehicle Plan)     — expanded PX4 MAV_CMD primitives per vehicle
  - Supporting types: Vehicle, Waypoint, Constraints, ContingencyRung,
    ConditionalBranch, enums, request/response bodies
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class MissionStatus(str, Enum):
    planning = "planning"
    validation_failed = "validation_failed"
    pending_authorization = "pending_authorization"
    authorized = "authorized"
    dispatching = "dispatching"
    dispatched = "dispatched"
    failed = "failed"


class VehicleType(str, Enum):
    multirotor = "multirotor"
    rover = "rover"


# ---------------------------------------------------------------------------
# Vehicle Action List (VAL) — sent to dispatch transports
# ---------------------------------------------------------------------------


class VehicleAction(BaseModel):
    action_type: str
    waypoint: Optional[dict] = None
    parameters: Optional[dict] = None


class VAL(BaseModel):
    version: str = "1.0"
    mission_id: str
    vehicle_id: str
    vehicle_type: VehicleType
    actions: list[VehicleAction] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Mission Intent Graph (MIG) — internal canonical plan
# ---------------------------------------------------------------------------


class WaypointTiming(BaseModel):
    earliest_sec: Optional[float] = None
    latest_sec: Optional[float] = None
    dwell_sec: Optional[float] = None


class Waypoint(BaseModel):
    id: str
    lat: float
    lon: float
    alt_m: float
    role: str  # e.g. "survey", "loiter", "perimeter", "rtl"
    timing: Optional[WaypointTiming] = None


class Vehicle(BaseModel):
    id: str
    vehicle_type: VehicleType
    sitl_target: str
    mavlink_sysid: int
    waypoints: list[str] = Field(default_factory=list)  # ordered list of Waypoint IDs


class Constraints(BaseModel):
    geofence_polygon: list[list[float]] = Field(default_factory=list)  # [[lat, lon], ...]
    max_alt_m: float = 120.0
    min_alt_m: float = 2.0
    require_rtl: bool = True
    max_range_m: float = 5000.0


class ContingencyAction(BaseModel):
    action_type: str
    vehicle_id: Optional[str] = None
    waypoint_id: Optional[str] = None
    parameters: Optional[dict] = None


class ContingencyRung(BaseModel):
    trigger: str
    priority: int = 100
    actions: list[ContingencyAction] = Field(default_factory=list)


class ConditionalBranch(BaseModel):
    condition: str
    if_vehicle_id: str
    then: list[ContingencyAction] = Field(default_factory=list)
    else_: list[ContingencyAction] = Field(default_factory=list, alias="else")

    model_config = {"populate_by_name": True}


class MIG(BaseModel):
    version: str = "1.1"
    mission_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    intent: str
    vehicles: list[Vehicle] = Field(default_factory=list)
    waypoints: list[Waypoint] = Field(default_factory=list)
    constraints: Constraints = Field(default_factory=Constraints)
    status: MissionStatus = MissionStatus.planning
    validation_errors: list[str] = Field(default_factory=list)
    contingency_ladder: list[ContingencyRung] = Field(default_factory=list)
    conditional_branches: list[ConditionalBranch] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-Vehicle Plan — expanded PX4 MAV_CMD primitives (produced by plan_decomposer)
# ---------------------------------------------------------------------------


class MavCommand(BaseModel):
    seq: int
    mav_cmd: str
    mav_cmd_id: int
    role: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    alt_m: Optional[float] = None
    param1: Optional[float] = None
    param2: Optional[float] = None
    param3: Optional[float] = None
    param4: Optional[float] = None


class Plan(BaseModel):
    version: str = "1.0"
    mission_id: str
    vehicle_id: str
    vehicle_type: VehicleType
    commands: list[MavCommand] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API request / response bodies
# ---------------------------------------------------------------------------


class IntentRequest(BaseModel):
    text: str = Field(min_length=10, description="Natural-language mission intent")


class AuthorizeRequest(BaseModel):
    authorized: bool
    operator: str = Field(min_length=1, description="Operator name or callsign")


class MissionResponse(BaseModel):
    mission_id: str
    status: MissionStatus
    mig: Optional[MIG] = None
    validation_errors: list[str] = Field(default_factory=list)
    authorized_at: Optional[datetime] = None
    authorized_by: Optional[str] = None
