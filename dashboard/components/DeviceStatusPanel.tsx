"use client";

import { useOfficeDevices } from "@/lib/OfficeDevicesProvider";
import type { Device } from "@/lib/types";

export function DeviceStatusPanel() {
  const { devices, rooms } = useOfficeDevices();

  // Grouping is done here, generically, by room_id — never by a fixed
  // room name/count (contract's non-negotiable rule applies to the
  // dashboard too, not just backend/simulator).
  const devicesByRoom = new Map<string, Device[]>();
  for (const device of devices) {
    const list = devicesByRoom.get(device.room_id) ?? [];
    list.push(device);
    devicesByRoom.set(device.room_id, list);
  }

  return (
    <section className="rounded-lg border border-panel-border bg-panel-bg p-4">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-ink-muted">
        Live Device Status
      </h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {rooms.map((room) => {
          const roomDevices = (devicesByRoom.get(room.id) ?? []).sort((a, b) =>
            a.label.localeCompare(b.label),
          );
          return (
            <div
              key={room.id}
              className="rounded-md border border-panel-border/60 p-3"
            >
              <h3 className="mb-2 text-sm font-medium text-ink">{room.name}</h3>
              <ul className="space-y-1.5">
                {roomDevices.map((device) => (
                  <li
                    key={device.id}
                    className="flex items-center justify-between text-sm"
                  >
                    <span className="flex items-center gap-1.5 text-ink-muted">
                      <span aria-hidden className="text-xs opacity-70">
                        {device.type === "fan" ? "◈" : "◉"}
                      </span>
                      {device.label}
                    </span>
                    <span
                      className={
                        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-mono text-[11px] font-medium tracking-wide " +
                        (device.status
                          ? "bg-status-on/12 text-status-on"
                          : "bg-status-off/15 text-ink-faint")
                      }
                    >
                      <span
                        className={
                          "h-1.5 w-1.5 rounded-full " +
                          (device.status
                            ? "bg-status-on shadow-[0_0_6px_var(--color-status-on)]"
                            : "bg-status-off")
                        }
                      />
                      {device.status ? "ON" : "OFF"}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </section>
  );
}
