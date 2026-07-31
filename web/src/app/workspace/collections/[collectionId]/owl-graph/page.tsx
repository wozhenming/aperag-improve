'use client';

import { Button } from '@/components/ui/button';
import {
  Drawer, DrawerContent, DrawerHeader, DrawerTitle,
} from '@/components/ui/drawer';
import { Separator } from '@/components/ui/separator';
import axios from 'axios';
import { ArrowLeft, ChevronDown, ChevronUp, Code2, Download, LoaderCircle, Maximize2, Minus, Plus, RotateCcw, X } from 'lucide-react';
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
  const mermaidZoomRef = useRef<any>(null);
  const [mermaidSvg, setMermaidSvg] = useState('');
  const [mermaidTab, setMermaidTab] = useState<'graph' | 'code'>('graph');
  const [dims, setDims] = useState({ width: 800, height: 600 });
  const [activeNode, setActiveNode] = useState<any>(null);
  const [showMermaid, setShowMermaid] = useState(true);
  const [classComments, setClassComments] = useState<Record<string, string>>({});

  const loadGraph = useCallback(async () => {
    if (typeof params.collectionId !== 'string') return;
    try {
      const basePath = process.env.NEXT_PUBLIC_BASE_PATH || '';
      const { data } = await axios.get(`${basePath}/api/v1/collections/${params.collectionId}/owl`);
      const preview = (data as any).preview;
      if (!preview) { setLoading(false); return; }
      const comments: Record<string, string> = {};
      for (const c of preview.classes || []) { if (c.comment) comments[c.name] = c.comment; }
      setClassComments(comments);
      const colorPalette = ['#e6194b','#3cb44b','#4363d8','#f58231','#911eb4','#46f0f0','#f032e6','#bcf60c','#008080','#e6beff','#9a6324','#fabebe','#800000','#ffe119','#aaffc3'];
      const depthMap: Record<string, number> = {};
      const calcDepth = (name: string, d: number) => { if (depthMap[name] !== undefined && depthMap[name] >= d) return; depthMap[name] = d; for (const c of (preview.classes || [])) { if ((c.parents || []).includes(name)) calcDepth(c.name, d + 1); } };
      const classNames = new Set((preview.classes || []).map((c: any) => c.name));
      for (const c of (preview.classes || [])) { if (!c.parents || c.parents.length === 0 || !c.parents.some((p: string) => classNames.has(p))) calcDepth(c.name, 0); }
      const maxDepth = Math.max(...Object.values(depthMap), 1);
      const nodes: any[] = (preview.classes || []).map((c: any, i: number) => { const depth = depthMap[c.name] ?? 0; const val = 15 - ((depth / maxDepth) * 11); return { id: c.name, label: c.label || c.name, comment: c.comment || '', parents: c.parents || [], val, color: colorPalette[i % colorPalette.length], dataProps: (preview.data_properties || {})[c.name] || [] }; });
      const edges: any[] = [];
      for (const p of (preview.object_properties || [])) { if (!p.domain || !p.range) continue; edges.push({ source: p.domain, target: p.range, label: p.label || p.name, id: `op_${p.name}_${edges.length}`, color: '#666' }); }
      for (const c of (preview.classes || [])) { if (!c.parents) continue; for (const parent of c.parents) { edges.push({ source: c.name, target: parent, label: '继承', id: `inh_${c.name}_${parent}`, color: '#aabbcc' }); } }
      setGraphData({ nodes, links: edges, preview });
    } catch { /* ignore */ }
    setLoading(false);
  }, [params.collectionId]);

  const mermaidCode = useMemo(() => {
    if (!graphData?.preview) return '';
    const classes: any[] = graphData.preview.classes || [];
    const objProps: any[] = graphData.preview.object_properties || [];
    const classMap = new Map(classes.map((c: any) => [c.name, c]));
    function esc(s: string) { return s.replace(/"/g, '&quot;'); }
    function label(c: any) { return `${esc(c.label || c.name)}<br/>${c.comment ? esc(c.comment.slice(0, 40)) + (c.comment.length > 40 ? '...' : '') : ''}`; }
    let nextCode = 0; const codes: Record<string, string> = {}; const getCode = (n: string) => { if (!codes[n]) codes[n] = 'C' + (nextCode++); return codes[n]; };
    const children: Record<string, string[]> = {};
    for (const c of classes) { for (const p of c.parents || []) { if (!children[p]) children[p] = []; children[p].push(c.name); } }
    const classSet = new Set(classes.map((c: any) => c.name));
    const roots = classes.filter((c: any) => !c.parents || c.parents.length === 0 || !c.parents.some((p: string) => classSet.has(p)));
    const lines: string[] = ['graph TB'];
    for (const c of classes) getCode(c.name);
    const doneNodes = new Set<string>();
    // Recursive function to collect and declare all descendants
    function collectDescendants(name: string) {
      if (doneNodes.has(name)) return;
      const c = classMap.get(name);
      lines.push(`  ${getCode(name)}["${c ? label(c) : name}"]`);
      doneNodes.add(name);
      for (const kid of children[name] || []) collectDescendants(kid);
    }
    for (const root of roots) {
      lines.push(`  subgraph ${getCode(root.name)}_sg["${label(root)} - 子类"]`);
      for (const kid of children[root.name] || []) collectDescendants(kid);
      lines.push('  end');
    }
    for (const c of classes) { for (const p of c.parents || []) { if (classSet.has(p)) lines.push(`  ${getCode(c.name)} -->|"继承"| ${getCode(p)}`); } }
    const addedEdges = new Set<string>();
    for (const p of objProps) { if (!p.domain || !p.range || !classSet.has(p.domain) || !classSet.has(p.range)) continue; const key = `${p.domain}|${p.range}|${p.label || p.name}`; if (addedEdges.has(key)) continue; addedEdges.add(key); lines.push(`  ${getCode(p.domain)} -->|"${esc(p.label || p.name)}"| ${getCode(p.range)}`); }
    lines.push('');
    const colorPalette2 = ['#e8eaf6,#3f51b5', '#e3f2fd,#1565c0', '#e8f5e9,#2e7d32', '#fff3e0,#e65100', '#fce4ec,#c62828', '#f3e5f5,#6a1b9a'];
    let ci = 0;
    for (const root of roots) { const [bg, border] = colorPalette2[ci % colorPalette2.length].split(','); const allNodes = [getCode(root.name)]; for (const kid of children[root.name] || []) allNodes.push(getCode(kid)); lines.push(`  classDef group${ci} fill:${bg},stroke:${border},stroke-width:2px;`); lines.push(`  class ${allNodes.join(',')} group${ci};`); ci++; }
    return lines.join('\n');
  }, [graphData]);

  useEffect(() => {
    if (!showMermaid || !mermaidCode) return;
    let cancelled = false;
    (async () => {
      const { default: mermaid } = await import('mermaid');
      mermaid.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'loose' });
      const id = 'owl-mermaid-' + Date.now();
      try {
        const { svg } = await mermaid.render(id, mermaidCode);
        if (!cancelled) setMermaidSvg(svg);
      } catch { /* ignore render errors */ }
    })();
    return () => { cancelled = true; };
  }, [mermaidCode, showMermaid]);

  // Attach panzoom to Mermaid SVG container after render
  useEffect(() => {
    if (!showMermaid || !mermaidSvg) return;
    const el = mermaidZoomRef.current;
    if (!el) return;
    let pz: any;
    import('panzoom').then(({ default: panzoom }) => {
      pz = panzoom(el, { minZoom: 0.3, maxZoom: 5 });
    });
    return () => { if (pz) pz.dispose(); };
  }, [mermaidSvg, showMermaid]);

  useEffect(() => { loadGraph(); }, [loadGraph]);

  useEffect(() => {
    if (!graphData) return;
    const el = containerRef.current; if (!el) return;
    const update = () => setDims({ width: el.offsetWidth, height: el.offsetHeight });
    setTimeout(update, 50);
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, [graphData, showMermaid]);

  const handleEngineStop = useCallback(() => {
    if (graphRef.current) { const fg = graphRef.current; if (fg.d3Force) { fg.d3Force('link')?.distance(150); fg.d3Force('charge')?.strength(-400); } fg.zoomToFit(400, 50); }
  }, []);

  if (loading) return (<div className="flex items-center justify-center h-screen"><LoaderCircle className="size-8 animate-spin text-muted-foreground" /></div>);
  if (!graphData || graphData.nodes.length === 0) return (<div className="flex flex-col items-center justify-center h-screen gap-4"><p className="text-muted-foreground">{page_collections('no_data')}</p><Button variant="outline" onClick={() => router.back()}><ArrowLeft className="mr-1 h-4 w-4" />{page_collections('back')}</Button></div>);

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <div className="flex items-center gap-3 px-3 py-2 border-b shrink-0">
        <Button variant="ghost" size="icon" onClick={() => router.back()}><ArrowLeft className="h-4 w-4" /></Button>
        <h2 className="font-semibold text-base">{page_collections('owl_view_graph')}</h2>
        <span className="text-muted-foreground text-xs">{graphData.nodes.length} {page_collections('classes')} / {graphData.links.length} {page_collections('relations')}</span>
        <div className="flex-1" />
        <Button variant="ghost" size="sm" className="text-xs gap-1" onClick={() => setShowMermaid(!showMermaid)}>
          {showMermaid ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}{page_collections('owl_view_graph')}
        </Button>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => graphRef.current?.zoom(1.5, 300)}><Plus className="h-4 w-4" /></Button>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => graphRef.current?.zoom(0.7, 300)}><Minus className="h-4 w-4" /></Button>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => graphRef.current?.zoomToFit(400, 50)}><Maximize2 className="h-4 w-4" /></Button>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => { setGraphData(null); setLoading(true); loadGraph(); }}><RotateCcw className="h-4 w-4" /></Button>
        </div>
      </div>

      {showMermaid && mermaidCode ? (
        <div className="flex-1 flex flex-col bg-muted/20 relative z-0">
          <div className="flex items-center justify-between px-3 py-1 border-b bg-muted/40 shrink-0">
            <div className="flex items-center gap-1">
              <Button variant={mermaidTab === 'graph' ? 'secondary' : 'ghost'} size="sm" className="h-7 text-xs"
                onClick={() => setMermaidTab('graph')}>{page_collections('owl_view_graph')}</Button>
              <Button variant={mermaidTab === 'code' ? 'secondary' : 'ghost'} size="sm" className="h-7 text-xs"
                onClick={() => setMermaidTab('code')}><Code2 className="h-3 w-3 mr-1" />Code</Button>
            </div>
            <Button variant="ghost" size="icon" className="h-6 w-6"
              onClick={async () => {
                const { default: mermaid } = await import('mermaid');
                mermaid.initialize({ startOnLoad: false, theme: 'neutral' });
                const id = 'mermaid-export-' + Date.now();
                const { svg: cleanSvg } = await mermaid.render(id, mermaidCode);
                document.getElementById('d' + id)?.remove();
                const scale = 4; const w = 800 * scale; const h = 600 * scale;
                const wrapper = document.createElement('div'); wrapper.innerHTML = cleanSvg;
                const cleanEl = wrapper.querySelector('svg')!;
                cleanEl.setAttribute('width', String(w)); cleanEl.setAttribute('height', String(h));
                const data = new XMLSerializer().serializeToString(cleanEl);
                const url = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(data);
                const img = new Image();
                img.onload = () => {
                  const c = document.createElement('canvas'); c.width = w; c.height = h;
                  const ctx = c.getContext('2d')!; ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, w, h); ctx.drawImage(img, 0, 0, w, h);
                  const a = document.createElement('a'); a.download = 'owl-mermaid.png'; a.href = c.toDataURL('image/png');
                  document.body.appendChild(a); a.click(); document.body.removeChild(a);
                };
                img.src = url;
              }}>
              <Download className="h-3 w-3" /></Button>
          </div>
          {mermaidTab === 'graph' ? (
            <div ref={mermaidZoomRef} className="flex-1 overflow-auto cursor-move p-4" dangerouslySetInnerHTML={{ __html: mermaidSvg }} />
          ) : (
            <div className="flex-1 overflow-auto p-4">
              <textarea readOnly className="w-full h-full text-xs font-mono text-muted-foreground bg-transparent border-0 resize-none p-4 outline-none" value={mermaidCode} />
            </div>
          )}
        </div>
      ) : (
        <div ref={containerRef} className="flex-1 relative min-h-[100px] overflow-hidden">
        <ForceGraph2D ref={graphRef} graphData={graphData} width={dims.width} height={dims.height}
          nodeLabel={(n) => (n as any).label} nodeColor={(n) => (n as any).color || '#4363d8'} nodeVal={(n) => (n as any).val || 5}
          linkLabel={(l) => (l as any).label} linkColor={(l) => (l as any).color || '#999'}
          linkDirectionalArrowLength={3} linkDirectionalArrowRelPos={1} linkCurvature={0.25} linkWidth={1.5}
          cooldownTicks={120} onEngineStop={handleEngineStop}
          nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
            const label = node.label || node.id; const size = Math.max(node.val || 5, 4);
            ctx.beginPath(); ctx.arc(node.x!, node.y!, size, 0, 2 * Math.PI); ctx.fillStyle = node.color || '#4363d8'; ctx.fill();
            ctx.strokeStyle = '#fff'; ctx.lineWidth = 0.5; ctx.stroke();
            const fontSize = Math.max(10, 11 / globalScale); ctx.font = `${fontSize}px sans-serif`; ctx.fillStyle = '#333';
            ctx.textAlign = 'center'; ctx.textBaseline = 'top'; ctx.fillText(label, node.x!, node.y! + size + 3);
          }}
          nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => { const size = Math.max(node.val || 5, 4); ctx.fillStyle = color; ctx.beginPath(); ctx.arc(node.x!, node.y!, size, 0, 2 * Math.PI); ctx.fill(); }}
          linkCanvasObjectMode={() => 'after'}
          linkCanvasObject={(link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
            if (!link.label) return; const start = link.source; const end = link.target;
            const mx = (start.x! + end.x!) / 2; const my = (start.y! + end.y!) / 2;
            const fontSize = Math.max(8, 10 / globalScale); ctx.font = `${fontSize}px sans-serif`;
            ctx.fillStyle = '#666'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(link.label, mx, my - 4);
          }}
          onNodeClick={(node: any) => setActiveNode({ id: node.id, label: node.label || node.id, comment: node.comment || classComments[node.id] || '', properties: (node.dataProps || []).map((p: any) => ({ name: p.name, label: p.label, range: p.range, comment: p.comment })) })}
        />
      </div>
      )}

      <Drawer direction="right" open={!!activeNode} onOpenChange={(v) => { if (!v) setActiveNode(null); }}>
        <DrawerContent className="flex sm:min-w-sm md:min-w-md"><DrawerHeader><DrawerTitle>{activeNode?.label || activeNode?.id}</DrawerTitle><Button variant="ghost" size="icon" className="absolute top-2 right-2" onClick={() => setActiveNode(null)}><X className="h-4 w-4" /></Button></DrawerHeader>
          <div className="flex-1 overflow-auto p-4">
            {activeNode?.comment && <><p className="text-sm text-muted-foreground mb-3">{activeNode.comment}</p><Separator className="my-3" /></>}
            {activeNode?.properties && activeNode.properties.length > 0 ? (<div className="grid gap-2 text-sm"><h4 className="font-medium text-sm mb-1">{page_collections('owl_data_props')}</h4>{activeNode.properties.map((p: any) => (<div key={p.name} className="flex flex-col border-b pb-1"><div className="flex items-baseline gap-2"><span className="font-medium">{p.label || p.name}</span><span className="text-xs text-muted-foreground">({p.range})</span></div>{p.comment && <span className="text-xs text-muted-foreground">{p.comment}</span>}</div>))}</div>) : (<p className="text-sm text-muted-foreground">{page_collections('no_data')}</p>)}
          </div>
        </DrawerContent>
      </Drawer>
    </div>
  );
}
