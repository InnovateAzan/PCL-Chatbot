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
   uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8001
   ```

6. Open [frontend/index.html](/D:/PROJECT/Chart%20Bot/frontend/index.html) in a browser or serve the `frontend` folder with a simple local static server.

## Gemini note

This project disables environment proxy variables for Gemini by default because
some local setups export placeholder proxy values that break outbound model
requests. If your network requires a real proxy, set `GEMINI_USE_ENV_PROXY=true`
in `.env`.

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
