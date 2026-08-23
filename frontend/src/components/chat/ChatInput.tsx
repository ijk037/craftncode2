"use client";

import { useState } from "react";
import { Mic, Square, Send, Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { showToast } from "@/components/ui/toast-utils";
import { useVoiceRecorder } from "@/hooks/use-voice-recorder";
import { useTranscribe } from "@/hooks/use-chat";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const t = useTranslations("chat");
  const [text, setText] = useState("");
  const recorder = useVoiceRecorder();
  const transcribeMutation = useTranscribe();

  const isTranscribing = transcribeMutation.isPending;
  const isBusy = disabled || isTranscribing;

  function handleSend() {
    const trimmed = text.trim();
    if (!trimmed || isBusy) return;
    onSend(trimmed);
    setText("");
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  async function handleMicClick() {
    if (recorder.isRecording) {
      const blob = await recorder.stop();
      recorder.reset();
      if (!blob) return;
      transcribeMutation.mutate(blob, {
        onSuccess: (res) => {
          const transcribed = res.data?.text ?? "";
          if (transcribed) {
            setText((prev) => (prev ? `${prev} ${transcribed}` : transcribed));
          } else {
            showToast(t("voice_no_speech_detected"), "info");
          }
        },
        onError: () => showToast(t("voice_transcribe_error"), "error"),
      });
      return;
    }

    await recorder.start();
    if (recorder.error) {
      showToast(recorder.error, "error");
    }
  }

  return (
    <div className="border-t bg-background p-4">
      <div className="flex items-end gap-2">
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            recorder.isRecording
              ? t("listening")
              : isTranscribing
                ? t("transcribing")
                : t("input_placeholder")
          }
          disabled={isBusy}
          rows={1}
          className="min-h-[44px] max-h-32 resize-none"
        />

        {recorder.isSupported && (
          <Button
            type="button"
            variant={recorder.isRecording ? "destructive" : "outline"}
            size="icon"
            className={cn("shrink-0", recorder.isRecording && "animate-pulse")}
            disabled={disabled || isTranscribing}
            title={recorder.isRecording ? t("stop_recording") : t("start_recording")}
            onClick={handleMicClick}
          >
            {isTranscribing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : recorder.isRecording ? (
              <Square className="h-4 w-4" />
            ) : (
              <Mic className="h-4 w-4" />
            )}
          </Button>
        )}

        <Button
          type="button"
          size="icon"
          className="shrink-0"
          disabled={isBusy || !text.trim()}
          title={t("send")}
          onClick={handleSend}
        >
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
