"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { chatService } from "@/services/chat.service";
import type { LanguageCode } from "@/types/chat";

export const CHAT_KEYS = {
  history: ["chat", "history"] as const,
};

export function useChatHistory() {
  return useQuery({
    queryKey: CHAT_KEYS.history,
    queryFn: () => chatService.getHistory(),
    staleTime: 1000 * 60,
  });
}

export function useAskChat() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (message: string) => chatService.ask(message),
    onSuccess: () => qc.invalidateQueries({ queryKey: CHAT_KEYS.history }),
  });
}

/** Speech-to-text: upload a recorded clip, get the transcribed text back. */
export function useTranscribe() {
  return useMutation({
    mutationFn: (audioBlob: Blob) => chatService.transcribe(audioBlob),
  });
}

/** Text-to-speech: get playable MP3 audio for a piece of text. */
export function useSpeak() {
  return useMutation({
    mutationFn: ({ text, language }: { text: string; language: LanguageCode }) =>
      chatService.speak(text, language),
  });
}
