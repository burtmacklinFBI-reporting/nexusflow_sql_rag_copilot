import os
import lancedb
from langchain_community.vectorstores import LanceDB
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
import uuid
import json
import pandas

# --- 1. Configuration ---
KNOWLEDGE_BASE_DIR = "knowledge_base"
DB_DIR = "./lancedb_data"
TABLE_NAME = "nexusflow_hierarchical_kb" # Our new table
PARENT_DOCS_FILE = os.path.join(KNOWLEDGE_BASE_DIR, "parent_docs.json")
DOCS_TO_CHUNK = [
    "company_knowledge.md",
    "external_targets_2026.md",
    "sales_comp_plans.md",
    "sql_style_guide.md"
]

# Use local embeddings for reliable development
# embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2") # this is 90mb, 384 dimensions.
embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-base-en-v1.5") #this is 440MB, 768 dimensions so much nuanced so that is what are try for this project.

# --- 2. Hierarchical Chunking Logic ---

def hierarchical_chunker(file_path):
    """
    Splits a markdown file into a hierarchy of parent and child chunks.
    Returns the child chunks and a document store for the parents.
    """
    with open(file_path, "r") as f:
        content = f.read()

    # --- Step 1: Create Parent Chunks ---
    # These are the large, top-level sections based on markdown headers.
    headers_to_split_on = [("#", "Header 1"), ("##", "Header 2")]
    parent_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)

#   You are spot on. It's not exactly an "alias" in a programming sense, but you can
#   think of it as assigning a name to a header level.


#    * ("#", "Header 1") tells the splitter: "When you see a # (a top-level header),
#      store its text content in the metadata under the key 'Header 1'."
#    * ("##", "Header 2") tells it: "When you see a ## (a second-level header), store
#      its text in the metadata under the key 'Header 2'.

    parent_chunks = parent_splitter.split_text(content) # see here split_text is being used, cause the result is a text, and later in the child_chunks line there is split_documents being used.

    # --- Step 2: Create Child Chunks and Parent Doc Store ---
    # These are smaller chunks derived from the parent chunks.
    child_splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=100) # this is fast and easy first experiment with this and after if you want you can use the langchain_text_splitters.SentenceTransformersTokenTextSplitter, SemanticChunker. Semantic Chunker is a little bit tricky to figure things out like it has to be be done with grouping. Also now the RecursiveCharacterTextSplitter is using the basic ones, but you can also create seperators, or extra seperators you do want.
    
    all_chunks = []
    parent_chunks_doc_store = {}  # Initialize the document store, 
    for parent in parent_chunks:
        parent_id = str(uuid.uuid4()) #The IDs are completely random and are not sequential.
        parent_header = " > ".join([v for k, v in parent.metadata.items() if "Header" in k])
        #`"Sales Compensation Plans >
#   Accelerators & Bonuses"`. This breadcrumb is then attached to all the smaller child
#   chunks made from Parent Chunk 3, giving them perfect contextual awareness of where
#   they live in the document.

        # Store the parent document in the doc store
        parent_chunks_doc_store[parent_id] = parent
        
        # Create smaller child chunks from the parent
        child_chunks = child_splitter.split_documents([parent]) # `child_splitter.split_documents([parent])`
    #    * Input: A list of Document objects. (This is why parent is wrapped in []—the
    #      method is designed for batching, so it expects a list even if we're just
    #      giving it one document at a time inside our loop).
    #    * Action: For each document it receives, it performs the following magic, which
    #      you correctly deduced:
    #        1. It takes the page_content of the input document (parent.page_content)
    #           and splits it according to its rules (recursive character splitting,
    #           chunk size, etc.).
    #        2. For every new, smaller child chunk it creates, it automatically copies
    #           all the metadata from the original parent document.
        
        for child in child_chunks:
            # Add metadata to link the child to its parent
            child.metadata["parent_id"] = parent_id
            child.metadata["parent_header"] = parent_header
            child.metadata["source"] = os.path.basename(file_path)
            all_chunks.append(child)
            
    return all_chunks, parent_chunks_doc_store

# --- 3. Ingestion ---

def ingest():
    """
    Ingests the hierarchically chunked documents into LanceDB.
    Returns the vector store and the document store.
    """
    all_docs = []
    parent_chunks_doc_store = {}  # Initialize the main document store

    for doc_name in DOCS_TO_CHUNK:
        file_path = os.path.join(KNOWLEDGE_BASE_DIR, doc_name)
        if os.path.exists(file_path):
            chunks, new_store = hierarchical_chunker(file_path)
            all_docs.extend(chunks) # to avoid list inside list and to have list of documents.
            parent_chunks_doc_store.update(new_store) # Add the new parent documents to the main store
            print(f"Chunked {doc_name} into {len(chunks)} hierarchical chunks.")

    if not all_docs:
        print("No documents to ingest. Aborting.")
        return

    print(f"\nTotal documents to ingest: {len(all_docs)}")
    db = lancedb.connect(DB_DIR)

    # Check if the table already exists
    if TABLE_NAME in db.table_names():
        print(f"Table '{TABLE_NAME}' already exists. Dropping it.")
        db.drop_table(TABLE_NAME)
    
    # Create the new vector store from our hierarchical chunks
    LanceDB.from_documents(
        documents=all_docs,
        embedding=embeddings,
        connection=db,
        table_name=TABLE_NAME
    )


# The vector_store is a "Pointer"


#   "Pointer" is a great analogy. More accurately, the vector_store object is a live
#   client or a handler for that specific table. It's a Python object that holds:
#    * The active connection to the database.
#    * The name of the table it's supposed to talk to (nexusflow_hierarchical_kb).
#    * The specific embedding model (BAAI/bge-base-en-v1.5) that was used to create the
#      vectors.

#   It's the main tool you use to interact with your vectorized data.

#   3. The Search Process


#   You are exactly right. When you use this vector_store object to search, here's what
#   happens under the hood:

#    1 # This is what happens in the agent/retriever
#    2 results = vector_store.similarity_search("What is the commission accelerator?")


#    1. The vector_store takes the query string "What is the commission accelerator?".
#    2. It uses the same embeddings model it holds to convert this query into a query
#       vector.
#    3. It sends this query vector to the LanceDB table.
#    4. LanceDB performs an extremely fast vector search (an Approximate Nearest
#       Neighbor search) to find the rows in the table whose vectors are mathematically
#       most similar to the query vector.
#    5. It then returns the full Document objects (page content and metadata) for those
#       top matching rows.


#   So, you are correct on all counts. The vector_store is your interface to a physical
#   table, and it orchestrates the process of converting your text query into a vector
#   to perform a similarity search.


    print(f"\n[SUCCESS] Ingestion complete. LanceDB table '{TABLE_NAME}' is populated.")

    # --- Create FTS Index for Hybrid Search ---
    print("Creating FTS index for hybrid search...")
    table = db.open_table(TABLE_NAME)
    table.create_fts_index("text")
    print("[SUCCESS] FTS index created.")
    
    # --- Persist the parent document store ---
    print(f"Saving parent document store to {PARENT_DOCS_FILE}...")
    # Convert Document objects to a JSON-serializable format (id -> content)
    json_serializable_store = {pid: doc.page_content for pid, doc in parent_chunks_doc_store.items()}
    with open(PARENT_DOCS_FILE, "w") as f:
        json.dump(json_serializable_store, f, indent=2)
    
    print(f"[SUCCESS] Parent document store saved with {len(json_serializable_store)} entries.")


if __name__ == "__main__":
    ingest()




#   The short answer is: Yes, LLMs are vastly better at finding the "needle in the
#   haystack" than vector search is, and that's precisely why this pattern works.

#   Let's dive into the details.


#   The Asymmetry: Why LLMs Succeed Where Vector Search Fails

#   The two systems work in fundamentally different ways, which is why their abilities
#   are so different.


#    * Vector Search is a Matching Tool: It operates on mathematics. It converts text to
#      a vector (an "average meaning") and finds other vectors that are mathematically
#      close. It has zero "reasoning" ability. As we discussed, this process of
#      averaging is what causes the specific "needle" to get lost in the general
#      "haystack."


#    * LLMs are a Reasoning Tool: They operate on attention. The "Transformer"
#      architecture that powers all modern LLMs uses a mechanism called
#      "self-attention." This allows the LLM, when given a prompt (a user query + a long
#      document), to dynamically figure out which words and sentences in the document
#      are most relevant to the query. It can "pay attention" to the important parts and
#      largely ignore the irrelevant parts.


#   This is exactly what you do when you read a book with a question in mind. You scan
#   the page, but your brain "lights up" and pays close attention when you see the
#   keywords and concepts related to your question. LLMs do a computational version of
#   this.

#   The "Lost in the Middle" Problem


#   Now, are LLMs perfect at this? No. And this is likely the research you are
#   remembering.


#   There is a well-documented phenomenon in LLM research called the "Lost in the
#   Middle" problem. Studies have shown that LLMs tend to recall information presented
#   at the very beginning and the very end of a long context window more reliably than
#   information that is buried right in the middle.

#   So, while an LLM is very good at finding the needle in the haystack, its performance
#   can start to degrade if the haystack becomes enormous (e.g., a 100,000-token context
#   window).


#   The Final Trade-Off: Why We Still Send the Parent Chunk

#   This brings us to your final, critical question: "Why not just send the smaller
#   chunk to the LLM?"

#   Here is the trade-off:


#    1. Sending Only the Small Chunk:
#        * Pro: Maximum precision. The LLM gets only the most relevant sentence. There's
#          no haystack at all, so no chance of getting "lost in the middle."
#        * Con (and this is a big one): Risk of losing critical context.
#            * What if the sentence before our small chunk said: NOTE: The following
#              rule only applies to deals in the EMEA region.
#            * What if the sentence after said: This accelerator is a one-time offer and
#              expires on March 31st.
#        * By sending only the small, isolated chunk, the LLM might give an answer that
#          is technically correct about the "1.2x" number but is dangerously wrong in
#          practice because it's missing the surrounding conditions.


#    2. Sending the Parent Chunk:
#        * Pro: Provides the full, local context. The LLM sees the surrounding
#          sentences, headers, and paragraphs, allowing it to give a safe,
#          well-reasoned, and accurate answer that respects the conditions and
#          exceptions.
#        * Con: A small risk of the "Lost in the Middle" problem if the parent chunk is
#          excessively long.

#   Conclusion:

# Point 2: The "Million-Dollar" Question

#   > "If you are using the small chunks to actually retrieve the parent chunk, why not
#   leave it at markdown splitter?...using a similarity search on the parent
#   chunk...Both are same, right?"


#   This is the most critical question for this entire strategy. It seems like two
#   different roads to the same destination. However, one road is a smooth, reliable
#   highway, and the other is a bumpy, unreliable dirt path.

#   The reason "Small-to-Big" is superior comes down to one core concept: Vector Search
#   is bad at finding a needle in a haystack.


#   Here’s why:

#   An embedding is a single vector that represents the average meaning of the entire
#   text chunk.


#    1. Searching Large "Parent" Chunks Directly (The "Haystack" Problem):
#        * Imagine a large parent chunk about "Sales Compensation." It talks about base
#          salary, commission structure, accelerators, quarterly bonuses, and the
#          approval process.
#        * The vector for this large chunk is a vague average of all those topics. It's
#          a "general compensation" vector. The specific detail about the "1.2x
#          accelerator" is diluted by all the other information.
#        * Now, a user asks a very specific question: "What is the 1.2x accelerator?"
#        * The query vector for this question is sharp and precise. When you compare
#          this sharp vector to the vague, "averaged out" vectors of all your large
#          parent chunks, the similarity scores can be misleading. The retriever might
#          find that a different parent chunk that happens to mention "accelerator" in a
#          different context is a slightly better mathematical match.
#        * The result: The search is unreliable. It often fails to find the specific
#          correct section.


#    2. Searching Small "Child" Chunks First (The "Needle" Advantage):
#        * Now, imagine a small child chunk that only contains: "For performance
#          exceeding 120% of quota, a 1.2x accelerator is applied to the commission
#          rate."
#        * The vector for this small chunk is sharp, dense, and precise. It's almost
#          purely about the "1.2x accelerator" concept.
#        * When you compare your sharp query vector to the vectors of these small
#          chunks, you get an extremely high and accurate similarity score with this
#          specific chunk.
#        * The result: The search is incredibly reliable at finding the exact, correct
#          piece of information.

#   Conclusion:


#   You are right that both methods end by giving a large parent chunk to the LLM. But
#   the "Small-to-Big" method is far more reliable at finding the correct parent chunk
#   to begin with.


#   We use the small chunks as highly accurate "pointers" or "homing missiles" to locate
#   the right information. Once we've found the precise location with a child chunk, we
#   then "zoom out" to its parent to gather the full context for the LLM.


# #   The standard best practice is to send the parent chunk.