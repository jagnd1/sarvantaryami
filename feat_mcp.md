# MCP Integration Design - Sarvantaryamin as Generic MCP Server

**Status**: Proposed
**Prerequisites**: OpenAPI spec path configurable, API agent auth support (optional but recommended)
**Goal**: Expose Sarvantaryamin's capabilities as a single MCP tool for Claude Desktop/Code

---

## 1. Vision

Transform Sarvantaryamin from a standalone FastAPI service into a **Model Context Protocol (MCP) server** that provides "Bring Your Own Backend" (BYOE) AI integration. This allows Claude Desktop/Code users to:

- Query their **SQL databases** (PostgreSQL, etc.)
- Call **any REST API** that has an OpenAPI/Swagger spec
- Perform **document Q&A** on uploaded files
- Get **general conversational** responses

All through a **single MCP tool** (`ask`) that internally routes to the appropriate agent.

---

## 2. Why This Makes Sense

### Current State
- Already has intelligent router (`SarvantaryamiAgent._decide_next_node`)
- Each agent (SQL, API, RAG, General) is self-contained
- Configuration-driven (OpenAPI spec path, DB URI, Qdrant, Ollama)
- Clean separation between `usecase` and `adapters`

### MCP Alignment
MCP servers expose **tools** and **resources** to LLMs. Our system already:
- ✅ Has tools (SQL execution, API calls, RAG search)
- ✅ Has resources conceptually (DB schema, OpenAPI spec, document store)
- ✅ Performs intelligent routing (so we only need ONE MCP tool)
- ✅ Runs locally (MCP prefers local servers)

### Differentiation
Most MCP servers are **static wrappers** around specific APIs. This would be **dynamic** - it reads OpenAPI specs at runtime and adapts to any backend.

---

## 3. Proposed MCP Interface

### Tools (only 1 needed)

```json
{
  "name": "ask",
  "description": "Route a natural language query to the appropriate backend capability. Automatically selects: SQL database queries, REST API calls (via OpenAPI spec), document Q&A from uploaded files, or general conversation.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Natural language query about database data, API endpoints, documents, or general topics"
      }
    },
    "required": ["query"]
  }
}
```

**Rationale for single tool:**
- Router already implements semantic + keyword routing
- Exposing separate tools (`sql_query`, `api_call`, `rag_search`, `chat`) would leak implementation details
- Simpler MCP configuration
- Claude can formulate any query naturally without needing to know which agent to use

**Alternative (not recommended):** Separate tools would give Claude explicit control but:
- Requires understanding of when to use which tool
- Duplicates routing logic
- Makes MCP config more complex

### Optional Resources (future)

Could expose metadata as readable resources:

- `openapi://spec` - Current OpenAPI spec (JSON)
- `openapi://summaries` - List of available operations with summaries
- `database://schema` - Database tables and columns
- `documents://indexed` - List of uploaded documents
- `documents://status` - Qdrant collection stats

**Not needed initially** - Claude can ask `ask("what APIs are available?")` and the LLM can introspect.

---

## 4. Architecture Changes

### Current Architecture
```
Claude → HTTP (FastAPI) → AgentUseCase → Router → [SQL|API|RAG|General]
```

### Proposed Architecture (MCP Mode)
```
Claude Desktop → MCP (stdio/SSE) → MCPServer → AgentUseCase → Router → [SQL|API|RAG|General]
```

**Key points:**
- Reuse existing `AgentUseCase` and all agents **unchanged**
- Add new `mcp_server/` package with MCP entry point
- Keep existing FastAPI for HTTP mode (optional, can run either or both)
- Configuration via environment variables (same `.env` file)

---

## 5. Implementation Steps

### Phase 1: Prerequisites (Blocking)

#### 5.1 Make OpenAPI Spec Path Configurable
**Why**: Current code hardcodes `"infrastructure/openapi.json"` in `api_agent.py:76`

**Change**:
```python
# infrastructure/config.py
class Settings(BaseSettings):
    # ... existing fields ...
    OPENAPI_SPEC_PATH: str = "infrastructure/openapi.json"

# api_agent.py
from infrastructure.config import settings
openapi_manager = OpenApiManager(settings.OPENAPI_SPEC_PATH)
```

**Impact**: Allows users to point to their own OpenAPI spec via env var.

#### 5.2 Optional: API Agent Authentication Support
**Why**: Current `call_api_endpoint` tool (api_agent.py:114-159) has **no auth**. Most enterprise APIs require Bearer tokens, API keys, etc.

**Options**:
- **A. Static auth via env vars**: Set `API_AUTH_HEADER: str = "Authorization: Bearer $TOKEN"` and inject into every call
- **B. Per-operation auth from OpenAPI**: Parse `securitySchemes` and `security` fields, prompt user for credentials at first call
- **C. Pass auth context in tool call**: Extend `call_api_endpoint` with optional `auth_override` param

**Recommended (A)** for MVP: Simple env-based header injection. User sets `API_AUTH_HEADER` in `.env`. The tool adds it to every request.

**Implementation**:
```python
# api_agent.py
from infrastructure.config import settings

@tool
def call_api_endpoint(operation_id: str, ...):
    # ... existing code ...
    headers = {}
    if settings.API_AUTH_HEADER:
        key, value = settings.API_AUTH_HEADER.split(":", 1)
        headers[key.strip()] = value.strip()

    if method == "GET":
        resp = requests.get(url, params=query_params, headers=headers)
    # ...
```

If auth not needed (public APIs), leave `API_AUTH_HEADER` empty.

**Complex solution (B)**: Would require storing credential state, handling OAuth flows - out of scope for MVP.

---

### Phase 2: MCP Server Implementation

#### 5.3 Add `mcp` Dependency
```bash
pip install mcp
```

Add to `requirements.txt`:
```
mcp>=0.9.0
```

#### 5.4 Create `mcp_server/server.py`

```python
#!/usr/bin/env python3
"""
MCP Server for Sarvantaryamin - Bring Your Own Backend AI Assistant

Exposes a single 'ask' tool that routes queries to SQL, API, RAG, or General agents.
"""
import asyncio
import logging
from mcp import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, EmbeddedResource

from infrastructure.config import settings
from usecase.agent_usecase import AgentUseCase
from adapters.agents.lc_agent import SarvantaryamiAgent

logger = logging.getLogger(__name__)

# Initialize agents (reuse singleton pattern from web/dependencies.py)
_agent_instance = SarvantaryamiAgent()
_usecase_instance = AgentUseCase(_agent_instance)

# Create MCP server
server = Server(
    name="sarvantaryami",
    version="1.0.0",
    instructions=(
        "Sarvantaryamin is an AI assistant that routes queries to appropriate backends: "
        "SQL databases, REST APIs (via OpenAPI spec), document search, or general chat. "
        "Use the 'ask' tool to interact with your enterprise systems."
    )
)

@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return available tools."""
    return [
        Tool(
            name="ask",
            description=(
                "Send a natural language query to the AI assistant. The system automatically "
                "routes your query to the appropriate backend:\n"
                "• **SQL**: Database queries ('count users', 'show latest transactions')\n"
                "• **API**: REST API calls based on OpenAPI spec ('get currency details', 'create user')\n"
                "• **RAG**: Document search from uploaded files ('how does protocol X work?')\n"
                "• **General**: Conversation, explanations, creative tasks\n\n"
                "Configure your backend via environment variables:\n"
                f"- OpenAPI spec: `{settings.OPENAPI_SPEC_PATH or 'not set'}`\n"
                f"- Database: `{settings.DB_URI.split('@')[0]}@...`\n"
                f"- LLM: {settings.LLM_MODEL}\n"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Your natural language query about databases, APIs, documents, or any topic"
                    }
                },
                "required": ["query"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent | EmbeddedResource]:
    """Handle tool calls."""
    if name != "ask":
        raise ValueError(f"Unknown tool: {name}")

    query = arguments.get("query")
    if not query:
        raise ValueError("Missing required argument: query")

    try:
        logger.info(f"MCP tool call: ask(query='{query[:100]}...')")
        result = await _usecase_instance.ask(query)
        return [TextContent(type="text", text=str(result))]
    except Exception as e:
        logger.error(f"Error in ask tool: {e}", exc_info=True)
        return [TextContent(type="text", text=f"Error: {str(e)}")]

async def main():
    """Run the MCP server over stdio."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    logger.info("Starting Sarvantaryami MCP Server...")
    logger.info(f"OpenAPI spec: {settings.OPENAPI_SPEC_PATH}")
    logger.info(f"Database: {settings.DB_URI.split('@')[0]}@...")
    logger.info(f"LLM: {settings.LLM_MODEL}")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="sarvantaryami",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    read_stream, write_stream, InitializationOptions(
                        server_name="sarvantaryami",
                        server_version="1.0.0"
                    )
                )
            )
        )

if __name__ == "__main__":
    asyncio.run(main())
```

**Notes:**
- Uses `stdio_server()` for Claude Desktop compatibility
- Reuses same `AgentUseCase` singleton pattern from `web/dependencies.py`
- Logs startup config to help debugging
- Returns `TextContent` only (no embedded resources yet)

#### 5.5 Add Setup Entry Point (Optional)

If using `pyproject.toml`:

```toml
[project.scripts]
sarvantaryami-mcp = "mcp_server.server:main"
sarvantaryami-server = "web.main:main"  # existing FastAPI
```

Or just run directly: `python -m mcp_server.server`

#### 5.6 Update `.env.example`

```ini
# MCP Server Mode (set to 'true' to enable MCP-specific logging)
# MCP_ENABLED=true

# Existing settings...
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=llama3.2:3b
EMBEDDING_MODEL=nomic-embed-text
DB_URI=postgresql+psycopg2://entity:password@localhost:5434/entdb
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=rag_collection

# NEW: Configurable OpenAPI spec path (default: infrastructure/openapi.json)
OPENAPI_SPEC_PATH=infrastructure/openapi.json

# NEW: Optional API auth header (format: "Authorization: Bearer $TOKEN")
# API_AUTH_HEADER=
```

---

### Phase 3: Testing & Documentation

#### 5.7 Test MCP Server Locally

**Manual test with mcp CLI** (if available):

```bash
# In one terminal, start Ollama and Qdrant (docker-compose up)
# In another, set env and run server:
OPENAPI_SPEC_PATH=/path/to/spec.json DB_URI=... python -m mcp_server.server

# In another, use mcp inspector or client to call:
mcp call ask '{"query": "count all users"}'
```

**Simulate stdin/stdout**:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"ask","arguments":{"query":"hello"}}}' | python -m mcp_server.server
```

#### 5.8 Claude Desktop Configuration

```json
{
  "mcpServers": {
    "enterprise-backend": {
      "command": "/path/to/sarvantaryami/bin/sarvantaryami-mcp",
      "env": {
        "OPENAPI_SPEC_PATH": "/path/to/your/openapi.json",
        "DB_URI": "postgresql://user:pass@localhost:5432/entdb",
        "OLLAMA_BASE_URL": "http://localhost:11434",
        "LLM_MODEL": "llama3.1:8b-instruct"
      }
    }
  }
}
```

Restart Claude Desktop. The `ask` tool should appear.

#### 5.9 Documentation (`MCP.md`)

Document:
- What the MCP server does
- Required environment variables
- How to obtain OpenAPI spec from backend
- How to configure authentication
- Troubleshooting (Ollama not running, Qdrant connection, etc.)
- Example queries

---

## 6. Gaps & Limitations

### 6.1 API Authentication (Current Gap)
**Problem**: `call_api_endpoint` doesn't send any authentication headers.

**Impact**: MCP server can only call **public APIs** or APIs that don't require auth.

**Solutions**:
1. **Static header injection** (simple): Set `API_AUTH_HEADER="Authorization: Bearer <token>"`
2. **Per-API credentials** (medium): Parse OpenAPI `securitySchemes`, store in config
3. **Dynamic auth prompts** (complex): Agent asks user for credentials when needed, caches in memory

**Recommendation**: Implement (1) first, document limitation, later add (2).

### 6.2 Uploading Documents via MCP
**Problem**: `upload_doc` endpoint accepts `multipart/form-data` (file upload). MCP tool arguments are JSON, not files.

**Options**:
- **A. Skip upload tool for MCP**: Users upload via standalone FastAPI server only
- **B. Base64 encoding**: Accept `filename` and `content_base64` arguments, decode in tool
- **C. Resource URIs**: Accept `file://path` if file already on server filesystem

**Recommendation**: **Skip for MVP**. Document that RAG requires the FastAPI server or manual Qdrant ingestion. The `ask` tool can only query already-indexed docs.

**Future**: Add `upload_document` MCP tool that accepts base64-encoded file content.

### 6.3 Session State & Memory
**Problem**: MCP tools are stateless. If user needs to maintain context across calls (e.g., "use that same API token from earlier"), not supported.

**Impact**: Low - `ask` is designed as independent queries.

### 6.4 Streaming Responses
**Problem**: MCP supports streaming but our `usecase.ask()` returns a single string.

**Impact**: Long-running queries (large doc retrieval, complex SQL) will buffer until complete.

**Not a priority** - acceptable for MVP.

### 6.5 Resource Control
**Problem**: MCP doesn't define quotas, rate limits, or cost controls.

**Impact**: User can spam queries, exhausting local resources (Ollama memory, DB connections).

**Mitigation**: Document that this is a local development tool, not production multi-tenant.

---

## 7. Configuration Strategy

### Environment Variables (all optional except where noted)

| Variable | Default | Required | Purpose |
|----------|---------|----------|---------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | ✅ | Ollama API endpoint |
| `LLM_MODEL` | `llama3.2:3b` | ✅ | Model for reasoning |
| `EMBEDDING_MODEL` | `nomic-embed-text` | ✅ | Embeddings for vector search |
| `DB_URI` | (none) | ⚠️ | PostgreSQL connection string. **Required for SQL agent**. |
| `QDRANT_HOST` | `localhost` | ✅ | Qdrant server |
| `QDRANT_PORT` | `6333` | ✅ | Qdrant port |
| `QDRANT_COLLECTION` | `rag_collection` | ✅ | Collection name |
| `OPENAPI_SPEC_PATH` | `infrastructure/openapi.json` | ⚠️ | Path to OpenAPI spec. **Required for API agent**. |
| `API_AUTH_HEADER` | (empty) | ❌ | Optional auth header, e.g., `"Authorization: Bearer $TOKEN"` |

**Validation**: Startup should log warnings if DB_URI or OPENAPI_SPEC_PATH are missing, but don't fail - agents will gracefully degrade (API agent will have no endpoints, SQL agent will error on query).

---

## 8. Testing Plan

### Unit Tests (if adding)
- `mcp_server/test_server.py`:
  - Mock `AgentUseCase.ask()` and verify tool returns expected format
  - Test `list_tools()` returns exactly one tool named "ask"
  - Test error handling when query is missing

### Integration Test
1. Start Ollama: `ollama serve`
2. Pull model: `ollama pull llama3.2:3b`
3. Start Qdrant: `docker run -p 6333:6333 qdrant/qdrant`
4. Set env: `OPENAPI_SPEC_PATH=test/spec.json DB_URI=postgresql://...`
5. Run: `python -m mcp_server.server`
6. Use MCP inspector or Claude Desktop to call `ask("hello")`
7. Verify response arrives

### Manual Validation Checklist
- [ ] MCP server starts without errors when Ollama is running
- [ ] `tools/list` returns the `ask` tool
- [ ] `tools/call` with query returns text response
- [ ] SQL query (`"count users"`) executes against DB
- [ ] API query (`"get currency USD"`) hits the OpenAPI-defined endpoint
- [ ] RAG query (`"what is RFC 8894?"`) retrieves from uploaded docs
- [ ] General query (`"hello"`) gets direct LLM response
- [ ] Invalid query returns readable error (not crash)

---

## 9. Deployment Considerations

### Claude Desktop Installation

**Option A: Direct script**
```json
{
  "mcpServers": {
    "backend": {
      "command": "python",
      "args": ["/path/to/sarvantaryami/mcp_server/server.py"],
      "env": { ... }
    }
  }
}
```

**Option B: Installed package**
```bash
pip install -e .[mcp]  # installs sarvantaryami-mcp entry point
```

```json
{
  "mcpServers": {
    "backend": {
      "command": "sarvantaryami-mcp",
      "env": { ... }
    }
  }
}
```

### Packaging
- Add `[mcp]` extra in `pyproject.toml` or `setup.py`
- Include `mcp_server/` in `package_data`
- Consider separate wheel: `sarvantaryami-mcp`

---

## 10. Future Enhancements

### T0 (MVP)
- ✅ OpenAPI spec path configurable
- ✅ Basic MCP server with single `ask` tool
- ✅ API auth via static header
- ✅ Documentation

### T1 (Next)
- **Expose resources**: `openapi://spec`, `database://schema`, `documents://list`
- **Add upload tool**: Base64 file upload for RAG
- **Per-agent tools**: Expose `sql_query`, `api_call`, `rag_search` as separate MCP tools (optional, behind flag)
- **Streaming**: Stream LLM output as MCP progress notifications

### T2 (Advanced)
- **Dynamic auth**: Parse OpenAPI securitySchemes, prompt for credentials
- **Multi-spec support**: Load multiple OpenAPI specs, merge intents
- **Agent specialization**: Separate MCP tools for each agent with fine-grained schema descriptions
- **Observability**: Logging, metrics, tracing (OpenTelemetry)
- **Cost controls**: Query quotas, rate limiting

---

## 11. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| API auth gap blocks real-world use | High | High | Implement static header injection first, document clearly |
| OpenAPI spec with no operationIds | Medium | Medium | Document requirement, maybe auto-generate IDs from path+method |
| MCP protocol changes | Low | Medium | Use stable `mcp` package version |
| Performance (LLM latency) | High | Low | Acceptable for local use; document that queries may take 5-30s |
| SQL injection via LLM | Medium | High | Use read-only DB user; add SQL query validation (allowlist SELECT) |
| Concurrent MCP calls | Low | Medium | Agents aren't thread-safe yet; serialize calls or add locks |

---

## 12. Success Criteria

- [ ] `sarvantaryami-mcp` command starts and lists tools over MCP
- [ ] Claude Desktop can invoke `ask` tool successfully
- [ ] Queries route correctly to SQL, API, RAG, and General agents
- [ ] Configuration via environment variables works
- [ ] User documentation (MCP.md) complete with examples
- [ ] No code changes to existing agents (reuse only)

---

## 13. Open Questions

1. **Should we support multiple OpenAPI specs?** Currently single spec path. Could extend to comma-separated list or directory scan.
2. **Should `ask` return structured data for SQL queries?** Currently returns formatted string (table as text). Could return JSON for programmatic consumption, but MCP `TextContent` expects text anyway.
3. **How to handle uploads in stateless MCP?** If we add `upload_document` tool, need to decide: base64 in JSON (large), file path on server filesystem (security), or skip entirely.
4. **Should resources be exposed?** Useful for Claude to introspect available APIs without asking. Could add later if needed.

---

## 14. Estimated Effort

| Task | Complexity | Time |
|------|------------|------|
| Make OpenAPI path configurable | Low | 30 min |
| Add static API auth header | Low | 30 min |
| Write MCP server wrapper | Low | 2 hours |
| Update `.env.example` & docs | Low | 1 hour |
| Testing & bugfixes | Medium | 2 hours |
| **Total** | | **~6 hours** |

---

## 15. Recommendation

**Proceed with MVP**:
1. Implement configurable OpenAPI path (blocking)
2. Add static API auth header (bridging gap)
3. Build MCP wrapper with single `ask` tool
4. Document thoroughly

**Rationale**: This leverages existing sophisticated routing logic and makes it accessible to any Claude Desktop user with a backend. The BYOE value proposition is strong - users provide their own data and APIs, Sarvantaryami provides the AI reasoning and integration layer.

**Do not**: Over-engineer auth, multi-spec, or separate tools initially. Get the happy path working first.
