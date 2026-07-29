'use client';

import { GraphNode } from '@/api';
import { Markdown } from '@/components/markdown';
import { Separator } from '@/components/ui/separator';
import {
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
} from '@/components/ui/drawer';
import { useTranslations } from 'next-intl';

export const CollectionGraphNodeDetail = ({
  open,
  node,
  onClose,
}: {
  open: boolean;
  node?: GraphNode;
  onClose: () => void;
}) => {
  const page_graph = useTranslations('page_graph');

  // Extract OWL structured properties from node.properties.properties (nested JSONB)
  const structured = (node?.properties as Record<string, unknown>)?.properties as
    | Record<string, unknown>
    | undefined;
  const hasStructured = structured && typeof structured === 'object' && Object.keys(structured).length > 0;

  return (
    <Drawer direction="right" open={open} onOpenChange={onClose} handleOnly={true}>
      <DrawerContent className="flex sm:min-w-sm md:min-w-md lg:min-w-lg">
        <DrawerHeader>
          <DrawerTitle>{node?.id}</DrawerTitle>
          {node?.properties?.entity_type && (
            <p className="text-sm text-muted-foreground">
              {String(node.properties.entity_type)}
            </p>
          )}
        </DrawerHeader>
        <div className="flex-1 overflow-auto p-4 select-text">
          <Markdown>{String(node?.properties?.description || '')}</Markdown>

          {hasStructured && (
            <>
              <Separator className="my-4" />
              <h4 className="text-sm font-medium mb-2">{page_graph('structured_properties')}</h4>
              <div className="grid gap-1 text-sm">
                {Object.entries(structured).map(([key, value]) => (
                  <div key={key} className="flex gap-2">
                    <span className="text-muted-foreground shrink-0">{key}:</span>
                    <span className="font-medium">{String(value ?? '-')}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </DrawerContent>
    </Drawer>
  );
};
