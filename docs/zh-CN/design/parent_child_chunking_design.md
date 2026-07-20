# 父子分段（Parent-Child Chunking）实现方案

## Context

当前 ApeRAG 的分块是平面化的：文档解析后按固定大小分块存入 Qdrant/ES，检索时直接返回匹配块的原始文本。这种方式的问题是：小块虽然精准匹配了查询，但缺乏周围上下文，LLM 难以给出连贯的回答。

Dify 的父子分段方案解决了这个问题：
- **父块** (800 token) 保留完整的段落上下文
- **子块** (150 token) 从父块中提取，只对子块做向量化
- 检索时：Query 命中子块 → 返回父块的完整内容给 LLM

## 实现方案

### 总览

所有改动都在索引侧，检索侧零改动。核心思路：

```
Rechunker 两阶段分块:
  文档部分 → 父块(800t) → 每个父块再切 → 子块(150t, 80t重叠)
       ↓                       ↓
   存入子块 Qdrant payload   向量化子块文本
   (parent_content字段)
```

### 需要改动的文件

| 文件 | 改动 |
|------|------|
| `aperag/docparser/chunking.py` | **新增** `ParentChildRechunker` 类，实现父子两阶段分块 |
| `aperag/llm/embed/embedding_utils.py` | **修改** `create_embeddings_and_store()`，接受并传递父块内容 |
| `aperag/index/vector_index.py` | **修改** 传递 `parent_child_mode` 参数给打包函数 |
| `aperag/index/fulltext_index.py` | **修改** 同上，ES 文档中也存入 `parent_content` |
| `aperag/service/setting_service.py` | **新增** `parent_child_enabled` 和父/子块参数的类型化访问器 |
| `aperag/schema/view_models.py` | **新增** `parent_child_enabled` 等字段到 Settings |
| `aperag/api/components/schemas/settings.yaml` | **新增** 对应 OpenAPI schema |
| `web/src/app/admin/configuration/core-settings.tsx` | **新增** 父子分段开关和参数 UI |
| `web/src/app/admin/configuration/page.tsx` | 无需改动（已集成 CoreSettings）|
| `web/src/i18n/zh-CN/admin_config.json` | 新字段翻译 |
| `web/src/i18n/en-US/admin_config.json` | 新字段翻译 |

### 详细设计

#### 1. ParentChildRechunker (`aperag/docparser/chunking.py`)

```python
@dataclass
class ParentChunk:
    """A large parent chunk that preserves context"""
    content: str
    metadata: dict

@dataclass
class ChildChunk:
    """A small child chunk for precise retrieval"""
    content: str
    metadata: dict
    parent_content: str       # The full parent chunk content
    parent_id: str            # e.g., "parent_0", "parent_1"

class ParentChildRechunker:
    def __init__(self, parent_chunk_size: int, child_chunk_size: int,
                 child_chunk_overlap: int, tokenizer):
        ...

    def __call__(self, parts: list[Part]) -> tuple[list[Part], list[ParentChunk]]:
        """
        Returns:
          child_chunks: list[Part] to be embedded and stored (small)
          parent_chunks: list[ParentChunk] for reference (stored in child metadata)
        """
        # 1. 先用大 chunk_size 切出父块（复用现有 Rechunker）
        parent_parts = rechunk(parts, self.parent_chunk_size,
                               self.parent_chunk_size // 10, self.tokenizer)

        # 2. 每个父块再切出子块（较小 chunk_size，有重叠）
        all_children = []
        all_parents = []
        for i, parent_part in enumerate(parent_parts):
            parent_content = parent_part.content
            parent_meta = parent_part.metadata.copy()
            parent_id = f"parent_{i}"

            # 将父块包装为单元素 list 进行子分块
            children = rechunk(
                [Part(content=parent_content, metadata=parent_meta)],
                self.child_chunk_size, self.child_chunk_overlap, self.tokenizer
            )

            for child in children:
                child.metadata["parent_id"] = parent_id
                child.metadata["parent_content"] = parent_content

            all_children.extend(children)
            all_parents.append(ParentChunk(
                content=parent_content,
                metadata=parent_meta,
                parent_id=parent_id,
            ))

        return all_children, all_parents
```

#### 2. embed_utils 改动

`create_embeddings_and_store()` 已经接受 `parts: list[Part]`。改动很小：子块的 `part.metadata["parent_content"]` 自然传递到 Qdrant payload 中（通过 `TextNode.metadata`）。

```python
# 无需改动核心逻辑！metadata 自动传递：
# part.metadata → TextNode.metadata → Qdrant payload
```

#### 3. 检索侧：零改动

关键在于 `DocumentWithScore` 的 `text` 字段：

**检索时：**
1. Qdrant 返回子块的 `text`（子块内容）和 `metadata`（含 `parent_content`）
2. 在 `_convert_scored_point_to_document_with_score()` 中，如果 metadata 有 `parent_content`，就用它替换 text

改动集中在 `qdrant_connector.py` 的 `_convert_scored_point_to_document_with_score`：

```python
def _convert_scored_point_to_document_with_score(self, scored_point):
    ...
    # 新增：如果有父块内容，返回父块而非子块
    if metadata and metadata.get("parent_content"):
        text = metadata["parent_content"]
    ...
```

这样检索出的 `DocumentWithScore.text` 就是完整的父块内容，LLM 有充足的上下文。

#### 4. 全文索引同步

ES 文档中也存储 `parent_content`：

```python
# fulltext_index.py _insert_chunk()
doc = {
    ...
    "content": chunk_content,          # 子块内容（用于关键词匹配）
    "parent_content": parent_content,  # 父块内容（返回给 LLM）
    ...
}
```

ES 搜索后，如果结果有 `parent_content`，用它替换返回的 text。

#### 5. 前端配置

在现有 `CoreSettings` 组件中新增开关：

- `parent_child_enabled` — 开关，默认 false
- `parent_chunk_size` — 父块大小，默认 800
- `child_chunk_size` — 子块大小，默认 150
- `child_chunk_overlap` — 子块重叠，默认 50

### 向后兼容

- `parent_child_enabled` 默认为 False
- 关闭时走原有的 `Rechunker` 路径，行为完全不变
- 开启后新建的索引才应用父子分段
- 已有 collection 不受影响

### 数据流对比

```
修改前:
  parse → Rechunker(400,20) → chunks(400t each)
    → embed → Qdrant(vector_indexer)
    → insert → ES(fulltext_indexer)
  检索 → DocumentWithScore(text=400t chunk)

修改后(开启):
  parse → ParentChildRechunker
    → 父块(800t) → 子块(150t, overlap=50)
      → embed 子块 → Qdrant (parent_content 存入 payload)
      → insert 子块 → ES (parent_content 存入文档)
  检索 → DocumentWithScore(text=800t 父块全文)
```

### 验证方法

1. 前端开启父子分段 → 上传文档 → 查看 Qdrant payload 确认有 `parent_content` 字段
2. 搜索测试：查询命中后返回的 `DocumentWithScore.text` 长度应为父块大小(~800t)，而非子块(~150t)
3. 关闭父子分段 → 上传文档 → 确认 payload 无 `parent_content`，行为恢复原样
4. `make lint` 通过
