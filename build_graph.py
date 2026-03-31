import os
from typing import List, Dict, Any
from pydantic import BaseModel, Field
import networkx as nx
from langchain_cerebras import ChatCerebras

# --- 1. Configuration ---
KNOWLEDGE_BASE_DIR = "knowledge_base"
SCHEMA_CARDS_DIR = os.path.join(KNOWLEDGE_BASE_DIR, "schema_cards")
GRAPH_FILE_PATH = "nexusflow_knowledge_graph.gml"


# The data that you are going to have, should be in the way the descriptions are going to be handled. Also if you are thinking of having join conditions in the encoding then rememeber one thing that the graph expansion should not leak into the retreival. If you see like wrong table joins or missing join awareness and in the retreival you might think of adding the join condionts also to the embedding text. One more thing is that we are going to test and check and know if this is necessary or not.

# --- 2. Pydantic Models for Graph Extraction ---
# These models define the exact JSON structure we want the LLM to return.
# This is far more reliable than parsing raw text.

class Node(BaseModel):
    id: str = Field(description="Unique identifier for the node (e.g., table name or 'table_name.column_name')")
    label: str = Field(description="The type of the node, must be either 'Table' or 'Column'")
    properties: Dict[str, Any] = Field(description="""A dictionary of node properties.
- For 'Table' Nodes: MUST contain a 'description' key with a string summary of the table.
- For 'Column' Nodes: MUST contain a 'data_type' key (string). SHOULD also include 'is_primary_key' (boolean) and 'description' (string) if available.""")

class Edge(BaseModel):
    source_id: str = Field(description="The id of the source node")
    target_id: str = Field(description="The id of the target node")
    label: str = Field(description="The type of relationship, e.g., 'HAS_COLUMN' or 'JOINS_WITH'")
    properties: Dict[str, Any] = Field(description="""Properties of the edge. For 'JOINS_WITH' edges, this MUST contain a 'join_condition' key that describes the exact SQL for the join, especially for "traps" involving casting or string manipulation.""")

class ExtractedGraph(BaseModel): # The with_structured_output function is smart and uses every piece of documentation it can find. The docstring you write for the class itself is used as the high-level description for the entire JSON object. So that is why are adding this description.
    """The complete graph structure extracted from the documentation."""
    nodes: List[Node]
    edges: List[Edge]

# --- 3. Graph Building Logic ---

def get_graph_from_llm(content: str, llm) -> ExtractedGraph:
    """
    Uses a structured-output LLM to extract graph data from schema documentation.
    """
    prompt = f"""
You are an expert database architect. Your task is to extract a comprehensive knowledge graph of all tables, columns, and their relationships from the provided schema documentation.

**CRITICAL INSTRUCTIONS:**
1.  **Node IDs:**
    *   For `Table` nodes, the `id` MUST be the table name (e.g., `"payments"`).
    *   For `Column` nodes, the `id` MUST be in the format `"table_name.column_name"` (e.g., `"payments.contract_ref_id"`).
2.  **Relationships:**
    *   Create a `HAS_COLUMN` edge from every `Table` to each of its `Column` nodes.
    *   Create `JOINS_WITH` edges between `Table` nodes where a relationship is defined.
    *   Accurately capture all properties for nodes and edges as defined in the requested JSON schema, paying special attention to join conditions.

    **Schema Documentation to Analyze:**```
{content}
```

Extract the graph structure as a JSON object that strictly adheres to the required format.
"""
    # Bind the Pydantic model to the LLM to force structured JSON output
    structured_llm = llm.with_structured_output(ExtractedGraph)
    
    print("Invoking LLM to extract graph data. This may take a moment...")
    try:
        graph_data = structured_llm.invoke(prompt)
        print("LLM extraction complete.")
        
        # --- START DEBUGGING ---
        print("\n--- DEBUG: Raw output from LLM ---")
        print(graph_data)
        print("--- END DEBUG ---\n")
        # --- END DEBUGGING ---

        return graph_data
    except Exception as e:
        import traceback
        print(f"\n[ERROR] An exception occurred during LLM extraction.")
        traceback.print_exc()
        return None

def build_graph():
    """
    Builds the knowledge graph from all schema documents and saves it to a file.
    """
    print("--- Starting Knowledge Graph Build Process ---")
    
    # For this task, a powerful reasoning model is preferred.
    # The 120B parameter model from Cerebras is excellent for complex structured data extraction.
    # Ensure you have a CEREBRAS_API_KEY in your .env file
    try:
        from dotenv import load_dotenv
        load_dotenv()
        llm = ChatCerebras(model="gpt-oss-120b", temperature=0)
    except Exception as e:
        print(f"Error initializing LLM. Make sure you have 'python-dotenv' and 'langchain-community' installed, and a valid CEREBRAS_API_KEY in your .env file. Error: {e}")
        return

    # 1. Consolidate all schema-related markdown files into one string
    schema_content_list = []
    
    # Add the main schema summary
    summary_path = os.path.join(KNOWLEDGE_BASE_DIR, "schema_summary.md")
    if os.path.exists(summary_path):
        with open(summary_path, "r") as f:
            schema_content_list.append(f.read())
            
    # Add individual schema cards
    if os.path.exists(SCHEMA_CARDS_DIR):
        for filename in sorted(os.listdir(SCHEMA_CARDS_DIR)):
            if filename.endswith(".md"):
                with open(os.path.join(SCHEMA_CARDS_DIR, filename), "r") as f:
                    schema_content_list.append(f.read())
    
    if not schema_content_list:
        print("No schema documents found. Aborting graph build.")
        return

    full_schema_content = "\n\n---\n\n".join(schema_content_list)


#     How .join() Works

#   Think of it like this: .join() is a method that belongs to a specific string, and
#   that string acts as the "glue."


#    1. The "Glue": In our code, the "glue" is the separator string: "\n\n---\n\n".
#    2. The List of Items: The method takes a list of strings as its input. In our case,
#       this is schema_content_list, which contains the text content of all our schema
#       files.


#   The .join() method then iterates through the list for you, takes every string, and
#   "glues" them together into one single string using the separator.

#   A Simple Example

#   Imagine you have this list:

#    1 my_list = ["first part", "second part", "third part"]


#   If you wanted to join them with  | , you would write:

#    1 separator = " | "
#    2 result = separator.join(my_list)
#    3
#    4 print(result)

#   The output would be a single string:
#   "first part | second part | third part"


#   It automatically puts the separator between the elements.

#   Our Code

#   In our case, schema_content_list might look like:
#   ['content of schema_summary.md', 'content of accounts_card.md', 'content of
#   contracts_card.md', ...]


#   So, the line full_schema_content = "\n\n---\n\n".join(schema_content_list) creates
#   one massive string that looks like this:


#     1 [content of schema_summary.md]
#     2
#     3 ---
#     4
#     5 [content of accounts_card.md]
#     6
#     7 ---
#     8
#     9 [content of contracts_card.md]
#    10
#    11 ...and so on...


#   It's the standard, most efficient, and most "Pythonic" way to accomplish this task.
#   You are right—no manual loop is needed.


    # 2. Use LLM to extract the graph structure
    extracted_graph = get_graph_from_llm(full_schema_content, llm)
    
    if not extracted_graph:
        print("Aborting graph build due to LLM extraction failure.")
        return None

    # 3. Save the raw extracted data for debugging
    print("Saving raw extracted graph data to extracted_graph.json...")
    try:
        with open("extracted_graph.json", "w") as f:
            f.write(extracted_graph.model_dump_json(indent=2))
        print("Successfully saved raw data.")
    except Exception as e:
        print(f"\n[WARN] Could not save extracted_graph.json. Error: {e}")

    # 4. Build the graph using NetworkX
    print("Constructing NetworkX graph...")
    # A MultiDiGraph can have multiple directed edges between the same two nodes,
    # which is useful for complex relationships, though we may not need it here.
    # It's a robust choice.
    G = nx.MultiDiGraph()
    
    for node in extracted_graph.nodes:
        # The 'properties' dict is unpacked as node attributes
        G.add_node(node.id, label=node.label, **node.properties) # since node is also a pydantic model you can access its fields using the dot conventions rather tahtn node['id'] where we do for dictionaries.
        
    for edge in extracted_graph.edges:
        # The 'properties' dict is unpacked as edge attributes
        G.add_edge(edge.source_id, edge.target_id, label=edge.label, **edge.properties)
        # When you use G.add_edge(), any keyword argument you provide (other than source and target) becomes an attribute of that edge. These attributes are stored in a dictionary.

    # 4. Save the final graph to disk
    try:
        nx.write_gml(G, GRAPH_FILE_PATH)
        print("\n[SUCCESS] Knowledge graph built successfully!")
        print(f"  - Nodes: {G.number_of_nodes()}")
        print(f"  - Edges: {G.number_of_edges()}")
        print(f"  - Saved to: '{GRAPH_FILE_PATH}'")
    except Exception as e:
        print(f"\n[ERROR] Failed to save the graph to file. Error: {e}")

    return G

# --- 4. Main Execution ---
if __name__ == "__main__":
    build_graph()
