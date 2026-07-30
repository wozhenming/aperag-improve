'use client';

import { Button } from '@/components/ui/button';
import axios from 'axios';
import { ArrowLeft, LoaderCircle, Maximize2, Minus, Plus, RotateCcw } from 'lucide-react';
import { useTranslations } from 'next-intl';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';

const ForceGraph2D = dynamic(() => import('react-force-graph-2d').then((r) => r), { ssr: false });

interface GraphNode {
  id: string;
  label: string;
  parents?: string[];
  val?: number;
}

interface GraphEdge {
  source: string;
  target: string;
  label: string;
  id: string;
}

export default function OwlGraphPage() {
  const params = useParams();
  const page_collections = useTranslations('page_collections');
  const [graphData, setGraphData] = useState<{ nodes: GraphNode[]; links: GraphEdge[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<any>(null);
  const [dims, setDims] = useState({ width: 800, height: 600 });

  const loadGraph = useCallback(async () => {
    if (typeof params.collectionId !== 'string') return;
    try {
      const basePath = process.env.NEXT_PUBLIC_BASE_PATH || '';
      const { data } = await axios.get(
        `${basePath}/api/v1/collections/${params.collectionId}/owl`
      );
      const preview = (data as any).preview;
      if (!preview) { setLoading(false); return; }

      const colorPalette = [
        '#e6194b', '#3cb44b', '#4363d8', '#f58231', '#911eb4',
        '#46f0f0', '#f032e6', '#bcf60c', '#008080', '#e6beff',
        '#9a6324', '#fabebe', '#800000', '#ffe119', '#aaffc3',
      ];

      const nodes: GraphNode[] = (preview.classes || []).map(
        (c: any, i: number) => ({
          id: c.name,
          label: c.label || c.name,
          parents: c.parents || [],
          val: (c.parents?.length || 0) * 3 + 5,
          color: colorPalette[i % colorPalette.length],
        })
      );

      const edges: GraphEdge[] = (preview.object_properties || [])
        .filter((p: any) => p.domain && p.range)
        .map((p: any, i: number) => ({
          source: p.domain,
          target: p.range,
          label: p.label || p.name,
          id: `${p.name}_${i}`,
        }));

      setGraphData({ nodes, links: edges });
    } catch { /* ignore */ }
    setLoading(false);
  }, [params.collectionId]);

  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  // Resize handler — triggered after DOM renders
  useEffect(() => {
    if (!graphData) return;
    const el = containerRef.current;
    if (!el) return;
    const update = () => setDims({ width: el.offsetWidth, height: el.offsetHeight });
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, [graphData]);

  // Auto zoom-to-fit after engine settles
  const handleEngineStop = useCallback(() => {
    if (graphRef.current) {
      graphRef.current.zoomToFit(400, 50);
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
        <Button asChild variant="outline">
          <Link href={`/workspace/collections/${params.collectionId}`}>
            <ArrowLeft className="mr-1 h-4 w-4" /> {page_collections('back')}
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      {/* Top bar */}
      <div className="flex items-center gap-3 px-3 py-2 border-b shrink-0">
        <Button asChild variant="ghost" size="icon">
          <Link href={`/workspace/collections/${params.collectionId}`}>
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <h2 className="font-semibold text-base">{page_collections('owl_view_graph')}</h2>
        <span className="text-muted-foreground text-xs">
          {graphData.nodes.length} {page_collections('classes')} / {graphData.links.length} {page_collections('relations')}
        </span>
        <div className="flex-1" />
        {/* Control buttons */}
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
            onClick={() => loadGraph()}>
            <RotateCcw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Graph area */}
      <div ref={containerRef} className="flex-1 relative">
        <ForceGraph2D
          ref={graphRef}
          graphData={graphData}
          width={dims.width}
          height={dims.height}
          nodeLabel={(n) => (n as GraphNode).label}
          nodeColor={(n) => (n as any).color || '#4363d8'}
          nodeVal={(n) => (n as GraphNode).val || 5}
          linkLabel={(l) => (l as GraphEdge).label}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={1}
          linkCurvature={0.25}
          linkWidth={1.5}
          cooldownTicks={100}
          onEngineStop={handleEngineStop}
          nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
            const label = node.label || node.id;
            const size = Math.max(node.val || 5, 4);
            // Node circle
            ctx.beginPath();
            ctx.arc(node.x!, node.y!, size, 0, 2 * Math.PI);
            ctx.fillStyle = node.color || '#4363d8';
            ctx.fill();
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 0.5;
            ctx.stroke();
            // Label below node
            const fontSize = Math.max(10, 12 / globalScale);
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
        />
      </div>
    </div>
  );
}
