'use client';

import { ChatDetails, ChatMessage, Feedback, Reference } from '@/api';

import { useWebSocket } from 'ahooks';
import { animateScroll as scroll } from 'react-scroll';
import axios from 'axios';

import { Button } from '@/components/ui/button';
import { useBotContext } from '@/components/providers/bot-provider';
import { apiClient } from '@/lib/api/client';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { ReadyState } from 'ahooks/lib/useWebSocket';
import { motion } from 'framer-motion';
import _ from 'lodash';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ChatInput, ChatInputSubmitParams } from './chat-input';
import { MessagePartsAi } from './message-parts-ai';
import { MessagePartsUser } from './message-parts-user';

export const ChatMessages = ({
  chat,
  ontologyMode = false,
}: {
  chat: ChatDetails;
  ontologyMode?: boolean;
}) => {
  const { chatRename } = useBotContext();
  const { botId, chatId } = useParams<{ botId: string; chatId: string }>();
  const [messages, setMessages] = useState<Array<Array<ChatMessage>>>(
    chat?.history || [],
  );
  // const [messagesLoading, setMessagesLoading] = useState<boolean>(false);

  const [loading, setLoading] = useState<boolean>(false);
  const { protocol, host } = useMemo(() => {
    if (typeof window !== 'undefined') {
      return {
        protocol: window.location.protocol === 'http:' ? 'ws://' : 'wss://',
        host: window.location.host,
      };
    } else {
      return {
        protocol: 'ws://',
        host: 'localhost:8000',
      };
    }
  }, []);

  const { sendMessage, readyState, disconnect, connect } = useWebSocket(
    `${protocol}${host}${process.env.NEXT_PUBLIC_BASE_PATH || ''}/api/v1/bots/${botId}/chats/${chatId}/connect`,
    {
      onMessage: (message) => {
        const fragment = JSON.parse(message.data) as ChatMessage;
        if (fragment.type === 'start') {
          setLoading(true);
        }
        if (fragment.type === 'stop') {
          setLoading(false);
          if (chatRename && chat) {
            // Title generation is best-effort; never block or error the chat
            (async () => {
              try {
                await chatRename(chat);
              } catch {
                /* ignore title failures */
              }
            })();
          }
        }
        setMessages((msgs) => {
          const partsIndex = msgs.findLastIndex((parts) => {
            return Boolean(
              parts.find(
                (part) =>
                  part.id !== 'error' &&
                  part.id === fragment.id &&
                  part.role === 'ai',
              ),
            );
          });
          const parts = partsIndex > -1 ? msgs[partsIndex] : undefined;

          if (parts) {
            if (fragment.type === 'stop') {
              parts.push({
                id: fragment.id,
                type: 'references',
                references: Array.isArray(fragment.data)
                  ? (fragment.data as Reference[])
                  : [],
                data: '',
                role: 'ai',
              });
            }
            if (fragment.type === 'start') {
              parts.push({
                ...fragment,
                type: 'start',
                data: '',
              });
            } else if (fragment.type === 'message') {
              const part = parts.find((p) => p.type === 'message');
              if (part) {
                part.data = (part.data || '') + fragment.data;
              } else {
                parts.push(fragment);
              }
            } else if (fragment.type === 'thinking') {
              // Accumulate thinking chunks into the last thinking part (collapsible)
              const lastThinking = [...parts].reverse().find((p) => p.type === 'thinking');
              if (lastThinking) {
                lastThinking.data = (lastThinking.data || '') + fragment.data;
              } else {
                parts.push(fragment);
              }
            } else {
              const part = parts.find(
                (p) => fragment.part_id && fragment.part_id === p.part_id,
              );
              if (part) {
                part.data = (part.data || '') + fragment.data;
              } else {
                parts.push(fragment);
              }
            }
            msgs[partsIndex] = [...parts];
          } else {
            msgs.push([
              {
                ...fragment,
                role: 'ai',
              },
            ]);
          }
          return [...msgs];
        });
      },
    },
  );

  const handleSendMessage = useCallback(
    (params: ChatInputSubmitParams) => {
      const timestamp = Math.floor(new Date().getTime() / 1000);
      const part: ChatMessage = {
        type: 'message',
        role: 'human',
        data: params.query,
        timestamp,
      };
      setMessages((msgs) => {
        msgs?.push([part]);
        return [...msgs];
      });

      sendMessage(JSON.stringify(params));
    },
    [sendMessage],
  );

  const hanldeMessageFeedback = useCallback(
    async (part: ChatMessage, feedback: Feedback) => {
      if (!botId || !chatId || !part.id) return;
      const res =
        await apiClient.defaultApi.botsBotIdChatsChatIdMessagesMessageIdPost({
          botId,
          chatId,
          messageId: part.id,
          feedback,
        });
      if (res.status === 200) {
        setMessages((msgs) => {
          const parts = msgs.find((items) =>
            items.find((p) => p.id === part.id && p.type === 'references'),
          );
          const feedbackPart = parts?.find((p) => p.type === 'references');
          if (feedbackPart) {
            feedbackPart.feedback = feedback;
          }
          return [...msgs];
        });
      }
    },
    [botId, chatId],
  );

  const handleCancel = useCallback(() => {
    disconnect();
    connect();
    setLoading(false);
  }, [connect, disconnect]);

  useEffect(() => {
    if (loading) {
      scroll.scrollToBottom({ duration: 0 });
    }
  }, [messages, chat, loading]);

  useEffect(() => {
    scroll.scrollToBottom({ duration: 0 });
  }, []);

  /**
   * render in server for the first time
   * should delete for production
   */
  // const loadMessages = useCallback(async () => {
  //   setMessagesLoading(true);
  //   const res = await apiClient.defaultApi.botsBotIdChatsChatIdGet({
  //     botId,
  //     chatId,
  //   });
  //   setMessages(res.data.history || []);
  //   setMessagesLoading(false);
  // }, [botId, chatId]);

  // useEffect(() => {
  //   loadMessages();
  // }, [loadMessages]);

  return (
    <div className="flex flex-col gap-6 pb-70">
      {messages.map((parts, index) => {
        const isAI = parts.some((part) => part.role === 'ai');
        const isLoading = loading && index + 1 === messages.length;
        const isAIPending =
          isLoading &&
          parts.filter((p) => p.type !== 'start').length === 0 &&
          isAI;

        return (
          <motion.div
            key={index}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              duration: 0.3,
              ease: 'easeIn',
            }}
          >
            {isAI ? (
              <MessagePartsAi
                pending={isAIPending}
                loading={isLoading}
                parts={parts}
                hanldeMessageFeedback={hanldeMessageFeedback}
              />
            ) : (
              <MessagePartsUser parts={parts} />
            )}
            {ontologyMode && !loading && isAI && (
              <OwlDetectPanel parts={parts} />
            )}
          </motion.div>
        );
      })}
      <ChatInput
        chat={chat}
        welcome={_.isEmpty(messages)}
        onSubmit={handleSendMessage}
        disabled={readyState !== ReadyState.Open}
        loading={loading}
        onCancel={handleCancel}
        ontologyMode={ontologyMode}
      />
    </div>
  );
};

/** Detect ```owl code blocks in AI messages and offer save + Mermaid preview. */
function OwlDetectPanel({ parts }: { parts: ChatMessage[] }) {
  const t = useTranslations('page_ontologies');
  const [saving, setSaving] = useState(false);
  const fullText = parts
    .filter((p) => p.type === 'message')
    .map((p) => p.data || '')
    .join('');

  const owlMatch = fullText.match(/```owl\s*([\s\S]*?)```/);
  const mermaidMatch = fullText.match(/```mermaid\s*([\s\S]*?)```/);
  if (!owlMatch) return null;

  const owlCode = owlMatch[1];
  const mermaidCode = mermaidMatch ? mermaidMatch[1] : '';

  const handleSave = async () => {
    setSaving(true);
    try {
      const blob = new Blob([owlCode.trim()], { type: 'application/xml' });
      const fd = new FormData();
      fd.append('file', blob, `ontology-${Date.now()}.owl`);
      fd.append('title', `本体-${new Date().toLocaleDateString()}`);
      const basePath = process.env.NEXT_PUBLIC_BASE_PATH || '';
      await axios.post(`${basePath}/api/v1/ontologies`, fd);
      toast.success(t('saved_success'));
    } catch {
      toast.error('Save failed');
    }
    setSaving(false);
  };

  return (
    <div className="mt-4 rounded-lg border bg-muted/30 p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium">{t('owl_preview')}</span>
        <Button size="sm" onClick={handleSave} disabled={saving}>
          {t('save_ontology')}
        </Button>
      </div>
      {mermaidCode ? (
        <div className="overflow-auto rounded bg-white/60 p-2">
          <MermaidPreview code={mermaidCode} />
        </div>
      ) : (
        <pre className="max-h-64 overflow-auto rounded bg-background p-2 text-xs">
          {owlCode.trim().slice(0, 2000)}
        </pre>
      )}
    </div>
  );
}

function MermaidPreview({ code }: { code: string }) {
  const [svg, setSvg] = useState('');
  const [id] = useState(() => 'mp-' + String(Math.floor(Math.random() * 100000)));
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const { default: mermaid } = await import('mermaid');
      mermaid.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'loose' });
      try {
        const r = await mermaid.render(id, code);
        if (!cancelled) setSvg(r.svg);
      } catch {
        /* invalid mermaid */
      }
    })();
    return () => { cancelled = true; };
  }, [code, id]);
  if (!svg) return <p className="text-xs text-muted-foreground">...</p>;
  return <div dangerouslySetInnerHTML={{ __html: svg }} />;
}
