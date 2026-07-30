'use client';

import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import axios from 'axios';
import { ArrowLeft, LoaderCircle } from 'lucide-react';
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
  const [dims, setDims] = useState({ width: 600, height: 500 });

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
        '#e6194b', '#3cb44b', '#ffe119', '#4363d8', '#f58231',
        '#911eb4', '#46f0f0', '#f032e6', '#bcf60c', '#fabebe',
        '#008080', '#e6beff', '#9a6324', '#fffac8', '#800000',
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
    const el = containerRef.current;
    if (el) {
      setDims({ width: el.offsetWidth - 4, height: el.offsetHeight - 4 });
      const onResize = () => setDims({ width: el.offsetWidth - 4, height: el.offsetHeight - 4 });
      window.addEventListener('resize', onResize);
      return () => window.removeEventListener('resize', onResize);
    }
  }, [loadGraph]);

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
    <div className="flex flex-col h-screen">
      <div className="flex items-center gap-4 p-3 border-b">
        <Button asChild variant="ghost" size="icon">
          <Link href={`/workspace/collections/${params.collectionId}`}>
            <ArrowLeft />
          </Link>
        </Button>
        <h2 className="font-semibold text-lg">{page_collections('owl_view_graph')}</h2>
        <span className="text-muted-foreground text-sm">
          {graphData.nodes.length} {page_collections('classes')}, {graphData.links.length} {page_collections('relations')}
        </span>
      </div>
      <Card ref={containerRef} className="flex-1 m-2 bg-card/0">
        <ForceGraph2D
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
          onEngineStop={() => {
            // Zoom to fit
          }}
        />
      </Card>
    </div>
  );
}
