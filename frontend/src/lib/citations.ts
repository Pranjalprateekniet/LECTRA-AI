import type { CitationItem } from "../types/api";

/**
 * Validates whether a citation object has a valid YouTube video ID and valid timestamp.
 */
export function isValidCitation(citation: unknown): citation is CitationItem {
  if (!citation || typeof citation !== "object") return false;
  const c = citation as Partial<CitationItem>;
  const hasYoutubeId =
    typeof c.youtube_id === "string" && c.youtube_id.trim().length > 0;
  const hasValidTimestamp =
    typeof c.start_seconds === "number" &&
    !isNaN(c.start_seconds) &&
    isFinite(c.start_seconds) &&
    c.start_seconds >= 0;
  return Boolean(hasYoutubeId && hasValidTimestamp);
}

/**
 * Finds the first valid citation from an array of citations, skipping any with invalid metadata.
 * Returns null if no valid citation exists or if citations is empty/missing.
 */
export function findFirstValidCitation(
  citations?: CitationItem[] | null
): CitationItem | null {
  if (!citations || !Array.isArray(citations)) {
    return null;
  }
  for (const c of citations) {
    if (isValidCitation(c)) {
      return c;
    }
  }
  return null;
}
