# چت‌بات سازمانی مبتنی بر RAG

چت‌باتی که به کارکنان اجازه می‌دهد با زبان طبیعی از مستندات داخلی سازمان (سیاست‌ها، آیین‌نامه‌ها، مستندات فنی و…) سؤال بپرسند و **پاسخ مستند، همراه با منبع** بگیرند.

خط‌لوله‌ی RAG به‌صورت **دستی و بدون فریمورک** (بدون LangChain/LlamaIndex) پیاده‌سازی شده است: chunking، embedding، retrieval و ساخت prompt همه با کد پایتون ساده و کتابخانه‌های پایه انجام می‌شوند.

## پشته فناوری

| لایه | فناوری |
| --- | --- |
| فرانت‌اند | HTML + CSS + Tailwind (بیلدشده) + Vanilla JS ماژولار، فارسی و RTL |
| بک‌اند | Python 3.11+، FastAPI، Uvicorn |
| پایگاه‌داده برداری | ChromaDB (PersistentClient) |
| Embedding و LLM | API سازگار با OpenAI — پیش‌فرض: Ollama |
| پیکربندی | `python-dotenv` + Pydantic Settings |

## پیش‌نیازها

- Python 3.11 یا بالاتر (با 3.13 تست شده است)
- [Ollama](https://ollama.com) در حال اجرا روی همان ماشین

```bash
ollama serve            # اگر به‌صورت سرویس اجرا نشده است
ollama list             # مدل‌های موجود
```

## راه‌اندازی

```bash
# ۱) مدل‌ها را دانلود کنید (نام‌ها را خودتان انتخاب می‌کنید)
ollama pull qwen2.5:7b-instruct     # مدل چت
ollama pull bge-m3                  # مدل embedding چندزبانه (مناسب فارسی)

# ۲) پیکربندی
cp backend/.env.example backend/.env   # اگر از قبل وجود ندارد
# LLM_MODEL و EMBEDDING_MODEL را با نام مدل‌های خودتان پر کنید

# ۳) اجرا (محیط مجازی و وابستگی‌ها خودکار نصب می‌شوند)
bash scripts/run.sh
```

سپس در مرورگر باز کنید: <http://127.0.0.1:8000>

مستندات تعاملی API: <http://127.0.0.1:8000/api/docs>

### مدل‌های پیشنهادی فارسی

- **چت:** `qwen2.5:7b-instruct`، `llama3.1:8b` یا هر مدلی که در Ollama دوست دارید
- **Embedding:** `bge-m3` (چندزبانه و قوی در فارسی)، `nomic-embed-text`، `embeddinggemma`

> ⚠️ مدل embedding را بعد از ایندکس‌گذاری تغییر ندهید. اگر تغییر دهید، بردارهای قدیمی و جدید ناسازگار می‌شوند؛ برنامه با خطای ۴۰۹ هشدار می‌دهد و باید اسناد قبلی را حذف و دوباره ایندکس کنید.

### طول context در Ollama

Ollama به‌طور پیش‌فرض context کوچکی (حدود ۲k توکن) در نظر می‌گیرد و ممکن است ابتدای prompt را ببرد. برای پاسخ‌های بهتر:

```bash
OLLAMA_CONTEXT_LENGTH=8192 ollama serve
```

همچنین `CONTEXT_MAX_CHARS` در `.env` (پیش‌فرض ۶۰۰۰) اندازه‌ی متن منابعی را که به مدل داده می‌شود محدود می‌کند.

## پیکربندی (`.env`)

همه‌ی مقادیر حساس یا محیط‌وابسته در `backend/.env` قرار می‌گیرند و در کد هاردکد نمی‌شوند:

| متغیر | توضیح |
| --- | --- |
| `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` | سرویس و مدل چت (پیش‌فرض `http://localhost:11434/v1`) |
| `LLM_TEMPERATURE` / `LLM_MAX_TOKENS` | پارامترهای تولید پاسخ |
| `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` | سرویس و مدل embedding |
| `EMBEDDING_BATCH_SIZE` | تعداد قطعات در هر درخواست embedding |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | اندازه‌ی قطعه و هم‌پوشانی (کاراکتر) |
| `RETRIEVAL_TOP_K` / `SIMILARITY_THRESHOLD` | تعداد منابع و آستانه‌ی شباهت کسینوسی |
| `CONTEXT_MAX_CHARS` | سقف کاراکتر متن منابع در prompt |
| `HISTORY_MAX_TURNS` | تعداد نوبت‌های تاریخچه‌ی گفتگو که به مدل می‌رود |
| `MAX_UPLOAD_MB` | سقف حجم هر فایل |
| `CHROMA_PERSIST_DIR` / `CHROMA_COLLECTION_NAME` | مسیر ذخیره و نام مجموعه در ChromaDB |
| `CORS_ALLOWED_ORIGINS` | دامنه‌های مجاز فرانت‌اند |

تنظیمات در لحظه‌ی start-up اعتبارسنجی می‌شوند (مثلاً `CHUNK_OVERLAP < CHUNK_SIZE`) تا خطا در وسط اجرا ظاهر نشود.

## API

| Method | مسیر | کاربرد |
| --- | --- | --- |
| `POST` | `/api/ingest` | آپلود چند فایل (multipart، فیلد `files`) و ایندکس‌گذاری |
| `GET` | `/api/documents` | فهرست اسناد ایندکس‌شده |
| `DELETE` | `/api/documents/{doc_id}` | حذف سند و همه‌ی قطعه‌های آن |
| `POST` | `/api/chat` | پرسش و دریافت پاسخ کامل (JSON) |
| `POST` | `/api/chat/stream` | پرسش و دریافت پاسخ جریانی (SSE) |
| `GET` | `/api/health` | سلامت سرویس، ChromaDB، مدل‌ها و تنظیمات ناقص |

نمونه:

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"سیاست مرخصی استعلاجی چیست؟"}'
```

جریان SSE:

```
event: open      data: {"conversation_id":"..."}
event: sources   data: {"sources":[{"filename":"...","page":3,"score":0.72,...}]}
event: token     data: {"delta":"بر اساس "}
event: done      data: {"conversation_id":"...","stopped":false}
event: error     data: {"message":"...","status_code":503}
```

## معماری

```
مرورگر (Vanilla JS)
   │  POST /api/chat/stream (SSE)
   ▼
FastAPI ──► retriever ──► embedder ──► Ollama /v1/embeddings
   │            │
   │            └──► ChromaDB (collection.query + آستانه شباهت)
   ▼
prompt_builder (system prompt + منابع شماره‌دار + تاریخچه + سؤال)
   │
   └──► Ollama /v1/chat/completions (stream) ──► پاسخ + منابع
```

خط‌لوله‌ی ایندکس‌گذاری: `document_loader` (PDF صفحه‌به‌صفحه، DOCX، TXT/MD با تشخیص انکودینگ) → `chunking` (پنجره‌ی لغزان روی مرز جمله با نقطه‌گذاری فارسی) → `embeddings` (batch + retry) → `ChromaDB` + `doc_registry.json`.

```
backend/
├── app/
│   ├── main.py            # FastAPI، CORS، سرو کردن فرانت‌اند
│   ├── config.py          # Pydantic Settings + اعتبارسنجی
│   ├── runtime.py         # ساخت اجزای مشترک
│   ├── api/               # routes_chat, routes_ingest, routes_health
│   ├── rag/               # chunking, embeddings, vector_store, retriever, prompt_builder
│   ├── llm/client.py      # کلاینت OpenAI-compatible با streaming
│   ├── models/schemas.py  # مدل‌های Pydantic
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

## تست

```bash
cd backend
.venv/bin/python -m pytest
```

تست‌ها با embedding و مدل تقلبی اجرا می‌شوند و به شبکه/Ollama وابسته نیستند: chunking، prompt building، آستانه‌ی retrieval و جریان کامل ingest → chat → stream → delete.

## تولید مجدد CSS (Tailwind)

```bash
cd frontend
npm install          # فقط بار اول
npm run build:css    # یا npm run watch:css در زمان توسعه
```

`tailwind.css` از قبل ساخته و در پروژه ذخیره شده است؛ در زمان اجرا به CDN وابسته نیست.

## محدودیت‌های شناخته‌شده

- **بدون احراز هویت/لاگین** (طبق تصمیم پروژه). اگر سرویس را روی شبکه باز می‌گذارید، آن را پشت reverse proxy با احراز هویت قرار دهید.
- **بدون OCR:** PDFهای اسکن‌شده متنی برای ایندکس ندارند و برنامه با هشدار صریح آن را گزارش می‌کند.
- **بدون rate limiting** و بدون لاگ ساخت‌یافته‌ی پرسش‌ها (می‌توان بعداً اضافه کرد).
- استخراج متن PDF فارسی به کیفیت فایل بستگی دارد؛ در صورت به‌هم‌ریختگی متن، نسخه‌ی DOCX/TXT را ایندکس کنید.
- یک collection مشترک برای همه‌ی اسناد؛ برای کنترل دسترسی بر اساس دپارتمان می‌توان فیلتر `where` روی متادیتا اضافه کرد.

## عیب‌یابی

| نشانه | علت و راه‌حل |
| --- | --- |
| «نیازمند تنظیم» در هدر | `LLM_MODEL` یا `EMBEDDING_MODEL` خالی است؛ بخش «وضعیت تنظیمات» را ببینید |
| خطای ۵۰۳ «اتصال به سرویس مدل» | Ollama اجرا نیست یا `LLM_BASE_URL` اشتباه است |
| «مدل … پیدا نشد» | `ollama pull <model>` را اجرا کنید |
| پاسخ‌ها نامرتبط‌اند | `SIMILARITY_THRESHOLD` را کم/زیاد کنید، `CHUNK_SIZE` را تنظیم کنید، مدل embedding فارسی‌پسند بگذارید |
| «در اسناد موجود پاسخی پیدا نکردم» | منابع بالای آستانه پیدا نشده؛ آستانه را کمی پایین بیاورید |
