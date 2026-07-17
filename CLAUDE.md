# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此代码仓库中工作时提供指导。

## 项目概述

ApeRAG 是一个生产就绪的 **Agentic Graph RAG 平台** —— 由 FastAPI 后端 + Next.js 前端构成，结合了知识图谱、向量检索、全文检索和 AI 智能体。它能够导入文档，构建五种并行的索引类型，并通过 REST 和 MCP（模型上下文协议）接口公开混合检索能力。

## 开发命令

所有命令均使用 `make`，并通过 `uv` 管理 Python 依赖（需要 Python 3.11，由工具自动管理）。

### 环境搭建

```bash
cp envs/env.template .env           # 配置环境变量
make compose-infra                  # 启动数据库（PostgreSQL、Redis、Qdrant、Elasticsearch）
make dev                            # 安装 uv、创建 .venv、安装开发工具及 git hooks
source .venv/bin/activate           # 激活虚拟环境（Windows: .venv\Scripts\activate）
make install                        # 通过 uv sync + yarn 安装所有 Python 及前端依赖
make migrate                        # 向 PostgreSQL 应用 Alembic 迁移
```

### 运行服务（分别在不同终端中）

```bash
make run-backend    # FastAPI，地址 :8000，开启自动重载（uvicorn）
make run-celery     # Celery worker + beat（--pool=threads --concurrency=16）
make run-frontend   # Next.js 开发服务器，地址 :3000（yarn dev --turbopack）
```

### 代码质量

```bash
make format         # ruff check --fix + ruff format
make lint           # ruff check（仅检查不修复）+ ruff format --check
make static-check   # mypy 类型检查
```

Pre-commit 钩子（通过 `make dev` 安装）会在每次提交时运行 `make lint` + `make add-license`。如果 lint 检查失败或新增了许可证头，提交会被阻止——请运行 `make format` 并重新暂存。

### 测试

```bash
make test                              # 所有测试（单元测试 + 端到端测试）
make unit-test                         # 仅单元测试（tests/unit_test/）
make e2e-test                          # 端到端测试（需要运行中的服务）
uv run pytest tests/unit_test/test_file.py::TestClass::test_func -v  # 运行单个测试
uv run pytest tests/unit_test/ --cov=aperag --cov-report=html        # 带覆盖率报告
```

### API 与代码生成

```bash
make generate-models         # OpenAPI 规范 → Pydantic 模型（datamodel-codegen）
make generate-frontend-sdk   # OpenAPI 规范 → TypeScript API 客户端
make makemigration           # 根据模型变更自动生成 Alembic 迁移
```

### Docker

```bash
make compose-up                        # 通过 docker-compose 启动完整技术栈
make compose-up WITH_NEO4J=1           # 增加 Neo4j profile
make compose-up WITH_DOCRAY=1          # 增加 DocRay（高级 PDF 解析）
make compose-infra                     # 仅启动数据库（用于本地开发）
make compose-down REMOVE_VOLUMES=1     # 停止并删除所有数据
```

### 其他

```bash
make evaluate    # 运行 RAG 评估套件（aperag.evaluation.run）
make docs        # 将 docs/ 同步到 web/docs/
```

## 架构

### 服务架构

技术栈中包含五个运行时服务：

| 服务                   | 技术栈            | 角色                                                   |
| ---------------------- | ----------------- | ------------------------------------------------------ |
| **api**          | FastAPI + Uvicorn | REST API、MCP 服务器、WebSocket（SSE 流式传输）        |
| **celeryworker** | Celery            | 异步文档解析、索引构建、图谱构建                       |
| **celerybeat**   | Celery Beat       | 周期性协调任务（索引协调，每 60 秒至 3600 秒执行一次） |
| **frontend**     | Next.js 15        | React Web UI，地址 :3000                               |
| **flower**       | Flower            | Celery 监控面板，地址 :5555                            |

### 存储层

| 数据库                           | 用途                                                                  |
| -------------------------------- | --------------------------------------------------------------------- |
| **PostgreSQL**（pgvector） | 主数据库：用户、集合、文档、聊天历史，以及小规模知识图谱（<10万实体） |
| **Qdrant**                 | 向量嵌入，用于语义检索和视觉索引                                      |
| **Elasticsearch**          | 全文检索，支持 BM25 + IK 中文分词器                                   |
| **Neo4j**（可选）          | 大规模知识图谱（>100万实体）、图谱遍历                                |
| **Redis**                  | Celery 消息代理/结果后端、LLM 调用缓存、会话缓存                      |
| **MinIO / S3**             | 原始文档文件存储                                                      |

### 双链异步架构（索引）

这是核心设计模式，灵感来自 Kubernetes 的协调器模式：

- **前端链**（`aperag/index/manager.py`）：API 将期望状态写入数据库的 `document_indexes` 表（状态为 `PENDING`，递增 `version`），并在 100 毫秒内返回。永远不会阻塞等待实际的索引工作。
- **后端链**（`aperag/index/reconciler.py`）：Celery Beat 周期性执行 `reconcile_indexes_task`。协调器检测到 `observed_version < version` 的记录，并调度 Celery 任务执行实际工作（解析 → 分块 → 创建索引 → 更新状态）。

这意味着：如果你修改了与索引相关的 API 端点，它们只会设置状态。真正的处理逻辑位于 `aperag/tasks/` 中。

### 五种索引类型

每份文档最多会构建五种并行的索引，每一种都作为独立的 Celery 任务组来构建：

| 索引               | 存储             | 代码路径                                             |
| ------------------ | ---------------- | ---------------------------------------------------- |
| **向量索引** | Qdrant           | `aperag/index/vector_index.py`                     |
| **全文索引** | Elasticsearch    | `aperag/index/fulltext_index.py`                   |
| **图谱索引** | PostgreSQL/Neo4j | `aperag/index/graph_index.py` → `aperag/graph/` |
| **摘要索引** | PostgreSQL       | `aperag/index/summary_index.py`                    |
| **视觉索引** | Qdrant           | `aperag/index/vision_index.py`                     |

### 知识图谱（LightRAG）

图谱子系统（`aperag/graph/`）是 LightRAG 的**重度修改、无状态**分支：

- 每个文档索引任务会创建一个独立的 LightRAG 实例，按 `workspace` 隔离
- 实体命名使用 `entity:{name}:{workspace}`，防止跨租户污染
- 连通分量优化：图谱被划分为独立的子图并并行处理（吞吐量提升 2-3 倍）
- 实体合并/归一化处理等价实体的去重
- 支持 PostgreSQL 和 Neo4j 作为图谱存储后端

### 流程引擎（`aperag/flow/`）

用于智能体工作流的 DAG 执行引擎：

- 节点在 `NODE_RUNNER_REGISTRY` 中注册（参见 `aperag/flow/runners/`）
- `aperag/flow/engine.py` 中的 `FlowEngine` 负责编排 DAG 遍历，每一步都会发出 `FlowEvent` 事件
- 流程以 JSON/YAML 定义，包含节点和边；引擎解析拓扑顺序、检测循环并执行
- 被智能体聊天系统用于运行多步推理流水线

### 智能体系统（`aperag/agent/`）

基于 `mcp-agent` 框架构建：

- 智能体使用 MCP 工具（search_collection、web_search、web_read）进行工具调用循环
- 通过 `AgentEventListener` 实现 SSE 流式传输，将实时响应推送到前端
- 会话管理，带有生命周期钩子（`agent_session_manager_lifecycle.py`）
- 无状态 HTTP MCP 服务器挂载在 `/mcp`（FastMCP，`stateless_http=True`）

### API 设计模式

API 开发遵循严格的代码生成流水线：

1. **定义**：在 `aperag/api/paths/` 和 `aperag/api/components/schemas/` 中编辑 OpenAPI YAML 规范
2. **生成后端模型**：`make generate-models` → `aperag/schema/view_models.py`
3. **实现**：在 `aperag/views/` 中编写视图处理器，在 `aperag/service/` 中编写业务逻辑
4. **生成前端 SDK**：`make generate-frontend-sdk` → 在 `web/src/api/` 中生成 TypeScript 客户端

视图调用服务层，服务层调用数据库仓库（`aperag/db/repositories/`）；长时间运行的工作分发给 Celery 任务（`aperag/tasks/`）。

### 关键源码目录结构

```
aperag/
  app.py              FastAPI 应用创建、路由注册、生命周期管理
  config.py           Pydantic Settings（环境变量 → 配置对象）
  agent/              AI 智能体系统（MCP 工具、SSE 流式传输、会话）
  api/                OpenAPI 3.0 规范（路径 + 模式，通过 redocly 打包）
  db/
    models.py         SQLAlchemy ORM 模型（声明式基类）
    repositories/     数据访问层（每个实体一个）
  flow/               智能体工作流的 DAG 执行引擎
    base/models.py    NodeInstance、FlowInstance、NODE_RUNNER_REGISTRY
    engine.py         FlowEngine，包含拓扑排序和执行逻辑
    runners/          各节点执行器的实现
  graph/
    lightrag/         修改后的 LightRAG 库（无状态、按 workspace 隔离）
    lightrag_manager.py  用于创建隔离 LightRAG 实例的工厂
  index/
    manager.py        前端链——设置期望状态
    reconciler.py     后端链——检测偏差，调度任务
    *_index.py        各索引构建器
  llm/                LLM 抽象层（LiteLLM）、嵌入、重排序
  mcp/                MCP 服务器（FastMCP）——工具、资源、提示词
  schema/
    view_models.py    自动生成的 Pydantic 模型（来自 OpenAPI）
  service/            业务逻辑层（由视图调用）
  tasks/              Celery 异步任务（文档处理、索引创建）
  trace/              OpenTelemetry 初始化（Jaeger 导出器）
  views/              FastAPI 路由处理器（每个资源一个文件）
  websearch/          网络搜索集成（DuckDuckGo、JINA、trafilatura）
config/
  celery.py           Celery 应用、Beat 调度、任务路由
web/
  src/app/            Next.js App Router 页面（workspace/、admin/、auth/、marketplace/）
  src/components/     React 组件
  src/api/            生成的 TypeScript API 客户端
  src/services/       前端服务层
```

### 多租户隔离

集合（Collection）是数据隔离的基本单位。LightRAG 实例通过 `workspace` 参数按集合隔离。图谱中的实体/关系标识符会带上 workspace 后缀，以防止跨集合泄漏。

### 链路追踪

OpenTelemetry 配合 Jaeger 导出器，在应用启动时初始化（`aperag/trace/`）。通过环境变量控制：`OTEL_ENABLED`、`JAEGER_ENABLED`、`JAEGER_ENDPOINT`。使用 `make compose-infra WITH_JAEGER=1` 启用后，可在 `:16686` 访问 Jaeger UI。

### 供应商抽象

LLM、嵌入、重排序和网络搜索都使用了抽象的提供者接口。LiteLLM 将 100 多个 LLM 提供者适配到统一的 API 之下。切换模型只需修改配置，无需更改代码。
