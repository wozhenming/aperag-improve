import { serverRequest } from '@/lib/api/server';
import { permanentRedirect, redirect } from 'next/navigation';

export const dynamic = 'force-dynamic';

export default async function Page() {
  let botId: string | undefined;
  let chatId: string | undefined;
  try {
    const res = await serverRequest.post('/ontologies/bot/session');
    botId = res.data?.bot_id;
    chatId = res.data?.chat_id;
  } catch {
    // bot/session failed — fall through to the library page
  }

  if (botId && chatId) {
    // redirect() throws internally; must be called OUTSIDE the try/catch
    redirect(`/workspace/bots/${botId}/chats/${chatId}?ontology=1`);
  }
  permanentRedirect('/workspace/ontologies');
}
