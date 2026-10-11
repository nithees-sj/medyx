"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { fmtInstant } from "@/lib/format";
import { SERIES_COLORS } from "@/lib/chart-colors";

type Series = { key: string; label: string; color: string };

/** Count-per-period lines on one axis (all series share the unit "events"). Legend always shown,
 * crosshair tooltip on hover, and a screen-reader table with the same numbers. */
function CountLines({
  data,
  xKey,
  series,
  xFormat,
  tooltipFormat,
  caption,
  height = 220,
}: {
  data: Record<string, string | number>[];
  xKey: string;
  series: Series[];
  xFormat: (v: string) => string;
  tooltipFormat: (v: string) => string;
  caption: string;
  height?: number;
}) {
  const totals = Object.fromEntries(series.map((s) => [s.key, data.reduce((n, d) => n + Number(d[s.key] || 0), 0)]));
  return (
    <figure className="space-y-3">
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs" aria-hidden>
        {series.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <span className="h-0.5 w-4 rounded-full" style={{ background: s.color }} />
            <span className="text-muted-foreground">{s.label}</span>
            <span className="font-medium tabular-nums">{totals[s.key].toLocaleString("en-IN")}</span>
          </li>
        ))}
      </ul>
      <div style={{ height }} aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis
              dataKey={xKey}
              tickFormatter={xFormat}
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              tickLine={false}
              axisLine={{ stroke: "var(--border)" }}
              minTickGap={24}
            />
            <YAxis
              allowDecimals={false}
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              tickLine={false}
              axisLine={false}
              width={44}
            />
            <Tooltip
              cursor={{ stroke: "var(--muted-foreground)", strokeDasharray: "3 3" }}
              content={({ active, payload, label }) =>
                active && payload?.length ? (
                  <div className="rounded-lg border bg-popover px-3 py-2 text-xs shadow-md">
                    <p className="mb-1 font-medium">{tooltipFormat(String(label))}</p>
                    {series.map((s) => (
                      <p key={s.key} className="flex items-center gap-2">
                        <span className="size-2 rounded-full" style={{ background: s.color }} />
                        <span className="flex-1 text-muted-foreground">{s.label}</span>
                        <span className="font-medium tabular-nums">
                          {Number(payload.find((p) => p.dataKey === s.key)?.value ?? 0).toLocaleString("en-IN")}
                        </span>
                      </p>
                    ))}
                  </div>
                ) : null
              }
            />
            {series.map((s) => (
              <Line
                key={s.key}
                dataKey={s.key}
                stroke={s.color}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, stroke: "var(--card)", strokeWidth: 2 }}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="sr-only">{caption}</figcaption>
      <table className="sr-only">
        <thead>
          <tr>
            <th>Period</th>
            {series.map((s) => (
              <th key={s.key}>{s.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((d) => (
            <tr key={String(d[xKey])}>
              <td>{tooltipFormat(String(d[xKey]))}</td>
              {series.map((s) => (
                <td key={s.key}>{d[s.key]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

export function DailyActivityChart({
  data,
}: {
  data: { date: string; sign_ins: number; uploads: number; doctor_access: number; ai_calls: number }[];
}) {
  return (
    <CountLines
      data={data}
      xKey="date"
      xFormat={(d) => fmtInstant(`${d}T12:00:00Z`, "d MMM")}
      tooltipFormat={(d) => fmtInstant(`${d}T12:00:00Z`, "EEE d MMM")}
      caption="Daily platform activity over the last 14 days"
      series={[
        { key: "sign_ins", label: "Sign-ins", color: SERIES_COLORS[0] },
        { key: "uploads", label: "Documents uploaded", color: SERIES_COLORS[1] },
        { key: "doctor_access", label: "Doctor record access", color: SERIES_COLORS[2] },
        { key: "ai_calls", label: "AI calls", color: SERIES_COLORS[3] },
      ]}
    />
  );
}

export function TrafficChart({
  data,
  hourly,
}: {
  data: { at: string; requests: number; server_errors: number }[];
  hourly: boolean;
}) {
  return (
    <CountLines
      data={data}
      xKey="at"
      xFormat={(t) => fmtInstant(t, hourly ? "h a" : "d MMM")}
      tooltipFormat={(t) => fmtInstant(t, hourly ? "d MMM, h a" : "EEE d MMM")}
      caption="API requests and server errors over time"
      height={200}
      series={[
        { key: "requests", label: "Requests", color: SERIES_COLORS[0] },
        // Status colour: errors are a state, not a category.
        { key: "server_errors", label: "Server errors (5xx)", color: "var(--critical)" },
      ]}
    />
  );
}
