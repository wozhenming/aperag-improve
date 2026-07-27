'use client';
import { Document, DocumentPreview } from '@/api';
import { getDocumentStatusColor } from '@/app/workspace/collections/tools';
import { FormatDate } from '@/components/format-date';
import { Markdown } from '@/components/markdown';
import { useCollectionContext } from '@/components/providers/collection-provider';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';
import _ from 'lodash';
import { ArrowLeft, FileText, LoaderCircle, ScrollText } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { ChunkList } from './chunk-list';
import { DocumentLogViewer } from './document-log-viewer';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';

const PDFDocument = dynamic(() => import('react-pdf').then((r) => r.Document), {
  ssr: false,
});
const PDFPage = dynamic(() => import('react-pdf').then((r) => r.Page), {
  ssr: false,
});

export const DocumentDetail = ({
  document,
  documentPreview,
}: {
  document: Document;

  documentPreview: DocumentPreview;
}) => {
  const { collection } = useCollectionContext();
  const page_collections = useTranslations('page_collections');
  const page_documents = useTranslations('page_documents');
  const [numPages, setNumPages] = useState<number>(0);
  const [mdPage, setMdPage] = useState(1);
  const [mdPageSize, setMdPageSize] = useState(50000); // ~50KB per page

  const isPdf = useMemo(() => {
    return Boolean(documentPreview.doc_filename?.match(/\.pdf/));
  }, [documentPreview.doc_filename]);

  const mdContent = documentPreview.markdown_content || '';
  const mdTotalChars = mdContent.length;
  const mdTotalPages = Math.max(1, Math.ceil(mdTotalChars / mdPageSize));
  const mdCurrentContent = useMemo(() => {
    const start = (mdPage - 1) * mdPageSize;
    return mdContent.slice(start, start + mdPageSize);
  }, [mdContent, mdPage, mdPageSize]);

  useEffect(() => { setMdPage(1); }, [documentPreview]);

  useEffect(() => {
    const loadPDF = async () => {
      const { pdfjs } = await import('react-pdf');

      pdfjs.GlobalWorkerOptions.workerSrc = new URL(
        'pdfjs-dist/build/pdf.worker.min.mjs',
        import.meta.url,
      ).toString();
    };
    loadPDF();
  }, []);

  return (
    <>
      <Tabs defaultValue="markdown" className="gap-4">
        <div className="flex flex-row items-center justify-between gap-2">
          <div className="flex flex-row items-center gap-4">
            <Button asChild variant="ghost" size="icon">
              <Link href={`/workspace/collections/${collection.id}/documents`}>
                <ArrowLeft />
              </Link>
            </Button>
            <div className={cn('max-w-80 truncate')}>
              {documentPreview.doc_filename}
            </div>
          </div>

          <div className="flex flex-row gap-6">
            <div className="text-muted-foreground flex flex-row items-center gap-4 text-sm">
              <div>{(Number(document.size || 0) / 1000).toFixed(2)} KB</div>
              <Separator
                orientation="vertical"
                className="data-[orientation=vertical]:h-6"
              />
              {document.updated ? (
                <>
                  <div>
                    <FormatDate datetime={new Date(document.updated)} />
                  </div>
                  <Separator
                    orientation="vertical"
                    className="data-[orientation=vertical]:h-6"
                  />
                </>
              ) : null}
              <div className={getDocumentStatusColor(document.status)}>
                {_.capitalize(document.status)}
              </div>
            </div>
            <TabsList>
              <TabsTrigger value="markdown">Markdown</TabsTrigger>
              {isPdf && <TabsTrigger value="pdf">PDF</TabsTrigger>}
              <TabsTrigger value="chunks">
                <FileText className="mr-1 h-4 w-4" />
                {page_collections('chunks')}
              </TabsTrigger>
              <TabsTrigger value="logs">
                <ScrollText className="mr-1 h-4 w-4" />
                {page_documents('index_logs')}
              </TabsTrigger>
            </TabsList>
          </div>
        </div>

        <TabsContent value="markdown">
          <Card>
            <CardContent>
              {mdTotalPages > 1 && (
                <div className="flex items-center justify-between mb-3 text-xs text-muted-foreground">
                  <div className="flex items-center gap-2">
                    <span>{(mdTotalChars / 1000).toFixed(1)}K {page_collections('chars')}</span>
                    <Select value={String(mdPageSize)} onValueChange={(v) => { setMdPageSize(Number(v)); setMdPage(1); }}>
                      <SelectTrigger className="h-7 w-20 text-xs"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {[10000, 25000, 50000, 100000].map((s) => (
                          <SelectItem key={s} value={String(s)}>{(s / 1000).toFixed(0)}K/{page_collections('page')}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" className="h-7 text-xs" disabled={mdPage <= 1}
                      onClick={() => setMdPage(mdPage - 1)}>‹</Button>
                    <span>{mdPage}/{mdTotalPages}</span>
                    <Button variant="outline" size="sm" className="h-7 text-xs" disabled={mdPage >= mdTotalPages}
                      onClick={() => setMdPage(mdPage + 1)}>›</Button>
                  </div>
                </div>
              )}
              <Markdown>{mdCurrentContent}</Markdown>
              {mdTotalPages > 1 && (
                <div className="flex items-center justify-center mt-4 text-xs text-muted-foreground gap-2">
                  <Button variant="outline" size="sm" className="h-7 text-xs" disabled={mdPage <= 1}
                    onClick={() => setMdPage(mdPage - 1)}>‹</Button>
                  <span>{mdPage}/{mdTotalPages}</span>
                  <Button variant="outline" size="sm" className="h-7 text-xs" disabled={mdPage >= mdTotalPages}
                    onClick={() => setMdPage(mdPage + 1)}>›</Button>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {isPdf && (
          <TabsContent value="pdf">
            <PDFDocument
              file={`${process.env.NEXT_PUBLIC_BASE_PATH || ''}/api/v1/collections/${collection.id}/documents/${document.id}/object?path=${documentPreview.converted_pdf_object_path}`}
              onLoadSuccess={({ numPages }: { numPages: number }) => {
                setNumPages(numPages);
              }}
              loading={
                <div className="flex flex-col py-8">
                  <LoaderCircle className="size-10 animate-spin self-center opacity-50" />
                </div>
              }
              className="flex flex-col justify-center gap-1"
            >
              {_.times(numPages).map((index) => {
                return (
                  <div key={index} className="text-center">
                    <Card className="inline-block overflow-hidden p-0">
                      <PDFPage pageNumber={index + 1} className="bg-accent" />
                    </Card>
                  </div>
                );
              })}
            </PDFDocument>
          </TabsContent>
        )}

        <TabsContent value="chunks">
          <ChunkList collectionId={collection.id || ''} documentId={document.id || ''} />
        </TabsContent>

        <TabsContent value="logs">
          <DocumentLogViewer collectionId={collection.id || ''} documentId={document.id || ''} />
        </TabsContent>
      </Tabs>
    </>
  );
};
