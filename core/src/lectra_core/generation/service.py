"""Grounded RAG Answer Generation Service orchestrating retrieval and LLM reasoning."""

import json
import re
from typing import Dict, List, Optional

from lectra_core.config import Settings, get_settings
from lectra_core.generation.context_builder import ContextBuilder
from lectra_core.generation.exceptions import GenerationError
from lectra_core.generation.groq_client import GroqClient
from lectra_core.generation.prompts import SYSTEM_PROMPT_V1, USER_PROMPT_TEMPLATE
from lectra_core.generation.schemas import (
    AnswerResponse,
    CitationItem,
    GenerationRequest,
    LLMRawAnswer,
)
from lectra_core.logging import get_logger
from lectra_core.retrieval.remote import RemoteRetrievalService
from lectra_core.retrieval.schemas import SearchResultItem
from lectra_core.retrieval.service import RetrievalService

logger = get_logger("lectra.generation.service")


class GenerationService:
    """Orchestrates retrieval, citation-budgeted context assembly, and grounded generation."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        retrieval_service: Optional[RetrievalService | RemoteRetrievalService] = None,
        groq_client: Optional[GroqClient] = None,
        context_builder: Optional[ContextBuilder] = None,
    ) -> None:
        self.settings = settings or get_settings()
        if retrieval_service is not None:
            self.retrieval_service = retrieval_service
        elif self.settings.app_mode == "USER":
            if not self.settings.retrieval_api_url:
                raise ValueError(
                    "Configuration error: In USER mode, RETRIEVAL_API_URL is mandatory. "
                    "Cannot instantiate local retrieval in USER mode."
                )
            self.retrieval_service = RemoteRetrievalService(settings=self.settings)
        elif self.settings.retrieval_api_url:
            self.retrieval_service = RemoteRetrievalService(settings=self.settings)
        else:
            self.retrieval_service = RetrievalService(settings=self.settings)
        self.groq_client = groq_client or GroqClient(settings=self.settings)
        self.context_builder = context_builder or ContextBuilder(
            max_context_tokens=self.settings.groq_max_context_tokens,
            reserved_output_tokens=self.settings.groq_reserved_output_tokens,
        )

    def _extract_json_from_response(self, text: str) -> dict:
        """Extract and parse JSON object from LLM response text, stripping any markdown wrappers."""
        clean_text = text.strip()

        # Remove markdown codeblock fences if present
        if clean_text.startswith("```"):
            clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
            clean_text = re.sub(r"\s*```$", "", clean_text)
            clean_text = clean_text.strip()

        # Try parsing directly
        try:
            return json.loads(clean_text)
        except json.JSONDecodeError:
            # Fallback: search for first '{' and last '}'
            match = re.search(r"(\{.*\})", clean_text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError as exc:
                    raise GenerationError(
                        f"Failed to parse JSON substring from LLM response: {exc}"
                    ) from exc
            raise GenerationError(f"LLM response did not contain valid JSON: {clean_text[:200]}")

    def _synthesize_citations(
        self,
        raw_citations: List[str],
        answer_text: str,
        source_map: Dict[str, SearchResultItem],
    ) -> List[CitationItem]:
        """Validate citation tokens against supplied sources and construct verified metadata."""
        # Normalize cited tokens from explicit array
        candidate_ids = set()
        for c in raw_citations:
            norm_id = c.strip().strip("[]").upper()
            if norm_id:
                candidate_ids.add(norm_id)

        # Also discover inline citations like [S1], [S2] in the answer text
        inline_found = re.findall(r"\[(S\d+)\]", answer_text, re.IGNORECASE)
        for c in inline_found:
            candidate_ids.add(c.upper())

        citations: List[CitationItem] = []
        for src_id in sorted(list(candidate_ids)):
            if src_id in source_map:
                chunk = source_map[src_id]
                citations.append(
                    CitationItem(
                        source_id=src_id,
                        video_title=chunk.video_title,
                        youtube_id=chunk.youtube_id,
                        chunk_index=chunk.chunk_index,
                        start_seconds=chunk.start_seconds,
                        end_seconds=chunk.end_seconds,
                        youtube_url=chunk.youtube_url,
                        text=chunk.text,
                        chunk_id=chunk.chunk_id,
                        playlist_id=chunk.playlist_id,
                    )
                )
            else:
                logger.warning(
                    "Model cited source ID that was not provided in context",
                    extra={"source_id": src_id, "valid_sources": list(source_map.keys())},
                )

        return citations

    def generate_answer(self, request: GenerationRequest) -> AnswerResponse:
        """Execute full RAG generation pipeline for a student revision query."""
        logger.info("Executing grounded answer generation", extra={"query": request.query})

        # Step 1 & 2: Call existing RetrievalService
        search_resp = self.retrieval_service.search(
            query=request.query,
            top_k=request.top_k,
            score_threshold=request.score_threshold,
            playlist_id=request.playlist_id,
            video_id=request.video_id,
            youtube_id=request.youtube_id,
        )

        if not search_resp.results:
            logger.info("Retrieval returned 0 chunks; returning insufficient_context")
            return AnswerResponse(
                status="insufficient_context",
                answer="No relevant lecture transcript segments were found to answer this query.",
                citations=[],
            )

        # Step 3: Context Assembly with token budgeting and citation indexing
        context_res = self.context_builder.build_context(
            query=request.query,
            retrieved_chunks=search_resp.results,
            system_prompt=SYSTEM_PROMPT_V1,
        )

        # Step 4: Construct messages
        user_message_content = USER_PROMPT_TEMPLATE.format(
            context=context_res.context_text,
            question=request.query,
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_V1},
            {"role": "user", "content": user_message_content},
        ]

        # Step 5: Invoke Groq model (openai/gpt-oss-120b)
        raw_completion = self.groq_client.generate_chat_completion(messages=messages)

        # Step 6: Parse structured response
        parsed_json = self._extract_json_from_response(raw_completion)
        try:
            raw_answer = LLMRawAnswer.model_validate(parsed_json)
        except Exception as exc:
            logger.error(
                "LLM JSON failed schema validation",
                extra={"error": str(exc), "raw_json": parsed_json},
            )
            raise GenerationError(
                f"Model output failed structured schema validation: {exc}"
            ) from exc

        # Step 7: Citation Validation & Construction
        if raw_answer.status == "insufficient_context":
            validated_citations: List[CitationItem] = []
        else:
            validated_citations = self._synthesize_citations(
                raw_citations=raw_answer.citations,
                answer_text=raw_answer.answer,
                source_map=context_res.source_map,
            )

        logger.info(
            "Answer generation complete",
            extra={
                "status": raw_answer.status,
                "citations_count": len(validated_citations),
                "chunks_used": context_res.chunks_included,
            },
        )

        return AnswerResponse(
            status=raw_answer.status,
            answer=raw_answer.answer,
            citations=validated_citations,
        )

    def close(self) -> None:
        """Release underlying retrieval embedding resources."""
        self.retrieval_service.close()
