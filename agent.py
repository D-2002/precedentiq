import os
import uuid
from dotenv import load_dotenv
from typing import TypedDict, Annotated
import operator

from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from elastic_tools import (
    search_case_law,
    search_memory,
    get_case_stats,
    save_to_memory,
    store_document
)

load_dotenv()

# ── 1. Define tools Gemini can call ─────────────────────────────

@tool
def tool_search_case_law(query: str, jurisdiction: str = None) -> str:
    """Search indexed legal precedents by legal concepts or fact patterns.
    Use this to find relevant past cases for a legal matter."""
    results = search_case_law(query, jurisdiction, limit=8)
    if not results:
        return "No relevant cases found in the database."
    
    output = f"Found {len(results)} relevant cases:\n\n"
    for i, r in enumerate(results, 1):
        output += f"{i}. {r['title']} ({r['year']})\n"
        output += f"   Court: {r['court']}\n"
        output += f"   Jurisdiction: {r['jurisdiction']}\n"
        output += f"   Citation: {r['citation']}\n"
        output += f"   Summary: {r['summary'][:200]}\n"
        output += f"   URL: {r['source_url']}\n\n"
    return output

@tool
def tool_search_memory(query: str) -> str:
    """Search past strategy briefs the agent has previously generated.
    ALWAYS call this first before generating any new brief."""
    results = search_memory(query, limit=3)
    if not results:
        return "No similar cases found in agent memory. This appears to be a new case type."
    
    output = f"Found {len(results)} similar past analyses:\n\n"
    for r in results:
        output += f"Case: {r.get('case_title', 'Unknown')}\n"
        output += f"Jurisdiction: {r.get('jurisdiction', '')}\n"
        output += f"Charge types: {r.get('charge_types', '')}\n"
        output += f"Past weak arguments identified: {r.get('weak_arguments', '')[:300]}\n\n"
    return output

@tool
def tool_get_case_stats(jurisdiction: str = None) -> str:
    """Get statistics about how many cases exist in the database
    for a given jurisdiction."""
    stats = get_case_stats(jurisdiction)
    output = f"Database contains {stats['total_cases']} total cases.\n"
    for j in stats.get("by_jurisdiction", []):
        output += f"  {j['jurisdiction']}: {j['count']} cases\n"
    return output

@tool
def tool_save_to_memory(
    case_title: str,
    jurisdiction: str,
    charge_types: str,
    top_precedents: str,
    weak_arguments: str,
    missing_evidence: str,
    full_brief: str,
    doc_id: str = ""
) -> str:
    """Save a completed strategy brief to agent memory so future
    similar cases can learn from this analysis."""
    result = save_to_memory(
        doc_id=doc_id or str(uuid.uuid4()),
        case_title=case_title,
        jurisdiction=jurisdiction,
        charge_types=charge_types.split(",") if isinstance(charge_types, str) else charge_types,
        top_precedents=top_precedents,
        weak_arguments=weak_arguments,
        missing_evidence=missing_evidence,
        full_brief=full_brief
    )
    return f"Strategy brief saved to memory. Memory ID: {result['memory_id']}"

# ── 2. Define agent state ────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    doc_id: str
    case_text: str
    jurisdiction: str
    brief: str

# ── 3. Build the graph ───────────────────────────────────────────

tools = [
    tool_search_memory,
    tool_get_case_stats,
    tool_search_case_law,
    tool_save_to_memory
]

llm = ChatVertexAI(
    model="gemini-2.0-flash-001",
    project=os.environ["GOOGLE_CLOUD_PROJECT"],
    location="us-central1",
    temperature=0.2
)

llm_with_tools = llm.bind_tools(tools)

SYSTEM_PROMPT = """You are PrecedentIQ, an expert legal strategy agent.

When given a legal case document, you MUST follow these steps in order:

STEP 1 - call tool_search_memory to check for similar past analyses
STEP 2 - call tool_get_case_stats to understand the database scope  
STEP 3 - call tool_search_case_law with the main legal issue and charge types
STEP 4 - call tool_search_case_law again with a more specific query if needed
STEP 5 - call tool_save_to_memory with your complete analysis
STEP 6 - return the final strategy brief

Your final strategy brief MUST follow this exact structure:

## Case Overview
[1-2 sentence summary of the case]

## Relevant Precedents Found
[List each case with name, year, court, and why it is relevant]

## Three Weakest Arguments
[Based on how similar cases were decided, identify the 3 weakest points]

## Missing Evidence
[What evidence was present in winning similar cases but is absent here]

## Recommended Strategy
[Concrete actionable recommendations based on the precedents]

## Memory Note
[Confirm the brief has been saved to agent memory]

Rules:
- Never invent case citations
- Always cite real cases returned by the search tools
- Be specific about which jurisdiction each precedent comes from
- If memory has similar past cases, reference them explicitly
"""

def agent_node(state: AgentState):
    """Main agent reasoning node."""
    messages = state["messages"]
    
    # Add system prompt if first message
    if not any(isinstance(m, SystemMessage) for m in messages):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
    
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

def should_continue(state: AgentState):
    """Decide whether to call tools or end."""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END

tool_node = ToolNode(tools)

# Build graph
graph = StateGraph(AgentState)
graph.add_node("agent", agent_node)
graph.add_node("tools", tool_node)

graph.set_entry_poi