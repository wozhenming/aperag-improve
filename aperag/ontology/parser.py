"""Parse OWL ontology files into structured schema for prompt injection."""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PropertyDef:
    """A data property from the ontology."""

    name: str
    domain: str | None = None
    range_: str | None = None
    functional: bool = False  # single-value, don't merge


@dataclass
class ObjectPropertyDef:
    """An object property with optional inverse."""

    name: str
    domain: str | None = None
    range_: str | None = None
    inverse: str | None = None


@dataclass
class OntologySchema:
    """Parsed OWL ontology schema."""

    classes: list[str] = field(default_factory=list)
    class_hierarchy: dict[str, list[str]] = field(default_factory=dict)
    disjoint_pairs: list[tuple[str, str]] = field(default_factory=list)
    object_properties: list[tuple[str, str, str]] = field(default_factory=list)
    inverse_map: dict[str, str] = field(default_factory=dict)  # name → inverse name
    data_properties: dict[str, list[PropertyDef]] = field(default_factory=dict)
    # Filesystem path for the OWL file
    functional_properties: dict[str, list[str]] = field(default_factory=dict)
    # class_name → [functional property names]

    def is_empty(self) -> bool:
        return not self.classes and not self.data_properties and not self.object_properties


def parse_owl(file_path: str) -> OntologySchema:
    """Parse an OWL ontology file into OntologySchema."""
    schema = OntologySchema()
    try:
        from owlready2 import Thing, get_ontology

        onto = get_ontology(f"file://{file_path}").load()

        with onto:
            # ----- Classes + hierarchy + disjoint -----
            for cls in onto.classes():
                if cls is Thing:
                    continue
                name = cls.name.replace("_", " ")
                schema.classes.append(name)

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

                # Inverse
                try:
                    inv = prop.inverse_property
                    if inv and hasattr(inv, "name"):
                        inv_name = inv.name.replace("_", " ")
                        schema.inverse_map[prop_name] = inv_name
                except Exception:
                    pass

                for domain_cls in domains or [""]:
                    for range_cls in ranges or [""]:
                        schema.object_properties.append((domain_cls, prop_name, range_cls))

            # ----- Data properties + functional -----
            for prop in onto.data_properties():
                prop_name = prop.name.replace("_", " ")
                domains = _get_property_domains(prop)
                ranges = _get_property_ranges(prop)
                range_str = ranges[0] if ranges else "string"

                # Check if functional (single value)
                is_func = False
                try:
                    is_func = prop.is_functional
                except Exception:
                    pass

                dp = PropertyDef(name=prop_name, range_=range_str, functional=is_func)

                if domains:
                    for domain_cls in domains:
                        if domain_cls not in schema.data_properties:
                            schema.data_properties[domain_cls] = []
                        schema.data_properties[domain_cls].append(dp)
                        if is_func:
                            if domain_cls not in schema.functional_properties:
                                schema.functional_properties[domain_cls] = []
                            schema.functional_properties[domain_cls].append(prop_name)
                else:
                    if "*" not in schema.data_properties:
                        schema.data_properties["*"] = []
                    schema.data_properties["*"].append(dp)

    except ImportError:
        logger.warning("owlready2 not installed, OWL parsing skipped")
    except Exception as e:
        logger.error(f"Failed to parse OWL file {file_path}: {e}")

    return schema


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
