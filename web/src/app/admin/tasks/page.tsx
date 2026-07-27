import {
  PageContainer,
  PageContent,
  PageHeader,
  PageTitle,
  PageDescription,
} from '@/components/page-container';
import { Metadata } from 'next';
import { getTranslations } from 'next-intl/server';

export async function generateMetadata(): Promise<Metadata> {
  const page_tasks = await getTranslations('page_tasks');
  return {
    title: page_tasks('metadata.title'),
    description: page_tasks('metadata.description'),
  };
}

export default async function Page() {
  const page_tasks = await getTranslations('page_tasks');
  const flowerUrl = process.env.NEXT_PUBLIC_FLOWER_URL || 'http://localhost:5555';

  return (
    <PageContainer>
      <PageHeader breadcrumbs={[{ title: page_tasks('metadata.title') }]} />
      <PageContent>
        <PageTitle>{page_tasks('metadata.title')}</PageTitle>
        <PageDescription className="mb-4">
          {page_tasks('metadata.description')}
        </PageDescription>

        <div className="h-[calc(100vh-12rem)] rounded-lg border overflow-hidden">
          <iframe
            src={flowerUrl}
            className="w-full h-full border-0"
            title={page_tasks('metadata.title')}
          />
        </div>
      </PageContent>
    </PageContainer>
  );
}
