import { useId } from "react";

interface Props {
  size?: number;
  /** Draw the brackets and let the spark arrive. Calm, and off for reduced motion (see styles). */
  animate?: boolean;
}

/** The DocMind mark: citation brackets, a folded page corner, and the spark of the answer. */
export function BrandMark({ size = 72, animate = true }: Props) {
  const gradient = useId();
  return (
    <svg
      className="brand-mark"
      data-animate={animate}
      width={size}
      height={size}
      viewBox="0 0 120 120"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#2BE4FF" />
          <stop offset="1" stopColor="#7C5CFF" />
        </linearGradient>
      </defs>
      <path
        className="bm-b"
        pathLength={1}
        d="M42 15 H23 V105 H42"
        stroke={`url(#${gradient})`}
        strokeWidth={11}
      />
      <path
        className="bm-b"
        pathLength={1}
        d="M78 15 H84 L98 29 V105 H78"
        stroke={`url(#${gradient})`}
        strokeWidth={11}
      />
      <path
        className="bm-b"
        pathLength={1}
        d="M84 15 V29 H98"
        stroke={`url(#${gradient})`}
        strokeWidth={8.8}
      />
      <path
        className="bm-spark"
        fill="#FFB21E"
        d="M60 35 C61.6 52.5 67.5 58.4 85 60 C67.5 61.6 61.6 67.5 60 85 C58.4 67.5 52.5 61.6 35 60 C52.5 58.4 58.4 52.5 60 35 Z"
      />
    </svg>
  );
}
