"use client";

/**
 * useAudioPlayer — plays one Blob at a time, tracked by an arbitrary `id`
 * (e.g. a chat message id) so a UI can show which item is currently speaking.
 * Starting a new playback stops whatever was playing before.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export function useAudioPlayer() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);
  const [playingId, setPlayingId] = useState<string | null>(null);

  const stop = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.onended = null;
    }
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    }
    audioRef.current = null;
    setPlayingId(null);
  }, []);

  const play = useCallback(
    (id: string, blob: Blob) => {
      stop();
      const url = URL.createObjectURL(blob);
      urlRef.current = url;
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => stop();
      setPlayingId(id);
      void audio.play();
    },
    [stop],
  );

  useEffect(() => stop, [stop]);

  return { playingId, play, stop };
}
