import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

load_dotenv()

# 1. Get the absolute, physical directory of this specific Python file (backend/app/rag)
SCRIPT_DIR = Path(__file__).resolve().parent

# 2. Navigate mathematically up to the project root
# rag -> app -> backend -> smart-wealth
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent

# 3. Construct the absolute paths directly to the target folders
CHROMA_PATH = os.getenv("CHROMA_PATH", str(PROJECT_ROOT / "data" / "chroma_db"))
PDF_DIR = os.getenv("PDF_DIR", str(PROJECT_ROOT / "data" / "tax_corpus" / "raw_pdfs"))

def ingest_tax_documents():
    """Loads tax PDFs, chunks them, and stores them in ChromaDB."""
    print(f"Loading PDFs from {PDF_DIR}...")
    loader = PyPDFDirectoryLoader(PDF_DIR)
    documents = loader.load()

    if not documents:
        print("No documents found. Ensure PDFs are in the raw_pdfs directory.")
        return

    # Tax codes are dense; use smaller chunks with decent overlap to maintain context
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        add_start_index=True,
    )
    chunks = text_splitter.split_documents(documents)
    print(f"Split into {len(chunks)} chunks.")

    # Using a local, lightweight Hugging Face model for completely private embeddings
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

    # Clear out the old DB if it exists for a fresh ingest
    if os.path.exists(CHROMA_PATH):
        print("Clearing existing Chroma database...")
        import shutil
        shutil.rmtree(CHROMA_PATH)

    print("Ingesting into Chroma...")
    Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=CHROMA_PATH
    )
    print("Ingestion complete.")

if __name__ == "__main__":
    ingest_tax_documents()