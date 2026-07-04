"use client";

import { useEffect, useRef, useState } from "react";
import { useOfficeDevices } from "@/lib/OfficeDevicesProvider";

// The 6 fan svg_ids, per api-contract.md Section 1.2.1. Listed explicitly
// here (not derived) because this is the one-time DOM restructuring step,
// not a data query — the contract's "don't hardcode device names" rule
// applies to queries/business logic, not to a fixed rendering fixup for a
// known static SVG asset.
const FAN_SVG_IDS = [
  "d-fan-top",
  "d-fan-bottom",
  "w1-fan-top",
  "w1-fan-bottom",
  "w2-fan-top",
  "w2-fan-bottom",
];

export function OfficeLayoutSvg() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svgReady, setSvgReady] = useState(false);
  const { devicesBySvgId } = useOfficeDevices();

  // Step 1: load the raw SVG once and inject it, then isolate each fan's
  // blade paths into a nested <g class="fan-blades"> so we can rotate
  // blades only — the exported SVG bundles hub+blades as flat siblings
  // (flagged in progress.md / contract 1.2.1).
  useEffect(() => {
    let cancelled = false;

    async function loadSvg() {
      const res = await fetch("/office-layout.svg");
      const svgText = await res.text();
      if (cancelled || !containerRef.current) return;

      containerRef.current.innerHTML = svgText;

      const svgRoot = containerRef.current.querySelector("svg");
      if (svgRoot) {
        // Let CSS control sizing instead of the fixed width/height from Figma.
        svgRoot.removeAttribute("width");
        svgRoot.removeAttribute("height");
      }

      for (const fanId of FAN_SVG_IDS) {
        const fanGroup = containerRef.current.querySelector(`#${fanId}`);
        if (!fanGroup) {
          console.warn(`OfficeLayoutSvg: fan group #${fanId} not found`);
          continue;
        }
        const children = Array.from(fanGroup.children); // [hub, blade, blade, blade]
        if (children.length < 2) continue;

        const [hub, ...bladePaths] = children;

        // The blade paths aren't pixel-perfectly symmetric around the hub
        // (Figma export imprecision), so centering rotation on the blade
        // group's own bounding box (fill-box) makes it wobble off-axis.
        // Instead, pin the rotation origin to the hub circle's actual
        // center, measured directly from its geometry.
        const hubBBox = (hub as SVGGraphicsElement).getBBox();
        const centerX = hubBBox.x + hubBBox.width / 2;
        const centerY = hubBBox.y + hubBBox.height / 2;

        const bladeGroup = document.createElementNS(
          "http://www.w3.org/2000/svg",
          "g",
        );
        bladeGroup.setAttribute("class", "fan-blades");
        // transform-box: view-box makes transform-origin interpret
        // centerX/centerY in the SVG's own coordinate space (viewBox
        // starts at 0,0 here), rather than as a % of the blade group's
        // own — imprecise — bounding box.
        bladeGroup.style.transformBox = "view-box";
        bladeGroup.style.transformOrigin = `${centerX}px ${centerY}px`;

        bladePaths.forEach((blade) => bladeGroup.appendChild(blade));
        fanGroup.appendChild(bladeGroup);
      }

      setSvgReady(true);
    }

    loadSvg();
    return () => {
      cancelled = true;
    };
  }, []);

  // Step 2: whenever device state changes, sync classes onto the SVG.
  // Lights: toggle device-on/device-off directly on the device's <g>.
  // Fans: toggle "spinning" on the nested .fan-blades group created above.
  useEffect(() => {
    if (!svgReady || !containerRef.current) return;

    for (const device of Object.values(devicesBySvgId)) {
      const el = containerRef.current.querySelector(`#${device.svg_id}`);
      if (!el) continue;

      if (device.type === "light") {
        el.classList.toggle("device-on", device.status);
        el.classList.toggle("device-off", !device.status);
      } else {
        const blades = el.querySelector(".fan-blades");
        blades?.classList.toggle("spinning", device.status);
      }
    }
  }, [devicesBySvgId, svgReady]);

  return (
    <div
      ref={containerRef}
      className="office-svg-wrapper w-full rounded-lg border border-panel-border bg-panel-bg p-2"
      aria-label="Live office layout"
      role="img"
    />
  );
}
