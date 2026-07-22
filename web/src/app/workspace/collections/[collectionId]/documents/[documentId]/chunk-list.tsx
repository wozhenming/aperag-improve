'use client';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Eye, EyeOff, LoaderCircle, Search, Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import React, { useCallback, useEffect, useRef, useState } from 'react';

interface Chunk {
  chunk_id: string;
  content: string;
  title: string;
  chunk_size: number;
  enabled?: boolean;
}

const PAGE_SIZES = [10, 20, 50, 100];

export const ChunkList = ({
  collectionId,
  documentId,
}: {
  collectionId: string;
  documentId: string;
}) => {
  const page_collections = useTranslations('page_collections');
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [jumpTo, setJumpTo] = useState('');
  const [detailChunk, setDetailChunk] = useState<Chunk | null>(null);
  const didInit = useRef(false);

  const load = useCallback(
    async (p: number, ps: number, q: string) => {
      setLoading(true);
      try {
        const url = `/api/v1/collections/${encodeURIComponent(collectionId)}/documents/${encodeURIComponent(documentId)}/chunks?page=${p}&page_size=${ps}&search=${encodeURIComponent(q)}`;
        const resp = await fetch(url);
        const data = await resp.json();
        setChunks(data.chunks || []);
        setTotal(data.total || 0);
        setPage(p);
        setPageSize(ps);
      } catch { /* ignore */ } finally {
        setLoading(false);
      }
    },
    [collectionId, documentId],
  );

  useEffect(() => {
    if (!didInit.current) {
      didInit.current = true;
      load(1, 20, '');
    }
  }, [load]);

  const handleSearch = () => {
    setSearch(searchInput);
    load(1, pageSize, searchInput);
  };

  const handleToggle = async (e: React.MouseEvent, chunkId: string) => {
    e.stopPropagation();
    // Optimistic UI update
    setChunks((prev) => prev.map((c) => c.chunk_id === chunkId ? { ...c, enabled: !c.enabled } : c));
    try {
      await fetch(
        `/api/v1/collections/${encodeURIComponent(collectionId)}/documents/${encodeURIComponent(documentId)}/chunks/${encodeURIComponent(chunkId)}/toggle`,
        { method: 'POST' },
      );
    } catch {
      // Revert on failure
      setChunks((prev) => prev.map((c) => c.chunk_id === chunkId ? { ...c, enabled: !c.enabled } : c));
    }
  };

  const handleDelete = async (chunkId: string) => {
    if (!confirm(page_collections('chunk_delete_confirm'))) return;
    try {
      await fetch(
        `/api/v1/collections/${encodeURIComponent(collectionId)}/documents/${encodeURIComponent(documentId)}/chunks/${encodeURIComponent(chunkId)}`,
        { method: 'DELETE' },
      );
      load(page, pageSize, search);
    } catch { /* ignore */ }
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const handleJump = () => {
    const n = parseInt(jumpTo);
    if (n >= 1 && n <= totalPages) { load(n, pageSize, search); setJumpTo(''); }
  };

  return (
    <div className="flex flex-col gap-3">
      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="flex items-center gap-1 flex-1 min-w-[200px]">
          <Input placeholder={page_collections('chunk_search')} value={searchInput}
            className="h-8 text-sm"
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSearch(); }} />
          <Button variant="outline" size="sm" className="h-8" onClick={handleSearch}>
            <Search className="h-3.5 w-3.5" />
          </Button>
        </div>
        <Select value={String(pageSize)} onValueChange={(v) => load(1, Number(v), search)}>
          <SelectTrigger className="h-8 w-20 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            {PAGE_SIZES.map((s) => (<SelectItem key={s} value={String(s)}>{s}</SelectItem>))}
          </SelectContent>
        </Select>
        <div className="flex items-center gap-1">
          <Input placeholder="#" value={jumpTo} className="h-8 w-14 text-xs text-center"
            onChange={(e) => setJumpTo(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleJump(); }} />
          <Button variant="outline" size="sm" className="h-8 text-xs" onClick={handleJump}>
            {page_collections('chunk_jump')}
          </Button>
        </div>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{total} {page_collections('chunks_total')}</span>
        <div className="flex items-center gap-1">
          <Button variant="outline" size="sm" className="h-7 text-xs" disabled={page <= 1}
            onClick={() => load(page - 1, pageSize, search)}>‹</Button>
          <span>{page}/{totalPages}</span>
          <Button variant="outline" size="sm" className="h-7 text-xs" disabled={page >= totalPages}
            onClick={() => load(page + 1, pageSize, search)}>›</Button>
        </div>
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex justify-center py-8">
          <LoaderCircle className="size-8 animate-spin opacity-50" />
        </div>
      )}

      {/* Empty state */}
      {!loading && chunks.length === 0 && (
        <Card><CardContent className="py-8 text-center text-muted-foreground text-sm">{page_collections('no_chunks')}</CardContent></Card>
      )}

      {/* Chunk list */}
      {!loading && chunks.map((chunk, idx) => (
        <Card key={chunk.chunk_id} className="cursor-pointer hover:bg-accent/30 transition-colors"
          onClick={() => setDetailChunk(chunk)}>
          <CardContent className="py-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-muted-foreground" onClick={(e) => e.stopPropagation()}>
                #{(page - 1) * pageSize + idx + 1} {chunk.chunk_id}
              </span>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">{chunk.chunk_size} {page_collections('chars')}</span>
                <Button variant="ghost" size="sm" className="h-6 w-6 p-0"
                  title={chunk.enabled === false ? page_collections('chunk_disabled') : page_collections('chunk_enabled')}
                  onClick={(e) => handleToggle(e, chunk.chunk_id)}>
                  {chunk.enabled === false ? <EyeOff className="h-3.5 w-3.5 text-muted-foreground" /> : <Eye className="h-3.5 w-3.5 text-green-600" />}
                </Button>
                <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-destructive"
                  onClick={(e) => { e.stopPropagation(); handleDelete(chunk.chunk_id); }}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
            {chunk.title && <p className="text-xs text-muted-foreground mb-1">{chunk.title}</p>}
            <p className="text-sm whitespace-pre-wrap line-clamp-6">{chunk.content}</p>
          </CardContent>
        </Card>
      ))}

      {/* Chunk detail dialog */}
      <Dialog open={!!detailChunk} onOpenChange={() => setDetailChunk(null)}>
        <DialogContent className="sm:max-w-[90vw] lg:max-w-[80vw] max-h-[90vh] overflow-auto">
          <DialogHeader>
            <DialogTitle className="text-sm font-mono">{detailChunk?.chunk_id}</DialogTitle>
          </DialogHeader>
          <div className="text-sm space-y-2">
            {detailChunk?.title && <p className="text-muted-foreground">{detailChunk.title}</p>}
            <div className="bg-muted rounded-md p-4 whitespace-pre-wrap break-words max-h-[70vh] overflow-auto">
              {detailChunk?.content}
            </div>
            <p className="text-xs text-muted-foreground">{detailChunk?.chunk_size} {page_collections('chars')}</p>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};
