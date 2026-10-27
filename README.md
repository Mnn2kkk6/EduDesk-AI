# EduDesk AI — Student Support & Workflow Agent

EduDesk AI is a local-first EdTech support assistant built to demonstrate RAG, LLM tool calling, structured data lookup, ticket workflows, and basic evaluation. All people, course records, and policies are fictional.

## What is included

- RAG over local Markdown, TXT, and PDF documents. The app shows the retrieved source snippets.
- Student and enrollment lookup through controlled Python tools.
- Course schedule lookup.
- Support ticket creation with a specific title, course association, issue description, priority, and status.
- A Ticket Dashboard with seeded examples, filters, ticket details, suggested next actions, an illustrative SLA target, and status history.
- Ticket status transitions: Open, In progress, and Resolved.
- A Demo Data tab showing students, courses, and enrollment/payment/access states.
- Document upload and local re-indexing.
- Optional Gemini API integration for LLM generation and automatic function calling.
- Offline Demo Mode that lets you demonstrate the retrieval and ticket flow without an API key.
- Pytest tests and GitHub Actions CI.

This is a portfolio demo, not a production student information system. It has no authentication and must not be connected to real student records.

## Architecture

- Streamlit: chat interface, ticket dashboard, data viewer, and document upload.
- FastAPI: chat, documents, students, courses, enrollments, tickets, and status update endpoints.
- RAG baseline: TF-IDF retrieval and cosine similarity over local text chunks. No vector database server is needed.
- Agent: Google Gen AI SDK with Python function tools when GEMINI_API_KEY is configured.
- SQLite: fictional students, courses, enrollments, tickets, ticket status history, and tool-call logs.
- Pytest: database, retrieval, ticket creation, and status-history tests.

The retriever currently uses TF-IDF rather than neural embeddings. This is intentional for the lightweight MVP: setup is faster and deterministic. Evaluate it before deciding whether a multilingual embedding model and vector database are needed.

## Sample data

The app automatically creates the following demo data in the local SQLite database when first started:

### Students

| ID | Name | Scenario |
| --- | --- | --- |
| SV001 | Nguyen An | PY101 paid, access pending |
| SV002 | Tran Binh | SQL101 paid, access active |
| SV003 | Le Chi | ML201 payment pending, access not activated |

### Courses

| ID | Course | Start date | Duration |
| --- | --- | --- | --- |
| PY101 | Python Beginner | 2026-11-02 | 6 weeks |
| SQL101 | SQL for Data Analysis | 2026-11-09 | 4 weeks |
| ML201 | Machine Learning Foundations | 2026-11-16 | 8 weeks |

### Seeded tickets

Four sample tickets are inserted automatically when the ticket table is empty:

- EDU-DEMO-001: PY101 was paid but the access flag is still pending; High / Open.
- EDU-DEMO-002: SQL101 week-one assignment is not visible in the LMS; Medium / In progress.
- EDU-DEMO-003: ML201 payment status needs confirmation before access is granted; Medium / Open.
- EDU-DEMO-004: SQL101 start date confirmation; Low / Resolved.

Ticket data is synthetic. The seeded policies and SLA targets are for demonstration only. The app seeds example tickets if the ticket table is empty, so an existing local database from the initial MVP will also populate its dashboard on restart.

## Repository layout

    app/
      agent.py
      config.py
      database.py
      knowledge_base.py
      main.py
    data/
      knowledge_base/
        faq.md
        policies.md
        lms_guide.md
      uploads/
    tests/
      test_core.py
    streamlit_app.py
    requirements.txt
    .env.example

## Requirements

- Python 3.11 or 3.12 recommended.
- Internet access for installing packages.
- Optional Gemini API key for live LLM generation and automatic function calling.

## Setup on Windows PowerShell

Open PowerShell in the repository directory:

    cd C:\path\to\EduDesk-AI
    py -3.11 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    Copy-Item .env.example .env

If PowerShell blocks activation, run this for the current terminal only:

    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    .\.venv\Scripts\Activate.ps1

Open .env in a text editor. To test without Gemini, leave GEMINI_API_KEY blank. To test live LLM function calling, add your own key and use a model available to your account. Never commit .env or share the key.

## Run the app

### Terminal 1 — FastAPI

    .\.venv\Scripts\Activate.ps1
    uvicorn app.main:app --reload

Open the API documentation at http://127.0.0.1:8000/docs.

### Terminal 2 — Streamlit

Open another PowerShell window in the repository directory:

    .\.venv\Scripts\Activate.ps1
    streamlit run streamlit_app.py

Open the local URL printed by Streamlit, usually http://localhost:8501.

## First checks

In another PowerShell window, run:

    Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
    Invoke-RestMethod http://127.0.0.1:8000/api/v1/students
    Invoke-RestMethod http://127.0.0.1:8000/api/v1/courses
    Invoke-RestMethod http://127.0.0.1:8000/api/v1/enrollments
    Invoke-RestMethod http://127.0.0.1:8000/api/v1/tickets

Health should report status=ok and data_counts for students, courses, enrollments, and tickets. In the initial database, the dashboard should display four seeded example tickets.

## End-to-end demo script

1. Open the Demo Data tab. Inspect the sample students, courses, and enrollment/payment/access states.
2. Open Ticket Dashboard. Select EDU-DEMO-001. It should show Nguyen An, PY101, payment=paid, access=pending, a detailed issue description, a suggested next action, and an initial event in the history.
3. Change EDU-DEMO-001 from Open to In progress, add a note, and save. Verify that the status and history change.
4. Open the AI Assistant tab, select SV001, and ask: “Em đã thanh toán PY101 nhưng chưa truy cập được.” The demo path should check enrollment state and create a new high-priority ticket.
5. Return to Ticket Dashboard and confirm the new ticket appears.
6. Ask: “Lịch học PY101 bắt đầu khi nào?” The agent should use the course schedule tool.
7. Ask: “Chính sách hoàn học phí như thế nào?” Inspect the retrieved passages from the policy document.
8. Upload a small PDF, MD, or TXT document in the Documents tab and ask a question about a distinctive phrase in that file.

In Demo Mode, natural-language behavior is rule-based by design. With Gemini configured, the model generates the response and selects among the provided function tools.

## Run tests

    python -m compileall -q app streamlit_app.py
    python -m pytest -q

The test suite uses a temporary SQLite database and does not require a Gemini API key.

## API endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | /api/v1/health | Health, model configuration, indexed documents, and data counts |
| GET | /api/v1/students | Sample student records |
| GET | /api/v1/courses | Sample course catalog |
| GET | /api/v1/enrollments | Payment, enrollment, and access status |
| GET | /api/v1/tickets | Filter by student, status, priority, and limit |
| GET | /api/v1/tickets/{ticket_code} | Ticket detail with status history |
| PATCH | /api/v1/tickets/{ticket_code}/status | Update status and append an audit event |
| POST | /api/v1/chat | RAG chat and controlled agent tools |
| GET | /api/v1/documents | Indexed files and chunk count |
| POST | /api/v1/documents/upload | Upload PDF, Markdown, or TXT |

Use the interactive API schema at /docs to inspect requests and responses.

## Known limitations and safety boundaries

- All student, course, ticket, and policy data are synthetic.
- No authentication or authorization is implemented; the student selector is for local demonstration only.
- The SLA labels are illustrative targets, not contractual promises.
- TF-IDF can miss paraphrases and semantic matches; review the retrieved source snippets.
- Offline Demo Mode is not an LLM. Configure Gemini to demonstrate live LLM generation and automatic function calling.
- A production system needs authentication, role-based authorization, ticket creation confirmation, robust logging, privacy review, monitoring, and formal evaluation.

## Potential next improvements

1. Add a labeled test set and report retrieval Recall@5, citation correctness, classification quality, and tool success rate.
2. Compare TF-IDF with multilingual neural embeddings on a Vietnamese/English test set.
3. Add ticket comments and a human-confirmation step before irreversible actions.
4. Introduce authentication and authorization before connecting real student information.
