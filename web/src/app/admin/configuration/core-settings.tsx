'use client';

import { Settings } from '@/api';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { apiClient } from '@/lib/api/client';
import { Info } from 'lucide-react';
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

const defaults = {
  chunk_size: 400,
  chunk_overlap_size: 20,
  cache_enabled: true,
  cache_ttl: 86400,
  parent_child_enabled: false,
  parent_chunk_size: 800,
  child_chunk_size: 150,
  child_chunk_overlap: 50,
  parent_chunk_separator: '',
  child_chunk_separator: '',
  preprocess_collapse_whitespace: false,
  preprocess_remove_urls_emails: false,
};

export const CoreSettings = ({
  data: initData = {},
}: {
  data: Settings;
}) => {
  const [data, setData] = useState<Settings>({
    ...defaults,
    ...initData,
  });
  const admin_config = useTranslations('admin_config');
  const common_action = useTranslations('common.action');
  const common_tips = useTranslations('common.tips');

  const handleSave = useCallback(async () => {
    await apiClient.defaultApi.settingsPut({
      settings: data,
    });
    toast.success(common_tips('save_success'));
  }, [data, common_action, common_tips]);

  useEffect(() => {
    setData({
      ...defaults,
      ...initData,
    });
  }, [initData]);

  return (
    <>
      {/* ── Core chunking card ── */}
      <Card>
        <CardHeader>
          <CardTitle>{admin_config('core_chunking')}</CardTitle>
          <CardDescription>
            {admin_config('core_chunking_description')}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div className="flex flex-col gap-2">
            <HintLabel text={admin_config('chunk_size')} hint={admin_config('hint_chunk_size')} />
            <Input
              type="number"
              min={50}
              max={10000}
              value={data.chunk_size}
              onChange={(e) => {
                setData({ ...data, chunk_size: Number(e.currentTarget.value) });
              }}
            />
          </div>
          <div className="flex flex-col gap-2">
            <HintLabel text={admin_config('chunk_overlap_size')} hint={admin_config('hint_chunk_overlap_size')} />
            <Input
              type="number"
              min={0}
              max={1000}
              value={data.chunk_overlap_size}
              onChange={(e) => {
                setData({ ...data, chunk_overlap_size: Number(e.currentTarget.value) });
              }}
            />
          </div>
        </CardContent>
        <CardFooter className="justify-end">
          <Button onClick={handleSave}>{common_action('save')}</Button>
        </CardFooter>
      </Card>

      {/* ── Cache card ── */}
      <Card>
        <CardHeader>
          <div className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>
                <HintLabel text={admin_config('cache_settings')} hint={admin_config('hint_cache_enabled')} />
              </CardTitle>
              <CardDescription>
                {admin_config('cache_settings_description')}
              </CardDescription>
            </div>
            <Switch
              checked={data.cache_enabled}
              onCheckedChange={(checked) => {
                const updated = { ...data, cache_enabled: checked };
                setData(updated);
                apiClient.defaultApi.settingsPut({ settings: updated });
              }}
            />
          </div>
        </CardHeader>
        <CardContent className={data.cache_enabled ? 'block' : 'hidden'}>
          <div className="flex flex-col gap-2">
            <HintLabel text={admin_config('cache_ttl')} hint={admin_config('hint_cache_ttl')} />
            <Input
              type="number"
              min={60}
              max={2592000}
              value={data.cache_ttl}
              onChange={(e) => {
                setData({ ...data, cache_ttl: Number(e.currentTarget.value) });
              }}
            />
          </div>
        </CardContent>
        <CardFooter className="justify-end">
          <Button onClick={handleSave}>{common_action('save')}</Button>
        </CardFooter>
      </Card>

      {/* ── Parent-child chunking card ── */}
      <Card>
        <CardHeader>
          <div className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>
                <HintLabel text={admin_config('parent_child_chunking')} hint={admin_config('hint_parent_child_enabled')} />
              </CardTitle>
              <CardDescription>
                {admin_config('parent_child_chunking_description')}
              </CardDescription>
            </div>
            <Switch
              checked={data.parent_child_enabled}
              onCheckedChange={(checked) => {
                const updated = { ...data, parent_child_enabled: checked };
                setData(updated);
                apiClient.defaultApi.settingsPut({ settings: updated });
              }}
            />
          </div>
        </CardHeader>
        <CardContent className={data.parent_child_enabled ? 'block' : 'hidden'}>
          <div className="flex flex-col gap-6">
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              <div className="flex flex-col gap-2">
                <HintLabel text={admin_config('parent_chunk_size')} hint={admin_config('hint_parent_chunk_size')} />
                <Input type="number" min={200} max={5000} value={data.parent_chunk_size}
                  onChange={(e) => setData({ ...data, parent_chunk_size: Number(e.currentTarget.value) })} />
              </div>
              <div className="flex flex-col gap-2">
                <HintLabel text={admin_config('child_chunk_size')} hint={admin_config('hint_child_chunk_size')} />
                <Input type="number" min={50} max={1000} value={data.child_chunk_size}
                  onChange={(e) => setData({ ...data, child_chunk_size: Number(e.currentTarget.value) })} />
              </div>
              <div className="flex flex-col gap-2">
                <HintLabel text={admin_config('child_chunk_overlap')} hint={admin_config('hint_child_chunk_overlap')} />
                <Input type="number" min={0} max={500} value={data.child_chunk_overlap}
                  onChange={(e) => setData({ ...data, child_chunk_overlap: Number(e.currentTarget.value) })} />
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="flex flex-col gap-2">
                <HintLabel text={admin_config('parent_chunk_separator')} hint={admin_config('hint_parent_chunk_separator')} />
                <Input placeholder="##" value={data.parent_chunk_separator}
                  onChange={(e) => setData({ ...data, parent_chunk_separator: e.currentTarget.value })} />
              </div>
              <div className="flex flex-col gap-2">
                <HintLabel text={admin_config('child_chunk_separator')} hint={admin_config('hint_child_chunk_separator')} />
                <Input placeholder="\n\n" value={data.child_chunk_separator}
                  onChange={(e) => setData({ ...data, child_chunk_separator: e.currentTarget.value })} />
              </div>
            </div>

            <div className="flex flex-col gap-3">
              <Label className="text-sm font-medium">
                {admin_config('text_preprocessing')}
              </Label>
              <div className="flex flex-row items-center justify-between">
                <div className="flex flex-row items-center gap-1">
                  <p className="text-sm">{admin_config('preprocess_collapse_whitespace')}</p>
                  <HintLabel text="" hint={admin_config('hint_preprocess_collapse_whitespace')} />
                </div>
                <Switch checked={data.preprocess_collapse_whitespace}
                  onCheckedChange={(checked) => {
                    const updated = { ...data, preprocess_collapse_whitespace: checked };
                    setData(updated);
                    apiClient.defaultApi.settingsPut({ settings: updated });
                  }} />
              </div>
              <div className="flex flex-row items-center justify-between">
                <div className="flex flex-row items-center gap-1">
                  <p className="text-sm">{admin_config('preprocess_remove_urls_emails')}</p>
                  <HintLabel text="" hint={admin_config('hint_preprocess_remove_urls_emails')} />
                </div>
                <Switch checked={data.preprocess_remove_urls_emails}
                  onCheckedChange={(checked) => {
                    const updated = { ...data, preprocess_remove_urls_emails: checked };
                    setData(updated);
                    apiClient.defaultApi.settingsPut({ settings: updated });
                  }} />
              </div>
            </div>
          </div>
        </CardContent>
        <CardFooter className="justify-end">
          <Button onClick={handleSave}>{common_action('save')}</Button>
        </CardFooter>
      </Card>
    </>
  );
};
