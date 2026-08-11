from __future__ import annotations

import argparse
import json
from pathlib import Path

from mcp_ops_ai_agent.engineering_rag import (
    EngineeringKnowledgeSearchRequest,
    EngineeringRagService,
)
from mcp_ops_ai_agent.engineering_rag.repo_docs import repository_engineering_documents


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect repository-document RAG ingestion.")
    parser.add_argument("--root", default=".", help="Repository root. Defaults to current folder.")
    parser.add_argument("--query", default="GitHub failed build workflow approval demo")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    documents = repository_engineering_documents(root)
    service = EngineeringRagService(documents=documents)
    response = service.search(
        EngineeringKnowledgeSearchRequest(query=args.query, top_k=args.top_k)
    )
    print(
        json.dumps(
            {
                "root": str(root),
                "documents_ingested": len(documents),
                "index_backend": response.index_backend,
                "query": args.query,
                "results": [
                    {
                        "citation_id": result.citation_id,
                        "title": result.chunk.metadata.title,
                        "source": result.chunk.metadata.source,
                        "score": result.combined_score,
                    }
                    for result in response.results
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
