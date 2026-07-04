import { supabase } from "@/lib/supabaseClient";
import { OfficeDevicesProvider } from "@/lib/OfficeDevicesProvider";
import { OfficeLayoutSvg } from "@/components/OfficeLayoutSvg";
import { DeviceStatusPanel } from "@/components/DeviceStatusPanel";
import { PowerMeter } from "@/components/PowerMeter";
import { AlertsPanel } from "@/components/AlertsPanel";
import type { Device, Room } from "@/lib/types";

// Server Component: does the initial snapshot fetch (Phase 4 spec) so the
// page has real data on first paint. The client then takes over via
// OfficeDevicesProvider's realtime subscription — no polling after this.
export default async function DashboardPage() {
  const [
    { data: rooms, error: roomsError },
    { data: devices, error: devicesError },
  ] = await Promise.all([
    supabase.from("rooms").select("*").order("name"),
    supabase.from("devices").select("*"),
  ]);

  if (roomsError || devicesError) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <p className="text-alert-continuous">
          Failed to load initial office data:{" "}
          {roomsError?.message ?? devicesError?.message}
        </p>
      </main>
    );
  }

  return (
    <OfficeDevicesProvider
      initialRooms={(rooms ?? []) as Room[]}
      initialDevices={(devices ?? []) as Device[]}
    >
      <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 p-6">
        <header className="border-b border-panel-border pb-4">
          <h1 className="text-2xl font-semibold tracking-tight text-ink">
            Office Monitor
          </h1>
          <p className="text-sm text-ink-muted">
            Live view of lights, fans, and power usage across all rooms.
          </p>
        </header>

        <div className="grid gap-6 lg:grid-cols-2">
          <DeviceStatusPanel />
          <PowerMeter />
        </div>

        <OfficeLayoutSvg />

        <AlertsPanel />
      </main>
    </OfficeDevicesProvider>
  );
}
