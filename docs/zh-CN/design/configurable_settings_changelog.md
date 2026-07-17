# 前端可配置化设置 — 变更日志

## 概述

将原先硬编码在 Python 源码中的核心分块参数和知识图谱参数迁移为可从管理后台（Admin → Configuration）动态配置，所有设置持久化到数据库并支持运行时修改，无需重启服务。

## 变更文件清单

### 后端

| 文件 | 操作 | 说明 |
|------|------|------|
| `aperag/schema/view_models.py` | 修改 | `Settings` 模型从 4 字段扩展到 16 字段 |
| `aperag/api/components/schemas/settings.yaml` | 修改 | OpenAPI schema 同步新增字段 |
| `aperag/service/setting_service.py` | 修改 | 新增 15 个类型化访问器（含 sync 版本），带三级 fallback |
| `aperag/graph/lightrag_manager.py` | 修改 | `LightRAGConfig` 从硬编码常量改为动态读取 DB |
| `aperag/index/vector_index.py` | 修改 | `chunk_size`/`chunk_overlap` 改为从 `setting_service` 读取 |
| `aperag/index/fulltext_index.py` | 修改 | 同上 |

### 前端

| 文件 | 操作 | 说明 |
|------|------|------|
| `web/src/app/admin/configuration/core-settings.tsx` | **新建** | 核心分块配置 + 缓存配置卡片组件 |
| `web/src/app/admin/configuration/kg-settings.tsx` | **新建** | 知识图谱配置卡片组件（含实体类型标签管理） |
| `web/src/app/admin/configuration/page.tsx` | 修改 | 集成新组件到管理配置页面 |
| `web/src/api/models/settings.ts` | 修改 | TypeScript `Settings` 接口扩展 |
| `web/src/i18n/zh-CN/admin_config.json` | 修改 | 新增中文字段标签 |
| `web/src/i18n/en-US/admin_config.json` | 修改 | 新增英文字段标签 |

## Settings 模型字段明细

### 原有字段（不变）

| 字段 | 类型 | 默认值 |
|------|------|--------|
| `use_mineru` | bool | false |
| `mineru_api_token` | string | - |
| `use_doc_ray` | bool | false |
| `use_markitdown` | bool | true |

### 新增：核心分块配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `chunk_size` | int | 400 | 文档向量/全文索引的分块大小 |
| `chunk_overlap_size` | int | 20 | 分块重叠大小 |

### 新增：知识图谱配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `kg_chunk_token_size` | int | 1200 | LightRAG 图谱分块 token 数 |
| `kg_chunk_overlap_token_size` | int | 100 | LightRAG 图谱分块重叠 token 数 |
| `kg_entity_extract_max_gleaning` | int | 0 | 实体提取最大 gleaning 轮次 |
| `kg_llm_model_max_async` | int | 20 | LLM 最大并发调用数 |
| `kg_cosine_threshold` | float | 0.2 | 向量相似度阈值 |
| `kg_max_batch_size` | int | 32 | 最大批处理大小 |
| `kg_summary_max_tokens` | int | 2000 | 实体/关系摘要最大 token 数 |
| `kg_force_llm_summary_on_merge` | int | 10 | 合并时强制 LLM 摘要的实体数阈值 |
| `kg_entity_types` | list[str] | 8种默认类型 | 自定义实体类型列表 |

### 新增：缓存配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `cache_enabled` | bool | true | LLM 缓存开关 |
| `cache_ttl` | int | 86400 | 缓存过期时间（秒） |

## 数据流

```
┌─────────────────────────────────────────────────────────────────┐
│  前端管理页面 (/admin/configuration)                              │
│  ├─ CoreSettings 组件  (chunk_size, chunk_overlap, cache...)     │
│  ├─ KgSettings 组件    (kg_*, entity_types)                      │
│  ├─ ParserSettings     (use_mineru, use_doc_ray, use_markitdown) │
│  └─ QuotaSettings      (max_bot_count, max_collection_count...)  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ PUT /api/v1/settings
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  SettingService (aperag/service/setting_service.py)              │
│  └─ update_settings() → 写入 Setting 表 (key-value)              │
└──────────────────────────┬──────────────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         Setting表    环境变量     硬编码默认值
         (优先)      (fallback)   (最终fallback)
```

## Fallback 机制

所有配置读取遵循三级优先级：

```
1. DB Setting 表 (用户在 UI 中设置的值)  ← 最高优先级
2. 环境变量 (如 CHUNK_SIZE=400)         ← 运维级别覆盖
3. 硬编码默认值                          ← 出厂默认值
```

示例（`SettingService.get_chunk_size_sync()`）：

```python
def get_chunk_size_sync(self) -> int:
    val = self.get_all_settings_sync().get("chunk_size")
    if val is not None:
        return val              # DB 中有值 → 优先
    return config_settings.chunk_size  # 读取 env CHUNK_SIZE → 默认 400
```

## 影响范围

- **文档索引**：`vector_index.py` 和 `fulltext_index.py` 的 `chunk_size`/`chunk_overlap` 改为从 `setting_service` 读取
- **知识图谱构建**：`LightRAGConfig` 的所有参数改为动态读取
- **LLM 缓存**：`cache_enabled`/`cache_ttl` 沿用原有的 config 读取方式，新增 UI 覆盖能力

## 向后兼容

- 所有新增设置项在 DB 中无值时，自动 fallback 到原有默认值
- 现有部署无需数据库迁移，无需修改 `.env` 文件
- 未访问管理页面时，系统行为与变更前完全一致

## 验证方法

1. 启动服务后访问 `http://localhost:8000/docs`，确认 `/api/v1/settings` 的 GET/PUT schema 包含所有新字段
2. 访问 `http://localhost:3000/admin/configuration`，在「核心分块配置」中修改 `chunk_size` 为 800，点击保存
3. 刷新页面，确认值持久化为 800
4. 上传一个文档触发索引，通过日志确认新的 `chunk_size=800` 实际生效
5. 在「知识图谱配置」中修改 `kg_cosine_threshold` 为 0.3，上传文档后确认图谱构建使用了新阈值
