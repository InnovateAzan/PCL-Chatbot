from pathlib import Path

import pytest
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.routes import chat as chat_route
from backend.app.models.schemas import ChatRequest, ChatResponse


def test_sharepoint_debug_iframe_and_frontend_assets_use_current_version():
    app_js = Path("frontend/app.js").read_text(encoding="utf-8")
    embed_html = Path("frontend/embed.html").read_text(encoding="utf-8")
    index_html = Path("frontend/index.html").read_text(encoding="utf-8")
    customizer = Path(
        "sharepoint-spfx/src/extensions/pclGpt/PclGptApplicationCustomizer.ts"
    ).read_text(encoding="utf-8")
    serve_json = Path("sharepoint-spfx/config/serve.json").read_text(encoding="utf-8")

    assert 'window.ONEASSIST_BUILD_VERSION = "2026-08-05-v3";' in app_js
    assert "OneDesk Assistant frontend version:" in app_js
    assert 'const WIDGET_VERSION = "20260805-3";' in customizer
    assert '"chatbotUrl": "http://127.0.0.1:5500/embed.html"' in serve_json
    assert "style.css?v=20260805-3" in embed_html
    assert "app.js?v=20260805-3" in embed_html
    assert "style.css?v=20260805-3" in index_html
    assert "app.js?v=20260805-3" in index_html


def test_removed_footer_text_is_not_present_in_frontend():
    frontend_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("frontend").glob("*.html")
    )

    assert "By using this AI assistant" not in frontend_text
    assert "read more" not in frontend_text
    assert (
        "One Assistant can make mistakes. Workspace data isn't used to train models."
        in frontend_text
    )


def test_best_effort_database_save_failure_does_not_make_chat_500(monkeypatch):
    def fail_persist(**kwargs):
        raise SQLAlchemyError("database unavailable")

    class FakeDb:
        def rollback(self):
            return None

    monkeypatch.setattr(chat_route, "persist_chat_best_effort", fail_persist)

    response = chat_route._persist_response_to_existing_db(
        db=FakeDb(),
        payload=ChatRequest(message="hi"),
        response=ChatResponse(
            answer="hello",
            provider="local-greeting",
        ),
        response_time_ms=1,
    )

    assert response.answer == "hello"
    assert response.provider == "local-greeting"
