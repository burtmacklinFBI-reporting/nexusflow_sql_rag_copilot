
import streamlit as st

@st.cache_data(show_spinner=False, ttl=3600)
def cached_embed(text: str):
    from advanced_agent import safe_embed_query
    return safe_embed_query(text)


@st.cache_data(show_spinner=False, ttl=3600)
def cached_rerank(query: str, docs_tuple: tuple):
    from advanced_agent import rerank
    result = rerank(query, list(docs_tuple))

    if result == [0.5] * len(docs_tuple):
        raise ValueError("Rerank failed, given 0.5 defult score — do not cache") ## streamlit does not cache values errors
    
    return result
