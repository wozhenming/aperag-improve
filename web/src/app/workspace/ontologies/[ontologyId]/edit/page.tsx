'use client';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { MermaidView, exportMermaidPng } from '@/components/mermaid-view';
import { OntologyStructureEditor } from '@/components/ontology-structure-editor';
import { buildOwlMermaid } from '@/lib/owl-mermaid';
import { Textarea } from '@/components/ui/textarea';
import axios from 'axios';
import {
  ArrowLeft, Code2, Copy, Download, Eye, LoaderCircle, Save, Shapes,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';

type EditMode = 'visual' | 'source';

export default function EditOntologyPage() {
  const params = useParams<{ ontologyId: string }>();
  const router = useRouter();
  const t = useTranslations('page_ontologies');
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [mode, setMode] = useState<EditMode>('visual');
  const [structure, setStructure] = useState<any>(null);

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

  // Initial parsed structure for the visual editor + graph
  useEffect(() => {
    (async () => {
      try {
        const { data } = await axios.get(`${basePath}/api/v1/ontologies/${params.ontologyId}/structure`);
        setStructure(data);
      } catch {
        setStructure(null);
      }
    })();
  }, [params.ontologyId, basePath]);

  // In source mode: live-parse the raw OWL text (debounced) so the graph stays in sync
  useEffect(() => {
    if (mode !== 'source') return;
    const timer = setTimeout(async () => {
      try {
        const { data } = await axios.post(`${basePath}/api/v1/ontologies/parse`, { content });
        setStructure(data);
      } catch {
        /* transient parse errors — keep last good structure */
      }
    }, 800);
    return () => clearTimeout(timer);
  }, [mode, content, basePath]);

  // Primary: mermaid generated from the structure (live in both modes).
  // Fallback: embedded ```mermaid block saved in the content from the chat.
  const mermaidCode = useMemo(() => {
    if (structure && !structure.error && structure.classes?.length) {
      return buildOwlMermaid(structure);
    }
    const m = content.match(/```mermaid\s*([\s\S]*?)```/);
    return m ? m[1] : '';
  }, [structure, content]);

  const handleSave = async () => {
    setSaving(true);
    try {
      if (mode === 'visual') {
        // Rebuild canonical OWL from the edited structure
        const { data } = await axios.post(
          `${basePath}/api/v1/ontologies/${params.ontologyId}/rebuild`,
          { structure, title },
        );
        setContent(data.content);
      } else {
        await axios.put(`${basePath}/api/v1/ontologies/${params.ontologyId}/content`, {
          content,
          title,
        });
      }
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

  const handleCopyMermaid = async () => {
    try {
      await navigator.clipboard.writeText(mermaidCode);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = mermaidCode;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    toast.success(t('copied'));
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
        <Button
          variant="outline"
          onClick={() => setMode(mode === 'visual' ? 'source' : 'visual')}
          className="gap-1"
        >
          {mode === 'visual' ? <Code2 className="h-4 w-4" /> : <Shapes className="h-4 w-4" />}
          {mode === 'visual' ? t('edit_mode') : t('preview_mode')}
        </Button>
        <Button onClick={handleSave} disabled={saving}>
          <Save className="h-4 w-4 mr-1" /> {t('save_ontology')}
        </Button>
      </div>

      <div className="grid gap-4 flex-1 md:grid-cols-2 min-h-0">
        <Card className="flex flex-col min-h-0">
          <CardHeader className="flex flex-row items-center justify-between py-3">
            <CardTitle className="text-sm">
              {mode === 'visual' ? t('editor.classes') : 'OWL'}
            </CardTitle>
            {mode === 'source' && (
              <span className="text-xs text-muted-foreground">{t('editor.source_hint')}</span>
            )}
          </CardHeader>
          <CardContent className="flex-1 min-h-0 p-0">
            {mode === 'visual' ? (
              <OntologyStructureEditor structure={structure} onChange={setStructure} />
            ) : (
              <Textarea
                className="h-full min-h-[300px] font-mono text-xs rounded-none border-0"
                value={content}
                onChange={(e) => setContent(e.currentTarget.value)}
              />
            )}
          </CardContent>
        </Card>

        <Card className="flex flex-col min-h-0">
          <CardHeader className="flex flex-row items-center justify-between py-3">
            <CardTitle className="text-sm">Mermaid</CardTitle>
            {mermaidCode && (
              <div className="flex items-center gap-1">
                <Button variant="ghost" size="icon" className="h-6 w-6" onClick={handleCopyMermaid}>
                  <Copy className="h-3 w-3" />
                </Button>
                <Button variant="ghost" size="icon" className="h-6 w-6"
                  onClick={() => exportMermaidPng(mermaidCode, `${title || 'ontology'}-mermaid.png`)}>
                  <Download className="h-3 w-3" />
                </Button>
              </div>
            )}
          </CardHeader>
          <CardContent className="flex-1 min-h-0 p-0 flex">
            {mermaidCode ? (
              <div className="flex-1 min-h-0">
                <MermaidView code={mermaidCode} />
              </div>
            ) : (
              <p className="text-muted-foreground text-sm p-4">{t('no_mermaid_hint')}</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
