# EduDesk AI — Student Support & Workflow Agent

EduDesk AI is a small, local-first EdTech support assistant built to demonstrate LLM applications, RAG, tool calling, API integration, and evaluation basics. It uses fictional students and course records.

## What the demo does

- Answers policy and FAQ questions from local Markdown/TXT/PDF documents and shows the retrieved source snippets.
- Checks a student's payment, enrollment, and course access status through controlled Python tools.
- Looks up course start dates and durations through a SQLite tool.
- Creates a support ticket when the user explicitly asks or when the demo confirms a paid enrollment whose course access is still pending.
- Shows an agent trace with each tool's inputs and results.
- Supports uploading PDF, Markdown, and TXT files to the local knowledge base.
- Includes an offline Demo Mode so the UI, retrieval, SQLite tools, and ticket flow can be checked without an LLM API key. Configure Gemini to enable natural-language generation and automatic function calling.

This is a portfolio/demo project, not a production student information system. All records and policies are fictional.

## Architecture

- Streamlit: chat UI, source display, ticket dashboard, and document upload.
- FastAPI: chat, document upload, course, ticket, health, and document endpoints.
- RAG baseline: local TF-IDF retrieval and cosine similarity over chunks; no vector database server is required.
- Agent: Google Gen AI SDK with Python function tools when a Gemini API key is configured.
- SQLite: sample students, courses, enrollments, support tickets, and tool-call logs.
- Pytest: tests for retrieval, seeded data, enrollment status, and ticket creation.

The lightweight retriever uses lexical TF-IDF rather than a neural embedding model in this MVP. This keeps first-time setup smaller and predictable. A multilingual embedding model and a vector database can be added later if evaluation shows that lexical retrieval is insufficient.

## Repository layout

    app/
      agent.py            Gemini tool-calling agent and offline fallback
      config.py           Environment variables and local paths
      database.py         SQLite schema, seed records, and tool persistence
      knowledge_base.py   Document parsing, chunking, TF-IDF retrieval
      main.py             FastAPI endpoints
    data/
      knowledge_base/     Fictional FAQ, policies, and LMS guide
      uploads/            Uploaded documents (ignored by Git)
    tests/
      test_core.py        Core unit tests
    streamlit_app.py      User interface
    requirements.txt
    .env.example

## Requirements

- Python 3.11 or 3.12 recommended.
- Internet access for installing packages.
- Optional Gemini API key for live LLM responses and automatic tool calling. Without it, the app runs in Demo Mode with deterministic rule-based examples.

## Setup on Windows PowerShell

Open PowerShell in the repository folder. For example:

    cd C:\path\to\EduDesk-AI
    py -3.11 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    Copy-Item .env.example .env

If PowerShell blocks activation, run the following only for the current terminal session, then activate the environment again:

    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    .\.venv\Scripts\Activate.ps1

Open .env in an editor. To use Gemini, set GEMINI_API_KEY to your own key and keep GEMINI_MODEL set to a model enabled for your account. Do not commit .env or share your key. Leave the key blank for the offline demo.

## Run the app

### Terminal 1 — FastAPI

    .\.venv\Scripts\Activate.ps1
    uvicorn app.main:app --reload

Expected: Uvicorn reports that the server is running at http://127.0.0.1:8000.

Open the interactive API documentation at http://127.0.0.1:8000/docs.

### Terminal 2 — Streamlit

Open a second PowerShell window in the repository folder:

    .\.venv\Scripts\Activate.ps1
    streamlit run streamlit_app.py

Streamlit prints a local URL, usually http://localhost:8501. Open it in your browser.

## Check the backend before opening the UI

In a third PowerShell window, run:

    Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
    Invoke-RestMethod http://127.0.0.1:8000/api/v1/courses
    Invoke-RestMethod http://127.0.0.1:8000/api/v1/documents

Health should report status=ok and a positive retrieval_chunks count. If llm_configured is false, that is expected when running without a Gemini key.

## End-to-end demo script

Use the default selected student SV001 unless a test says otherwise.

1. Ask: “Chính sách hoàn học phí như thế nào?” The app should retrieve the refund policy document and display source snippets.
2. Ask: “Lịch học PY101 bắt đầu khi nào?” The app should call get_course_schedule and show the start date and duration.
3. Ask: “Em đã thanh toán PY101 nhưng chưa truy cập được.” SV001 has paid but access is pending in the seed data. The app should call get_enrollment_status and then create a high-priority ticket. The answer should show the ticket code.
4. Open the Ticket dashboard tab. Verify that the new ticket exists with category payment_access and status open.
5. Open Agent trace under the chat answer to inspect each tool name, arguments, and result.
6. In the Documents tab, upload a small policy PDF or TXT. Ask a question about a unique phrase in the file and check the source listing.
7. Select SV002 and ask for the SQL101 enrollment status. It should report active access; this should not create an issue ticket.

In Demo Mode, these examples are intentionally rule-based. With Gemini configured, the model performs natural-language generation and decides when to call the provided Python tools.

## Run tests

From the repository root with the virtual environment activated:

    python -m pytest -q

The tests use a temporary SQLite database and local text files. They do not require a Gemini API key.

## API endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | /api/v1/health | Backend status, LLM configuration, index size |
| GET | /api/v1/courses | Seeded course list |
| GET | /api/v1/tickets | Ticket list; optional student_id and limit query parameters |
| GET | /api/v1/documents | Indexed document list and chunk count |
| POST | /api/v1/chat | RAG chat and controlled agent tool execution |
| POST | /api/v1/documents/upload | Upload PDF, Markdown, or TXT and rebuild the local index |

The interactive API schema is available at /docs while FastAPI is running.

## Known limitations and safety boundaries

- The app uses synthetic records and simulated policies. Do not use it with real student records.
- There is no authentication layer. The student selector is for local demonstration only.
- TF-IDF retrieval is a lightweight baseline and may miss paraphrases or semantically similar wording. Review the displayed sources.
- The offline fallback is a deterministic demo path, not an LLM. Use a configured Gemini key to demonstrate actual LLM generation and automatic function calling.
- An LLM can make a poor tool choice. Tool functions validate the active student and ticket fields, and tool traces are stored for inspection.
- Uploaded documents are stored locally under data/uploads and are not committed to Git.
- Never paste API keys, passwords, OTPs, or payment card information into the chat.

## Suggested next improvements

1. Add a small labeled evaluation set and report Recall@5, citation correctness, and tool success rate.
2. Compare TF-IDF against a multilingual embedding model.
3. Add explicit confirmation UI before creating tickets in a future production-oriented version.
4. Add authentication and authorization before any real user or account data is connected.
