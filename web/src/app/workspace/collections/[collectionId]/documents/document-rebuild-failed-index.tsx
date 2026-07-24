'use client';

import { RebuildIndexesRequestIndexTypesEnum } from '@/api';
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
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { toast } from 'sonner';

export const DocumentReBuildFailedIndex = ({
  children,
}: {
  children: React.ReactNode;
}) => {
  const { collection } = useCollectionContext();
  const common_tips = useTranslations('common.tips');
  const common_action = useTranslations('common.action');
  const page_documents = useTranslations('page_documents');
  const [visible, setVisible] = useState(false);
  const [selectedTypes, setSelectedTypes] = useState<string[]>(['VECTOR', 'FULLTEXT', 'GRAPH']);
  const router = useRouter();

  const allTypes = Object.keys(RebuildIndexesRequestIndexTypesEnum);

  const handleRebuild = async () => {
    if (!collection.id || selectedTypes.length === 0) return;
    try {
      await apiClient.defaultApi.collectionsCollectionIdRebuildFailedIndexesPost({
        collectionId: collection.id,
      });
      toast.success(page_documents('index_rebuild_failed_success'));
      setVisible(false);
      setTimeout(router.refresh, 300);
    } catch { /* ignore */ }
  };

  return (
    <Dialog open={visible} onOpenChange={setVisible}>
      <DialogTrigger asChild>
        <Slot onClick={(e) => { setVisible(true); e.preventDefault(); }}>
          {children}
        </Slot>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{common_tips('confirm')}</DialogTitle>
          <DialogDescription>{page_documents('index_rebuild_failed_confirm')}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-2">
          <Label className="text-sm font-medium">{page_documents('index_rebuild_select_types')}</Label>
          {allTypes.map((t) => (
            <label key={t} className="flex items-center gap-2 cursor-pointer">
              <Checkbox
                checked={selectedTypes.includes(t)}
                onCheckedChange={(checked) => {
                  setSelectedTypes(checked
                    ? [...selectedTypes, t]
                    : selectedTypes.filter((x) => x !== t));
                }}
              />
              <span className="text-sm">{t}</span>
            </label>
          ))}
          <p className="text-xs text-muted-foreground mt-1">{page_documents('index_rebuild_failed_types_hint')}</p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setVisible(false)}>{common_action('cancel')}</Button>
          <Button onClick={handleRebuild} disabled={selectedTypes.length === 0}>{common_action('continue')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
