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
import { apiClient } from '@/lib/api/client';
import { useTranslations } from 'next-intl';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';

const defaults = {
  chunk_size: 400,
  chunk_overlap_size: 20,
  cache_enabled: true,
  cache_ttl: 86400,
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
      <Card>
        <CardHeader>
          <CardTitle>{admin_config('core_chunking')}</CardTitle>
          <CardDescription>
            {admin_config('core_chunking_description')}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div className="flex flex-col gap-2">
            <Label>{admin_config('chunk_size')}</Label>
            <Input
              type="number"
              min={50}
              max={10000}
              value={data.chunk_size}
              onChange={(e) => {
                setData({
                  ...data,
                  chunk_size: Number(e.currentTarget.value),
                });
              }}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label>{admin_config('chunk_overlap_size')}</Label>
            <Input
              type="number"
              min={0}
              max={1000}
              value={data.chunk_overlap_size}
              onChange={(e) => {
                setData({
                  ...data,
                  chunk_overlap_size: Number(e.currentTarget.value),
                });
              }}
            />
          </div>
        </CardContent>
        <CardFooter className="justify-end">
          <Button onClick={handleSave}>{common_action('save')}</Button>
        </CardFooter>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>{admin_config('cache_settings')}</CardTitle>
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
            <Label>{admin_config('cache_ttl')}</Label>
            <Input
              type="number"
              min={60}
              max={2592000}
              value={data.cache_ttl}
              onChange={(e) => {
                setData({
                  ...data,
                  cache_ttl: Number(e.currentTarget.value),
                });
              }}
            />
          </div>
        </CardContent>
        <CardFooter className="justify-end">
          <Button onClick={handleSave}>{common_action('save')}</Button>
        </CardFooter>
      </Card>
    </>
  );
};
