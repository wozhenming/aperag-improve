"""Build ontology guidance text from OntologySchema for prompt injection."""

import logging

from aperag.ontology.parser import OntologySchema

logger = logging.getLogger(__name__)


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
            inv_hint = f" [inverse: {inv}]" if inv else ""
            lines.append(f"- {name}({d} → {r}){inv_hint}")
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
