# Hosted Read-Only Retrieval API Documentation

## 1. Overview & Architecture

Revision RAG provides a hosted, read-only semantic retrieval service that allows users running the Revision RAG frontend and backend locally to query a centrally hosted Qdrant Cloud knowledge base without ever receiving access to Qdrant credentials.

The local backend uses the user's own `GROQ_API_KEY` to construct grounded answers with timestamped YouTube links. The central retrieval service handles only chunk search and citation delivery.

```
[Local Next.js Frontend]
          |
          v (localhost:8000)
[Local FastAPI Backend]  --- (GROQ_API_KEY locally) ---> [Groq Cloud API]
          |
          v HTTPS POST /api/v1/retrieve (Server-to-Server, no CORS needed)
[Hosted Retrieval API] (FastAPI + Cached EmbeddingGemma 2 + Rate Limiter)
          |
          v (Private TLS)
[Qdrant Cloud Cluster] (revision_chunks collection - Read-Only)
```

---

## 2. Application Modes (`APP_MODE`)

The application supports two explicit operational modes:

### `APP_MODE=USER` (Local End-User Machine)
- **Mandatory Remote Retrieval**: `RETRIEVAL_API_URL` is strictly required. If missing, startup fails immediately with a descriptive configuration error (`ValueError`). The system **never silently falls back** to local retrieval.
- **Zero Local Model Downloads**: PyTorch weights, `EmbeddingModelManager`, and `EmbeddingService` are **never instantiated or downloaded** on the user's machine. The local backend uses lightweight `httpx` to communicate with the hosted retrieval API.
- **No Local Qdrant Connection**: Qdrant connection parameters (`QDRANT_URL`, `QDRANT_API_KEY`) are cleared (`qdrant_url = None`).
- **Ingestion Disabled**: Playlist submission (`POST /api/v1/playlists`), retries, and deletions return `HTTP 403 Forbidden`. The user machine functions exclusively as a grounded revision assistant.
- **Private Groq Key**: The user's `GROQ_API_KEY` is kept exclusively on their local machine and is never transmitted to the hosted retrieval service.

### `APP_MODE=DEVELOPER` (Local Development & Ingestion)
- Enables the full local pipeline: playlist discovery, Whisper audio transcription, translation, chunking, local Qdrant indexing, and local semantic search.
- When `RETRIEVAL_API_URL` is set, developers can also query the remote hosted service for testing.

---

## 3. Embedding Model & Vector Index Specification

The retrieval service uses the exact configuration verified against the existing ingestion pipeline:

| Parameter | Ingestion Implementation | Hosted Retrieval Implementation |
| :--- | :--- | :--- |
| **Model** | `google/embeddinggemma-2` | `google/embeddinggemma-2` |
| **Model Architecture** | Text-only backbone (`AutoConfig` disabling vision/audio) | Text-only backbone (`AutoConfig` disabling vision/audio) |
| **Vector Dimensions** | Exactly 768 float dimensions | Exactly 768 float dimensions |
| **Document Template** | `title: {title} \| text: {text}` | *(Used for stored chunks)* |
| **Query Template** | `task: search result \| query: {query}` | `task: search result \| query: {query}` |
| **Pooling** | Attention-mask-weighted mean pooling | Attention-mask-weighted mean pooling |
| **Normalization** | L2 unit normalization (`torch.nn.functional.normalize(p=2)`) | L2 unit normalization (`torch.nn.functional.normalize(p=2)`) |
| **Distance Metric** | Cosine similarity (`models.Distance.COSINE`) | Cosine similarity (`models.Distance.COSINE`) |
| **Startup Behavior** | Lazy loaded on demand | **Preloaded and cached on server startup** via `lifespan` warmup |

---

## 4. API Endpoints

### 4.1. Semantic Search: `POST /api/v1/retrieve`

Accepts a natural-language query and returns the most relevant transcript chunks along with verified YouTube timestamp URLs.

#### Request Format
- **Content-Type**: `application/json`
- **Body**:

```json
{
  "query": "Explain the fractional knapsack greedy choice",
  "top_k": 5
}
```

#### Request Parameters
| Parameter | Type | Required | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- |
| `query` | string | Yes | Min 1, Max 1,000 characters | Natural language question or revision search string. |
| `top_k` | integer | No | Default `5`, Min `1`, Max `10` | Number of chunks to retrieve (server-enforced maximum of 10). |

*Note: Extra fields are rejected with HTTP 400 (`extra="forbid"`).*

#### Response Format
- **Status**: `200 OK`
- **Body**:

```json
{
  "success": true,
  "results": [
    {
      "video_title": "Fractional Knapsack | Greedy Algorithms",
      "text": "In the fractional knapsack problem, we calculate the value to weight ratio for each item...",
      "start_timestamp": 120.0,
      "start_seconds": 120.0,
      "end_seconds": 195.0,
      "duration_seconds": 75.0,
      "youtube_url": "https://www.youtube.com/watch?v=F_DDzYnxO14&t=120",
      "score": 0.884,
      "similarity_score": 0.884,
      "chunk_id": "934c9c71-f9eb-53a5-bc6f-578bfa73d6b6",
      "video_id": "f516a8b7-6ebc-4c6e-827c-3f2d229f37b9",
      "youtube_id": "F_DDzYnxO14",
      "playlist_id": "6568daaf-8fa9-4546-9b2e-a53d9dd15e6d",
      "chunk_index": 2
    }
  ]
}
```

If no relevant chunks are found, the endpoint returns:
```json
{
  "success": true,
  "results": []
}
```

---

### 4.2. Health Check: `GET /health`

Indicates whether the retrieval service and vector store are operational without leaking credentials or internal host topology.

#### Success Response (`200 OK`)
```json
{
  "status": "healthy",
  "qdrant_status": "connected",
  "embedding_model": "google/embeddinggemma-2",
  "version": "0.1.0"
}
```

#### Degraded Response (`503 Service Unavailable`)
```json
{
  "status": "degraded",
  "qdrant_status": "unreachable",
  "embedding_model": "google/embeddinggemma-2",
  "version": "0.1.0"
}
```

---

## 5. Rate Limiting & Abuse Prevention

The service enforces strict per-IP rate limits:
- **10 requests per minute** per client IP.
- **100 requests per hour** per client IP.
- **Maximum query length**: 1,000 characters.
- **Server-side maximum top-k**: 10.
- **Concurrency limit**: Default 10 simultaneous requests to prevent CPU/GPU memory exhaustion.
- **Request timeout**: Default 15.0 seconds.

### Rate Limit Headers
Every response includes rate-limit metadata:
- `X-RateLimit-Limit-Minute`: Configured per-minute limit (e.g. `10`).
- `X-RateLimit-Remaining-Minute`: Remaining requests in the active 60s sliding window.
- `X-RateLimit-Limit-Hour`: Configured per-hour limit (e.g. `100`).
- `X-RateLimit-Remaining-Hour`: Remaining requests in the active 3600s sliding window.

When exceeded, the service returns **HTTP 429 Too Many Requests**:
- `Retry-After`: Seconds to wait before retrying (e.g. `45`).
```json
{
  "detail": "Rate limit exceeded. Please retry after 45 seconds."
}
```

### Storage Engines & Showcase Characteristics
- **In-Memory Sliding Window (Default for Showcase)**:
  - Thread-safe and async-safe with automatic stale IP cleanup.
  - **Limitations**: In-memory limits are ephemeral and scoped to a single process. Restarting the server resets rate counters. If deployed across multiple worker processes or load-balanced containers, limits are tracked per instance rather than globally.
- **Redis Engine (Extensible for Multi-Instance Deployments)**:
  - Enabled simply by setting `REDIS_URL`. Uses atomic Redis Sorted Sets (ZSET) with millisecond precision sliding windows across all horizontal replicas.

### CORS & Server-to-Server Architecture
- The retrieval workflow is server-to-server (`local FastAPI backend` -> `hosted retrieval API`).
- Unrestricted wildcard CORS (`*`) is **disabled by default**. `cors_origins` defaults to empty, preventing arbitrary third-party browser apps from cross-origin querying.
- If browser access is needed, specific domains can be configured in `CORS_ORIGINS`.

### Reverse Proxy & Anti-Spoofing
Client IPs are resolved using `TRUSTED_PROXIES`.
- Direct requests without a trusted proxy use `request.client.host`.
- Untrusted peers cannot forge client identity by injecting `X-Forwarded-For`.
- Only when connecting through a configured trusted proxy is `X-Forwarded-For` inspected from right to left, stopping at the first untrusted upstream IP.

---

## 6. HTTP Status Codes & Error Handling

| Code | Reason | Example Detail |
| :--- | :--- | :--- |
| `200` | Successful retrieval | Structured chunks returned |
| `400` | Validation error | Query empty, query >1000 chars, top_k > 10, or extra unknown fields |
| `403` | Ingestion attempted in USER mode | Playlist ingestion is disabled in USER mode. |
| `429` | Rate limit exceeded | Rate limit exceeded. Please retry after X seconds. |
| `503` | Qdrant unavailable or concurrency saturated | Knowledge base vector store is currently unavailable. |
| `504` | Request timed out | Retrieval processing timed out. |
| `500` | Internal server error | An unexpected error occurred during request processing. |

*All internal stack traces, database parameters, and credentials are intentionally stripped from error responses.*

---

## 7. Environment Variables

### 7.1. Hosted Server Environment
Configured on the central server hosting the retrieval API:

```env
# Server Network Settings
HOST=0.0.0.0
PORT=8001
ENVIRONMENT=production

# Qdrant Cloud Cluster Credentials (Read-only access)
QDRANT_URL=https://your-cluster-url.cloud.qdrant.io
QDRANT_API_KEY=your_qdrant_api_key_here
QDRANT_COLLECTION_NAME=revision_chunks
QDRANT_TIMEOUT_SECONDS=10.0

# Embedding Model (Exact ingestion model: google/embeddinggemma-2)
EMBEDDING_MODEL_NAME=google/embeddinggemma-2
EMBEDDING_DEVICE=auto

# Rate Limiting (In-memory default; Redis optional via REDIS_URL)
RATE_LIMIT_PER_MINUTE=10
RATE_LIMIT_PER_HOUR=100
MAX_QUERY_LENGTH=1000
MAX_TOP_K=10
MAX_CONCURRENT_REQUESTS=10
REQUEST_TIMEOUT_SECONDS=15.0

# Network & Security (Server-to-server: CORS is empty by default)
TRUSTED_PROXIES=127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
# CORS_ORIGINS=https://app.example.com
```

### 7.2. User's Local Environment
Configured in the user's local `.env`:

```env
# Mandatory mode for local users
APP_MODE=USER

# Groq API Key (Kept exclusively on local machine)
GROQ_API_KEY=gsk_your_groq_api_key_here

# Central retrieval API endpoint (MANDATORY in USER mode)
RETRIEVAL_API_URL=https://your-retrieval-api.example.com/api/v1/retrieve
```

---

## 8. Deployment Guidelines

### 8.1. Standalone Host Service (No Docker Required)
The retrieval service runs directly on the host using Python 3.12+ and `uvicorn`. Docker is not required:

```bash
cd retrieval_service
cp .env.example .env
# Edit .env with your QDRANT_URL and QDRANT_API_KEY
python3 -m uvicorn retrieval_service.main:app --host 0.0.0.0 --port 8001
```

### 8.2. Reverse Proxy (Nginx + Let's Encrypt TLS)
In production, place the service behind Nginx or Cloudflare with TLS encryption:

```nginx
server {
    server_name api-revision.example.com;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }

    listen 443 ssl http2;
    ssl_certificate /etc/letsencrypt/live/api-revision.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api-revision.example.com/privkey.pem;
}
```
