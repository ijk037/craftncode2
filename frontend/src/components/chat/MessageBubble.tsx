"use client";

import { Volume2, Loader2, VolumeX } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { LANGUAGE_NAMES, TTS_UNSUPPORTED_LANGUAGES, type ChatMessage } from "@/types/chat";

interface MessageBubbleProps {
  message: ChatMessage;
  isSpeaking: boolean;
  isLoadingSpeech: boolean;
  onSpeak: (message: ChatMessage) => void;
  onStopSpeaking: () => void;
}

export function MessageBubble({
  message,
  isSpeaking,
  isLoadingSpeech,
  onSpeak,
  onStopSpeaking,
}: MessageBubbleProps) {
  const t = useTranslations("chat");
  const speechAvailable = !TTS_UNSUPPORTED_LANGUAGES.includes(message.language);

  return (
    <div className="space-y-2">
      {/* User question */}
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground">
          {message.question}
        </div>
      </div>

      {/* AI answer */}
      <div className="flex justify-start">
        <div className="flex max-w-[80%] items-end gap-2">
          <div className="rounded-2xl rounded-bl-sm border bg-card px-4 py-2.5 text-sm text-card-foreground whitespace-pre-wrap">
            {message.answer}
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className={cn("h-8 w-8 shrink-0", !speechAvailable && "opacity-40")}
            disabled={!speechAvailable || isLoadingSpeech}
            title={
              speechAvailable
                ? t("speak_answer")
                : t("speak_unavailable", { language: LANGUAGE_NAMES[message.language] })
            }
            onClick={() => (isSpeaking ? onStopSpeaking() : onSpeak(message))}
          >
            {isLoadingSpeech ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : isSpeaking ? (
              <VolumeX className="h-4 w-4" />
            ) : (
              <Volume2 className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
