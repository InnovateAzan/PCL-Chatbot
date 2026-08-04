from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.models.schemas import SourceReference
from backend.app.services.chatbot import PolicyChatbot
from backend.app.services.document_loader import DocumentLoader
from backend.app.services.retriever import PolicyRetriever
from backend.app.services.source_utils import (
    extract_document_number,
    normalize_source_title,
    source_dedup_key,
    source_document_key,
)


def test_policy_reference_notice_uses_clean_page_bullets():
    sources = [
        SourceReference(
            document_name="0038 - PCL - IT Asset Endpoint Management Policy.pdf",
            page_number=5,
            snippet="Do not display this excerpt.",
            chunk_id="chunk-1",
            similarity_score=0.91,
        ),
        SourceReference(
            document_name="0045 - PCL - Access Control & Identity Management Policy.pdf",
            page_number=3,
            snippet="Do not display this excerpt either.",
            chunk_id="chunk-2",
            similarity_score=0.88,
        ),
    ]

    notice = PolicyChatbot._build_policy_reference_notice(sources)

    assert notice == (
        "Sources:\n"
        "• 0038 - PCL - IT Asset & Endpoint Management Policy — Page 5\n"
        "• 0045 - PCL - Access Control & Identity Management Policy — Page 3"
    )
    assert "Do not display" not in notice
    assert "chunk-1" not in notice
    assert "0.91" not in notice


def test_policy_reference_notice_deduplicates_document_page_and_handles_missing_page():
    sources = [
        SourceReference(
            document_name="0038 - PCL - IT Asset Endpoint Management Policy.pdf",
            page_number=None,
            chunk_id="chunk-1",
        ),
        SourceReference(
            document_name="0038 - PCL - IT Asset Endpoint Management Policy.pdf",
            page_number=None,
            chunk_id="chunk-2",
        ),
    ]

    notice = PolicyChatbot._build_policy_reference_notice(sources)

    assert notice == (
        "Sources:\n"
        "• 0038 - PCL - IT Asset & Endpoint Management Policy — Page unavailable"
    )
    assert "Page not indexed" not in notice


def test_document_number_extraction_and_filename_normalization():
    document_name = "0038 - PCL - IT Asset Endpoint Management Policy.pdf"

    assert extract_document_number(document_name) == "0038"
    assert normalize_source_title(document_name) == (
        "0038 - PCL - IT Asset & Endpoint Management Policy"
    )
    assert extract_document_number("PCL - Legacy Policy.pdf") is None
    assert normalize_source_title("PCL - Legacy   Policy.pdf") == (
        "PCL - Legacy Policy"
    )


def test_retriever_deduplicates_by_document_name_and_page_number():
    retriever = PolicyRetriever.__new__(PolicyRetriever)
    duplicate_page_sources = [
        (
            0.9,
            SourceReference(
                document_name="0038 - PCL - IT Asset Endpoint Management Policy.pdf",
                page_number=5,
                snippet="first chunk",
            ),
        ),
        (
            0.8,
            SourceReference(
                document_name="0038 - PCL - IT Asset Endpoint Management Policy.pdf",
                page_number=5,
                snippet="second chunk from same page",
            ),
        ),
        (
            0.7,
            SourceReference(
                document_name="0038 - PCL - IT Asset Endpoint Management Policy.pdf",
                page_number=6,
                snippet="different page",
            ),
        ),
    ]

    sources = retriever._deduplicate_sources(
        duplicate_page_sources,
        limit=5,
    )

    assert [
        (source.document_name, source.page_number, source.snippet)
        for source in sources
    ] == [
        (
            "0038 - PCL - IT Asset Endpoint Management Policy.pdf",
            5,
            "first chunk",
        ),
        (
            "0038 - PCL - IT Asset Endpoint Management Policy.pdf",
            6,
            "different page",
        ),
    ]


def test_response_sources_group_same_document_pages_and_relevance():
    sources = [
        SourceReference(
            document_name="0041 - PCL - IT Hardware Procurement Policy.pdf",
            document_number="0041",
            page_number=2,
            relevance_score=0.91,
        ),
        SourceReference(
            document_name="IT Software & Hardware Procurement Flow.pdf",
            page_number=1,
            relevance_score=0.87,
        ),
        SourceReference(
            document_name="0041 - PCL - IT Hardware Procurement Policy.pdf",
            document_number="0041",
            page_number=1,
            relevance_score=0.96,
        ),
        SourceReference(
            document_name="0041 - PCL - IT Hardware Procurement Policy.pdf",
            document_number="0041",
            page_number=2,
            relevance_score=0.82,
        ),
    ]

    grouped = PolicyChatbot._group_sources_by_document(sources)

    assert [
        (
            source.document_number,
            source.title,
            source.pages,
            source.relevance_score,
        )
        for source in grouped
    ] == [
        (
            "0041",
            "PCL - IT Hardware Procurement Policy",
            [1, 2],
            0.96,
        ),
        (
            None,
            "IT Software & Hardware Procurement Flow",
            [1],
            0.87,
        ),
    ]


def test_response_source_grouping_uses_normalized_title_without_document_number():
    sources = [
        SourceReference(
            document_name="IT Software & Hardware Procurement Flow.pdf",
            page_number=2,
        ),
        SourceReference(
            document_name="IT Software & Hardware Procurement Flow.pdf",
            page_number=1,
        ),
    ]

    grouped = PolicyChatbot._group_sources_by_document(sources)

    assert len(grouped) == 1
    assert grouped[0].document_number is None
    assert grouped[0].title == "IT Software & Hardware Procurement Flow"
    assert grouped[0].pages == [1, 2]
    assert source_document_key(
        document_name="IT Software & Hardware Procurement Flow.pdf",
        document_number=None,
    ) == "it software & hardware procurement flow"


def test_response_source_pages_sort_numerically():
    grouped = PolicyChatbot._group_sources_by_document(
        [
            SourceReference(
                document_name="0041 - PCL - IT Hardware Procurement Policy.pdf",
                document_number="0041",
                page_number=10,
            ),
            SourceReference(
                document_name="0041 - PCL - IT Hardware Procurement Policy.pdf",
                document_number="0041",
                page_number=1,
            ),
            SourceReference(
                document_name="0041 - PCL - IT Hardware Procurement Policy.pdf",
                document_number="0041",
                page_number=2,
            ),
        ]
    )

    assert grouped[0].pages == [1, 2, 10]


def test_source_notice_groups_pages_with_singular_and_plural_wording():
    notice = PolicyChatbot._build_policy_reference_notice(
        [
            SourceReference(
                document_name="0041 - PCL - IT Hardware Procurement Policy.pdf",
                document_number="0041",
                page_number=2,
            ),
            SourceReference(
                document_name="0041 - PCL - IT Hardware Procurement Policy.pdf",
                document_number="0041",
                page_number=1,
            ),
            SourceReference(
                document_name="IT Software & Hardware Procurement Flow.pdf",
                page_number=1,
            ),
        ]
    )

    assert notice == (
        "Sources:\n"
        "• 0041 - PCL - IT Hardware Procurement Policy — Pages 1, 2\n"
        "• IT Software & Hardware Procurement Flow — Page 1"
    )
    assert "Page 1,2" not in notice


def test_source_notice_limits_to_top_three_retrieval_order():
    sources = [
        SourceReference(
            document_name=f"00{number} - PCL - Policy {number}.pdf",
            page_number=number,
        )
        for number in range(1, 5)
    ]

    notice = PolicyChatbot._build_policy_reference_notice(sources)

    assert notice.count("\n• ") == 3
    assert "Policy 4" not in notice


def test_source_dedup_key_uses_document_number_then_page():
    assert source_dedup_key(
        document_name="0038 - PCL - IT Asset Endpoint Management Policy.pdf",
        document_number="0038",
        page_number=3,
    ) == ("0038", 3)
    assert source_dedup_key(
        document_name="PCL - Legacy Policy.pdf",
        document_number=None,
        page_number=None,
    ) == ("pcl - legacy policy", None)


def test_pdf_page_numbers_are_preserved(tmp_path):
    fitz = pytest.importorskip("fitz")
    pdf_path = tmp_path / "0038 - PCL - IT Asset Endpoint Management Policy.pdf"
    document = fitz.open()

    for page_number in range(1, 3):
        page = document.new_page()
        page.insert_text(
            (72, 72),
            f"Policy page {page_number} text for indexing.",
        )

    document.save(str(pdf_path))
    document.close()

    pages = DocumentLoader()._load_pdf_pages(pdf_path)

    assert [page.page_number for page in pages] == [1, 2]
    assert all(
        page.to_metadata()["document_name"] == pdf_path.name
        for page in pages
    )


def test_pdf_ocr_page_numbers_are_preserved(tmp_path, monkeypatch):
    fitz = pytest.importorskip("fitz")
    pdf_path = tmp_path / "0038 - PCL - IT Asset Endpoint Management Policy.pdf"
    document = fitz.open()
    document.new_page()
    document.new_page()
    document.save(str(pdf_path))
    document.close()

    loader = DocumentLoader()
    monkeypatch.setattr(loader, "_needs_ocr", lambda text: True)
    monkeypatch.setattr(
        loader,
        "_ocr_pdf_page",
        lambda page: f"OCR text page {page.number + 1}",
    )

    pages = loader._load_pdf_pages(pdf_path)

    assert [page.page_number for page in pages] == [1, 2]
    assert [page.extraction_method for page in pages] == ["ocr", "ocr"]


def test_structured_source_response_excludes_internal_fields():
    source = SourceReference(
        document_name="0038 - PCL - IT Asset Endpoint Management Policy.pdf",
        document_number="0038",
        title="PCL - IT Asset & Endpoint Management Policy",
        display_title="0038 - PCL - IT Asset & Endpoint Management Policy",
        page_number=3,
        relevance_score=0.91,
        snippet="Internal chunk text",
        chunk_id="internal-id",
        similarity_score=0.91,
    )

    payload = source.model_dump()

    assert payload["document_number"] == "0038"
    assert payload["display_title"] == (
        "0038 - PCL - IT Asset & Endpoint Management Policy"
    )
    assert payload["pages"] == [3]
    assert "page" not in payload
    assert "page_number" not in payload
    assert payload["relevance_score"] == 0.91
    assert "snippet" not in payload
    assert "chunk_id" not in payload
    assert "similarity_score" not in payload


def test_frontend_source_rendering_uses_unordered_list():
    app_js = Path("frontend/app.js").read_text(encoding="utf-8")

    assert 'document.createElement("ul")' in app_js
    assert 'list.className = "sources-list"' in app_js
    assert "Pages ${uniquePages.join(\", \")}" in app_js
    assert "join(\"; \")" not in app_js
    assert "Page 1,2" not in app_js
    assert "Page not indexed" not in app_js


def test_general_fallback_has_no_policy_sources():
    chatbot = PolicyChatbot(retriever=None)
    chatbot.gemini_client = None

    response = chatbot._build_general_response(
        "What is SharePoint?"
    )

    assert response.sources == []


def test_answer_source_selection_excludes_irrelevant_context_pages():
    chatbot = PolicyChatbot(retriever=None)
    sources = [
        SourceReference(
            document_name="0038 - PCL - IT Asset Endpoint Management Policy.pdf",
            document_number="0038",
            page_number=3,
            snippet=(
                "Personal laptops and external drives shall not be "
                "permitted to connect to the PCL network."
            ),
            relevance_score=0.9,
        ),
        SourceReference(
            document_name="0038 - PCL - IT Asset Endpoint Management Policy.pdf",
            document_number="0038",
            page_number=1,
            snippet="Objective scope applicability governance standards.",
            relevance_score=0.8,
        ),
        SourceReference(
            document_name="0041 - PCL - IT Hardware Procurement Policy.pdf",
            document_number="0041",
            page_number=1,
            snippet="Hardware must be procured after IT approval.",
            relevance_score=0.7,
        ),
    ]

    selected = chatbot._select_answer_sources(
        sources=sources,
        answer=(
            "Personal laptops and external drives are not permitted "
            "to connect to the PCL network."
        ),
    )

    assert [(source.document_number, source.page_number) for source in selected] == [
        ("0038", 3)
    ]


def test_laptop_expiry_question_gets_policy_lifecycle_interpretation():
    interpreted = PolicyChatbot._interpreted_policy_question(
        "When is the laptop expiry date?"
    )

    assert interpreted is not None
    assert "lifecycle" in interpreted
    assert "calendar date" in interpreted


def test_laptop_expiry_context_prefers_lifecycle_chunks():
    chatbot = PolicyChatbot(retriever=None)
    sources = [
        SourceReference(
            document_name="0038 - PCL - IT Asset Endpoint Management Policy.pdf",
            document_number="0038",
            page_number=3,
            snippet="The lifecycle of Tier 1 laptops shall be four years.",
        ),
        SourceReference(
            document_name="0038 - PCL - IT Asset Endpoint Management Policy.pdf",
            document_number="0038",
            page_number=4,
            snippet="End-of-life devices shall be securely wiped.",
        ),
    ]

    selected = chatbot._select_policy_context_sources(
        message="When is the laptop expiry date?",
        sources=sources,
    )

    assert [(source.document_number, source.page_number) for source in selected] == [
        ("0038", 3)
    ]


def test_malformed_bullet_closing_tag_is_repaired():
    cleaned = PolicyChatbot._clean_ai_formatting(
        "[BULLET]End-of-life devices are disposed.[/BULplet]"
    )

    assert cleaned == (
        "[BULLET]End-of-life devices are disposed.[/BULLET]"
    )


def test_rto_rpo_direct_policy_answer_uses_retrieved_chunk_without_gemini():
    chatbot = PolicyChatbot(retriever=None)
    answer = chatbot._try_direct_policy_answer(
        message=(
            "What do RTO and RPO stand for, and how often should "
            "disaster recovery procedures be tested?"
        ),
        sources=[
            SourceReference(
                document_name="0046 - PCL - Backup & Disaster Recovery Policy.pdf",
                document_number="0046",
                page_number=1,
                snippet=(
                    "RTO Recovery Time Objective RPO Recovery Point Objective "
                    "Disaster recovery procedures shall be tested annually "
                    "to validate system resilience by ICT team."
                ),
            )
        ],
    )

    assert answer == (
        "RTO = Recovery Time Objective\n\n"
        "RPO = Recovery Point Objective\n\n"
        "Disaster recovery procedures shall be tested annually to validate "
        "system resilience by ICT team"
    )


def test_rto_rpo_policy_intent_prefers_backup_disaster_recovery_policy():
    retriever = PolicyRetriever.__new__(PolicyRetriever)
    query = "what do rto and rpo stand for"
    backup_score = retriever._policy_intent_score(
        query,
        "0046 - PCL - Backup & Disaster Recovery Policy.pdf",
        "RTO Recovery Time Objective RPO Recovery Point Objective",
    )
    appendix_score = retriever._policy_intent_score(
        query,
        "Appendix B - IT Security Assessment Checklist.pdf",
        "RTO Recovery Time Objective RPO Recovery Point Objective",
    )

    assert backup_score > appendix_score


def test_rto_rpo_chatbot_answer_does_not_call_gemini_when_policy_chunk_exists():
    class FakeRetriever:
        def search(self, message):
            return [
                SourceReference(
                    document_name="0046 - PCL - Backup & Disaster Recovery Policy.pdf",
                    document_number="0046",
                    page_number=1,
                    snippet=(
                        "RTO Recovery Time Objective RPO Recovery Point "
                        "Objective Disaster recovery procedures shall be "
                        "tested annually to validate system resilience by ICT "
                        "team."
                    ),
                    relevance_score=0.8,
                )
            ]

    class FailingGeminiClient:
        pass

    chatbot = PolicyChatbot(retriever=FakeRetriever())
    chatbot.gemini_client = FailingGeminiClient()

    response = chatbot.answer(
        "What do RTO and RPO stand for?"
    )

    assert response.provider == "policy-rules"
    assert response.sources[0].document_number == "0046"
    assert response.sources[0].page_number == 1
    assert "Sources: Gemini general knowledge" not in (
        response.notice or ""
    )


def test_section_aware_chunking_detects_numbered_page_sections():
    retriever = PolicyRetriever.__new__(PolicyRetriever)

    sections = retriever._split_page_into_sections(
        """
        6. Hardware Procurement Workflow
        Business submits requirement justification to IT.
        IT performs technical and cybersecurity assessment.

        7. Security and Compliance
        All devices shall comply with security baselines.
        """
    )

    assert [
        (
            section.section_number,
            section.section_title,
        )
        for section in sections
    ] == [
        (
            "6",
            "Hardware Procurement Workflow",
        ),
        (
            "7",
            "Security and Compliance",
        ),
    ]


def test_chunks_keep_document_page_and_section_metadata():
    retriever = PolicyRetriever.__new__(PolicyRetriever)
    retriever.chunk_size = 260
    retriever.chunk_overlap = 40

    chunks = retriever._create_chunks(
        document_name=(
            "0041 - PCL - IT Hardware Procurement Policy.pdf"
        ),
        file_path="policies/0041 - PCL - IT Hardware Procurement Policy.pdf",
        file_hash="hash",
        extracted_text=(
            "[Page 2 | text]\n"
            "6. Hardware Procurement Workflow\n"
            "Business submits requirement justification to IT.\n"
            "IT performs technical and cybersecurity assessment.\n"
        ),
    )

    assert chunks

    for chunk in chunks:
        assert chunk.document_name == (
            "0041 - PCL - IT Hardware Procurement Policy.pdf"
        )
        assert chunk.document_number == "0041"
        assert chunk.normalized_title == (
            "PCL - IT Hardware Procurement Policy"
        )
        assert chunk.page_number == 2
        assert chunk.section_number == "6"
        assert chunk.section_title == (
            "Hardware Procurement Workflow"
        )
        assert chunk.source_type == "pdf"


def test_section_aware_chunking_does_not_merge_pages():
    retriever = PolicyRetriever.__new__(PolicyRetriever)
    retriever.chunk_size = 260
    retriever.chunk_overlap = 40

    chunks = retriever._create_chunks(
        document_name="0046 - PCL - Backup & Disaster Recovery Policy.pdf",
        file_path="policies/0046 - PCL - Backup & Disaster Recovery Policy.pdf",
        file_hash="hash",
        extracted_text=(
            "[Page 1 | text]\n"
            "1. Objective\n"
            "RTO means Recovery Time Objective.\n"
            "[Page 2 | ocr]\n"
            "2. Testing\n"
            "Disaster recovery procedures shall be tested annually.\n"
        ),
    )

    assert {
        chunk.page_number
        for chunk in chunks
    } == {1, 2}

    page_one_sections = {
        chunk.section_number
        for chunk in chunks
        if chunk.page_number == 1
    }
    page_two_sections = {
        chunk.section_number
        for chunk in chunks
        if chunk.page_number == 2
    }

    assert page_one_sections == {"1"}
    assert page_two_sections == {"2"}
