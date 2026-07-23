from __future__ import annotations

import traceback

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover
    genai = None
    genai_types = None

from backend.app.core.config import get_settings
from backend.app.models.schemas import ChatResponse, SourceReference
from backend.app.services.retriever import PolicyRetriever


class PolicyChatbot:
    """Policy chatbot with Gemini generation and safe fallback answers."""

    def __init__(self, retriever: PolicyRetriever | None = None) -> None:
        self.settings = get_settings()
        self.retriever = retriever or PolicyRetriever()
        self.gemini_client = self._build_gemini_client()

    def answer(self, message: str) -> ChatResponse:
        message = message.strip()

        if not message:
            return ChatResponse(
                answer="Please enter your question.",
                sources=[],
                fallback=True,
                provider="validation",
            )

        greeting_answer = self._handle_greeting(message)
        if greeting_answer:
            return ChatResponse(
                answer=greeting_answer,
                sources=[],
                fallback=False,
                provider="local-greeting",
            )

        sources = self.retriever.search(message)

        if not sources:
            general_answer, general_notice = self._try_general_gemini_answer(
                message
            )

            if general_answer:
                return ChatResponse(
                    answer=general_answer,
                    sources=[],
                    fallback=False,
                    provider="gemini-general",
                    notice=general_notice,
                )

            return ChatResponse(
                answer="Information not available in IT policies.",
                sources=[],
                fallback=True,
                provider="policy-rules",
                notice=general_notice,
            )

        gemini_answer, gemini_notice = self._try_gemini_answer(
            message,
            sources,
        )

        if gemini_answer:
            return ChatResponse(
                answer=gemini_answer,
                sources=sources,
                fallback=False,
                provider="gemini",
                notice=gemini_notice,
            )

        fallback_answer = self._build_policy_answer(message)

        return ChatResponse(
            answer=fallback_answer,
            sources=sources,
            fallback=True,
            provider="policy-rules",
            notice=gemini_notice,
        )

    def health_snapshot(self) -> dict[str, str | bool]:
        return {
            "llm_mode": (
                "gemini-configured"
                if self.gemini_client
                else "policy-fallback"
            ),
            "gemini_configured": bool(self.gemini_client),
        }

    def _build_gemini_client(self):
        if (
            not genai
            or not genai_types
            or not self.settings.gemini_api_key.strip()
        ):
            return None

        try:
            return genai.Client(
                api_key=self.settings.gemini_api_key,
                http_options=genai_types.HttpOptions(
                    client_args={
                        "trust_env": self.settings.gemini_use_env_proxy
                    }
                ),
            )

        except Exception as error:
            print("\n================ GEMINI CLIENT ERROR ================")
            print(type(error).__name__)
            print(str(error))
            traceback.print_exc()
            print("=====================================================\n")
            return None

    def _try_gemini_answer(
        self,
        message: str,
        sources: list[SourceReference],
    ) -> tuple[str | None, str | None]:
        if not self.gemini_client:
            return None, "Gemini is not configured."

        prompt = self._build_prompt(message, sources)

        try:
            response = self.gemini_client.models.generate_content(
                model=self.settings.gemini_model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=500,
                ),
            )

            answer = (response.text or "").strip()

        except Exception as error:
            error_text = str(error)

            if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
                print("\n================ GEMINI QUOTA ERROR =================")
                print(error_text)
                print("=====================================================\n")

                return (
                    None,
                    "Gemini free quota is temporarily exhausted. "
                    "Please wait a few seconds and try again.",
                )

            print("\n================ GEMINI POLICY ERROR ================")
            print(type(error).__name__)
            print(error_text)
            traceback.print_exc()
            print("=====================================================\n")

            return (
                None,
                "Gemini is currently unavailable, so a policy-only "
                "fallback answer was used.",
            )

        if not answer:
            return (
                None,
                "Gemini returned an empty policy response, so a policy-only "
                "fallback answer was used.",
            )

        return answer, None

    def _build_prompt(
        self,
        message: str,
        sources: list[SourceReference],
    ) -> str:
        context_blocks: list[str] = []

        for source in sources:
            location = source.section or "Section not provided"

            page = (
                f"Page {source.page_number}"
                if source.page_number
                else "Page not provided"
            )

            snippet = source.snippet or "No supporting excerpt provided."

            context_blocks.append(
                f"Document: {source.document_name}\n"
                f"Location: {location}\n"
                f"{page}\n"
                f"Excerpt: {snippet}"
            )

        context = "\n\n".join(context_blocks)

        return (
            "You are Pakistan Cables IT Policy Assistant.\n"
            "Answer in clear, simple and professional English.\n"
            "Use only the policy context provided below.\n"
            "Do not invent company rules, approvals, limits or requirements.\n"
            "If the policy context does not answer the question, reply exactly:\n"
            "Information not available in IT policies.\n\n"
            "Response format:\n"
            "1. Give the direct answer first.\n"
            "2. Explain the rule in simple language.\n"
            "3. Give one practical example when it helps understanding.\n"
            "4. Keep the answer concise.\n"
            "5. Do not repeat the source details because the application "
            "shows sources separately.\n\n"
            "Password-specific instructions:\n"
            "- If the question is about passwords, provide a safe example "
            "only when useful.\n"
            "- Clearly say that the example is for illustration only.\n"
            "- Tell the user not to copy or reuse the exact example.\n"
            "- Do not claim that the example is an approved Pakistan Cables "
            "password.\n"
            "- Only mention password length or complexity requirements if "
            "they exist in the provided policy context.\n\n"
            f"User question:\n{message}\n\n"
            f"Policy context:\n{context}"
        )

    def _build_policy_answer(self, message: str) -> str:
        normalized = message.lower()

        if "vpn" in normalized or "remote access" in normalized:
            return (
                "To request VPN or remote access, create an IT Service Desk "
                "ticket and follow the required approval process.\n\n"
                "Example: If you need to work from home, submit a ticket "
                "explaining why remote access is required and wait for the "
                "relevant approval before connecting."
            )

        if "password" in normalized:
            return (
                "If your password expires, use the approved password reset "
                "process or contact the IT Service Desk for assistance.\n\n"
                "Example only: a strong password format could combine an "
                "unrelated phrase, numbers and symbols, such as "
                "`BlueCable!47River`.\n\n"
                "Do not copy this exact example. Create your own unique "
                "password according to the company password policy."
            )

        return (
            "Relevant policy context was found, but Gemini could not generate "
            "the detailed response. Please review the source shown below or "
            "contact the IT Service Desk."
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

        prompt = (
            "You are Pakistan Cables PCL GPT.\n"
            "The company policy knowledge base did not contain an answer.\n"
            "Provide a helpful, clear and professional general answer.\n"
            "Do not claim that the answer comes from Pakistan Cables policy.\n"
            "Do not invent internal Pakistan Cables procedures.\n"
            "If the message is a greeting, reply naturally and briefly.\n"
            "For security-sensitive questions, give safe general guidance.\n"
            "Give a practical example when it improves understanding.\n"
            "Keep the answer concise but complete.\n\n"
            f"User message:\n{message}"
        )

        try:
            response = self.gemini_client.models.generate_content(
                model=self.settings.gemini_model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=500,
                ),
            )

            answer = (response.text or "").strip()

        except Exception as error:
            error_text = str(error)

            if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
                print("\n================ GEMINI QUOTA ERROR =================")
                print(error_text)
                print("=====================================================\n")

                return (
                    None,
                    "Gemini free quota is temporarily exhausted. "
                    "Please wait a few seconds and try again.",
                )

            print("\n================ GEMINI GENERAL ERROR ================")
            print(type(error).__name__)
            print(error_text)
            traceback.print_exc()
            print("======================================================\n")

            return (
                None,
                "No matching policy was found. Gemini general fallback is "
                "currently unavailable.",
            )

        if not answer:
            return (
                None,
                "No matching policy was found, and Gemini returned an empty "
                "general response.",
            )

        return (
            answer,
            "This answer is AI-generated and not based on company policy.",
        )

    def _handle_greeting(self, message: str) -> str | None:
        normalized = message.lower().strip()

        greetings = {
            "hi",
            "hello",
            "hey",
            "salam",
            "assalam o alaikum",
            "assalamualaikum",
            "aoa",
        }

        if normalized in greetings:
            return (
                "Assalam o Alaikum! I am the Pakistan Cables IT Policy "
                "Assistant. How can I help you today?"
            )

        return None