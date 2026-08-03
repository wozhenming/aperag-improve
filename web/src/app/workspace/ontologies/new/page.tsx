import { serverRequest } from '@/lib/api/server';
import { redirect } from 'next/navigation';

export const dynamic = 'force-dynamic';

export default async function Page() {
  try {
    // Get or create the Ontology Engineer bot + a fresh chat
    // (SDK not regenerated yet — call via raw axios)
    const res = await serverRequest.post('/ontologies/bot/session');
    const { bot_id, chat_id } = res.data || {};
    if (bot_id && chat_id) {
      redirect(`/workspace/bots/${bot_id}/chats/${chat_id}?ontology=1`);
    }
  } catch {
    /* fall through */
  }
  redirect('/workspace/ontologies');
}
