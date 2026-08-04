/* Generate Mermaid graph TB code from a parsed OWL structure preview.
   Shared by the collection owl-graph page and the ontology edit page. */

interface OwlClassPreview {
  name: string;
  label?: string;
  comment?: string;
  parents?: string[];
}

interface OwlObjPropPreview {
  name: string;
  label?: string;
  comment?: string;
  domain?: string;
  range?: string;
  inverse?: string;
}

export interface OwlPreview {
  classes?: OwlClassPreview[];
  object_properties?: OwlObjPropPreview[];
  [key: string]: unknown;
}

export function buildOwlMermaid(preview: OwlPreview): string {
  const classes: OwlClassPreview[] = preview.classes || [];
  const objProps: OwlObjPropPreview[] = preview.object_properties || [];
  const classMap = new Map(classes.map((c) => [c.name, c]));
  function esc(s: string) { return s.replace(/"/g, '&quot;'); }
  function label(c: OwlClassPreview) {
    return `${esc(c.label || c.name)}<br/>${c.comment ? esc(c.comment.slice(0, 40)) + (c.comment.length > 40 ? '...' : '') : ''}`;
  }
  let nextCode = 0;
  const codes: Record<string, string> = {};
  const getCode = (n: string) => { if (!codes[n]) codes[n] = 'C' + (nextCode++); return codes[n]; };
  const children: Record<string, string[]> = {};
  for (const c of classes) {
    for (const p of c.parents || []) {
      if (!children[p]) children[p] = [];
      children[p].push(c.name);
    }
  }
  const classSet = new Set(classes.map((c) => c.name));
  const roots = classes.filter((c) => !c.parents || c.parents.length === 0 || !c.parents.some((p) => classSet.has(p)));
  const lines: string[] = ['graph TB'];
  for (const c of classes) getCode(c.name);
  const doneNodes = new Set<string>();

  // Recursively emit a node and its children inside nested subgraphs.
  // Subgraph IDs must NOT collide with node IDs — use a distinct prefix.
  const emitNode = (name: string, depth: number) => {
    if (doneNodes.has(name)) return;
    doneNodes.add(name);
    const c = classMap.get(name);
    const kids = children[name] || [];
    const indent = '  '.repeat(depth + 1);
    if (kids.length === 0) {
      lines.push(`${indent}${getCode(name)}["${label(c || { name, label: name, comment: '' })}"]`);
    } else {
      // Parent class is BOTH a node (for inheritance edges) and a subgraph container.
      // Declare the node inside its own subgraph.
      lines.push(`${indent}subgraph SG_${getCode(name)}["${c ? (c.label || c.name) : name}"]`);
      lines.push(`${indent}  ${getCode(name)}["${label(c || { name, label: name, comment: '' })}"]`);
      for (const kid of kids) emitNode(kid, depth + 1);
      lines.push(`${indent}end`);
    }
  };

  for (const root of roots) {
    const c = classMap.get(root.name);
    const kids = children[root.name] || [];
    lines.push(`  ${getCode(root.name)}["${c ? label(c) : root.name}"]`);
    doneNodes.add(root.name);
    if (kids.length > 0) {
      lines.push(`  subgraph SG_${getCode(root.name)}["${c ? (c.label || c.name) : root.name} - 子类"]`);
      for (const kid of kids) emitNode(kid, 1);
      lines.push('  end');
    }
  }
  for (const c of classes) {
    for (const p of c.parents || []) {
      if (classSet.has(p)) lines.push(`  ${getCode(c.name)} -->|"继承"| ${getCode(p)}`);
    }
  }
  const addedEdges = new Set<string>();
  for (const p of objProps) {
    if (!p.domain || !p.range || !classSet.has(p.domain) || !classSet.has(p.range)) continue;
    const key = `${p.domain}|${p.range}|${p.label || p.name}`;
    if (addedEdges.has(key)) continue;
    addedEdges.add(key);
    lines.push(`  ${getCode(p.domain)} -->|"${esc(p.label || p.name)}"| ${getCode(p.range)}`);
  }
  lines.push('');
  const colorPalette2 = ['#e8eaf6,#3f51b5', '#e3f2fd,#1565c0', '#e8f5e9,#2e7d32', '#fff3e0,#e65100', '#fce4ec,#c62828', '#f3e5f5,#6a1b9a'];
  let ci = 0;
  for (const root of roots) {
    const [bg, border] = colorPalette2[ci % colorPalette2.length].split(',');
    const allNodes = [getCode(root.name)];
    for (const kid of children[root.name] || []) allNodes.push(getCode(kid));
    lines.push(`  classDef group${ci} fill:${bg},stroke:${border},stroke-width:2px;`);
    lines.push(`  class ${allNodes.join(',')} group${ci};`);
    ci++;
  }
  return lines.join('\n');
}
