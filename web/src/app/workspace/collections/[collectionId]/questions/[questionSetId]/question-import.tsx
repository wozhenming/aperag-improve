'use client';

import { QuestionSet } from '@/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { apiClient } from '@/lib/api/client';
import { Slot } from '@radix-ui/react-slot';
import { AlertCircle, Check, FileUp, LoaderCircle } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useCallback, useRef, useState } from 'react';
import { toast } from 'sonner';

interface ParsedQuestion {
  question_text: string;
  ground_truth: string;
}

/**
 * Parse CSV text into question objects.
 * Expected columns: question_text (or question), ground_truth (or answer).
 * First row is treated as header.
 */
function parseCSV(text: string): ParsedQuestion[] {
  const lines = text.trim().split('\n');
  if (lines.length < 2) return [];

  const header = lines[0].toLowerCase().split(',').map((h) => h.trim().replace(/^"|"$/g, ''));
  const qIdx = header.findIndex((h) => h === 'question_text' || h === 'question');
  const aIdx = header.findIndex((h) => h === 'ground_truth' || h === 'answer');

  if (qIdx === -1 || aIdx === -1) return [];

  const results: ParsedQuestion[] = [];
  for (let i = 1; i < lines.length; i++) {
    const cols = parseCSVLine(lines[i]);
    const question = (cols[qIdx] || '').trim().replace(/^"|"$/g, '');
    const answer = (cols[aIdx] || '').trim().replace(/^"|"$/g, '');
    if (question && answer) {
      results.push({ question_text: question, ground_truth: answer });
    }
  }
  return results;
}

/** Simple CSV line parser that handles quoted fields. */
function parseCSVLine(line: string): string[] {
  const result: string[] = [];
  let current = '';
  let inQuotes = false;
  for (const ch of line) {
    if (ch === '"') { inQuotes = !inQuotes; continue; }
    if (ch === ',' && !inQuotes) { result.push(current); current = ''; continue; }
    current += ch;
  }
  result.push(current);
  return result;
}

/** Parse JSON text — expects an array of { question_text, ground_truth } objects. */
function parseJSON(text: string): ParsedQuestion[] {
  const data = JSON.parse(text);
  if (!Array.isArray(data)) return [];
  return data
    .filter((item) => item.question_text || item.question)
    .map((item) => ({
      question_text: item.question_text || item.question || '',
      ground_truth: item.ground_truth || item.answer || '',
    }));
}

const MAX_PREVIEW = 20;

export const QuestionImport = ({
  questionSet,
  children,
}: {
  questionSet: QuestionSet;
  children: React.ReactNode;
}) => {
  const [visible, setVisible] = useState(false);
  const [parsed, setParsed] = useState<ParsedQuestion[]>([]);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const page_question_set = useTranslations('page_question_set');
  const common_action = useTranslations('common.action');
  const common_tips = useTranslations('common.tips');

  const handleFile = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setError('');
    setParsed([]);
    const file = e.target.files?.[0];
    if (!file) return;

    const ext = file.name.split('.').pop()?.toLowerCase();
    const reader = new FileReader();
    reader.onload = (evt) => {
      const raw = evt.target?.result as string;
      try {
        let result: ParsedQuestion[] = [];
        if (ext === 'csv') {
          result = parseCSV(raw);
        } else if (ext === 'json') {
          result = parseJSON(raw);
        } else {
          setError(page_question_set('import_unsupported_format'));
          return;
        }
        if (!result.length) {
          setError(page_question_set('import_no_valid_questions'));
        }
        setParsed(result);
      } catch {
        setError(page_question_set('import_parse_error'));
      }
    };
    reader.readAsText(file);
  }, [page_question_set]);

  const handleImport = useCallback(async () => {
    if (!parsed.length || !questionSet?.id) return;
    setImporting(true);
    try {
      await apiClient.evaluationApi.addQuestionsApiV1QuestionSetsQsIdQuestionsPost({
        qsId: questionSet.id,
        questionsAdd: { questions: parsed },
      });
      toast.success(common_tips('save_success'));
      router.refresh();
      setVisible(false);
    } catch {
      toast.error(page_question_set('import_failed'));
    } finally {
      setImporting(false);
    }
  }, [parsed, questionSet?.id, router, common_tips, page_question_set]);

  return (
    <Dialog
      open={visible}
      onOpenChange={(open) => {
        if (!open) { setParsed([]); setError(''); }
        setVisible(open);
      }}
    >
      <DialogTrigger asChild>
        <Slot onClick={(e) => { setVisible(true); e.preventDefault(); }}>
          {children}
        </Slot>
      </DialogTrigger>

      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{page_question_set('import_questions')}</DialogTitle>
          <DialogDescription>
            {page_question_set('import_questions_description')}
          </DialogDescription>
        </DialogHeader>

        {/* Format guide */}
        <div className="bg-muted rounded-md p-3 text-xs space-y-1">
          <p className="font-medium">{page_question_set('import_format_guide')}:</p>
          <p>
            <Badge variant="outline" className="mr-1">CSV</Badge>
            question_text, ground_truth
          </p>
          <p>
            <Badge variant="outline" className="mr-1">JSON</Badge>
            {'[{ "question_text": "...", "ground_truth": "..." }]'}
          </p>
        </div>

        {/* File picker */}
        <div className="flex items-center gap-3">
          <Button variant="outline" onClick={() => fileInputRef.current?.click()}>
            <FileUp className="mr-2 h-4 w-4" />
            {page_question_set('import_select_file')}
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.json"
            className="hidden"
            onChange={handleFile}
          />
          {parsed.length > 0 && (
            <span className="text-sm text-muted-foreground">
              {page_question_set('import_parsed_count')}: {parsed.length}
            </span>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" />
            {error}
          </div>
        )}

        {/* Preview table */}
        {parsed.length > 0 && (
          <div className="max-h-64 overflow-auto border rounded-md">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">#</TableHead>
                  <TableHead>{page_question_set('question_content')}</TableHead>
                  <TableHead>{page_question_set('ground_truth')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {parsed.slice(0, MAX_PREVIEW).map((q, i) => (
                  <TableRow key={i}>
                    <TableCell className="text-muted-foreground">{i + 1}</TableCell>
                    <TableCell className="max-w-xs truncate">{q.question_text}</TableCell>
                    <TableCell className="max-w-xs truncate">{q.ground_truth}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {parsed.length > MAX_PREVIEW && (
              <p className="text-muted-foreground p-2 text-xs text-center">
                {page_question_set('import_more_items')}: {parsed.length - MAX_PREVIEW}
              </p>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => { setParsed([]); setError(''); setVisible(false); }}>
            {common_action('cancel')}
          </Button>
          <Button disabled={!parsed.length || importing} onClick={handleImport}>
            {importing ? (
              <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Check className="mr-2 h-4 w-4" />
            )}
            {page_question_set('import_confirm')} ({parsed.length})
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
