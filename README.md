# RAG-Based Enterprise Chatbot

A chatbot that lets employees ask questions in natural language about internal organizational documents (policies, regulations, technical docs, etc.) and get **grounded answers with sources**.

The RAG pipeline is implemented **manually, without any framework** (no LangChain/LlamaIndex): chunking, embedding, retrieval, and prompt building are all done in plain Python with basic libraries.

## Video Tutorials

- RAG theory: [How to Build an AI Chatbot with Your Own Data?](https://youtu.be/TVSKG8c10f4) (Persian)
- Project implementation steps: [Hands-On RAG Project with FastAPI and Ollama | Without LangChain](https://youtu.be/URA2CMZims8) (Persian)

## Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | HTML + CSS + Tailwind (prebuilt) + modular Vanilla JS, Persian and RTL |
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Vector database | ChromaDB (PersistentClient) |
| Embedding and LLM | OpenAI-compatible API — default: Ollama |
| Configuration | `python-dotenv` + Pydantic Settings |

## Prerequisites

- Python 3.11 or higher (tested with 3.13)
- [Ollama](https://ollama.com) running on the same machine

```bash
ollama serve            # if it is not already running as a service
ollama list             # available models
```

## Setup

```bash
# 1) Pull the models (you choose the names)
ollama pull qwen2.5:7b-instruct     # chat model
ollama pull bge-m3                  # multilingual embedding model (good for Persian)

# 2) Configuration
cp backend/.env.example backend/.env   # if it doesn't already exist
# Fill LLM_MODEL and EMBEDDING_MODEL with your own model names

# 3) Run (the virtual environment and dependencies are installed automatically)
bash scripts/run.sh
```

Then open in your browser: <http://127.0.0.1:8000>

Interactive API docs: <http://127.0.0.1:8000/api/docs>

### Recommended Models for Persian

- **Chat:** `qwen2.5:7b-instruct`, `llama3.1:8b`, or any model you prefer in Ollama
- **Embedding:** `bge-m3` (multilingual and strong in Persian), `nomic-embed-text`, `embeddinggemma`

> ⚠️ Do not change the embedding model after indexing. If you do, old and new vectors become incompatible; the app will warn with a 409 error, and you must delete and re-index the previous documents.

### Context Length in Ollama

By default, Ollama uses a small context window (about 2k tokens) and may truncate the beginning of the prompt. For better answers:

```bash
OLLAMA_CONTEXT_LENGTH=8192 ollama serve
```

Also, `CONTEXT_MAX_CHARS` in `.env` (default 6000) limits the size of the source text passed to the model.

## Configuration (`.env`)

All sensitive or environment-dependent values live in `backend/.env` and are never hardcoded:

| Variable | Description |
| --- | --- |
| `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` | Chat service and model (default `http://localhost:11434/v1`) |
| `LLM_TEMPERATURE` / `LLM_MAX_TOKENS` | Generation parameters |
| `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` | Embedding service and model |
| `EMBEDDING_BATCH_SIZE` | Number of chunks per embedding request |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | Chunk size and overlap (in characters) |
| `RETRIEVAL_TOP_K` / `SIMILARITY_THRESHOLD` | Number of sources and cosine similarity threshold |
| `CONTEXT_MAX_CHARS` | Maximum characters of source text in the prompt |
| `HISTORY_MAX_TURNS` | Number of conversation history turns sent to the model |
| `MAX_UPLOAD_MB` | Maximum size per file |
| `CHROMA_PERSIST_DIR` / `CHROMA_COLLECTION_NAME` | Storage path and collection name in ChromaDB |
| `CORS_ALLOWED_ORIGINS` | Allowed frontend origins |

Settings are validated at start-up (e.g. `CHUNK_OVERLAP < CHUNK_SIZE`) so errors surface immediately rather than mid-run.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/ingest` | Upload multiple files (multipart, `files` field) and index them |
| `GET` | `/api/documents` | List indexed documents |
| `DELETE` | `/api/documents/{doc_id}` | Delete a document and all its chunks |
| `POST` | `/api/chat` | Ask a question and receive the full answer (JSON) |
| `POST` | `/api/chat/stream` | Ask a question and receive a streamed answer (SSE) |
| `GET` | `/api/health` | Health of the service, ChromaDB, models, and incomplete settings |

Example:

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What is the sick leave policy?"}'
```

SSE stream:

```
event: open      data: {"conversation_id":"..."}
event: sources   data: {"sources":[{"filename":"...","page":3,"score":0.72,...}]}
event: token     data: {"delta":"Based on "}
event: done      data: {"conversation_id":"...","stopped":false}
event: error     data: {"message":"...","status_code":503}
```

## Architecture

```
Browser (Vanilla JS)
   │  POST /api/chat/stream (SSE)
   ▼
FastAPI ──► retriever ──► embedder ──► Ollama /v1/embeddings
   │            │
   │            └──► ChromaDB (collection.query + similarity threshold)
   ▼
prompt_builder (system prompt + numbered sources + history + question)
   │
   └──► Ollama /v1/chat/completions (stream) ──► answer + sources
```

Indexing pipeline: `document_loader` (PDF page by page, DOCX, TXT/MD with encoding detection) → `chunking` (sliding window on sentence boundaries with Persian punctuation) → `embeddings` (batch + retry) → `ChromaDB` + `doc_registry.json`.

```
backend/
├── app/
│   ├── main.py            # FastAPI, CORS, serving the frontend
│   ├── config.py          # Pydantic Settings + validation
│   ├── runtime.py         # Builds shared components
│   ├── api/               # routes_chat, routes_ingest, routes_health
│   ├── rag/               # chunking, embeddings, vector_store, retriever, prompt_builder
│   ├── llm/client.py      # OpenAI-compatible client with streaming
│   ├── models/schemas.py  # Pydantic models
│   ├── services/          # document_loader, registry
│   └── data/              # raw_documents, chroma_db, doc_registry.json
├── tests/                 # pytest
└── requirements.txt
frontend/
├── index.html
├── css/{input.css,style.css,tailwind.css}
└── js/{api.js,chat.js,upload.js}
scripts/
├── run.sh
└── sample/leave-policy.txt
```

## Testing

```bash
cd backend
.venv/bin/python -m pytest
```

Tests run with a fake embedding and model and do not depend on the network or Ollama: chunking, prompt building, the retrieval threshold, and the full ingest → chat → stream → delete flow.

## Rebuilding CSS (Tailwind)

```bash
cd frontend
npm install          # first time only
npm run build:css    # or npm run watch:css during development
```

`tailwind.css` is prebuilt and committed to the project; there is no runtime dependency on a CDN.

## Known Limitations

- **No authentication/login** (by project decision). If you expose the service on a network, put it behind a reverse proxy with authentication.
- **No OCR:** scanned PDFs have no extractable text to index, and the app reports this with an explicit warning.
- **No rate limiting** and no structured query logging (can be added later).
- Persian PDF text extraction depends on file quality; if the text comes out garbled, index the DOCX/TXT version instead.
- A single shared collection for all documents; for department-based access control, a `where` filter on metadata can be added.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| "Needs configuration" in the header | `LLM_MODEL` or `EMBEDDING_MODEL` is empty; check the "configuration status" section |
| 503 error "connection to model service" | Ollama is not running or `LLM_BASE_URL` is wrong |
| "Model … not found" | Run `ollama pull <model>` |
| Answers are irrelevant | Raise/lower `SIMILARITY_THRESHOLD`, tune `CHUNK_SIZE`, use a Persian-friendly embedding model |
| "I couldn't find an answer in the available documents" | No sources passed the threshold; lower the threshold slightly |