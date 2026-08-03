"""Parse OWL ontology files into structured schema for prompt injection.

Uses RDFLib for robust parsing of RDF/XML, handling Chinese IRIs natively.
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# OWL namespace
OWL = "http://www.w3.org/2002/07/owl#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"


@dataclass
class PropertyDef:
    """A data property from the ontology."""
    name: str
    label: str | None = None
    comment: str | None = None
    domain: str | None = None
    range_: str | None = None
    functional: bool = False


@dataclass
class ObjectPropertyDef:
    """An object property with optional inverse and characteristics."""
    name: str
    label: str | None = None
    comment: str | None = None
    domain: str | None = None
    range_: str | None = None
    inverse: str | None = None
    transitive: bool = False
    symmetric: bool = False
    functional: bool = False


@dataclass
class OntologySchema:
    """Parsed OWL ontology schema."""
    classes: list[str] = field(default_factory=list)
    class_labels: dict[str, str] = field(default_factory=dict)
    class_comments: dict[str, str] = field(default_factory=dict)
    class_hierarchy: dict[str, list[str]] = field(default_factory=dict)
    disjoint_pairs: list[tuple[str, str]] = field(default_factory=list)
    object_properties: list[tuple[str, str, str]] = field(default_factory=list)
    obj_prop_details: dict[str, ObjectPropertyDef] = field(default_factory=dict)
    inverse_map: dict[str, str] = field(default_factory=dict)
    data_properties: dict[str, list[PropertyDef]] = field(default_factory=dict)
    functional_properties: dict[str, list[str]] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.classes and not self.data_properties and not self.object_properties


def _short_name(uri: str) -> str:
    """Extract the fragment/localname from a URI, or return as-is if not a URI."""
    if "#" in uri:
        return uri.rsplit("#", 1)[-1]
    return uri.rsplit("/", 1)[-1]


def parse_owl(file_path: str) -> OntologySchema:
    """Parse an OWL ontology file using RDFLib (handles Chinese natively)."""
    schema = OntologySchema()
    try:
        from rdflib import OWL as RDFLIB_OWL
        from rdflib import RDF as RDFLIB_RDF
        from rdflib import RDFS as RDFLIB_RDFS
        from rdflib import Graph

        # Strip non-standard nested tags that break RDFLib's XML parser
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        import re

        # Extract inverseOf pairs + property characteristics before stripping
        inverse_pairs: list[tuple[str, str]] = []
        for m in re.finditer(
            r'<owl:ObjectProperty\s+rdf:about="([^"]+)">\s*<owl:inverseOf\s+rdf:resource="([^"]+)"/>\s*</owl:ObjectProperty>',
            content,
        ):
            inverse_pairs.append((m.group(1), m.group(2)))

        # Functional/Transitive/Symmetric/InverseFunctional markers on ObjectProperty
        functional_props: set[str] = set()
        transitive_props: set[str] = set()
        symmetric_props: set[str] = set()
        inverse_func_props: set[str] = set()
        for m in re.finditer(
            r'<owl:(ObjectProperty|DatatypeProperty)\s+rdf:about="([^"]+)"[^>]*>(.*?)</owl:\1>',
            content,
            re.DOTALL,
        ):
            prop_name, body = m.group(2), m.group(3)
            if '<owl:FunctionalProperty/>' in body:
                functional_props.add(prop_name)
            if '<owl:TransitiveProperty/>' in body:
                transitive_props.add(prop_name)
            if '<owl:SymmetricProperty/>' in body:
                symmetric_props.add(prop_name)
            if '<owl:InverseFunctionalProperty/>' in body:
                inverse_func_props.add(prop_name)

        # Strip non-standard nested tags + XML comments (RDFLib parser issues)
        content = re.sub(r'\s*<owl:(FunctionalProperty|TransitiveProperty|SymmetricProperty|AsymmetricProperty|ReflexiveProperty|IrreflexiveProperty|InverseFunctionalProperty)\s*/>', '', content)
        content = re.sub(r'\s*<owl:inverseOf\s+[^>]+/>', '', content)
        content = re.sub(r'<!--[\s\S]*?-->', '', content)
        g = Graph()
        g.parse(data=content.encode("utf-8"), format="xml")

        # Apply extracted property characteristics to schema
        for pname in functional_props:
            # functional data/object property — mark in functional_properties global list
            schema.functional_properties.setdefault('*', [])
            if pname not in schema.functional_properties['*']:
                schema.functional_properties['*'].append(pname)
            schema.obj_prop_details.setdefault(pname, ObjectPropertyDef(name=pname)).functional = True
        for pname in transitive_props:
            schema.obj_prop_details.setdefault(pname, ObjectPropertyDef(name=pname)).__dict__['transitive'] = True
        for pname in symmetric_props:
            schema.obj_prop_details.setdefault(pname, ObjectPropertyDef(name=pname)).__dict__['symmetric'] = True

        # Add extracted inverse pairs
        for prop_a, prop_b in inverse_pairs:
            schema.inverse_map[prop_a] = prop_b
            schema.inverse_map[prop_b] = prop_a
            # Ensure the inverse pair properties exist in obj_prop_details
            for pname in (prop_a, prop_b):
                if pname not in schema.obj_prop_details:
                    schema.obj_prop_details[pname] = ObjectPropertyDef(name=pname)
                    schema.object_properties.append(("", pname, ""))

        # Collect namespace prefix → full URI, and extract base namespaces
        ns_prefix_map: dict[str, str] = {}  # URI → prefix
        all_ns_uris: list[str] = []
        for prefix, ns in g.namespaces():
            all_ns_uris.append(str(ns))
            if prefix:
                ns_prefix_map[str(ns)] = prefix

        # Add xml:base variants (with/without #) for relative URI resolution
        base_ns = set(all_ns_uris)
        for ns in list(base_ns):
            if ns.endswith("#"):
                base_ns.add(ns[:-1])
            else:
                base_ns.add(ns + "#")

        def _qname(uri: str) -> str:
            """Convert URI to short local name."""
            s = str(uri)
            # Try exact namespace match first
            for ns in sorted(base_ns, key=len, reverse=True):
                if s.startswith(ns):
                    local = s[len(ns):]
                    if local:
                        return local
            return _short_name(s)

        # ----- Classes -----
        for cls_uri in g.subjects(RDFLIB_RDF.type, RDFLIB_OWL.Class):
            name = _qname(cls_uri)
            schema.classes.append(name)

            # Labels & comments
            for label in g.objects(cls_uri, RDFLIB_RDFS.label):
                schema.class_labels[name] = str(label)
            for cmt in g.objects(cls_uri, RDFLIB_RDFS.comment):
                schema.class_comments[name] = str(cmt)

            # SubClassOf
            for parent in g.objects(cls_uri, RDFLIB_RDFS.subClassOf):
                parent_name = _qname(parent)
                if parent_name != name and parent_name:
                    if name not in schema.class_hierarchy:
                        schema.class_hierarchy[name] = []
                    schema.class_hierarchy[name].append(parent_name)

            # EquivalentClasses / disjointWith
            for disjoint in g.objects(cls_uri, RDFLIB_OWL.disjointWith):
                other = _qname(disjoint)
                pair = tuple(sorted([name, other]))
                if pair not in schema.disjoint_pairs:
                    schema.disjoint_pairs.append(pair)

        # ----- Object Properties -----
        for prop_uri in g.subjects(RDFLIB_RDF.type, RDFLIB_OWL.ObjectProperty):
            prop_name = _qname(prop_uri)
            label = None
            comment = None
            domain = None
            range_ = None
            inv = None

            for lbl in g.objects(prop_uri, RDFLIB_RDFS.label):
                label = str(lbl)
            for cmt in g.objects(prop_uri, RDFLIB_RDFS.comment):
                comment = str(cmt)
            for dom in g.objects(prop_uri, RDFLIB_RDFS.domain):
                domain = _qname(dom)
            for rng in g.objects(prop_uri, RDFLIB_RDFS.range):
                range_ = _qname(rng)
            for inv_obj in g.objects(prop_uri, RDFLIB_OWL.inverseOf):
                inv = _qname(inv_obj)
                schema.inverse_map[prop_name] = inv
                schema.inverse_map[inv] = prop_name  # bidirectional

            detail = ObjectPropertyDef(
                name=prop_name, label=label, comment=comment,
                domain=domain, range_=range_, inverse=inv,
            )
            schema.obj_prop_details[prop_name] = detail
            schema.object_properties.append((domain or "", prop_name, range_ or ""))

        # ----- Data Properties -----
        seen_data_props: set = set()
        for prop_uri in g.subjects(RDFLIB_RDF.type, RDFLIB_OWL.DatatypeProperty):
            prop_name = _qname(prop_uri)
            label = None
            comment = None
            range_ = "string"
            domain = None
            functional = False

            for lbl in g.objects(prop_uri, RDFLIB_RDFS.label):
                label = str(lbl)
            for cmt in g.objects(prop_uri, RDFLIB_RDFS.comment):
                comment = str(cmt)
            for rng in g.objects(prop_uri, RDFLIB_RDFS.range):
                range_ = _qname(rng)
            for dom in g.objects(prop_uri, RDFLIB_RDFS.domain):
                domain = _qname(dom)

            # FunctionalProperty marker — <owl:FunctionalProperty/> as nested tag
            # is parsed by RDFLib as (prop_uri, rdf:type, owl:FunctionalProperty)
            if (prop_uri, RDFLIB_RDF.type, RDFLIB_OWL.FunctionalProperty) in g:
                functional = True

            # Deduplicate
            dedup_key = (domain or "*", prop_name)
            if dedup_key in seen_data_props:
                continue
            seen_data_props.add(dedup_key)

            dp = PropertyDef(name=prop_name, label=label, comment=comment,
                             domain=domain, range_=range_, functional=functional)

            cls_key = domain or "*"
            if cls_key not in schema.data_properties:
                schema.data_properties[cls_key] = []
            schema.data_properties[cls_key].append(dp)

            if functional and domain:
                if domain not in schema.functional_properties:
                    schema.functional_properties[domain] = []
                if prop_name not in schema.functional_properties[domain]:
                    schema.functional_properties[domain].append(prop_name)


    except ImportError:
        logger.warning("rdflib not installed, OWL parsing skipped")
    except Exception as e:
        logger.error(f"Failed to parse OWL file {file_path}: {e}")

    return schema
