"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, MessageCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import { showToast } from "@/components/ui/toast-utils";
import { useAskChat, useChatHistory, useSpeak } from "@/hooks/use-chat";
import { useAudioPlayer } from "@/hooks/use-audio-player";
import type { ChatMessage } from "@/types/chat";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";

export function ChatWindow() {
  const t = useTranslations("chat");
  const { data: historyRes, isLoading } = useChatHistory();
  const askMutation = useAskChat();
  const speakMutation = useSpeak();
  const audioPlayer = useAudioPlayer();
  const [loadingSpeechId, setLoadingSpeechId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  // History comes back newest-first from the API; render oldest-first.
  const messages: ChatMessage[] = [...(historyRes?.data ?? [])].reverse();

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, askMutation.isPending]);

  function handleSend(question: string) {
    askMutation.mutate(question, {
      onError: () => showToast(t("ask_error"), "error"),
    });
  }

  function handleSpeak(message: ChatMessage) {
    setLoadingSpeechId(message.id);
    speakMutation.mutate(
      { text: message.answer, language: message.language },
      {
        onSuccess: (blob) => {
          setLoadingSpeechId(null);
          audioPlayer.play(message.id, blob);
        },
        onError: () => {
          setLoadingSpeechId(null);
          showToast(t("voice_speak_error"), "error");
        },
      },
    );
  }

  return (
    <div className="flex h-[calc(100vh-8.5rem)] flex-col rounded-xl border bg-background">
      <div className="flex-1 overflow-y-auto p-4">
        {isLoading ? (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        ) : messages.length === 0 && !askMutation.isPending ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-muted-foreground">
            <MessageCircle className="h-8 w-8" />
            <p className="text-sm">{t("empty_state")}</p>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((m) => (
              <MessageBubble
                key={m.id}
                message={m}
                isSpeaking={audioPlayer.playingId === m.id}
                isLoadingSpeech={loadingSpeechId === m.id}
                onSpeak={handleSpeak}
                onStopSpeaking={audioPlayer.stop}
              />
            ))}
            {askMutation.isPending && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                {t("thinking")}
              </div>
            )}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <ChatInput onSend={handleSend} disabled={askMutation.isPending} />
    </div>
  );
}
