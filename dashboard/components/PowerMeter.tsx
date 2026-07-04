"use client";

import { useOfficeDevices } from "@/lib/OfficeDevicesProvider";

export function PowerMeter() {
  const { devices, rooms } = useOfficeDevices();

  // Instant total = SUM(watts WHERE status = true), computed on demand —
  // matches contract Section 4.5 exactly. No stored/cached wattage here.
  const totalWatts = devices.reduce(
    (sum, d) => sum + (d.status ? d.watts : 0),
    0,
  );

  const perRoom = rooms.map((room) => {
    const watts = devices
      .filter((d) => d.room_id === room.id)
      .reduce((sum, d) => sum + (d.status ? d.watts : 0), 0);
    return { room, watts };
  });

  const maxRoomWatts = Math.max(1, ...perRoom.map((r) => r.watts));

  return (
    <section className="rounded-lg border border-panel-border bg-panel-bg p-4">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-ink-muted">
        Live Power Consumption
      </h2>

      <div className="mb-4 flex items-baseline gap-2">
        <span className="font-mono text-4xl font-semibold tabular-nums text-ink">
          {totalWatts}
        </span>
        <span className="text-sm text-ink-muted">W total</span>
      </div>

      <ul className="space-y-2.5">
        {perRoom.map(({ room, watts }) => (
          <li key={room.id}>
            <div className="mb-1 flex justify-between text-xs text-ink-muted">
              <span>{room.name}</span>
              <span className="font-mono tabular-nums">{watts} W</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-panel-border">
              <div
                className="h-full rounded-full bg-status-on transition-[width] duration-500"
                style={{ width: `${(watts / maxRoomWatts) * 100}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
