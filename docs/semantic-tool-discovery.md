# Semantic MCP Tool Discovery

Semantic tool discovery limits the tools exposed to AI planning. A natural-language engineering
request is matched against normalized MCP tool metadata, ranked with hybrid retrieval, filtered by
policy/RBAC, and returned as a planner-safe subset.

## Flow

```text
natural-language request
-> normalized MCP tool registry
-> embedding index
-> semantic retrieval
-> lexical and metadata scoring
-> policy/RBAC pre-filter
-> top-k tools for planner/debug UI
```

The implementation is intentionally engineering-focused. It supports CI/CD, repository, deployment,
ticket, documentation, service ownership, device, diagnostics, and knowledge workflows. It does not
add cybersecurity SOC or attack-detection behavior.

## Implementation

Core files:

- `packages/policy/src/mcp_ops_policy/tool_registry.py`
- `services/ai-agent/src/mcp_ops_ai_agent/tool_discovery/models.py`
- `services/ai-agent/src/mcp_ops_ai_agent/tool_discovery/embeddings.py`
- `services/ai-agent/src/mcp_ops_ai_agent/tool_discovery/index.py`
- `services/ai-agent/src/mcp_ops_ai_agent/tool_discovery/retrieval.py`
- `services/ai-agent/src/mcp_ops_ai_agent/tool_discovery/service.py`
- `services/ai-agent/src/mcp_ops_ai_agent/tool_discovery/evaluation.py`
- `services/ai-agent/benchmarks/tool_discovery_benchmark.json`

The registry now exposes normalized fields:

- `tool_name`
- `description`
- `server`
- `category`
- `risk_level`
- `required_permission`
- `required_roles`
- `input_schema`
- `tags`
- `executable`

Catalog-only engineering tools are discoverable for planning, but marked `executable=false` until
their MCP servers exist. The gateway rejects non-executable catalog entries.

## Retrieval

The retrieval service combines:

- deterministic feature-hashing retrieval baseline from `HashingEmbeddingProvider`
- provider-backed embeddings from `GeminiEmbeddingProvider`
- lexical/BM25-style scoring
- metadata boosts for tags, category, and tool name
- server/category filters
- role and policy filtering

OpenSearch is supported through `OpenSearchToolEmbeddingIndex`. When
`TOOL_DISCOVERY_INDEX_BACKEND=opensearch`, normalized MCP tool documents are indexed into
`OPENSEARCH_TOOL_INDEX` and searched through OpenSearch lexical scoring. If OpenSearch is
unavailable, retrieval falls back to the deterministic in-memory index.

Provider switches:

```env
EMBEDDING_PROVIDER=hashing
TOOL_DISCOVERY_INDEX_BACKEND=memory
```

Live demo switches:

```env
EMBEDDING_PROVIDER=gemini
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
TOOL_DISCOVERY_INDEX_BACKEND=opensearch
```

## API

Endpoint:

```http
POST /api/v1/ai/tool-discovery
```

Example request:

```json
{
  "query": "Why did the latest deployment fail?",
  "top_k": 8,
  "role": "ENGINEER"
}
```

Response includes ranked tools, semantic score, lexical score, combined score, risk, authorization
status, server, category, and retrieval explanation.

Benchmark endpoint:

```http
GET /api/v1/ai/tool-discovery/evaluate?top_k=5
```

## Frontend

The debug view is available at:

```text
/tool-discovery
```

It lets a developer enter an engineering request and inspect retrieved tools, ranking, scores, MCP
server, risk, and authorization status.

## Metrics

Prometheus metrics:

- `mcp_tool_discovery_requests_total`
- `mcp_tool_discovery_latency_seconds`
- `mcp_tool_discovery_results_total`
- `mcp_tool_discovery_empty_results_total`

## Evaluation

The benchmark dataset contains 50 engineering requests mapped to expected tools. Evaluation reports:

- Recall@K
- Precision@K
- Mean Reciprocal Rank

Run through Python:

```powershell
python -m pytest tests/unit/test_tool_discovery.py
python -m evaluation.run --config semantic_rag_graph --mode real --limit 3
```

Real-mode evaluation requires a valid provider key and must not silently fall back to hashing. The
deterministic hashing provider remains the CI fallback and should be used for normal unit tests.
