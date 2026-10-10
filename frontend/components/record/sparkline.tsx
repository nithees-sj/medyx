"use client";

import { Line, LineChart, ResponsiveContainer, YAxis } from "recharts";

/** Tiny trend line. Single series, so no legend; the label carries the numbers. */
export function Sparkline({
  points,
  label,
  tone = "neutral",
  width = 96,
  height = 28,
}: {
  points: { date: string; value: number }[];
  label: string;
  tone?: "neutral" | "warning";
  width?: number;
  height?: number;
}) {
  if (points.length < 2) return <span className="text-xs text-muted-foreground">—</span>;
  const stroke = tone === "warning" ? "var(--warning)" : "var(--primary)";
  return (
    <span className="inline-flex items-center gap-2" role="img" aria-label={label} title={label}>
      <span style={{ width, height }} className="inline-block">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 3, right: 3, bottom: 3, left: 3 }}>
            <YAxis hide domain={["dataMin", "dataMax"]} />
            <Line
              dataKey="value"
              stroke={stroke}
              strokeWidth={2}
              isAnimationActive={false}
              dot={(p: { cx?: number; cy?: number; index?: number }) =>
                p.index === points.length - 1 ? <circle key="last" cx={p.cx} cy={p.cy} r={3} fill={stroke} /> : <g key={p.index} />
              }
            />
          </LineChart>
        </ResponsiveContainer>
      </span>
      <span className="text-xs tabular-nums text-muted-foreground">
        {points[0].value}→{points[points.length - 1].value}
      </span>
    </span>
  );
}
