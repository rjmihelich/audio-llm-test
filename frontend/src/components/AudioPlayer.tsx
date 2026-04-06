import { useRef, useState } from "react";

interface AudioPlayerProps {
  url: string;
}

export default function AudioPlayer({ url }: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState<number | null>(null);
  const [currentTime, setCurrentTime] = useState(0);

  function toggle() {
    const el = audioRef.current;
    if (!el) return;
    if (playing) {
      el.pause();
    } else {
      el.play();
    }
    setPlaying(!playing);
  }

  function formatTime(s: number): string {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, "0")}`;
  }

  return (
    <div className="flex items-center gap-3 bg-gray-50 rounded-lg px-4 py-3 border border-gray-200">
      <audio
        ref={audioRef}
        src={url}
        onLoadedMetadata={() => setDuration(audioRef.current?.duration ?? null)}
        onTimeUpdate={() => setCurrentTime(audioRef.current?.currentTime ?? 0)}
        onEnded={() => setPlaying(false)}
      />

      <button
        onClick={toggle}
        className="w-9 h-9 flex items-center justify-center rounded-full bg-slate-800 text-white hover:bg-slate-700 transition-colors text-sm shrink-0"
      >
        {playing ? "\u23F8" : "\u25B6"}
      </button>

      {/* Waveform placeholder */}
      <div className="flex-1 h-8 bg-gray-200 rounded-md flex items-center justify-center relative overflow-hidden">
        <div
          className="absolute left-0 top-0 bottom-0 bg-slate-300 transition-all"
          style={{
            width: duration ? `${(currentTime / duration) * 100}%` : "0%",
          }}
        />
        <span className="relative text-xs text-gray-500">waveform</span>
      </div>

      <span className="text-xs text-gray-500 tabular-nums shrink-0">
        {formatTime(currentTime)}
        {duration !== null && ` / ${formatTime(duration)}`}
      </span>
    </div>
  );
}
