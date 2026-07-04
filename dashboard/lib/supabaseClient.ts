import { createClient } from "@supabase/supabase-js";

// Uses the new Supabase key naming (sb_publishable_...), consistent with
// .env.example across the other services (legacy anon/service_role keys
// are being deprecated end of 2026 per Supabase's announcement).
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabasePublishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

if (!supabaseUrl || !supabasePublishableKey) {
  throw new Error(
    "Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY. " +
      "Add them to dashboard/.env.local (see repo root .env.example).",
  );
}

// Single shared client for the whole app — every hook/component imports
// this instance rather than creating its own, so we don't open redundant
// realtime websocket connections.
export const supabase = createClient(supabaseUrl, supabasePublishableKey);
