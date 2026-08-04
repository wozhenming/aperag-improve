'use client';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { toast } from 'sonner';

export default function NewOntologyPage() {
  const t = useTranslations('page_ontologies');
  const router = useRouter();
  const [title, setTitle] = useState('');
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    if (!title.trim()) {
      toast.error(t('title_required'));
      return;
    }
    setCreating(true);
    try {
      const fd = new FormData();
      fd.append('title', title.trim());
      const basePath = process.env.NEXT_PUBLIC_BASE_PATH || '';
      const res = await fetch(`${basePath}/api/v1/ontologies/bot/session`, {
        method: 'POST',
        body: fd,
        credentials: 'include',
      });
      if (!res.ok) throw new Error('session failed');
      const { bot_id, chat_id } = await res.json();
      router.push(`/workspace/bots/${bot_id}/chats/${chat_id}?ontology=1`);
    } catch {
      toast.error('Failed to start session');
      setCreating(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-[70vh]">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{t('add_ontology')}</CardTitle>
          <CardDescription>{t('add_ontology_title_desc')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
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
            {creating ? '...' : t('start_guide')}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
