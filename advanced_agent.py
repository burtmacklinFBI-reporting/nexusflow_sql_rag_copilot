import os
import re
import lancedb
import sqlparse
import psycopg2
import ast
import networkx as nx
import uuid
import json
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor
from typing import Annotated, List, Union, TypedDict, Literal, Optional
from pydantic import BaseModel, Field
from psycopg2 import OperationalError
import streamlit as st
from langchain_huggingface import HuggingFaceEndpointEmbeddings
import time
import requests
from cache_utils import cached_embed, cached_rerank
import cohere

# Load environment variables from .env file
load_dotenv()

# Now:
# @traceable ✅ works --> cause they detect Libraries like LangChain / LangSmith:
# Internally call os.environ
# They expect env variables to exist globally
# LangSmith tracking ✅ works
# LangChain auto-detects keys ✅




from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.documents import Document
from langchain_community.vectorstores import LanceDB
from langchain_huggingface import HuggingFaceEmbeddings
from langgraph.graph import StateGraph, END
from langsmith import traceable

from langchain_groq import ChatGroq
# from sentence_transformers import CrossEncoder

import numpy as np

# --- 1. Configuration & Global Objects ---

LANCEDB_DIR = "./lancedb_data"
HIERARCHICAL_TABLE_NAME = "nexusflow_hierarchical_kb"
GRAPH_FILE_PATH = "nexusflow_knowledge_graph.gml"
KNOWLEDGE_BASE_DIR = "knowledge_base"
PARENT_DOCS_FILE = os.path.join(KNOWLEDGE_BASE_DIR, "parent_docs.json")
LANCEDB_INDEX_DIR = "./graph_index_data"
GRAPH_INDEX_TABLE_NAME = "graph_node_index"

# useful for local
# The rate limits are like this - 
# RPM = Requests Per Minute - max 150
# Tokens Per minute - → sum of input + output tokens per minute - max 30k
# well under the free tier.
GROQ_ROUTER_MODEL = os.getenv("GROQ_ROUTER_MODEL", "llama-3.1-8b-instant")
GROQ_REASONER_MODEL = os.getenv("GROQ_REASONER_MODEL", "llama-3.3-70b-versatile")

llm_router = ChatGroq(model_name=GROQ_ROUTER_MODEL, temperature=0)
llm_reasoner = ChatGroq(model_name=GROQ_REASONER_MODEL, temperature=0)
# this is a local embedding model which has been downloaded, but on cloud storage it is difficult for you to deploy it so use api calls, when testing locally you can switch back to these ones.
# embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-base-en-v1.5")

embeddings = HuggingFaceEndpointEmbeddings(
    model="BAAI/bge-base-en-v1.5",
    huggingfacehub_api_token=os.getenv("HUGGINGFACE_API_KEY")
)



def safe_embed_query(text: str, retries=2):
    if not isinstance(text, str) or not text.strip():
        print("[WARN] Invalid embedding input")
        return None

    for attempt in range(retries):
        try:
            vec = embeddings.embed_query(text)

            # 🔒 TYPE CHECK
            if not isinstance(vec, list):
                raise ValueError("Embedding is not a list")

            # 🔒 LENGTH CHECK (BGE ~768 dims)
            if len(vec) < 100:
                raise ValueError("Embedding too small → likely broken")

            # 🔒 NUMERIC CHECK
            if not all(isinstance(x, (int, float)) for x in vec[:10]):
                raise ValueError("Embedding contains non-numeric values")

            return vec

        except Exception as e:
            print(f"[WARN] Embedding attempt {attempt+1} failed: {e}")

            # 🔁 Backoff (handles HF cold start)
            time.sleep(1.5 * (attempt + 1))

    # 🔥 FINAL FALLBACK
    print("[ERROR] Embedding failed after retries → returning None")
    return None

# This is the local downlaoded cross encoder which is making it difficult to run on cloud so switching to the api endpoint.
# reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
RERANK_THRESHOLD = 0.2

co = cohere.Client(os.getenv("COHERE_API_KEY"))

# Cohere returns results like:
# response.results
# Each item has:
# index
# relevance_score

def rerank(query, docs, retries=2):
    if not docs:
        return []

    for attempt in range(retries):
        try:
            response = co.rerank(
                query=query,
                documents=docs,
                model="rerank-v4.0-pro"
            )

            if not response or not response.results:
                raise ValueError("Empty rerank response")

            scores = [None] * len(docs)

            for r in response.results:
                scores[r.index] = r.relevance_score

            if any(s is None for s in scores):
                raise ValueError("Incomplete rerank results")

            return scores

        except Exception as e:
            msg = str(e).lower()

            if "rate" in msg:
                print(f"[WARN] Rate limit hit (attempt {attempt+1})")
            elif "auth" in msg:
                print(f"[ERROR] API key issue: {e}")
                break  # no point retrying
            else:
                print(f"[WARN] Reranker attempt {attempt+1} failed: {e}")

            time.sleep(1.5 * (attempt + 1))

    # 🔥 fallback (safe)
    print("[FALLBACK] Using default rerank scores")
    return [0.5] * len(docs)




# useful for local
PG_CONN_PARAMS = {
    "host": os.getenv("PG_HOST"), "port": os.getenv("PG_PORT"),
    "database": os.getenv("PG_DATABASE"), "user": os.getenv("PG_USER"),
    "password": os.getenv("PG_PASSWORD"),
    "sslmode": "require"
}



_conn = None

def get_connection():
    global _conn
    if _conn is None or _conn.closed != 0:
        _conn = psycopg2.connect(**PG_CONN_PARAMS, connect_timeout=5)
    return _conn

# 1. More is Better: A higher score is always better. A score close to 1.0 would mean
#       the document is a near-perfect answer to the question.
#    2. 0.1 Seems Low: On the surface, a threshold of 0.1 does seem very low.

#   Here is the reasoning behind choosing a value like 0.1. It's a classic trade-off
#   between Precision and Recall:


#    * High Threshold (e.g., `0.9`): This would be very precise. Only documents that are
#      an almost perfect match would get through. The risk is that you might discard a
#      document that is actually very relevant but isn't worded in the exact same way as
#      the question. You might miss important context.


#    * Low Threshold (e.g., `0.1`): This is more forgiving. It's designed to increase
#      recall, meaning it's less likely to accidentally throw away a useful document.
#      The strategy is to let a wider range of "potentially relevant" documents pass the
#      filter, and then trust the large, powerful llm_reasoner (llama3-70b-8192) to be
#      smart enough to find the useful information and ignore any minor noise in the
#      final context.


#   So, the value of 0.1 is a calibrated "sweet spot." It's high enough to filter out
#   complete junk but low enough to make sure no valuable context is accidentally
#   discarded.

db_conn = lancedb.connect(LANCEDB_DIR)
try:
    hierarchical_table = db_conn.open_table(HIERARCHICAL_TABLE_NAME)
except FileNotFoundError:
    print(f"[ERROR] LanceDB table '{HIERARCHICAL_TABLE_NAME}' not found. Please run advanced_ingest.py first.")
    hierarchical_table = None

try:
    graph_index_db = lancedb.connect(LANCEDB_INDEX_DIR)
    graph_index_table = graph_index_db.open_table(GRAPH_INDEX_TABLE_NAME)
    print(f"[INFO] Graph node index table '{GRAPH_INDEX_TABLE_NAME}' loaded successfully.")
except Exception as e:
    print(f"[ERROR] Graph node index table not found at '{LANCEDB_INDEX_DIR}/{GRAPH_INDEX_TABLE_NAME}'. Please run build_graph_index.py first. {e}")
    graph_index_table = None

try:
    G = nx.read_gml(GRAPH_FILE_PATH)
    print("[INFO] Knowledge graph loaded successfully.")
except Exception as e:
    print(f"[ERROR] Knowledge graph file '{GRAPH_FILE_PATH}' not found or invalid: {e}. Please run build_graph.py first.")
    G = None

try:
    with open(PARENT_DOCS_FILE, 'r') as f:
        parent_doc_store = json.load(f)
    print(f"[INFO] Parent document store loaded from {PARENT_DOCS_FILE} with {len(parent_doc_store)} entries.")
except FileNotFoundError:
    print(f"[ERROR] Parent document store file not found at '{PARENT_DOCS_FILE}'. Please run advanced_ingest.py first.")
    parent_doc_store = None # we are doing cause we can know the exact value and there is no ghosting of variables that are being lost.
except json.JSONDecodeError:
    print(f"[ERROR] Failed to decode JSON from {PARENT_DOCS_FILE}. The file might be corrupted.")
    parent_doc_store = None



# --- 2. Agent State & Pydantic Models ---

def merge_errors(existing: dict, new: dict) -> dict:
    if not new: return existing
    if not existing: return new
    return {**existing, **new}


def classify_sql_error(msg: str):
    msg = msg.lower()

    if "column" in msg and "does not exist" in msg:
        return "column_error"

    elif "operator does not exist" in msg or "join" in msg:
        return "join_error"

    elif "invalid input syntax" in msg or "cast" in msg or "type" in msg:
        return "type_error"

    elif "relation" in msg and "does not exist" in msg:
        return "table_error"

    else:
        return "unknown_error"
    

def extract_clean_answer(text: str) -> str:  # 🌶️🌶️🌶️🌶️🌶️🌶️This is a function which is working to deal in a text based way, but the best way would be to handle it in JSON way so that llm's can respond better. ALso you can make it more structured like Key Entities:
# - time_period: Q1
# - metric: revenue
# - filter: enterprise accounts
    sections = {
        "answer": "",
        "summary": "",
        "entities": "",
        "data_notes": "",
        "result_status": ""
    }

    current_section = None

    def normalize_header(s: str) -> str:
        return s.lower().replace(" ", "").strip()

    def clean(text: str) -> str:
        return " ".join(text.split()).strip()

    def is_meaningful(text: str) -> bool:
        return text and text.lower().strip(" .") not in ["none", ""]

    SECTION_MAP = {
        "answer:": "answer",
        "summary:": "summary",
        "keyentities:": "entities",
        "datanotes:": "data_notes",
        "resultstatus:": "result_status"
    }

    SKIP_PREFIXES = [
        "sqlquery:",
        "error:",
        "error(ifany):",
        "error(if any):"
    ]

    for line in text.splitlines():
        line_strip = line.strip()
        if not line_strip:
            continue

        normalized = normalize_header(line_strip)

        # -------------------------------
        # SECTION DETECTION
        # -------------------------------
        matched = False

        for prefix, section_name in SECTION_MAP.items():
            if normalized.startswith(prefix):
                current_section = section_name

                # safer inline extraction
                content = line_strip.split(":", 1)
                content = content[1].strip() if len(content) > 1 else ""

                if content:
                    sections[section_name] += content + " "

                matched = True
                break

        if matched:
            continue

        # -------------------------------
        # SKIP UNWANTED SECTIONS
        # -------------------------------
        if any(normalized.startswith(p) for p in SKIP_PREFIXES):
            current_section = None
            continue

        # -------------------------------
        # MULTI-LINE CAPTURE
        # -------------------------------
        if current_section:
            sections[current_section] += line_strip + " "

    # -------------------------------
    # CLEAN + NORMALIZE
    # -------------------------------

    answer = clean(sections["answer"])
    summary = clean(sections["summary"])
    entities = clean(sections["entities"])
    data_notes = clean(sections["data_notes"])
    result_status = clean(sections["result_status"]).lower()

    VALID_STATUS = {"success", "empty", "error", "partial"}
    if result_status and result_status not in VALID_STATUS:
        result_status = "partial"

    # -------------------------------
    # BUILD FINAL MEMORY
    # -------------------------------

    clean_parts = []

    if answer:
        clean_parts.append(f"Answer: {answer}")

    if summary:
        clean_parts.append(f"Summary: {summary}")

    if entities:
        # 🔥 small improvement: comma separation
        clean_parts.append(f"Context: {entities}")

    if is_meaningful(data_notes):
        clean_parts.append(f"Notes: {data_notes}")

    if is_meaningful(result_status) and result_status != "success":
        clean_parts.append(f"Result Status: {result_status}")

    return "\n".join(clean_parts).strip()

# Keys in dictionary must be unique, so while merging from left to right if there is a new values then it will overwrite it.

# The merge_errors function uses the expression {**existing, **new}. This dictionary
#   unpacking follows the exact same rule. It works from left to right:
#    1. It first lays down all the key-value pairs from the existing dictionary.
#    2. It then lays down all the key-value pairs from the new dictionary. If any key
#       from new already exists, its value overwrites the one from existing.

#   Let's trace your exact scenario:

#    * Current State: error is {"intent": "Classification failed", "sql_execution":
#      "Database timeout"}.


#    * New Event: The agent retries, and the sql_executor fails again, this time with a
#      different error. The node returns {"error": {"sql_execution": "Column 'rev' does
#      not exist"}}.


#    * `merge_errors` is called:
#        * existing = {"intent": "Classification failed", "sql_execution": "Database
#          timeout"}
#        * new = {"sql_execution": "Column 'rev' does not exist"}


#    * The Result of `{existing, new}`:
#        1. Starts with existing: {"intent": "Classification failed", "sql_execution":
#           "Database timeout"}
#        2. Unpacks new. It sees the key sql_execution.
#        3. It overwrites the existing value for that key.


#    * Final State: The error dictionary becomes {"intent": "Classification failed",
#      "sql_execution": "Column 'rev' does not exist"}.


#   Conclusion: You are correct. The new error for an existing key will replace the old
#   one. This is actually the desired behavior, as it ensures the agent's state always
#   contains the most recent, relevant error for a given step in the process, which is
#   the most useful information for the next retry attempt.

class AgentState(TypedDict):
    question: str
    rewritten_question: Optional[str] # these values are called state field, state key is also fine.
    intent: str
    hybrid_context: Optional[List[str]]
    structural_context: Optional[str] # NOte : if there is a typo from the node that updates the key like intent is written itnent, then that will create a new key with that value in it, the origianal intent , if extracted like state.get(intent) will return none, and if you retreive liek state['intent'] then it will cause, the value of it is silently sitting in the itnent which is a new key that is made.
    final_context: Optional[str]
    generated_sql: Optional[str]
    sql_result: Optional[Union[List[dict], str]]
    error: Annotated[Optional[dict], merge_errors]
    messages: Annotated[List[BaseMessage], lambda x, y: x + y] #Works during ONE execution of app.stream()
    final_answer_clean: Optional[str]
    retry_count: int
    safety_passed: bool
    total_retry_count: int
    sql_repeat_count: int

class RewrittenQuestion(BaseModel):
    question: str = Field(description="A standalone, complete question that includes all necessary context from the conversation history.")

class IntentClassification(BaseModel):
    intent: Literal["chat", "sql", "hybrid", "ambiguous"]
    reasoning: str = Field(description="The step-by-step reasoning for the intent classification.")

class SQLOutput(BaseModel):
    query: str
    explanation: str = Field(description="A brief, human-readable explanation of the SQL query's logic.")

class Entities(BaseModel):
    names: Optional[List[str]] = Field(
        description="List of PERSON or ORGANIZATION names mentioned in the user question. Example: ['Stacy Kelly', 'Acme Corp']"
    )

# never 👉 Never trust .with_structured_output() blindly, “best effort JSON suggestion”

structured_llm_router = llm_router.with_structured_output(IntentClassification)
sql_structured_llm = llm_reasoner.with_structured_output(SQLOutput)
entity_extractor_llm = llm_router.with_structured_output(Entities) # not being used can be used to get nodes from users questions
query_rewriter_llm = llm_router.with_structured_output(RewrittenQuestion) # the small model is enough unless you are heavy reasoning , and the model keeps on failing when you are rewriting until then you can keep the model suffieciently enough.

# --- 3. Agent Node Implementations ---

def _derive_sql_explanation(query: str) -> str:
    """
    Build a deterministic explanation from the SQL itself.
    This avoids free-text drift from model-generated explanations.
    """
    q = (query or "").strip()
    q_lower = q.lower()

    parts = []

    if "sum(" in q_lower:
        parts.append("Aggregates records using SUM.")
    if "count(" in q_lower:
        parts.append("Counts matching records.")
    if "avg(" in q_lower:
        parts.append("Computes averages over matching records.")
    if "group by" in q_lower:
        parts.append("Groups results before aggregation.")
    if "order by" in q_lower:
        parts.append("Orders rows by the requested ranking.")
    if "limit " in q_lower:
        parts.append("Applies a result limit.")

    if "left join" in q_lower and " is null" in q_lower:
        parts.append("Uses LEFT JOIN + IS NULL anti-join logic to keep unmapped rows.")

    if " at time zone " in q_lower:
        parts.append("Applies timezone conversion in SQL filters.")

    if " where " in q_lower:
        parts.append("Applies row-level filters in the WHERE clause.")

    if not parts:
        return "Selects data from the relevant tables using the joins and filters in the SQL."

    return " ".join(parts)

def _extract_names_safe(question: str):
    """
    Safely extract person/org names using LLM with fallback recovery.
    Never breaks execution.
    """
    try:
        result = entity_extractor_llm.invoke(question)
        names = getattr(result, "names", None)

        # 🔒 Strict validation
        if isinstance(names, list):
            names = [
                n for n in names
                if isinstance(n, str) and 2 <= len(n.split()) <= 3
            ]
            if names:
                return names

    except Exception as e:
        err_text = str(e)

        # 🔥 Recover from tool-call leakage (like query_transformer)
        import re, json

        tag_match = re.search(
            r"<function=Entities>(.*?)</function>",
            err_text,
            flags=re.DOTALL
        )

        if tag_match:
            raw = tag_match.group(1)

            # Try JSON parse
            try:
                parsed = json.loads(raw)
                names = parsed.get("names", None)

                if isinstance(names, list):
                    return names
            except:
                pass

            # Fallback: regex extraction of capitalized names
            cleaned = re.findall(
                r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+",
                raw
            )
            if cleaned:
                return cleaned

    return None

def _is_entity_specific_question(question: str) -> bool:
    """
    Prevent accidental entity filtering in broad/aggregate queries.
    """
    q = question.lower()

    broad_patterns = [
        "total ",
        "overall",
        "by region",
        "by segment",
        "distribution",
        "across",
        "trend",
        "compare"
    ]

    return not any(p in q for p in broad_patterns)


def _has_name_filter_intent(question: str) -> bool:
    """
    Determines whether a name-based SQL filter is justified
    based on user intent (explicit + implicit).
    """
    if not isinstance(question, str):
        return False

    import re

    q = question.lower()

    # -----------------------------------
    # 1. Explicit intent (strongest)
    # -----------------------------------
    explicit_markers = [
        "named ",
        "name is",
        "organization name",
        "org name",
        "account name",
        "customer name",
        "where name",
        "whose name"
    ]

    if any(m in q for m in explicit_markers):
        return True

    # -----------------------------------
    # 2. Possessive pattern
    # "Stacy Kelly's commission"
    # -----------------------------------
    if re.search(r"\b[a-z]+(?:\s+[a-z]+)*'s\b", q):
        return True

    # -----------------------------------
    # 3. Prepositional pattern (tightened)
    # "for Stacy Kelly", "of John Doe"
    # -----------------------------------
    if re.search(r"\b(for|of)\s+[a-z]+(?:\s+[a-z]+)+\b", q):
        if _is_entity_specific_question(question):
            return True

    # -----------------------------------
    # 4. LLM entity extraction (fallback)
    # -----------------------------------
    names = _extract_names_safe(question)

    if names and _is_entity_specific_question(question):
        return True

    return False

def _has_unjustified_name_filter(query: str, question: str) -> bool:
    """
    Detect policy/company name leakage into SQL row filters.
    Example to block unless explicitly requested:
      ... WHERE o.name ILIKE '%NexusFlow%'
    """
    if not isinstance(query, str):
        return False
    if _has_name_filter_intent(question):
        return False

    q_lower = query.lower()
    # Only block filters in predicates, not SELECT/GROUP BY usage of name.
    suspicious = re.search(
        r"\b[a-z_][a-z0-9_]*\.name\s*(?:=|like|ilike)\s*'[^']+'",
        q_lower
    )
    return bool(suspicious)

def query_transformer(state: AgentState):
    print("--- NODE: query_transformer ---")

    original_question = state.get("question")
    
    if not state.get("messages") or len(state["messages"]) <= 1:
        return {"rewritten_question": original_question}

    system_prompt = """You are a query rewriting expert.

Your task is to rewrite the LATEST/LAST user question ( HUMAN MESSAGE ) into a fully self-contained, standalone query.

CRITICAL RULES:
- The rewritten question MUST be fully self-contained and understandable without any prior context.
- You MUST include all relevant entities, filters, dates, and conditions from the conversation history.
- DO NOT summarize the conversation; only augment the latest question.
- DO NOT introduce any new information not present in the conversation.
- Preserve the exact intent of the user.
"""

    filtered_messages = [
        m for m in state["messages"]
        if isinstance(m, HumanMessage) or isinstance(m, AIMessage) # Note here we are adding AI messages, but becuase of our AI models you cannot completey depend on them especially while retries. Your model sends all the noise, the sql queries and the retireis and everything. You need to have better classification of the data if you are thinking of sending it to the models. 🌶️🌶️🌶️🌶️🌶️🌶️ Can implement later but it is a important bug that you need to keep in mind.
    ] 
    
    # filtered_messages = filtered_messages[-6:]# last few turns only, keeps writing focused and prevents long context drift. Context explosion, since we aer only going to be testing it now, let us not worry about it.

    
    messages = [SystemMessage(content=system_prompt)] + filtered_messages

    def _validate_rewrite(candidate: str) -> str:
        if not isinstance(candidate, str):
            raise ValueError("Rewritten question is not a string")
        rewritten_local = candidate.strip()
        if len(rewritten_local) < 5:
            raise ValueError("Rewritten question too short")
        if len(rewritten_local) > 3 * len(original_question):
            raise ValueError("Rewrite too long → likely hallucinated")
        if "select " in rewritten_local.lower():
            raise ValueError("Rewrite contains SQL → invalid")
        return rewritten_local

    try:
        result = query_rewriter_llm.invoke(messages)
        rewritten = _validate_rewrite(getattr(result, "question", None))

        print(f"Rewritten Question: {rewritten}")
        return {
            "rewritten_question": rewritten,
            "error": {"query_rewrite": None}
        }

    except Exception as e:
        print(f"--- WARNING: Query transformation failed: {e} ---")

        err_text = str(e)

        # Fallback 1: recover valid rewrite from failed function-call payload.
        tag_match = re.search(r"<function=RewrittenQuestion>(.*?)</function>", err_text, flags=re.DOTALL)
        if tag_match:
            try:
                recovered = _validate_rewrite(tag_match.group(1))
                print(f"Recovered Rewritten Question from failed_generation: {recovered}")
                return {
                    "rewritten_question": recovered,
                    "error": {"query_rewrite": "Recovered from tool_use_failed payload"}
                }
            except Exception:
                pass

        # Fallback 2: plain-text rewrite call (no structured parser).
        try:
            fallback_system_prompt = """You are a query rewriting expert.
Rewrite ONLY the latest user question into a standalone question using conversation context.
Return plain text only. No function tags. No JSON. No markdown."""
            fallback_messages = [SystemMessage(content=fallback_system_prompt)] + filtered_messages
            fallback_result = llm_router.invoke(fallback_messages)
            fallback_text = getattr(fallback_result, "content", "") or ""
            fallback_text = re.sub(r"</?function[^>]*>", "", fallback_text, flags=re.IGNORECASE).strip()
            fallback_text = fallback_text.strip("`").strip()

            recovered = _validate_rewrite(fallback_text)
            print(f"Recovered Rewritten Question from plain-text fallback: {recovered}")
            return {
                "rewritten_question": recovered,
                "error": {"query_rewrite": "Recovered via plain-text fallback"}
            }
        except Exception:
            pass

        return {
            "rewritten_question": original_question,
            "error": {"query_rewrite": str(e)}
        }

def intent_classifier(state: AgentState):
    """Classifies user intent."""
    print("--- NODE: intent_classifier ---")
    system_prompt = """You are an expert at classifying user intent for a RevOps SQL Copilot. Based on the provided conversation history, classify the intent of the LATEST user message.

**Intent Definitions & Examples:**
- **'sql'**: The user wants raw data, numbers, lists, or counts directly from the database.
  *Examples*: "How many invoices were voided?", "List all reps in the East region."
- **'chat'**: The user wants a definition or explanation found in company documents. No database query is needed.
  *Examples*: "What is a 'Ghost Contract'?", "Explain our revenue recognition policy."
- **'hybrid'**: A complex question requiring BOTH database data AND business rules from documents.
  *Examples*: "Calculate Stacy's commission for Q1.", "What is the total quota-weighted attainment for reps in the West region?"
- **'ambiguous'**: The query is nonsensical, irrelevant, or too vague.
  *Examples*: "asdfjkl", "What is the weather today?", "And for him?"

Routing rule:
- If the user asks for interpretation/policy guidance (e.g., "explain", "how should we interpret", "what does this mean") and does NOT explicitly request a numeric result/list/table output, prefer 'chat' over 'hybrid'/'sql'.
"""
    query = state.get("rewritten_question") or state.get("question")

    messages_for_llm = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=query)
    ]
    try:
        raw = structured_llm_router.invoke(messages_for_llm)

        # 🔒 HARD VALIDATION
        intent = getattr(raw, "intent", None)
        reasoning = getattr(raw, "reasoning", "")

        if not isinstance(intent, str):
            raise ValueError(f"Missing/invalid intent. Raw output: {raw}")

        intent = intent.strip().lower()

        if intent not in {"chat", "sql", "hybrid", "ambiguous"}:
            raise ValueError(f"Invalid intent value: {intent}. Raw: {raw}")

        ql = query.lower() if isinstance(query, str) else ""

        policy_or_interpretation = any(
            phrase in ql for phrase in [
                "explain",
                "what does",
                "what is",
                "how should",
                "interpret",
                "policy",
                "definition",
                "meaning",
                "which month should",
                "belong to",
                "why"
            ]
        )
        timezone_interpretation = (
            any(t in ql for t in ["utc", "est", "timezone"])
            and any(p in ql for p in ["month-end", "month end", "which month", "belong", "interpret", "reporting"])
        )
        explicit_data_request = any(
            phrase in ql for phrase in [
                "how many",
                "count",
                "list ",
                "show ",
                "top ",
                "sum",
                "average",
                "total ",
                "give me rows",
                "table of",
                "query"
            ]
        )

        if intent in {"sql", "hybrid"} and (policy_or_interpretation or timezone_interpretation) and not explicit_data_request:
            intent = "chat"

        return {
            "intent": intent,
            "error": {"intent": None}
        }

    except Exception as e:
        return {"intent": "ambiguous", "error": {"intent": f"Intent classification failed: {e}"}}

def ambiguous_responder(state: AgentState):
    print("--- NODE: ambiguous_responder ---")
    response = "I'm sorry, I am a specialized RevOps data assistant. Your question is outside my scope."
    return {"messages": [AIMessage(content=response)]}

def not_found_responder(state: AgentState): # this node is used to manage the knowledge graph failures. Like even if the question makes sense if you do not have the data then this would show up.
    print("--- NODE: not_found_responder ---")
    response = "I'm sorry, I couldn't find a definitive answer for that in our knowledge base. Please try rephrasing your question."
    return {"messages": [AIMessage(content=response)]}

def hybrid_retriever(state: AgentState):
    """Performs hybrid search (vector + FTS), reranks, and selects the top K."""
    print("--- NODE: hybrid_retriever ---")
    if not hierarchical_table or not parent_doc_store:
        return {"hybrid_context": None, "error": {"hybrid_retrieval": "Knowledge base not loaded."}}
    
    query = state.get("rewritten_question") or state.get("question")
    try:
        def _collect_rows(search_builder):
            """LanceDB compatibility across versions."""
            if hasattr(search_builder, "to_list"):
                return search_builder.to_list()
            if hasattr(search_builder, "to_pylist"):
                return search_builder.to_pylist()
            if hasattr(search_builder, "to_pandas"):
                return search_builder.to_pandas().to_dict("records")
            raise AttributeError("Search result builder has no supported materialization method.")

        # --------------------------------------------------
        # 🔍 Vector Search (SAFE)
        # --------------------------------------------------

        vector_results = []
        vector_error = None

        try:
            vector_results = _collect_rows(hierarchical_table.search(query).limit(7))

            # 🔥 FIX: validate structure
            vector_results = [
                r for r in vector_results
                if isinstance(r, dict) and r.get("text") and r.get("metadata")
            ]

        except Exception as e:
            vector_error = str(e)
            print(f"[WARN] Vector search failed: {e}")


        # --------------------------------------------------
        # 🔍 FTS Search (SAFE)
        # --------------------------------------------------

        fts_results = []
        fts_error = None

        try:
            fts_results = _collect_rows(hierarchical_table.search(query, query_type="fts").limit(7))

            # 🔥 FIX: validate structure
            fts_results = [
                r for r in fts_results
                if isinstance(r, dict) and r.get("text") and r.get("metadata")
            ]

        except Exception as e:
            fts_error = str(e)
            print(f"[WARN] FTS search failed: {e}")


        # --------------------------------------------------
        # 🧠 Merge Logic (PARTIAL SUCCESS SAFE)
        # --------------------------------------------------

        if not vector_results and not fts_results:
            return {
                "hybrid_context": None,
                "error": {
                    "hybrid_retrieval": {
                        "type": "lancedb_failure",
                        "vector_error": vector_error,
                        "fts_error": fts_error
                    }
                }
            }
        
        child_docs = list({doc['text']: doc for doc in vector_results + fts_results}.values()) # since the keys in the dictionary should be unique, there will be no overlapping of the chunks and since the chunks are the same just the method of retreival is different so the doc['text'] key would be the same. we are using like doc text cause this search would give vector, text, metadata. 
        if not child_docs: return {"hybrid_context": None, "error": {"hybrid_retrieval": "Could not retreive chunks"}}

       # 🔥 NEW: limit before rerank
        # child_docs = child_docs[:8] # I do not want this hard limit as of now but yaa I will look into it.

        # pairs = [[query, doc['text']] for doc in child_docs] # ---> can be used for the local version but since we are using cloud cross encoder we are doing it like this and based on the function rerank we only give it the text.
        docs = [doc['text'] for doc in child_docs] #-----> useful for cloud as the rerank function is based on like this, remember that if you are doing local testing make sure it is like commented and the local ones are used.

        # 🔥 FIX: reranker safety
        try:
            # scores = reranker.predict(pairs) # these are just numbers which say about the scores in the same order.  ---> for local
            scores = cached_rerank(query, tuple(docs))  # --> for the crossencoder via the api calls, this is being used for caching , hence we are using the tuple to make a hashable key and also remember to check the streamlit notes if you want and also the app.py function if you want.
            print("[SUCCESS RERANKER] - The new reranker has ran successfully without any error")

        except Exception as e:
            print(f"[WARN] Reranker failed: {e}")
            scores = None

        if not scores or len(scores) != len(docs):
            print("[WARN] Invalid reranker output → fallback")
            scores = None

        # 🔥 Detect fallback mode
        is_fallback = scores is None


        # 🔥 Apply logic
        if is_fallback:
            print("[INFO] Reranker fallback → skipping filtering")

            # Keep original retrieval order
            scored_docs = [(1.0, doc) for doc in child_docs]

        else:
            # Normal reranking path
            scored_docs = [
                (score, doc)
                for score, doc in zip(scores, child_docs)
                if score > RERANK_THRESHOLD
            ]

            # 🔥 If everything filtered out → fallback
            if not scored_docs:
                print("[INFO] All docs filtered → fallback to top docs")
                scored_docs = list(zip(scores, child_docs))


        # 🔥 Final sort (only meaningful if not fallback)
        scored_docs.sort(key=lambda x: x[0], reverse=True)
        
        # Group chunks by parent_id
        parent_groups = {}

        for score, doc in scored_docs[:10]:  # slightly larger pool for grouping

            metadata = doc.get("metadata") or {}  # 🔥 FIX: metadata safety

            parent_id = metadata.get('parent_id')

            # 🔥 FIX: prevent None collapsing all docs into one group
            if not parent_id:
                parent_id = f"orphan_{uuid.uuid4()}"

            if parent_id not in parent_groups:
                parent_groups[parent_id] = {
                    "header": metadata.get('parent_header', 'Unknown Section'),
                    "chunks": []
                }

            parent_groups[parent_id]["chunks"].append((score, doc['text']))


        # Build final context (1 entry per parent)
        final_context = []

        for parent_id, data in parent_groups.items():
            header = data["header"]

            # Sort chunks within parent by score
            sorted_chunks = sorted(data["chunks"], key=lambda x: x[0], reverse=True)

            # Take top 1–2 chunks per parent (controlled expansion)
            selected_chunks = [text for _, text in sorted_chunks[:2]]

            combined_text = "\n".join(selected_chunks)

            formatted_chunk = f"Section: {header}\nContent:\n{combined_text}"

            final_context.append(formatted_chunk)

        # Optional: limit total parents (token control)
        # final_context = final_context[:5]

        return {"hybrid_context": final_context if final_context else None}

    except Exception as e:
        return {"hybrid_context": None, "error": {"hybrid_retrieval": f"Failed: {e}"}}

# THERE ARE A LOT OF IMPROVEMENTS THAT WE  CAN DO WITH GRAPHS LIKE ADDING SEMANTIC QUERY PLANNER, ADDING METRIC AND KNOWLEDGE GRAPHS ALONG WITH THE SCHEMA GRAPH THAT WE HAVE, ADDING QUERY LOG AND SUBGRAPH CACHING, ADDING WEIGHT STEINER GRAPH AND JOIN GRAPH INDEX. LOT OF ADDITIONS CAN BE DONE BUT FOR NOW THIS SHOULD DO. BUT FOR A LONG PRODUCTION SCALE RAG SYSTEM THAT WE ARE BUILDING YOU SHOULD DEFINITELY KNOW ALL OF THIS. CAUSE WITH STENIER GRAPH SHORT IS NOT EQUAL TO THE CORRECT RIGHT PATH.

def graph_explorer(state: AgentState):
    """
    GRAPH EXPLORER V4 — Production Graph-RAG traversal

    Features:
    - Hybrid node retrieval
    - Column → table normalization
    - Steiner Tree traversal (shortest path union)
    - Join-edge prioritization
    - Graph centrality relevance scoring
    - Adaptive context expansion
    - Token-aware formatting
    - Robust error handling compatible with merge_errors reducer
    """

    print("--- NODE: graph_explorer (V4: Steiner Graph Retrieval) ---")

    # --------------------------------------------------
    # 0️⃣ Safety checks
    # --------------------------------------------------

    if not G or not graph_index_table:
        print("[ERROR] Graph or index not loaded.")
        return {
            "structural_context": None,
            "error": {"graph": "Graph or graph index not loaded."}
        }

    TOKEN_BUDGET = 2000
    question = state.get("rewritten_question") or state.get("question")

    # 🔥 FIX: strict validation
    if not isinstance(question, str) or not question.strip():
        return {
            "structural_context": None,
            "error": {"graph": "Invalid or empty question."}
        }

    try:

        # --------------------------------------------------
        # 1️⃣ Hybrid Node Retrieval
        # --------------------------------------------------

        try:
            results = graph_index_table.search(
                question,
                query_type="hybrid"
            ).limit(20).to_list()
        except Exception as e:
            err_msg = str(e)
            if "No embedding function for vector" in err_msg:
                print("[Graph Explorer] Hybrid search unavailable (missing embedding metadata). Falling back to manual vector + FTS.")
                merged = {}

                # Vector fallback using the globally loaded embedding model.
                try:
                    query_vec = cached_embed(question)
                    if query_vec is not None:
                        # reduced limit from 20 to 12 to save tokens 
                        for row in graph_index_table.search(query_vec).limit(12).to_list():
                            node_id = row.get("node_id")
                            if node_id and node_id not in merged:
                                merged[node_id] = row
                        print("[EMBEDDING HUGGING FACE SUCESS] The embedding model is working, it has searched as we want") #this is to check whether the model hf embedding is working or not
                    else:
                        raise ValueError(" Graph Index Search Embedding failed")#since you have raise an error here it will be recoridng here
                except Exception as vec_err:
                    print(f"[Graph Explorer] Vector fallback failed: {vec_err}")

                # FTS fallback (if FTS index exists).
                try:
                    for row in graph_index_table.search(question, query_type="fts").limit(12).to_list(): # reduced limit from 20 to 12 to save tokens 
                        node_id = row.get("node_id")
                        if node_id and node_id not in merged:
                            merged[node_id] = row
                except Exception as fts_err:
                    print(f"[Graph Explorer] FTS fallback failed: {fts_err}")

                results = list(merged.values())
            else:
                return {
                    "structural_context": None,
                    "error": {"graph": f"Graph index search failed: {err_msg}"}
                }

        # 🔥 FIX: validate results
        clean_results = []
        for r in results:
            if isinstance(r, dict) and r.get("text") and r.get("node_id"):
                clean_results.append(r)

        if not clean_results:
            return {
                "structural_context": None,
                "error": {"graph": "No relevant schema nodes found (invalid index results)."}
            }

        results = clean_results

        # You can slice results to reduce the token size
        # results = results[:10] ---> you can do this to save tokens but I am not planning on doing this as of now. I will only take the top 10 after reranking but not before.

        # --------------------------------------------------
        # 2️⃣ Cross-Encoder Reranking
        # --------------------------------------------------

        # pairs = [[question, r["text"]] for r in results]-- > use this incase of local
        docs = [r["text"] for r in results] # ---> this is so that we can match it with the rerank function that we made, if we are doing local we can coment this and use pairs

        # 🔥 FIX: reranker safety
        try:
            # scores = reranker.predict(pairs) # this will just have the score in the same order of the pairs. ----> This will be used when you are doing local
            scores = cached_rerank(question, tuple(docs)) # use when you are caching results from the api endpint to save credits.
            print("[SUCCESS RERANKER] - The new reranker has ran successfully without any error")
        except Exception as e:
            print(f"[WARN] Reranker failed: {e}")
            scores = [0.5] * len(docs)

        scored_results = list(zip(scores, results))

        scored_results.sort(key=lambda x: x[0], reverse=True) # to sort we should give a key and here we are using a lamda function to say that sort based on the score and reverse means descending order the default is ascending over here.

        top_results = [r for _, r in scored_results[:10]] 

        start_nodes = [
            r.get("node_id")
            for r in top_results
            if r.get("node_id") and r.get("node_id") in G  # 🔥 FIX
        ]

       # start_nodes = list(set(start_nodes)) # You would want to filter out and keep only the disctinct ones. But with this the order will not be preversed so you cannot get the anchor node. Since order is important and you want to skip duplicates you implement the method below.

        seen = set()
        start_nodes = [x for x in start_nodes if not (x in seen or seen.add(x))]

        print(f"[Graph Explorer] Entry nodes after reranking: {start_nodes}")

        # --------------------------------------------------
        # 2️⃣ Column → Table Normalization
        # --------------------------------------------------

        normalized_nodes = []
        seen_normalized = set()

        for node in start_nodes:
            normalized = node.split(".")[0] if "." in node else node
            if normalized in G and normalized not in seen_normalized:
                normalized_nodes.append(normalized)
                seen_normalized.add(normalized)

        start_nodes = normalized_nodes

        # Build JOIN-only graph once and reuse it for expansion + pathing.
        join_graph = nx.Graph()
        for u, v, data in G.edges(data=True):
            if isinstance(data, dict) and data.get("label") == "JOINS_WITH":
                join_graph.add_edge(u, v)

        # If retrieval is too narrow, expand via JOIN graph neighbors (controlled breadth/depth).
        # This helps recover bridge tables needed for multi-hop analytical queries.
        if len(start_nodes) <= 2:
            expanded_tables = list(start_nodes)
            visited_tables = set(start_nodes)
            frontier = list(start_nodes)

            for _ in range(2):  # up to 2 hops
                next_frontier = []
                for table in frontier:
                    if table not in join_graph:
                        continue

                    neighbors = sorted(
                        list(join_graph.neighbors(table)),
                        key=lambda n: join_graph.degree(n),
                        reverse=True
                    )

                    for neighbor in neighbors:
                        if neighbor in visited_tables:
                            continue
                        visited_tables.add(neighbor)
                        expanded_tables.append(neighbor)
                        next_frontier.append(neighbor)
                        if len(expanded_tables) >= 6:
                            break
                    if len(expanded_tables) >= 6:
                        break

                if len(expanded_tables) >= 6 or not next_frontier:
                    break
                frontier = next_frontier

            start_nodes = expanded_tables

        print(f"Entry Nodes (Normalized): {start_nodes}")

        if not start_nodes:
            return {
                "structural_context": None,
                "error": {"graph": "No valid start nodes after normalization."}
            }

        # --------------------------------------------------
        # 3️⃣ Steiner Tree Approximation (JOIN-AWARE + ANCHOR)
        # --------------------------------------------------

        connected_nodes = [n for n in start_nodes if n in join_graph]
        isolated_nodes = [n for n in start_nodes if n not in join_graph]

        anchor_node = connected_nodes[0] if connected_nodes else start_nodes[0]

        steiner_nodes = set([anchor_node]) #This is set right, it will contain the list of all the nodes and it will keep in updating. It become the union of all the paths and keep on updating. But one important thing is the nodes can be in any way and not in the same particular order that the code will be. The LLM will be given the ndoes and the join conditions and the llm can figure out what is the way. If you want order also then you should use Join Graph INdex.
        steiner_nodes.update(isolated_nodes)

        # steiner nodes only contain the shortest path from the anchor_node and the other start nodes only.

        for node in connected_nodes:

            if node == anchor_node:
                continue

            try:
                path = nx.shortest_path(join_graph, anchor_node, node) # we are only using the join graph as of now.
                steiner_nodes.update(path)

            except nx.NetworkXNoPath:
                continue

        # Fallback if graph is disconnected
        if len(steiner_nodes) <= 1:

            print("--- No connecting paths found, expanding local neighborhoods ---")

            expanded = set(steiner_nodes)

            for node in start_nodes:

                try:
                    neighbors = list(G.neighbors(node))

                    for n in neighbors:
                        edge_data = G.get_edge_data(node, n)

                        # 🔥 FIX: controlled expansion (prevents noise explosion)
                        if edge_data and edge_data.get("label") in ["JOINS_WITH", "HAS_COLUMN"]:
                            expanded.add(n)

                except:
                    continue

            # 🔥 FIX: fail if still useless
            if len(expanded) <= 1:
                return {
                    "structural_context": None,
                    "error": {"graph": "Insufficient graph connectivity after expansion."}
                }

            steiner_nodes = expanded

        # --------------------------------------------------
        # 4️⃣ Join Edge Prioritization
        # --------------------------------------------------

        prioritized_nodes = set()

        for u, v, data in G.edges(data=True):

            # 🔥 FIX: avoid duplicate amplification
            if data.get("label") == "JOINS_WITH" and u in steiner_nodes and v in steiner_nodes:
                prioritized_nodes.add(u)
                prioritized_nodes.add(v)

        final_nodes = set(steiner_nodes)

        # 🔥 FIX: only expand if too small
        if len(final_nodes) < 4:
            final_nodes = final_nodes.union(prioritized_nodes)

        # This step is just simply for more recall maybe so that the extra tables will help in the sql generation, but also one more thing is that the LLM can also be confused cause of the more noise. So we are trusting the LLM to actually filter properly, so given that you ar senting the context properly about the tables, columns and all the rest of the descriptions it should help. 

        # Current setup is “expand → trust LLM”
        # Future setup here would be to actually use a cross encoder again. “expand → filter → trust LLM” -> But I actually feel that is also reduntant. Should actually look for a better way to deal with this.

        # --------------------------------------------------
        # 5️⃣ Graph Centrality Ranking
        # --------------------------------------------------

        try:
            centrality = nx.degree_centrality(G)  # computes “How connected is each node in the graph?”
        except Exception as e:
            print(f"[WARN] Centrality failed: {e}")
            centrality = {}

        node_scores = []

        for node in final_nodes:

            if node not in G:  # 🔥 FIX
                continue

            base_score = centrality.get(node, 0) # if you do not get the centrality then just give 0.

            distance_bonus = 0

            for entry in start_nodes:

                try:
                    distance = nx.shortest_path_length(G, node, entry) # here we ar using the whole graph, but if you use the join graph it would be better, but anyways the graph would penalise it so, there is no issue.

                    # 🔥 FIX: avoid long-distance noise
                    if distance > 5:
                        continue

                    distance_bonus += 1 / (distance + 1) # distance_bonus is reset per outer node, NOT per inner loop, For EACH node: sum(distance to ALL start_nodes), distance_bonus = combined relevance to ALL query nodes -> gives us like how close this node is to the question.

                except:
                    continue  # used when there is no path between nodes.

            # 🔥 NEW: Type-based boost ( moving from simple to actually getting better scoring based on the type of node we are using)
            node_type = G.nodes[node].get("label", "")
            if not node_type:
                node_type = "Column" if "." in node else "Table"

            type_bonus = 0

            if node_type == "Table":
                type_bonus += 0.3

                join_degree = sum(
                    1 for _, _, d in G.edges(node, data=True)
                    if d.get("label") == "JOINS_WITH"
                )

                type_bonus += min(join_degree * 0.05, 0.3)

            elif node_type == "Column":
                type_bonus -= 0.1

            score = base_score + distance_bonus + type_bonus #global importance (centrality) + multi-point relevance (distance to all start nodes)

            node_scores.append((score, node))

        node_scores.sort(reverse=True) # for tuples the sorting is based on the first element which is the score here , and if it is tie then they would be using the second element. But one important thing is that there is no key that is necessary. It would break if you kept node as the first element.

        ranked_nodes = [n for _, n in node_scores]

        # It is possible that the the nodes that are not in the start_nodes can end up getting a higher score related to the question. Think of this as the reranking of the nodes. This is a good way to filter out the nodes. Cause the order of the nodes would be important for the LLM.

        # --------------------------------------------------
        # 7️⃣ Token-Aware Context Assembly (STRUCTURED)
        # --------------------------------------------------

        tables = {}
        joins = set()
        columns_map = {}

        token_count = 0
        token_exceeded = False  # 🔥 FIX

        def estimate_tokens(text):
            return len(text.split())

        for node_id in ranked_nodes:

            if token_exceeded:
                break  # 🔥 FIX

            if node_id not in G:
                continue

            node_data = G.nodes[node_id]

            node_type = node_data.get("label", "Unknown")
            if node_type == "Unknown" or not node_type:
                node_type = "Column" if "." in node_id else "Table"
            description = node_data.get("description", "N/A")

            table_name = node_id if node_type == "Table" else node_id.split('.')[0]

            try:
                table_node_data = G.nodes.get(table_name, {}) if table_name in G else {}
                table_description = table_node_data.get("description", "") if isinstance(table_node_data, dict) else ""
                best_table_desc = table_description or (description if node_type == "Table" else "Referenced table")

                if table_name not in tables:
                    table_text = f"{table_name}: {best_table_desc}"
                    t_tokens = estimate_tokens(table_text)

                    if token_count + t_tokens > TOKEN_BUDGET:
                        print("--- Graph Explorer: Token budget reached (tables) ---") 
                        token_exceeded = True
                        break

                    tables[table_name] = best_table_desc
                    token_count += t_tokens
                elif tables[table_name] == "Referenced table" and best_table_desc != "Referenced table":
                    # Upgrade placeholder with real table description when we encounter it later.
                    tables[table_name] = best_table_desc

                join_edges = []
                column_edges = []

                for u, v, edge_data in G.edges(node_id, data=True):
                    if edge_data.get("label") == "JOINS_WITH":
                        join_edges.append((u, v, edge_data))
                    elif edge_data.get("label") == "HAS_COLUMN":
                        column_edges.append((u, v, edge_data))

                for u, v, edge_data in join_edges:

                    join_condition = edge_data.get("join_condition", "N/A")

                    if join_condition not in joins:
                        j_tokens = estimate_tokens(join_condition)

                        if token_count + j_tokens > TOKEN_BUDGET:
                            print("--- Graph Explorer: Token budget reached (joins) ---")  
                            token_exceeded = True
                            break

                        joins.add(join_condition)
                        token_count += j_tokens

                for u, v, edge_data in column_edges:

                    if v not in G:  # 🔥 FIX
                        continue

                    col_data = G.nodes[v]  # 🔥 FIX

                    col_name = v.split('.')[-1]

                    col_text = (
                        f"{table_name}.{col_name} ({col_data.get('data_type','N/A')}): "
                        f"{col_data.get('description','N/A')}"
                    )

                    c_tokens = estimate_tokens(col_text)

                    if token_count + c_tokens > TOKEN_BUDGET:
                        print("--- Graph Explorer: Token budget reached (columns) ---")
                        token_exceeded = True
                        break

                    columns_map.setdefault(table_name, []).append(
                        f"  - {col_name} ({col_data.get('data_type','N/A')}): {col_data.get('description','N/A')}"
                    )
                    token_count += c_tokens

            except Exception:
                continue

        # -------------------------------
        # FORMAT BLOCKS
        # -------------------------------

        # 🔥 FIX: stronger validation
        if not tables:
            return {
                "structural_context": None,
                "error": {"graph": "Graph traversal produced no usable tables."}
            }

        tables_block = "\n".join([
            f"- {t}: {desc}" for t, desc in tables.items()
        ])

        joins_block = "\n".join(sorted(list(joins)))

        columns_block = ""
        for t, cols in columns_map.items():
            columns_block += f"{t}:\n" + "\n".join(cols) + "\n\n"

        final_context = f"""
        ======================
        TABLES
        ======================
        {tables_block}

        ======================
        JOIN PATHS
        ======================
        {joins_block}

        ======================
        COLUMNS
        ======================
        {columns_block}
        """

        print(f"Graph Context Tables: {len(tables)} | Joins: {len(joins)} | Tokens: {token_count}")

        return {
            "structural_context": final_context.strip()
            # 🔥 FIX: removed error overwrite (was wiping previous errors)
        }

    except Exception as e:

        import traceback

        print(f"[ERROR] Graph Explorer V4 failed: {e}\n{traceback.format_exc()}")

        return {
            "structural_context": None,
            "error": {"graph": f"Graph exploration failed: {str(e)}"}
        }

# You can have a semantic query retriever, cause you are not using JOin graph index and so here,  the shortest path might not be the best path and so for the LLM to figure out is not a good thing, use to only filter the best paths before sending it to the LLM.


def context_builder(state: AgentState):
    print("--- NODE: context_builder ---")

    try:
        intent = state.get("intent", "sql")
        hybrid_context = state.get("hybrid_context") or []
        structural_context = state.get("structural_context") or ""
        question = state.get("rewritten_question") or state.get("question")

        if not question:
            return {
                "final_context": None,
                "error": {"context_builder": "Missing question"}
            }

        # -------------------------------
        # 1. SCHEMA CONTEXT (Always Needed)
        # -------------------------------
        schema_block = structural_context if structural_context else "None"
        structural_context_for_state = structural_context

        # Fallback schema should be used only when the intent has no retrieved context.
        # In practice:
        # - SQL: use fallback when structural graph context is missing.
        # - Hybrid: only use fallback if BOTH semantic and structural contexts are missing.
        #   (normally unreachable due to upstream routing, but kept as a hard guardrail).
        has_semantic_context = bool(hybrid_context)
        use_schema_fallback = (
            (intent == "sql" and not structural_context)
            or (intent == "hybrid" and not structural_context and not has_semantic_context)
        )

        if use_schema_fallback:
            fallback_path = os.path.join(KNOWLEDGE_BASE_DIR, "schema_summary.md")
            try:
                with open(fallback_path, "r") as f:
                    fallback_schema = f.read().strip()
                if fallback_schema:
                    structural_context_for_state = fallback_schema
                    schema_block = f"""
======================
TABLES (FALLBACK)
======================
{fallback_schema}
"""
            except Exception:
                # Keep existing behavior if fallback is unavailable.
                pass

        # -------------------------------
        # 2. BUSINESS CONTEXT (Conditional)
        # -------------------------------
        if intent == "hybrid":
            semantic_block = "\n\n".join(hybrid_context[:5]) if hybrid_context else "None"
        else:
            semantic_block = "None"

        # -------------------------------
        # 3. SQL RULES (Always Needed)
        # -------------------------------
        sql_rules = """
SQL RULES (PostgreSQL 15 - STRICT):

1. SAFETY
- Only SELECT queries allowed
- NEVER use INSERT, UPDATE, DELETE, DROP, ALTER

2. PERFORMANCE
- Always include LIMIT 100 unless aggregation/count
- NEVER use SELECT *
- Select only required columns

3. AGGREGATIONS
- Always alias aggregations
  Example: SUM(amount_paid) AS total_revenue
- Use GROUP BY when needed

4. JOINS
- Always use explicit JOIN syntax
- Always use table aliases (accounts a, payments p)

5. DIVISION SAFETY
- Always use NULLIF to avoid division by zero
  Example: revenue / NULLIF(goal, 0)

6. STRING MATCHING
- Always use ILIKE for case-insensitive matching

7. DATE HANDLING
- Use CURRENT_DATE when needed
- Use proper DATE filtering

8. JOIN TRAPS (IMPORTANT) -> It's a hostile schema so look for specific join information given.
- payments.contract_ref_id is VARCHAR and can contain non-numeric prefixes/suffixes.
- SAFE join pattern:
  CAST(SUBSTRING(p.contract_ref_id FROM '[0-9]+') AS INTEGER) = c.contract_id
- NEVER use direct CAST(p.contract_ref_id AS INT) unless guaranteed numeric.

9. FILTER INTENT SAFETY
- Do NOT add organization/account/customer name literal filters unless the user explicitly asks to filter by a specific name.
- Company/policy text in the question (e.g., "NexusFlow finance policy") is context, not a row filter.
"""

        # -------------------------------
        # 4. Final Structured Prompt
        # -------------------------------
        final_context = f"""
You are a senior data analyst writing PostgreSQL 15 SQL queries.

======================
SCHEMA CONTEXT
======================
{schema_block}
"""

    # Only include business context if needed - but we are only doing this for Hybrid it could be great if we could this also for sql only cause info regarding the docs can help the sql also. Let us do implement this again later. Also it can be great if you can also do the graph traversal based on hybrid context.🌶️🌶️🌶️🌶️🌶️
        if intent == "hybrid":
            final_context += f"""

======================
BUSINESS CONTEXT
======================
{semantic_block}
"""

        final_context += f"""

    ======================
    SQL RULES
    ======================
    {sql_rules}

    ======================
    USER QUESTION
    ======================
    {question}

    ======================
    INSTRUCTIONS
    ======================
    - Use ONLY tables and columns from SCHEMA CONTEXT
    - Follow JOIN CONDITIONS strictly
    - NEVER guess joins
    - NEVER invent columns
    - Prefer correct joins over incomplete answers
    - If unsure, choose safest valid SQL
    """

    # Add hybrid-specific instruction
        if intent == "hybrid":
            final_context += """
    - Apply BUSINESS CONTEXT rules when generating SQL
    """

        final_context += """
    - Prefer correct joins over assumptions
    - Ensure SQL is executable and correct
    """

        return {
            "final_context": final_context,
            "structural_context": structural_context_for_state,
            "error": {"context_builder": None}
        }

    except Exception as e:
        return {
            "final_context": None,
            "error": {"context_builder": f"Failed: {str(e)}"}
        }


def synchronize(state: AgentState):
    intent = state.get("intent")

    if intent == "hybrid":
        if not state.get("hybrid_context") and not state.get("structural_context"):
            return {"error": {"sync": "No hybrid or structural context"}}

    elif intent == "sql":
        if not state.get("structural_context"):
            return {"error": {"sync": "Missing structural context"}}

    elif intent == "chat":
        if not state.get("hybrid_context"):
            return {"error": {"sync": "Missing knowledge context"}} # since there are no retries with this it is fine, but once there are retries for hybrid_context and structural_context you would need to sort that out as well.
    print("--- NODE: synchronize (Waiting for retrievers) ---")
    return {}

# LangGraph does NOT do:
# hybrid_retriever → next node
# graph_explorer → next node
# Instead, it tracks:

# “Which nodes are supposed to reach the same next node?”
# ”
# 🧱 Step 3: Both Nodes Point to synchronize
# workflow.add_edge("hybrid_retriever", "synchronize")
# workflow.add_edge("graph_explorer", "synchronize")
# 👉 This creates a join condition
# 🚨 THIS IS THE CRUCIAL PART
# LangGraph internally says:

# “synchronize has TWO incoming edges
# → I will WAIT until BOTH are done”
# hybrid_retriever finishes ❌ (WAIT)
# graph_explorer finishes ❌ (WAIT)

# Only when BOTH are done:
# → call synchronize(state)
# 👉 It does NOTHING to state

# But:

# ✅ It guarantees timing
# ✅ It forces both branches to complete
# ✅ It receives fully merged state
def sql_generator(state: AgentState):
    print("--- NODE: sql_generator ---")

    final_context = state.get("final_context", "")
    intent = state.get("intent", "sql")
    structural_context = state.get("structural_context") or ""
    previous_query = (state.get("generated_sql") or "").strip()
    effective_question = state.get("rewritten_question") or state.get("question") or ""

    # --------------------------------------------------
    # 🧠 Error Prioritization (ONLY ONE ACTIVE ERROR)
    # --------------------------------------------------

    error = state.get("error", {}) or {}

    priority_order = ["sql_execution", "safety", "sql_generation"]
    active_error_type = None
    active_error = None

    for err_type in priority_order:
        if error.get(err_type):
            active_error_type = err_type
            active_error = error[err_type]
            break

    # --------------------------------------------------
    # 🧠 Error-Aware Context (NON-OVERLAPPING)
    # --------------------------------------------------

    error_context = ""

    if active_error_type == "sql_execution":
        err = active_error

        if isinstance(err, dict):
            error_type = err.get("type", "unknown")

            error_context = f"""
            Previous SQL execution failed.

            Error Type: {error_type}
            Error Message: {err.get("message", "N/A")}

            Failed Query:
            {err.get("failed_query", state.get("generated_sql", ""))}

            Fix the query based on the error.
            """

            # 🎯 Targeted correction (NO duplication with retry block)
            if error_type == "column_error":
                error_context += """
                CORRECTION:
                - Use ONLY valid columns from SCHEMA CONTEXT
                - Verify aliases carefully
                """

            elif error_type == "join_error":
                error_context += """
                CORRECTION:
                - Fix JOIN conditions
                - Follow JOIN PATHS strictly
                """

            elif error_type == "type_error":
                error_context += """
                CORRECTION:
                - Fix type mismatches using safe CAST patterns
                - For payments.contract_ref_id joins, use:
                  CAST(SUBSTRING(p.contract_ref_id FROM '[0-9]+') AS INTEGER)
                - Avoid direct CAST on dirty string IDs
                """

            elif error_type == "table_error":
                error_context += """
                CORRECTION:
                - Use ONLY valid tables from SCHEMA CONTEXT
                """

            elif error_type == "connection_error":
                error_context += """
                CORRECTION:
                - Retry same query without modification
                """

            elif error_type == "timeout_error":
                error_context += """
                CORRECTION:
                - Simplify query
                - Reduce joins or add LIMIT
                """

            else:
                error_context += """
                CORRECTION:
                - Fix the query logically
                """

        else:
            error_context = f"""
            Previous SQL execution failed.

            Error:
            {err}

            Fix the query.
            """

    # --------------------------------------------------
    # ⚠️ SAFETY ERROR HANDLING
    # --------------------------------------------------

    elif active_error_type == "safety":
        safety_err = active_error

        error_context = f"""
        Previous query failed safety validation.

        Reason:
        {safety_err}

        Fix the query to comply with safety rules.
        """

        if isinstance(safety_err, str):
            s = safety_err.lower()

            if "multiple" in s:
                error_context += """
                CORRECTION:
                - Ensure only ONE SQL statement
                - Remove extra semicolons
                """

            elif "select" in s:
                error_context += """
                CORRECTION:
                - Only generate SELECT queries
                - Do NOT use INSERT/UPDATE/DELETE
                """

            elif "forbidden" in s:
                error_context += """
                CORRECTION:
                - Remove restricted keywords
                - Keep query read-only
                """

    # --------------------------------------------------
    # ⚠️ SQL GENERATION ERROR HANDLING
    # --------------------------------------------------

    elif active_error_type == "sql_generation":
        gen_err = active_error

        error_context = f"""
        Previous SQL generation failed.

        Error:
        {gen_err}

        Generate a valid SQL query.
        """
        if isinstance(gen_err, str) and "name filter appears unjustified" in gen_err.lower():
            error_context += """
            CORRECTION:
            - Remove literal filters on *.name columns unless explicitly requested.
            - Treat policy/company mentions in the question as context, not SQL row filters.
            """

    # --------------------------------------------------
    # 🛑 Weak Schema Guard (No Hallucinated SQL)
    # --------------------------------------------------
    if intent in {"sql", "hybrid"}:
        sc = structural_context.strip()
        sc_lower = sc.lower()
        weak_schema = (
            not sc
            or len(sc) < 80
            or "tables:" in sc_lower and "none" in sc_lower
            or "joins:" in sc_lower and "none" in sc_lower
            or "columns:" in sc_lower and "none" in sc_lower
            or "no relevant schema nodes" in sc_lower
            or "insufficient graph connectivity" in sc_lower
            or "no usable tables" in sc_lower
        )

        if weak_schema and active_error_type != "connection_error":
            return {
                "generated_sql": None,
                "error": {
                    "sql_generation": "Insufficient schema context for safe SQL generation. Aborting SQL to avoid hallucinated tables/columns."
                },
                "retry_count": 3,
                "total_retry_count": state.get("total_retry_count", 0) + 1,
                "sql_repeat_count": 0
            }

    # --------------------------------------------------
    # 🔁 Retry Awareness (NO OVERLAP)
    # --------------------------------------------------

    retry_note = ""

    if state.get("retry_count", 0) > 0:
        retry_note = f"""
Retry Attempt: {state['retry_count']}

INSTRUCTIONS:
- Fix the issue identified above
- Do NOT repeat the same mistake
- Modify only what is necessary
"""

        # 🔥 Escalation mode (global awareness)
        if state.get("total_retry_count", 0) > 5:
            retry_note += """
ESCALATION:
- Simplify the query
- Reduce joins
- Prefer correctness over completeness
"""

    # --------------------------------------------------
    # 🧾 Final Prompt (CLEAN COMPOSITION)
    # --------------------------------------------------

    prompt = f"""
{final_context}

{error_context}

{retry_note}

Generate a single PostgreSQL SELECT query.
"""

    # --------------------------------------------------
    # 🚀 LLM CALL
    # --------------------------------------------------

    try:
        result = sql_structured_llm.invoke(prompt)

        query = getattr(result, "query", None)
        _ = getattr(result, "explanation", "")

        # ==================================================
        # 🔒 HARD VALIDATION (STRUCTURE)
        # ==================================================
        if not isinstance(query, str):
            raise ValueError(f"SQL query is not a string. Raw: {result}")

        query = query.strip()

        if not query:
            raise ValueError("Empty SQL query generated")

        # ==================================================
        # 🔒 SQL VALIDATION (BASIC)
        # ==================================================
        q_lower = query.lower()

        if not q_lower.startswith(("select", "with")):
            raise ValueError("Generated query is not SELECT or an WITH CTE METHOD")

        # prevent hallucinated text
        if "```" in query or "sql" in q_lower[:20]:
            raise ValueError("Query contains formatting artifacts")

        # prevent explanation leakage
        if "\n\n" in query and "select" not in query.split("\n")[0].lower():
            raise ValueError("Query contains extra text")

        # prevent policy/company context leakage into row-level name filters
        if _has_unjustified_name_filter(query, effective_question):
            raise ValueError("Name filter appears unjustified by user intent")

        # ==================================================
        # 🔒 LENGTH + COMPLEXITY CHECK
        # ==================================================
        if len(query) > 5000:
            raise ValueError("Query too long → likely hallucinated")

        # ==================================================
        # ✅ SUCCESS
        # ==================================================
        repeat_count = state.get("sql_repeat_count", 0)
        if previous_query and query.strip().lower() == previous_query.lower():
            repeat_count += 1
        else:
            repeat_count = 0

        # Hard stop to avoid regenerate/safety loops with unchanged SQL
        if repeat_count >= 2:
            return {
                "generated_sql": query,
                "error": {"sql_generation": "Repeated SQL regeneration detected with no meaningful change. Stopping retries."},
                "retry_count": 3,
                "total_retry_count": state.get("total_retry_count", 0) + 1,
                "sql_repeat_count": repeat_count
            }

        # Keep explanation aligned with executed SQL to prevent reasoning drift.
        explanation = _derive_sql_explanation(query)

        return {
            "generated_sql": query,
            "messages": [AIMessage(content=f"**SQL Query Explanation:**\n```\n{explanation}\n```")],
            "error": {"sql_generation": None},
            "retry_count": state.get("retry_count", 0),
            "sql_repeat_count": repeat_count
        }

    except Exception as e:
        print(f"[SQL GENERATOR ERROR]: {e}")

        return {
            "error": {"sql_generation": str(e)},
            "retry_count": state.get("retry_count", 0) + 1,
            "total_retry_count": state.get("total_retry_count", 0) + 1,
            "sql_repeat_count": state.get("sql_repeat_count", 0)
        }

def safety_check(state: AgentState):
    """
    Validates that the generated SQL is safe to execute.

    Rules:
    - Must be a single read-only query
    - Must not contain dangerous operations
    - Must be syntactically valid SQL (basic level)
    """

    print("--- NODE: safety_check ---")

    sql = state.get("generated_sql")

    # --------------------------------------------------
    # 1️⃣ Basic Validation
    # --------------------------------------------------
    if not isinstance(sql, str) or not sql.strip():
        return {
            "error": {"safety": "Empty or invalid SQL query."},
            "safety_passed": False,
            "retry_count": state.get("retry_count", 0) + 1,
            "total_retry_count": state.get("total_retry_count", 0) + 1
        }

    sql_clean = sql.strip().lower()

    # --------------------------------------------------
    # 2️⃣ Block Multiple Statements
    # --------------------------------------------------
    # Prevent: SELECT ...; DROP TABLE ...
    if ";" in sql_clean.strip(";"):
        return {
            "error": {"safety": "Multiple SQL statements are not allowed."},
            "safety_passed": False,
            "retry_count": state.get("retry_count", 0) + 1,
            "total_retry_count": state.get("total_retry_count", 0) + 1
        }

    # --------------------------------------------------
    # 3️⃣ Enforce Read-Only Queries
    # --------------------------------------------------
    allowed_starts = ("select", "with")

    if not sql_clean.startswith(allowed_starts):
        return {
            "error": {"safety": "Only SELECT queries are allowed."},
            "safety_passed": False,
            "retry_count": state.get("retry_count", 0) + 1,
            "total_retry_count": state.get("total_retry_count", 0) + 1
        }

    # --------------------------------------------------
    # 4️⃣ Block Dangerous Keywords
    # --------------------------------------------------
    forbidden_keywords = [
        "insert", "update", "delete", "drop",
        "alter", "truncate", "create", "grant", "revoke"
    ]

    if any(keyword in sql_clean for keyword in forbidden_keywords):
        return {
            "error": {"safety": f"Forbidden operation detected in SQL."},
            "safety_passed": False,
            "retry_count": state.get("retry_count", 0) + 1,
            "total_retry_count": state.get("total_retry_count", 0) + 1
        }

    # --------------------------------------------------
    # 5️⃣ SQL Parsing Check (Optional but Strong)
    # --------------------------------------------------
    try:
        parsed = sqlparse.parse(sql)

        if not parsed:
            return {
                "error": {"safety": "SQL parsing failed."},
                "safety_passed": False,
                "retry_count": state.get("retry_count", 0) + 1,
                "total_retry_count": state.get("total_retry_count", 0) + 1
            }

    except Exception as e:
        return {
            "error": {"safety": f"SQL parsing error: {str(e)}"},
            "safety_passed": False,
            "retry_count": state.get("retry_count", 0) + 1,
            "total_retry_count": state.get("total_retry_count", 0) + 1
        }

    # --------------------------------------------------
    # ✅ SUCCESS: Clear Previous Errors
    # --------------------------------------------------
    return {
        "safety_passed": True,
        "error": {"safety": None}, # 🔥  This is actuallly not being used so you can remove it maybe later
        "retry_count": 0
    }


def sql_executor(state: AgentState):
    """Executes the SQL query against the database."""
    print("--- NODE: sql_executor ---")
    sql = state.get("generated_sql")
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # cur.execute("SET statement_timeout = 10000;") -> this can be used as timeouts but honeslty not now
            cur.execute(sql)
            return {"sql_result": cur.fetchall()[:500], # List[Dict[str, Any]]
                    "error": {"sql_execution": None},
                    "retry_count": 0,
                    "sql_repeat_count": 0} # important notes, the error pertaining to that node should only be cleared only when 
    except Exception as e:
        error_msg = str(e)

        # -------------------------------
        # CONNECTION ERRORS
        # -------------------------------
        if isinstance(e, psycopg2.OperationalError):
            global _conn
            _conn = None
            error_type = "connection_error"

        # -------------------------------
        # TIMEOUT ERRORS
        # -------------------------------
        elif "statement timeout" in error_msg.lower():
            error_type = "timeout_error"

        # -------------------------------
        # SQL EXECUTION ERRORS
        # -------------------------------
        else:
            error_type = classify_sql_error(error_msg)

        return {
            "error": {
                "sql_execution": {
                    "type": error_type,
                    "message": error_msg,
                    "failed_query": state.get("generated_sql")
                }
            },
            "retry_count": state.get("retry_count", 0) + 1,
            "total_retry_count": state.get("total_retry_count", 0) + 1
        }
    finally:
        if conn: conn.close() # finally always runs no matter what happens, even though return works.

def synthesizer(state: AgentState):
    """Synthesizes the final natural language answer."""
    print("--- NODE: synthesizer ---")

    question = state.get("rewritten_question") or state.get("question")
    sql_result = state.get("sql_result")
    hybrid_context = state.get("hybrid_context")
    error = state.get("error", {}) # normally will give None if you do not give it anything now that you are giving it that you can give it a emtpy dictionary if you are not interrested in the output of it, it will not return None.
    sql_generated = state.get("generated_sql")

    # --------------------------------------------------
    # 🧠 Result Formatting
    # --------------------------------------------------

    result_block = "No data returned."

    if isinstance(sql_result, list):
        if len(sql_result) == 0:
            result_block = "Query executed successfully but returned no results."
        else:
            # Show only first few rows for readability
            preview = sql_result[:5]
            result_block = f"Sample Results:\n{json.dumps(preview, indent=2, default=str)}" # default=str handles datetime/decimal values from DB rows.
    elif isinstance(sql_result, str):
        result_block = sql_result

    # --------------------------------------------------
    # ⚠️ Error Awareness
    # --------------------------------------------------

    error_block = ""

    if (sql_result is None or (isinstance(sql_result, list) and len(sql_result) == 0)) or error:

        if error.get("sql_execution"):
           exec_err = error.get("sql_execution")

           if exec_err:
                error_block += f"""
            [EXECUTION ERROR]
            Type: {exec_err.get("type")}
            Message: {exec_err.get("message")}
            Failed Query: {exec_err.get("failed_query")}
            """
        if error.get("safety"):
            error_block += f"""
            [SAFETY ERROR]
            {error["safety"]}
            """
        if error.get("sql_generation"):
            error_block += f"""
            [SQL GENERATION ERROR]
            {error["sql_generation"]}
            """


    # --------------------------------------------------
    # 📚 Business Context Formatting
    # --------------------------------------------------

    business_block = ""

    if hybrid_context:
        top_chunks = hybrid_context[:5]
        business_block = "\n\n".join(top_chunks)

    # --------------------------------------------------
    # 🕒 Time Boundary Reasoning Hints
    # --------------------------------------------------
    question_lower = (question or "").lower()
    timezone_reasoning_block = ""
    if any(k in question_lower for k in ["utc", "est", "timezone", "midnight", "month-end", "month end"]):
        timezone_reasoning_block = """
TIME-BOUNDARY REASONING RULES:
- NexusFlow finance policy uses EST (UTC-5) for reporting boundaries.
- Convert UTC -> EST with: EST = UTC - 5 hours.
- When classifying month-end records, use the EST calendar day/month boundary (not UTC).
- Include one concrete conversion example when relevant.
  Example: 2026-04-01 02:00 UTC = 2026-03-31 21:00 EST (counts toward March in EST reporting).
- If the question is policy/interpretation-only and SQL data is not required, answer directly from policy context without inventing SQL analysis.
"""

    # --------------------------------------------------
    # 🎯 Final Prompt
    # --------------------------------------------------

    prompt = f"""
You are a senior RevOps Analyst.

Your job is to answer the user's question using:
- SQL query results (PRIMARY source of truth)
- Business context (if relevant)

-----------------------
USER QUESTION:
{question}

-----------------------
SQL QUERY GENERATED:
{sql_generated if sql_generated else "None"}


-----------------------
SQL RESULT:
{result_block if result_block else "None"}

-----------------------
BUSINESS CONTEXT:
{business_block if business_block else "None"}

-----------------------
ERRORS (if any):
{error_block if error_block else "None"}

-----------------------
SPECIAL REASONING:
{timezone_reasoning_block if timezone_reasoning_block else "None"}

-----------------------
INSTRUCTIONS:

- If SQL RESULT contains data:
  → Answer using the data clearly and directly

- If result is a single value:
  → Return the value with a brief explanation

- If result is a table:
  → Summarize key insights (do NOT dump all rows)

- If result is empty:
  → Clearly say no data found and suggest possible reasons

- If errors occurred:
  → Explain the issue simply and clearly
  → Do NOT expose raw SQL error traces

- SQL visibility rules:
  → Always include the SQL query if execution was successful or returned data
  → If execution failed, you may omit or simplify the query if it is not helpful

- Be concise, professional, and business-friendly

- If results are partial, sampled, or limited in scope:
  → Explicitly mention it briefly

-----------------------
OUTPUT FORMAT (STRICT):

Answer:
<final business answer>

Summary:
<short explanation of what was done>

SQL Query:
<query used OR "Not shown due to error">

Result Status:
<success | empty | error | partial>

Error (if any):
<short explanation OR "None">

Data Notes:
<assumptions, limitations, partial data, or "None">

Key Entities:
<important filters, entities, metrics used>

-----------------------

STRICT RULE for OUTPUT:
- All sections MUST be present
- If empty → write "None"
"""

    try:
        response = llm_reasoner.invoke(prompt)

        clean_answer = extract_clean_answer(response.content)

        return {
            "messages": [AIMessage(content=response.content)],
            "final_answer_clean": clean_answer,
            "error": {"synthesis": None}
        }

    except Exception as e:
        return {
            "error": {
                "synthesis": f"Final answer synthesis failed: {e}"
            }
        }

# --- 4. Graph Definition & Routers ---

#🌶️🌶️🌶️🌶️🌶️🌶️🌶️ -> Please check how the retry count is happening, is it for like each query or an incremental bonanza? Also like they said something like this about the retries. 👉 make retries smarter:

# if execution_error.type == "column_error" → fix columns
# if type == "join_error" → fix joins
# if type == "type_error" → add casting

# That’s how real copilots behave. If you want next, we can:
# 👉 upgrade your retry loop into error-aware self-healing SQL generation (this is 🔥)

def route_after_intent(state: AgentState):
    intent = state.get("intent", "ambiguous")
    return "ambiguous_responder" if intent == "ambiguous" else "query_transformer"

def route_to_retrievers(state: AgentState): # these are called router functions and down is the routing happening. They do control the flow.
    intent = state.get("intent")

    if intent == "chat":
        return "hybrid_retriever"

    elif intent == "sql":
        return "graph_explorer"

    elif intent == "hybrid":
        return ["hybrid_retriever", "graph_explorer"] # both nodes will be executed. Then the merging of the states wil happen, given that they are not overwriting the values of each other in the state.

    else:
        return "ambiguous_responder" # you cannot keep simply END here cause the user has to see something. This atleast informs that the user question is not appropriate. 8. When SHOULD you use END?

# Only when:

# You already have a final response in state
# OR you're exiting after a responder node

# Example:
# intent_classifier
#    ↓
# router
#    ↓
# some node ALWAYS
#    ↓
# response node
#    ↓
# END

def route_after_retrieval(state: AgentState):
    intent = state.get("intent")

    knowledge_context = state.get("hybrid_context")
    schema_context = state.get("structural_context")

    #🔥 FIX: handle synchronize failure explicitly
    sync_error = state.get("error", {}).get("sync")

    if sync_error and intent != "sql":
        if "missing structural" in sync_error.lower():
            return "not_found_responder"
    
    if intent == "chat":
        return "synthesizer" if knowledge_context else "not_found_responder"

    if intent == "sql":
        graph_error = state.get("error", {}).get("graph")

        # 🔥 FIX: only block on HARD failures -> we only stop on fatal failures not on all failures of the graph.
        if graph_error:
            msg = str(graph_error).lower()

            if any(x in msg for x in [
                "not loaded",
                "invalid or empty question"
            ]):
                return "not_found_responder"

        # Let SQL continue; context_builder can use schema_summary fallback when graph context is sparse.
        return "context_builder"

    if intent == "hybrid":
        return "context_builder" if (knowledge_context or schema_context) else "not_found_responder" # this is strict, cause for hybrid we are keeping it like this, we are not keeping it strict. We are also aiming for partial success as of now. 🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴 If both the contexts are weak this might lead to hallucination and pollution in the context builder, so you need to have some sort of QC check.
    return "not_found_responder"

def route_after_generation(state: AgentState):
    if state.get("error", {}).get("sql_generation"):
        if state.get("retry_count", 0) < 3 and state.get("total_retry_count", 0) < 8:
            return "sql_generator"
        return "synthesizer"
    return "safety_check"

def route_after_safety(state: AgentState):
    if state.get("error", {}).get("safety"):
        if state.get("retry_count", 0) < 3 and state.get("total_retry_count", 0) < 8:
            return "sql_generator"
        return "synthesizer"
    return "sql_executor"

def route_after_execution(state: AgentState):
    if state.get("error", {}).get("sql_execution"): # see here there are two conditions, there should be an error in the sql_execution and also the retry count should be less than 3.
        err_type = state["error"]["sql_execution"].get("type")
        if err_type == "connection_error":
            if state.get("retry_count", 0) < 3 and state.get("total_retry_count", 0) < 8: # if retry not incremented properly then will in a endless look.
                return "sql_executor"  # retry same query

        elif state.get("retry_count", 0) < 3 and state.get("total_retry_count", 0) < 8:
            return "sql_generator"  # fix query
    return "synthesizer"

# StateGraph is a graph builder for workflows, usually from libraries like LangGraph (used with LLM agents). A directed graph where each node = a function, and data flows through a shared state object. When you write -> workflow = StateGraph(AgentState), “Every node in this graph will receive and return a shared state”. That state follows the structure of AgentState. state → node → updated state → next node → ... They can be called directly (they're normal functions)
# But in this design → the graph calls them, not you

def create_graph():
    """Assembles the agent's graph."""
    workflow = StateGraph(AgentState)
    
    nodes = ["intent_classifier", "query_transformer", "ambiguous_responder", "not_found_responder", 
             "hybrid_retriever", "graph_explorer", "synchronize", "context_builder", 
             "sql_generator", "safety_check", "sql_executor", "synthesizer"]
    for node in nodes:
        workflow.add_node(node, globals()[node]) # The globals part means this, “Take the function whose name is stored in node (string), and pass the actual function object.” node = "intent_classifier"
# globals()[node] → function intent_classifier. workflow.add_node("intent_classifier", intent_classifier) -> you can refer to the agent.py if you want to see this structure being followed.

    workflow.set_entry_point("intent_classifier")

    # 🔴🔴🔴🔴🔴🔴🔴🔴🔴 --> I am seeing a issue over here, like suppose here the entry point is intent classifier which is working fine, it is filtering out the ambigious nodes and one more thing is that maybe the query_transformer node should run first right so that entire context is given to check the intent, let us do multiple testing to check how it will work.
    
    workflow.add_conditional_edges("intent_classifier", route_after_intent) # used when using helper function to decide which edge to take.
    workflow.add_edge("ambiguous_responder", END) # every node before END should provide a user facing message.
    
    workflow.add_conditional_edges("query_transformer", route_to_retrievers)

    workflow.add_edge("hybrid_retriever", "synchronize")
    workflow.add_edge("graph_explorer", "synchronize")
    workflow.add_conditional_edges("synchronize", route_after_retrieval)
    workflow.add_edge("not_found_responder", END)

    workflow.add_edge("context_builder", "sql_generator")
    workflow.add_conditional_edges("sql_generator", route_after_generation)
    workflow.add_conditional_edges("safety_check", route_after_safety)
    workflow.add_conditional_edges("sql_executor", route_after_execution)
    
    workflow.add_edge("synthesizer", END)
    
    return workflow.compile()

app = create_graph()

# --- 5. Main Execution Block ---

# 👉 Each app.stream() call starts with ONLY what you pass in initial_state.The old value does NOT persist. It is completely gone. Overwritten only happens in the same run. If you did not do the state reset, then if you had 
# "generated_sql" value in the previous state and in the new intial state you do not supply it with this.
# state.get("generated_sql") → None, so always use get it is better.
# state["generated_sql"] → KeyError
# ❗ Crucially:

# 👉 It will NOT be: "SELECT * FROM invoices" ❌, a value from the previous runs

# Run 1 → State A (lives only inside stream)
# END → State A is destroyed

# Run 2 → State B (brand new), Until you are manually saving the previous state and then using it again as the initial state.

# ✅ Always:
# Define all keys in AgentState
# Initialize them in initial_state

@traceable
def run_agent(query: str):
    """CLI entry point for a single question."""
    print(f"\n>>> USER QUESTION: {query}")
    # STATE GHOSTING PROTECTION: Initialize all variables to None to prevent leakage from old turns
    initial_state = {
        "question": query, "messages": [HumanMessage(content=query)], "retry_count": 0, "safety_passed": False, 
        "error": {}, "rewritten_question": None, "hybrid_context": None, 
        "structural_context": None, "style_guide_context": None, "generated_sql": None, "sql_result": None, "final_context":None, "final_answer_clean": None, "total_retry_count": 0, "sql_repeat_count": 0
    }
    final_state = None
 # Stream node-by-node updates to the terminal for a "Live" heartbeat fee
 # Output is ALWAYS: -> {
#   "node_name": {state_updates}
# }
# {
#   "intent_classifier": {"intent": "hybrid"}
# }
# {
#   "synthesizer": {
#       "messages": [AIMessage(...)]
#       "erors":
#   }
# }



    for output in app.stream(initial_state, {"recursion_limit": 25}): # Maximum number of node executions allowed. Like since this is only a one time thing. ALong with retry count this is another safegarud limit that we can keep. This will also be reset for each and every stream.
        if not output: continue # This is like the node output that it has currently executed, so if it give None keep in conitinuing do not stop.
        for key, value in output.items():
            print(f"--- Ran Node: {key} | Keys: {list(value.keys()) if value else None} ---") # print statements are great for debugging.
            final_state = value 

            if value and "messages" in value:
                print(f"[{key}]: {value['messages'][-1].content}") # final_state will only have the output of the last node cause we are overwriting it.  We will be losing sql, context and a lot. So if you want to can include them.
                           
    if final_state and final_state.get("messages"):
        return final_state["messages"][-1].content
    elif final_state and any(v for v in final_state.get("error", {}).values()):
        return f"When compiling the knowledge we ran into this Error: {final_state['error']}"
    else:
        return "Sorry, something went wrong, contact the development team."


@traceable
def chat_loop():
    print("💬 Entering Advanced RAG Chat Mode...")
    messages = []

    while True:
        query = input("\n👤 YOU: ")
        if query.lower() in ["exit", "quit"]:
            break

        initial_state = {
            "question": query,
            "messages": messages + [HumanMessage(content=query)], # here the message is not being appended it is simpley being sent.
            "retry_count": 0,
            "safety_passed": False,
            "error": {},
            "rewritten_question": None,
            "hybrid_context": None,
            "structural_context": None,
            "style_guide_context": None,
            "generated_sql": None,
            "sql_result": None,
            "final_context": None,
            "final_answer_clean": None,
            "total_retry_count": 0,
            "sql_repeat_count": 0
        }

        final_state = None

        for output in app.stream(initial_state, {"recursion_limit": 25}): #This is a hard lock if you do not want to depend on the retry count only.
            if not output:
                continue

            for key, value in output.items():
                print(f"--- Ran Node: {key} | Keys: {list(value.keys()) if value else None} ---") 

                if value:
                    final_state = value

                if value and "messages" in value:
                    print(f"[{key}]: {value['messages'][-1].content}")

        messages.append(HumanMessage(content=query)) # do not think of appening the rewritten query over here.❌ Problems
        # You lose original user intent
        # rewriting is lossy
        # may inject bias

        # Compounds errors over turns
        # rewrite → rewrite → rewrite → drift
        
        # LLM starts talking to itself
        # conversation becomes synthetic

        if final_state and final_state.get("messages"):
            agent_response = final_state["messages"][-1]
            clean_answer = final_state.get("final_answer_clean")

            if clean_answer:
                messages.append(AIMessage(content=clean_answer))
            else:
                messages.append(agent_response)
            print(f"🤖 ASSISTANT: {agent_response.content}")

        elif final_state and any(v for v in final_state.get("error", {}).values()):
            error_msg = f"⚠️ Error: {final_state['error']}"
            messages.append(AIMessage(content=error_msg))
            print(error_msg)

        else:
            fallback = "Sorry, something went wrong."
            messages.append(AIMessage(content=fallback))
            print(fallback)

if __name__ == "__main__":
    import sys

    command = sys.argv[1].lower() if len(sys.argv) > 1 else "chat"

    if command == "chat":
        chat_loop()

    elif command == "ask":
        query = " ".join(sys.argv[2:])
        if not query:
            print("⚠️ Please provide a query after 'ask'")
        else:
            print(run_agent(query))

    elif command == "demo":
        query = (
            "What is the total revenue from organizations in the 'Technology' industry, "
            "and what is our company policy on 'Ghost Contracts'?"
        )
        print("🚀 Running demo query...\n")
        print(run_agent(query))

    elif command == "help":
        print("""
🧠 Advanced SQL RAG Copilot

Usage:
  python advanced_agent.py                # Start chat mode
  python advanced_agent.py chat           # Start chat mode
  python advanced_agent.py ask <query>    # Ask a single query
  python advanced_agent.py demo           # Run demo example
  python advanced_agent.py help           # Show this help message

Examples:
  python advanced_agent.py ask "What is total revenue?"
  python advanced_agent.py demo
""")

    else:
        # Fallback: treat everything as a query
        query = " ".join(sys.argv[1:])
        print(run_agent(query))
    


#The sys (System) module is a built-in Python tool that lets the script talk to the Operating System. ng System. Usage: We use it specifically to read Command Line Arguments (the words you type after the filename).


# sys.argv (The Argument List)
#   When you run a command, Python puts every word
#   into a list called sys.argv:
#    * python agent.py -> sys.argv is ['agent.py']
#      (Length 1)
#    * python agent.py chat -> sys.argv is
#      ['agent.py', 'chat'] (Length 2)
#    * python agent.py "What is revenue?" -> sys.argv
#      is ['agent.py', 'What is revenue?'] (Length 2)

#   4. The Logic Flow (Lines 378–381)


#    1 if len(sys.argv) > 1:
#    * Meaning: "Did the user type anything extra
#      after python agent.py?"


#    1 if sys.argv[1].lower() == "chat": 
#    2     chat_loop()
#    * Meaning: If the first word after the filename
#      is "chat", start the interactive loop where you
#      can talk back and forth.


#    1 else: 
#    2     run_agent(" ".join(sys.argv[1:]))
#    * Meaning: If the user typed a question directly
#      (e.g., python agent.py How much is revenue?),
#      take all those words, join them into one string
#      (the join part), and run the agent exactly
#      once, then exit.


#    1 else: 
#    2     chat_loop()
#    * Meaning: If the user typed nothing but the
#      filename (python agent.py), default to starting
#      the interactive Chat Mode.
