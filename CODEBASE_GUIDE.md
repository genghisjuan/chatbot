# Juna Codebase Guide (Repo Map)

## 1) High-Level Overview

**Juna** is a dual-interface AI support system: it provides a customer-facing **Chatbot** for solving technical queries (using RAG + LLM) and an internal **Admin Dashboard** for support analysts to track trends, feedback, and KPIs. The backend is built with **Python (FastAPI)**, serving a vanilla JS/HTML frontend.

**Major Parts:**
*   **Chatbot UI:** Public interface for users to chat, upload images, and request support calls.
*   **Admin Dashboard:** Restricted interface for visualizing query volume, trending topics, and improved feedback.
*   **Backend API:** FastAPI application handling RAG logic, database logging, and analytics endpoints.
*   **Database:** Hybrid system using SQLAlchemy.
    *   **Local Development:** Uses SQLite (`analytics.db`).
    *   **Production (Railway):** Uses PostgreSQL.
*   **Deployment:** Docker-ready, configured for Railway via `Procfile`.

## 2) How to Run It (As-Is)

**Prerequisites:** Python 3.9+

**Steps:**
1.  **Environment Setup**:
    Copy `.env.example` to `.env` and fill in `OPENAI_API_KEY`.
    ```bash
    cp .env.example .env
    ```

2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run the Server**:
    Use the included start script or Uvicorn directly.
    ```bash
    # Option A: Direct
    uvicorn app.main:app --reload

    # Option B: Via Procfile logic (simulates prod)
    python migrate_db.py && uvicorn app.main:app
    ```

4.  **Verify**:
    *   **Chatbot:** Open `http://localhost:8000/`
    *   **Admin:** Open `http://localhost:8000/admin`
    *   **Health Check:** `http://localhost:8000/health` (Should return `{"status": "healthy"}`)

## 3) Architecture Map

**Data Flow Diagram:**

```text
Browser (User)      Browser (Admin)
      │                   │
      ▼                   ▼
[ Static Files (HTML/JS/CSS) ]
      │                   │
      └───────► ▲ ◄───────┘
                │ HTTP / JSON
                ▼
      [ FastAPI Backend (app.main) ]
                │
        ┌───────┴───────┐
        ▼               ▼
[ Chat Router ]   [ Admin Router ]
    │   │               │
    │   ▼               ▼
    │ [ LLM / RAG ]   [ Analytics Service ]
    │   │               │
    ▼   ▼               ▼
[ External APIs ]  [ Database (SQLite/PG) ]
   (OpenAI)           (Logs & Stats)
```

## 4) Directory-by-Directory Walkthrough

| Directory | Purpose | Notes |
| :--- | :--- | :--- |
| **`app/`** | The main application source code. | Core logic lives here. |
| **`app/api/`** | API route definitions (Controllers). | Defines your HTTP endpoints. |
| **`app/core/`** | App configuration and shared logic. | Settings and Bot core logic. |
| **`app/services/`** | Business logic layer. | **Crucial.** Contains Analytics, RAG, and Email services. |
| **`app/static/`** | Frontend assets (HTML, CSS, JS). | **Safe to edit** for UI changes. |
| **`data/`** | Local storage for RAG documents/indexes. | Do not manually edit built indexes. |
| **`docker/`** | Docker configuration files. | For containerized deployment. |
| **`docs/`** | Project documentation. | |

## 5) File-by-File Breakdown

### Root Configuration
*   **`app/main.py`**: **Entry Point.** Configures FastAPI, CORS, Rate Limiting (in-memory, 60 req/min), and mounts static files.
*   **`requirements.txt`**: Python dependencies (FastAPI, SQLAlchemy, LangChain, etc.).
*   **`Procfile`**: Railway deployment command. Runs `migrate_db.py` before starting the app.
*   **`migrate_db.py`**: Custom script to safely migrate database schema (e.g., converting `rating` from string to int).
*   **`.env`**: **Critical.** Stores secrets (API Keys, Database URL).

### Backend Logic (`app/`)
*   **`app/services/analytics.py`**: **Core Logic.**
    *   **Purpose:** Manages the database connection and all reading/writing of logs.
    *   **Key Function:** `get_trending_topics` (Calculates trends), `log_query`, `log_feedback`.
    *   **Gotcha:** Includes logic to use OpenAI to "categorize" queries for trends.
*   **`app/services/email_service.py`**: Handles sending support emails/tickets (SMTP).
*   **`app/api/chat.py`**:
    *   **Purpose:** Handles user chat messages and feedback.
    *   **Flow:** Receives message -> Calls `process_chat_stream` -> Streams response.
*   **`app/api/admin.py`**:
    *   **Purpose:** Powers the Admin Dashboard.
    *   **Key Functions:** `get_summary` (KPIs), `get_trends` (Charts), `run_alert_check` (Email alerts).
*   **`app/api/tts.py`**: Text-to-Speech endpoint (ElevenLabs integration).

### Frontend Code (`app/static/`)
*   **`index.html`**: The main Chatbot page structure.
*   **`js/app.js`**: **Main Frontend Logic.** Handles chat UI updates, API calls (`/chat`), and maintaining conversation history.
*   **`admin/index.html`**: The Admin Dashboard page.
*   **`admin/admin.js`**: **Admin Logic.** Fetches data from `/api/v1/admin/*` and renders charts (using Chart.js) and tables.
*   **`admin/admin.css`**: Styles specific to the admin panel.

## 6) Key User Flows

### Chat Message Flow
1.  **Frontend**: User types message -> `app.js` sends `POST /api/v1/chat`.
2.  **API**: `chat_endpoint` validates input (and optional image).
3.  **Bot**: `process_chat_stream` runs RAG logic + LLM generation.
4.  **Analytics**: `log_query` saves message to DB (async).
5.  **Response**: Streamed back to UI for typewriter effect.

### Feedback Flow (Thumbs Up/Down)
1.  **Frontend**: User clicks thumb -> `app.js` sends `POST /api/v1/feedback`.
2.  **API**: `feedback_endpoint` receives `message_id`, `rating` (1 or -1), and `user_query`.
3.  **DB**: `AnalyticsService.log_feedback` upserts the record (updates if exists).

### Admin Trends Flow
1.  **Frontend**: Admin loads page -> `admin.js` calls `GET /api/v1/admin/trends`.
2.  **API**: Parses date range (e.g., "Last 7 Days").
3.  **DB**: Queries `QueryLog` for timestamp buckets and `FeedbackLog` for sentiment.
4.  **Logic**: Aggregates counts by hour/day.
5.  **UI**: `admin.js` renders Chart.js graphs.

## 7) Data Model Explanation

The app uses **SQLAlchemy**. Tables are defined in `app/services/analytics.py`.

*   **`query_logs`**:
    *   **Entries**: One row per user message.
    *   **Fields**: `timestamp`, `message` (text), `category` (AI-assigned tag), `input_tokens`, `output_tokens`.
*   **`feedback_logs`**:
    *   **Entries**: One row per rated message.
    *   **Fields**: `user_query`, `bot_response`, `rating` (Integer: 1=Up, -1=Down), `message_id` (Link to chat).
    *   **Migration**: Codebase contains logic to migrate legacy string ratings ("up"/"down") to integers.
*   **`escalation_logs`**:
    *   **Entries**: Tracks when a user asks for a human ("email", "callback").

**DB Difference**:
*   **Local**: `analytics.db` (SQLite). File is created automatically.
*   **Prod**: Expects `DATABASE_URL` to point to PostgreSQL.

## 8) Configuration & Environments

*   **Logic**: `app/core/config.py` loads variables using Pydantic `BaseSettings`.
*   **Key Variables**:
    *   `OPENAI_API_KEY`: Required for Chat and Trends categorization.
    *   `DATABASE_URL`: Connection string.
    *   `SMTP_*`: For sending email alerts/tickets.
*   **Deployment (Railway)**:
    *   `Procfile` handles startup.
    *   `migrate_db.py` runs automatically on deploy to ensure schema consistency.

## 9) Known Risk Areas and Debugging Playbook

| Issue | Symptom | Check First |
| :--- | :--- | :--- |
| **Trends Empty** | Tables show "No Data" | Check `OPENAI_API_KEY`. Trends aggregation uses LLM. If key fails, it returns empty list or default defaults. |
| **Stats Don't Match** | KPI numbers verify differently | **Timezones.** The DB stores UTC. The UI/API converts to EST (`America/New_York`). Verify your local machine time vs server time. |
| **Migrations** | "Column rating not found" | Run `python migrate_db.py` manually. Ensure `DATABASE_URL` is set. |
| **Deployment** | App crashes on start | Check `Procfile`. It chains commands (`&&`). If migration fails, app won't start. |
| **Rate Limits** | "429 Too Many Requests" | Check `main.py`. The limit is strict (60/min) and in-memory (resets on restart). |

## 10) Where a New Developer Should Start

1.  **Read**: `app/main.py` (Architecture) and `app/services/analytics.py` (Data Model).
2.  **Run**: Start the server locally using `uvicorn app.main:app --reload`.
3.  **Task**:
    *   Open `localhost:8000/admin`.
    *   Review the "Trends" chart.
    *   **Safe Change:** Edit `app/static/admin/index.html` to change a button color or label. Refresh to see immediate effect.
4.  **Avoid**: Do not edit `migrate_db.py` or `data/` files without understanding the schema/RAG pipeline.
