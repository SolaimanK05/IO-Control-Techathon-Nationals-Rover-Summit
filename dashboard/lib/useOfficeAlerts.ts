"use client";

import { useEffect, useState } from "react";
import { supabase } from "./supabaseClient";
import type { AlertPayload } from "./types";

interface OfficeAlertsState {
  alerts: AlertPayload[];
  loading: boolean;
  error: string | null;
}

/**
 * Owns the full lifecycle of alerts:
 * - Initial fetch of all uncleared alerts (cleared_at IS NULL)
 * - Live updates via the office-alerts broadcast topic
 *
 * Behaviour by alert type:
 *   after_hours         → added on raise, removed from list on clear
 *                         (it's an ongoing condition — clearing means it's resolved)
 *   room_continuous_2h  → added on raise, KEPT in list even after cleared
 *                         (crossing 2h is a completed event — stays as a record
 *                          until the user explicitly removes it via the Clear button,
 *                          which triggers the backend to set cleared_at)
 *
 * The alert `message` field is already human-readable and includes room
 * context (contract Section 1.4), so this hook doesn't need to join against
 * rooms/devices — keeping it fully independent, as the plan specifies.
 */
export function useOfficeAlerts(): OfficeAlertsState {
  const [alerts, setAlerts] = useState<AlertPayload[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadActiveAlerts() {
      const { data, error: fetchError } = await supabase
        .from("alerts")
        .select("*")
        .is("cleared_at", null)
        .order("raised_at", { ascending: false });

      if (cancelled) return;

      if (fetchError) {
        setError(fetchError.message);
      } else {
        setAlerts((data ?? []) as AlertPayload[]);
      }
      setLoading(false);
    }

    loadActiveAlerts();

    const channel = supabase
      .channel("office-alerts", { config: { private: false } })
      .on(
        "broadcast",
        { event: "alert_raised" },
        (message: { payload: AlertPayload }) => {
          setAlerts((prev) => {
            // Avoid duplicates if initial fetch and broadcast race
            if (prev.some((a) => a.id === message.payload.id)) return prev;
            return [message.payload, ...prev];
          });
        },
      )
      .on(
        "broadcast",
        { event: "alert_cleared" },
        (message: { payload: AlertPayload }) => {
          setAlerts((prev) =>
            prev.flatMap((a) => {
              if (a.id !== message.payload.id) return [a];
              // room_continuous_2h: keep in list so it stays visible on the
              // dashboard as a historical record. The user clears it manually.
              if (a.type === "room_continuous_2h") {
                return [{ ...a, cleared_at: message.payload.cleared_at }];
              }
              // after_hours: remove — it's an ongoing condition that's now resolved.
              return [];
            }),
          );
        },
      )
      .subscribe((status, err) => {
        if (status === "CHANNEL_ERROR") {
          setError(err?.message ?? "office-alerts channel error");
        }
      });

    return () => {
      cancelled = true;
      supabase.removeChannel(channel);
    };
  }, []);

  return { alerts, loading, error };
}
