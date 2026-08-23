export type LanguageCode =
  | "en"
  | "hi"
  | "ta"
  | "te"
  | "bn"
  | "mr"
  | "gu"
  | "kn"
  | "ml"
  | "pa"
  | "or"
  | "as"
  | "ur";

/** Languages gTTS (Google Translate TTS) has no voice for — speak is disabled for these. */
export const TTS_UNSUPPORTED_LANGUAGES: readonly LanguageCode[] = ["or", "as"];

export const LANGUAGE_NAMES: Record<LanguageCode, string> = {
  en: "English",
  hi: "Hindi",
  ta: "Tamil",
  te: "Telugu",
  bn: "Bengali",
  mr: "Marathi",
  gu: "Gujarati",
  kn: "Kannada",
  ml: "Malayalam",
  pa: "Punjabi",
  or: "Odia",
  as: "Assamese",
  ur: "Urdu",
};

export interface ChatMessage {
  id: string;
  user_id: string;
  question: string;
  answer: string;
  language: LanguageCode;
  created_at: string;
  updated_at: string;
}

export interface TranscribeResult {
  text: string;
  detected_language: string;
}
