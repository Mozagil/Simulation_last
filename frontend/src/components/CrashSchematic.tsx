/** Crash senaryo şeması — mühendise karar önermez, düzeni gösterir. */

export type CrashScenarioId = "rigid_wall" | "plate_ball";

export default function CrashSchematic({ scenario }: { scenario: CrashScenarioId }) {
  if (scenario === "plate_ball") {
    return <PlateBallSchematic />;
  }
  return <RigidWallSchematic />;
}

function RigidWallSchematic() {
  return (
    <figure className="template-schematic crash-schematic">
      <svg
        viewBox="0 0 320 150"
        role="img"
        aria-label="Rigid wall: cisim -Z hızıyla sonsuz düzlem bariyere çarpar"
      >
        <defs>
          <pattern
            id="crash-wall-hatch"
            width="6"
            height="6"
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(45)"
          >
            <line x1="0" y1="0" x2="0" y2="6" className="template-schematic-hatch" />
          </pattern>
        </defs>
        <rect x="8" y="118" width="304" height="22" className="template-schematic-wall" />
        <rect x="8" y="118" width="304" height="22" fill="url(#crash-wall-hatch)" />
        <text x="160" y="146" textAnchor="middle" className="template-schematic-caption">
          /RWALL PLANE
        </text>
        <polygon
          points="118,42 202,42 214,30 130,30"
          className="template-schematic-face-top"
        />
        <polygon
          points="118,42 202,42 202,88 118,88"
          className="template-schematic-face-side"
        />
        <polygon
          points="202,42 214,30 214,76 202,88"
          className="template-schematic-face-end"
        />
        <line x1="160" y1="24" x2="160" y2="8" className="template-schematic-load" />
        <polygon points="154,22 166,22 160,32" className="template-schematic-load-head" />
        <text x="176" y="18" className="template-schematic-label">
          v
        </text>
        <text x="160" y="108" textAnchor="middle" className="template-schematic-caption">
          n
        </text>
        <line x1="160" y1="92" x2="160" y2="116" className="template-schematic-dim" />
      </svg>
      <figcaption className="crash-schematic-caption">
        Rigid wall: yüklenen 3D mesh + sonsuz düzlem. 0° = duvara dik (−n).
      </figcaption>
    </figure>
  );
}

function PlateBallSchematic() {
  return (
    <figure className="template-schematic crash-schematic">
      <svg
        viewBox="0 0 320 150"
        role="img"
        aria-label="Plaka-küre: küre aşağı hız, rijit plaka RWALL"
      >
        <defs>
          <pattern
            id="crash-plate-hatch"
            width="6"
            height="6"
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(45)"
          >
            <line x1="0" y1="0" x2="0" y2="6" className="template-schematic-hatch" />
          </pattern>
        </defs>
        <rect x="48" y="112" width="224" height="16" className="template-schematic-wall" />
        <rect x="48" y="112" width="224" height="16" fill="url(#crash-plate-hatch)" />
        <text x="160" y="144" textAnchor="middle" className="template-schematic-caption">
          rijit plaka = /RWALL
        </text>
        <ellipse cx="160" cy="58" rx="28" ry="26" className="template-schematic-face-end" />
        <ellipse cx="160" cy="52" rx="28" ry="12" className="template-schematic-face-top" />
        <line x1="160" y1="22" x2="160" y2="8" className="template-schematic-load" />
        <polygon points="154,20 166,20 160,30" className="template-schematic-load-head" />
        <text x="176" y="18" className="template-schematic-label">
          v
        </text>
      </svg>
      <figcaption className="crash-schematic-caption">
        Plaka–küre: plaka şu an rijit duvar. Deforme plaka + /INTER ayrı adım.
        Mesh olarak küre (veya impactor) yüklenir.
      </figcaption>
    </figure>
  );
}
