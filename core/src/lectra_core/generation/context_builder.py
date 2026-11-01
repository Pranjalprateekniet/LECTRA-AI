"""Citation-aware context construction with strict token budgeting and injection defense."""

from dataclasses import dataclass
from typing import Dict, List, Set

from lectra_core.chunking.tokenizer import count_tokens
from lectra_core.generation.exceptions import ContextBudgetExceededError
from lectra_core.generation.prompts import SYSTEM_PROMPT_V1
from lectra_core.logging import get_logger
from lectra_core.retrieval.schemas import SearchResultItem

logger = get_logger("lectra.generation.context_builder")

PROMPT_OVERHEAD_TOKENS = 150


@dataclass
class ContextBuildResult:
    """Artifact resulting from context assembly and token budget enforcement."""

    context_text: str
    source_map: Dict[str, SearchResultItem]
    total_tokens: int
    chunks_included: int
    chunks_dropped: int


class ContextBuilder:
    """Builds prompt-injection-resistant, citation-indexed context blocks under token limits."""

    def __init__(
        self,
        max_context_tokens: int = 8192,
        reserved_output_tokens: int = 1024,
    ) -> None:
        self.max_context_tokens = max_context_tokens
        self.reserved_output_tokens = reserved_output_tokens

    def format_chunk_block(self, source_id: str, chunk: SearchResultItem) -> str:
        """Format a single transcript chunk with citation header and untrusted text boundary."""
        # Clean title and handle missing metadata defensively
        title = chunk.video_title.strip() if chunk.video_title else "Unknown Video"
        yt_id = chunk.youtube_id.strip() if chunk.youtube_id else "unknown"

        # Triple quotation and block isolation to defend against transcript prompt injection
        return (
            f"[{source_id}]\n"
            f"Video: {title}\n"
            f"YouTube ID: {yt_id}\n"
            f"Chunk: {chunk.chunk_index}\n"
            f"Timestamp: {chunk.start_seconds:.1f}s - {chunk.end_seconds:.1f}s\n\n"
            f'Transcript:\n"""{chunk.text.strip()}"""\n'
        )

    def build_context(
        self,
        query: str,
        retrieved_chunks: List[SearchResultItem],
        system_prompt: str = SYSTEM_PROMPT_V1,
    ) -> ContextBuildResult:
        """Assemble retrieved chunks into citation-indexed text within available token budget."""
        # 1. Calculate token overhead of system prompt, user prompt template, and query
        system_tokens = count_tokens(system_prompt)
        query_tokens = count_tokens(query)
        base_overhead = system_tokens + query_tokens + PROMPT_OVERHEAD_TOKENS

        available_budget = self.max_context_tokens - self.reserved_output_tokens - base_overhead

        if available_budget <= 0:
            raise ContextBudgetExceededError(
                f"Query and system instructions ({base_overhead} tokens) exceed the available "
                f"context budget ({self.max_context_tokens - self.reserved_output_tokens} tokens)."
            )

        source_map: Dict[str, SearchResultItem] = {}
        seen_chunk_ids: Set[str] = set()
        chunk_blocks: List[str] = []
        current_context_tokens = 0
        chunks_dropped = 0
        source_counter = 1

        # 2. Iterate through retrieved chunks, deduplicating and budgeting
        for chunk in retrieved_chunks:
            # Deduplicate by chunk_id
            if chunk.chunk_id in seen_chunk_ids:
                logger.debug(
                    "Skipping duplicate chunk in context assembly",
                    extra={"chunk_id": chunk.chunk_id},
                )
                continue
            seen_chunk_ids.add(chunk.chunk_id)

            source_id = f"S{source_counter}"
            formatted_block = self.format_chunk_block(source_id, chunk)
            block_tokens = count_tokens(formatted_block)

            # Check if block fits within budget
            if current_context_tokens + block_tokens <= available_budget:
                chunk_blocks.append(formatted_block)
                source_map[source_id] = chunk
                current_context_tokens += block_tokens
                source_counter += 1
            else:
                chunks_dropped += 1
                logger.info(
                    "Context budget reached; dropping remaining chunks",
                    extra={
                        "chunks_included": len(chunk_blocks),
                        "chunk_id": chunk.chunk_id,
                        "current_context_tokens": current_context_tokens,
                        "available_budget": available_budget,
                    },
                )
                break

        full_context_text = (
            "\n---\n\n".join(chunk_blocks) if chunk_blocks else "No relevant lecture chunks found."
        )
        total_prompt_tokens = base_overhead + current_context_tokens

        return ContextBuildResult(
            context_text=full_context_text,
            source_map=source_map,
            total_tokens=total_prompt_tokens,
            chunks_included=len(chunk_blocks),
            chunks_dropped=chunks_dropped,
        )
