"use client";

import { ArrowDownRight, ArrowRight, ArrowUpRight, LineChart as LineChartIcon, TrendingDown, TrendingUp } from "lucide-react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { OrgDot, OrgLegend } from "@/components/record/org-chip";
import { useDocumentViewer } from "@/components/record/viewer-context";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fmtDate } from "@/lib/format";
import { orgColor, useTrends } from "@/lib/hooks/record";
import type { Analyte, ObservationPoint, OrgColors } from "@/lib/record-types";
import { cn } from "@/lib/utils";

const DAY = 86_400_000;

type Pt = { x: number; y: number; point: ObservationPoint; color: string };

function fmtValue(v: number, decimals: number) {
  return v.toFixed(decimals);
}

/** Round the y-domain outward to "nice" steps (1, 2, 2.5, 5 × 10^n) so ticks read cleanly. */
function niceTicks(min: number, max: number, count = 5): number[] {
  const raw = (max - min) / Math.max(1, count - 1) || 1;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = ([1, 2, 2.5, 5, 10].find((m) => m * mag >= raw) ?? 10) * mag;
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Number(v.toFixed(6)));
  return ticks;
}

export function TrendsView({ profileId, emptyAction }: { profileId: string; emptyAction?: React.ReactNode }) {
  const { data, isLoading, isError, error, refetch } = useTrends(profileId);
  if (isLoading) return <LoadingState rows={3} />;
  if (isError) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (!data?.analytes.length)
    return (
      <EmptyState
        icon={LineChartIcon}
        title="No lab results yet"
        description="Upload lab reports from any lab. The same test is merged into one trend, even when names and units differ."
        action={emptyAction}
      />
    );
  const drifting = data.analytes.filter((a) => a.drift);
  const rest = data.analytes.filter((a) => !a.drift);
  return (
    <div className="space-y-4">
      <OrgLegend colors={data.org_colors} />
      <div className="grid gap-4 lg:grid-cols-2">
        {[...drifting, ...rest].map((a) => (
          <AnalyteCard key={a.loinc} analyte={a} colors={data.org_colors} />
        ))}
      </div>
    </div>
  );
}

function TrendArrow({ analyte }: { analyte: Analyte }) {
  const pts = analyte.points;
  if (pts.length < 2) return null;
  const a = pts[pts.length - 2].value ?? 0;
  const b = pts[pts.length - 1].value ?? 0;
  const pct = a ? ((b - a) / Math.abs(a)) * 100 : 0;
  const Icon = Math.abs(pct) < 2 ? ArrowRight : pct > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <span className="inline-flex items-center gap-0.5 text-xs text-muted-foreground" title="Change since previous result">
      <Icon className="size-3.5" />
      {pct > 0 ? "+" : ""}
      {pct.toFixed(0)}%
    </span>
  );
}

export function AnalyteCard({ analyte: a, colors }: { analyte: Analyte; colors: OrgColors }) {
  const viewer = useDocumentViewer();
  const pts: Pt[] = a.points
    .filter((p) => p.value != null && p.date)
    .map((p) => ({ x: Date.parse(p.date as string), y: p.value as number, point: p, color: orgColor(colors, p.org) }));
  const drift = a.drift;
  const fitted = drift?.fitted.map((d) => ({ x: Date.parse(d.date), y: d.value })) ?? [];
  const projection = drift?.projection.map((d) => ({ x: Date.parse(d.date), y: d.value })) ?? [];

  const xs = [...pts.map((p) => p.x), ...projection.map((p) => p.x)];
  const xMin = Math.min(...xs) - 30 * DAY;
  const xMax = Math.max(...xs) + 30 * DAY;
  const ys = [
    ...pts.map((p) => p.y),
    ...projection.map((p) => p.y),
    ...(a.ref_low != null ? [a.ref_low] : []),
    ...(a.ref_high != null ? [a.ref_high] : []),
    ...(drift ? [drift.threshold] : []),
  ];
  const span = Math.max(...ys) - Math.min(...ys) || 1;
  const yTicks = niceTicks(Math.max(0, Math.min(...ys) - span * 0.1), Math.max(...ys) + span * 0.1);
  const yMin = yTicks[0];
  const yMax = yTicks[yTicks.length - 1];
  const tickDecimals = yTicks.some((t) => !Number.isInteger(t)) ? (yTicks.some((t) => !Number.isInteger(t * 10)) ? 2 : 1) : 0;
  const latest = a.latest;
  const abnormal = latest.interpretation === "H" || latest.interpretation === "L";

  return (
    <Card className={cn(drift && "border-warning/50")}>
      <CardHeader className="pb-0">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="text-base">{a.name}</CardTitle>
            <p className="truncate text-xs text-muted-foreground">
              LOINC {a.loinc} · {a.count} result{a.count === 1 ? "" : "s"} from{" "}
              {new Set(a.points.map((p) => p.org)).size} source{new Set(a.points.map((p) => p.org)).size === 1 ? "" : "s"}
            </p>
          </div>
          <div className="text-right">
            <p className="text-lg leading-tight font-semibold">
              {latest.value != null ? fmtValue(latest.value, a.decimals) : "—"}{" "}
              <span className="text-xs font-normal text-muted-foreground">{a.unit}</span>
            </p>
            <div className="flex items-center justify-end gap-2">
              <TrendArrow analyte={a} />
              {abnormal && (
                <Badge variant="outline" className="border-warning/50 text-[10px]">
                  {latest.interpretation === "H" ? "above range" : "below range"}
                </Badge>
              )}
            </div>
          </div>
        </div>
        {drift && (
          <div className="mt-2 flex items-start gap-2 rounded-lg bg-warning-soft px-3 py-2 text-xs">
            {drift.slope_per_year < 0 ? (
              <TrendingDown className="mt-0.5 size-4 shrink-0 text-warning" />
            ) : (
              <TrendingUp className="mt-0.5 size-4 shrink-0 text-warning" />
            )}
            <span>
              <span className="font-medium">Steady drift across labs:</span> {drift.slope_per_year > 0 ? "+" : ""}
              {drift.slope_per_year.toFixed(a.decimals >= 1 ? 2 : 1)} {a.unit} per year.
              {drift.projected_cross_date
                ? ` Projected to cross ${drift.threshold_label} around ${fmtDate(drift.projected_cross_date, "MMM yyyy")}.`
                : ""}
            </span>
          </div>
        )}
      </CardHeader>
      <CardContent className="pt-3">
        <div className="h-56" role="img" aria-label={`${a.name} trend chart`}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
              <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="0" />
              <XAxis
                dataKey="x"
                type="number"
                scale="time"
                domain={[xMin, xMax]}
                tickFormatter={(v) => fmtDate(new Date(v).toISOString(), "MMM yyyy")}
                tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                axisLine={{ stroke: "var(--border)" }}
                tickLine={false}
                minTickGap={24}
              />
              <YAxis
                dataKey="y"
                type="number"
                domain={[yMin, yMax]}
                tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                axisLine={false}
                tickLine={false}
                width={44}
                ticks={yTicks}
                tickFormatter={(v: number) => v.toFixed(tickDecimals)}
              />
              {(a.ref_low != null || a.ref_high != null) && (
                <ReferenceArea
                  y1={a.ref_low ?? yMin}
                  y2={a.ref_high ?? yMax}
                  fill="var(--success)"
                  fillOpacity={0.08}
                  stroke="none"
                  ifOverflow="hidden"
                />
              )}
              {drift && (
                <ReferenceLine
                  y={drift.threshold}
                  stroke="var(--warning)"
                  strokeDasharray="4 4"
                  label={{ value: drift.threshold_label, position: "insideBottomLeft", fontSize: 10, fill: "var(--muted-foreground)" }}
                />
              )}
              <Tooltip content={<PointTooltip unit={a.unit} decimals={a.decimals} />} cursor={{ stroke: "var(--border)" }} />
              <Line
                data={pts}
                dataKey="y"
                stroke="var(--muted-foreground)"
                strokeOpacity={0.5}
                strokeWidth={2}
                isAnimationActive={false}
                dot={(props: { cx?: number; cy?: number; payload?: Pt; index?: number }) => (
                  <circle
                    key={props.index}
                    cx={props.cx}
                    cy={props.cy}
                    r={5}
                    fill={props.payload?.color}
                    stroke="var(--card)"
                    strokeWidth={2}
                    className="cursor-pointer"
                    onClick={() => {
                      const s = props.payload?.point.sources[0];
                      if (s) viewer.open({ documentId: s.document_id, page: s.page, snippet: s.snippet, title: `${s.doc_label} · page ${s.page}` });
                    }}
                  />
                )}
                activeDot={{ r: 7, stroke: "var(--card)", strokeWidth: 2 }}
              />
              {drift && (
                <Line data={fitted} dataKey="y" stroke="var(--warning)" strokeWidth={2} dot={false} isAnimationActive={false} />
              )}
              {drift && projection.length > 0 && (
                <Line
                  data={projection}
                  dataKey="y"
                  stroke="var(--warning)"
                  strokeWidth={2}
                  strokeDasharray="6 5"
                  dot={false}
                  isAnimationActive={false}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <details className="mt-2 text-sm">
          <summary className="cursor-pointer text-xs text-muted-foreground select-none">Show values as a table</summary>
          <table className="mt-2 w-full text-xs">
            <thead className="text-muted-foreground">
              <tr className="text-left">
                <th className="py-1 font-medium">Date</th>
                <th className="py-1 font-medium">Value</th>
                <th className="py-1 font-medium">As written</th>
                <th className="py-1 font-medium">Source</th>
              </tr>
            </thead>
            <tbody>
              {a.points.map((p) => (
                <tr key={p.ref} className="border-t">
                  <td className="py-1">{fmtDate(p.date)}</td>
                  <td className="py-1 font-medium">
                    {p.value != null ? fmtValue(p.value, a.decimals) : "—"} {a.unit}
                  </td>
                  <td className="py-1">{p.written_text ?? p.value_text}</td>
                  <td className="py-1">
                    <span className="inline-flex items-center gap-1">
                      <OrgDot color={orgColor(colors, p.org)} /> {p.org}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </CardContent>
    </Card>
  );
}

function PointTooltip({
  active,
  payload,
  unit,
  decimals,
}: {
  active?: boolean;
  payload?: { payload: Pt | { x: number; y: number } }[];
  unit: string;
  decimals: number;
}) {
  const p = payload?.find((e) => "point" in e.payload)?.payload as Pt | undefined;
  if (!active || !p) return null;
  return (
    <div className="rounded-lg border bg-popover px-3 py-2 text-xs shadow-md">
      <p className="font-medium">
        {fmtValue(p.y, decimals)} {unit}
        {p.point.written_text && p.point.written_text !== `${fmtValue(p.y, decimals)} ${unit}` && (
          <span className="font-normal text-muted-foreground"> (written as {p.point.written_text})</span>
        )}
      </p>
      <p className="text-muted-foreground">{fmtDate(p.point.date)}</p>
      <p className="mt-1 flex items-center gap-1.5">
        <OrgDot color={p.color} /> {p.point.org}
      </p>
      <p className="mt-1 text-muted-foreground">Click the point to open the report</p>
    </div>
  );
}
