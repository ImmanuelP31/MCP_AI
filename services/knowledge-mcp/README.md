# Knowledge MCP Server

Owns the knowledge repository abstraction for manuals, SOPs, troubleshooting procedures, configuration guides, and engineering documents.

Seeded documents are fictional/demo engineering documentation for the simulator environment.
They are not actual company documentation. Search is keyword based today and sits behind a
replaceable backend interface for later semantic/vector retrieval without MCP contract changes.

The initial implementation will use seeded local documents behind an interface that can later target S3, SharePoint, Confluence, OpenSearch/vector search, or another enterprise source.
