# SQL Knowledge RAG Copilot - Master Documentation

## Project Overview

An advanced interactive AI assistant designed to navigate complex, "hostile" SQL databases using LangGraph, Graph-RAG, and Hybrid Search. Built with Python 3.11, PostgreSQL 15, LanceDB, and NetworkX. It specifically targets real-world data messiness like missing constraints, type mismatches, unstructured JSONB data, and complex multi-hop database joins.

## Connection Details

*   **Credentials:** All database credentials and API keys are stored in the `.env` file.
*   **Required Variables:**
    *   `PG_HOST`: Database host (e.g., `127.0.0.1`)
    *   `PG_PORT`: Database port (e.g., `5432`)
    *   `PG_DATABASE`: Database name (e.g., `nexusflow_revops`)
    *   `PG_USER`: Database user
    *   `PG_PASSWORD`: Database password
    *   `GROQ_API_KEY`: Groq API Key for high-speed LLM inference (Required)
    *   `GROQ_ROUTER_MODEL`: e.g., `llama-3.1-8b-instant`
    *   `GROQ_REASONER_MODEL`: e.g., `llama-3.3-70b-versatile`

## Database Schema (The "Hostile" Layers)

1.  **organizations:** Basic company info.
2.  **accounts:** Linked to organizations.
3.  **contracts:** Linked to accounts.
4.  **invoices:** Monthly billing data (Monthly Grain).
5.  **payments:** **Trap:** `contract_ref_id` (string) vs `contract_id` (int). Requires explicit casting in SQL.
6.  **usage_ledger:** Daily product usage (Daily Grain).
7.  **status_mapping:** Lookup for integer status codes (e.g., 0=Failed).
8.  **legacy_billing_logs:** **Trap:** No foreign keys; string-based matching only.
9.  **product_metrics_metadata:** Metric definitions and billable status.
10. **sales_reps:** Sales personnel records.
11. **rep_performance_targets:** Quarterly revenue goals.
12. **audit_logs_unstructured:** **Trap:** Data stored in `JSONB` columns. Requires `->>` syntax for extraction.

## Core Scripts & Structure

*   `setup_init_db.py`: Rebuilds schema using `init_db.sql` (with `CASCADE` drops to ensure clean resets).
*   `generate_data.py`: Populates tables with messy `Faker` data to simulate real-world noise.
*   `advanced_ingest.py`: Builds the parent-child Hierarchical Vector DB for knowledge documents (LanceDB).
*   `build_graph.py` & `build_graph_index.py`: Generates the NetworkX schema graph (`nexusflow_knowledge_graph.gml`) and its corresponding LanceDB search index.
*   `advanced_agent.py`: The main LangGraph agent runtime utilizing **Model Cascading**, **Graph RAG**, and an interactive Chat Loop.
*   `knowledge_base/`:
    *   `schema_cards/`: Individual Markdown files per table.
    *   `schema_summary.md`: A single-file fallback "Global Schema Truth".
    *   `parent_docs.json`: Extracted parent doc references for hierarchical RAG.

---

## Agent Architecture: Production-Grade "Agentic" Approach

The system leverages **LangGraph** for a cyclic, state-aware agent with powerful error-correction and memory.

### 1. The Brain: `AgentState`
A single `TypedDict` state shared across the graph:
*   `question` & `rewritten_question`: Context-aware query tracking.
*   `intent`: Routing decision (`chat`, `sql`, `hybrid`, `ambiguous`).
*   `hybrid_context`: Semantic business rules retrieved from docs.
*   `structural_context`: Graph-RAG derived schema paths, tables, and columns.
*   `error`: **Namespaced Error Reducer** using `merge_errors`.
*   `messages`: Conversation history.
*   `retry_count`, `total_retry_count`, `sql_repeat_count`: Safety budgets to prevent infinite loops.

### 2. Model Cascade & Inference
Uses Groq for split-brain efficiency:
*   **Router (`llama-3.1-8b-instant`)**: Fast and cheap. Used for Intent Classification and Query Rewriting.
*   **Reasoner (`llama-3.3-70b-versatile`)**: High-reasoning model. Handles SQL Generation and Final Synthesis.
*   **Embeddings & Reranking**: Local `BAAI/bge-base-en-v1.5` embeddings and `cross-encoder/ms-marco-MiniLM-L-6-v2` reranker for precision recall.

### 3. Dual-Retrieval System

**A. Semantic Hybrid Retrieval (`hybrid_retriever`)**
*   Executes Vector + FTS search on business documents.
*   Uses Cross-Encoder reranking.
*   Implements Parent-Child chunk aggregation to deliver complete contextual sections.

**B. Graph-RAG Structural Retrieval (`graph_explorer`)**
*   **Hybrid Node Retrieval**: Finds relevant schema nodes (Tables/Columns) using the LanceDB graph index.
*   **Steiner Tree Approximation**: Uses NetworkX to find the shortest reliable JOIN paths between disconnected tables.
*   **Centrality Scoring**: Ranks tables based on graph importance and proximity to query nodes.
*   **Token-Aware Assembly**: Strictly limits the extracted schema context to fit within LLM token budgets.

### 4. The Nodes (Workflow)
*   `intent_classifier`: Routes query to chat, sql, or hybrid processing.
*   `query_transformer`: Rewrites follow-up questions to be self-contained using chat history.
*   `hybrid_retriever`: Fetches business context.
*   `graph_explorer`: Navigates schema graph to extract tables and JOIN paths.
*   `synchronize`: Wait-state node to merge parallel retrieval branches.
*   `context_builder`: Assembles prompt combining schema, business rules, and SQL guidelines.
*   `sql_generator`: Generates robust Postgres SQL using context.
*   `safety_check`: Validates read-only status and catches syntax risks.
*   `sql_executor`: Executes queries against Postgres with safe time-outs and row limits.
*   `synthesizer`: Combines database results and context into a polished business answer.

---

## Hardening & Data Integrity

1.  **State Initialization:** Prevents "State Ghosting" across conversational turns.
2.  **Namespaced Error Reducers:** `merge_errors` ensures failures in retrieval don't erase failures in execution.
3.  **Self-Healing SQL Generation:** Failed executions feed specific Postgres error messages (e.g., `column_error`, `join_error`, `type_error`) back to the Reasoner for targeted corrections.
4.  **Loop Prevention:** Tracks local retries, total retries, and repetitive SQL generation to safely abort dead-ends.

## Getting Started

1.  **Start Database:**
    ```bash
    docker run --name nexus_db -e POSTGRES_USER=nexus_admin_aditya -e POSTGRES_PASSWORD=nexus_pass_aditya123 -e POSTGRES_DB=nexusflow_revops -v ./postgres_data:/var/lib/postgresql/data -p 5432:5432 -d postgres:15
    ```

2.  **Environment Setup:** Create a `.env` file with DB credentials and your `GROQ_API_KEY`.

3.  **Interactive Chat:**
    Run the conversational agent loop:
    ```bash
    python advanced_agent.py chat
    ```

4.  **Single Query Mode:**
    ```bash
    python advanced_agent.py ask "What is Stacy Kelly's commission if revenue is $50k?"
    ```
