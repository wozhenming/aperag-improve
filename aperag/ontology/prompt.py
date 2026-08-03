"""Build ontology guidance text from OntologySchema for prompt injection."""

import logging

from aperag.ontology.parser import OntologySchema

logger = logging.getLogger(__name__)

ONTOLOGY_ENGINEER_SYSTEM_PROMPT = """你是专业的知识图谱本体工程师，帮助用户一步步构建 OWL 本体。

## 工作方式

采用引导式对话，逐步收集信息，不要一次性问太多问题。按以下顺序引导：

1. **领域与范围**：询问用户要建模的业务领域（如：公路工程造价、医疗诊断、电商订单）。了解后复述确认。
2. **核心类**：引导用户列出核心实体类型（类）。提示示例：领域名词、业务对象。每轮最多确认 5-8 个类。
3. **数据属性**：逐个类询问需要哪些属性（属性名 + 类型：string/integer/decimal/date/boolean）。
4. **对象属性（关系）**：引导用户描述类之间的关系，明确 domain（源类）和 range（目标类），用自然语言如"定额 适用于 清单子目"。
5. **约束**：询问是否有单值属性（FunctionalProperty）、传递关系（TransitiveProperty）、互斥类（disjointWith）。

用户信息不足时只问当前步骤的必要问题，不要提前问后续步骤。用户回答后总结确认，信息足够后输出最终本体。

## 输出格式

当信息收集完成，输出两部分：

1. **OWL 本体**（RDF/XML 格式）放在 ```owl 代码块中。规范：
   - 类用 <owl:Class rdf:about="类名"> + <rdfs:comment>描述</rdfs:comment>
   - 继承用 <rdfs:subClassOf rdf:resource="父类"/>
   - 数据属性用 <owl:DatatypeProperty rdf:about="属性名"> + <rdfs:domain> + <rdfs:range>（xsd:string/integer/decimal/date）
   - 对象属性用 <owl:ObjectProperty rdf:about="关系名"> + <rdfs:domain> + <rdfs:range>
   - **不要使用 <owl:FunctionalProperty/> 嵌套标签**（解析器不兼容）；用 <rdf:type rdf:resource="http://www.w3.org/2002/07/owl#FunctionalProperty"/> 代替
   - 类名和属性名使用中文（与领域语言一致）
2. **Mermaid 关系图** 放在 ```mermaid 代码块中（graph TB 语法，类作为节点，继承和对象属性作为连线）。

输出示例结构：
```owl
<?xml version="1.0"?>
<rdf:RDF xmlns="http://example.org/ontology#" xmlns:owl="http://www.w3.org/2002/07/owl#" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#" xmlns:xsd="http://www.w3.org/2001/XMLSchema#">
  <owl:Class rdf:about="类A"><rdfs:comment>描述</rdfs:comment></owl:Class>
  ...
</rdf:RDF>
```
```mermaid
graph TB
  A["类A"] --> B["类B"]
```

## 语言
始终使用用户的语言交流。"""


def build_ontology_guide(schema: OntologySchema) -> str:
    """Convert OntologySchema into LLM prompt constraints."""
    if not schema or schema.is_empty():
        return ""

    lines = ["---Ontology Schema---", ""]

    # 1. Classes + hierarchy
    if schema.classes:
        lines.append("Classes (entity types):")
        for cls_name in schema.classes:
            parents = schema.class_hierarchy.get(cls_name, [])
            if parents:
                lines.append(f"- {cls_name} (subclass of {', '.join(parents)})")
            else:
                lines.append(f"- {cls_name}")
        lines.append("")

    # 2. Disjoint constraint
    if schema.disjoint_pairs:
        lines.append("Disjoint Classes (MUTUALLY EXCLUSIVE — an entity CANNOT belong to both):")
        for a, b in schema.disjoint_pairs[:30]:
            lines.append(f"- {a} ⟂ {b}")
        lines.append("")

    # 3. Object properties + inverse
    if schema.object_properties:
        lines.append(
            "Object Properties (relationship constraints — only use these relation keywords):"
        )
        for domain, name, range_ in schema.object_properties:
            d = domain or "*"
            r = range_ or "*"
            inv = schema.inverse_map.get(name)
            detail = schema.obj_prop_details.get(name)
            inv_hint = f" [inverse: {inv}]" if inv else ""
            char_hints = []
            if detail:
                if detail.transitive:
                    char_hints.append("transitive")
                if detail.symmetric:
                    char_hints.append("symmetric")
                if detail.functional:
                    char_hints.append("functional")
            char_hint = f" [{' + '.join(char_hints)}]" if char_hints else ""
            lines.append(f"- {name}({d} → {r}){inv_hint}{char_hint}")
        lines.append("")

    if schema.inverse_map:
        lines.append("Inverse Relationships (also extract the reverse automatically):")
        for name, inv in schema.inverse_map.items():
            lines.append(f"- If {name}(A → B) exists, also add {inv}(B → A)")
        lines.append("")

    # 4. Data properties + functional
    if schema.data_properties:
        lines.append(
            "Data Properties (structured attributes — MUST extract these for each entity):"
        )
        for class_name, props in schema.data_properties.items():
            cls_label = class_name if class_name != "*" else "All classes"
            lines.append(f"--- {cls_label} ---")
            for dp in props:
                rng = dp.range_ or "string"
                func = " [SINGLE VALUE]" if dp.functional else ""
                lines.append(f"  - {dp.name} ({rng}){func}")
        lines.append("")

        # Functional properties hint
        if schema.functional_properties:
            func_names = set()
            for names in schema.functional_properties.values():
                func_names.update(names)
            if func_names:
                lines.append(
                    "Functional Properties (accept only ONE value, do NOT list multiple): "
                    + ", ".join(sorted(func_names))
                )
                lines.append("")

        # Extended format hint
        lines.append("Entity Format (includes structured properties as JSON):")
        lines.append(
            '("entity"{tuple_delimiter}<entity_name>{tuple_delimiter}<entity_type>'
            '{tuple_delimiter}<entity_description>'
            '{tuple_delimiter}<properties_json>)'
        )
        lines.append("")
        lines.append(
            "For functional properties, include exactly one value. "
            "For non-functional properties, use an array if multiple values exist."
        )
        lines.append("properties_json must be a valid JSON object, e.g.")
        lines.append(
            '{"文号":"交公路发[2018]123号","发布机关":"交通运输部","生效日期":"2018-05-01"}'
        )
        lines.append("If a property value is unknown, omit that key. Do NOT fabricate values.")
        lines.append("")

    return "\n".join(lines)
