# SQL Knowledge RAG Copilot

This project is a SQL + RAG copilot for a fictional RevOps company called NexusFlow. It lets a user ask natural-language business questions and routes them through a LangGraph-based agent that can:

- answer document-only questions from a knowledge base,
- generate and execute PostgreSQL queries for data questions,
- combine database results with business-policy context for hybrid questions.

The repository is built around a "hostile schema" idea: the database includes messy joins, JSON fields, string-based foreign keys, and business rules that are not fully captured in the SQL schema. The goal is to show how retrieval, graph reasoning, and SQL generation can work together in a more realistic analytics assistant.

## What This Project Does

At a high level, the system combines three layers:

1. A Streamlit chat app in `app.py` for the user interface.
2. A LangGraph workflow in `advanced_agent.py` that classifies intent, retrieves context, generates SQL, validates it, runs it, and synthesizes an answer.
3. Preparation scripts that build the database, ingest markdown knowledge into LanceDB, and create a knowledge graph plus a graph index for schema-aware retrieval.

## Main Files

### `app.py`

This is the main Streamlit application.

- Provides a password-protected chat interface.
- Stores UI chat history and a cleaner internal agent history separately.
- Sends each user prompt into the LangGraph app exposed from `advanced_agent.py`.
- Streams node-by-node progress updates into the UI so the user can see which stage is running.
- Displays the final answer and keeps the cleaned response for future conversational context.

Use this file when you want to run the full web app:

```bash
streamlit run app.py
```

### `advanced_agent.py`

This is the core of the project. It defines the LangGraph workflow and the retrieval/SQL logic.

Main responsibilities:

- Loads the environment variables and external resources:
  - PostgreSQL connection settings,
  - LanceDB knowledge base,
  - graph index,
  - NetworkX knowledge graph,
  - parent document store.
- Initializes the models and embedding components:
  - Groq LLMs for routing and reasoning,
  - HuggingFace embeddings,
  - cross-encoder reranker.
- Defines the shared `AgentState` for the graph workflow.
- Routes each question into one of four intents:
  - `chat`
  - `sql`
  - `hybrid`
  - `ambiguous`
- Performs:
  - query rewriting for conversational follow-ups,
  - hybrid document retrieval from LanceDB,
  - graph-based schema exploration from the knowledge graph,
  - prompt/context building for SQL generation,
  - SQL generation with safety rules,
  - SQL validation and execution,
  - final answer synthesis.

It also supports CLI usage:

```bash
python advanced_agent.py chat
python advanced_agent.py ask "What does Optum Standard mean at NexusFlow?"
python advanced_agent.py demo
python advanced_agent.py help
```

### `advanced_ingest.py`

Builds the document retrieval layer.

- Reads the markdown knowledge base files.
- Splits them into hierarchical parent/child chunks.
- Stores child chunks in LanceDB.
- Creates a full-text search index for hybrid retrieval.
- Saves the parent chunk store into `knowledge_base/parent_docs.json`.

Run this after the knowledge base exists and before the agent is expected to answer document-driven questions:

```bash
python advanced_ingest.py
```

### `build_graph.py`

Builds the schema knowledge graph from the documentation.

- Reads `knowledge_base/schema_summary.md` and the markdown files in `knowledge_base/schema_cards/`.
- Uses an LLM with structured output to extract tables, columns, and joins.
- Saves raw extracted graph data to `extracted_graph.json`.
- Saves the final NetworkX graph to `nexusflow_knowledge_graph.gml`.

This graph is later used by the agent to reason about table structure and join paths.

### `build_graph_index.py`

Builds a searchable index for graph nodes.

- Loads `nexusflow_knowledge_graph.gml`.
- Converts graph nodes into graph-aware searchable text.
- Embeds them and stores them in LanceDB under `graph_index_data/`.
- Creates a full-text search index for hybrid graph retrieval.

This is what lets the agent retrieve schema-relevant nodes from a user question.

### `setup_init_db.py`

Creates the PostgreSQL schema defined in `init_db.sql`.

- Connects to PostgreSQL using environment variables.
- Executes the schema creation script.
- Prints the created tables for verification.

Use this before generating data.

### `generate_data.py`

Populates the database with synthetic but intentionally tricky data.

- Inserts data across the CRM, billing, usage, lookup, sales, legacy, and audit domains.
- Introduces noisy or "trap" conditions such as:
  - `payments.contract_ref_id` stored as dirty text,
  - legacy contract codes,
  - JSONB audit metadata,
  - test accounts,
  - mixed status codes.

This file is important because many of the project’s SQL and hybrid behaviors depend on these edge cases existing.

### `db_test.py`

A minimal connectivity check for PostgreSQL.

- Tries to connect using the configured environment variables.
- Runs `SELECT version();`
- Prints whether the connection succeeded.

Use this first if database access is failing.

### `inspect_db.py`

A debugging utility for inspecting the live database.

- Lists all public tables.
- Prints each table’s columns and types.
- Prints a few sample rows from each table.

Useful when validating the generated schema and sample data.

## Other Important Files

### `requirements.txt`

Lists the Python dependencies for the project, including:

- Streamlit
- LangChain / LangGraph
- Groq integrations
- HuggingFace embeddings
- LanceDB
- NetworkX
- psycopg2
- sentence-transformers

### `init_db.sql`

Defines the database schema. The schema is intentionally designed to contain realistic analytics pain points, such as:

- string-to-int join traps,
- status-code lookups,
- JSONB metadata,
- tables at different grains,
- legacy billing artifacts.

### `questions.md` and `questions_testing.md`

Contain example prompts for evaluating the agent.

- `questions.md` focuses on structured test cases.
- `questions_testing.md` includes practical prompts for chat, SQL, hybrid, and follow-up testing.

### `GEMINI.md`

Supplementary project notes and experimentation context.

### `assets/`

Contains the images used by the project and repo:

- `chat_assistant.png`
- `graph_visualization_enhanced.png`

### Generated / Stored Data Directories

- `lancedb_data/`: vector and hybrid-search index for the markdown knowledge base.
- `graph_index_data/`: vector and hybrid-search index for knowledge graph nodes.
- `knowledge_base/`: markdown documents and schema cards used for RAG.
- `nexusflow_knowledge_graph.gml`: saved schema graph.
- `extracted_graph.json`: raw graph extraction output.

## Project Flow

This is the typical lifecycle of the project:

1. Create the PostgreSQL schema from `init_db.sql`.
2. Generate synthetic NexusFlow data.
3. Ingest markdown business knowledge into LanceDB.
4. Build the schema graph from documentation.
5. Build the graph node index.
6. Start the Streamlit app or use the CLI agent.

Recommended command order:

```bash
python db_test.py
python setup_init_db.py
python generate_data.py
python advanced_ingest.py
python build_graph.py
python build_graph_index.py
streamlit run app.py
```

## Agent Workflow

The workflow in `advanced_agent.py` is the main technical idea in this repository.

For each question, the agent:

1. Classifies the intent.
2. Rewrites the question if it depends on chat history.
3. Retrieves context:
   - document context from LanceDB,
   - schema/join context from the knowledge graph.
4. Builds a final SQL-generation prompt with schema rules and business context.
5. Generates SQL only for `sql` or `hybrid` questions.
6. Validates that the SQL is safe and read-only.
7. Executes the SQL in PostgreSQL.
8. Synthesizes a final user-facing answer.

Important design ideas in this project:

- Hybrid retrieval: combines vector search and full-text search.
- Hierarchical RAG: retrieves small chunks, then expands to parent context.
- Graph-aware retrieval: uses schema nodes and join paths to guide SQL generation.
- Retry loop: attempts to repair SQL after execution or safety failures.
- Guardrails: blocks non-SELECT SQL and suspicious query patterns.

## Knowledge Base

The `knowledge_base/` folder provides the non-SQL business logic the agent needs.

Examples of what lives there:

- company terminology such as "Optum Standard"
- policy rules such as timezone and fiscal-year handling
- compensation plans
- schema summaries and schema cards
- SQL style guidance
- external target and quota definitions

This is what allows the project to answer business questions that the database alone cannot answer.

## Environment Setup

Create a `.env` file with the values required by the app and agent. Based on the code, the main variables are:

```env
PG_HOST=
PG_PORT=
PG_DATABASE=
PG_USER=
PG_PASSWORD=

STREAMLIT_PASSWORD=

GROQ_API_KEY=
GROQ_ROUTER_MODEL=llama-3.1-8b-instant
GROQ_REASONER_MODEL=llama-3.3-70b-versatile

LANGCHAIN_API_KEY=
LANGCHAIN_TRACING_V2=
LANGCHAIN_PROJECT=

CEREBRAS_API_KEY=
```

Notes:

- PostgreSQL connections are configured with `sslmode=require`.
- `build_graph.py` expects a valid `CEREBRAS_API_KEY`.
- `advanced_agent.py` expects the Groq models and API key to be available.
- LangSmith tracing is optional but supported by the code.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running the Project

### Streamlit UI

```bash
streamlit run app.py
```

### CLI Chat Mode

```bash
python advanced_agent.py chat
```

### Single Question from CLI

```bash
python advanced_agent.py ask "Which accounts exceeded 5000 API calls in February 2026?"
```

## Example Questions

- "What does Optum Standard mean at NexusFlow?"
- "What is the total settled payment amount in 2026?"
- "Which accounts exceeded 5000 API calls in February 2026?"
- "For finance reporting at NexusFlow, explain the timezone policy and how it affects month-end interpretation."
- "What is Stacy Kelly's commission for Q1 2026?"

## Repo Structure

```text
sql_rag_app/
│
├── app.py
├── advanced_agent.py
├── advanced_ingest.py
├── build_graph.py
├── build_graph_index.py
├── db_test.py
├── generate_data.py
├── inspect_db.py
├── setup_init_db.py
├── requirements.txt
├── init_db.sql
├── extracted_graph.json
├── nexusflow_knowledge_graph.gml
├── questions.md
├── questions_testing.md
├── GEMINI.md
├── assets/
├── lancedb_data/
├── knowledge_base/
└── graph_index_data/
```

## Notes for Reviewers

If you are checking this repository on GitHub, the most important files to understand first are:

1. `app.py` for the user-facing interface,
2. `advanced_agent.py` for the full agent pipeline,
3. `advanced_ingest.py` for the RAG ingestion flow,
4. `build_graph.py` and `build_graph_index.py` for schema-aware retrieval,
5. `setup_init_db.py`, `generate_data.py`, and `init_db.sql` for the database foundation.

This project is not just a chatbot UI. It is an end-to-end prototype showing how to combine:

- natural-language querying,
- SQL generation,
- document retrieval,
- graph-based schema reasoning,
- and business-rule synthesis

in a single analytics copilot.
