# ApeRAG
[![Trust Score](https://archestra.ai/mcp-catalog/api/badge/quality/apecloud/ApeRAG)](https://archestra.ai/mcp-catalog/apecloud__aperag)

![HarryPotterKG2.png](docs%2Fzh-CN%2Fimages%2FHarryPotterKG2.png)

![chat2.png](docs%2Fzh-CN%2Fimages%2Fchat2.png)

ApeRAG 是一个生产就绪的 RAG（检索增强生成）平台，结合了图检索（Graph RAG）、向量搜索和全文搜索，并集成了高级 AI 智能体。通过混合检索、多模态文档处理、智能体和企业级管理功能，构建复杂的 AI 应用。

ApeRAG 是构建你自己的知识图谱、上下文工程和部署能够自主搜索推理的 AI 智能体的最佳选择。

[Read English Docs](README.md)

- [快速开始](#快速开始)
- [核心特性](#核心特性)
- [Docker Compose 部署](#docker-compose-部署)
- [生产与测试双环境](#生产与测试双环境)
- [MCP（模型上下文协议）支持](#mcp模型上下文协议支持)
- [本体（OWL）管理](#本体owl管理)
- [Kubernetes 部署](#kubernetes-部署推荐生产环境)
- [开发指南](./docs/zh-CN/development-guide.md)
- [构建 Docker 镜像](./docs/zh-CN/build-docker-image.md)
- [致谢](#致谢)
- [许可证](#许可证)

## 快速开始

> 安装 ApeRAG 前，请确保你的机器满足以下最低系统要求：
>
> - CPU >= 2 核
> - 内存 >= 4 GiB
> - Docker 与 Docker Compose

启动 ApeRAG 最简单的方式是通过 Docker Compose。运行以下命令前，请确保已安装 [Docker](https://docs.docker.com/get-docker/) 和 [Docker Compose](https://docs.docker.com/compose/install/)：

```bash
git clone https://github.com/apecloud/ApeRAG.git
cd ApeRAG
cp envs/env.template .env
docker-compose up -d --build
```

前端在 **Docker 内完成编译**（多阶段构建：容器内 `yarn install` → `next build`），无需将本地构建产物拷贝到服务器。启动后可通过浏览器访问：

- **Web 界面**：http://localhost:3010
- **API 文档**：http://localhost:8010/docs

## 核心特性

**1. 高级索引类型**：
五种并行索引类型实现最优检索：**向量**、**全文**、**图谱**、**摘要**和**视觉**——提供多维度的文档理解与搜索能力。

**2. 智能 AI 智能体**：
内置支持 MCP（模型上下文协议）工具的 AI 智能体，可自动识别相关知识库、智能搜索内容，并提供网络搜索能力。

**3. 增强的图谱 RAG 与实体归一化**：
深度修改的 LightRAG 实现，支持高级实体归一化（实体合并），生成更干净的知识图谱和更好的关系理解。

**4. 多模态处理与视觉支持**：
完整的多模态文档处理，支持图片、图表和视觉内容分析，同时保留传统文本处理能力。

**5. 混合检索引擎**：
结合图谱 RAG、向量搜索、全文搜索、摘要检索和视觉搜索的综合检索系统。

**6. MinerU 集成（云端与本地部署）**：
由 MinerU 驱动的先进文档解析服务。支持官方云端 API（Token 认证），也支持**自建 MinerU 服务**（通过本地 API 协议 `POST /file_parse`，无需云端 Token）。系统配置页提供"验证连接"按钮，可在使用前确认服务可达。

**7. 本体（OWL）管理**：
完整的 OWL 本体全生命周期管理：
- **我的知识库本体**：导入 `.owl` 文件，或通过 AI 引导对话（本体工程师）与从零构建两种方式创建本体
- **可视化本体编辑器**：可视化增删改类、对象属性（域/值域/逆关系）和数据属性（XSD 类型、函数型标记），无需手写 XML，右侧 Mermaid 图实时预览
- **Protégé 集成**：可上传 OWL 2（RDF/XML）或 Turtle 格式本体，并在知识库设置页通过下拉框将本体库中的本体绑定到图谱提取
- **导出格式转换**：可导出为 OWL 2（RDF/XML）或 Turtle（`.ttl`），内容自动转换而非仅改后缀

**8. Web 内容检索增强**：
`web_read` 支持 **POST/AJAX 数据接口**（表单/JSON body、自定义请求头），可抓取 JS 渲染页面的数据接口；返回内容附带页面内**链接清单**支持多跳检索（顺着侧边栏/子页面链接继续访问）；页面结构无语义时自动回退到正文容器提取。

**9. 生产级部署**：
- Docker Compose 部署，**生产与测试双环境隔离**（`docker-compose.yml` + `docker-compose.test.yml`）
- 完整的 Kubernetes 支持：Helm Chart 与 KubeBlocks 集成，生产级数据库（PostgreSQL、Redis、Qdrant、Elasticsearch、Neo4j）

**10. 企业管理**：
内置审计日志、LLM 模型管理、图谱可视化、完整的文档管理界面和智能体工作流管理。

**11. MCP 集成**：
完整支持模型上下文协议（MCP），包括站点栏目浏览工具（`scm_list` / `list_scm_categories`），支持对特定网站进行结构化检索。

**12. 开发者友好**：
FastAPI 后端、React 前端、Celery 异步任务处理、完善的测试体系、开发文档和智能体开发框架。

## Docker Compose 部署

> **生产推荐**——本仓库的实际部署配置

本仓库的 `docker-compose.yml` 已按本部署定制：

| 服务 | 宿主机端口 | 说明 |
|------|-----------|------|
| **frontend**（Next.js） | `3010:3000` | Docker 内多阶段构建，无需本地产物 |
| **api**（FastAPI） | `8010:8000` | REST API + MCP 服务器 + WebSocket |
| **celeryworker** | — | 文档解析、索引构建、图谱构建 |
| **celerybeat** | — | 周期协调任务 |
| **flower** | `5555` | Celery 监控 |
| **postgres / redis / qdrant / es** | — | 数据库（pgvector、Redis、Qdrant、Elasticsearch） |

```bash
cp envs/env.template .env
docker-compose up -d --build
```

## 生产与测试双环境

本项目在同一台服务器维护**两个隔离环境**：

```bash
# 生产环境
docker compose -p aperag --env-file .env -f docker-compose.yml up -d --build

# 测试环境
docker compose -p aperag-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml up -d --build
```

- 测试环境使用 `aperag-test-*` 容器名和独立端口（如 `3012`/`8012`），对象存储使用本地模式（非 S3），避免跨环境冲突
- 两个环境的数据库、Redis、对象存储路径完全隔离
- 前端更新通过 `--build` 自动完成——**无需手动拷贝构建产物**

## MCP（模型上下文协议）支持

ApeRAG 支持 [MCP（模型上下文协议）](https://modelcontextprotocol.io/) 集成，允许 AI 助手直接与你的知识库交互。启动服务后，按如下配置 MCP 客户端：

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

**认证方式**（按优先级）：
1. **HTTP Authorization 请求头**（推荐）：`Authorization: Bearer your-api-key`
2. **环境变量**（兜底）：`APERAG_API_KEY=your-api-key`

**注意**：非本机部署时请使用你的 API 地址（如 `https://your-host/mcp/`）。将 `your-api-key-here` 替换为 ApeRAG 设置中的有效 API Key。

### 可用 MCP 工具

**知识库工具**：
- `list_collections` — 浏览你的知识库集合
- `search_collection` — 混合检索（向量 / 全文 / 图谱 / 摘要 / 视觉）
- `search_chat_files` — 搜索当前对话中上传的文件

**Web 工具**：
- `web_search` — 网络搜索（JINA 优先，DuckDuckGo 兜底）
- `web_read` — 读取并提取网页内容；支持 **POST/AJAX 数据接口**（适用于 JS 渲染页面）：

  ```
  web_read(url_list=["https://www.scm.com.cn/search/news/"],
           method="POST",
           body={"key": "搜索关键字", "page": 1},
           body_type="form",
           extra_headers={"Referer": "https://www.scm.com.cn/search",
                          "X-Requested-With": "XMLHttpRequest"})
  ```

  返回内容附带页面内**链接清单**（`## 页面内链接`），模型可顺着子页面链接进行多跳检索。

**站点栏目工具**（针对特定网站的结构化浏览，如 scm.com.cn 广东计量）：
- `list_scm_categories` — 列出该站可浏览栏目（文章列表型 vs 静态信息页）
- `scm_list(category, page, keyword)` — 浏览文章列表栏目（标题/日期/URL），由站点地图驱动（`aperag/websearch/scm/scm_site.yaml`）

## 本体（OWL）管理

ApeRAG 内置完整的本体工作流，用于约束知识图谱提取：

1. **我的知识库本体**（侧边栏入口）：导入 `.owl` 文件或新建本体
2. **AI 引导创建**：本体工程师机器人逐步引导你完成 领域 → 类 → 属性 → 关系，**只输出 OWL 2（RDF/XML）格式**（拒绝 Turtle / N-Triples / JSON-LD），label 和 comment 使用中文
3. **从零构建**：创建空本体，在**可视化编辑器**中构建——类（含父类层级）、对象属性（域/值域/逆关系）、数据属性（XSD 类型、函数型），右侧 Mermaid 图实时预览
4. **绑定到知识库**：知识库设置页的 OWL 字段为本体库下拉选择，绑定后约束图谱的实体/关系提取
5. **导出**：可导出为 OWL 2（RDF/XML）或 Turtle（`.ttl`）——内容自动转换，而非仅改后缀

## Kubernetes 部署（推荐生产环境）

> **企业级高可用、可扩展部署**

使用提供的 Helm Chart 将 ApeRAG 部署到 Kubernetes，提供高可用、可扩展和生产级管理能力。

### 前提条件

*   [Kubernetes 集群](https://kubernetes.io/docs/setup/)（v1.20+）
*   已配置并连接集群的 [`kubectl`](https://kubernetes.io/docs/tasks/tools/)
*   已安装 [Helm v3+](https://helm.sh/docs/intro/install/)

### 克隆仓库

```bash
git clone https://github.com/apecloud/ApeRAG.git
cd ApeRAG
```

### 步骤 1：部署数据库服务

ApeRAG 需要 PostgreSQL、Redis、Qdrant 和 Elasticsearch。有两种选择：

**方案 A：使用现有数据库** - 如果集群中已有这些数据库，编辑 `deploy/aperag/values.yaml` 配置数据库连接信息，然后跳到步骤 2。

**方案 B：使用 KubeBlocks 部署数据库** - 使用自动化数据库部署（数据库连接已预配置）：

```bash
# 进入数据库部署脚本目录
cd deploy/databases/

# （可选）查看配置 - 默认设置适用于大多数情况
# edit 00-config.sh

# 安装 KubeBlocks 并部署数据库
bash ./01-prepare.sh          # 安装 KubeBlocks
bash ./02-install-database.sh # 部署 PostgreSQL、Redis、Qdrant、Elasticsearch

# 监控数据库部署
kubectl get pods -n default

# 返回项目根目录进行步骤 2
cd ../../
```

等待所有数据库 Pod 处于 `Running` 状态后再继续。

### 步骤 2：部署 ApeRAG 应用

```bash
# 如果使用 KubeBlocks 部署了数据库，数据库连接已预配置
# 如果使用现有数据库，编辑 deploy/aperag/values.yaml 配置连接信息

# 部署 ApeRAG
helm install aperag ./deploy/aperag --namespace default --create-namespace

# 监控 ApeRAG 部署
kubectl get pods -n default -l app.kubernetes.io/instance=aperag
```

### 配置选项

**资源要求**：默认包含 [`doc-ray`](https://github.com/apecloud/doc-ray) 服务（需要 4+ CPU 核、8GB+ 内存）。如需禁用：在 `values.yaml` 中设置 `docray.enabled: false`。

**高级设置**：查看 `values.yaml` 了解更多配置选项，包括镜像、资源和 Ingress 设置。

### 访问部署

部署完成后，使用端口转发访问 ApeRAG：

```bash
# 快速端口转发
kubectl port-forward svc/aperag-frontend 3000:3000 -n default
kubectl port-forward svc/aperag-api 8000:8000 -n default

# 浏览器访问
# Web 界面: http://localhost:3000
# API 文档: http://localhost:8000/docs
```

生产环境请通过 `values.yaml` 配置 Ingress 对外访问。

### 故障排查

**数据库问题**：参见 `deploy/databases/README.md` 了解 KubeBlocks 管理、凭据和卸载流程。

**Pod 状态**：检查 Pod 日志排查部署问题：
```bash
kubectl logs -f deployment/aperag-api -n default
kubectl logs -f deployment/aperag-frontend -n default
```

## 致谢

ApeRAG 集成并构建于多个优秀的开源项目之上：

### LightRAG
ApeRAG 中的图检索能力基于深度修改的 [LightRAG](https://github.com/HKUDS/LightRAG)：
- **论文**："LightRAG: Simple and Fast Retrieval-Augmented Generation"（[arXiv:2410.05779](https://arxiv.org/abs/2410.05779)）
- **作者**：Zirui Guo, Lianghao Xia, Yanhua Yu, Tu Ao, Chao Huang
- **许可证**：MIT License

我们对 LightRAG 进行了大量修改，以支持生产级并发处理、分布式任务队列（Celery/Prefect）和无状态操作。详见 [LightRAG 修改日志](./aperag/graph/changelog.md)。

## 社区

* [Discord](https://discord.gg/FsKpXukFuB)
* [飞书](docs%2Fzh-CN%2Fimages%2Ffeishu-qr-code.png)

<img src="docs/zh-CN/images/feishu-qr-code.png" alt="飞书" width="150"/>

## Star History

![star-history-2025922.png](docs%2Fzh-CN%2Fimages%2Fstar-history-2025922.png)

## 许可证

ApeRAG 基于 Apache License 2.0 许可证。详见 [LICENSE](./LICENSE) 文件。
