'use client';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { LoaderCircle, Search, Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useCallback, useEffect, useRef, useState } from 'react';

interface Chunk {
  chunk_id: string;
  content: string;
  title: string;
  chunk_size: number;
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
  const didInit = useRef(false);

  const cursorRef = useRef<{ first: string; last: string; page: number }[]>([]);

  const load = useCallback(
    async (p: number, ps: number, q: string, after?: string, before?: string) => {
      setLoading(true);
      try {
        let url = `/api/v1/collections/${encodeURIComponent(collectionId)}/documents/${encodeURIComponent(documentId)}/chunks?page=${p}&page_size=${ps}&search=${encodeURIComponent(q)}`;
        if (after) url += `&after=${encodeURIComponent(after)}`;
        if (before) url += `&before=${encodeURIComponent(before)}`;
        const resp = await fetch(url);
        const data = await resp.json();
        const items: Chunk[] = data.chunks || [];
        setChunks(items);
        setTotal(data.total || 0);
        setPage(p);
        setPageSize(ps);
        // Store cursor for this page
        if (items.length > 0) {
          const entry = { first: items[0].chunk_id, last: items[items.length - 1].chunk_id, page: p };
          cursorRef.current[p] = entry;
        }
      } catch { /* ignore */ } finally {
        setLoading(false);
      }
    },
    [collectionId, documentId],
  );

  const goNext = () => {
    const lastItem = chunks[chunks.length - 1];
    if (lastItem) load(page + 1, pageSize, search, lastItem.chunk_id);
  };

  const goPrev = () => {
    const firstItem = chunks[0];
    if (firstItem) load(page - 1, pageSize, search, undefined, firstItem.chunk_id);
  };

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
    if (n >= 1 && n <= totalPages) {
      // Use cached cursor for nearby pages, fallback to first page for distant jumps
      const cached = cursorRef.current[n];
      if (cached) {
        load(n, pageSize, search, cached.last || undefined, n < page ? cached.first : undefined);
      } else {
        load(1, pageSize, search); // fallback to page 1
      }
      setJumpTo('');
    }
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
            onClick={goPrev}>‹</Button>
          <span>{page}/{totalPages}</span>
          <Button variant="outline" size="sm" className="h-7 text-xs" disabled={page >= totalPages}
            onClick={goNext}>›</Button>
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
        <Card key={chunk.chunk_id}>
          <CardContent className="py-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-muted-foreground">
                #{(page - 1) * pageSize + idx + 1} {chunk.chunk_id}
              </span>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">{chunk.chunk_size} {page_collections('chars')}</span>
                <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-destructive"
                  onClick={() => handleDelete(chunk.chunk_id)}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
            {chunk.title && <p className="text-xs text-muted-foreground mb-1">{chunk.title}</p>}
            <p className="text-sm whitespace-pre-wrap line-clamp-6">{chunk.content}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
};
