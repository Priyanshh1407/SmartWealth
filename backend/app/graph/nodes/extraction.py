import os
import time
import json
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from backend.app.graph.state import AuditState, CategorizedTransaction
from backend.app.tools.categorizer_tools import CategorizationResult, CATEGORIZER_PROMPT
from backend.app.progress import progress_store

# Load the .env file containing your GEMINI_API_KEY
load_dotenv()

# --- Configurable via Environment Variables ---
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", 5))
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", 3))
API_DELAY_SECONDS = float(os.environ.get("API_DELAY_SECONDS", 4))

primary_llm = ChatGoogleGenerativeAI(
        model="gemini-3-flash-preview",
        temperature=0,
        max_retries=0,   # We handle retries ourselves with backoff
        timeout=30
)

# Llama 3 8B is incredibly fast and free on Groq, perfect for categorization
fallback_llm = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0,
    max_retries=0,
    api_key=os.environ.get("GROQ_API_KEY")
)

# Bind the structured output schema to both models
primary_structured = primary_llm.with_structured_output(CategorizationResult)
fallback_structured = fallback_llm.with_structured_output(CategorizationResult)
structured_llm = primary_structured.with_fallbacks([fallback_structured])


def _invoke_with_backoff(prompt: str, txn_id: str):
    """
    Invokes the LLM with exponential backoff on rate-limit and timeout errors.
    Returns a CategorizationResult or None after all retries are exhausted.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return structured_llm.invoke(prompt)
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = any(k in err_str for k in ("429", "resource_exhausted", "rate", "quota", "504", "503", "502", "500", "timeout"))
            if is_rate_limit and attempt < MAX_RETRIES:
                wait = API_DELAY_SECONDS * (2 ** (attempt - 1))  # 4s → 8s → 16s
                print(f"      ⏳ API overloaded/timeout for {txn_id} (attempt {attempt}/{MAX_RETRIES}). Waiting {wait:.0f}s...")
                time.sleep(wait)
            else:
                print(f"      ⚠️ API Error on {txn_id} (attempt {attempt}/{MAX_RETRIES}): {e}\n")
                if attempt >= MAX_RETRIES:
                    return None
    return None


def _build_batch_prompt(batch: list) -> str:
    """Builds a single prompt for a batch of transactions."""
    txn_lines = ""
    for txn in batch:
        txn_lines += f"\n  - ID: {txn.transaction_id} | Date: {txn.date} | Merchant: {txn.merchant} | Amount: ₹{txn.amount} | Original Category: {txn.category} | Description: {txn.description}"

    return f"""{CATEGORIZER_PROMPT}

You will now be given a batch of {len(batch)} transactions. For EACH transaction, output a JSON object with:
  - transaction_id: the ID exactly as given
  - predicted_category: one of the allowed categories
  - confidence_score: float 0.0-1.0
  - reasoning: one-sentence explanation

Output a JSON ARRAY (one object per transaction, same order as input).
Do NOT wrap in markdown. Output raw JSON only.

TRANSACTIONS:{txn_lines}
"""


def _parse_batch_response(raw_text: str, batch: list) -> list:
    """Parses the LLM's JSON batch response into CategorizedTransaction objects."""
    try:
        clean = raw_text.strip().strip("```json").strip("```").strip()
        items = json.loads(clean)
        if not isinstance(items, list) or len(items) != len(batch):
            raise ValueError(f"Expected {len(batch)} items, got {len(items) if isinstance(items, list) else 'non-list'}")
        results = []
        for item in items:
            results.append(CategorizedTransaction(
                transaction_id=item["transaction_id"],
                predicted_category=item.get("predicted_category", "Unknown"),
                confidence_score=float(item.get("confidence_score", 0.0))
            ))
        return results
    except Exception as e:
        print(f"      ⚠️ Batch parse failed: {e}. Falling back to individual processing.")
        return []


def _process_batch(batch: list, thread_id: str = "") -> tuple:
    """
    Tries to process a batch of transactions in a single LLM call.
    Strategy:
      1. Try Gemini batch call (fast, but rate-limited)
      2. On failure, immediately try Groq batch call (free, no rate limit)
      3. Only if BOTH fail, fall back to individual per-transaction calls
    
    Returns: (results_list, errors_list)
    """
    errors = []
    print(f"   📦 Processing batch: {[t.transaction_id for t in batch]}")
    prompt = _build_batch_prompt(batch)
    message = [HumanMessage(content=prompt)]

    # --- Attempt 1: Gemini batch ---
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw = primary_llm.invoke(message)
            parsed = _parse_batch_response(raw.content, batch)
            if parsed:
                print(f"      ✅ Gemini batch succeeded.")
                return parsed, errors
            # parse OK but wrong count — try Groq batch next
            print(f"      ⚠️ Gemini batch parse mismatch. Trying Groq batch...")
            break
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = any(k in err_str for k in ("429", "resource_exhausted", "rate", "quota", "504", "503", "502", "500", "timeout"))
            if is_rate_limit and attempt < MAX_RETRIES:
                wait = API_DELAY_SECONDS * (2 ** (attempt - 1))  # 4s → 8s → 16s
                print(f"      ⏳ Gemini rate limit on batch (attempt {attempt}/{MAX_RETRIES}). Waiting {wait:.0f}s...")
                time.sleep(wait)
            else:
                err_msg = f"Gemini batch failed: {e}"
                print(f"      ⚠️ {err_msg}. Trying Groq batch...")
                # Do not append to frontend errors here, because we still have a Groq fallback!
                break

    # --- Attempt 2: Groq batch (same prompt, no rate limit) ---
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw = fallback_llm.invoke(message)
            parsed = _parse_batch_response(raw.content, batch)
            if parsed:
                print(f"      ✅ Groq batch succeeded.")
                return parsed, errors
            print(f"      ⚠️ Groq batch parse mismatch. Falling back to individual processing.")
            break
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = any(k in err_str for k in ("429", "resource_exhausted", "rate", "quota", "504", "503", "502", "500", "timeout"))
            if is_rate_limit and attempt < MAX_RETRIES:
                wait = API_DELAY_SECONDS * (2 ** (attempt - 1))
                print(f"      ⏳ Groq rate limit on batch (attempt {attempt}/{MAX_RETRIES}). Waiting {wait:.0f}s...")
                time.sleep(wait)
            else:
                err_msg = f"Groq batch also failed: {e}"
                print(f"      ⚠️ {err_msg}. Falling back to individual processing.")
                # Do not append to frontend errors here, because we still have individual fallback!
                break

    # --- Attempt 3: Individual fallback (structured_llm = Gemini → Groq per transaction) ---
    print(f"      🔄 Running individual fallback for {len(batch)} transactions...")
    results = []
    for txn in batch:
        print(f"   -> [Individual] Analyzing {txn.transaction_id} (Merchant: {txn.merchant})...")
        single_prompt = f"""
        {CATEGORIZER_PROMPT}

        TRANSACTION DETAILS:
        - ID: {txn.transaction_id}
        - Date: {txn.date}
        - Merchant: {txn.merchant}
        - Amount: ₹{txn.amount}
        - Original Category: {txn.category}
        - Description: {txn.description}
        """
        result = _invoke_with_backoff(single_prompt, txn.transaction_id)

        if result:
            categorized_txn = CategorizedTransaction(
                transaction_id=txn.transaction_id,
                predicted_category=result.predicted_category,
                confidence_score=result.confidence_score
            )
            print(f"      Result: {result.predicted_category} | Confidence: {result.confidence_score}")
        else:
            categorized_txn = CategorizedTransaction(
                transaction_id=txn.transaction_id,
                predicted_category="Unknown",
                confidence_score=0.0
            )
            err_msg = f"All API retries exhausted for {txn.transaction_id} (both Gemini & Groq). Marked as Unknown."
            print(f"      ❌ {err_msg}")
            errors.append(err_msg)

        results.append(categorized_txn)
        time.sleep(API_DELAY_SECONDS)

    return results, errors



def extraction_node(state: AuditState):
    print("🟢 [NODE 1] Running LLM Extraction & Categorization...")
    print(f"   Config: BATCH_SIZE={BATCH_SIZE}, MAX_RETRIES={MAX_RETRIES}, API_DELAY={API_DELAY_SECONDS}s")

    thread_id = state.get("thread_id", "")
    transactions = state.get("transactions", [])
    categorized_results = []
    all_errors = list(state.get("errors", []))

    # Update progress
    progress_store.update(
        thread_id,
        current_node="extraction",
        message="Starting extraction & categorization…",
        processed=0,
        total=len(transactions),
    )

    # Split transactions into batches
    batches = [transactions[i:i + BATCH_SIZE] for i in range(0, len(transactions), BATCH_SIZE)]
    print(f"   Processing {len(transactions)} transactions in {len(batches)} batch(es) of up to {BATCH_SIZE}...\n")

    for batch_num, batch in enumerate(batches, 1):
        print(f"\n   --- Batch {batch_num}/{len(batches)} ---")
        
        # Update progress before each batch
        progress_store.update(
            thread_id,
            message=f"Categorizing batch {batch_num}/{len(batches)} ({len(categorized_results)}/{len(transactions)} done)",
            processed=len(categorized_results),
        )
        
        batch_results, batch_errors = _process_batch(batch, thread_id)
        categorized_results.extend(batch_results)
        all_errors.extend(batch_errors)
        
        # Report errors to progress store too
        for err in batch_errors:
            progress_store.add_error(thread_id, err)

        # Respect rate limits between batches
        if batch_num < len(batches):
            time.sleep(API_DELAY_SECONDS)

    # Final progress update
    progress_store.update(
        thread_id,
        message=f"Extraction complete: {len(categorized_results)}/{len(transactions)} categorized",
        processed=len(categorized_results),
    )
    
    print(f"\n   ✅ Extraction complete: {len(categorized_results)}/{len(transactions)} transactions categorized.")
    return {"categorized": categorized_results, "current_node": "extraction_node", "errors": all_errors}