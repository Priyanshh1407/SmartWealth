from typing import List, Dict, Any
from dotenv import load_dotenv
load_dotenv()

from langchain_chroma import Chroma
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_huggingface import HuggingFaceEmbeddings

from app.graph.state import AuditState, DeductibilityResult, Transaction
from app.rag.grader import get_retrieval_grader

# Initialize shared resources
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
vectorstore = Chroma(persist_directory="../../../data/chroma_db", embedding_function=embeddings)
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
grader = get_retrieval_grader()

def rewrite_query(original_query: str) -> str:
    """Rewrites a query to be better optimized for vector retrieval."""
    llm = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", temperature=0)
    system = """You a question re-writer that converts an input question to a better version that is optimized 
    for vectorstore retrieval. Look at the input and try to reason about the underlying semantic intent / meaning."""
    re_write_prompt = ChatPromptTemplate.from_messages([
        ("system", system),
        ("human", "Here is the initial question: \n\n {question} \n Formulate an improved question."),
    ])
    chain = re_write_prompt | llm | StrOutputParser()
    return chain.invoke({"question": original_query})

def evaluate_deductibility(transaction: Transaction, max_retries: int = 1) -> DeductibilityResult:
    """
    Executes the CRAG loop for a single transaction.
    retrieve -> grade -> rewrite -> retry -> flag if unresolved.
    """
    query = f"What are the tax deduction rules for an expense categorized as: {transaction.category}?"
    current_query = query
    retries = 0

    while retries <= max_retries:
        docs = retriever.invoke(current_query)
        relevant_docs = []

        # Grade each retrieved document
        for doc in docs:
            score = grader.invoke({"question": current_query, "document": doc.page_content})
            if score.binary_score.lower() == "yes":
                relevant_docs.append(doc)
        
        # If we have relevant documents, we pass them down to the final report node
        if relevant_docs:
            source_citations = [doc.metadata.get('source', 'Unknown Document') for doc in relevant_docs]
            return DeductibilityResult(
                transaction_id=transaction.transaction_id,
                is_deductible=True,
                reasoning="Relevant tax documents found.",
                source_citation=source_citations[0] if source_citations else "Unknown"
            )
        
        # Rewrite and retry if no relevant documents were found
        retries += 1
        if retries <= max_retries:
            current_query = rewrite_query(query)

    # EXIT CRITERIA HIT: Give-up-and-flag. Never fallback to parametric memory.
    return DeductibilityResult(
        transaction_id=transaction.transaction_id,
        is_deductible=False,
        reasoning="undetermined",
        source_citation="None"
    )

def corrective_rag_node(state: AuditState) -> Dict[str, Any]:
    """
    Node 2: Takes categorized transactions and applies the CRAG loop to determine deductibility.
    """
    deductibility_results = []
    
    # Process only transactions that survived Node 1 with high confidence
    # (Low confidence items should be routed to Auditor Loop by edges before this node)
    for tx in state["categorized"]:
        result = evaluate_deductibility(tx)
        deductibility_results.append(result)
        
    return {"deductibility_results": deductibility_results}