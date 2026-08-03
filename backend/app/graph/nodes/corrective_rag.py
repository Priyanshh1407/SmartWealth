import os
import time
from typing import List, Dict, Any
from dotenv import load_dotenv
load_dotenv()

# --- Configurable via Environment Variables ---
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", 3))
API_DELAY_SECONDS = float(os.environ.get("API_DELAY_SECONDS", 4))

from langchain_chroma import Chroma # type: ignore
from langchain_google_genai import ChatGoogleGenerativeAI # type: ignore
from langchain_groq import ChatGroq # type: ignore
from langchain_core.prompts import ChatPromptTemplate # type: ignore
from langchain_core.output_parsers import StrOutputParser # type: ignore
from langchain_huggingface import HuggingFaceEmbeddings # type: ignore

from backend.app.graph.state import AuditState, DeductibilityResult, CategorizedTransaction
from backend.app.rag.grader import get_retrieval_grader
from backend.app.progress import progress_store

# Initialize shared resources
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../../../"))
CHROMA_PATH = os.path.join(project_root, "data", "chroma_db")

embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
vectorstore = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
grader = get_retrieval_grader()

def _rag_call_with_backoff(fn, label: str):
    """Calls fn() with exponential backoff on rate-limit errors. Returns result or None."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn()
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = any(k in err_str for k in ("429", "resource_exhausted", "rate", "quota", "504", "503", "502", "500", "timeout"))
            if is_rate_limit and attempt < MAX_RETRIES:
                wait = API_DELAY_SECONDS * (2 ** (attempt - 1))  # 4s → 8s → 16s
                print(f"      ⏳ Rate limit on {label} (attempt {attempt}/{MAX_RETRIES}). Waiting {wait:.0f}s...")
                time.sleep(wait)
            else:
                print(f"      ⚠️ Error on {label} (attempt {attempt}/{MAX_RETRIES}): {e}")
                return None
    return None


def rewrite_query(original_query: str) -> str:
    """Rewrites a query to be better optimized for vector retrieval."""
    primary_llm = ChatGoogleGenerativeAI(
        model="gemini-3-flash-preview",
        temperature=0,
        max_retries=0,
        timeout=30
    )

    # Initialize Groq Fallback
    fallback_llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0,
        max_retries=0,
        timeout=30
    )

    # Create the resilient fallback chain
    llm = primary_llm.with_fallbacks([fallback_llm])
    system = """You are an expert in Indian Income Tax Law. Convert the input question into a broader, optimized search query for vectorstore retrieval. 
    Include keywords like 'business expenditure', 'deduction', and synonyms for the category name. Keep it concise."""
    re_write_prompt = ChatPromptTemplate.from_messages([
        ("system", system),
        ("human", "Here is the initial question: \n\n {question} \n Formulate an improved question."),
    ])
    chain = re_write_prompt | llm | StrOutputParser()
    return chain.invoke({"question": original_query})


def _evaluate_category(category: str, max_retries: int = 1) -> Dict[str, Any]:
    """
    Evaluates deductibility for an entire CATEGORY (not a single transaction).
    This is the CRAG loop: retrieve -> grade -> rewrite -> retry -> flag.
    
    Returns a dict with the result template that can be applied to all transactions
    in this category.
    """
    query = f"Are {category} business expenses tax deductible under the Indian Income Tax Act?"
    current_query = query
    retries = 0

    try:
        while retries <= max_retries:
            docs = retriever.invoke(current_query)
            relevant_docs = []

            # Grade each retrieved document with backoff
            for doc in docs:
                score = _rag_call_with_backoff(
                    lambda d=doc: grader.invoke({"question": current_query, "document": d.page_content}),
                    f"grader/{category}"
                )
                if score and score.binary_score.lower() == "yes":
                    relevant_docs.append(doc)
                time.sleep(API_DELAY_SECONDS)
            
            # If we have relevant documents, return the result template
            if relevant_docs:
                source_citations = [doc.metadata.get('source', 'Unknown Document') for doc in relevant_docs]
                passage_text = relevant_docs[0].page_content.strip()
                return {
                    "is_deductible": True,
                    "reasoning": "Relevant tax documents found.",
                    "source_citation": source_citations[0] if source_citations else "Unknown",
                    "source_passage": passage_text,
                    "error": None,
                }
            
            # Rewrite and retry if no relevant documents were found
            retries += 1
            if retries <= max_retries:
                rewritten = _rag_call_with_backoff(
                    lambda: rewrite_query(query),
                    f"query_rewrite/{category}"
                )
                if rewritten:
                    current_query = rewritten
                else:
                    break  # Don't retry if rewrite itself fails
    except Exception as e:
        error_msg = f"CRAG error for category '{category}': {e}"
        print(f"      ⚠️ {error_msg}")
        return {
            "is_deductible": False,
            "reasoning": "undetermined",
            "source_citation": "None",
            "source_passage": "",
            "error": error_msg,
        }

    # EXIT CRITERIA HIT: Give-up-and-flag. Never fallback to parametric memory.
    return {
        "is_deductible": False,
        "reasoning": "undetermined",
        "source_citation": "None",
        "source_passage": "",
        "error": None,
    }


def corrective_rag_node(state: AuditState) -> Dict[str, Any]:
    """
    Node 2: Evaluates deductibility using Corrective RAG.
    
    OPTIMIZATION: Groups transactions by predicted_category and runs the CRAG
    loop ONCE per unique category instead of once per transaction.
    This reduces API calls from ~900 (300 txns × 3 docs) to ~15 (5 categories × 3 docs).
    """
    print("🔵 [NODE 2] Running Corrective RAG for deductibility analysis...")
    
    thread_id = state.get("thread_id", "")
    categorized = state["categorized"]
    all_errors = list(state.get("errors", []))
    
    # --- Step 1: Group transactions by predicted category ---
    category_groups: Dict[str, List[CategorizedTransaction]] = {}
    for tx in categorized:
        category_groups.setdefault(tx.predicted_category, []).append(tx)
    
    unique_categories = list(category_groups.keys())
    print(f"   Found {len(unique_categories)} unique categories across {len(categorized)} transactions.")
    print(f"   Categories: {unique_categories}\n")
    
    progress_store.update(
        thread_id,
        current_node="corrective_rag",
        message=f"Evaluating deductibility for {len(unique_categories)} categories…",
        processed=0,
        total=len(unique_categories),
    )
    
    # --- Step 2: Evaluate deductibility ONCE per category ---
    category_results: Dict[str, Dict[str, Any]] = {}
    
    for idx, category in enumerate(unique_categories, 1):
        txn_count = len(category_groups[category])
        print(f"   -> [{idx}/{len(unique_categories)}] Evaluating '{category}' ({txn_count} transactions)...")
        
        progress_store.update(
            thread_id,
            message=f"RAG: Evaluating '{category}' ({idx}/{len(unique_categories)}) — covers {txn_count} transactions",
            processed=idx - 1,
        )
        
        result = _evaluate_category(category)
        category_results[category] = result
        
        status = "✅ DEDUCTIBLE" if result["is_deductible"] else "❌ Not deductible"
        print(f"      Result: {status} | Citation: {result['source_citation']}")
        
        if result["is_deductible"] and result["source_passage"]:
            preview = result["source_passage"].replace("\n", " ")[:150]
            print(f"      Passage: \"{preview}...\"")
        
        if result["error"]:
            all_errors.append(result["error"])
            progress_store.add_error(thread_id, result["error"])
        
        # Small delay between categories
        if idx < len(unique_categories):
            time.sleep(API_DELAY_SECONDS)
    
    # --- Step 3: Fan out results to ALL transactions ---
    deductibility_results = []
    for tx in categorized:
        template = category_results.get(tx.predicted_category, {
            "is_deductible": False,
            "reasoning": "undetermined",
            "source_citation": "None",
            "source_passage": "",
        })
        
        deductibility_results.append(DeductibilityResult(
            transaction_id=tx.transaction_id,
            is_deductible=template["is_deductible"],
            reasoning=template["reasoning"],
            source_citation=template["source_citation"],
            source_passage=template.get("source_passage", ""),
        ))
    
    progress_store.update(
        thread_id,
        message=f"RAG complete: {len(deductibility_results)} transactions evaluated across {len(unique_categories)} categories",
        processed=len(unique_categories),
    )
    
    print(f"\n   ✅ Corrective RAG complete: {len(deductibility_results)} results from {len(unique_categories)} category lookups.")
    return {"deductibility_results": deductibility_results, "errors": all_errors}