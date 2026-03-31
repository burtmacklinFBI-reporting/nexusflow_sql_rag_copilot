
import os
import lancedb
import networkx as nx
from pydantic import BaseModel
from langchain_huggingface import HuggingFaceEmbeddings
import logging


# a lot of people are telling me that the embeddings are really weak, like now we have like this 

# searchable_text = f"Type: {node_type}, Name: {node_id}, Description: {description}"

# Problem:

# This misses:

# relationships

# join conditions

# importance of node

# searchable_text = f"""
# Node: {node_id}
# Type: {node_type}
# Description: {description}
# Connected To: {neighbors}
# Join Conditions: {join_edges}
# """

# Configure logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] - %(message)s')

# --- Configuration ---
GRAPH_FILE_PATH = "nexusflow_knowledge_graph.gml"
LANCEDB_INDEX_DIR = "./graph_index_data"
TABLE_NAME = "graph_node_index"
EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"

# --- Pydantic Schema for LanceDB Table ---
class NodeIndex(BaseModel):
    node_id: str
    text: str # Combination of node properties for searching
    vector: list[float]

def build_index():
    """
    Loads the knowledge graph, generates embeddings for node descriptions,
    and persists them into a dedicated LanceDB table for fast hybrid search.
    """
    if not os.path.exists(GRAPH_FILE_PATH):
        logging.error(f"Knowledge graph file not found at '{GRAPH_FILE_PATH}'. Please run build_graph.py first.")
        return

    logging.info("--- Starting Graph Node Indexing Process ---")

    # 1. Load Knowledge Graph
    try:
        G = nx.read_gml(GRAPH_FILE_PATH)
        logging.info(f"Successfully loaded knowledge graph with {G.number_of_nodes()} nodes.")
    except Exception as e:
        logging.error(f"Failed to load or parse graph file '{GRAPH_FILE_PATH}': {e}")
        return

    # 2. Initialize Models and DB
    try:
        embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
        db = lancedb.connect(LANCEDB_INDEX_DIR)
        logging.info("Initialized embedding model and LanceDB connection.")
    except Exception as e:
        logging.error(f"Failed to initialize models or DB: {e}")
        return

    # 3. Prepare Node Data
    node_data_list = []
    texts_to_embed = []
    for node_id, data in G.nodes(data=True):
        description = data.get('description', '')
        node_type = data.get('label', '') or ('Column' if '.' in node_id else 'Table')

        join_neighbors = []
        join_conditions = []
        try:
            for u, v, edge_data in G.edges(node_id, data=True):
                if edge_data.get("label") == "JOINS_WITH":
                    other = v if u == node_id else u
                    join_neighbors.append(str(other))
                    jc = edge_data.get("join_condition")
                    if jc:
                        join_conditions.append(str(jc))
        except Exception:
            pass

        join_neighbors_txt = ", ".join(sorted(set(join_neighbors))) if join_neighbors else "None"
        join_conditions_txt = " | ".join(sorted(set(join_conditions))[:3]) if join_conditions else "None"

        # Create a richer graph-aware text representation for retrieval.
        searchable_text = (
            f"Type: {node_type}. "
            f"Name: {node_id}. "
            f"Description: {description}. "
            f"Join Neighbors: {join_neighbors_txt}. "
            f"Join Conditions: {join_conditions_txt}."
        )
        
        node_data_list.append({"node_id": node_id, "text": searchable_text})
        texts_to_embed.append(searchable_text)

    if not node_data_list:
        logging.warning("Graph has no nodes to index. Exiting.")
        return
        
    logging.info(f"Prepared {len(node_data_list)} nodes for embedding.")

    # 4. Generate Embeddings in a Single Batch
    try:
        logging.info("Generating embeddings for all nodes... (This may take a moment)")
        vectors = embeddings.embed_documents(texts_to_embed)
        logging.info("Embedding generation complete.")
    except Exception as e:
        logging.error(f"Failed to generate embeddings: {e}")
        return

    # 5. Combine Data and Create Pydantic Objects
    final_data = []
    for i, node_data in enumerate(node_data_list):
        final_data.append(NodeIndex(
            node_id=node_data['node_id'],
            text=node_data['text'],
            vector=vectors[i]
        ))
    
    # 6. Create LanceDB Table and Add Data
    try:
        # Drop the table if it exists to ensure a clean slate
        if TABLE_NAME in db.table_names():
            db.drop_table(TABLE_NAME)
            logging.info(f"Dropped existing LanceDB table: '{TABLE_NAME}'")

        # Convert Pydantic objects to a list of dictionaries for LanceDB
        data_for_lancedb = [d.dict() for d in final_data]

        # Create the table by passing the list of dictionaries
        table = db.create_table(TABLE_NAME, data=data_for_lancedb, mode="create")
        logging.info(f"Successfully created and populated LanceDB table '{TABLE_NAME}' with {len(final_data)} records.")
    except Exception as e:
        logging.error(f"Failed to create or populate LanceDB table: {e}")
        return
        
    # 7. Create FTS Index for Hybrid Search
    try:
        table.create_fts_index("text")
        logging.info("Successfully created FTS index on 'text' field for hybrid search.")
    except Exception as e:
        logging.error(f"Failed to create FTS index: {e}")

    logging.info("--- Graph Node Indexing Process Complete ---")

if __name__ == "__main__":
    build_index()


#  1. Why logging instead of print()?


#   While print() is great for simple and quick outputs, the logging module is a much
#   more powerful and professional tool for reporting events in a program. It is the
#   standard for any script that runs as a process, like this indexing script.

#   Here's why it's better:


#    * Severity Levels: You can categorize your messages. logging.info() is for normal
#      updates ("Script is running"). logging.warning() is for non-critical issues.
#      logging.error() is for failures that stop the script. This allows you to quickly
#      see how important a message is.
#    * Timestamps & Structure: Logging can automatically add useful information to every
#      message, like the date, time, and severity level. This is incredibly helpful for
#      debugging what happened and when.
#    * Flexibility: You can easily configure the logging system to send messages to
#      different places. Right now, it's sending them to the console, but with a few
#      changes to the configuration, we could have it save all the output to a file
#      (index_builder.log) without changing any of the logging.info or logging.error
#      calls.

#   2. What does logging.basicConfig(...) on Line 10 Mean?

#   This is the one-time setup command for the logging module in this script. Let's
#   break it down:


#   logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] -
#   %(message)s')


#    * level=logging.INFO: This sets the minimum "importance" level that will be
#      displayed. It tells the logger to show all INFO, WARNING, and ERROR messages.
#    * format=...: This is a template that defines how each log message will look.
#        * %(asctime)s: This automatically inserts the current date and time.
#        * %(levelname)s: This inserts the severity level (e.g., INFO, ERROR).
#        * %(message)s: This is where your actual message goes.


#   So, that one line of configuration is what turns a simple logging.error("File not
#   found") call into the rich, informative output we saw in the log: [2026-03-06
#   18:00:23,766] [ERROR] - Knowledge graph file not found...

#   3. If logging is better, why don't we use it in the main agent?

#   This is the most insightful question. The choice depends on the purpose of the
#   script.


#    * `build_graph_index.py` is a "Batch Job": It's an offline, non-interactive script.
#      Its purpose is to perform a task and report its progress and result. logging is
#      the perfect and standard tool here because it creates a formal, structured report
#      of the execution.


#    * `advanced_agent.py` is an "Interactive Application": The print("--- NODE: ...
#      ---") statements in the agent are not meant as formal logs. They are simple,
#      real-time diagnostic status updates for you, the developer, to see the agent
#      "thinking" and follow its flow of control. Using the verbose, timestamped format
#      from the logging module here would make the interactive output very cluttered and
#      harder to read at a glance.


#   In a truly production-grade system, you would actually use both. You would keep the
#   simple print() statements for the clean interactive display, and you would also
#   configure the logging module in the agent to save much more detailed debug
#   information to a persistent file (e.g., agent_run.log) for later analysis.


#   So, we used the right tool for the right job in each script: logging for the formal
#   batch process, and print for the simple, interactive diagnostic view.


# That's a great, precise question about the inner workings of the NetworkX library.
#   You are thinking exactly right.

#   Let's look at this line:
#    1 for node_id, data in G.nodes(data=True):


#   The G.nodes(data=True) method returns an iterator that yields a series of 2-part
#   tuples. Each tuple contains:
#    1. The unique ID of the node.
#    2. A dictionary containing all the attributes of that node.


#   So, for a single node like our organizations table, the item yielded by the iterator
#   would look like this:
#    1 ( 
#    2   "organizations",                                     # Part 1: The Node ID
#    3   {"label": "Table", "description": "Parent company..."}  # Part 2: The Attribute
#      Dictionary
#    4 )


#   When we use the for node_id, data in ... syntax, Python performs "tuple unpacking."
#   It automatically:
#    * Assigns the first item of the tuple ("organizations") to the node_id variable.
#    * Assigns the second item of the tuple (the dictionary {"label": ...}) to the data
#      variable.


#   To answer your question directly: You are correct. The data variable is limited to
#   only the attributes we added (label, description, etc.). The node_id is not also
#   contained inside the data dictionary; it is provided as a separate item in the
#   tuple. This is why we need both variables, node_id and data, in our loop to get all
#   the information.


# ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
# ✦ Excellent questions. You are correctly piecing together how the final system works.
#   Let's clarify both points.


#   1. The Structure of the New LanceDB Table

#   You are exactly right. The new graph_node_index table is structured very similarly
#   to a standard document vector store, but we've named the columns to fit our specific
#   purpose.


#   The schema is defined by the NodeIndex Pydantic model in build_graph_index.py:
#    1 class NodeIndex(BaseModel):
#    2     node_id: str
#    3     text: str 
#    4     vector: list[float]
#   So, a single row in this new table will look like this:



#   ┌───────────────────────────────────┬────────────────────────────────┬─────────┐
#   │ node_id (string)                │ text (string)                │ `vector │
#   │                                   │                                │ ` (list │
#   │                                   │                                │ of      │
#   │                                   │                                │ floats) │
#   ├───────────────────────────────────┼────────────────────────────────┼─────────┤
#   │ "invoices"                      │ `"Type: Table, Name: invoices, │ `[0.12, │
#   │                                   │ Description: Monthly billing   │ -0.45,  │
#   │                                   │ rows..."`                      │ ...]`   │
#   │ `"contracts.total_contract_value" │ `"Type: Column, Name:          │ `[0.34, │
#   │ `                                 │ contracts.total_contract_value │ 0.56,   │
#   │                                   │ , Description: Total monetary  │ ...]`   │
#   │                                   │ value..."`                     │         │
#   └───────────────────────────────────┴────────────────────────────────┴─────────┘



#   You can think of it this way:
#    * node_id is the unique identifier, like a document ID.
#    * text is the searchable content, analogous to a "chunk" of text.
#    * vector is the embedding of that text.

#   Your understanding of the table's structure is perfect.

#   2. The Search Mechanism: Not Just Vectors


#   To answer your second question: no, the search will not be on the vectors only.

#   As we discussed, we are using LanceDB's powerful built-in hybrid search. This is the
#   key to the graph_explorer's intelligence.


#   Here's what happens when we call this line in the graph_explorer:
#    1 results = graph_index_table.search(question,
#      query_type="hybrid").limit(3).to_list()
#   LanceDB automatically performs two searches in parallel:
#    1. Vector Search: It compares the embedding of your question against the vector
#       column to find nodes that are semantically similar.
#    2. Full-Text Search (FTS): It searches for the keywords in your question within the
#       text column to find nodes that are a literal match. We enabled this by running
#       table.create_fts_index("text") in our indexing script.


# Of course. Those are both excellent, detailed questions about how LanceDB works
#   "under the hood."


#   1. What does create_fts_index("text") actually do?

#   Creating a Full-Text Search (FTS) index is like creating the index you find at the
#   back of a textbook.


#   Without an Index:
#   Imagine you have a 500-page book and you want to find every page that mentions the
#   word "contract." Without an index, you would have no choice but to read every single
#   word on all 500 pages. This is very slow.


#   With an FTS Index:
#   The table.create_fts_index("text") command does the hard work once, upfront. It goes
#   through the text column of every single row and builds a special map, called an
#   inverted index. This index looks conceptually like this:


#    1 {
#    2   "contract": [row_5, row_12, row_43, ...],
#    3   "invoice":  [row_1, row_12, row_22, ...],
#    4   "paid":     [row_1, row_33, ...],
#    5   ...
#    6 }
#   It maps every important word to a list of all the rows that contain it.


#   Now, when you do a keyword search for "contract," the database doesn't read the
#   whole table. It just does a lightning-fast lookup in this index, sees that it only
#   needs to look at rows 5, 12, and 43, and retrieves them instantly.


#   So, create_fts_index("text") is a one-time operation that pre-processes the text
#   data to enable these incredibly fast keyword searches.

#   2. How does .search() know which column is the vector?

#   This is an excellent question about the "magic" of a vector database. The search()
#   method knows which column to use because of the schema that was defined when we
#   created the table.


#   Remember the Pydantic schema we used in build_graph_index.py:
#    1 class NodeIndex(BaseModel):
#    2     node_id: str
#    3     text: str 
#    4     vector: list[float]
#   When we created the LanceDB table from this schema, LanceDB's internal logic did two
#   things:
#    1. It saw node_id and text and treated them as normal data columns.
#    2. It saw vector: list[float] and, because it's a vector database, it specifically
#       tagged this column as the primary vector column for this table. This information
#       is stored as part of the table's permanent metadata.


#   Therefore, when you later call graph_index_table.search(question), the method is
#   pre-programmed to automatically:
#    1. Look at the table's internal metadata.
#    2. Identify which column has the "primary vector" tag (in our case, the vector
#       column).
#    3. Perform the vector similarity search using the data in that specific column.


#   In short, LanceDB tables are "vector-aware." The schema itself makes the vector
#   column special and tells all future search operations which column to use for vector
#   calculations.
