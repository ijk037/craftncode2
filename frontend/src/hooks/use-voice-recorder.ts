"use client";

/**
 * useVoiceRecorder — thin wrapper around the browser MediaRecorder API.
 * Requests the mic on start(), returns a playable audio Blob on stop().
 * Purely client-side — no dependency on any particular backend.
 */

import { useCallback, useRef, useState } from "react";

export type RecorderStatus = "idle" | "requesting" | "recording" | "stopped" | "error";

export function useVoiceRecorder() {
  const [status, setStatus] = useState<RecorderStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  const isSupported =
    typeof window !== "undefined" &&
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== "undefined";

  const start = useCallback(async () => {
    if (!isSupported) {
      setError("Voice input isn't supported in this browser.");
      setStatus("error");
      return;
    }
    setError(null);
    setStatus("requesting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setStatus("recording");
    } catch {
      setError("Microphone access was denied.");
      setStatus("error");
    }
  }, [isSupported]);

  const stop = useCallback((): Promise<Blob | null> => {
    return new Promise((resolve) => {
      const recorder = mediaRecorderRef.current;
      if (!recorder || recorder.state === "inactive") {
        resolve(null);
        return;
      }
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        setStatus("stopped");
        resolve(blob.size > 0 ? blob : null);
      };
      recorder.stop();
    });
  }, []);

  const reset = useCallback(() => {
    setStatus("idle");
    setError(null);
  }, []);

  return {
    status,
    error,
    isSupported,
    isRecording: status === "recording",
    start,
    stop,
    reset,
  };
}
