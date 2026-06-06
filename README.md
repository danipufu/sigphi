# SigPhi

Humanities RAG chatbot grounded exclusively in primary public-domain texts.
Work in progress â€” Clean Architecture refactor under way on a Netcup VPS.

## Stack
- **Embeddings:** sentence-transformers (multilingual MiniLM, local)
- **Vector DB:** Pinecone (active) / ChromaDB (future, when RAM >= 16 GB)
- **LLM:** Google Gemini (gemini-2.5-flash-lite)
- **API:** FastAPI

See `CORPUS_MASTER.md` for the corpus specification.
