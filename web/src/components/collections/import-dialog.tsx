'use client';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Progress } from '@/components/ui/progress';
import { AlertCircle, Check, FileArchive, LoaderCircle, Upload } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useCallback, useRef, useState } from 'react';
import { toast } from 'sonner';

// endOfLine placeholder for clean diff

type ImportStep = 'select' | 'uploading' | 'processing' | 'incompatible' | 'completed' | 'failed';

interface ImportStatus {
  task_id?: string;
  status: string;
  progress?: number;
  message?: string;
  error_message?: string;
  collection_id?: string;
  collection_title?: string;
}

export const CollectionImport = () => {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<ImportStep>('select');
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<ImportStatus | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [, setUploading] = useState(false);
  const router = useRouter();
  const t = useTranslations('page_collections');

  const stopPolling = useCallback(() => {
    if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; }
  }, []);

  const startPolling = useCallback((taskId: string) => {
    stopPolling();
    pollingRef.current = setInterval(async () => {
      try {
        const resp = await fetch(`/api/v1/import-tasks/${taskId}`);
        if (!resp.ok) return;
        const data = await resp.json() as ImportStatus;
        setStatus(data);
        if (data.status === 'COMPLETED') { stopPolling(); setStep('completed'); }
        if (data.status === 'FAILED' || data.status === 'CANCELLED') { stopPolling(); setStep('failed'); }
        if (data.status === 'INCOMPATIBLE') { stopPolling(); setStep('incompatible'); }
      } catch { /* ignore */ }
    }, 2000);
  }, [stopPolling]);

  const handleOpen = useCallback(() => {
    setStep('select'); setFile(null); setStatus(null); setOpen(true);
  }, []);

  const handleClose = useCallback(() => {
    if (step === 'uploading' || step === 'processing') return;
    stopPolling(); setOpen(false);
  }, [step, stopPolling]);

  const [embeddingInfo, setEmbeddingInfo] = useState('');

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!f.name.endsWith('.zip')) {
      toast.error(t('import_invalid_file'));
      return;
    }
    setFile(f);
    setEmbeddingInfo('');
    // Try to read manifest.json from ZIP to show embedding info
    f.arrayBuffer().then((buf) => {
      try {
        // Minimal ZIP reader: find manifest.json
        const view = new DataView(buf);
        const decoder = new TextDecoder();
        let pos = 0;
        while (pos < buf.byteLength - 30) {
          const sig = view.getUint32(pos, true);
          if (sig !== 0x04034b50) { pos++; continue; }
          const nameLen = view.getUint16(pos + 26, true);
          const extraLen = view.getUint16(pos + 28, true);
          const compSize = view.getUint32(pos + 18, true);
          const name = decoder.decode(new Uint8Array(buf, pos + 30, nameLen));
          const dataStart = pos + 30 + nameLen + extraLen;
          if (name === 'manifest.json' && compSize < 100000) {
            const manifest = JSON.parse(decoder.decode(new Uint8Array(buf, dataStart, compSize)));
            if (manifest.embedding_model) {
              setEmbeddingInfo(`${manifest.embedding_model}${manifest.embedding_provider ? ` (${manifest.embedding_provider})` : ''} | dim=${manifest.embedding_dim || '?'}`);
            }
            break;
          }
          pos = dataStart + compSize;
        }
      } catch { /* ignore parse errors */ }
    }).catch(() => {});
  }, [t]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (f && f.name.endsWith('.zip')) {
      setFile(f);
    } else {
      toast.error(t('import_invalid_file'));
    }
  }, [t]);

  const handleImport = useCallback(async () => {
    if (!file) return;
    setUploading(true);
    setStep('uploading');
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('collection_title', file.name.replace('.zip', ''));
      const resp = await fetch('/api/v1/collections/import', {
        method: 'POST',
        body: formData,
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error((err as any).detail || `HTTP ${resp.status}`);
      }
      const data = await resp.json() as ImportStatus;
      setStatus(data);
      setStep('processing');
      startPolling(data.task_id!);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t('import_failed');
      toast.error(msg);
      setStep('failed');
    } finally {
      setUploading(false);
    }
  }, [file, startPolling, t]);

  const handleContinue = useCallback(async (action: 'reindex' | 'cancel') => {
    if (!status?.task_id) return;
    if (action === 'cancel') {
      setOpen(false);
      return;
    }
    setStep('processing');
    try {
      await fetch(`/api/v1/import-tasks/${status.task_id}/continue`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      });
      startPolling(status.task_id);
    } catch {
      toast.error(t('import_failed'));
      setStep('failed');
    }
  }, [status, startPolling, t]);

  const handleGoToCollection = useCallback(() => {
    if (status?.collection_id) {
      router.push(`/workspace/collections/${status.collection_id}`);
    }
    setOpen(false);
  }, [status, router]);

  return (
    <>
      <Button onClick={handleOpen} variant="outline">
        <Upload className="mr-2 h-4 w-4" />
        {t('import_knowledge_base')}
      </Button>

      <Dialog open={open} onOpenChange={handleClose}>
        <DialogContent
          onInteractOutside={(e) => { if (step === 'uploading' || step === 'processing') e.preventDefault(); }}
          onEscapeKeyDown={(e) => { if (step === 'uploading' || step === 'processing') e.preventDefault(); }}
          className="max-w-md"
        >
          {/* ── Step: File selection ── */}
          {step === 'select' && (
            <>
              <DialogHeader>
                <DialogTitle>{t('import_title')}</DialogTitle>
                <DialogDescription>{t('import_description')}</DialogDescription>
              </DialogHeader>

              <div
                className={[
                  'border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors',
                  file ? 'border-primary bg-primary/5' : 'border-muted-foreground/25 hover:border-primary/50',
                ].join(' ')}
                onDrop={handleDrop}
                onDragOver={(e) => e.preventDefault()}
                onClick={() => document.getElementById('import-file-input')?.click()}
              >
                {file ? (
                  <div className="flex flex-col items-center gap-2">
                    <FileArchive className="h-10 w-10 text-primary" />
                    <p className="font-medium">{file.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {(file.size / 1024 / 1024).toFixed(1)} MB
                    </p>
                    {embeddingInfo && (
                      <p className="text-xs bg-blue-50 text-blue-700 rounded px-2 py-1">
                        {t('import_embedding_model')}: {embeddingInfo}
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-2 text-muted-foreground">
                    <Upload className="h-10 w-10" />
                    <p>{t('import_drop_hint')}</p>
                    <p className="text-xs">{t('import_format_hint')}</p>
                  </div>
                )}
                <input
                  id="import-file-input"
                  type="file"
                  accept=".zip"
                  className="hidden"
                  onChange={handleFileChange}
                />
              </div>

              <div className="flex items-start gap-2 text-xs text-amber-600 bg-amber-50 rounded-md p-3">
                <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                <span>{t('import_warning')}</span>
              </div>

              <DialogFooter>
                <Button variant="outline" onClick={handleClose}>{t('cancel')}</Button>
                <Button disabled={!file} onClick={handleImport}>
                  {t('import_start')}
                </Button>
              </DialogFooter>
            </>
          )}

          {/* ── Step: Uploading ── */}
          {step === 'uploading' && (
            <>
              <DialogHeader>
                <DialogTitle>{t('import_uploading_title')}</DialogTitle>
                <DialogDescription>{t('import_uploading_desc')}</DialogDescription>
              </DialogHeader>
              <div className="flex justify-center py-4">
                <LoaderCircle className="h-8 w-8 animate-spin text-primary" />
              </div>
            </>
          )}

          {/* ── Step: Processing ── */}
          {step === 'processing' && (
            <>
              <DialogHeader>
                <DialogTitle>{t('import_processing_title')}</DialogTitle>
                <DialogDescription>{status?.message ?? '...'}</DialogDescription>
              </DialogHeader>
              <div className="py-4">
                <Progress value={status?.progress ?? 0} className="w-full" />
                <p className="text-muted-foreground mt-2 text-sm text-center">
                  {status?.progress ?? 0}%
                </p>
              </div>
            </>
          )}

          {/* ── Step: Completed ── */}
          {step === 'completed' && (
            <>
              <DialogHeader>
                <DialogTitle>
                  <span className="flex items-center gap-2">
                    <Check className="h-5 w-5 text-green-600" />
                    {t('import_completed_title')}
                  </span>
                </DialogTitle>
                <DialogDescription>
                  {t('import_completed_desc').replace('{name}', status?.collection_title || '—')}
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={handleClose}>{t('cancel')}</Button>
                <Button onClick={handleGoToCollection}>
                  {t('import_go_to_collection')}
                </Button>
              </DialogFooter>
            </>
          )}

          {/* ── Step: Incompatible ── */}
          {step === 'incompatible' && (
            <>
              <DialogHeader>
                <DialogTitle>
                  <span className="flex items-center gap-2">
                    <AlertCircle className="h-5 w-5 text-amber-600" />
                    {t('import_incompatible_title')}
                  </span>
                </DialogTitle>
                <DialogDescription>
                  {status?.message || t('import_incompatible_desc')}
                </DialogDescription>
              </DialogHeader>
              <div className="bg-amber-50 rounded-md p-3 text-sm text-amber-800">
                {t('import_incompatible_hint')}
              </div>
              <DialogFooter className="flex-col sm:flex-row gap-2">
                <Button variant="outline" onClick={() => handleContinue('cancel')}>
                  {t('cancel')}
                </Button>
                <Button onClick={() => handleContinue('reindex')}>
                  {t('import_reindex_action')}
                </Button>
              </DialogFooter>
            </>
          )}

          {/* ── Step: Failed ── */}
          {step === 'failed' && (
            <>
              <DialogHeader>
                <DialogTitle>
                  <span className="flex items-center gap-2">
                    <AlertCircle className="h-5 w-5 text-destructive" />
                    {t('import_failed_title')}
                  </span>
                </DialogTitle>
                <DialogDescription>
                  {status?.error_message || t('import_failed')}
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={handleClose}>{t('cancel')}</Button>
                <Button onClick={() => { setStep('select'); setFile(null); setStatus(null); }}>
                  {t('import_retry')}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
};
