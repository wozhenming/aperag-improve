import {
  PageContainer,
  PageContent,
  PageDescription,
  PageHeader,
  PageTitle,
} from '@/components/page-container';
import { serverRequest } from '@/lib/api/server';
import { toJson } from '@/lib/utils';
import { Metadata } from 'next';
import { getTranslations } from 'next-intl/server';
import { OntologyList } from './ontology-list';

export const dynamic = 'force-dynamic';

export async function generateMetadata(): Promise<Metadata> {
  const page_ontologies = await getTranslations('page_ontologies');
  return {
    title: page_ontologies('metadata.title'),
    description: page_ontologies('metadata.description'),
  };
}

export default async function Page() {
  const page_ontologies = await getTranslations('page_ontologies');

  let items: any[] = [];
  try {
    const res = await serverRequest.get('/ontologies');
    items = res.data?.items || [];
  } catch (err) {
    console.log(err);
  }

  return (
    <PageContainer>
      <PageHeader breadcrumbs={[{ title: page_ontologies('metadata.title') }]} />
      <PageContent>
        <PageTitle>{page_ontologies('metadata.title')}</PageTitle>
        <PageDescription>{page_ontologies('metadata.description')}</PageDescription>
        <OntologyList ontologies={toJson(items)} />
      </PageContent>
    </PageContainer>
  );
}
