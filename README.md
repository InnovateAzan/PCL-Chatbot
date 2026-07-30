# Pakistan Cables IT Policy Chatbot

This repository is a starter blueprint for a standalone chatbot that answers questions from Pakistan Cables IT policy documents and can later be embedded into One Desk SharePoint as a floating chat widget.

The current scaffold focuses on three things:

- a practical architecture that fits the requested RAG-based approach
- a starter FastAPI backend with chat and policy endpoints
- a simple frontend chat interface for local testing
- SharePoint-ready embed assets for One Desk integration

## What this project uses

- Frontend: HTML, CSS, JavaScript
- Backend: Python, FastAPI, Uvicorn
- AI generation: Gemini API through `google-genai`
- Embeddings: `sentence-transformers/all-MiniLM-L6-v2`
- Vector database: ChromaDB
- Document parsing: PyMuPDF, `python-docx`
- App database: SQLite for the first version
- Future integration: SharePoint SPFx Application Customizer

## Current status

This scaffold is intentionally safe to start with:

- the backend is wired and ready for Gemini and Chroma integration
- the chat endpoint currently returns demo answers and source references
- the frontend already talks to the backend and shows references
- the architecture for SharePoint integration is documented in [ARCHITECTURE.md](/D:/PROJECT/Chart%20Bot/ARCHITECTURE.md)

## Suggested folder structure

```text
backend/
  app/
    api/routes/
    core/
    models/
    services/
frontend/
policies/
```

## Local run

1. Create a virtual environment:

   ```powershell
   python -m venv .venv
   ```

2. Activate it:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

3. Install packages:

   ```powershell
   pip install -r requirements.txt
   ```

4. Copy the environment file:

   ```powershell
   Copy-Item .env.example .env
   ```

5. Start the API:

   ```powershell
   uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8085
   ```

6. Open [frontend/index.html](/D:/PROJECT/Chart%20Bot/frontend/index.html) in a browser or serve the `frontend` folder with a simple local static server.

## Gemini note

This project disables environment proxy variables for Gemini by default because
some local setups export placeholder proxy values that break outbound model
requests. If your network requires a real proxy, set `GEMINI_USE_ENV_PROXY=true`
in `.env`.

## PostgreSQL chat history

Set the PostgreSQL connection string in `.env`. Do not commit `.env`.

```env
DATABASE_URL=postgresql+psycopg2://appuser:YOUR_PASSWORD@10.4.3.78:5432/oneassist_db
```

The application maps to existing PostgreSQL tables and does not create,
truncate, or migrate them at startup.

Existing tables used:

- `users`
- `chat_sessions`
- `chat_messages`
- `message_sources`
- `feedback`
- `unanswered_questions`
- `documents`
- `document_chunks`
- `audit_logs`

Test the database connection:

```powershell
python scripts/test_postgres_connection.py
```

Start the backend:

```powershell
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8085
```

To verify records in pgAdmin after sending a chat message, run:

```sql
select * from users order by id desc limit 10;
select * from chat_sessions order by id desc limit 10;
select * from chat_messages order by id desc limit 20;
select * from message_sources order by id desc limit 20;
select * from unanswered_questions order by id desc limit 20;
```

If PostgreSQL is unavailable or a write fails, OneDesk Assistant logs the error
and still returns the chatbot answer.

## Temporary Cloudflare Quick Tunnel

Use this only for temporary testing from SharePoint. Do not commit real tunnel
URLs, Gemini keys, or database credentials.

1. Install Cloudflare Tunnel:

   ```powershell
   winget install --id Cloudflare.cloudflared
   ```

2. Open PowerShell terminal 1 and start FastAPI:

   ```powershell
   .\scripts\start-api.ps1
   ```

3. Open PowerShell terminal 2 and start a Quick Tunnel:

   ```powershell
   .\scripts\start-cloudflared-tunnel.ps1
   ```

4. Copy the generated `https://*.trycloudflare.com` URL.

5. In `.env`, set only the temporary public URL values:

   ```env
   TEMPORARY_TUNNEL_URL=https://YOUR-TUNNEL.trycloudflare.com
   PUBLIC_API_BASE_URL=https://YOUR-TUNNEL.trycloudflare.com/api
   ```

6. Restart FastAPI after editing `.env`.

7. Update [frontend/config.js](/D:/PROJECT/Chart%20Bot/frontend/config.js):

   ```javascript
   window.PCL_GPT_CONFIG = {
     ...(window.PCL_GPT_CONFIG || {}),
     apiBaseUrl: "https://YOUR-TUNNEL.trycloudflare.com/api",
   };
   ```

8. For SPFx debug, update `apiBaseUrl` in
   [sharepoint-spfx/config/serve.json](/D:/PROJECT/Chart%20Bot/sharepoint-spfx/config/serve.json)
   to the same `https://YOUR-TUNNEL.trycloudflare.com/api` value.

9. Test the public health endpoint:

   ```powershell
   Invoke-WebRequest https://YOUR-TUNNEL.trycloudflare.com/api/health
   ```

10. Run the SharePoint debug page with the existing SPFx local serve flow.

When the temporary test is finished, stop both PowerShell windows and remove the
tunnel URL from `.env`, `frontend/config.js`, and `sharepoint-spfx/config/serve.json`.

## SharePoint note

For One Desk integration, use:

- [frontend/embed.html](/D:/PROJECT/Chart%20Bot/frontend/embed.html)
- [frontend/sharepoint-loader.js](/D:/PROJECT/Chart%20Bot/frontend/sharepoint-loader.js)
- [SHAREPOINT_SETUP.md](/D:/PROJECT/Chart%20Bot/SHAREPOINT_SETUP.md)

SharePoint runs on `https`, so it cannot call `http://127.0.0.1:8001` directly.
For SharePoint preview or production, host both the frontend and backend on an
internal HTTPS URL first.

## Next implementation step

The next practical step is to replace the demo retriever in `backend/app/services/` with:

- real document extraction from `policies/`
- text chunking and embedding generation
- ChromaDB indexing
- Gemini answer generation using retrieved policy chunks only
