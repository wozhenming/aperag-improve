'use client';

import { Document, RebuildIndexesRequestIndexTypesEnum } from '@/api';
import { useCollectionContext } from '@/components/providers/collection-provider';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { apiClient } from '@/lib/api/client';
import { Slot } from '@radix-ui/react-slot';
import { FolderSync } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { toast } from 'sonner';

export const DocumentReBuildMulti = ({
  documents,
  children,
}: {
  documents: Document[];
  children?: React.ReactNode;
}) => {
  const { collection } = useCollectionContext();
  const page_documents = useTranslations('page_documents');
  const common_action = useTranslations('common.action');
  const [visible, setVisible] = useState(false);
  const [selectedDocs, setSelectedDocs] = useState<Set<string>>(new Set());
  const [selectedTypes, setSelectedTypes] = useState<string[]>(['GRAPH']);
  const [rebuilding, setRebuilding] = useState(false);
  const router = useRouter();
  const allTypes = Object.keys(RebuildIndexesRequestIndexTypesEnum);

  const toggleDoc = (id: string) => {
    const next = new Set(selectedDocs);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelectedDocs(next);
  };
  const toggleAll = () => {
    if (selectedDocs.size === documents.length) {
      setSelectedDocs(new Set());
    } else {
      setSelectedDocs(new Set(documents.map((d) => d.id || '').filter(Boolean)));
    }
  };

  const handleRebuild = async () => {
    if (!collection.id || selectedDocs.size === 0 || selectedTypes.length === 0) return;
    setRebuilding(true);
    let ok = 0;
    let fail = 0;
    for (const docId of selectedDocs) {
      try {
        await apiClient.defaultApi.collectionsCollectionIdDocumentsDocumentIdRebuildIndexesPost({
          collectionId: collection.id || '',
          documentId: docId,
          rebuildIndexesRequest: { index_types: selectedTypes as any },
        });
        ok++;
      } catch { fail++; }
    }
    setRebuilding(false);
    toast.success(  page_documents('index_rebuild_multi_done', {
    ok: String(ok),
    fail: String(fail)
  }));
    setVisible(false);
    setTimeout(router.refresh, 500);
  };

  return (
    <Dialog open={visible} onOpenChange={setVisible}>
      <DialogTrigger asChild>
        <Slot onClick={(e) => { setVisible(true); e.preventDefault(); }}>
          {children}
        </Slot>
      </DialogTrigger>
      <DialogContent className="sm:max-w-4xl max-w-[calc(100%-2rem)]">
        <DialogHeader>
          <DialogTitle>{page_documents('index_rebuild_multi_title')}</DialogTitle>
          <DialogDescription>{page_documents('index_rebuild_multi_desc')}</DialogDescription>
        </DialogHeader>

        {/* Index type selection */}
        <div>
          <Label className="text-sm font-medium">{page_documents('index_rebuild_select_types')}</Label>
          <div className="flex gap-4 mt-1">
            {allTypes.map((t) => (
              <label key={t} className="flex items-center gap-1.5 cursor-pointer text-sm">
                <Checkbox checked={selectedTypes.includes(t)}
                  onCheckedChange={(c) => setSelectedTypes(c ? [...selectedTypes, t] : selectedTypes.filter((x) => x !== t))} />
                {t}
              </label>
            ))}
          </div>
        </div>

        {/* File selection */}
        <div>
          <Label className="text-sm font-medium flex items-center justify-between">
            {page_documents('index_rebuild_select_files')} ({selectedDocs.size}/{documents.length})
            <button className="text-xs underline" onClick={toggleAll}>
              {selectedDocs.size === documents.length
                ? page_documents('index_rebuild_deselect_all')
                : page_documents('index_rebuild_select_all')}
            </button>
          </Label>
          <div className="max-h-48 overflow-auto border rounded-md mt-1">
            {documents.length === 0 && (
              <p className="text-muted-foreground text-sm p-3">{page_documents('no_documents_found')}</p>
            )}
            {documents.map((doc) => (
              <label key={doc.id} className="flex items-center gap-2 px-3 py-1.5 hover:bg-accent cursor-pointer text-sm border-b last:border-0 overflow-hidden">
                <Checkbox checked={selectedDocs.has(doc.id || '')}
                  onCheckedChange={() => toggleDoc(doc.id || '')}
                  className="shrink-0" />
                <span className="truncate min-w-0 flex-1">{doc.name}</span>
                <span className="text-muted-foreground text-xs shrink-0">{doc.id}</span>
              </label>
            ))}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setVisible(false)}>{common_action('cancel')}</Button>
          <Button onClick={handleRebuild} disabled={selectedDocs.size === 0 || selectedTypes.length === 0 || rebuilding}>
            {rebuilding ? '...' : `${page_documents('index_rebuild')} (${selectedDocs.size})`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
