'use client';

import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import axios from 'axios';
import { LoaderCircle, ScrollText } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useCallback, useEffect, useRef, useState } from 'react';

interface TaskLogEntry {
  id: number;
  collection_id: string | null;
  document_id: string | null;
  index_type: string | null;
  level: string;
  message: string;
  created_at: string;
}

const LEVEL_COLORS: Record<string, string> = {
  ERROR: 'text-red-500',
  WARNING: 'text-yellow-500',
  INFO: 'text-muted-foreground',
  DEBUG: 'text-muted-foreground/60',
};

export const DocumentLogViewer = ({
  collectionId,
  documentId,
}: {
  collectionId: string;
  documentId: string;
}) => {
  const page_documents = useTranslations('page_documents');
  const [logs, setLogs] = useState<TaskLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [hasMore, setHasMore] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchLogs = useCallback(
    async (append = false) => {
      try {
        const basePath = process.env.NEXT_PUBLIC_BASE_PATH || '';
        const params: Record<string, string | number> = { limit: 200 };
        params.document_id = documentId;
        if (append && logs.length > 0) {
          params.before_id = logs[logs.length - 1].id;
        }
        const request = axios.create({ baseURL: `${basePath}/api/v1`, timeout: 10000 });
        const res = await request.get('/logs', { params });
        const data = res.data as { logs: TaskLogEntry[]; has_more: boolean };
        if (append) {
          setLogs((prev) => [...prev, ...data.logs]);
        } else {
          setLogs(data.logs || []);
        }
        setHasMore(data.has_more);
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    },
    [documentId, logs],
  );

  useEffect(() => {
    setLoading(true);
    fetchLogs(false);

    // Auto-refresh every 5 seconds
    intervalRef.current = setInterval(() => fetchLogs(false), 5000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [documentId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-12">
          <LoaderCircle className="size-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (logs.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-2">
          <ScrollText className="size-8" />
          <p className="text-sm">{page_documents('no_index_logs')}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent>
        <div className="max-h-[60vh] overflow-auto font-mono text-xs">
          {logs.map((log) => (
            <div
              key={log.id}
              className={cn(
                'flex gap-3 py-1 border-b border-border/30 last:border-0',
                log.level === 'ERROR' && 'bg-red-500/5',
              )}
            >
              <span className="text-muted-foreground/50 shrink-0 w-36">
                {new Date(log.created_at).toLocaleString()}
              </span>
              <span
                className={cn(
                  'shrink-0 w-16 font-semibold',
                  LEVEL_COLORS[log.level] || 'text-muted-foreground',
                )}
              >
                {log.level}
              </span>
              {log.index_type && (
                <span className="shrink-0 w-20 text-blue-500">{log.index_type}</span>
              )}
              <span className="break-all">{log.message}</span>
            </div>
          ))}
        </div>
        {hasMore && (
          <div className="flex justify-center mt-3">
            <button
              className="text-xs text-muted-foreground hover:text-foreground underline"
              onClick={() => fetchLogs(true)}
            >
              {page_documents('load_more')}
            </button>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
