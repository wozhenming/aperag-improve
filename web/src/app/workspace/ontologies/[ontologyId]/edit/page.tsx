'use client';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import axios from 'axios';
import { ArrowLeft, Download, Eye, LoaderCircle, Pencil, Save } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';

export default function EditOntologyPage() {
  const params = useParams<{ ontologyId: string }>();
  const router = useRouter();
  const t = useTranslations('page_ontologies');
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState(false);
  const [mermaidCode, setMermaidCode] = useState('');

  const basePath = process.env.NEXT_PUBLIC_BASE_PATH || '';

  useEffect(() => {
    (async () => {
      try {
        const res = await axios.get(`${basePath}/api/v1/ontologies/${params.ontologyId}/content`);
        setTitle(res.data.title || '');
        setContent(res.data.content || '');
      } catch {
        toast.error('Failed to load');
      } finally {
        setLoading(false);
      }
    })();
  }, [params.ontologyId, basePath]);

  // Parse Mermaid from OWL code blocks if present in content (e.g. saved from chat)
  useEffect(() => {
    const m = content.match(/```mermaid\s*([\s\S]*?)```/);
    if (m) setMermaidCode(m[1]);
  }, [content]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await axios.put(`${basePath}/api/v1/ontologies/${params.ontologyId}/content`, {
        content,
        title,
      });
      toast.success(t('saved_success'));
      router.refresh();
    } catch {
      toast.error('Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleDownload = () => {
    const blob = new Blob([content], { type: 'application/xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${title || 'ontology'}.owl`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return <div className="flex items-center justify-center h-screen"><LoaderCircle className="size-8 animate-spin text-muted-foreground" /></div>;
  }

  return (
    <div className="flex flex-col gap-4 h-[calc(100vh-6rem)]">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => router.back()}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <Input
          value={title}
          onChange={(e) => setTitle(e.currentTarget.value)}
          className="max-w-xs font-semibold"
        />
        <div className="flex-1" />
        <Button variant="outline" onClick={handleDownload}>
          <Download className="h-4 w-4 mr-1" /> {t('export_ontology')}
        </Button>
        <Button variant="outline" onClick={() => setPreview(!preview)}>
          {preview ? <Pencil className="h-4 w-4 mr-1" /> : <Eye className="h-4 w-4 mr-1" />}
          {preview ? t('edit_mode') : t('preview_mode')}
        </Button>
        <Button onClick={handleSave} disabled={saving}>
          <Save className="h-4 w-4 mr-1" /> {t('save_ontology')}
        </Button>
      </div>

      {preview ? (
        <div className="flex-1 overflow-auto rounded-lg border p-4">
          <pre className="text-xs leading-relaxed whitespace-pre-wrap font-mono">{content}</pre>
        </div>
      ) : (
        <div className="grid gap-4 flex-1 md:grid-cols-2 min-h-0">
          <Card className="flex flex-col min-h-0">
            <CardHeader><CardTitle className="text-sm">OWL</CardTitle></CardHeader>
            <CardContent className="flex-1 min-h-0 p-2">
              <Textarea
                className="h-full min-h-[300px] font-mono text-xs"
                value={content}
                onChange={(e) => setContent(e.currentTarget.value)}
              />
            </CardContent>
          </Card>
          <Card className="flex flex-col min-h-0">
            <CardHeader><CardTitle className="text-sm">Mermaid</CardTitle></CardHeader>
            <CardContent className="flex-1 min-h-0 overflow-auto p-2">
              {mermaidCode ? (
                <OwlMermaid code={mermaidCode} />
              ) : (
                <p className="text-muted-foreground text-sm p-4">{t('no_mermaid_hint')}</p>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

function OwlMermaid({ code }: { code: string }) {
  const [svg, setSvg] = useState('');
  const [id] = useState(() => 'edit-mermaid-' + String(Math.floor(Math.random() * 100000)));
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const { default: mermaid } = await import('mermaid');
      mermaid.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'loose' });
      try {
        const r = await mermaid.render(id, code);
        if (!cancelled) setSvg(r.svg);
      } catch {
        /* invalid */
      }
    })();
    return () => { cancelled = true; };
  }, [code, id]);
  if (!svg) return <p className="text-muted-foreground text-sm p-4">...</p>;
  return <div dangerouslySetInnerHTML={{ __html: svg }} className="overflow-auto" />;
}
