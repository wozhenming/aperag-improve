'use client';

import dynamic from 'next/dynamic';
import { useTheme } from 'next-themes';
import { useMemo } from 'react';
import Color from 'color';
import * as d3 from 'd3';

const ForceGraph2D = dynamic(
  () => import('react-force-graph-2d').then((r) => r),
  { ssr: false },
);

interface OwlPreview {
  classes: { name: string; label?: string; parents?: string[] }[];
  object_properties: { name: string; label?: string; domain?: string; range?: string }[];
}

const TOPIC_COLORS: Record<string, string> = {
  TechnicalTopic: '#3b82f6',
  ManagementTopic: '#8b5cf6',
  EconomicTopic: '#f59e0b',
  RegulatoryTopic: '#ef4444',
};

export const OwlGraph = ({ preview }: { preview: OwlPreview }) => {
  const { resolvedTheme } = useTheme();
  const color = useMemo(() => d3.scaleOrdinal(d3.schemeCategory10), []);

  const { nodes, links } = useMemo(() => {
    const clsSet = new Set(preview.classes.map((c) => c.name));
    const nodes = preview.classes.map((c) => ({
      id: c.name,
      label: c.label || c.name,
      val: c.parents?.length ? 8 : 5,
      topic: c.parents?.[c.parents.length - 1] || c.name,
    }));

    const links: { source: string; target: string; label: string }[] = [];

    // Hierarchy edges
    for (const c of preview.classes) {
      if (c.parents) {
        for (const p of c.parents) {
          if (clsSet.has(p)) {
            links.push({ source: p, target: c.name, label: 'subClassOf' });
          }
        }
      }
    }

    // Object property edges
    for (const p of preview.object_properties) {
      if (p.domain && p.range && clsSet.has(p.domain) && clsSet.has(p.range)) {
        links.push({ source: p.domain, target: p.range, label: p.label || p.name });
      }
    }

    return { nodes, links };
  }, [preview]);

  return (
    <div className="h-[400px] border rounded">
      <ForceGraph2D
        graphData={{ nodes, links } as any}
        width={700}
        height={400}
        nodeLabel={(n: any) => `${n.label}`}
        linkLabel={(l: any) => l.label}
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={1}
        nodeCanvasObject={(node: any, ctx: any) => {
          const x = node.x || 0, y = node.y || 0;
          const size = Math.min(node.val || 5, 16);
          ctx.beginPath();
          ctx.arc(x, y, size, 0, 2 * Math.PI, false);
          const topic = node.topic || '';
          ctx.fillStyle = TOPIC_COLORS[topic] || color(topic);
          ctx.fill();
          ctx.strokeStyle = resolvedTheme === 'dark' ? '#555' : '#ccc';
          ctx.lineWidth = 0.5;
          ctx.stroke();
          // label
          ctx.font = '10px Arial';
          ctx.fillStyle = resolvedTheme === 'dark' ? '#ddd' : '#333';
          ctx.fillText(node.label || node.id, x + size + 3, y + 4);
        }}
        linkColor={() => (resolvedTheme === 'dark' ? '#666' : '#bbb')}
        linkWidth={1}
      />
    </div>
  );
};
