'use client';

import { ExportTaskResponse } from '@/api';
import { Button } from '@/components/ui/button';
import { Card, CardDescription, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Progress } from '@/components/ui/progress';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { apiClient } from '@/lib/api/client';
import { cn } from '@/lib/utils';
import { Slot } from '@radix-ui/react-slot';
import { AlertCircle, Box, FileArchive } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';

type ExportStep = 'choose' | 'confirm' | 'processing' | 'completed' | 'failed';
type ExportType = 'basic' | 'full';

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

export const CollectionExport = ({
  collectionId,
  children,
}: {
  collectionId: string;
  children?: React.ReactNode;
}) => {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<ExportStep>('choose');
  const [exportType, setExportType] = useState<ExportType>('basic');
  const [taskStatus, setTaskStatus] = useState<ExportTaskResponse | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const t = useTranslations('page_collections');

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const startPolling = useCallback(
    (taskId: string) => {
      stopPolling();
      pollingRef.current = setInterval(async () => {
        try {
          const res = await apiClient.defaultApi.getExportTask({ taskId });
          const data = res.data;
          setTaskStatus(data);
          if (data.status === 'COMPLETED') { stopPolling(); setStep('completed'); }
          if (data.status === 'FAILED') { stopPolling(); setStep('failed'); }
        } catch { /* polling errors are non-fatal */ }
      }, 2000);
    },
    [stopPolling],
  );

  useEffect(() => () => stopPolling(), [stopPolling]);

  const handleOpen = useCallback(() => {
    setStep('choose');
    setExportType('basic');
    setTaskStatus(null);
    setOpen(true);
  }, []);

  const handleClose = useCallback(() => {
    if (step === 'processing') return;
    stopPolling();
    setOpen(false);
  }, [step, stopPolling]);

  const handleStartExport = useCallback(async () => {
    if (step === 'processing') return;
    try {
      const res = await apiClient.defaultApi.createExportTask({
        collectionId,
        createExportRequest: { export_type: exportType },
      });
      const data = res.data;
      setTaskStatus(data);
      setStep('processing');
      startPolling(data.export_task_id);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 429) {
        toast.error(t('export_too_many_tasks'));
      } else {
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        toast.error(detail || t('export_failed_description'));
      }
      setOpen(false);
    }
  }, [collectionId, exportType, step, startPolling, t]);

  const handleDownload = useCallback(() => {
    if (!taskStatus?.download_url) return;
    const a = document.createElement('a');
    a.href = taskStatus.download_url;
    a.click();
  }, [taskStatus]);

  return (
    <>
      <Slot onClick={(e) => { handleOpen(); e.preventDefault(); }}>
        {children}
      </Slot>

      <Dialog open={open} onOpenChange={handleClose}>
        <DialogContent
          onInteractOutside={(e) => { if (step === 'processing') e.preventDefault(); }}
          onEscapeKeyDown={(e) => { if (step === 'processing') e.preventDefault(); }}
          className={step === 'choose' ? 'max-w-lg' : undefined}
        >
          {/* ── Step: Choose export type ── */}
          {step === 'choose' && (
            <>
              <DialogHeader>
                <DialogTitle>{t('export_title')}</DialogTitle>
                <DialogDescription>{t('export_description')}</DialogDescription>
              </DialogHeader>

              <RadioGroup value={exportType} onValueChange={(v) => setExportType(v as ExportType)}
                className="flex flex-col gap-3">
                <label
                  className={cn(
                    'flex items-start gap-3 rounded-lg border p-4 cursor-pointer transition-colors',
                    exportType === 'basic' ? 'border-primary bg-primary/5' : 'border-border',
                  )}
                >
                  <RadioGroupItem value="basic" className="mt-0.5" />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <FileArchive className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium">{t('export_basic_title')}</span>
                      <span className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded">
                        {t('export_recommended')}
                      </span>
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">
                      {t('export_basic_desc')}
                    </p>
                    <ul className="text-xs text-muted-foreground mt-2 space-y-0.5">
                      <li>✓ {t('export_basic_point1')}</li>
                      <li>✓ {t('export_basic_point2')}</li>
                      <li className="flex items-center gap-1 text-amber-600">
                        <AlertCircle className="h-3 w-3" /> {t('export_basic_warning')}
                      </li>
                    </ul>
                  </div>
                </label>

                <label
                  className={cn(
                    'flex items-start gap-3 rounded-lg border p-4 cursor-pointer transition-colors',
                    exportType === 'full' ? 'border-primary bg-primary/5' : 'border-border',
                  )}
                >
                  <RadioGroupItem value="full" className="mt-0.5" />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <Box className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium">{t('export_full_title')}</span>
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">
                      {t('export_full_desc')}
                    </p>
                    <ul className="text-xs text-muted-foreground mt-2 space-y-0.5">
                      <li>✓ {t('export_full_point1')}</li>
                      <li>✓ {t('export_full_point2')}</li>
                      <li className="flex items-center gap-1 text-amber-600">
                        <AlertCircle className="h-3 w-3" /> {t('export_full_warning1')}
                      </li>
                      <li className="flex items-center gap-1 text-amber-600">
                        <AlertCircle className="h-3 w-3" /> {t('export_full_warning2')}
                      </li>
                    </ul>
                  </div>
                </label>
              </RadioGroup>

              <DialogFooter>
                <Button variant="outline" onClick={handleClose}>{t('cancel')}</Button>
                <Button onClick={() => setStep('confirm')}>
                  {t('export_continue')}
                </Button>
              </DialogFooter>
            </>
          )}

          {/* ── Step: Confirm ── */}
          {step === 'confirm' && (
            <>
              <DialogHeader>
                <DialogTitle>
                  {exportType === 'basic' ? t('export_confirm_title_basic') : t('export_confirm_title_full')}
                </DialogTitle>
                <DialogDescription>
                  {exportType === 'basic' ? t('export_confirm_desc_basic') : t('export_confirm_desc_full')}
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={() => setStep('choose')}>
                  {t('back')}
                </Button>
                <Button onClick={handleStartExport}>{t('export_start')}</Button>
              </DialogFooter>
            </>
          )}

          {/* ── Step: Processing ── */}
          {step === 'processing' && (
            <>
              <DialogHeader>
                <DialogTitle>{t('export_processing_title')}</DialogTitle>
                <DialogDescription>{taskStatus?.message ?? '...'}</DialogDescription>
              </DialogHeader>
              <div className="py-4">
                <Progress value={taskStatus?.progress ?? 0} className="w-full" />
                <p className="text-muted-foreground mt-2 text-sm text-center">
                  {taskStatus?.progress ?? 0}%
                </p>
              </div>
            </>
          )}

          {/* ── Step: Completed ── */}
          {step === 'completed' && (
            <>
              <DialogHeader>
                <DialogTitle>{t('export_completed_title')}</DialogTitle>
                <DialogDescription>
                  {t('export_completed_desc', {
                    size: taskStatus?.file_size ? formatFileSize(taskStatus.file_size) : '—',
                  })}
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={handleClose}>{t('cancel')}</Button>
                <Button onClick={handleDownload}>{t('export_download')}</Button>
              </DialogFooter>
            </>
          )}

          {/* ── Step: Failed ── */}
          {step === 'failed' && (
            <>
              <DialogHeader>
                <DialogTitle>{t('export_failed_title')}</DialogTitle>
                <DialogDescription>
                  {taskStatus?.error_message || t('export_failed_description')}
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={handleClose}>{t('cancel')}</Button>
                <Button onClick={() => setStep('choose')}>{t('export_retry')}</Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
};
