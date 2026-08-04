'use client';

import { useEffect, useRef, useState } from 'react';

/* Full-size Mermaid renderer with pan/zoom — same as the collection owl-graph page. */
export function MermaidView({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState('');
  const [id] = useState(() => 'mv-' + String(Math.floor(Math.random() * 100000)));
  useEffect(() => {
    let cancelled = false;
    import('mermaid').then(({ default: mermaid }) => {
      if (cancelled) return;
      mermaid.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'loose' });
      mermaid.render(id, code).then((r) => { if (!cancelled) setSvg(r.svg); }).catch(() => {});
    });
    return () => { cancelled = true; };
  }, [code, id]);
  useEffect(() => {
    if (!svg || !ref.current) return;
    let zoomInstance: any;
    import('panzoom').then(({ default: panzoom }) => {
      const el = ref.current;
      if (el) zoomInstance = panzoom(el, { minZoom: 0.2, maxZoom: 10, smoothScroll: false });
    });
    return () => { if (zoomInstance && typeof zoomInstance.dispose === 'function') zoomInstance.dispose(); };
  }, [svg]);
  if (!svg) return null;
  return (
    <div className="w-full h-full overflow-hidden">
      <div
        ref={ref}
        className="w-full h-full flex items-center justify-center cursor-move"
        dangerouslySetInnerHTML={{
          __html: svg.replace(/<svg/, '<svg style="max-width:100%;max-height:100%"'),
        }}
      />
    </div>
  );
}

/* Render the mermaid code and download it as a cropped PNG (uses the SVG viewBox, scale 4x). */
export async function exportMermaidPng(code: string, filename = 'ontology-mermaid.png') {
  const { default: mermaid } = await import('mermaid');
  mermaid.initialize({ startOnLoad: false, theme: 'neutral' });
  const id = 'mermaid-export-' + String(Math.floor(Math.random() * 100000));
  const { svg: cleanSvg } = await mermaid.render(id, code);
  document.getElementById('d' + id)?.remove();
  const wrapper = document.createElement('div');
  wrapper.innerHTML = cleanSvg;
  const cleanEl = wrapper.querySelector('svg')!;
  const vb = (cleanEl.getAttribute('viewBox') || '0 0 800 600').split(' ').map(Number);
  const vbw = vb[2] || 800;
  const vbh = vb[3] || 600;
  const scale = 4;
  const w = Math.round(vbw * scale);
  const h = Math.round(vbh * scale);
  cleanEl.setAttribute('width', String(w));
  cleanEl.setAttribute('height', String(h));
  const data = new XMLSerializer().serializeToString(cleanEl);
  const url = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(data);
  const img = new Image();
  img.onload = () => {
    const c = document.createElement('canvas');
    c.width = w;
    c.height = h;
    const ctx = c.getContext('2d')!;
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, w, h);
    ctx.drawImage(img, 0, 0, w, h);
    const a = document.createElement('a');
    a.download = filename;
    a.href = c.toDataURL('image/png');
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };
  img.src = url;
}
