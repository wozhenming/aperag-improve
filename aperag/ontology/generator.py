# Copyright 2025 ApeCloud, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Generate canonical OWL RDF/XML from an ontology structure dict.

The emitted form matches what Protégé writes and what `parse_owl` reads back
losslessly: prefixed elements (`<owl:Class rdf:about="...">`), self-closing
`<owl:inverseOf rdf:resource="..."/>`, and real `<rdf:type>` triples for
FunctionalProperty markers.
"""

# Ontology base namespace — local names are joined with '#'
BASE_NS = "http://www.example.com/ontology#"

XSD_URI = "http://www.w3.org/2001/XMLSchema#"
XSD_TYPES = {
    "string": XSD_URI + "string",
    "integer": XSD_URI + "integer",
    "decimal": XSD_URI + "decimal",
    "double": XSD_URI + "double",
    "boolean": XSD_URI + "boolean",
    "date": XSD_URI + "date",
    "dateTime": XSD_URI + "dateTime",
    "anyURI": XSD_URI + "anyURI",
}
FUNCTIONAL_URI = "http://www.w3.org/2002/07/owl#FunctionalProperty"


def _esc_attr(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def _esc_text(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _clean_name(name: str) -> str:
    """Sanitize a local name so it can be used as an IRI fragment."""
    import re

    cleaned = re.sub(r"[^\w一-鿿-]", "_", name.strip())
    return cleaned if cleaned else "unnamed"


def structure_to_owl(structure: dict) -> str:
    """Build canonical OWL RDF/XML from a structure dict.

    Shape (same as `OntologyService.get_ontology_structure`):
      classes: [{name, label?, comment?, parents?: [str]}]
      object_properties: [{name, label?, comment?, domain?, range?, inverse?}]
      data_properties: {domain_class_or_*: [{name, label?, comment?, range?, functional?}]}
    """
    classes = structure.get("classes") or []
    obj_props = structure.get("object_properties") or []
    data_props = structure.get("data_properties") or {}

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"',
        '  xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"',
        '  xmlns:owl="http://www.w3.org/2002/07/owl#"',
        '  xmlns:xsd="http://www.w3.org/2001/XMLSchema#">',
        f'  <owl:Ontology rdf:about="{_esc_attr(BASE_NS)}"/>',
    ]

    # ----- Classes -----
    seen = set()
    for c in classes:
        name = _clean_name(c.get("name") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        lines.append(f'  <owl:Class rdf:about="{_esc_attr(BASE_NS + name)}">')
        if c.get("label"):
            lines.append(f"    <rdfs:label>{_esc_text(str(c['label']))}</rdfs:label>")
        if c.get("comment"):
            lines.append(f"    <rdfs:comment>{_esc_text(str(c['comment']))}</rdfs:comment>")
        for parent in c.get("parents") or []:
            p = _clean_name(parent)
            if p and p != name:
                lines.append(f'    <rdfs:subClassOf rdf:resource="{_esc_attr(BASE_NS + p)}"/>')
        lines.append("  </owl:Class>")

    # ----- Object properties -----
    seen = set()
    for p in obj_props:
        name = _clean_name(p.get("name") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        lines.append(f'  <owl:ObjectProperty rdf:about="{_esc_attr(BASE_NS + name)}">')
        if p.get("label"):
            lines.append(f"    <rdfs:label>{_esc_text(str(p['label']))}</rdfs:label>")
        if p.get("comment"):
            lines.append(f"    <rdfs:comment>{_esc_text(str(p['comment']))}</rdfs:comment>")
        if p.get("domain"):
            lines.append(f'    <rdfs:domain rdf:resource="{_esc_attr(BASE_NS + _clean_name(p["domain"]))}"/>')
        if p.get("range"):
            lines.append(f'    <rdfs:range rdf:resource="{_esc_attr(BASE_NS + _clean_name(p["range"]))}"/>')
        if p.get("inverse") and _clean_name(p["inverse"]) != name:
            lines.append(f'    <owl:inverseOf rdf:resource="{_esc_attr(BASE_NS + _clean_name(p["inverse"]))}"/>')
        lines.append("  </owl:ObjectProperty>")

    # ----- Data properties (grouped by domain class) -----
    seen = set()
    for cls, props in data_props.items():
        for dp in props:
            name = _clean_name(dp.get("name") or "")
            if not name or name in seen:
                continue
            seen.add(name)
            lines.append(f'  <owl:DatatypeProperty rdf:about="{_esc_attr(BASE_NS + name)}">')
            if dp.get("label"):
                lines.append(f"    <rdfs:label>{_esc_text(str(dp['label']))}</rdfs:label>")
            if dp.get("comment"):
                lines.append(f"    <rdfs:comment>{_esc_text(str(dp['comment']))}</rdfs:comment>")
            if cls and cls != "*":
                lines.append(f'    <rdfs:domain rdf:resource="{_esc_attr(BASE_NS + _clean_name(cls))}"/>')
            rng = dp.get("range") or "string"
            rng_uri = XSD_TYPES.get(rng, rng)
            lines.append(f'    <rdfs:range rdf:resource="{_esc_attr(rng_uri)}"/>')
            if dp.get("functional"):
                lines.append(f'    <rdf:type rdf:resource="{FUNCTIONAL_URI}"/>')
            lines.append("  </owl:DatatypeProperty>")

    lines.append("</rdf:RDF>")
    return "\n".join(lines)
