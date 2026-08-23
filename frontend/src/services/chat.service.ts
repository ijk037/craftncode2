import apiClient from "@/lib/axios";
import type { ApiSuccessResponse } from "@/types";
import type { ChatMessage, LanguageCode, TranscribeResult } from "@/types/chat";

const BASE = "/api/v1/chat";

export const chatService = {
  async ask(message: string): Promise<ApiSuccessResponse<ChatMessage>> {
    const res = await apiClient.post<ApiSuccessResponse<ChatMessage>>(`${BASE}/ask`, { message });
    return res.data;
  },

  async getHistory(skip = 0, limit = 50): Promise<ApiSuccessResponse<ChatMessage[]>> {
    const res = await apiClient.get<ApiSuccessResponse<ChatMessage[]>>(`${BASE}/history`, {
      params: { skip, limit },
    });
    return res.data;
  },

  /** Speech-to-text: upload a recorded audio blob, get back the transcribed text. */
  async transcribe(audioBlob: Blob): Promise<ApiSuccessResponse<TranscribeResult>> {
    const form = new FormData();
    form.append("audio", audioBlob, "recording.webm");
    const res = await apiClient.post<ApiSuccessResponse<TranscribeResult>>(
      `${BASE}/transcribe`,
      form,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
    return res.data;
  },

  /** Text-to-speech: get back playable MP3 audio for a piece of text. */
  async speak(text: string, language: LanguageCode): Promise<Blob> {
    const res = await apiClient.post(
      `${BASE}/speak`,
      { text, language },
      { responseType: "blob" },
    );
    return res.data as Blob;
  },
};
