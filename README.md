# HighLevel (GoHighLevel) <-> LINE OA Middleware Integration (FastAPI)

A high-performance, asynchronous Webhook Middleware and OAuth Token Management service bridging **LINE Official Account (LINE Messaging API v2)** and **HighLevel (GoHighLevel Conversations API v2)** built with **FastAPI (Python 3.11+)** and **SQLAlchemy 2.0 (Async Engine / asyncpg)**.

---

## 🛠 Tech Stack

- **Framework:** FastAPI (ASGI via Uvicorn) running on port 3000
- **Database & ORM:** PostgreSQL using **SQLAlchemy 2.0 (Async Engine)** with **asyncpg** (100% schema compatible with existing tables)
- **HTTP Client:** `httpx` (Async Client) for LINE Messaging API and GoHighLevel API
- **Data Validation:** Pydantic v2 & Pydantic-Settings
- **Concurrency & Resilience:** `asyncio.Lock()` Mutual Exclusion (Mutex) per `locationId` preventing Race Conditions during OAuth Token Refresh, with a 5-minute pre-expiration buffer
- **Logging & Tracing:** Structured JSON Logging (Pino-compatible) with automatic `traceId` (UUID v4) context propagation
- **Containerization:** Dockerfile (Python 3.11-slim) & `docker-compose.yml`

---

## 🚀 Data Pipelines

### 1. Inbound Pipeline (LINE -> HighLevel)
- LINE user sends a text message to LINE OA.
- LINE Messaging API posts webhook to `POST /api/webhooks/line`.
- Middleware verifies HMAC-SHA256 signature (`x-line-signature`) with constant-time equality check.
- **Fast Return:** Immediately responds `HTTP 200 {"status": "ok"}` and delegates processing to `BackgroundTasks`.
- In Background Task:
  - Caches `replyToken` with **60-second TTL** (In-Memory + PostgreSQL durability).
  - Checks contact mapping in `contact_mappings` table (`location_id` + `line_user_id`).
  - If not found: Searches HighLevel contact via Search API; if still not found, fetches user profile from LINE API, creates contact in HighLevel with custom field `line_user_id`, and creates mapping in DB.
  - Injects message into HighLevel Conversations API (`POST /conversations/messages/inbound`).

### 2. Outbound Pipeline (HighLevel -> LINE)
- Agent replies in HighLevel Conversation view.
- HighLevel posts outbound webhook to `POST /api/webhooks/highlevel/outbound`.
- **Echo Suppression:** Ignores inbound echo events or received status.
- Maps `contactId` to `line_user_id` from `contact_mappings`.
- Checks for valid `replyToken` (< 60s TTL):
  - **If valid:** Dispatches via **LINE Reply API** (`POST /v2/bot/message/reply`) to save Push quotas and immediately consumes token.
  - **If expired/missing or reply error:** Automatically falls back to **LINE Push API** (`POST /v2/bot/message/push`).

### 3. OAuth 2.0 Flow with Multi-Tier Fallback
- `GET /api/oauth/callback` receives OAuth authorization code from GoHighLevel.
- Exchanges code for `access_token` and `refresh_token`.
- Resolves `locationId` via 3-Tier Fallback:
  1. Response JSON Body
  2. Query Parameter
  3. JWT Claims decoded from `access_token`
- Upserts tokens in `hl_oauth_tokens`.

---

## 📦 Project Setup

### 1. Prerequisites
- Python 3.11+
- PostgreSQL database instance running locally or via Docker

### 2. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Update configuration parameters:
```env
PORT=3000
NODE_ENV=development
BASE_URL=http://localhost:3000

# HighLevel App Credentials
GHL_CLIENT_ID=your_ghl_client_id
GHL_CLIENT_SECRET=your_ghl_client_secret
GHL_REDIRECT_URI=http://localhost:3000/api/oauth/callback

# LINE OA Credentials
LINE_CHANNEL_ID=your_line_channel_id
LINE_CHANNEL_SECRET=your_line_channel_secret
LINE_CHANNEL_ACCESS_TOKEN=your_line_channel_access_token

# PostgreSQL Connection URL
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/line_ghl_poc?schema=public
```

### 3. Run Locally with Virtualenv
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload
```

### 4. Run with Docker Compose
```bash
docker-compose up --build -d
```

### 5. Run Automated Tests
```bash
pytest -v
```

---

## 🔗 Endpoints Summary

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service health status, uptime, and PostgreSQL connectivity check |
| `GET` | `/api/oauth/callback` | GoHighLevel OAuth 2.0 Authorization Callback |
| `GET` / `POST` | `/api/webhooks/line` | Inbound LINE Messaging API Webhook (Signature verified & non-blocking) |
| `GET` / `POST` | `/api/webhooks/highlevel/outbound` | Outbound HighLevel Provider Webhook (Echo-suppressed & Reply/Push routed) |

---

## 🔒 Security & Concurrency Highlights

1. **HMAC-SHA256 Verification:** Validates `x-line-signature` against raw request payload using `hmac.compare_digest` to eliminate timing attacks.
2. **Mutex Token Lock (`asyncio.Lock`):** Location-level mutual exclusion prevents race conditions and redundant refresh calls during OAuth access token renewals.
3. **5-Minute Auto-Refresh Buffer:** Proactively refreshes tokens 5 minutes prior to expiration.
4. **Non-Blocking Inbound Execution:** Fast return `HTTP 200` to LINE with `BackgroundTasks` execution ensures zero timeout issues from LINE's 1-second timeout expectation.
