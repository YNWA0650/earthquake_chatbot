import asyncio
import os
import uuid
import warnings
from datetime import datetime, timezone
from typing import Literal, Optional
from urllib.parse import urlencode

# LangGraph checkpoints state by serialising LangChain messages via Pydantic.
# In LangChain 1.x + LangGraph 1.x the tool-call messages contain a `parsed`
# field (set to the structured-output Pydantic model) that Pydantic's serialiser
# doesn't expect to be non-None. This is a known upstream compatibility quirk —
# the warning is harmless and the serialised value is correct.
warnings.filterwarnings(
    "ignore",
    message=".*PydanticSerializationUnexpectedValue.*",
    category=UserWarning,
)

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END
from pydantic import BaseModel, Field

from earthquake_agent.utils.state import (
    AgentEnrichedResponse,
    APICallLog,
    EarthquakeQueryModel,
    State,
    apply_radius_default,
    build_default_model,
    get_default_assumptions,
)
from earthquake_agent.utils.tools import (
    USGS_BASE_URL,
    QueryExecutionError,
    execute_query,
    format_glossary_for_llm,
    format_glossary_for_user,
    format_result_for_summariser,
    parse_api_response,
)

load_dotenv()

llm = ChatOpenAI(
    api_key=os.getenv("OPENAI_KEY"),
    model="gpt-4o-mini",
)


# ---------------------------------------------------------------------------
# Supervisor
# ---------------------------------------------------------------------------

SUPERVISOR_PROMPT = """You are a helpful earthquake information assistant.

Analyse the user's message and classify it into one of three actions:

  "normalise_query"
      The user wants to search for earthquake data — a list, count, ranked results,
      or details about a specific event.
      Examples: "earthquakes near Tokyo last year", "how many M5+ events in 2024?",
                "show me the biggest earthquakes this month", "details for event us6000m0xl"

  "show_glossary"
      The user explicitly asks to see the full parameter list or glossary.
      Only use this for direct requests to see the reference — NOT for general capability questions.
      Examples: "show me all parameters", "list all filters", "show the glossary",
                "what are all the search options?"

  "answer_question"
      Everything else, including:
        - Capability questions ("what can you search?", "can I filter by location?", "what do you support?")
        - Query-building help ("how do I search near Tokyo?", "what magnitude should I use for big earthquakes?")
        - General earthquake knowledge or follow-up questions on previous results
        - Off-topic requests

Respond with:
  - action: one of the three values above
  - user_query: the user's data request verbatim (only when action is "normalise_query", else "")
  - response: your reply to show the user
      • "normalise_query" → brief acknowledgement, e.g. "Searching for earthquakes…"
      • "show_glossary"   → "Here is the full list of search parameters:" (the glossary will be appended automatically)
      • "answer_question" → answer directly using the guidance below

GUIDANCE FOR "answer_question" responses:

When the user asks what you can do or how to build a query:
  - Give a helpful, conversational answer. Do NOT reproduce the raw parameter list.
  - Cover the most useful search dimensions with concrete examples:
      • Location — by city ("near Tokyo"), country/region ("earthquakes in Japan"), or radius ("within 200 km of Los Angeles")
      • Time — relative ("last week", "in 2024") or absolute date ranges
      • Magnitude — floor ("M5 or greater"), range ("between M4 and M6"), or vague terms ("major", "significant")
      • Count — "how many M6+ earthquakes hit Turkey this year?"
      • Specific event — "tell me about earthquake us6000m0xl"
      • Impact filters — felt reports, PAGER alert level, depth, review status
  - Suggest 2–3 example queries they could try right now.
  - End with: "Say 'show me all parameters' if you'd like the full filter reference."

When answering general earthquake questions or follow-ups:
  - Answer directly using your knowledge and any context already in the conversation.
  - For off-topic requests, politely explain you specialise in earthquake information.
"""


class SupervisorDecision(BaseModel):
    action: Literal["normalise_query", "show_glossary", "answer_question"] = Field(
        description="Intent classification"
    )
    user_query: str = Field(
        description="The user's data request verbatim if action is normalise_query, else empty string"
    )
    response: str = Field(description="The reply to show the user")


supervisor_llm = llm.with_structured_output(SupervisorDecision)


def supervisor_node(state: State):
    """Classifies intent. Appends glossary content when action is show_glossary."""
    decision = supervisor_llm.invoke(
        [SystemMessage(content=SUPERVISOR_PROMPT)] + state["messages"]
    )

    response_text = decision.response
    if decision.action == "show_glossary":
        response_text = decision.response + "\n\n" + format_glossary_for_user()

    return {
        "action": decision.action,
        "user_query": decision.user_query,
        "messages": [AIMessage(content=response_text)],
    }


# ---------------------------------------------------------------------------
# Normaliser
# ---------------------------------------------------------------------------

_TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

QUERY_NORMALISER_PROMPT = f"""You are a Query Normaliser for a USGS earthquake search agent.
Today's date is {_TODAY}.

Your job is to extract search parameters from the user's query and map them
directly to fields in the EarthquakeQueryModel. Only set fields the user
explicitly stated or that you can confidently infer. Leave everything else
as null — defaults will be applied afterwards.

{format_glossary_for_llm()}

---

MAPPING RULES

1. TIME
   - Compute actual ISO8601 dates from relative phrases using today = {_TODAY}.
   - "last week" → starttime = 7 days ago, endtime = today
   - "yesterday" → starttime = yesterday, endtime = yesterday
   - "in January 2024" → starttime = 2024-01-01, endtime = 2024-01-31
   - "last 24 hours" → starttime = yesterday's datetime, endtime = now
   - If the user gives only a start ("since January") set starttime and leave endtime null.

2. GEOGRAPHY
   - Named cities → use well-known lat/lon coordinates (latitude + longitude).
     If the user does not give a radius, leave maxradiuskm null — the default will be applied.
   - Named countries or regions → use a bounding box (minlatitude/maxlatitude/minlongitude/maxlongitude).
   - Never set both circle and bbox fields.

3. MAGNITUDE
   - Vague phrases require an assumption — record it in the assumptions list:
     "big"         → assume minmagnitude=6   (record assumption)
     "major"       → assume minmagnitude=7   (record assumption)
     "significant" → assume minmagnitude=5   (record assumption)
     "strong"      → assume minmagnitude=6   (record assumption)

4. QUERY TYPE
   - "how many", "count", "number of"  →  query_type="/count"
   - All other data requests            →  query_type="/query"

5. LIMIT / ORDERING
   - "top N" or "N biggest" → limit=N, orderby="magnitude"
   - "most recent N"        → limit=N, orderby="time"
   - "N earthquakes"        → limit=N

6. ASSUMPTIONS
   - Record every inference you had to make that was not stated explicitly.
   - Format: "<original phrase> → <field>=<value>"
   - Examples:
     "User said 'big earthquakes' → assumed minmagnitude=6.0"
     "User said 'near Tokyo' → mapped to latitude=35.68, longitude=139.69"
     "User said 'Japan' → mapped to bounding box lat 30–46, lon 130–146"
"""


class NormalisedQuery(EarthquakeQueryModel):
    """
    Fields extracted directly from the user's query.
    Extends EarthquakeQueryModel so field definitions stay in one place.

    Only two parent fields have non-None defaults and are overridden here:
      - query_type : parent defaults to "/query"
      - limit      : parent defaults to DEFAULT_LIMIT (100)
    All other fields are already Optional = None on the parent.
    Defaults are applied afterwards via build_default_model() + model_copy().
    """

    query_type: Literal["/query", "/count"] = None   # type: ignore[assignment]
    limit: Optional[int] = Field(default=None, ge=1, le=20000)

    assumptions: list[str] = Field(
        default_factory=list,
        description="Record every inference that was not explicitly stated by the user.",
    )

normaliser_llm = llm.with_structured_output(NormalisedQuery)


def normaliser_node(state: State):
    """
    Maps the raw user query to EarthquakeQueryModel fields.

    1. LLM extracts what the user said into NormalisedQuery.
    2. Named location without radius → apply DEFAULT_RADIUS_KM.
    3. Merge user fields over build_default_model() to produce the final model.
    4. Store user-specified fields and assumptions separately in state.
    """
    response: NormalisedQuery = normaliser_llm.invoke(
        [SystemMessage(content=QUERY_NORMALISER_PROMPT),
         HumanMessage(content=state["user_query"])]
    )

    # Collect what the user actually specified (non-null, excluding assumptions)
    user_fields = {
        k: v
        for k, v in response.model_dump(exclude={"assumptions"}).items()
        if v is not None
    }

    # Build final model: defaults first, user values overwrite, then radius default.
    # The final model itself is not stored — executor rebuilds from user_fields independently.
    _, radius_assumption = apply_radius_default(
        build_default_model().model_copy(update=user_fields)
    )

    # LLM-recorded assumptions (ambiguous phrases, inferred locations, etc.)
    assumptions = list(response.assumptions)
    # Defaults silently applied because the user didn't specify those fields
    assumptions.extend(get_default_assumptions(user_fields))
    if radius_assumption:
        assumptions.append(radius_assumption)

    summary_parts = [f"type={response.query_type}"]
    if user_fields:
        summary_parts.append(f"fields={list(user_fields.keys())}")
    if assumptions:
        summary_parts.append(f"assumptions={assumptions}")

    return {
        "query_type": response.query_type,
        "normalised_query": user_fields,
        "action": "build_execute_query",
        "assumptions": assumptions,
        "messages": [AIMessage(content="Normalised: " + " | ".join(summary_parts))],
    }


# ---------------------------------------------------------------------------
# Executor node
# ---------------------------------------------------------------------------

def executor_node(state: State):
    """
    Rebuilds the final EarthquakeQueryModel from state, executes the API
    call, captures retrieval timestamp and full URL, then parses the response.
    No LLM involved.
    """
    user_fields = state.get("normalised_query", {})
    query_type  = state.get("query_type") or "/query"

    model = build_default_model().model_copy(
        update={**user_fields, "query_type": query_type}
    )

    # Apply conditional radius default — must mirror normaliser_node so validation passes.
    # normalised_query stores only the user-specified fields (no radius), so we re-derive
    # it here to ensure the model is always fully valid before execution.
    model, _ = apply_radius_default(model)

    # Reconstruct the full URL as it will be sent, for provenance logging.
    params = model.to_api_params()
    api_call_url = f"{USGS_BASE_URL}{query_type}?{urlencode(params)}"

    retrieved_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        raw = asyncio.run(execute_query(model))
    except ValueError as e:
        return {"messages": [AIMessage(content=f"Could not build query: {e}")]}
    except QueryExecutionError as e:
        return {"messages": [AIMessage(content=f"API error ({e.status_code}): {e}")]}
    except Exception as e:
        return {"messages": [AIMessage(content=f"Unexpected error: {e}")]}

    parsed = parse_api_response(raw, query_type=query_type)

    return {
        "api_response": raw,
        "parsed_result": parsed,
        "retrieved_at_utc": retrieved_at_utc,
        "api_call_url": api_call_url,
        "messages": [AIMessage(content=f"Executed: {api_call_url}")],
    }


# ---------------------------------------------------------------------------
# Summariser
# ---------------------------------------------------------------------------

SUMMARISER_PROMPT = """You are a Summariser for a grounded earthquake information system.

You will produce two fields — nothing else.

---

FIELD 1: title
A short, interesting, specific title for this result. Base it on the user query and what the
evidence actually shows. Examples:
  "5 Major Earthquakes Near Tokyo in 2024"
  "No M4.5+ Events Detected Near London (2016–2026)"
  "M7.5 Noto Peninsula Earthquake — January 2024"

---

FIELD 2: answer_summary
Write in markdown. Directly answer the user's question, then enrich the answer with key facts
drawn exclusively from the evidence block. Rules:

- Use only numbers, magnitudes, places, and counts that appear in the evidence block.
  Do not invent or estimate anything.
- Where relevant, reference individual events using their event ID (e.g. `us6000m0yg`).
- If the evidence shows failure (empty result, count = 0, error), say so explicitly and explain
  the filters that were applied so the user understands why — then suggest what they could change.
- Keep prose flowing and readable — do not impose a rigid section structure.
- Use bullet points or bold text where it genuinely helps clarity.
- Search the assumptions. Mention any assumptions that could have impacted the answer. Suggest how the query could be changed to get a different answer reference their query {user_query} directly when doing this.

---

ASSUMPTIONS applied during query normalisation (for your context only — do not list them):
{assumptions}

USER QUERY:
{user_query}

{evidence_block}
"""


class SummariserOutput(BaseModel):
    """The two fields the LLM generates. Everything else in the envelope is set deterministically."""
    title: str = Field(description="Short, specific, interesting title based on the query and evidence")
    answer_summary: str = Field(description="Markdown answer directly addressing the user query, enriched with key facts from the evidence block")


summariser_llm = llm.with_structured_output(SummariserOutput)


def summariser_node(state: State):
    """
    Composes the final grounded answer from the parsed API result.

    The LLM produces only title and answer_summary.
    All other AgentEnrichedResponse fields are set deterministically from state.
    """
    parsed           = state.get("parsed_result")
    retrieved_at_utc = state.get("retrieved_at_utc", "unknown")
    api_call_url     = state.get("api_call_url", "unknown")
    assumptions      = state.get("assumptions", [])
    user_query       = state.get("user_query", "")

    if parsed is None:
        return {}

    evidence_block   = format_result_for_summariser(parsed, retrieved_at_utc, api_call_url)
    assumptions_text = "\n".join(f"  • {a}" for a in assumptions) if assumptions else "  (none)"

    prompt = SUMMARISER_PROMPT.format(
        assumptions=assumptions_text,
        user_query=user_query,
        evidence_block=evidence_block,
    )

    llm_output: SummariserOutput = summariser_llm.invoke(
        [SystemMessage(content=prompt)]
    )

    api_call_log = APICallLog(
        url=api_call_url,
        retrieved_at_utc=retrieved_at_utc,
        result_type=parsed.result_type,
        total_available=parsed.total_available,
        returned=parsed.returned,
        count=parsed.count,
    )

    enriched = AgentEnrichedResponse(
        request_id=str(uuid.uuid4()),
        title=llm_output.title,
        parsed_intent=user_query,
        assumptions=assumptions,
        api_calls=[api_call_log],
        answer_text=llm_output.answer_summary,
    )

    return {
        "enriched_response": enriched,
        "messages": [AIMessage(content=f"## {enriched.title}\n\n{enriched.answer_text}")],
    }


# ---------------------------------------------------------------------------
# Conditional edge
# ---------------------------------------------------------------------------

def route_from_supervisor(state: State):
    action = state.get("action")
    if action == "normalise_query":
        return "normaliser"
    return END
