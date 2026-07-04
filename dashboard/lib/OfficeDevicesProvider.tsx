"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { supabase } from "./supabaseClient";
import type { Device, DeviceStatusChangedPayload, Room } from "./types";

interface OfficeDevicesContextValue {
  devices: Device[];
  rooms: Room[];
  devicesBySvgId: Record<string, Device>;
  loading: boolean;
  error: string | null;
}

const OfficeDevicesContext = createContext<OfficeDevicesContextValue | null>(
  null,
);

interface OfficeDevicesProviderProps {
  // Server Component does the first fetch (Phase 4 spec: "Server Component
  // initial load"); we hydrate the client store with it so there's no
  // flash-of-empty-dashboard while the client fetch would otherwise run.
  initialDevices: Device[];
  initialRooms: Room[];
  children: ReactNode;
}

export function OfficeDevicesProvider({
  initialDevices,
  initialRooms,
  children,
}: OfficeDevicesProviderProps) {
  const [devices, setDevices] = useState<Device[]>(initialDevices);
  const [rooms] = useState<Room[]>(initialRooms);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Public broadcast channel — matches migration 0002 (private = false).
    // No Realtime Authorization needed since there's no auth system.
    const channel = supabase
      .channel("office-updates", { config: { private: false } })
      .on(
        "broadcast",
        { event: "device_status_changed" },
        (message: { payload: DeviceStatusChangedPayload }) => {
          // eslint-disable-next-line no-console
          console.log(
            "[office-updates] device_status_changed",
            message.payload,
          );
          const p = message.payload;
          setDevices((prev) =>
            prev.map((d) =>
              d.id === p.device_id
                ? { ...d, status: p.new_status, last_changed: p.ts }
                : d,
            ),
          );
        },
      )
      // TEMP DEBUG: catches ANY broadcast event on this topic regardless of
      // name, so we can see in devtools whether messages are arriving at
      // all, and under what event name, before assuming the subscription
      // itself is broken. Remove once "device_status_changed" is confirmed
      // to be the actual event name the DB trigger sends.
      .on("broadcast", { event: "*" }, (message) => {
        // eslint-disable-next-line no-console
        console.log("[office-updates] RAW broadcast received:", message);
      })
      .subscribe((status, err) => {
        // eslint-disable-next-line no-console
        console.log("[office-updates] channel status:", status, err ?? "");
        if (status === "CHANNEL_ERROR") {
          setError(err?.message ?? "office-updates channel error");
        }
        if (status === "TIMED_OUT") {
          setError("office-updates subscription timed out");
        }
      });

    return () => {
      supabase.removeChannel(channel);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const devicesBySvgId = useMemo(
    () => Object.fromEntries(devices.map((d) => [d.svg_id, d])),
    [devices],
  );

  return (
    <OfficeDevicesContext.Provider
      value={{ devices, rooms, devicesBySvgId, loading, error }}
    >
      {children}
    </OfficeDevicesContext.Provider>
  );
}

export function useOfficeDevices() {
  const ctx = useContext(OfficeDevicesContext);
  if (!ctx) {
    throw new Error(
      "useOfficeDevices must be used within <OfficeDevicesProvider>",
    );
  }
  return ctx;
}
