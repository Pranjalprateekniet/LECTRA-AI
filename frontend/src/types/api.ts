/**
 * TypeScript API contracts matching backend FastAPI schemas.
 */

export interface HealthData {
  status: string;
  timestamp: string;
  version: string;
  environment: string;
  database: string;
  execution_device: string;
  components?: {
    api: string;
    database: string;
    qdrant_configured: boolean;
  };
}

export interface Playlist {
  id: string;
  youtube_id: string;
  url: string;
  title: string;
  channel_name: string | null;
  video_count: number;
  status: string;
  discovery_error: string | null;
  created_at: string;
  updated_at: string;
  completed_count: number;
  processing_count: number;
  failed_count: number;
  thumbnail_url: string | null;
}

export interface PlaylistSubmitResponse {
  job_id: string;
  playlist_id: string;
  youtube_id: string;
  status: string;
  message: string;
}

export interface JobSummary {
  id: string;
  status: string;
  attempts: number;
  error_summary: string | null;
}

export interface PlaylistStatusResponse {
  playlist_id: string;
  youtube_id: string;
  title: string;
  status: string;
  discovery_error: string | null;
  video_count: number;
  discovered_count: number;
  unavailable_count: number;
  transcripts_ready_count: number;
  needs_transcription_count: number;
  completed_count: number;
  processing_count: number;
  failed_count: number;
  total_chunks: number;
  total_embeddings: number;
  total_vectors_indexed: number;
  total_transcript_segments: number;
  embedding_model: string;
  latest_job: JobSummary | null;
}

export interface StageDetail {
  stage_name: string; // "DISCOVERY", "TRANSCRIPT_ACQUISITION", "CHUNKING", "INDEXING", etc.
  status: "PENDING" | "IN_PROGRESS" | "COMPLETED" | "FAILED" | "SKIPPED";
  attempts: number;
  error_category: string | null;
  error_detail: string | null;
  completed_at: string | null;
  artifact_path: string | null;
}

export interface VideoResponse {
  id: string;
  playlist_id: string;
  youtube_id: string;
  title: string;
  url: string;
  duration_seconds: number | null;
  position: number;
  status: string; // "DISCOVERED" | "TRANSCRIPT_READY" | "CHUNKED" | "INDEXED" | "SKIPPED_UNAVAILABLE" | "FAILED"
  availability: string | null;
  discovery_error: string | null;
  transcript_segments_count: number;
  transcript_source: string | null; // "manual" | "generated" | "whisper" | null
  language: string | null;
  chunks_count: number;
  indexed_vectors_count: number;
  thumbnail_url: string | null;
  stages: StageDetail[];
}

export interface ActivityEventResponse {
  id: string;
  timestamp: string;
  playlist_id: string;
  video_id: string | null;
  video_title: string | null;
  stage: string;
  event: string;
  severity: "info" | "warning" | "error" | "success";
  details: string | null;
}

export interface RetryResponse {
  success: boolean;
  job_id: string;
  message: string;
}

export interface PipelineStageConfig {
  key: string;
  label: string;
  description: string;
}

export type AnswerStatus = "answered" | "partially_answered" | "insufficient_context";

export interface CitationItem {
  source_id: string;
  video_title: string;
  youtube_id: string;
  chunk_index: number;
  start_seconds: number;
  end_seconds: number;
  youtube_url: string;
  text?: string | null;
  chunk_id?: string | null;
  playlist_id?: string | null;
  message_id?: string;
}

export interface GenerationRequest {
  query: string;
  top_k?: number | null;
  score_threshold?: number | null;
  playlist_id?: string | null;
  video_id?: string | null;
  youtube_id?: string | null;
}

export interface AnswerResponse {
  status: AnswerStatus;
  answer: string;
  citations: CitationItem[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  status?: AnswerStatus;
  citations?: CitationItem[];
  timestamp: string;
  playlist_id?: string | null;
}
