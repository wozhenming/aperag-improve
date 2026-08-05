'use client';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { toast } from 'sonner';

type Mode = 'ai' | 'blank';

export default function NewOntologyPage() {
  const t = useTranslations('page_ontologies');
  const router = useRouter();
  const [mode, setMode] = useState<Mode>('ai');
  const [title, setTitle] = useState('');
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    if (!title.trim()) {
      toast.error(t('title_required'));
      return;
    }
    setCreating(true);
    const basePath = process.env.NEXT_PUBLIC_BASE_PATH || '';
    try {
      if (mode === 'ai') {
        // AI-guided: start an Ontology Engineer chat session
        const fd = new FormData();
        fd.append('title', title.trim());
        const res = await fetch(`${basePath}/api/v1/ontologies/bot/session`, {
          method: 'POST',
          body: fd,
          credentials: 'include',
        });
        if (!res.ok) throw new Error('session failed');
        const { bot_id, chat_id } = await res.json();
        router.push(`/workspace/bots/${bot_id}/chats/${chat_id}?ontology=1`);
      } else {
        // Build from scratch: create a blank ontology, then open the visual editor
        const fd = new FormData();
        fd.append('title', title.trim());
        const res = await fetch(`${basePath}/api/v1/ontologies`, {
          method: 'POST',
          body: fd,
          credentials: 'include',
        });
        if (!res.ok) throw new Error('create failed');
        const ontology = await res.json();
        router.push(`/workspace/ontologies/${ontology.id}/edit`);
      }
    } catch {
      toast.error('Failed to create');
      setCreating(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-[70vh]">
      <Card className="w-full max-w-xl">
        <CardHeader>
          <CardTitle>{t('add_ontology')}</CardTitle>
          <CardDescription>{t('add_ontology_title_desc')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {/* Mode selection */}
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => setMode('ai')}
              className={cn(
                'rounded-lg border p-3 text-left transition-colors cursor-pointer',
                mode === 'ai' ? 'border-primary bg-primary/5' : 'hover:bg-accent/50',
              )}
            >
              <div className="text-sm font-medium">{t('mode_ai')}</div>
              <div className="mt-1 text-xs text-muted-foreground">{t('mode_ai_desc')}</div>
            </button>
            <button
              type="button"
              onClick={() => setMode('blank')}
              className={cn(
                'rounded-lg border p-3 text-left transition-colors cursor-pointer',
                mode === 'blank' ? 'border-primary bg-primary/5' : 'hover:bg-accent/50',
              )}
            >
              <div className="text-sm font-medium">{t('mode_blank')}</div>
              <div className="mt-1 text-xs text-muted-foreground">{t('mode_blank_desc')}</div>
            </button>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="ontology-title">{t('ontology_title')}</Label>
            <Input
              id="ontology-title"
              placeholder={t('ontology_title_placeholder')}
              value={title}
              onChange={(e) => setTitle(e.currentTarget.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCreate();
              }}
              autoFocus
            />
          </div>
          <Button onClick={handleCreate} disabled={creating || !title.trim()}>
            {creating ? '...' : mode === 'ai' ? t('start_guide') : t('create_blank')}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
