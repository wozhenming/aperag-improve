'use client';

import axios from 'axios';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

type Issue = {
  code: string;
  level: string;
  fixable: boolean;
  message: string;
  hint?: string;
  count?: number;
};

type RepairResponse = { repaired: string[]; message?: string };

const basePath = process.env.NEXT_PUBLIC_BASE_PATH || '';

export const CollectionRepairDialog = ({
  collectionId,
  open,
  onOpenChange,
}: {
  collectionId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) => {
  const t = useTranslations('page_collections');
  const [scanning, setScanning] = useState(false);
  const [repairing, setRepairing] = useState(false);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [resultMsg, setResultMsg] = useState<string>('');

  const runScan = async () => {
    setScanning(true);
    setResultMsg('');
    try {
      const { data } = await axios.post(
        `${basePath}/api/v1/collections/${collectionId}/repair/scan`,
      );
      setIssues(data.issues || []);
    } catch {
      setIssues([]);
      setResultMsg(t('repair_error'));
    } finally {
      setScanning(false);
    }
  };

  const runRepair = async () => {
    setRepairing(true);
    setResultMsg('');
    try {
      const codes = issues.filter((i) => i.fixable).map((i) => i.code);
      const { data } = await axios.post<RepairResponse>(
        `${basePath}/api/v1/collections/${collectionId}/repair`,
        { codes },
      );
      setIssues([]);
      setResultMsg(data.message || t('repair_success', { msg: (data.repaired || []).join(', ') }));
    } catch {
      setResultMsg(t('repair_error'));
    } finally {
      setRepairing(false);
      setScanning(false);
    }
  };

  const onOpen = (next: boolean) => {
    onOpenChange(next);
    if (next && issues.length === 0 && !resultMsg) {
      runScan();
    }
  };

  const healthy = !scanning && issues.length === 0 && !resultMsg;

  return (
    <Dialog open={open} onOpenChange={onOpen}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('repair_title')}</DialogTitle>
          <DialogDescription>{t('repair_desc')}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          {scanning && (
            <div className="text-muted-foreground text-sm">{t('repair_scanning')}</div>
          )}

          {healthy && (
            <div className="flex flex-row items-center gap-2 text-sm text-green-600">
              <CheckCircle2 className="size-4" />
              <span>{t('repair_healthy')}</span>
            </div>
          )}

          {scanning === false && issues.length > 0 && (
            <>
              <div className="text-sm font-medium">
                {t('repair_issues_found', { n: issues.length })}
              </div>
              <div className="flex flex-col gap-2">
                {issues.map((issue) => (
                  <div
                    key={issue.code}
                    className="border-border flex flex-col gap-1 rounded-md border p-3 text-sm"
                  >
                    <div className="flex flex-row items-center gap-2">
                      <AlertTriangle className="size-4 text-amber-500" />
                      <span className="font-medium">{issue.message}</span>
                      {issue.count !== undefined && (
                        <Badge variant="secondary" className="ml-auto">{issue.count}</Badge>
                      )}
                    </div>
                    {issue.hint && (
                      <div className="text-muted-foreground text-xs">{issue.hint}</div>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}

          {resultMsg && (
            <div
              className={cn(
                'flex flex-row items-center gap-2 text-sm',
                resultMsg.includes('失败') ? 'text-red-600' : 'text-green-600',
              )}
            >
              <CheckCircle2 className="size-4" />
              <span>{resultMsg}</span>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={repairing}>
            {resultMsg ? t('repair_close') : t('repair_cancel')}
          </Button>
          {issues.length > 0 && (
            <Button onClick={runRepair} disabled={repairing || scanning}>
              {repairing ? t('repair_repairing') : t('repair_confirm')}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};