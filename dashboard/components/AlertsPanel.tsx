"use client";

import { useState } from "react";
import { supabase } from "@/lib/supabaseClient";
import { useOfficeAlerts } from "@/lib/useOfficeAlerts";
import type { AlertType } from "@/lib/types";

const ALERT_STYLES: Record<
  AlertType,
  { label: string; color: string; pulsing: boolean }
> = {
  after_hours: {
    label: "After Hours",
    color: "text-alert-after-hours",
    pulsing: true, // ongoing condition — reads as "still happening"
  },
  room_continuous_2h: {
    label: "Continuous 2h+",
    color: "text-alert-continuous",
    pulsing: false, // crossed the threshold — reads as "needs attention now"
  },
};

function formatSimulatedTime(iso: string) {
  // Contract Section 4: these are simulated timestamps, not wall-clock —
  // must be labeled as such wherever they're displayed.
  return new Date(iso).toLocaleString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
    day: "numeric",
  });
}

export function AlertsPanel() {
  const { alerts, loading, error } = useOfficeAlerts();
  const [clearingIds, setClearingIds] = useState<Set<string>>(new Set());
  const [clearError, setClearError] = useState<string | null>(null);

  async function handleClear(alertId: string) {
    setClearError(null);
    setClearingIds((prev) => new Set(prev).add(alertId));

    const { error: updateError } = await supabase
      .from("alerts")
      .update({ cleared_at: new Date().toISOString() })
      .eq("id", alertId);

    if (updateError) {
      setClearError(`Couldn't clear alert: ${updateError.message}`);
      setClearingIds((prev) => {
        const next = new Set(prev);
        next.delete(alertId);
        return next;
      });
      return;
    }
    // For after_hours: the alert_cleared broadcast removes it from state.
    // For room_continuous_2h: the hook keeps it in state but marks cleared_at,
    // so the panel switches it to a dimmed "resolved" row instead of hiding it.
  }

  // Sort: active alerts first, then resolved ones (most recent first within each group)
  const sorted = [...alerts].sort((a, b) => {
    const aResolved = a.cleared_at !== null && a.cleared_at !== undefined;
    const bResolved = b.cleared_at !== null && b.cleared_at !== undefined;
    if (aResolved !== bResolved) return aResolved ? 1 : -1;
    return new Date(b.raised_at).getTime() - new Date(a.raised_at).getTime();
  });

  const activeCount = alerts.filter((a) => !a.cleared_at).length;

  return (
    <section className="rounded-lg border border-panel-border bg-panel-bg p-4">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-ink-muted">
        Alerts
        {activeCount > 0 && (
          <span className="ml-2 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-alert-after-hours px-1 text-[10px] font-bold text-white">
            {activeCount}
          </span>
        )}
      </h2>

      {error && (
        <p className="text-sm text-alert-continuous">
          Couldn&apos;t load alerts: {error}
        </p>
      )}
      {clearError && (
        <p className="mb-2 text-sm text-alert-continuous">{clearError}</p>
      )}

      {!error && loading && (
        <p className="text-sm text-ink-faint">Loading alerts…</p>
      )}

      {!error && !loading && alerts.length === 0 && (
        <p className="text-sm text-ink-faint">
          No active alerts. Everything looks normal.
        </p>
      )}

      <ul className="divide-y divide-panel-border">
        {sorted.map((alert) => {
          const style = ALERT_STYLES[alert.type];
          const isClearing = clearingIds.has(alert.id);
          const isResolved =
            alert.cleared_at !== null && alert.cleared_at !== undefined;

          return (
            <li
              key={alert.id}
              className={`flex items-center gap-3 py-2.5 first:pt-0 last:pb-0 transition-opacity ${
                isResolved ? "opacity-50" : ""
              }`}
            >
              {/* Status lamp — dimmed when resolved */}
              <span
                className={`alert-lamp ${style.color} ${
                  style.pulsing && !isResolved ? "pulsing" : ""
                }`}
                style={{ backgroundColor: "currentColor" }}
                aria-hidden
              />

              <div className="min-w-0 flex-1">
                <div className="mb-0.5 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide">
                  <span className={style.color}>{style.label}</span>

                  {/* Resolved badge for continuous alerts that have been cleared */}
                  {isResolved && (
                    <span className="rounded bg-panel-border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-widest text-ink-faint">
                      Resolved
                    </span>
                  )}

                  <span className="font-mono font-normal normal-case tracking-normal text-ink-faint">
                    {formatSimulatedTime(alert.raised_at)} (simulated)
                  </span>
                </div>
                <p className="truncate text-sm text-ink" title={alert.message}>
                  {alert.message}
                </p>
                {/* Show resolution time for resolved continuous alerts */}
                {isResolved && alert.cleared_at && (
                  <p className="mt-0.5 text-[11px] text-ink-faint">
                    Resolved at {formatSimulatedTime(alert.cleared_at)}
                  </p>
                )}
              </div>

              {/* Only show Clear button if not already resolved */}
              {!isResolved && (
                <button
                  type="button"
                  onClick={() => handleClear(alert.id)}
                  disabled={isClearing}
                  className="shrink-0 rounded border border-panel-border-strong bg-office-bg px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-ink-muted transition-colors hover:border-status-on/50 hover:text-status-on disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isClearing ? "Clearing…" : "Clear"}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
