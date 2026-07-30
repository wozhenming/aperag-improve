"""Parse OWL ontology files into structured schema for prompt injection."""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PropertyDef:
    """A data property from the ontology."""

    name: str
    label: str | None = None  # rdfs:label (Chinese display name)
    comment: str | None = None
    domain: str | None = None
    range_: str | None = None
    functional: bool = False


@dataclass
class ObjectPropertyDef:
    """An object property with optional inverse."""

    name: str
    label: str | None = None  # rdfs:label
    comment: str | None = None
    domain: str | None = None
    range_: str | None = None
    inverse: str | None = None


@dataclass
class OntologySchema:
    """Parsed OWL ontology schema."""

    classes: list[str] = field(default_factory=list)
    class_labels: dict[str, str] = field(default_factory=dict)
    class_hierarchy: dict[str, list[str]] = field(default_factory=dict)
    disjoint_pairs: list[tuple[str, str]] = field(default_factory=list)
    object_properties: list[tuple[str, str, str]] = field(default_factory=list)
    obj_prop_details: dict[str, ObjectPropertyDef] = field(default_factory=dict)
    inverse_map: dict[str, str] = field(default_factory=dict)
    data_properties: dict[str, list[PropertyDef]] = field(default_factory=dict)
    functional_properties: dict[str, list[str]] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.classes and not self.data_properties and not self.object_properties


def _label_of(entity) -> str | None:
    """Get rdfs:label first() from an owlready2 entity, fallback to None."""
    try:
        lbls = entity.label
        if lbls:
            return str(lbls[0])
    except Exception:
        pass
    return None


def _comment_of(entity) -> str | None:
    """Get rdfs:comment first() from an owlready2 entity."""
    try:
        cmts = entity.comment
        if cmts:
            return str(cmts[0])
    except Exception:
        pass
    return None


def parse_owl(file_path: str) -> OntologySchema:
    """Parse an OWL ontology file into OntologySchema."""
    schema = OntologySchema()
    try:
        from owlready2 import Thing, get_ontology

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        content = _resolve_owl_entities(content)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        onto = get_ontology(f"file://{file_path}").load()

        with onto:
            # ----- Classes + hierarchy + disjoint -----
            for cls in onto.classes():
                if cls is Thing:
                    continue
                name = cls.name.replace("_", " ")
                schema.classes.append(name)

                # Chinese label
                label = _label_of(cls)
                if label:
                    schema.class_labels[name] = label

                # Class hierarchy (subClassOf)
                for parent in cls.is_a:
                    if hasattr(parent, "name") and parent is not Thing:
                        parent_name = parent.name.replace("_", " ")
                        if name not in schema.class_hierarchy:
                            schema.class_hierarchy[name] = []
                        schema.class_hierarchy[name].append(parent_name)

                # Disjoint classes
                try:
                    for disjoint_set in cls.disjoints():
                        for other in disjoint_set.entities:
                            if other is cls or other is Thing:
                                continue
                            other_name = other.name.replace("_", " ")
                            pair = tuple(sorted([name, other_name]))
                            if pair not in schema.disjoint_pairs:
                                schema.disjoint_pairs.append(pair)
                except Exception:
                    pass

            # ----- Object properties + inverse -----
            for prop in onto.object_properties():
                prop_name = prop.name.replace("_", " ")
                domains = _get_property_domains(prop)
                ranges = _get_property_ranges(prop)
                label = _label_of(prop)
                comment = _comment_of(prop)

                # Inverse
                inv_name = None
                try:
                    inv = prop.inverse_property
                    if inv and hasattr(inv, "name"):
                        inv_name = inv.name.replace("_", " ")
                        schema.inverse_map[prop_name] = inv_name
                except Exception:
                    pass

                detail = ObjectPropertyDef(
                    name=prop_name,
                    label=label,
                    comment=comment,
                    domain=domains[0] if domains else None,
                    range_=ranges[0] if ranges else None,
                    inverse=inv_name,
                )
                schema.obj_prop_details[prop_name] = detail

                for domain_cls in domains or [""]:
                    for range_cls in ranges or [""]:
                        schema.object_properties.append((domain_cls, prop_name, range_cls))

            # ----- Data properties + functional -----
            seen_data_props: set = set()
            for prop in onto.data_properties():
                prop_name = prop.name.replace("_", " ")
                domains = _get_property_domains(prop)
                ranges = _get_property_ranges(prop)
                range_str = ranges[0] if ranges else "string"
                label = _label_of(prop)
                comment = _comment_of(prop)

                # Check if functional (single value)
                is_func = False
                try:
                    is_func = prop.is_functional
                except Exception:
                    pass

                dp = PropertyDef(
                    name=prop_name,
                    label=label,
                    comment=comment,
                    range_=range_str,
                    functional=is_func,
                )

                if domains:
                    for domain_cls in domains:
                        dedup_key = (domain_cls, prop_name)
                        if dedup_key in seen_data_props:
                            continue
                        seen_data_props.add(dedup_key)

                        dp.domain = domain_cls
                        if domain_cls not in schema.data_properties:
                            schema.data_properties[domain_cls] = []
                        schema.data_properties[domain_cls].append(dp)
                        if is_func:
                            if domain_cls not in schema.functional_properties:
                                schema.functional_properties[domain_cls] = []
                            if prop_name not in schema.functional_properties[domain_cls]:
                                schema.functional_properties[domain_cls].append(prop_name)
                else:
                    dedup_key = ("*", prop_name)
                    if dedup_key in seen_data_props:
                        continue
                    seen_data_props.add(dedup_key)
                    if "*" not in schema.data_properties:
                        schema.data_properties["*"] = []
                    schema.data_properties["*"].append(dp)

    except ImportError:
        logger.warning("owlready2 not installed, OWL parsing skipped")
    except Exception as e:
        logger.error(f"Failed to parse OWL file {file_path}: {e}")

    return schema


def _resolve_owl_entities(content: str) -> str:
    """Pre-process OWL XML: resolve entities, strip invalid nesting, encode IRIs."""
    import re
    from urllib.parse import quote

    # Fix Protégé shorthand that owlready2 can't parse:
    # Replace <owl:FunctionalProperty/> with standard <rdf:type rdf:resource="..."/>
    content = re.sub(
        r'<owl:FunctionalProperty\s*/>',
        '<rdf:type rdf:resource="http://www.w3.org/2002/07/owl#FunctionalProperty"/>',
        content,
    )
    # Keep inverseOf declarations as comments for now
    content = re.sub(r'<owl:inverseOf\s+rdf:resource="([^"]*)"\s*/>', r'<!-- inverseOf \1 -->', content)

    ns_map: dict[str, str] = {}
    for m in re.finditer(r'xmlns:(\w+)="([^"]+)"', content):
        ns_map[m.group(1)] = m.group(2)

    default_ns = re.search(r'xmlns="([^"]+)"', content)
    if default_ns:
        ns_map["ontology"] = default_ns.group(1)

    entity_refs = set(re.findall(r"&([a-zA-Z_]\w*);", content))
    for entity in entity_refs:
        if entity in ns_map:
            content = content.replace(f"&{entity};", ns_map[entity])

    def _encode_iri(m: re.Match) -> str:
        before, value, after = m.group(1), m.group(2), m.group(3)
        if any(ord(c) > 127 for c in value):
            encoded = quote(value, safe='/#:')
            return before + encoded + after
        return before + value + after

    # Encode non-ASCII in rdf:about, xml:base, and default xmlns values
    content = re.sub(r'(rdf:about=")([^"]+)(")', _encode_iri, content)
    content = re.sub(r'(xml:base=")([^"]+)(")', _encode_iri, content)
    content = re.sub(r'(xmlns=")([^"]+)(")', _encode_iri, content)
    return content


def _get_property_domains(prop) -> list[str]:
    try:
        return [d.name.replace("_", " ") for d in prop.domain if d.name != "Thing"]
    except Exception:
        return []


def _get_property_ranges(prop) -> list[str]:
    try:
        return [r.name.replace("_", " ") for r in prop.range]
    except Exception:
        return []
