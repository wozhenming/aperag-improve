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
import { cn } from '@/lib/utils';
import { Info, LaptopMinimalCheck, LoaderCircle } from 'lucide-react';
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

const defaultValue = {
  use_mineru: false,
  mineru_api_token: '',
  mineru_api_base_url: '',
  use_doc_ray: false,
  use_markitdown: true,
};

export const ParserSettings = ({
  data: initData = defaultValue,
}: {
  data: Settings;
}) => {
  const [data, setData] = useState<Settings>({
    ...defaultValue,
    ...initData,
  });
  const admin_config = useTranslations('admin_config');
  const common_action = useTranslations('common.action');
  const common_tips = useTranslations('common.tips');
  const [checked, setChecked] = useState<boolean>(false);
  const [checking, setChecking] = useState<boolean>(false);

  const handleSave = useCallback(async () => {
    await apiClient.defaultApi.settingsPut({ settings: data });
    toast.success(common_tips('save_success'));
  }, [data, common_tips]);

  const handleSwitchChange = useCallback(
    async (key: keyof Settings, checked: boolean) => {
      const settings = { ...data, [key]: checked };
      setData(settings);
      await apiClient.defaultApi.settingsPut({ settings });
    },
    [data],
  );

  const handleCheckMineruToken = useCallback(async () => {
    if (!data.mineru_api_token) {
      toast.error(admin_config('mineru_api_token_required'));
      return;
    }
    setChecking(true);
    const res = await apiClient.defaultApi.settingsTestMineruTokenPost({
      settingsTestMineruTokenPostRequest: { token: data.mineru_api_token },
    });
    if (res.data.status_code === 401) {
      toast.error(admin_config('mineru_api_token_invalid'));
    } else {
      setChecked(true);
      toast.success(common_tips('save_success'));
    }
    setChecking(false);
  }, [admin_config, common_tips, data.mineru_api_token]);

  useEffect(() => {
    setData({ ...defaultValue, ...initData });
  }, [initData]);

  return (
    <>
      {/* ── MinerU card ── */}
      <Card>
        <CardHeader>
          <div className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>
                <HintLabel text={admin_config('mineru_api')} hint={admin_config('hint_use_mineru')} />
              </CardTitle>
              <CardDescription>{admin_config('mineru_api_description')}</CardDescription>
            </div>
            <Switch
              checked={data.use_mineru}
              onCheckedChange={(checked) => handleSwitchChange('use_mineru', checked)}
            />
          </div>
        </CardHeader>
        <CardContent className={data.use_mineru ? 'block' : 'hidden'}>
          <div className="flex flex-col gap-2">
            <HintLabel text={admin_config('mineru_api_token')} hint={admin_config('hint_mineru_api_token')} />
            <div className="flex flex-row gap-4">
              <Input placeholder={admin_config('mineru_api_token')} value={data.mineru_api_token}
                onChange={(e) => setData({ ...data, mineru_api_token: e.currentTarget.value })} />
              <Button disabled={checking} variant="outline" onClick={handleCheckMineruToken}>
                {checking ? <LoaderCircle className="animate-spin opacity-50" /> : <LaptopMinimalCheck />}
                {admin_config('check')}
              </Button>
            </div>
          </div>
          <div className="text-muted-foreground mt-2 text-sm">
            {admin_config('mineru_api_token_tips')}
          </div>
          <div className="flex flex-col gap-2 mt-4">
            <HintLabel text={admin_config('mineru_api_base_url')} hint={admin_config('hint_mineru_api_base_url')} />
            <Input placeholder="https://mineru.net" value={data.mineru_api_base_url || ''}
              onChange={(e) => setData({ ...data, mineru_api_base_url: e.currentTarget.value })} />
          </div>
        </CardContent>
        <CardFooter className={cn('justify-end', data.use_mineru ? 'flex' : 'hidden')}>
          <Button disabled={!checked} onClick={handleSave}>{common_action('save')}</Button>
        </CardFooter>
      </Card>

      {/* ── DocRay card ── */}
      <Card>
        <CardHeader>
          <div className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>
                <HintLabel text={admin_config('use_doc_ray')} hint={admin_config('hint_use_doc_ray')} />
              </CardTitle>
              <CardDescription>{admin_config('use_doc_ray_description')}</CardDescription>
            </div>
            <Switch
              checked={data.use_doc_ray}
              onCheckedChange={(checked) => handleSwitchChange('use_doc_ray', checked)}
            />
          </div>
        </CardHeader>
      </Card>

      {/* ── MarkItDown card ── */}
      <Card>
        <CardHeader>
          <div className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>
                <HintLabel text={admin_config('use_markitdown')} hint={admin_config('hint_use_markitdown')} />
              </CardTitle>
              <CardDescription>{admin_config('use_markitdown_description')}</CardDescription>
            </div>
            <Switch
              checked={data.use_markitdown}
              onCheckedChange={(checked) => handleSwitchChange('use_markitdown', checked)}
            />
          </div>
        </CardHeader>
      </Card>

      {/* ── PaddleOCR & Whisper card ── */}
      <Card>
        <CardHeader>
          <CardTitle>{admin_config('ocr_asr_settings')}</CardTitle>
          <CardDescription>{admin_config('ocr_asr_settings_description')}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div className="flex flex-col gap-2">
            <HintLabel text={admin_config('paddleocr_host')} hint={admin_config('hint_paddleocr_host')} />
            <Input placeholder="http://paddleocr:8866" value={data.paddleocr_host || ''}
              onChange={(e) => setData({ ...data, paddleocr_host: e.currentTarget.value })} />
          </div>
          <div className="flex flex-col gap-2">
            <HintLabel text={admin_config('whisper_host')} hint={admin_config('hint_whisper_host')} />
            <Input placeholder="http://whisper:9000" value={data.whisper_host || ''}
              onChange={(e) => setData({ ...data, whisper_host: e.currentTarget.value })} />
          </div>
        </CardContent>
        <CardFooter className="justify-end">
          <Button onClick={handleSave}>{common_action('save')}</Button>
        </CardFooter>
      </Card>
    </>
  );
};
