'use client';

import { Button } from '@/components/ui/button';
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import axios from 'axios';
import { Boxes, FileUp, Plus, Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useRef, useState } from 'react';
import { toast } from 'sonner';

interface OntologyItem {
  id: string;
  title?: string;
  description?: string;
  preview?: {
    classes_count?: number;
    object_properties_count?: number;
    data_properties_count?: number;
  } | null;
  created?: string;
}

export const OntologyList = ({ ontologies }: { ontologies: OntologyItem[] }) => {
  const t = useTranslations('page_ontologies');
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [search, setSearch] = useState('');

  const filtered = ontologies.filter((o) =>
    (o.title || '').toLowerCase().includes(search.toLowerCase())
  );

  const handleImport = async (file: File) => {
    try {
      const fd = new FormData();
      fd.append('file', file);
      const basePath = process.env.NEXT_PUBLIC_BASE_PATH || '';
      await axios.post(`${basePath}/api/v1/ontologies`, fd);
      toast.success(t('saved_success'));
      router.refresh();
    } catch {
      toast.error('Import failed');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      const basePath = process.env.NEXT_PUBLIC_BASE_PATH || '';
      await axios.delete(`${basePath}/api/v1/ontologies/${id}`);
      toast.success(t('delete_success'));
      router.refresh();
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <Input
          placeholder={t('search')}
          value={search}
          onChange={(e) => setSearch(e.currentTarget.value)}
          className="max-w-xs"
        />
        <div className="flex items-center gap-2">
          <input
            ref={fileRef}
            type="file"
            accept=".owl,.rdf,.xml"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleImport(f);
              e.target.value = '';
            }}
          />
          <Button variant="outline" onClick={() => fileRef.current?.click()}>
            <FileUp />
            {t('import_ontology')}
          </Button>
          <Button asChild className="cursor-pointer">
            <Link href="/workspace/ontologies/new">
              <Plus />
              {t('add_ontology')}
            </Link>
          </Button>
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="bg-accent/50 py-40 text-center text-muted-foreground">
          {t('no_ontologies_found')}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filtered.map((o) => (
            <Card key={o.id} className="gap-0 overflow-hidden py-0">
              <CardHeader className="flex flex-row items-center justify-between gap-2 px-4 py-3">
                <div className="flex items-center gap-2 min-w-0">
                  <Boxes className="h-4 w-4 text-muted-foreground shrink-0" />
                  <CardTitle className="truncate text-base">{o.title}</CardTitle>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 text-muted-foreground hover:text-destructive"
                  onClick={() => handleDelete(o.id)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </CardHeader>
              <CardDescription className="px-4 pb-3 text-xs text-muted-foreground">
                {o.preview
                  ? `${o.preview.classes_count ?? 0} classes / ${o.preview.object_properties_count ?? 0} relations / ${o.preview.data_properties_count ?? 0} props`
                  : '—'}
              </CardDescription>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};
