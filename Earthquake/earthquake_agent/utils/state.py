"""
State, Data Models, and Defaults

Everything that defines the shape of data in this agent:
  1. DEFAULT_* constants
  2. EarthquakeQueryModel  — typed USGS API query
  3. ValidationResult / validate_query
  4. build_default_model / apply_radius_default / get_default_assumptions
  5. EarthquakeEvent / APIResult  — normalised API output models
  6. APICallLog / AgentEnrichedResponse  — summariser output envelope
  7. State  — LangGraph shared state schema

Workflow:
    build_default_model()
      → normaliser overwrites user fields
      → apply_radius_default()
      → validate_query()
      → EarthquakeQueryModel.to_api_params()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal, Optional

from langgraph.graph.message import AnyMessage, add_messages
from pydantic import BaseModel, Field, model_validator
from typing_extensions import TypedDict


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------

# Time: window to look back when the user gives no date range
DEFAULT_TIMESPAN_DAYS: int = 30

# Geography: radius (km) used when a location is named but no radius given
# 100 km ≈ 62 miles — covers a city and its surrounding region
DEFAULT_RADIUS_KM: float = 100.0

# Magnitude: floor for global (no geography) queries to keep result sizes sane
# 4.5 = regionally felt, meaningful globally
DEFAULT_MIN_MAGNITUDE: float = 4.5

# Event type: filters out blasts, collapses, and other non-earthquake events
DEFAULT_EVENT_TYPE: str = "earthquake"

# Result cap: safe page size, well under the API's 20,000 hard limit
DEFAULT_LIMIT: int = 100


# ---------------------------------------------------------------------------
# EarthquakeQueryModel
# ---------------------------------------------------------------------------

class EarthquakeQueryModel(BaseModel):
    """
    Typed representation of a USGS Earthquake API query.

    Three valid patterns (checked by validate_query):
      - Pattern 1 "global"   : starttime + endtime + minmagnitude
      - Pattern 2 "regional" : starttime + endtime + circle OR bbox
      - Pattern 3 "event"    : eventid only
    """

    # Query endpoint ("/query" or "/count")
    query_type: Literal["/query", "/count"] = "/query"

    # ------------------------------------------------------------------
    # Pattern 3 — single event
    # ------------------------------------------------------------------
    eventid: Optional[str] = Field(
        default=None,
        description="USGS event ID. When set, all other filters are optional.",
    )

    # ------------------------------------------------------------------
    # Time — required for Pattern 1 and 2
    # ------------------------------------------------------------------
    starttime: Optional[str] = Field(
        default=None,
        description="ISO8601 start time (UTC). e.g. '2024-01-01' or '2024-01-01T00:00:00'",
    )
    endtime: Optional[str] = Field(
        default=None,
        description="ISO8601 end time (UTC). e.g. '2024-01-31'",
    )
    updatedafter: Optional[str] = Field(
        default=None,
        description="Return only events updated after this ISO8601 timestamp (incremental sync).",
    )

    # ------------------------------------------------------------------
    # Geography — circle (Pattern 2, option A)
    # All three must be set together.
    # ------------------------------------------------------------------
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-360, le=360)
    maxradiuskm: Optional[float] = Field(default=None, gt=0, description="Radius in km. Mutually exclusive with maxradius.")

    # ------------------------------------------------------------------
    # Geography — bounding box (Pattern 2, option B)
    # All four must be set together.
    # ------------------------------------------------------------------
    minlatitude: Optional[float] = Field(default=None, ge=-90, le=90)
    maxlatitude: Optional[float] = Field(default=None, ge=-90, le=90)
    minlongitude: Optional[float] = Field(default=None, ge=-360, le=360)
    maxlongitude: Optional[float] = Field(default=None, ge=-360, le=360)

    # ------------------------------------------------------------------
    # Magnitude
    # ------------------------------------------------------------------
    minmagnitude: Optional[float] = Field(
        default=None,
        description="Required for Pattern 1. Recommended floor: 4.5 for global queries.",
    )
    maxmagnitude: Optional[float] = Field(default=None)

    # ------------------------------------------------------------------
    # Depth (km)
    # ------------------------------------------------------------------
    mindepth: Optional[float] = Field(default=None, ge=-100, le=1000)
    maxdepth: Optional[float] = Field(default=None, ge=-100, le=1000)

    # ------------------------------------------------------------------
    # Event classification
    # ------------------------------------------------------------------
    eventtype: Optional[str] = Field(
        default=None,
        description="e.g. 'earthquake'. Omit to include all seismic event types.",
    )
    reviewstatus: Optional[Literal["automatic", "reviewed"]] = Field(
        default=None,
        description="'reviewed' = human-checked, higher quality. 'automatic' = machine-detected, more recent. Omit to return all events.",
    )
    alertlevel: Optional[Literal["green", "yellow", "orange", "red"]] = Field(
        default=None,
        description="PAGER impact alert level. 'red' = highest impact events only.",
    )
    producttype: Optional[str] = Field(
        default=None,
        description="Filter to events with a specific USGS product. e.g. 'shakemap', 'moment-tensor', 'losspager'.",
    )

    # ------------------------------------------------------------------
    # Impact filters
    # ------------------------------------------------------------------
    minfelt: Optional[int] = Field(
        default=None, ge=0,
        description="Minimum number of DYFI 'felt' reports. e.g. 100 = widely felt events.",
    )
    minsig: Optional[int] = Field(
        default=None, ge=0,
        description="Minimum USGS significance score (0–2000+). 500+ = significant, 1000+ = major.",
    )

    # ------------------------------------------------------------------
    # Output control
    # ------------------------------------------------------------------
    orderby: Optional[Literal["time", "time-asc", "magnitude", "magnitude-asc"]] = Field(
        default=None,
        description="Sort order. Defaults to 'time' (newest first) when omitted.",
    )
    limit: int = Field(
        default=DEFAULT_LIMIT, ge=1, le=20000,
        description="Max results to return. See DEFAULT_LIMIT; API hard cap is 20,000.",
    )

    # ------------------------------------------------------------------
    # Geometry invariant
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def _resolve_geometry_conflict(self) -> "EarthquakeQueryModel":
        """
        Circle (lat/lon/radius) and bounding box are mutually exclusive.
        When the LLM sets both, keep whichever group is more complete:
          - full bbox beats circle (country/region queries)
          - circle beats a partial bbox (city queries with stray bbox fields)
        """
        has_circle   = self.latitude is not None or self.longitude is not None
        bbox         = (self.minlatitude, self.maxlatitude, self.minlongitude, self.maxlongitude)
        has_full_bbox = all(v is not None for v in bbox)
        has_any_bbox  = any(v is not None for v in bbox)

        if has_full_bbox and has_circle:
            self.latitude = self.longitude = self.maxradiuskm = None
        elif has_circle and has_any_bbox and not has_full_bbox:
            self.minlatitude = self.maxlatitude = self.minlongitude = self.maxlongitude = None

        return self

    # ------------------------------------------------------------------
    # API param export
    # ------------------------------------------------------------------

    def to_api_params(self) -> dict:
        """
        Convert to a flat dict of URL parameters ready for the USGS API.
        Strips None values and internal fields (query_type).
        Injects format=geojson.
        """
        params = {
            k: v
            for k, v in self.model_dump(exclude={"query_type"}).items()
            if v is not None
        }
        params["format"] = "geojson"
        return params


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    valid: bool
    provided: list[str] = field(default_factory=list)
    message: str = ""

    def __str__(self) -> str:
        return self.message


def validate_query(model: EarthquakeQueryModel) -> ValidationResult:
    """
    Validate the model for logical consistency.

    Checks:
      1. Time ordering       — starttime must be before endtime
      2. Magnitude ordering  — minmagnitude must be <= maxmagnitude
      3. Depth ordering      — mindepth must be <= maxdepth
      4. Circle completeness — if any circle field is set, all three are needed
      5. Bbox completeness   — if any bbox field is set, all four are needed
      6. Geometry exclusivity— circle and bbox must not both be fully set
    """
    provided = [
        k for k, v in model.model_dump(exclude={"query_type", "limit"}).items()
        if v is not None
    ]
    errors: list[str] = []

    if model.starttime and model.endtime and model.starttime > model.endtime:
        errors.append(
            f"starttime ({model.starttime}) must be before endtime ({model.endtime})."
        )

    if (
        model.minmagnitude is not None
        and model.maxmagnitude is not None
        and model.minmagnitude > model.maxmagnitude
    ):
        errors.append(
            f"minmagnitude ({model.minmagnitude}) must be <= maxmagnitude ({model.maxmagnitude})."
        )

    if (
        model.mindepth is not None
        and model.maxdepth is not None
        and model.mindepth > model.maxdepth
    ):
        errors.append(
            f"mindepth ({model.mindepth}) must be <= maxdepth ({model.maxdepth})."
        )

    circle_fields = {
        "latitude": model.latitude,
        "longitude": model.longitude,
        "maxradiuskm": model.maxradiuskm,
    }
    circle_set = {k for k, v in circle_fields.items() if v is not None}
    if circle_set and circle_set != set(circle_fields):
        missing_circle = set(circle_fields) - circle_set
        errors.append(
            f"Incomplete circle geometry. Have: {sorted(circle_set)}. "
            f"Also need: {sorted(missing_circle)}."
        )

    bbox_fields = {
        "minlatitude": model.minlatitude,
        "maxlatitude": model.maxlatitude,
        "minlongitude": model.minlongitude,
        "maxlongitude": model.maxlongitude,
    }
    bbox_set = {k for k, v in bbox_fields.items() if v is not None}
    if bbox_set and bbox_set != set(bbox_fields):
        missing_bbox = set(bbox_fields) - bbox_set
        errors.append(
            f"Incomplete bounding box. Have: {sorted(bbox_set)}. "
            f"Also need: {sorted(missing_bbox)}."
        )

    has_circle = circle_set == set(circle_fields)
    has_bbox   = bbox_set   == set(bbox_fields)
    if has_circle and has_bbox:
        errors.append(
            "Both circle geometry and bounding box are fully set. "
            "Use one or the other — the API returns their intersection, which is likely empty."
        )

    if errors:
        message = "Invalid query:\n" + "\n".join(f"  - {e}" for e in errors)
        message += f"\nFields currently set: {provided}"
        return ValidationResult(valid=False, provided=provided, message=message)

    return ValidationResult(valid=True, provided=provided)


# ---------------------------------------------------------------------------
# Default model builders
# ---------------------------------------------------------------------------

def build_default_model() -> EarthquakeQueryModel:
    """
    Create an EarthquakeQueryModel pre-filled with all unconditional defaults.

    The caller then overwrites fields with values from the normaliser, then
    calls apply_radius_default() to handle the one conditional default.

    Defaults applied:
      - starttime / endtime : today minus DEFAULT_TIMESPAN_DAYS … today
      - eventtype           : DEFAULT_EVENT_TYPE  ("earthquake")
      - minmagnitude        : DEFAULT_MIN_MAGNITUDE  (4.5)
      - limit               : DEFAULT_LIMIT  (100)
    """
    now = datetime.now(timezone.utc)
    return EarthquakeQueryModel(
        starttime=(now - timedelta(days=DEFAULT_TIMESPAN_DAYS)).strftime("%Y-%m-%d"),
        endtime=now.strftime("%Y-%m-%d"),
        eventtype=DEFAULT_EVENT_TYPE,
        minmagnitude=DEFAULT_MIN_MAGNITUDE,
        limit=DEFAULT_LIMIT,
    )


def apply_radius_default(model: EarthquakeQueryModel) -> tuple[EarthquakeQueryModel, str | None]:
    """
    Apply DEFAULT_RADIUS_KM when latitude + longitude are set but maxradiuskm
    is not. Called after the user's fields have been merged into the model.

    Returns the (possibly updated) model and an assumption string if the
    default was applied, or None if no change was needed.
    """
    if (
        model.latitude is not None
        and model.longitude is not None
        and model.maxradiuskm is None
    ):
        updated = model.model_copy(update={"maxradiuskm": DEFAULT_RADIUS_KM})
        assumption = (
            f"No radius given for location (lat={model.latitude}, lon={model.longitude})"
            f" → applied default radius of {DEFAULT_RADIUS_KM} km"
        )
        return updated, assumption

    return model, None


def get_default_assumptions(user_fields: dict) -> list[str]:
    """
    Return an assumption string for every default that was silently applied
    because the user did not provide that field.

    Based on the USGS API minimum viable parameter guidance:
      - Without starttime/endtime   → last 30 days returned (often surprising)
      - Without minmagnitude        → ~500 events/day globally (result flood)
      - Without eventtype           → non-earthquake events included
      - Without limit               → capped at DEFAULT_LIMIT silently
    """
    now = datetime.now(timezone.utc)
    assumptions: list[str] = []

    has_starttime = "starttime" in user_fields
    has_endtime   = "endtime"   in user_fields

    if not has_starttime and not has_endtime:
        start = (now - timedelta(days=DEFAULT_TIMESPAN_DAYS)).strftime("%Y-%m-%d")
        end   = now.strftime("%Y-%m-%d")
        assumptions.append(
            f"No time window specified → defaulted to last {DEFAULT_TIMESPAN_DAYS} days "
            f"(starttime={start}, endtime={end})"
        )
    elif not has_starttime:
        start = (now - timedelta(days=DEFAULT_TIMESPAN_DAYS)).strftime("%Y-%m-%d")
        assumptions.append(
            f"No start date specified → defaulted starttime={start} "
            f"({DEFAULT_TIMESPAN_DAYS} days before today)"
        )
    elif not has_endtime:
        end = now.strftime("%Y-%m-%d")
        assumptions.append(f"No end date specified → defaulted endtime={end} (today)")

    if "minmagnitude" not in user_fields and "maxmagnitude" not in user_fields:
        assumptions.append(
            f"No magnitude filter specified → defaulted to minmagnitude={DEFAULT_MIN_MAGNITUDE} "
            f"(recommended floor; without it a global query returns ~500 events/day)"
        )

    if "eventtype" not in user_fields:
        assumptions.append(
            f"No event type specified → defaulted to eventtype={DEFAULT_EVENT_TYPE!r} "
            f"(excludes explosions, blasts, and other non-earthquake seismic events)"
        )

    if "limit" not in user_fields:
        assumptions.append(
            f"No result limit specified → defaulted to limit={DEFAULT_LIMIT}"
        )

    return assumptions


# ---------------------------------------------------------------------------
# API output models
# ---------------------------------------------------------------------------

class EarthquakeEvent(BaseModel):
    """
    A single earthquake event, normalised from a USGS GeoJSON Feature.

    Fields are selected for downstream agent utility (Summariser, Validator).
    Low-value seismological fields (nst, gap, dmin, rms, net, code, ids,
    sources, types, detail, updated) are intentionally excluded.
    """
    id: str
    magnitude: Optional[float]
    mag_type: Optional[str]
    place: Optional[str]
    time_ms: Optional[int]            # Unix timestamp in milliseconds
    latitude: Optional[float]
    longitude: Optional[float]
    depth_km: Optional[float]
    status: Optional[str]             # "reviewed" | "automatic"
    event_type: Optional[str]         # e.g. "earthquake"
    significance: Optional[int]       # USGS composite score (0–2000+)
    tsunami: Optional[bool]           # True if tsunami flag is set
    alert: Optional[str]              # PAGER level: "green" | "yellow" | "orange" | "red"
    felt: Optional[int]               # DYFI "felt" report count (significant events only)
    cdi: Optional[float]              # Max community decimal intensity
    mmi: Optional[float]              # Max ShakeMap intensity
    url: Optional[str]
    title: Optional[str]


class APIResult(BaseModel):
    """
    Normalised, purpose-built representation of a USGS API response.

    Resolves the structural difference between response types into a single
    consistent shape. Downstream agents (Summariser, Validator) should work
    from this model rather than the raw api_response dict.

    result_type values:
      "collection"   — /query returned one or more events
      "single_event" — /query?eventid=... returned one Feature (different shape)
      "count"        — /count returned an integer
      "empty"        — /query returned zero results (HTTP 200, count=0)
    """
    result_type: Literal["collection", "single_event", "count", "empty"]
    count: Optional[int] = None           # populated for result_type="count"
    total_available: Optional[int] = None # metadata.count from /query responses
    returned: Optional[int] = None        # len(features) actually in this response
    events: list[EarthquakeEvent] = Field(default_factory=list)
    query_url: Optional[str] = None       # URL from metadata, for provenance
    generated_ms: Optional[int] = None    # metadata.generated timestamp


# ---------------------------------------------------------------------------
# Summariser output models
# ---------------------------------------------------------------------------

class APICallLog(BaseModel):
    """Operational record for a single USGS API call."""

    url: str                              # full URL with query string as sent
    retrieved_at_utc: str                 # ISO8601 UTC timestamp of the call
    result_type: str                      # "collection" | "single_event" | "count" | "empty"
    total_available: Optional[int] = None # metadata.count from /query
    returned: Optional[int] = None        # number of events in this response
    count: Optional[int] = None           # value from /count endpoint


class AgentEnrichedResponse(BaseModel):
    """Canonical output envelope produced by the Summariser."""
    request_id: str                    # UUID for this request
    title: str                         # short, descriptive title (LLM-composed)
    parsed_intent: str                 # verbatim user_query
    assumptions: list[str]             # all assumptions and defaults applied
    api_calls: list[APICallLog]        # one entry per USGS call made
    answer_text: str                   # user-facing grounded markdown answer (LLM-composed)


# ---------------------------------------------------------------------------
# Evaluator output models
# ---------------------------------------------------------------------------

class RubricCheck(BaseModel):
    """Result of a single evaluator rubric check."""
    name: str
    passed: bool
    detail: str = ""


class EvaluationResult(BaseModel):
    """Quality gate output produced by the Evaluator."""
    confidence_score: int              # 0–100, derived from fraction of checks passed
    passed: bool                       # True when score >= 70 or max retries reached
    rubric_checks: list[RubricCheck]   # one entry per check performed
    retry_target: str                  # "" | "normaliser" | "summariser"
    retry_reason: str                  # human-readable explanation when retry is needed


# ---------------------------------------------------------------------------
# LangGraph state schema
# ---------------------------------------------------------------------------

class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    action: str                               # "normalise_query" | "answer_question" | "show_glossary"
    user_query: str                           # raw user query extracted by supervisor
    query_type: str                           # "/count" or "/query", set by normaliser
    normalised_query: dict                    # field -> value extracted from user query (pre-defaults)
    assumptions: list[str]                    # ambiguous mappings and defaults applied
    api_response: dict[str, Any]              # raw USGS API response (provenance)
    parsed_result: Optional[APIResult]        # structured output for Summariser and Evaluator
    retrieved_at_utc: str                     # ISO8601 UTC timestamp of the API call
    api_call_url: str                         # full URL as sent to USGS
    enriched_response: Optional[AgentEnrichedResponse]  # final output envelope
    evaluation_result: Optional[EvaluationResult]       # latest evaluator output
    eval_loop_count: int                      # incremented each evaluator pass; caps retries at 2
    eval_feedback: Optional[str]              # feedback injected into summariser on retry
