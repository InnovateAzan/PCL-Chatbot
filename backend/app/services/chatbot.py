from __future__ import annotations

import re
import traceback

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

from backend.app.core.config import get_settings
from backend.app.models.schemas import ChatResponse, SourceReference
from backend.app.services.retriever import PolicyRetriever


class PolicyChatbot:
    """Pakistan Cables policy chatbot with Gemini and general fallback."""

    POLICY_UNAVAILABLE_MESSAGE = (
        "Information not available in IT policies."
    )

    def __init__(
        self,
        retriever: PolicyRetriever | None = None,
    ) -> None:
        self.settings = get_settings()
        self.retriever = retriever
        self.gemini_client = self._build_gemini_client()

    def answer(
        self,
        message: str,
        user_display_name: str | None = None,
        preferred_name: str | None = None,
    ) -> ChatResponse:
        message = message.strip()

        if not message:
            return ChatResponse(
                answer="Please enter your question.",
                sources=[],
                fallback=True,
                provider="validation",
            )

        greeting_answer = self._handle_greeting(
            message,
            user_display_name=user_display_name,
            preferred_name=preferred_name,
        )

        if greeting_answer:
            return ChatResponse(
                answer=greeting_answer,
                sources=[],
                fallback=False,
                provider="local-greeting",
            )

        retriever = self._get_retriever()
        sources = self.retriever.search(message)

        if not sources:
            return self._build_general_response(message)

        policy_answer, policy_notice = self._try_gemini_answer(
            message=message,
            sources=sources,
        )

        if policy_answer:
            if self._is_policy_unavailable_answer(policy_answer):
                return self._build_general_response(message)

            return ChatResponse(
                answer=policy_answer,
                sources=sources,
                fallback=False,
                provider="gemini-policy",
                notice=self._build_policy_reference_notice(sources),
            )

        fallback_answer = self._build_policy_fallback_answer()

        return ChatResponse(
            answer=fallback_answer,
            sources=sources,
            fallback=True,
            provider="policy-rules",
            notice=(
                policy_notice
                or self._build_policy_reference_notice(sources)
            ),
        )

    def health_snapshot(self) -> dict[str, str | bool]:
        return {
            "llm_mode": (
                "gemini-configured"
                if self.gemini_client
                else "policy-fallback"
            ),
            "gemini_configured": bool(self.gemini_client),
            "retriever_ready": bool(self.retriever),
        }

    def _get_retriever(self) -> PolicyRetriever:
        if self.retriever is None:
            self.retriever = PolicyRetriever(
                auto_index=False
            )

        return self.retriever

    def _build_general_response(
        self,
        message: str,
    ) -> ChatResponse:
        answer, notice = self._try_general_gemini_answer(message)

        if answer:
            return ChatResponse(
                answer=answer,
                sources=[],
                fallback=False,
                provider="gemini-general",
                notice=notice,
            )

        return ChatResponse(
            answer=self.POLICY_UNAVAILABLE_MESSAGE,
            sources=[],
            fallback=True,
            provider="policy-rules",
            notice=notice,
        )

    def _build_gemini_client(self):
        if (
            genai is None
            or genai_types is None
            or not self.settings.gemini_api_key.strip()
        ):
            return None

        try:
            return genai.Client(
                api_key=self.settings.gemini_api_key,
                http_options=genai_types.HttpOptions(
                    client_args={
                        "trust_env": (
                            self.settings.gemini_use_env_proxy
                        )
                    }
                ),
            )

        except Exception as error:
            print(
                "\n"
                "================ GEMINI CLIENT ERROR ================\n"
            )
            print(type(error).__name__)
            print(str(error))
            traceback.print_exc()
            print(
                "=====================================================\n"
            )
            return None

    def _try_gemini_answer(
        self,
        message: str,
        sources: list[SourceReference],
    ) -> tuple[str | None, str | None]:
        if not self.gemini_client:
            return None, "Gemini is not configured."

        prompt = self._build_policy_prompt(
            message=message,
            sources=sources,
        )

        try:
            response = self.gemini_client.models.generate_content(
                model=self.settings.gemini_model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.15,
                    max_output_tokens=900,
                ),
            )

            answer = self._clean_ai_formatting(
                response.text or ""
            )

        except Exception as error:
            return self._handle_gemini_error(
                error=error,
                context="POLICY",
            )

        if not answer:
            return (
                None,
                "Gemini returned an empty policy response.",
            )

        return answer, None

    def _build_policy_prompt(
        self,
        message: str,
        sources: list[SourceReference],
    ) -> str:
        context_blocks: list[str] = []

        for source in sources:
            location = (
                source.section
                or "Section not provided"
            )

            page = (
                f"Page {source.page_number}"
                if source.page_number
                else "Page not provided"
            )

            snippet = (
                source.snippet
                or "No supporting excerpt provided."
            )

            context_blocks.append(
                f"Document: {source.document_name}\n"
                f"Location: {location}\n"
                f"{page}\n"
                f"Excerpt: {snippet}"
            )

        context = "\n\n".join(context_blocks)

        return (
            "You are Pakistan Cables OneDesk Assistant.\n"
            "Answer only from the policy context supplied below.\n"
            "Do not invent internal rules, limits, approvals, timelines, "
            "roles, controls, procedures or requirements.\n"
            "If the supplied context does not answer the question, reply "
            "exactly with this sentence:\n"
            f"{self.POLICY_UNAVAILABLE_MESSAGE}\n\n"

            "Required output format:\n"
            "- Start with one short introductory paragraph.\n"
            "- Use sections only when useful.\n"
            "- Write section headings exactly like this:\n"
            "[SECTION]Heading text[/SECTION]\n"
            "- Write every bullet exactly like this:\n"
            "[BULLET]Bullet text[/BULLET]\n"
            "- Put every section and bullet on its own separate line.\n"
            "- Never put two bullets on the same line.\n"
            "- Do not change the spelling or casing of SECTION or BULLET tags.\n"
            "- Always close every SECTION and BULLET tag.\n"
            "- Do not use Markdown headings such as #, ## or ###.\n"
            "- Do not use Markdown bold symbols such as **text**.\n"
            "- Do not use hyphen or asterisk bullets.\n"
            "- Do not use tables.\n"
            "- Keep each bullet concise and readable.\n"
            "- Do not repeat document names or page numbers because the "
            "application displays sources separately.\n\n"

            "Accuracy rules:\n"
            "- Include only information found in the supplied context.\n"
            "- Do not add general industry practices to policy answers.\n"
            "- Do not add a requirement that is absent from the context.\n"
            "- Do not guess missing policy information.\n\n"

            "Correct output example:\n"
            "Vendor agreements must contain controls that protect company "
            "information and define vendor responsibilities.\n\n"
            "[SECTION]Required Contractual Clauses[/SECTION]\n"
            "[BULLET]Data protection clauses[/BULLET]\n"
            "[BULLET]Confidentiality obligations[/BULLET]\n"
            "[BULLET]Breach notification requirements[/BULLET]\n\n"

            f"User question:\n{message}\n\n"
            f"Policy context:\n{context}"
        )

    def _try_general_gemini_answer(
        self,
        message: str,
    ) -> tuple[str | None, str | None]:
        if not self.gemini_client:
            return (
                None,
                "No matching policy was found, and Gemini is not configured "
                "for general AI fallback.",
            )

        prompt = self._build_general_prompt(message)

        try:
            response = self.gemini_client.models.generate_content(
                model=self.settings.gemini_model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.25,
                    max_output_tokens=900,
                ),
            )

            answer = self._clean_ai_formatting(
                response.text or ""
            )

        except Exception as error:
            return self._handle_gemini_error(
                error=error,
                context="GENERAL",
            )

        if not answer:
            return (
                None,
                "Gemini returned an empty general response.",
            )

        return (
            answer,
            "Sources: Gemini general knowledge; not from PCL policy.",
        )

    def _build_general_prompt(
        self,
        message: str,
    ) -> str:
        return (
            "You are Pakistan Cables OneDesk Assistant.\n"
            "The policy knowledge base did not contain a reliable answer.\n"
            "Answer using accurate general knowledge.\n"
            "Do not claim that the answer comes from Pakistan Cables policy.\n"
            "Do not invent Pakistan Cables systems, approvals, contacts, "
            "responsibilities or procedures.\n"
            "For Microsoft products such as SharePoint, Teams, Power BI, "
            "Power Apps or Power Automate, provide a clear general "
            "explanation.\n\n"

            "Required output format:\n"
            "- Start with one short introductory paragraph.\n"
            "- Use sections when useful.\n"
            "- Write headings exactly as:\n"
            "[SECTION]Heading text[/SECTION]\n"
            "- Write bullets exactly as:\n"
            "[BULLET]Bullet text[/BULLET]\n"
            "- Put every heading and bullet on its own line.\n"
            "- Always close every tag.\n"
            "- Never change the spelling or casing of the tags.\n"
            "- Never use #, ##, ###, **, hyphen bullets or asterisk bullets.\n"
            "- Do not use tables.\n"
            "- Keep the answer concise but complete.\n\n"

            "Correct example:\n"
            "SharePoint is a Microsoft platform used to create internal "
            "websites and manage organizational content.\n\n"
            "[SECTION]Common Uses[/SECTION]\n"
            "[BULLET]Store and share documents[/BULLET]\n"
            "[BULLET]Create departmental sites[/BULLET]\n"
            "[BULLET]Build lists and approval workflows[/BULLET]\n\n"

            f"User message:\n{message}"
        )

    @staticmethod
    def _build_policy_fallback_answer() -> str:
        return (
            "Relevant policy information was found, but the AI service could "
            "not generate the complete answer.\n\n"
            "[SECTION]Recommended Action[/SECTION]\n"
            "[BULLET]Review the policy source displayed below[/BULLET]\n"
            "[BULLET]Follow only the requirements written in the policy"
            "[/BULLET]\n"
            "[BULLET]Contact the IT Service Desk if clarification is needed"
            "[/BULLET]"
        )

    @staticmethod
    def _build_policy_reference_notice(
        sources: list[SourceReference],
    ) -> str:
        document_names: list[str] = []

        for source in sources:
            name = source.document_name.strip()
            cleaned_name = re.sub(
                r"\.[^.]+$",
                "",
                name,
            )
            cleaned_name = re.sub(
                r"^\d+\s*-\s*PCL\s*-\s*",
                "",
                cleaned_name,
                flags=re.IGNORECASE,
            )
            cleaned_name = re.sub(
                r"^PCL\s*-\s*",
                "",
                cleaned_name,
                flags=re.IGNORECASE,
            ).strip()

            page_suffix = (
                f" (Page {source.page_number})"
                if source.page_number
                else ""
            )
            label = f"{cleaned_name}{page_suffix}" if cleaned_name else name

            if label and label not in document_names:
                document_names.append(label)

            if len(document_names) >= 3:
                break

        if not document_names:
            return "Sources: PCL policy knowledge base."

        return "Sources: " + "; ".join(document_names) + "."

    def _handle_gemini_error(
        self,
        error: Exception,
        context: str,
    ) -> tuple[str | None, str | None]:
        error_text = str(error)

        if (
            "429" in error_text
            or "RESOURCE_EXHAUSTED" in error_text
        ):
            print(
                "\n"
                "================ GEMINI QUOTA ERROR =================\n"
            )
            print(error_text)
            print(
                "=====================================================\n"
            )

            return (
                None,
                "Gemini free quota is temporarily exhausted. "
                "Please wait and try again later.",
            )

        if (
            "404" in error_text
            or "NOT_FOUND" in error_text
        ):
            print(
                "\n"
                f"================ GEMINI {context} MODEL ERROR "
                "================\n"
            )
            print(error_text)
            traceback.print_exc()
            print(
                "=====================================================\n"
            )

            return (
                None,
                "The configured Gemini model is unavailable. "
                "Please update GEMINI_MODEL in the .env file.",
            )

        if (
            "401" in error_text
            or "403" in error_text
            or "UNAUTHENTICATED" in error_text
            or "PERMISSION_DENIED" in error_text
        ):
            print(
                "\n"
                f"================ GEMINI {context} AUTH ERROR "
                "================\n"
            )
            print(error_text)
            traceback.print_exc()
            print(
                "=====================================================\n"
            )

            return (
                None,
                "Gemini authentication failed. Please verify the API key.",
            )

        print(
            "\n"
            f"================ GEMINI {context} ERROR =============\n"
        )
        print(type(error).__name__)
        print(error_text)
        traceback.print_exc()
        print(
            "=====================================================\n"
        )

        if context == "POLICY":
            notice = (
                "Gemini is currently unavailable, so a policy fallback "
                "response was used."
            )
        else:
            notice = (
                "Gemini general fallback is currently unavailable."
            )

        return None, notice

    @staticmethod
    def _clean_ai_formatting(answer: str) -> str:
        """
        Normalize Gemini output into safe SECTION and BULLET tags.
        """

        if not answer:
            return ""

        answer = answer.replace("\r\n", "\n").replace("\r", "\n")

        # Normalize malformed tags regardless of casing or spacing.
        answer = re.sub(
            r"\[\s*section\s*\]",
            "[SECTION]",
            answer,
            flags=re.IGNORECASE,
        )

        answer = re.sub(
            r"\[\s*/\s*section\s*\]",
            "[/SECTION]",
            answer,
            flags=re.IGNORECASE,
        )

        answer = re.sub(
            r"\[\s*bullet\s*\]",
            "[BULLET]",
            answer,
            flags=re.IGNORECASE,
        )

        answer = re.sub(
            r"\[\s*/\s*bullet\s*\]",
            "[/BULLET]",
            answer,
            flags=re.IGNORECASE,
        )

        cleaned_lines: list[str] = []

        for raw_line in answer.splitlines():
            line = raw_line.strip()

            if not line:
                if cleaned_lines and cleaned_lines[-1] != "":
                    cleaned_lines.append("")
                continue

            # Remove Markdown headings.
            line = re.sub(
                r"^#{1,6}\s*",
                "",
                line,
            )

            # Remove Markdown bold and underline formatting.
            line = line.replace("**", "")
            line = line.replace("__", "")

            # Convert ordinary bullets to BULLET tags.
            if line.startswith("- "):
                line = (
                    f"[BULLET]{line[2:].strip()}[/BULLET]"
                )

            elif line.startswith("* "):
                line = (
                    f"[BULLET]{line[2:].strip()}[/BULLET]"
                )

            elif line.startswith("• "):
                line = (
                    f"[BULLET]{line[2:].strip()}[/BULLET]"
                )

            # Repair missing closing BULLET tag.
            if (
                line.startswith("[BULLET]")
                and "[/BULLET]" not in line
            ):
                content = line.replace(
                    "[BULLET]",
                    "",
                    1,
                ).strip()

                line = (
                    f"[BULLET]{content}[/BULLET]"
                )

            # Repair missing closing SECTION tag.
            if (
                line.startswith("[SECTION]")
                and "[/SECTION]" not in line
            ):
                content = line.replace(
                    "[SECTION]",
                    "",
                    1,
                ).strip()

                line = (
                    f"[SECTION]{content}[/SECTION]"
                )

            cleaned_lines.append(line)

        while cleaned_lines and cleaned_lines[-1] == "":
            cleaned_lines.pop()

        return "\n".join(cleaned_lines).strip()

    @staticmethod
    def _is_policy_unavailable_answer(
        answer: str,
    ) -> bool:
        normalized = (
            answer.lower()
            .strip()
            .replace("*", "")
            .replace("#", "")
        )

        unavailable_phrases = (
            "information not available in it policies",
            "information is not available in it policies",
            "not available in the provided policy",
            "not available in the policy context",
            "policy context does not contain",
            "the provided policy does not contain",
            "not found in the policy",
            "not found in the provided policy",
            "the policy does not provide",
            "the context does not provide",
        )

        return any(
            phrase in normalized
            for phrase in unavailable_phrases
        )

    @staticmethod
    def _handle_greeting(
        message: str,
        user_display_name: str | None = None,
        preferred_name: str | None = None,
    ) -> str | None:
        normalized = message.lower().strip()

        greetings = {
            "hi",
            "hello",
            "hey",
            "salam",
            "assalam o alaikum",
            "assalamualaikum",
            "aoa",
            "good morning",
            "good afternoon",
            "good evening",
        }

        if normalized in greetings:
            if user_display_name or preferred_name:
                name = PolicyChatbot._safe_first_name(
                    display_name=user_display_name or "",
                    preferred_name=preferred_name,
                )
                return f"Hi {name}, how can I help you today?"

            return (
                "Assalam o Alaikum!\n\n"
                "I am the Pakistan Cables OneDesk Assistant.\n\n"
                "[SECTION]How I Can Help[/SECTION]\n"
                "[BULLET]Ask about available Pakistan Cables policies"
                "[/BULLET]\n"
                "[BULLET]Ask general IT and Microsoft product questions"
                "[/BULLET]"
            )

        return None

    @staticmethod
    def _safe_first_name(
        *,
        display_name: str,
        preferred_name: str | None = None,
    ) -> str:
        source = (preferred_name or display_name or "").strip()
        match = re.search(r"[A-Za-z][A-Za-z.'-]*", source)
        return match.group(0) if match else "there"
