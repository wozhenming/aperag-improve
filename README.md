# ApeRAG
[![Trust Score](https://archestra.ai/mcp-catalog/api/badge/quality/apecloud/ApeRAG)](https://archestra.ai/mcp-catalog/apecloud__aperag)

![HarryPotterKG2.png](docs%2Fen-US%2Fimages%2FHarryPotterKG2.png)

![chat2.png](docs%2Fen-US%2Fimages%2Fchat2.png)


ApeRAG is a production-ready RAG (Retrieval-Augmented Generation) platform that combines Graph RAG, vector search, and full-text search with advanced AI agents. Build sophisticated AI applications with hybrid retrieval, multimodal document processing, intelligent agents, and enterprise-grade management features.

ApeRAG is the best choice for building your own Knowledge Graph, Context Engineering, and deploying intelligent AI agents that can autonomously search and reason across your knowledge base.

[阅读中文文档](README-zh.md)

- [Quick Start](#quick-start)
- [Key Features](#key-features)
- [Docker Compose Deployment](#docker-compose-deployment)
- [Production & Test Environments](#production--test-environments)
- [MCP (Model Context Protocol) Support](#mcp-model-context-protocol-support)
- [Ontology (OWL) Management](#ontology-owl-management)
- [Kubernetes Deployment](#kubernetes-deployment-recommended-for-production)
- [Development](./docs/en-US/development-guide.md)
- [Build Docker Image](./docs/en-US/build-docker-image.md)
- [Acknowledgments](#acknowledgments)
- [License](#license)

## Quick Start

> Before installing ApeRAG, make sure your machine meets the following minimum system requirements:
>
> - CPU >= 2 Core
> - RAM >= 4 GiB
> - Docker & Docker Compose

The easiest way to start ApeRAG is through Docker Compose. Before running the following commands, make sure that [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) are installed on your machine:

```bash
git clone https://github.com/apecloud/ApeRAG.git
cd ApeRAG
cp envs/env.template .env
docker-compose up -d --build
```

The frontend is compiled **inside Docker** (multi-stage build: `yarn install` → `next build` inside the container), so no local build artifacts need to be copied to the server. After running, you can access ApeRAG in your browser at:

- **Web Interface**: http://localhost:3010
- **API Documentation**: http://localhost:8010/docs

## Key Features

**1. Advanced Index Types**:
Five comprehensive index types for optimal retrieval: **Vector**, **Full-text**, **Graph**, **Summary**, and **Vision** - providing multi-dimensional document understanding and search capabilities.

**2. Intelligent AI Agents**:
Built-in AI agents with MCP (Model Context Protocol) tool support that can automatically identify relevant collections, search content intelligently, and provide web search capabilities for comprehensive question answering.

**3. Enhanced Graph RAG with Entity Normalization**:
Deeply modified LightRAG implementation with advanced entity normalization (entity merging) for cleaner knowledge graphs and improved relational understanding.

**4. Multimodal Processing & Vision Support**:
Complete multimodal document processing including vision capabilities for images, charts, and visual content analysis alongside traditional text processing.

**5. Hybrid Retrieval Engine**:
Sophisticated retrieval system combining Graph RAG, vector search, full-text search, summary-based retrieval, and vision-based search for comprehensive document understanding.

**6. MinerU Integration (Cloud & Self-Hosted)**:
Advanced document parsing service powered by MinerU. Supports both the official cloud API (token-based) and **self-hosted MinerU deployments** (local API protocol via `POST /file_parse`, no cloud token required). A connection check button in the admin settings verifies service reachability before use.

**7. Ontology (OWL) Management**:
Full OWL ontology lifecycle built in:
- **My Ontology Library** ("我的知识库本体"): import `.owl` files, or create ontologies via AI-guided chat (Ontology Engineer bot) or from scratch
- **Visual ontology editor**: add/rename/delete classes, object properties (with domain/range/inverse) and data properties (with XSD types and functional flags) — no XML editing required, with a live Mermaid diagram preview
- **Protégé integration**: upload OWL 2 (RDF/XML) or Turtle ontologies and attach them to a collection's KG extraction via a dropdown picker
- **Format conversion on export**: download as OWL 2 (RDF/XML) or Turtle (`.ttl`), converting the stored content automatically

**8. Web Content Retrieval Enhancements**:
`web_read` supports **POST/AJAX endpoints** (form or JSON bodies, custom headers) for JS-rendered pages, appends an in-page **link list** to enable multi-hop retrieval (follow sidebar/sub-page links), and falls back to content-container extraction when page structure is unsemantic.

**9. Production-Grade Deployment**:
- Docker Compose deployment with separate **production and test environments** (`docker-compose.yml` + `docker-compose.test.yml`)
- Full Kubernetes support with Helm charts and KubeBlocks integration for production-grade databases (PostgreSQL, Redis, Qdrant, Elasticsearch, Neo4j)

**10. Enterprise Management**:
Built-in audit logging, LLM model management, graph visualization, comprehensive document management interface, and agent workflow management.

**11. MCP Integration**:
Full support for Model Context Protocol (MCP), including site-catalog browsing tools (`scm_list` / `list_scm_categories`) for structured retrieval from specific websites.

**12. Developer Friendly**:
FastAPI backend, React frontend, async task processing with Celery, extensive testing, comprehensive development guides, and agent development framework for easy contribution and customization.

## Docker Compose Deployment

> **Recommended for production** — the deployed configuration in this repository

The `docker-compose.yml` in this repository is customized for this deployment:

| Service | Host port | Notes |
|---------|-----------|-------|
| **frontend** (Next.js) | `3010:3000` | Built inside Docker (multi-stage), no local artifacts needed |
| **api** (FastAPI) | `8010:8000` | REST API + MCP server + WebSocket |
| **celeryworker** | — | Document parsing, indexing, graph building |
| **celerybeat** | — | Periodic reconciliation tasks |
| **flower** | `5555` | Celery monitoring |
| **postgres / redis / qdrant / es** | — | Databases (pgvector, Redis, Qdrant, Elasticsearch) |

```bash
cp envs/env.template .env
docker-compose up -d --build
```

## Production & Test Environments

This project maintains **two isolated environments** on the same host:

```bash
# Production
docker compose -p aperag --env-file .env -f docker-compose.yml up -d --build

# Test
docker compose -p aperag-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml up -d --build
```

- Test environment uses `aperag-test-*` container names and separate ports (e.g. `3012`/`8012`), with local object storage (no S3) to avoid cross-environment conflicts
- Both environments are fully isolated (databases, Redis, object store paths)
- Frontend updates are picked up automatically by `--build` — **no manual copying of build artifacts**

## MCP (Model Context Protocol) Support

ApeRAG supports [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) integration, allowing AI assistants to interact with your knowledge base directly. After starting the services, configure your MCP client with:

```json
{
  "mcpServers": {
    "aperag-mcp": {
      "url": "http://localhost:8010/mcp/",
      "headers": {
        "Authorization": "Bearer your-api-key-here"
      }
    }
  }
}
```

**Authentication** (by priority):
1. **HTTP Authorization Header** (Recommended): `Authorization: Bearer your-api-key`
2. **Environment Variable** (Fallback): `APERAG_API_KEY=your-api-key`

**Important**: Use your deployed API origin if not local (e.g. `https://your-host/mcp/`). Replace `your-api-key-here` with a valid API key from your ApeRAG settings.

### Available MCP Tools

**Knowledge base tools**:
- `list_collections` — browse your knowledge collections
- `search_collection` — hybrid search (vector / full-text / graph / summary / vision)
- `search_chat_files` — search files uploaded in the current chat

**Web tools**:
- `web_search` — web search (JINA priority, DuckDuckGo fallback)
- `web_read` — read and extract web page content; supports **POST/AJAX endpoints** for JS-rendered pages:

  ```
  web_read(url_list=["https://www.scm.com.cn/search/news/"],
           method="POST",
           body={"key": "搜索关键字", "page": 1},
           body_type="form",
           extra_headers={"Referer": "https://www.scm.com.cn/search",
                          "X-Requested-With": "XMLHttpRequest"})
  ```

  Returned content includes an in-page **link list** (`## 页面内链接`) so the model can follow sub-page links for multi-hop retrieval.

**Site catalog tools** (structured browsing of specific websites, e.g. scm.com.cn 广东计量):
- `list_scm_categories` — list browsable categories of the site (article-list vs static pages)
- `scm_list(category, page, keyword)` — browse an article-list category (title/date/URL), driven by a site map (`aperag/websearch/scm/scm_site.yaml`)

## Ontology (OWL) Management

ApeRAG ships a complete ontology workflow for constraint-based knowledge graph extraction:

1. **My Ontology Library** (sidebar → 我的知识库本体): import `.owl` files or create new ontologies
2. **AI-guided creation**: the Ontology Engineer bot walks you through domain → classes → properties → relations, and emits **OWL 2 (RDF/XML) only** (Turtle / N-Triples / JSON-LD are rejected) with Chinese labels/comments
3. **From scratch**: create a blank ontology and build it in the **visual editor** — classes (with parents/hierarchy), object properties (domain/range/inverse), data properties (XSD types, functional) — with a live Mermaid diagram
4. **Attach to a collection**: the collection settings page's OWL field is a dropdown of your ontology library; the ontology then constrains KG entity/relation extraction
5. **Export**: download as OWL 2 (RDF/XML) or Turtle (`.ttl`) — content is converted, not just renamed

## Kubernetes Deployment (Recommended for Production)

> **Enterprise-grade deployment with high availability and scalability**

Deploy ApeRAG to Kubernetes using our provided Helm chart. This approach offers high availability, scalability, and production-grade management capabilities.

### Prerequisites

*   [Kubernetes cluster](https://kubernetes.io/docs/setup/) (v1.20+)
*   [`kubectl`](https://kubernetes.io/docs/tasks/tools/) configured and connected to your cluster
*   [Helm v3+](https://helm.sh/docs/intro/install/) installed

### Clone the Repository

First, clone the ApeRAG repository to get the deployment files:

```bash
git clone https://github.com/apecloud/ApeRAG.git
cd ApeRAG
```

### Step 1: Deploy Database Services

ApeRAG requires PostgreSQL, Redis, Qdrant, and Elasticsearch. You have two options:

**Option A: Use existing databases** - If you already have these databases running in your cluster, edit `deploy/aperag/values.yaml` to configure your database connection details, then skip to Step 2.

**Option B: Deploy databases with KubeBlocks** - Use our automated database deployment (database connections are pre-configured):

```bash
# Navigate to database deployment scripts
cd deploy/databases/

# (Optional) Review configuration - defaults work for most cases
# edit 00-config.sh

# Install KubeBlocks and deploy databases
bash ./01-prepare.sh          # Installs KubeBlocks
bash ./02-install-database.sh # Deploys PostgreSQL, Redis, Qdrant, Elasticsearch

# Monitor database deployment
kubectl get pods -n default

# Return to project root for Step 2
cd ../../
```

Wait for all database pods to be in `Running` status before proceeding.

### Step 2: Deploy ApeRAG Application

```bash
# If you deployed databases with KubeBlocks in Step 1, database connections are pre-configured
# If you're using existing databases, edit deploy/aperag/values.yaml with your connection details

# Deploy ApeRAG
helm install aperag ./deploy/aperag --namespace default --create-namespace

# Monitor ApeRAG deployment
kubectl get pods -n default -l app.kubernetes.io/instance=aperag
```

### Configuration Options

**Resource Requirements**: By default, includes [`doc-ray`](https://github.com/apecloud/doc-ray) service (requires 4+ CPU cores, 8GB+ RAM). To disable: set `docray.enabled: false` in `values.yaml`.

**Advanced Settings**: Review `values.yaml` for additional configuration options including images, resources, and Ingress settings.

### Access Your Deployment

Once deployed, access ApeRAG using port forwarding:

```bash
# Forward ports for quick access
kubectl port-forward svc/aperag-frontend 3000:3000 -n default
kubectl port-forward svc/aperag-api 8000:8000 -n default

# Access in browser
# Web Interface: http://localhost:3000
# API Documentation: http://localhost:8000/docs
```

For production environments, configure Ingress in `values.yaml` for external access.

### Troubleshooting

**Database Issues**: See `deploy/databases/README.md` for KubeBlocks management, credentials, and uninstall procedures.

**Pod Status**: Check pod logs for any deployment issues:
```bash
kubectl logs -f deployment/aperag-api -n default
kubectl logs -f deployment/aperag-frontend -n default
```

## Acknowledgments

ApeRAG integrates and builds upon several excellent open-source projects:

### LightRAG
The graph-based knowledge retrieval capabilities in ApeRAG are powered by a deeply modified version of [LightRAG](https://github.com/HKUDS/LightRAG):
- **Paper**: "LightRAG: Simple and Fast Retrieval-Augmented Generation" ([arXiv:2410.05779](https://arxiv.org/abs/2410.05779))
- **Authors**: Zirui Guo, Lianghao Xia, Yanhua Yu, Tu Ao, Chao Huang
- **License**: MIT License

We have extensively modified LightRAG to support production-grade concurrent processing, distributed task queues (Celery/Prefect), and stateless operations. See our [LightRAG modifications changelog](./aperag/graph/changelog.md) for details.

## Community

* [Discord](https://discord.gg/FsKpXukFuB)
* [Feishu](docs%2Fen-US%2Fimages%2Ffeishu-qr-code.png)

<img src="docs/en-US/images/feishu-qr-code.png" alt="Feishu" width="150"/>

## Star History

![star-history-2025922.png](docs%2Fen-US%2Fimages%2Fstar-history-2025922.png)

## License

ApeRAG is licensed under the Apache License 2.0. See the [LICENSE](./LICENSE) file for details.
