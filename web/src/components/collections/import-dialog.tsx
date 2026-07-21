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

type ImportStep = 'select' | 'uploading' | 'processing' | 'completed' | 'failed';

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
        if (data.status === 'FAILED') { stopPolling(); setStep('failed'); }
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

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f && f.name.endsWith('.zip')) {
      setFile(f);
    } else {
      toast.error(t('import_invalid_file'));
    }
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
