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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { AlertCircle, Check, FileArchive, LoaderCircle, ShieldAlert, Upload } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import _ from 'lodash';

type ImportStep = 'select' | 'confirm' | 'uploading' | 'processing' | 'incompatible' | 'completed' | 'failed';

interface ImportStatus {
  task_id?: string;
  status: string;
  progress?: number;
  message?: string;
  error_message?: string;
  collection_id?: string;
  collection_title?: string;
}

interface ManifestInfo {
  export_type: string;
  embedding_model?: string;
  embedding_provider?: string;
  embedding_dim?: number;
  collection_title: string;
  document_count: number;
}

interface EmbeddingOption {
  label: string;
  name: string;
  model: string;
  provider: string;
  custom_llm_provider?: string;
}

/** Parse ZIP's manifest.json to extract export info, returns null on failure. */
async function parseManifest(file: File): Promise<ManifestInfo | null> {
  try {
    const buf = await file.arrayBuffer();
    const view = new DataView(buf);
    const decoder = new TextDecoder();
    const u8 = new Uint8Array(buf);

    // Find end-of-central-directory record (EOCD) at end of file
    // The EOCD signature is 0x06054b50
    let eocdOffset = -1;
    const maxSearch = Math.min(65557, buf.byteLength); // EOCD max size (65535 + 22)
    for (let i = buf.byteLength - 22; i >= buf.byteLength - maxSearch && i >= 0; i--) {
      if (view.getUint32(i, true) === 0x06054b50) {
        eocdOffset = i;
        break;
      }
    }
    if (eocdOffset < 0) return null; // No valid ZIP

    const cdOffset = view.getUint32(eocdOffset + 16, true); // central directory offset
    const cdSize = view.getUint32(eocdOffset + 12, true);

    // Scan central directory entries
    let pos = cdOffset;
    const cdEnd = cdOffset + cdSize;
    while (pos + 46 <= cdEnd) {
      const sig = view.getUint32(pos, true);
      if (sig !== 0x02014b50) break;
      const nameLen = view.getUint16(pos + 28, true);
      const extraLen = view.getUint16(pos + 30, true);
      const commentLen = view.getUint16(pos + 32, true);
      const localOffset = view.getUint32(pos + 42, true);
      const name = decoder.decode(u8.slice(pos + 46, pos + 46 + nameLen));

      if (name === 'manifest.json') {
        // Read from local file header
        const lhNameLen = view.getUint16(localOffset + 26, true);
        const lhExtraLen = view.getUint16(localOffset + 28, true);
        const compSize = view.getUint32(localOffset + 18, true);
        const compMethod = view.getUint16(localOffset + 8, true);
        const dataStart = localOffset + 30 + lhNameLen + lhExtraLen;

        if (compSize > 100000) return null; // Too large

        let jsonBytes: Uint8Array;
        if (compMethod === 0) {
          // Stored (uncompressed)
          jsonBytes = u8.slice(dataStart, dataStart + compSize);
        } else if (compMethod === 8) {
          // Deflate compressed — use browser API
          const compressed = u8.slice(dataStart, dataStart + compSize);
          const ds = new DecompressionStream('deflate-raw');
          const writer = ds.writable.getWriter();
          writer.write(compressed);
          writer.close();
          const decompressed = await new Response(ds.readable).arrayBuffer();
          jsonBytes = new Uint8Array(decompressed);
        } else {
          return null; // Unknown compression method
        }

        const manifest = JSON.parse(decoder.decode(jsonBytes));
        return {
          export_type: manifest.export_type || 'basic',
          embedding_model: manifest.embedding_model,
          embedding_provider: manifest.embedding_provider,
          embedding_dim: manifest.embedding_dim,
          collection_title: manifest.collection?.title || '',
          document_count: (manifest.documents || []).length,
        };
      }
      pos += 46 + nameLen + extraLen + commentLen;
    }
  } catch { /* ignore */ }
  return null;
}

export const CollectionImport = () => {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<ImportStep>('select');
  const [file, setFile] = useState<File | null>(null);
  const [manifest, setManifest] = useState<ManifestInfo | null>(null);
  const [status, setStatus] = useState<ImportStatus | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [, setUploading] = useState(false);
  const [embeddingOptions, setEmbeddingOptions] = useState<EmbeddingOption[]>([]);
  const [completionOptions, setCompletionOptions] = useState<EmbeddingOption[]>([]);
  const [selectedModel, setSelectedModel] = useState('');
  const [selectedCompletionModel, setSelectedCompletionModel] = useState('');
  const [loadingModels, setLoadingModels] = useState(false);
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
        const data: ImportStatus = await resp.json();
        setStatus(data);
        if (data.status === 'COMPLETED') { stopPolling(); setStep('completed'); }
        if (data.status === 'FAILED' || data.status === 'CANCELLED') { stopPolling(); setStep('failed'); }
        if (data.status === 'INCOMPATIBLE') { stopPolling(); setStep('incompatible'); }
      } catch { /* ignore */ }
    }, 2000);
  }, [stopPolling]);

  const handleOpen = useCallback(() => {
    setStep('select'); setFile(null); setManifest(null); setStatus(null); setSelectedModel(''); setOpen(true);
  }, []);

  const handleClose = useCallback(() => {
    if (step === 'uploading' || step === 'processing') return;
    stopPolling(); setOpen(false);
  }, [step, stopPolling]);

  /* Load available embedding models for the dropdown */
  const loadModels = useCallback(async () => {
    if (!_.isEmpty(embeddingOptions)) return;
    setLoadingModels(true);
    try {
      const res = await apiClient.defaultApi.availableModelsPost({
        tagFilterRequest: { tag_filters: [{ operation: 'AND', tags: ['enable_for_collection'] }] },
      });
      const items = res.data.items || [];
      const opts: EmbeddingOption[] = [];
      items.forEach((p: any) => {
        (p.embedding || []).forEach((m: any) => {
          opts.push({
            label: `${p.label} / ${m.label || m.model}`,
            name: p.name,
            model: m.model || m.name,
            provider: p.name,
            custom_llm_provider: m.custom_llm_provider || '',
          });
        });
      });
      setEmbeddingOptions(opts);
      const def = opts.find((o: any) => o.model?.toLowerCase()?.includes('default'));
      if (!def && opts.length > 0) setSelectedModel(opts[0].model);
      else if (def) setSelectedModel(def.model);

      // Also load completion models
      const cOpts: EmbeddingOption[] = [];
      items.forEach((p: any) => {
        (p.completion || []).forEach((m: any) => {
          cOpts.push({
            label: `${p.label} / ${m.label || m.model}`,
            name: p.name,
            model: m.model || m.name,
            provider: p.name,
            custom_llm_provider: m.custom_llm_provider || '',
          });
        });
      });
      setCompletionOptions(cOpts);
      const cDef = cOpts.find((o: any) => o.model?.toLowerCase()?.includes('default'));
      if (!cDef && cOpts.length > 0) setSelectedCompletionModel(cOpts[0].model);
      else if (cDef) setSelectedCompletionModel(cDef.model);
    } catch { /* ignore */ }
    finally { setLoadingModels(false); }
  }, [embeddingOptions]);

  const handleFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!f.name.endsWith('.zip')) { toast.error(t('import_invalid_file')); return; }
    setFile(f);
    const m = await parseManifest(f);
    setManifest(m);
    await loadModels();
  }, [t, loadModels]);

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (!f) return;
    if (!f.name.endsWith('.zip')) { toast.error(t('import_invalid_file')); return; }
    setFile(f);
    const m = await parseManifest(f);
    setManifest(m);
    await loadModels();
  }, [t, loadModels]);

  /* Proceed to confirmation step */
  const goToConfirm = useCallback(() => { setStep('confirm'); }, []);

  /* Checks if export model matches selected target model */
  const modelMatch = manifest?.embedding_model && selectedModel
    ? manifest.embedding_model === selectedModel ||
      embeddingOptions.find(e => e.model === selectedModel)?.label?.includes(manifest.embedding_model || '')
    : undefined;

  /* Whether this is a full export */
  const isFull = manifest?.export_type === 'full';

  const handleImport = useCallback(async () => {
    if (!file) return;
    setUploading(true);
    setStep('uploading');
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('collection_title', manifest?.collection_title || file.name.replace('.zip', ''));
      if (selectedModel) formData.append('target_embedding_model', selectedModel);
      if (selectedCompletionModel) formData.append('target_completion_model', selectedCompletionModel);
      if (manifest?.export_type) formData.append('export_type', manifest.export_type);

      // Send provider names for model config
      const embOpt = embeddingOptions.find(o => o.model === selectedModel);
      const compOpt = completionOptions.find(o => o.model === selectedCompletionModel);
      if (embOpt?.provider) formData.append('target_embedding_provider', embOpt.provider);
      if (compOpt?.provider) formData.append('target_completion_provider', compOpt.provider);
      if (embOpt?.custom_llm_provider) formData.append('target_embedding_custom_provider', embOpt.custom_llm_provider);
      if (compOpt?.custom_llm_provider) formData.append('target_completion_custom_provider', compOpt.custom_llm_provider);

      const resp = await fetch('/api/v1/collections/import', { method: 'POST', body: formData });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error((err as any).detail || `HTTP ${resp.status}`);
      }
      const data = await resp.json() as ImportStatus;
      setStatus(data);
      setStep('processing');
      startPolling(data.task_id!);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : t('import_failed'));
      setStep('failed');
    } finally {
      setUploading(false);
    }
  }, [file, manifest, selectedModel, startPolling, t]);

  const handleContinue = useCallback(async (action: 'reindex' | 'cancel' | 'force') => {
    if (!status?.task_id) return;
    if (action === 'cancel') { setOpen(false); return; }
    setStep('processing');
    try {
      await fetch(`/api/v1/import-tasks/${status.task_id}/continue`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      });
      startPolling(status.task_id);
    } catch {
      toast.error(t('import_failed')); setStep('failed');
    }
  }, [status, startPolling, t]);

  const handleGoToCollection = useCallback(() => {
    if (status?.collection_id) router.push(`/workspace/collections/${status.collection_id}`);
    setOpen(false);
  }, [status, router]);

  useEffect(() => () => stopPolling(), [stopPolling]);

  return (
    <>
      <Button onClick={handleOpen} variant="outline">
        <Upload className="mr-2 h-4 w-4" />{t('import_knowledge_base')}
      </Button>

      <Dialog open={open} onOpenChange={handleClose}>
        <DialogContent
          onInteractOutside={(e) => { if (step === 'uploading' || step === 'processing') e.preventDefault(); }}
          onEscapeKeyDown={(e) => { if (step === 'uploading' || step === 'processing') e.preventDefault(); }}
          className="max-w-md"
        >
          {/* ── Step: File Selection ── */}
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
                    <p className="text-xs text-muted-foreground">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
                    {manifest && (
                      <div className="text-xs text-left mt-2 space-y-0.5 bg-muted rounded p-2 w-full max-w-xs">
                        <p>{t('import_export_type')}: <strong>{isFull ? t('export_full_title') : t('export_basic_title')}</strong></p>
                        <p>{t('import_doc_count')}: {manifest.document_count}</p>
                        {manifest.embedding_model && (
                          <p>{t('import_embedding_model')}: {manifest.embedding_model}
                            {manifest.embedding_provider ? ` (${manifest.embedding_provider})` : ''}
                            {manifest.embedding_dim ? ` dim=${manifest.embedding_dim}` : ''}
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-2 text-muted-foreground">
                    <Upload className="h-10 w-10" />
                    <p>{t('import_drop_hint')}</p>
                    <p className="text-xs">{t('import_format_hint')}</p>
                  </div>
                )}
                <input id="import-file-input" type="file" accept=".zip" className="hidden" onChange={handleFileChange} />
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={handleClose}>{t('cancel')}</Button>
                <Button disabled={!file || !manifest} onClick={goToConfirm}>
                  {t('import_continue')}
                </Button>
              </DialogFooter>
            </>
          )}

          {/* ── Step: Confirmation ── */}
          {step === 'confirm' && (
            <>
              <DialogHeader>
                <DialogTitle>{t('import_confirm_title')}</DialogTitle>
                <DialogDescription>{t('import_confirm_desc')}</DialogDescription>
              </DialogHeader>

              {/* Export info summary */}
              <div className="bg-muted rounded-md p-3 text-sm space-y-1">
                <p><strong>{t('import_export_type')}:</strong> {isFull ? t('export_full_title') : t('export_basic_title')}</p>
                <p><strong>{t('import_doc_count')}:</strong> {manifest?.document_count}</p>
                {manifest?.embedding_model && (
                  <p><strong>{t('import_export_model')}:</strong> {manifest.embedding_model}
                    {manifest.embedding_provider ? ` (${manifest.embedding_provider})` : ''}</p>
                )}
              </div>

              {/* Target embedding model selection */}
              <div className="flex flex-col gap-2">
                <Label>{t('import_target_model')}</Label>
                {loadingModels ? (
                  <div className="flex items-center gap-2 text-muted-foreground text-sm">
                    <LoaderCircle className="h-4 w-4 animate-spin" /> {t('import_loading_models')}
                  </div>
                ) : (
                  <Select value={selectedModel} onValueChange={setSelectedModel}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder={t('import_select_model')} />
                    </SelectTrigger>
                    <SelectContent>
                      {embeddingOptions.map((opt) => (
                        <SelectItem key={`emb-${opt.provider}/${opt.model}`} value={opt.model}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>

              {/* Target completion model selection */}
              <div className="flex flex-col gap-2">
                <Label>{t('import_target_completion_model')}</Label>
                {loadingModels ? (
                  <div className="flex items-center gap-2 text-muted-foreground text-sm">
                    <LoaderCircle className="h-4 w-4 animate-spin" /> {t('import_loading_models')}
                  </div>
                ) : (
                  <Select value={selectedCompletionModel} onValueChange={setSelectedCompletionModel}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder={t('import_select_completion_model')} />
                    </SelectTrigger>
                    <SelectContent>
                      {completionOptions.map((opt) => (
                        <SelectItem key={`comp-${opt.provider}/${opt.model}`} value={opt.model}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>

              {/* Match/Mismatch indicator — only for full export */}
              {isFull && manifest?.embedding_model && selectedModel && (
                <div className={[
                  'flex items-start gap-2 rounded-md p-3 text-sm',
                  modelMatch ? 'bg-green-50 text-green-800' : 'bg-amber-50 text-amber-800',
                ].join(' ')}>
                  {modelMatch ? (
                    <Check className="h-4 w-4 mt-0.5 shrink-0" />
                  ) : (
                    <ShieldAlert className="h-4 w-4 mt-0.5 shrink-0" />
                  )}
                  <span>
                    {modelMatch
                      ? t('import_model_match')
                      : t('import_model_mismatch')}
                  </span>
                </div>
              )}

              {/* Risk warning for full export with mismatched model */}
              {isFull && manifest?.embedding_model && selectedModel && !modelMatch && (
                <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-md p-3 text-sm text-red-800">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  <span>{t('import_force_warning')}</span>
                </div>
              )}

              <DialogFooter>
                <Button variant="outline" onClick={() => setStep('select')}>{t('back')}</Button>
                <Button onClick={handleImport} disabled={!selectedModel}>
                  {t('import_start')}
                </Button>
              </DialogFooter>
            </>
          )}

          {/* Uploading / Processing / Incompatible / Completed / Failed */}
          {step === 'uploading' && (
            <>
              <DialogHeader>
                <DialogTitle>{t('import_uploading_title')}</DialogTitle>
                <DialogDescription>{t('import_uploading_desc')}</DialogDescription>
              </DialogHeader>
              <div className="flex justify-center py-4"><LoaderCircle className="h-8 w-8 animate-spin text-primary" /></div>
            </>
          )}
          {step === 'processing' && (
            <>
              <DialogHeader>
                <DialogTitle>{t('import_processing_title')}</DialogTitle>
                <DialogDescription>{status?.message ?? '...'}</DialogDescription>
              </DialogHeader>
              <div className="py-4">
                <Progress value={status?.progress ?? 0} className="w-full" />
                <p className="text-muted-foreground mt-2 text-sm text-center">{status?.progress ?? 0}%</p>
              </div>
            </>
          )}
          {step === 'incompatible' && (
            <>
              <DialogHeader>
                <DialogTitle>
                  <span className="flex items-center gap-2"><AlertCircle className="h-5 w-5 text-amber-600" />{t('import_incompatible_title')}</span>
                </DialogTitle>
                <DialogDescription>{status?.message || t('import_incompatible_desc')}</DialogDescription>
              </DialogHeader>
              <div className="bg-amber-50 rounded-md p-3 text-sm text-amber-800">{t('import_incompatible_hint')}</div>
              <DialogFooter className="flex-col gap-2">
                <div className="flex flex-row gap-2 justify-end">
                  <Button variant="outline" onClick={() => handleContinue('cancel')}>{t('cancel')}</Button>
                  <Button variant="destructive" onClick={() => handleContinue('force')}>{t('import_force_action')}</Button>
                  <Button onClick={() => handleContinue('reindex')}>{t('import_reindex_action')}</Button>
                </div>
                <p className="text-xs text-muted-foreground text-right">
                  {t('import_force_warning_short')}
                </p>
              </DialogFooter>
            </>
          )}
          {step === 'completed' && (
            <>
              <DialogHeader>
                <DialogTitle><span className="flex items-center gap-2"><Check className="h-5 w-5 text-green-600" />{t('import_completed_title')}</span></DialogTitle>
                <DialogDescription>{t('import_completed_desc').replace('{name}', status?.collection_title || '—')}</DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={handleClose}>{t('cancel')}</Button>
                <Button onClick={handleGoToCollection}>{t('import_go_to_collection')}</Button>
              </DialogFooter>
            </>
          )}
          {step === 'failed' && (
            <>
              <DialogHeader>
                <DialogTitle><span className="flex items-center gap-2"><AlertCircle className="h-5 w-5 text-destructive" />{t('import_failed_title')}</span></DialogTitle>
                <DialogDescription>{status?.error_message || t('import_failed')}</DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={handleClose}>{t('cancel')}</Button>
                <Button onClick={() => { setStep('select'); setFile(null); setManifest(null); setStatus(null); }}>{t('import_retry')}</Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
};
