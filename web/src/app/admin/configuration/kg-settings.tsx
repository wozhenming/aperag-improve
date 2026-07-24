'use client';

import { Settings } from '@/api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { apiClient } from '@/lib/api/client';
import { Info, X } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';

/* Helper: label with an info icon that shows a tooltip hint on hover */
const HintLabel = ({ text, hint }: { text: string; hint: string }) => (
  <Tooltip>
    <TooltipTrigger asChild>
      <span className="inline-flex items-center gap-1 cursor-help">
        {text}
        <Info className="h-3.5 w-3.5 text-muted-foreground" />
      </span>
    </TooltipTrigger>
    <TooltipContent>
      <p className="max-w-xs">{hint}</p>
    </TooltipContent>
  </Tooltip>
);

const defaultEntityTypes = [
  'organization',
  'person',
  'geo',
  'event',
  'product',
  'technology',
  'date',
  'category',
];

const defaults = {
  kg_chunk_token_size: 1200,
  kg_chunk_overlap_token_size: 100,
  kg_entity_extract_max_gleaning: 0,
  kg_llm_model_max_async: 20,
  kg_cosine_threshold: 0.2,
  kg_max_batch_size: 32,
  kg_summary_max_tokens: 2000,
  kg_force_llm_summary_on_merge: 10,
  kg_entity_types: defaultEntityTypes,
  max_graph_nodes: 1000,
};

export const KgSettings = ({
  data: initData = {},
}: {
  data: Settings;
}) => {
  const [data, setData] = useState<Settings>({
    ...defaults,
    ...initData,
  });
  const [entityTypeInput, setEntityTypeInput] = useState('');
  const admin_config = useTranslations('admin_config');
  const common_action = useTranslations('common.action');
  const common_tips = useTranslations('common.tips');

  const entityTypes: string[] = data.kg_entity_types || defaultEntityTypes;

  const handleSave = useCallback(async () => {
    await apiClient.defaultApi.settingsPut({ settings: data });
    toast.success(common_tips('save_success'));
  }, [data, common_action, common_tips]);

  const addEntityType = useCallback(() => {
    const trimmed = entityTypeInput.trim();
    if (trimmed && !entityTypes.includes(trimmed)) {
      const updated = { ...data, kg_entity_types: [...entityTypes, trimmed] };
      setData(updated);
    }
    setEntityTypeInput('');
  }, [entityTypeInput, entityTypes, data]);

  const removeEntityType = useCallback(
    (type: string) => {
      const updated = { ...data, kg_entity_types: entityTypes.filter((t) => t !== type) };
      setData(updated);
    },
    [entityTypes, data],
  );

  useEffect(() => {
    setData({ ...defaults, ...initData });
  }, [initData]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{admin_config('kg_settings')}</CardTitle>
        <CardDescription>{admin_config('kg_settings_description')}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          <div className="flex flex-col gap-2">
            <HintLabel text={admin_config('kg_chunk_token_size')} hint={admin_config('hint_kg_chunk_token_size')} />
            <Input type="number" min={100} max={10000} value={data.kg_chunk_token_size}
              onChange={(e) => setData({ ...data, kg_chunk_token_size: Number(e.currentTarget.value) })} />
          </div>
          <div className="flex flex-col gap-2">
            <HintLabel text={admin_config('kg_chunk_overlap_token_size')} hint={admin_config('hint_kg_chunk_overlap_token_size')} />
            <Input type="number" min={0} max={1000} value={data.kg_chunk_overlap_token_size}
              onChange={(e) => setData({ ...data, kg_chunk_overlap_token_size: Number(e.currentTarget.value) })} />
          </div>
          <div className="flex flex-col gap-2">
            <HintLabel text={admin_config('kg_entity_extract_max_gleaning')} hint={admin_config('hint_kg_entity_extract_max_gleaning')} />
            <Input type="number" min={0} max={10} value={data.kg_entity_extract_max_gleaning}
              onChange={(e) => setData({ ...data, kg_entity_extract_max_gleaning: Number(e.currentTarget.value) })} />
          </div>
          <div className="flex flex-col gap-2">
            <HintLabel text={admin_config('kg_llm_model_max_async')} hint={admin_config('hint_kg_llm_model_max_async')} />
            <Input type="number" min={1} max={100} value={data.kg_llm_model_max_async}
              onChange={(e) => setData({ ...data, kg_llm_model_max_async: Number(e.currentTarget.value) })} />
          </div>
          <div className="flex flex-col gap-2">
            <HintLabel text={admin_config('kg_cosine_threshold')} hint={admin_config('hint_kg_cosine_threshold')} />
            <Input type="number" step={0.01} min={0} max={1} value={data.kg_cosine_threshold}
              onChange={(e) => setData({ ...data, kg_cosine_threshold: Number(e.currentTarget.value) })} />
          </div>
          <div className="flex flex-col gap-2">
            <HintLabel text={admin_config('kg_max_batch_size')} hint={admin_config('hint_kg_max_batch_size')} />
            <Input type="number" min={1} max={256} value={data.kg_max_batch_size}
              onChange={(e) => setData({ ...data, kg_max_batch_size: Number(e.currentTarget.value) })} />
          </div>
          <div className="flex flex-col gap-2">
            <HintLabel text={admin_config('kg_summary_max_tokens')} hint={admin_config('hint_kg_summary_max_tokens')} />
            <Input type="number" min={50} max={10000} value={data.kg_summary_max_tokens}
              onChange={(e) => setData({ ...data, kg_summary_max_tokens: Number(e.currentTarget.value) })} />
          </div>
          <div className="flex flex-col gap-2">
            <HintLabel text={admin_config('kg_force_llm_summary_on_merge')} hint={admin_config('hint_kg_force_llm_summary_on_merge')} />
            <Input type="number" min={1} max={100} value={data.kg_force_llm_summary_on_merge}
              onChange={(e) => setData({ ...data, kg_force_llm_summary_on_merge: Number(e.currentTarget.value) })} />
          </div>
          <div className="flex flex-col gap-2">
            <HintLabel text={admin_config('max_graph_nodes')} hint={admin_config('hint_max_graph_nodes')} />
            <Input type="number" min={1} max={10000} value={data.max_graph_nodes}
              onChange={(e) => setData({ ...data, max_graph_nodes: Number(e.currentTarget.value) })} />
          </div>
        </div>

        {/* Entity types */}
        <div className="flex flex-col gap-2">
          <HintLabel text={admin_config('kg_entity_types')} hint={admin_config('hint_kg_entity_types')} />
          <div className="flex flex-row gap-2">
            <Input placeholder={admin_config('kg_entity_types_placeholder')}
              value={entityTypeInput}
              onChange={(e) => setEntityTypeInput(e.currentTarget.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addEntityType(); } }} />
            <Button type="button" variant="outline" onClick={addEntityType}>
              {common_action('add')}
            </Button>
          </div>
          <div className="flex flex-wrap gap-1 mt-1">
            {entityTypes.map((type) => (
              <Badge key={type} variant="secondary">
                {type}
                <button type="button" className="ml-1 hover:text-destructive" onClick={() => removeEntityType(type)}>
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            ))}
          </div>
        </div>
      </CardContent>
      <CardFooter className="justify-end">
        <Button onClick={handleSave}>{common_action('save')}</Button>
      </CardFooter>
    </Card>
  );
};
