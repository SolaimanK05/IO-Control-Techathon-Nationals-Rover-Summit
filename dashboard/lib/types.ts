// Mirrors docs/api-contract.md Sections 1.2 and 2 exactly.
// If the contract changes, update here first — every component derives
// its props from these types, nothing redeclares shapes locally.

export type DeviceType = "fan" | "light";

export interface Device {
  id: string;
  room_id: string;
  type: DeviceType;
  label: string; // display only — never used to target the SVG
  svg_id: string; // targets the SVG element — never shown to the user
  status: boolean;
  watts: number;
  last_changed: string; // ISO 8601, simulated time (see contract Section 4)
}

export interface Room {
  id: string;
  name: string;
}

// Topic: office-updates (contract Section 2)
export interface DeviceStatusChangedPayload {
  device_id: string;
  room_id: string;
  label: string;
  type: DeviceType;
  new_status: boolean;
  watts: number;
  ts: string;
}

export type AlertType = "after_hours" | "room_continuous_2h";

// Topic: office-alerts (contract Section 2)
export interface AlertPayload {
  id: string;
  type: AlertType;
  room_id: string;
  device_id: string | null;
  message: string;
  raised_at: string;
  cleared_at: string | null;
}

// Client-side alert shape (adds room_name for display, since the dashboard
// has rooms loaded locally and shouldn't need a second round trip to label
// an alert)
export interface DashboardAlert extends AlertPayload {
  room_name: string;
}
