from fastapi import APIRouter

from backend.app.core.config import get_settings
from backend.app.services.document_loader import PolicyDocumentLoader

router = APIRouter(tags=["policies"])


@router.get("/policies")
def list_policies() -> dict[str, list[dict[str, str]]]:
    loader = PolicyDocumentLoader(get_settings().policies_path)
    return {"items": loader.describe_policies()}


@router.post("/policies/reindex", status_code=202)
def reindex_policies() -> dict[str, str]:
    return {
        "message": "Reindex job placeholder created. Replace this with a real indexing pipeline.",
    }
