# Live Validation Report

Generated during the final presentation-readiness pass.

## Summary

| Area | Status | Evidence |
| --- | --- | --- |
| GitHub token | Configured | `.env` contains a GitHub token; token value was not printed. |
| GitHub read smoke | Live validated | `get_latest_failed_build` reached `ImmanuelP31/MCP_AI` and returned no current failed run. |
| Controlled failing workflow | Implemented locally | `.github/workflows/demo-failing-build.yml`; requires push before live dispatch. |
| Repository-document RAG | Live validated | 34 bounded repository docs/workflows ingested. |
| OpenSearch RAG backend | Live validated | Query returned `index_backend: opensearch` with the controlled failing workflow as top result. |
| OpenAI planner | Blocked | Provider endpoint reached, but returned HTTP 401 with the configured key. |
| OpenAI embeddings | Blocked | Embedding endpoint reached, but returned HTTP 401 with the configured key. |
| 30-50 live LLM benchmark | Blocked | Cannot run honestly until OpenAI authentication succeeds. |
| Hashing vs real embedding comparison | Partially blocked | Hashing baseline is available; real OpenAI embedding run is blocked by HTTP 401. |

## OpenSearch RAG Evidence

Command:

```powershell
$env:KNOWLEDGE_INDEX_BACKEND="opensearch"
$env:EMBEDDING_PROVIDER="hashing"
$env:OPENSEARCH_URL="http://localhost:9200"
python scripts/ingest_repo_docs.py --query "GitHub controlled failing build approval" --top-k 5
```

Measured output summary:

- Documents ingested: 34
- Index backend: `opensearch`
- Top citation: `REPO-GITHUB-WORKFLOWS-DEMO-FAILING-BUILD-YML`
- Top source: `local-repository:.github/workflows/demo-failing-build.yml`
- Top score: `1.0`

## OpenAI Failure Analysis

The OpenAI key was present in `.env`, but both provider endpoints rejected it:

- Planner endpoint: HTTP 401
- Embeddings endpoint: HTTP 401

This is an authentication/configuration failure, not an LLM quality result. The benchmark runner
correctly records provider failures instead of fabricating successful model metrics.

## Required Rerun After Key Rotation

After replacing `OPENAI_API_KEY` with a valid key:

```powershell
$env:LLM_PLANNER_PROVIDER="openai"
$env:EMBEDDING_PROVIDER="openai"
python -m evaluation.run --config semantic_rag_graph --mode real --limit 30
```

For the retrieval comparison:

```powershell
$env:EMBEDDING_PROVIDER="hashing"
python -m evaluation.run --config semantic_rag_graph --mode mock --limit 50

$env:EMBEDDING_PROVIDER="openai"
python -m evaluation.run --config semantic_rag_graph --mode real --limit 50
```

Report both successful and failed cases. Do not compare mock hashing results directly against live
LLM results without labeling the different execution modes.
