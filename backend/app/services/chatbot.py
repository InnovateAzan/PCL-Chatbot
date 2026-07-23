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

    POLICY_UNAVAILABLE_MESSAGE = (
        "Information not available in IT policies."
    )

    def __init__(
        self,
        retriever: PolicyRetriever | None = None,
    ) -> None:
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
            return self._build_general_response(message)

        gemini_answer, gemini_notice = self._try_gemini_answer(
            message=message,
            sources=sources,
        )

        if gemini_answer:
            if self._is_policy_unavailable_answer(gemini_answer):
                return self._build_general_response(message)

            return ChatResponse(
                answer=gemini_answer,
                sources=sources,
                fallback=False,
                provider="gemini-policy",
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

    def _build_general_response(
        self,
        message: str,
    ) -> ChatResponse:
        general_answer, general_notice = (
            self._try_general_gemini_answer(message)
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
            answer=self.POLICY_UNAVAILABLE_MESSAGE,
            sources=[],
            fallback=True,
            provider="policy-rules",
            notice=general_notice,
        )

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
            return (
                None,
                "Gemini is not configured.",
            )

        prompt = self._build_policy_prompt(
            message=message,
            sources=sources,
        )

        try:
            response = self.gemini_client.models.generate_content(
                model=self.settings.gemini_model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=700,
                ),
            )

            answer = (response.text or "").strip()

        except Exception as error:
            return self._handle_gemini_error(
                error=error,
                context="POLICY",
            )

        if not answer:
            return (
                None,
                "Gemini returned an empty policy response, so a policy-only "
                "fallback answer was used.",
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
            "You are Pakistan Cables IT Policy Assistant.\n"
            "Answer only from the policy context provided below.\n"
            "Do not invent Pakistan Cables rules, approvals, limits, "
            "responsibilities, timelines or procedures.\n"
            "If the context does not answer the question, reply exactly:\n"
            f"{self.POLICY_UNAVAILABLE_MESSAGE}\n\n"

            "Writing style:\n"
            "- Use clear, simple and professional English.\n"
            "- Start with a short heading.\n"
            "- Give one direct introductory sentence.\n"
            "- Use bullet points beginning with the symbol •.\n"
            "- Put every bullet point on a separate line.\n"
            "- Use short paragraphs.\n"
            "- Add a practical example only when it is supported by the "
            "policy context or clearly labelled as an illustration.\n"
            "- Do not number every sentence.\n"
            "- Do not write one long paragraph.\n"
            "- Do not use a Markdown table.\n"
            "- Keep the answer concise and easy to scan.\n"
            "- Do not repeat document names, page numbers or source details "
            "because the application shows sources separately.\n\n"

            "Important accuracy rules:\n"
            "- Mention only requirements present in the supplied context.\n"
            "- Do not combine the policy with general industry practices.\n"
            "- Do not add a clause, control or requirement that is not in "
            "the context.\n"
            "- If multiple context snippets disagree, state that the policy "
            "information is unclear rather than guessing.\n\n"

            "Password-specific instructions:\n"
            "- If the question is about passwords, provide an example only "
            "when useful.\n"
            "- Clearly say that the example is for illustration only.\n"
            "- Tell the user not to copy or reuse the exact example.\n"
            "- Do not claim the example is an approved Pakistan Cables "
            "password.\n"
            "- Mention password length or complexity only if it appears in "
            "the policy context.\n\n"

            f"User question:\n{message}\n\n"
            f"Policy context:\n{context}"
        )

    def _build_policy_answer(
        self,
        message: str,
    ) -> str:
        normalized = message.lower()

        if (
            "vpn" in normalized
            or "remote access" in normalized
        ):
            return (
                "Remote Access Request\n\n"
                "Relevant policy information was found, but Gemini could not "
                "generate the full response.\n\n"
                "• Review the source shown below.\n"
                "• Follow only the approval and access steps stated in the "
                "policy.\n"
                "• Contact the IT Service Desk if clarification is required."
            )

        if "password" in normalized:
            return (
                "Password Assistance\n\n"
                "Relevant password policy information was found, but Gemini "
                "could not generate the full response.\n\n"
                "• Review the policy source shown below.\n"
                "• Use the approved password reset process.\n"
                "• Contact the IT Service Desk if the reset does not work."
            )

        return (
            "Policy Information\n\n"
            "Relevant policy context was found, but Gemini could not generate "
            "the detailed response.\n\n"
            "• Review the source shown below.\n"
            "• Follow only the requirements stated in the policy.\n"
            "• Contact the IT Service Desk if clarification is required."
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
                    temperature=0.3,
                    max_output_tokens=700,
                ),
            )

            answer = (response.text or "").strip()

        except Exception as error:
            return self._handle_gemini_error(
                error=error,
                context="GENERAL",
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

    def _build_general_prompt(
        self,
        message: str,
    ) -> str:
        return (
            "You are Pakistan Cables PCL GPT.\n"
            "The company policy knowledge base did not contain a reliable "
            "answer to the user's question.\n"
            "Provide an accurate and helpful general-information answer.\n"
            "Do not claim that the answer comes from Pakistan Cables policy.\n"
            "Do not invent internal Pakistan Cables procedures, approvals, "
            "systems, contacts or responsibilities.\n"
            "If the question asks about a Microsoft product such as "
            "SharePoint, Teams, Power Automate or Power BI, explain the "
            "product generally and clearly.\n"
            "For security-sensitive questions, provide safe general guidance.\n\n"

            "Writing style:\n"
            "- Start with a short heading.\n"
            "- Give a simple definition first.\n"
            "- Use bullet points beginning with the symbol • when listing "
            "features or steps.\n"
            "- Put every bullet point on a separate line.\n"
            "- Use short paragraphs.\n"
            "- Do not number every sentence.\n"
            "- Do not write one long paragraph.\n"
            "- Do not use a Markdown table.\n"
            "- Keep the answer concise but complete.\n"
            "- Do not end with an unnecessary invitation for more questions.\n\n"

            f"User message:\n{message}"
        )

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
            f"================ GEMINI {context} ERROR "
            "================\n"
        )
        print(type(error).__name__)
        print(error_text)
        traceback.print_exc()
        print(
            "=====================================================\n"
        )

        if context == "POLICY":
            notice = (
                "Gemini is currently unavailable, so a policy-only fallback "
                "answer was used."
            )
        else:
            notice = (
                "No matching policy was found. Gemini general fallback is "
                "currently unavailable."
            )

        return None, notice

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
            return (
                "Assalam o Alaikum!\n\n"
                "I am the Pakistan Cables IT Policy Assistant.\n\n"
                "• Ask me about available Pakistan Cables policies.\n"
                "• You can also ask general IT questions."
            )

        return None