"""
Tools — Glossary and API Executor

External interactions available to the agent:
  1. GLOSSARY + formatters  — field reference for users and LLM prompts
  2. execute_query          — fires HTTP requests against the USGS Earthquake API
"""

from datetime import datetime, timezone

import httpx
from earthquake_agent.utils.state import (
    DEFAULT_EVENT_TYPE,
    DEFAULT_LIMIT,
    DEFAULT_MIN_MAGNITUDE,
    DEFAULT_RADIUS_KM,
    DEFAULT_TIMESPAN_DAYS,
    APIResult,
    EarthquakeEvent,
    EarthquakeQueryModel,
    validate_query,
)


# ---------------------------------------------------------------------------
# Glossary
# ---------------------------------------------------------------------------

GLOSSARY: list[dict] = [
    # ------------------------------------------------------------------ Query type
    {
        "field": "query_type",
        "category": "Query type",
        "type": '"/query" or "/count"',
        "description": "Whether to fetch event records or just count them.",
        "default": "/query",
        "format": '"/query" or "/count"',
        "example_phrases": [
            "how many earthquakes  →  /count",
            "show me / list / find earthquakes  →  /query",
        ],
    },
    # ------------------------------------------------------------------ Identity
    {
        "field": "eventid",
        "category": "Identity",
        "type": "string",
        "description": "Look up one specific event by its USGS ID. No other filters needed.",
        "default": None,
        "format": "e.g. us6000m0xl",
        "example_phrases": [
            "tell me about earthquake us6000m0xl",
            "details for event id us6000m0xl",
        ],
    },
    # ------------------------------------------------------------------ Time
    {
        "field": "starttime",
        "category": "Time",
        "type": "ISO8601 date string",
        "description": "Start of the time window to search.",
        "default": f"today minus {DEFAULT_TIMESPAN_DAYS} days",
        "format": "YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS",
        "example_phrases": [
            "since January 2024",
            "from 2024-01-01",
            "in the last week  →  compute starttime = today - 7 days",
            "yesterday  →  compute starttime = yesterday's date",
        ],
    },
    {
        "field": "endtime",
        "category": "Time",
        "type": "ISO8601 date string",
        "description": "End of the time window to search.",
        "default": "today",
        "format": "YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS",
        "example_phrases": [
            "up to March 2024",
            "before 2024-03-01",
            "last week  →  compute endtime = today",
        ],
    },
    {
        "field": "updatedafter",
        "category": "Time",
        "type": "ISO8601 datetime string",
        "description": "Return only events that were updated after this timestamp. "
                       "Use for incremental sync jobs, not typical user queries.",
        "default": None,
        "format": "YYYY-MM-DDTHH:MM:SS",
        "example_phrases": [
            "events revised since 2025-01-01",
        ],
    },
    # ------------------------------------------------------------------ Geography (circle)
    {
        "field": "latitude",
        "category": "Geography — circle",
        "type": "float  (-90 to 90)",
        "description": "Centre latitude for a circular area search. "
                       "Must be combined with longitude and maxradiuskm.",
        "default": None,
        "format": "decimal degrees, e.g. 35.68",
        "example_phrases": [
            "near Tokyo  →  latitude=35.68, longitude=139.69",
            "near Los Angeles  →  latitude=34.05, longitude=-118.24",
        ],
    },
    {
        "field": "longitude",
        "category": "Geography — circle",
        "type": "float  (-360 to 360)",
        "description": "Centre longitude for a circular area search.",
        "default": None,
        "format": "decimal degrees, e.g. 139.69 or -118.24",
        "example_phrases": ["see latitude examples"],
    },
    {
        "field": "maxradiuskm",
        "category": "Geography — circle",
        "type": "float  (> 0)",
        "description": "Radius of the circle in kilometres.",
        "default": f"{DEFAULT_RADIUS_KM} km (~{int(DEFAULT_RADIUS_KM * 0.621)} miles) "
                   "— applied automatically when lat/lon are set without a radius",
        "format": "kilometres, e.g. 100",
        "example_phrases": [
            "within 200 km of Tokyo",
            "within 50 miles of Los Angeles  →  convert to km (× 1.609)",
        ],
    },
    # ------------------------------------------------------------------ Geography (bbox)
    {
        "field": "minlatitude / maxlatitude / minlongitude / maxlongitude",
        "category": "Geography — bounding box",
        "type": "float",
        "description": "Rectangular bounding box. All four must be set together.",
        "default": None,
        "format": "decimal degrees",
        "example_phrases": [
            "earthquakes in Japan  →  minlat=30, maxlat=46, minlon=130, maxlon=146",
            "earthquakes in California  →  minlat=32, maxlat=42, minlon=-124, maxlon=-114",
            "earthquakes in Turkey  →  minlat=36, maxlat=42, minlon=26, maxlon=45",
        ],
    },
    # ------------------------------------------------------------------ Magnitude
    {
        "field": "minmagnitude",
        "category": "Magnitude",
        "type": "float",
        "description": "Minimum magnitude. The recommended global floor is 4.5.",
        "default": str(DEFAULT_MIN_MAGNITUDE),
        "format": "e.g. 4.5",
        "example_phrases": [
            "magnitude 5 or greater  →  minmagnitude=5",
            "M6+  →  minmagnitude=6",
            "big earthquakes  →  assume minmagnitude=6",
            "major earthquakes  →  assume minmagnitude=7",
            "significant earthquakes  →  assume minmagnitude=5",
        ],
    },
    {
        "field": "maxmagnitude",
        "category": "Magnitude",
        "type": "float",
        "description": "Maximum magnitude cap.",
        "default": None,
        "format": "e.g. 6.0",
        "example_phrases": [
            "smaller than M5  →  maxmagnitude=5",
            "between M4 and M6  →  minmagnitude=4, maxmagnitude=6",
        ],
    },
    # ------------------------------------------------------------------ Depth
    {
        "field": "mindepth",
        "category": "Depth",
        "type": "float  (-100 to 1000 km)",
        "description": "Minimum depth in kilometres below the surface.",
        "default": None,
        "format": "kilometres",
        "example_phrases": [
            "deep earthquakes  →  mindepth=300",
            "deeper than 100 km  →  mindepth=100",
        ],
    },
    {
        "field": "maxdepth",
        "category": "Depth",
        "type": "float  (-100 to 1000 km)",
        "description": "Maximum depth in kilometres.",
        "default": None,
        "format": "kilometres",
        "example_phrases": [
            "shallow earthquakes  →  maxdepth=30",
            "near-surface earthquakes  →  maxdepth=10",
        ],
    },
    # ------------------------------------------------------------------ Classification
    {
        "field": "eventtype",
        "category": "Event classification",
        "type": "string",
        "description": "Filter by event type. Omit to include everything; "
                       "use 'earthquake' to exclude blasts, collapses, etc.",
        "default": DEFAULT_EVENT_TYPE,
        "format": "e.g. earthquake, explosion, quarry blast",
        "example_phrases": [
            "explosions  →  eventtype=explosion",
            "only earthquakes  →  eventtype=earthquake (default)",
        ],
    },
    {
        "field": "reviewstatus",
        "category": "Event classification",
        "type": '"reviewed" | "automatic"',
        "description": "'reviewed' = human-checked, higher quality. "
                       "'automatic' = machine-detected, more recent but less accurate. "
                       "Omit entirely to return all events.",
        "default": None,
        "format": "reviewed / automatic  (omit for all)",
        "example_phrases": [
            "confirmed earthquakes  →  reviewstatus=reviewed",
            "latest detections  →  reviewstatus=automatic",
        ],
    },
    {
        "field": "alertlevel",
        "category": "Event classification",
        "type": '"green" | "yellow" | "orange" | "red"',
        "description": "PAGER impact alert level. Red = highest casualty/damage risk.",
        "default": None,
        "format": "green / yellow / orange / red",
        "example_phrases": [
            "deadly earthquakes  →  alertlevel=red",
            "high impact earthquakes  →  alertlevel=orange or red",
        ],
    },
    {
        "field": "producttype",
        "category": "Event classification",
        "type": "string",
        "description": "Filter to events where USGS has produced a specific analysis product.",
        "default": None,
        "format": "e.g. shakemap, moment-tensor, losspager, dyfi, finite-fault",
        "example_phrases": [
            "earthquakes with ShakeMaps  →  producttype=shakemap",
            "earthquakes with loss estimates  →  producttype=losspager",
        ],
    },
    # ------------------------------------------------------------------ Impact
    {
        "field": "minfelt",
        "category": "Impact",
        "type": "int (>= 0)",
        "description": "Minimum number of public 'I felt it' reports (DYFI). "
                       "Good proxy for widely felt events.",
        "default": None,
        "format": "integer, e.g. 100",
        "example_phrases": [
            "widely felt earthquakes  →  minfelt=100",
            "earthquakes felt by many people  →  minfelt=100",
        ],
    },
    {
        "field": "minsig",
        "category": "Impact",
        "type": "int (>= 0)",
        "description": "Minimum USGS significance score (0–2000+). "
                       "Composite of magnitude, felt reports, and impact. "
                       "500+ = significant event, 1000+ = major.",
        "default": None,
        "format": "integer, e.g. 500",
        "example_phrases": [
            "most significant earthquakes  →  minsig=1000",
            "notable earthquakes  →  minsig=500",
        ],
    },
    # ------------------------------------------------------------------ Output control
    {
        "field": "orderby",
        "category": "Output",
        "type": '"time" | "time-asc" | "magnitude" | "magnitude-asc"',
        "description": "Sort order of results.",
        "default": "time (newest first)",
        "format": "time / time-asc / magnitude / magnitude-asc",
        "example_phrases": [
            "biggest earthquakes first  →  orderby=magnitude",
            "oldest first  →  orderby=time-asc",
            "most recent first  →  orderby=time (default)",
        ],
    },
    {
        "field": "limit",
        "category": "Output",
        "type": "int (1–20000)",
        "description": "Maximum number of results to return.",
        "default": str(DEFAULT_LIMIT),
        "format": "integer",
        "example_phrases": [
            "top 10  →  limit=10, orderby=magnitude",
            "show me 50  →  limit=50",
        ],
    },
]


def format_glossary_for_user() -> str:
    """Returns a human-readable, grouped glossary for display to the user."""
    lines = ["**Earthquake Query Glossary**", ""]
    current_category = None

    for entry in GLOSSARY:
        cat = entry["category"]
        if cat != current_category:
            lines.append(f"**{cat}**")
            current_category = cat

        lines.append(f"  `{entry['field']}`  ({entry['type']})")
        lines.append(f"    {entry['description']}")
        if entry["default"]:
            lines.append(f"    Default: {entry['default']}")
        lines.append(f"    Format: {entry['format']}")
        if entry["example_phrases"]:
            lines.append("    Examples:")
            for phrase in entry["example_phrases"]:
                lines.append(f"      • {phrase}")
        lines.append("")

    return "\n".join(lines)


def format_glossary_for_llm() -> str:
    """
    Returns a compact reference string for inclusion in LLM prompts.
    Optimised for token efficiency while keeping enough detail for accurate mapping.
    """
    lines = ["QUERY FIELD REFERENCE (EarthquakeQueryModel):"]
    current_category = None

    for entry in GLOSSARY:
        cat = entry["category"]
        if cat != current_category:
            lines.append(f"\n[{cat}]")
            current_category = cat

        default_str = f"  default={entry['default']}" if entry["default"] else ""
        lines.append(f"  {entry['field']} ({entry['type']}){default_str}")
        lines.append(f"    → {entry['description']}")
        lines.append(f"    format: {entry['format']}")
        for phrase in entry["example_phrases"]:
            lines.append(f"    e.g. \"{phrase}\"")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# API executor
# ---------------------------------------------------------------------------

USGS_BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1"


class QueryExecutionError(Exception):
    """Raised when the USGS API returns a non-200 status code."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"API returned {status_code}: {message}")


async def execute_query(model: EarthquakeQueryModel) -> dict:
    """
    Validate and execute a query against the USGS Earthquake API.

    Returns the parsed JSON response dict, or {} on HTTP 204 (no results).
    Raises:
      - ValueError         if validate_query() fails
      - QueryExecutionError if the API returns a non-200 status
    """
    result = validate_query(model)
    if not result.valid:
        raise ValueError(str(result))

    url = f"{USGS_BASE_URL}{model.query_type}"
    params = model.to_api_params()

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, params=params)

    if response.status_code == 204:
        return {}
    if response.status_code != 200:
        raise QueryExecutionError(response.status_code, response.text)

    return response.json()


# ---------------------------------------------------------------------------
# API response parser
# ---------------------------------------------------------------------------

def _parse_feature(feature: dict) -> EarthquakeEvent:
    """Parse a single GeoJSON Feature dict into an EarthquakeEvent."""
    props = feature.get("properties") or {}
    coords = (feature.get("geometry") or {}).get("coordinates") or []

    # GeoJSON coordinates are [longitude, latitude, depth_km]
    longitude = coords[0] if len(coords) > 0 else None
    latitude  = coords[1] if len(coords) > 1 else None
    depth_km  = coords[2] if len(coords) > 2 else None

    tsunami_raw = props.get("tsunami")
    tsunami = bool(tsunami_raw) if tsunami_raw is not None else None

    return EarthquakeEvent(
        id=feature.get("id") or "",
        magnitude=props.get("mag"),
        mag_type=props.get("magType"),
        place=props.get("place"),
        time_ms=props.get("time"),
        latitude=latitude,
        longitude=longitude,
        depth_km=depth_km,
        status=props.get("status"),
        event_type=props.get("type"),
        significance=props.get("sig"),
        tsunami=tsunami,
        alert=props.get("alert"),
        felt=props.get("felt"),
        cdi=props.get("cdi"),
        mmi=props.get("mmi"),
        url=props.get("url"),
        title=props.get("title"),
    )


def parse_api_response(raw: dict, query_type: str = "/query") -> APIResult:
    """
    Convert a raw USGS API response dict into a structured APIResult.

    Handles all four response shapes:
      - FeatureCollection  (/query returning multiple events)
      - Single Feature     (/query?eventid=... — structurally different)
      - Count              (/count — plain int wrapped as {"count": N})
      - Empty              (/query returning zero results)
      - No-data            (HTTP 204 returned as {})

    Args:
        raw:        The dict returned by execute_query().
        query_type: The query endpoint used ("/query" or "/count").
    """
    # No data at all (HTTP 204 or unexpected empty)
    if not raw:
        return APIResult(result_type="empty", total_available=0, returned=0)

    # /count response
    if query_type == "/count":
        return APIResult(
            result_type="count",
            count=raw.get("count"),
        )

    response_type = raw.get("type")

    # Single Feature (/query?eventid=...)
    if response_type == "Feature":
        event = _parse_feature(raw)
        return APIResult(
            result_type="single_event",
            total_available=1,
            returned=1,
            events=[event],
        )

    # FeatureCollection
    if response_type == "FeatureCollection":
        metadata  = raw.get("metadata") or {}
        features  = raw.get("features") or []
        total     = metadata.get("count", 0)

        if total == 0 or not features:
            return APIResult(
                result_type="empty",
                total_available=total,
                returned=0,
                query_url=metadata.get("url"),
                generated_ms=metadata.get("generated"),
            )

        events = [_parse_feature(f) for f in features]
        return APIResult(
            result_type="collection",
            total_available=total,
            returned=len(events),
            events=events,
            query_url=metadata.get("url"),
            generated_ms=metadata.get("generated"),
        )

    # Unrecognised shape — return empty rather than crash
    return APIResult(result_type="empty", total_available=0, returned=0)


# ---------------------------------------------------------------------------
# Summariser evidence formatter
# ---------------------------------------------------------------------------

def _ms_to_iso(ms: int | None) -> str:
    """Convert a Unix millisecond timestamp to an ISO8601 UTC string."""
    if ms is None:
        return "unknown"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_result_for_summariser(result: APIResult, retrieved_at_utc: str, api_call_url: str) -> str:
    """
    Render the parsed API result as a structured evidence block for the
    summariser LLM prompt. The LLM must use only the facts in this block
    — no hallucination outside it is permitted.

    Includes event IDs, URLs, timestamps, and key fields for each event
    so the LLM can reference them directly in the answer.
    """
    lines = [
        "=== API EVIDENCE BLOCK ===",
        f"Retrieved at: {retrieved_at_utc} (UTC)",
        f"API URL: {api_call_url}",
        "Source: USGS preferred event data",
        f"Result type: {result.result_type}",
    ]

    if result.result_type == "count":
        lines.append(f"Count: {result.count}")

    elif result.result_type == "empty":
        lines.append("No events matched the query.")
        lines.append(f"Total available: {result.total_available or 0}")

    elif result.result_type in ("collection", "single_event"):
        lines.append(f"Total matching in catalogue: {result.total_available}")
        lines.append(f"Events returned in this response: {result.returned}")
        lines.append("")

        for i, ev in enumerate(result.events, start=1):
            lines.append(f"--- Event {i} ---")
            lines.append(f"  ID:         {ev.id}")
            lines.append(f"  Magnitude:  {ev.magnitude} {ev.mag_type or ''}")
            lines.append(f"  Place:      {ev.place or 'unknown'}")
            lines.append(f"  Time (UTC): {_ms_to_iso(ev.time_ms)}")
            lines.append(f"  Depth:      {ev.depth_km} km")
            lines.append(f"  Location:   lat={ev.latitude}, lon={ev.longitude}")
            lines.append(f"  Status:     {ev.status or 'unknown'}")
            if ev.alert:
                lines.append(f"  Alert:      {ev.alert} (PAGER)")
            if ev.tsunami:
                lines.append(f"  Tsunami:    YES")
            if ev.significance is not None:
                lines.append(f"  Significance: {ev.significance}")
            if ev.felt is not None:
                lines.append(f"  Felt reports: {ev.felt}")
            if ev.cdi is not None:
                lines.append(f"  Max CDI:    {ev.cdi}")
            if ev.mmi is not None:
                lines.append(f"  Max MMI:    {ev.mmi}")
            if ev.url:
                lines.append(f"  URL:        {ev.url}")
            lines.append("")

    lines.append("=== END EVIDENCE BLOCK ===")
    return "\n".join(lines)
