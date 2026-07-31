'use client';

import { ChartMermaid } from '@/components/chart-mermaid';
import { Button } from '@/components/ui/button';
import {
  Drawer, DrawerContent, DrawerHeader, DrawerTitle,
} from '@/components/ui/drawer';
import { Separator } from '@/components/ui/separator';
import axios from 'axios';
import { ArrowLeft, ChevronDown, ChevronUp, Download, LoaderCircle, Maximize2, Minus, Plus, RotateCcw, X } from 'lucide-react';
import { useTranslations } from 'next-intl';
import dynamic from 'next/dynamic';
import { useParams, useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

const ForceGraph2D = dynamic(() => import('react-force-graph-2d').then((r) => r), { ssr: false });

export default function OwlGraphPage() {
  const params = useParams();
  const router = useRouter();
  const page_collections = useTranslations('page_collections');
  const [graphData, setGraphData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<any>(null);
  const mermaidRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ width: 800, height: 600 });
  const [activeNode, setActiveNode] = useState<any>(null);
  const [showMermaid, setShowMermaid] = useState(true);
  const [mermaidPct, setMermaidPct] = useState(40); // % height for Mermaid
  const [dragging, setDragging] = useState(false);
  const [classComments, setClassComments] = useState<Record<string, string>>({});

  const loadGraph = useCallback(async () => {
    if (typeof params.collectionId !== 'string') return;
    try {
      const basePath = process.env.NEXT_PUBLIC_BASE_PATH || '';
      const { data } = await axios.get(
        `${basePath}/api/v1/collections/${params.collectionId}/owl`
      );
      const preview = (data as any).preview;
      if (!preview) { setLoading(false); return; }

      // Save class comments
      const comments: Record<string, string> = {};
      for (const c of preview.classes || []) {
        if (c.comment) comments[c.name] = c.comment;
      }
      setClassComments(comments);

      const colorPalette = [
        '#e6194b', '#3cb44b', '#4363d8', '#f58231', '#911eb4',
        '#46f0f0', '#f032e6', '#bcf60c', '#008080', '#e6beff',
        '#9a6324', '#fabebe', '#800000', '#ffe119', '#aaffc3',
      ];

      // Compute node depth: roots = 0, leaves = max depth
      const depthMap: Record<string, number> = {};
      const calcDepth = (name: string, d: number) => {
        if (depthMap[name] !== undefined && depthMap[name] >= d) return;
        depthMap[name] = d;
        for (const c of (preview.classes || [])) {
          if ((c.parents || []).includes(name)) calcDepth(c.name, d + 1);
        }
      };
      // Find roots (no parents or external parents)
      const classNames = new Set((preview.classes || []).map((c: any) => c.name));
      for (const c of (preview.classes || [])) {
        if (!c.parents || c.parents.length === 0 || !c.parents.some((p: string) => classNames.has(p))) {
          calcDepth(c.name, 0);
        }
      }
      const maxDepth = Math.max(...Object.values(depthMap), 1);

      const nodes: any[] = (preview.classes || []).map((c: any, i: number) => {
        const depth = depthMap[c.name] ?? 0;
        // Top-level: 15, leaf: 4
        const val = 15 - ((depth / maxDepth) * 11);
        return {
          id: c.name,
          label: c.label || c.name,
          comment: c.comment || '',
          parents: c.parents || [],
          val,
          color: colorPalette[i % colorPalette.length],
          dataProps: (preview.data_properties || {})[c.name] || [],
        };
      });

      const edges: any[] = [];

      // Object property edges
      for (const p of (preview.object_properties || [])) {
        if (!p.domain || !p.range) continue;
        edges.push({
          source: p.domain,
          target: p.range,
          label: p.label || p.name,
          id: `op_${p.name}_${edges.length}`,
          color: '#666',
        });
      }

      // Inheritance edges (subClassOf)
      for (const c of (preview.classes || [])) {
        if (!c.parents) continue;
        for (const parent of c.parents) {
          edges.push({
            source: c.name,
            target: parent,
            label: '继承',
            id: `inh_${c.name}_${parent}`,
            color: '#aabbcc',
          });
        }
      }

      setGraphData({ nodes, links: edges, preview });
    } catch { /* ignore */ }
    setLoading(false);
  }, [params.collectionId]);

  // Build Mermaid graph TB
  const mermaidCode = useMemo(() => {
    if (!graphData?.preview) return '';
    const classes: any[] = graphData.preview.classes || [];
    const objProps: any[] = graphData.preview.object_properties || [];
    const classMap = new Map(classes.map((c: any) => [c.name, c]));

    // Assign short codes
    let nextCode = 0;
    const codes: Record<string, string> = {};
    const getCode = (name: string) => {
      if (!codes[name]) codes[name] = 'C' + (nextCode++);
      return codes[name];
    };

    // Build hierarchy tree: child → [parents]
    const parents: Record<string, string[]> = {};
    const children: Record<string, string[]> = {};
    for (const c of classes) {
      parents[c.name] = c.parents || [];
      for (const p of c.parents || []) {
        if (!children[p]) children[p] = [];
        children[p].push(c.name);
      }
    }

    // Find root classes (no parents or parents not in our class list)
    const classSet = new Set(classes.map((c: any) => c.name));
    const roots = classes.filter((c: any) => !c.parents || c.parents.length === 0 || !c.parents.some((p: string) => classSet.has(p)));

    // Recursive grouping
    const lines: string[] = ['graph TB'];

    function esc(s: string) { return s.replace(/"/g, '&quot;'); }
    function label(c: any) { return `${esc(c.label || c.name)}<br/>${c.comment ? esc(c.comment.slice(0, 40)) + (c.comment.length > 40 ? '...' : '') : ''}`; }

    // Build subgraph recursively
    function buildSubgraph(clsList: string[], depth: number, parentName: string) {
      for (const name of clsList) {
        const c = classMap.get(name);
        if (!c) continue;
        const code = getCode(name);
        const kids = children[name] || [];
        if (kids.length > 0) {
          lines.push(`  subgraph ${code}["${label(c)}"]`);
          for (const kid of kids) {
            const kc = classMap.get(kid);
            const kcode = getCode(kid);
            lines.push(`    ${kcode}["${kc ? label(kc) : kid}"]`);
          }
          lines.push('  end');
        } else {
          lines.push(`  ${code}["${label(c)}"]`);
        }
      }
    }

    // Step 1: Declare ALL node IDs
    for (const c of classes) getCode(c.name);

    // Step 2: Build subgraphs — root is standalone, children grouped recursively
    const doneNodes = new Set<string>();

    function collectAll(className: string) {
      if (doneNodes.has(className)) return;
      doneNodes.add(className);
      for (const kid of children[className] || []) collectAll(kid);
    }

    function emitSubgraph(className: string, depth: number) {
      const kids = children[className] || [];
      if (kids.length === 0) return;
      const c = classMap.get(className);
      const indent = '  '.repeat(depth + 1);
      if (depth === 0) {
        // Root: node itself at top level, children in subgraph
        lines.push(`  subgraph ${getCode(className)}_sg["${c ? (c.label || c.name) : className}"]`);
        for (const kid of kids) {
          lines.push(`${indent}${getCode(kid)}["${label(classMap.get(kid) || { name: kid, label: kid, comment: '' })}"]`);
          emitSubgraph(kid, depth + 1);
        }
        lines.push('  end');
      } else {
        lines.push(`  subgraph ${getCode(className)}_kid["${c ? (c.label || c.name) : className}"]`);
        for (const kid of kids) {
          lines.push(`${indent}${getCode(kid)}["${label(classMap.get(kid) || { name: kid, label: kid, comment: '' })}"]`);
          emitSubgraph(kid, depth + 1);
        }
        lines.push('  end');
      }
    }

    for (const root of roots) {
      // Declare root node
      lines.push(`  ${getCode(root.name)}["${label(root)}"]`);
      // Declare all descendants
      for (const kid of children[root.name] || []) collectAll(kid);
      // Build subgraph nesting
      emitSubgraph(root.name, 0);
    }

    // Inheritance edges (subClassOf)
    for (const c of classes) {
      for (const p of c.parents || []) {
        if (classSet.has(p)) {
          lines.push(`  ${getCode(c.name)} -->|"继承"| ${getCode(p)}`);
        }
      }
    }

    // Object property edges
    const addedEdges = new Set<string>();
    for (const p of objProps) {
      if (!p.domain || !p.range || !classSet.has(p.domain) || !classSet.has(p.range)) continue;
      const key = `${p.domain}|${p.range}|${p.label || p.name}`;
      if (addedEdges.has(key)) continue;
      addedEdges.add(key);
      const plabel = esc(p.label || p.name);
      lines.push(`  ${getCode(p.domain)} -->|"${plabel}"| ${getCode(p.range)}`);
    }

    // Styles
    lines.push('');
    const colorPalette = ['#e8eaf6,#3f51b5', '#e3f2fd,#1565c0', '#e8f5e9,#2e7d32', '#fff3e0,#e65100', '#fce4ec,#c62828', '#f3e5f5,#6a1b9a'];
    let ci = 0;
    for (const root of roots) {
      const [bg, border] = colorPalette[ci % colorPalette.length].split(',');
      const allNodes = [getCode(root.name)];
      for (const kid of children[root.name] || []) { allNodes.push(getCode(kid)); }
      lines.push(`  classDef group${ci} fill:${bg},stroke:${border},stroke-width:2px;`);
      lines.push(`  class ${allNodes.join(',')} group${ci};`);
      ci++;
    }

    return lines.join('\n');
  }, [graphData]);

  useEffect(() => { loadGraph(); }, [loadGraph]);

  useEffect(() => {
    if (!graphData) return;
    const el = containerRef.current;
    if (!el) return;
    const update = () => setDims({ width: el.offsetWidth, height: el.offsetHeight });
    setTimeout(update, 50);
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, [graphData, showMermaid]);

  const handleEngineStop = useCallback(() => {
    if (graphRef.current) {
      // Spread nodes apart
      const fg = graphRef.current;
      if (fg.d3Force) {
        fg.d3Force('link')?.distance(150);
        fg.d3Force('charge')?.strength(-400);
      }
      fg.zoomToFit(400, 50);
    }
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <LoaderCircle className="size-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!graphData || graphData.nodes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4">
        <p className="text-muted-foreground">{page_collections('no_data')}</p>
        <Button variant="outline" onClick={() => router.back()}>
          <ArrowLeft className="mr-1 h-4 w-4" /> {page_collections('back')}
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      {/* Top bar */}
      <div className="flex items-center gap-3 px-3 py-2 border-b shrink-0">
        <Button variant="ghost" size="icon" onClick={() => router.back()}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h2 className="font-semibold text-base">{page_collections('owl_view_graph')}</h2>
        <span className="text-muted-foreground text-xs">
          {graphData.nodes.length} {page_collections('classes')} / {graphData.links.length} {page_collections('relations')}
        </span>
        <div className="flex-1" />
        <Button variant="ghost" size="sm" className="text-xs gap-1"
          onClick={() => setShowMermaid(!showMermaid)}>
          {showMermaid ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          {page_collections('owl_view_graph')}
        </Button>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-8 w-8"
            onClick={() => graphRef.current?.zoom(1.5, 300)}>
            <Plus className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8"
            onClick={() => graphRef.current?.zoom(0.7, 300)}>
            <Minus className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8"
            onClick={() => graphRef.current?.zoomToFit(400, 50)}>
            <Maximize2 className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8"
            onClick={() => { setGraphData(null); setLoading(true); loadGraph(); }}>
            <RotateCcw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Mermaid diagram — resizable */}
      {showMermaid && mermaidCode && (
        <div ref={mermaidRef} className="border-b bg-muted/20 relative flex flex-col shrink-0 overflow-hidden"
          style={{ flexBasis: `${mermaidPct}%`, minHeight: 100, maxHeight: `${mermaidPct}%` }}>
          <div className="flex items-center justify-between px-3 py-1 border-b bg-muted/40 shrink-0">
            <span className="text-xs text-muted-foreground">Mermaid</span>
            <Button variant="ghost" size="icon" className="h-6 w-6"
              onClick={() => {
                const container = mermaidRef.current?.querySelector<HTMLElement>('.flex-1.overflow-auto');
                if (!container) return;
                const svg = container.querySelector('svg:not(.lucide)');
                if (!svg) return;
                const clone = svg.cloneNode(true) as SVGSVGElement;
                // Set explicit size from the rendered SVG bounding box
                const bbox = svg.getBoundingClientRect();
                const scale = 4;
                const w = Math.max(bbox.width, 600) * scale;
                const h = Math.max(bbox.height, 400) * scale;
                clone.setAttribute('width', String(w));
                clone.setAttribute('height', String(h));
                clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
                // Force light theme — inject CSS that overrides dark Mermaid theme
                const fixStyle = document.createElementNS('http://www.w3.org/2000/svg', 'style');
                fixStyle.textContent = `
                  svg { background: #fff !important; }
                  .node rect, .node circle, .node ellipse, .node polygon, .node path { fill: #e8eaf6 !important; stroke: #3f51b5 !important; }
                  .node .label { color: #1a237e !important; }
                  .node .label text { fill: #1a237e !important; }
                  g.edgePath path { stroke: #666 !important; stroke-width: 1.5px !important; fill: none !important; }
                  .edgeLabel rect { fill: #fff !important; stroke: none !important; }
                  .edgeLabel span, .edgeLabel foreignObject div { color: #333 !important; background: #fff !important; }
                  marker path { fill: #666 !important; stroke: #666 !important; }
                  .cluster rect { fill: #f5f5f5 !important; stroke: #bbb !important; }
                  .cluster .label { color: #333 !important; }
                  text, tspan { fill: #333 !important; }
                `;
                clone.appendChild(fixStyle);
                // Force paths inside edgePath to be visible
                clone.querySelectorAll('g.edgePath path').forEach((el) => {
                  const p = el as SVGPathElement;
                  p.setAttribute('stroke', '#555');
                  p.setAttribute('stroke-width', '1.5');
                  p.setAttribute('fill', 'none');
                });
                const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                bg.setAttribute('width', '100%');
                bg.setAttribute('height', '100%');
                bg.setAttribute('fill', '#ffffff');
                clone.insertBefore(bg, clone.firstChild);

                const data = new XMLSerializer().serializeToString(clone);
                const svgDataUrl = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(data);
                const img = new Image();
                img.onload = () => {
                  const c = document.createElement('canvas');
                  c.width = w;
                  c.height = h;
                  const ctx = c.getContext('2d')!;
                  ctx.fillStyle = '#fff';
                  ctx.fillRect(0, 0, c.width, c.height);
                  ctx.drawImage(img, 0, 0, c.width, c.height);
                  const a = document.createElement('a');
                  a.download = 'owl-mermaid.png';
                  a.href = c.toDataURL('image/png');
                  document.body.appendChild(a);
                  a.click();
                  document.body.removeChild(a);
                };
                img.src = svgDataUrl;
              }}>
              <Download className="h-3 w-3" />
            </Button>
          </div>
          <div className="flex-1 overflow-auto p-2">
            <ChartMermaid>{mermaidCode}</ChartMermaid>
          </div>
          {/* Drag handle */}
          <div
            className="absolute bottom-0 left-0 right-0 h-3 cursor-row-resize hover:bg-primary/20 flex items-center justify-center group z-10"
            onMouseDown={(e) => {
              e.preventDefault();
              const startY = e.clientY;
              const startPct = mermaidPct;
              const rootH = (e.currentTarget.closest('.flex.h-screen') as HTMLElement)?.clientHeight || window.innerHeight;
              const onMove = (ev: MouseEvent) => {
                const dy = ev.clientY - startY;
                setMermaidPct(Math.max(10, Math.min(80, startPct + (dy / rootH) * 100)));
              };
              const onUp = () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
              window.addEventListener('mousemove', onMove);
              window.addEventListener('mouseup', onUp);
            }}
          >
            <div className="w-8 h-1 rounded-full bg-border group-hover:bg-primary/50 transition-colors" />
          </div>
        </div>
      )}
      {dragging && <div className="fixed inset-0 z-50 cursor-row-resize" />}

      {/* Graph area */}
      <div ref={containerRef} className="flex-1 relative min-h-[120px]">
        <ForceGraph2D
          ref={graphRef}
          graphData={graphData}
          width={dims.width}
          height={dims.height}
          nodeLabel={(n) => (n as any).label}
          nodeColor={(n) => (n as any).color || '#4363d8'}
          nodeVal={(n) => (n as any).val || 5}
          linkLabel={(l) => (l as any).label}
          linkColor={(l) => (l as any).color || '#999'}
          linkDirectionalArrowLength={3}
          linkDirectionalArrowRelPos={1}
          linkCurvature={0.25}
          linkWidth={1.5}
          cooldownTicks={120}
          onEngineStop={handleEngineStop}
          linkCanvasObjectMode={() => 'after'}
          linkCanvasObject={(link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
            if (!link.label) return;
            const start = link.source;
            const end = link.target;
            const mx = (start.x! + end.x!) / 2;
            const my = (start.y! + end.y!) / 2;
            const fontSize = Math.max(8, 10 / globalScale);
            ctx.font = `${fontSize}px sans-serif`;
            ctx.fillStyle = '#666';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(link.label, mx, my - 4);
          }}
          nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
            const label = node.label || node.id;
            const size = Math.max(node.val || 5, 4);
            ctx.beginPath();
            ctx.arc(node.x!, node.y!, size, 0, 2 * Math.PI);
            ctx.fillStyle = node.color || '#4363d8';
            ctx.fill();
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 0.5;
            ctx.stroke();
            const fontSize = Math.max(10, 11 / globalScale);
            ctx.font = `${fontSize}px sans-serif`;
            ctx.fillStyle = '#333';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'top';
            ctx.fillText(label, node.x!, node.y! + size + 3);
          }}
          nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
            const size = Math.max(node.val || 5, 4);
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(node.x!, node.y!, size, 0, 2 * Math.PI);
            ctx.fill();
          }}
          onNodeClick={(node: any) => {
            setActiveNode({
              id: node.id,
              label: node.label || node.id,
              comment: node.comment || classComments[node.id] || '',
              properties: (node.dataProps || []).map((p: any) => ({
                name: p.name, label: p.label, range: p.range, comment: p.comment,
              })),
            });
          }}
        />
      </div>

      {/* Properties drawer */}
      <Drawer direction="right" open={!!activeNode} onOpenChange={(v) => { if (!v) setActiveNode(null); }}>
        <DrawerContent className="flex sm:min-w-sm md:min-w-md">
          <DrawerHeader>
            <DrawerTitle>{activeNode?.label || activeNode?.id}</DrawerTitle>
            <Button variant="ghost" size="icon" className="absolute top-2 right-2"
              onClick={() => setActiveNode(null)}>
              <X className="h-4 w-4" />
            </Button>
          </DrawerHeader>
          <div className="flex-1 overflow-auto p-4">
            {activeNode?.comment && (
              <>
                <p className="text-sm text-muted-foreground mb-3">{activeNode.comment}</p>
                <Separator className="my-3" />
              </>
            )}
            {activeNode?.properties && activeNode.properties.length > 0 ? (
              <div className="grid gap-2 text-sm">
                <h4 className="font-medium text-sm mb-1">{page_collections('owl_data_props')}</h4>
                {activeNode.properties.map((p: any) => (
                  <div key={p.name} className="flex flex-col border-b pb-1">
                    <div className="flex items-baseline gap-2">
                      <span className="font-medium">{p.label || p.name}</span>
                      <span className="text-xs text-muted-foreground">({p.range})</span>
                    </div>
                    {p.comment && <span className="text-xs text-muted-foreground">{p.comment}</span>}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                {page_collections('no_data')}
              </p>
            )}
          </div>
        </DrawerContent>
      </Drawer>
    </div>
  );
}
