from __future__ import annotations

import hashlib
import json
import re
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import chromadb
except ImportError:
    chromadb = None

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

from backend.app.models.schemas import SourceReference
from backend.app.services.document_loader import DocumentLoader


@dataclass
class PolicyChunk:
    """One searchable section of a policy document."""

    chunk_id: str
    document_name: str
    file_path: str
    file_hash: str
    page_number: int | None
    section: str | None
    text: str
    chunk_index: int


class PolicyRetriever:
    """
    Pakistan Cables policy retriever.

    Flow:
        policies folder
        -> DocumentLoader
        -> OCR when required
        -> text chunking
        -> local SentenceTransformer embeddings
        -> persistent ChromaDB
        -> semantic and filename retrieval
    """

    COLLECTION_NAME = "pakistan_cables_policies"
    INDEX_FORMAT_VERSION = 2

    PAGE_PATTERN = re.compile(
        r"\[Page\s+(\d+)(?:\s*\|\s*[^\]]+)?\]",
        flags=re.IGNORECASE,
    )

    SECTION_PATTERN = re.compile(
        r"^(?:"
        r"\d+(?:\.\d+)*[.)]?\s+"
        r"|[A-Z][A-Z\s&/\-]{4,}"
        r")"
    )

    def __init__(
        self,
        policies_folder: str | Path | None = None,
        chroma_folder: str | Path | None = None,
        model_name: str = "all-MiniLM-L6-v2",
        chunk_size: int = 900,
        chunk_overlap: int = 150,
        top_k: int = 5,
        auto_index: bool = True,
    ) -> None:
        if chromadb is None:
            raise RuntimeError(
                "chromadb is not installed. "
                "Run: pip install chromadb"
            )

        if SentenceTransformer is None:
            raise RuntimeError(
                "sentence-transformers is not installed. "
                "Run: pip install sentence-transformers"
            )

        self.project_root = Path(__file__).resolve().parents[3]

        self.policies_folder = Path(
            policies_folder
            or self.project_root / "policies"
        ).resolve()

        self.chroma_folder = Path(
            chroma_folder
            or self.project_root / "backend" / "data" / "chroma"
        ).resolve()

        self.manifest_path = (
            self.chroma_folder / "policy_index_manifest.json"
        )

        self.model_name = model_name
        self.chunk_size = max(chunk_size, 300)
        self.chunk_overlap = max(
            0,
            min(chunk_overlap, self.chunk_size // 2),
        )
        self.top_k = max(top_k, 1)

        self.chroma_folder.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.loader = DocumentLoader(
            tesseract_path=(
                r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            ),
            ocr_language="eng",
            use_tika_fallback=True,
        )

        print(
            f"Loading embedding model: {self.model_name}"
        )

        self.embedding_model = SentenceTransformer(
            self.model_name
        )

        self.chroma_client = chromadb.PersistentClient(
            path=str(self.chroma_folder)
        )

        self.collection = (
            self.chroma_client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={
                    "description": (
                        "Pakistan Cables policy and manual documents"
                    ),
                    "hnsw:space": "cosine",
                },
            )
        )

        if auto_index:
            try:
                self.sync_index()
            except Exception as error:
                print(
                    "\n"
                    "================ POLICY INDEX ERROR ================\n"
                    f"{type(error).__name__}: {error}"
                )
                traceback.print_exc()
                print(
                    "====================================================\n"
                )

    # =========================================================
    # Public methods
    # =========================================================

    def search(
        self,
        query: str,
        limit: int | None = None,
    ) -> list[SourceReference]:
        """
        Search policies using semantic similarity plus filename matching.
        """

        normalized_query = self._normalize_text(query)

        if not normalized_query:
            return []

        result_limit = limit or self.top_k

        if self.collection.count() == 0:
            print(
                "Policy index is empty. Running indexing now."
            )
            self.sync_index()

        if self.collection.count() == 0:
            return []

        query_embedding = self._encode_texts(
            [normalized_query]
        )[0]

        fetch_count = min(
            max(result_limit * 4, 10),
            max(self.collection.count(), 1),
        )

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=fetch_count,
            include=[
                "documents",
                "metadatas",
                "distances",
            ],
        )

        documents = self._first_result_list(
            results.get("documents")
        )
        ids = self._first_result_list(
            results.get("ids")
        )
        metadatas = self._first_result_list(
            results.get("metadatas")
        )
        distances = self._first_result_list(
            results.get("distances")
        )

        ranked_results: list[
            tuple[float, SourceReference]
        ] = []

        for index, document_text in enumerate(documents):
            if not document_text:
                continue

            metadata = (
                metadatas[index]
                if index < len(metadatas)
                and isinstance(metadatas[index], dict)
                else {}
            )

            distance = (
                float(distances[index])
                if index < len(distances)
                and distances[index] is not None
                else 1.0
            )

            semantic_score = max(
                0.0,
                min(1.0, 1.0 - distance),
            )

            document_name = str(
                metadata.get(
                    "document_name",
                    "Unknown document",
                )
            )

            filename_score = self._filename_match_score(
                normalized_query,
                document_name,
            )

            keyword_score = self._keyword_match_score(
                normalized_query,
                document_text,
            )
            policy_intent_score = self._policy_intent_score(
                normalized_query,
                document_name,
                document_text,
            )

            final_score = (
                semantic_score * 0.45
                + filename_score * 0.20
                + keyword_score * 0.10
                + policy_intent_score * 0.25
            )

            # Avoid irrelevant generic matches.
            if (
                final_score < 0.20
                and filename_score < 0.45
            ):
                continue

            page_number = self._safe_int(
                metadata.get("page_number")
            )

            section = str(
                metadata.get("section") or ""
            ).strip() or None

            source = SourceReference(
                document_name=document_name,
                section=section,
                page_number=page_number,
                snippet=self._make_snippet(
                    document_text,
                    normalized_query,
                ),
                chunk_id=(
                    str(ids[index])
                    if index < len(ids)
                    and ids[index] is not None
                    else None
                ),
                similarity_score=round(final_score, 4),
            )

            ranked_results.append(
                (final_score, source)
            )

        ranked_results.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        return self._deduplicate_sources(
            ranked_results,
            limit=result_limit,
        )

    def sync_index(
        self,
        force: bool = False,
    ) -> dict[str, int]:
        """
        Incrementally synchronize the policies folder with ChromaDB.

        - New file: index
        - Modified file: remove old chunks and re-index
        - Deleted file: remove its chunks
        - Unchanged file: skip
        """

        if not self.policies_folder.exists():
            raise FileNotFoundError(
                f"Policies folder not found: "
                f"{self.policies_folder}"
            )

        manifest = self._load_manifest()
        current_files = self._current_policy_files()

        indexed_count = 0
        skipped_count = 0
        failed_count = 0
        deleted_count = 0
        chunk_count = 0

        current_paths = {
            str(path.resolve())
            for path in current_files
        }

        # Remove deleted documents from Chroma.
        for old_path in list(manifest.keys()):
            if old_path not in current_paths:
                self._delete_document_chunks(old_path)
                manifest.pop(old_path, None)
                deleted_count += 1

        for file_path in current_files:
            absolute_path = str(file_path.resolve())
            file_hash = self._calculate_file_hash(
                file_path
            )

            previous_hash = (
                manifest.get(absolute_path, {})
                .get("file_hash")
            )
            previous_index_version = (
                manifest.get(absolute_path, {})
                .get("index_format_version")
            )

            if (
                not force
                and previous_hash == file_hash
                and previous_index_version
                == self.INDEX_FORMAT_VERSION
            ):
                skipped_count += 1
                continue

            print(
                f"Indexing policy: {file_path.name}"
            )

            # Remove old chunks before re-indexing.
            self._delete_document_chunks(
                absolute_path
            )

            loaded_document = self.loader.load(
                file_path
            )

            if loaded_document.status != "success":
                failed_count += 1

                print(
                    f"Failed to load {file_path.name}: "
                    f"{loaded_document.error}"
                )
                continue

            chunks = self._create_chunks(
                document_name=loaded_document.file_name,
                file_path=absolute_path,
                file_hash=file_hash,
                extracted_text=loaded_document.text,
            )

            if not chunks:
                failed_count += 1
                print(
                    f"No chunks created for "
                    f"{file_path.name}"
                )
                continue

            self._save_chunks(chunks)

            manifest[absolute_path] = {
                "file_hash": file_hash,
                "document_name": (
                    loaded_document.file_name
                ),
                "index_format_version": (
                    self.INDEX_FORMAT_VERSION
                ),
                "chunk_count": len(chunks),
            }

            indexed_count += 1
            chunk_count += len(chunks)

        self._save_manifest(manifest)

        summary = {
            "indexed": indexed_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "deleted": deleted_count,
            "chunks_created": chunk_count,
            "total_chunks": self.collection.count(),
        }

        print("\nPolicy indexing completed.")
        print(
            f"Indexed: {summary['indexed']}"
        )
        print(
            f"Skipped: {summary['skipped']}"
        )
        print(
            f"Failed: {summary['failed']}"
        )
        print(
            f"Deleted: {summary['deleted']}"
        )
        print(
            f"New chunks: {summary['chunks_created']}"
        )
        print(
            f"Total Chroma chunks: "
            f"{summary['total_chunks']}"
        )

        return summary

    def rebuild_index(self) -> dict[str, int]:
        """Delete the complete collection and rebuild it."""

        try:
            self.chroma_client.delete_collection(
                name=self.COLLECTION_NAME
            )
        except Exception:
            pass

        self.collection = (
            self.chroma_client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={
                    "description": (
                        "Pakistan Cables policy and manual documents"
                    ),
                    "hnsw:space": "cosine",
                },
            )
        )

        if self.manifest_path.exists():
            self.manifest_path.unlink()

        return self.sync_index(force=True)

    def index_status(self) -> dict[str, Any]:
        """Return current index information."""

        manifest = self._load_manifest()

        return {
            "policies_folder": str(
                self.policies_folder
            ),
            "chroma_folder": str(
                self.chroma_folder
            ),
            "collection": self.COLLECTION_NAME,
            "embedding_model": self.model_name,
            "indexed_documents": len(manifest),
            "total_chunks": self.collection.count(),
        }

    # =========================================================
    # Chunking
    # =========================================================

    def _create_chunks(
        self,
        document_name: str,
        file_path: str,
        file_hash: str,
        extracted_text: str,
    ) -> list[PolicyChunk]:
        page_sections = self._split_by_page(
            extracted_text
        )

        chunks: list[PolicyChunk] = []
        chunk_index = 0

        normalized_title = self._normalize_filename(
            document_name
        )

        for page_number, page_text in page_sections:
            page_chunks = self._chunk_text(
                page_text
            )

            current_section: str | None = None

            for chunk_text in page_chunks:
                detected_section = (
                    self._detect_section(chunk_text)
                )

                if detected_section:
                    current_section = detected_section

                # Add document title to every chunk.
                searchable_text = (
                    f"Document title: {normalized_title}\n"
                    f"File name: {document_name}\n"
                    f"{chunk_text}"
                )

                chunk_id = self._build_chunk_id(
                    file_path=file_path,
                    file_hash=file_hash,
                    chunk_index=chunk_index,
                )

                chunks.append(
                    PolicyChunk(
                        chunk_id=chunk_id,
                        document_name=document_name,
                        file_path=file_path,
                        file_hash=file_hash,
                        page_number=page_number,
                        section=current_section,
                        text=searchable_text,
                        chunk_index=chunk_index,
                    )
                )

                chunk_index += 1

        return chunks

    def _split_by_page(
        self,
        text: str,
    ) -> list[tuple[int | None, str]]:
        matches = list(
            self.PAGE_PATTERN.finditer(text)
        )

        if not matches:
            return [(None, text.strip())]

        pages: list[tuple[int | None, str]] = []

        for index, match in enumerate(matches):
            start = match.end()

            end = (
                matches[index + 1].start()
                if index + 1 < len(matches)
                else len(text)
            )

            page_number = self._safe_int(
                match.group(1)
            )

            page_text = text[start:end].strip()

            if page_text:
                pages.append(
                    (page_number, page_text)
                )

        return pages or [(None, text.strip())]

    def _chunk_text(
        self,
        text: str,
    ) -> list[str]:
        cleaned_text = self._clean_text(text)

        if not cleaned_text:
            return []

        paragraphs = [
            paragraph.strip()
            for paragraph in re.split(
                r"\n\s*\n",
                cleaned_text,
            )
            if paragraph.strip()
        ]

        chunks: list[str] = []
        current_chunk = ""

        for paragraph in paragraphs:
            if len(paragraph) > self.chunk_size:
                if current_chunk:
                    chunks.append(
                        current_chunk.strip()
                    )
                    current_chunk = ""

                chunks.extend(
                    self._split_large_paragraph(
                        paragraph
                    )
                )
                continue

            candidate = (
                f"{current_chunk}\n\n{paragraph}"
                if current_chunk
                else paragraph
            )

            if len(candidate) <= self.chunk_size:
                current_chunk = candidate
                continue

            if current_chunk:
                chunks.append(
                    current_chunk.strip()
                )

            overlap = self._take_overlap(
                current_chunk
            )

            current_chunk = (
                f"{overlap}\n\n{paragraph}".strip()
                if overlap
                else paragraph
            )

        if current_chunk:
            chunks.append(
                current_chunk.strip()
            )

        return [
            chunk
            for chunk in chunks
            if len(chunk.strip()) >= 20
        ]

    def _split_large_paragraph(
        self,
        paragraph: str,
    ) -> list[str]:
        chunks: list[str] = []
        start = 0
        text_length = len(paragraph)

        while start < text_length:
            end = min(
                start + self.chunk_size,
                text_length,
            )

            if end < text_length:
                preferred_end = paragraph.rfind(
                    " ",
                    start,
                    end,
                )

                if preferred_end > start + 200:
                    end = preferred_end

            chunk = paragraph[start:end].strip()

            if chunk:
                chunks.append(chunk)

            if end >= text_length:
                break

            start = max(
                end - self.chunk_overlap,
                start + 1,
            )

        return chunks

    def _take_overlap(
        self,
        text: str,
    ) -> str:
        if not text or self.chunk_overlap <= 0:
            return ""

        overlap = text[-self.chunk_overlap:]

        first_space = overlap.find(" ")

        if first_space >= 0:
            overlap = overlap[first_space + 1:]

        return overlap.strip()

    # =========================================================
    # Embeddings and Chroma
    # =========================================================

    def _save_chunks(
        self,
        chunks: list[PolicyChunk],
    ) -> None:
        if not chunks:
            return

        batch_size = 32

        for start in range(
            0,
            len(chunks),
            batch_size,
        ):
            batch = chunks[
                start:start + batch_size
            ]

            documents = [
                chunk.text
                for chunk in batch
            ]

            embeddings = self._encode_texts(
                documents
            )

            ids = [
                chunk.chunk_id
                for chunk in batch
            ]

            metadatas = [
                {
                    "document_name": (
                        chunk.document_name
                    ),
                    "file_path": chunk.file_path,
                    "file_hash": chunk.file_hash,
                    "page_number": (
                        chunk.page_number
                        if chunk.page_number is not None
                        else -1
                    ),
                    "section": (
                        chunk.section or ""
                    ),
                    "chunk_index": (
                        chunk.chunk_index
                    ),
                }
                for chunk in batch
            ]

            self.collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )

    def _encode_texts(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        embeddings = self.embedding_model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        if hasattr(embeddings, "tolist"):
            return embeddings.tolist()

        return [
            list(map(float, embedding))
            for embedding in embeddings
        ]

    def _delete_document_chunks(
        self,
        file_path: str,
    ) -> None:
        try:
            result = self.collection.get(
                where={
                    "file_path": file_path
                },
                include=[],
            )

            ids = result.get("ids") or []

            if ids:
                self.collection.delete(
                    ids=ids
                )

        except Exception as error:
            print(
                f"Could not remove existing chunks for "
                f"{file_path}: {error}"
            )

    # =========================================================
    # Ranking
    # =========================================================

    def _filename_match_score(
        self,
        query: str,
        document_name: str,
    ) -> float:
        normalized_name = self._normalize_filename(
            document_name
        )

        if not normalized_name:
            return 0.0

        if query == normalized_name:
            return 1.0

        if query in normalized_name:
            return 0.95

        if normalized_name in query:
            return 0.90

        query_words = set(query.split())
        name_words = set(
            normalized_name.split()
        )

        if not query_words or not name_words:
            return 0.0

        common_words = (
            query_words & name_words
        )

        return len(common_words) / max(
            len(query_words),
            len(name_words),
        )

    def _keyword_match_score(
        self,
        query: str,
        document: str,
    ) -> float:
        query_words = {
            word
            for word in query.split()
            if len(word) > 2
        }

        document_words = set(
            self._normalize_text(
                document
            ).split()
        )

        if not query_words:
            return 0.0

        matches = query_words & document_words

        return len(matches) / len(query_words)

    def _policy_intent_score(
        self,
        query: str,
        document_name: str,
        document: str,
    ) -> float:
        normalized_name = self._normalize_filename(document_name)
        normalized_document = self._normalize_text(document[:3000])

        endpoint_terms = {
            "laptop",
            "desktop",
            "endpoint",
            "asset",
            "device",
            "pool laptop",
        }

        if any(term in query for term in endpoint_terms):
            if "asset endpoint management" in normalized_name:
                return 1.0

            if (
                "tier 1 laptop" in normalized_document
                or "tier 2 laptop" in normalized_document
                or "pool laptop" in normalized_document
            ):
                return 0.9

            if "hardware procurement" in normalized_name:
                return 0.15

        procurement_terms = {
            "procurement",
            "purchase",
            "buy",
            "approval",
            "vendor",
        }

        if any(term in query for term in procurement_terms):
            if "hardware procurement" in normalized_name:
                return 1.0

        return 0.0

    def _make_snippet(
        self,
        text: str,
        query: str,
        maximum_length: int = 750,
    ) -> str:
        clean_text = re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

        if len(clean_text) <= maximum_length:
            return clean_text

        query_words = [
            word
            for word in query.split()
            if len(word) > 3
        ]

        lower_text = clean_text.lower()
        position = -1

        for word in query_words:
            position = lower_text.find(
                word.lower()
            )

            if position >= 0:
                break

        if position < 0:
            return (
                clean_text[:maximum_length]
                + "..."
            )

        start = max(
            position - maximum_length // 3,
            0,
        )

        end = min(
            start + maximum_length,
            len(clean_text),
        )

        snippet = clean_text[start:end]

        if start > 0:
            snippet = "..." + snippet

        if end < len(clean_text):
            snippet += "..."

        return snippet

    def _deduplicate_sources(
        self,
        ranked_results: list[
            tuple[float, SourceReference]
        ],
        limit: int,
    ) -> list[SourceReference]:
        sources: list[SourceReference] = []
        seen: set[tuple[str, int | None, str]] = set()

        for _, source in ranked_results:
            key = (
                source.document_name.lower(),
                source.page_number,
                source.snippet[:120].lower(),
            )

            if key in seen:
                continue

            seen.add(key)
            sources.append(source)

            if len(sources) >= limit:
                break

        return sources

    # =========================================================
    # Manifest and files
    # =========================================================

    def _current_policy_files(
        self,
    ) -> list[Path]:
        return list(
            self.loader.iter_files(
                self.policies_folder,
                recursive=True,
            )
        )

    def _calculate_file_hash(
        self,
        file_path: Path,
    ) -> str:
        digest = hashlib.sha256()

        with file_path.open("rb") as file:
            for block in iter(
                lambda: file.read(1024 * 1024),
                b"",
            ):
                digest.update(block)

        return digest.hexdigest()

    def _build_chunk_id(
        self,
        file_path: str,
        file_hash: str,
        chunk_index: int,
    ) -> str:
        raw_value = (
            f"{file_path}|{file_hash}|"
            f"{chunk_index}"
        )

        return hashlib.sha256(
            raw_value.encode("utf-8")
        ).hexdigest()

    def _load_manifest(
        self,
    ) -> dict[str, dict[str, Any]]:
        if not self.manifest_path.exists():
            return {}

        try:
            return json.loads(
                self.manifest_path.read_text(
                    encoding="utf-8"
                )
            )

        except Exception:
            return {}

    def _save_manifest(
        self,
        manifest: dict[str, dict[str, Any]],
    ) -> None:
        self.manifest_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.manifest_path.write_text(
            json.dumps(
                manifest,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    # =========================================================
    # Helpers
    # =========================================================

    def _detect_section(
        self,
        text: str,
    ) -> str | None:
        for line in text.splitlines():
            cleaned_line = line.strip()

            if not cleaned_line:
                continue

            if self.SECTION_PATTERN.match(
                cleaned_line
            ):
                return cleaned_line[:180]

            break

        return None

    @staticmethod
    def _normalize_filename(
        file_name: str,
    ) -> str:
        name = Path(file_name).stem

        name = re.sub(
            r"[_\-]+",
            " ",
            name,
        )

        name = re.sub(
            r"\s+",
            " ",
            name,
        )

        return name.lower().strip()

    @staticmethod
    def _normalize_text(
        value: str,
    ) -> str:
        value = value.lower()

        value = re.sub(
            r"[_\-]+",
            " ",
            value,
        )

        value = re.sub(
            r"[^a-z0-9\s]",
            " ",
            value,
        )

        value = re.sub(
            r"\s+",
            " ",
            value,
        )

        return value.strip()

    @staticmethod
    def _clean_text(
        value: str,
    ) -> str:
        value = value.replace(
            "\x00",
            " ",
        )

        value = re.sub(
            r"[ \t]+",
            " ",
            value,
        )

        value = re.sub(
            r"\n{3,}",
            "\n\n",
            value,
        )

        return value.strip()

    @staticmethod
    def _safe_int(
        value: Any,
    ) -> int | None:
        try:
            converted = int(value)

            if converted < 0:
                return None

            return converted

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _first_result_list(
        value: Any,
    ) -> list[Any]:
        if not value:
            return []

        if (
            isinstance(value, list)
            and value
            and isinstance(value[0], list)
        ):
            return value[0]

        if isinstance(value, list):
            return value

        return []


if __name__ == "__main__":
    retriever = PolicyRetriever(
        auto_index=False
    )

    print("\nRebuilding policy index...")

    summary = retriever.rebuild_index()

    print("\nIndex status:")
    print(
        json.dumps(
            retriever.index_status(),
            indent=2,
        )
    )

    print("\nTest search:")

    test_results = retriever.search(
        "Vendor and Third Party Risk Policy",
        limit=5,
    )

    for result in test_results:
        print(
            "\n"
            f"Document: {result.document_name}\n"
            f"Page: {result.page_number}\n"
            f"Section: {result.section}\n"
            f"Snippet: {result.snippet[:300]}"
        )
