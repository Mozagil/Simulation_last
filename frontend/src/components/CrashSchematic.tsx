/** Crash şeması (rijit duvar) — mühendise karar önermez, düzeni gösterir.
 * Eski "Plaka–küre" ön ayarı kaldırıldı (2026-10-04): yalnız duvar yönünü
 * z'ye çeviriyordu, 1.18 plaka–küre şablonuyla karışıyordu. */

export default function CrashSchematic() {
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
        Rigid wall: yüklenen mesh (3D solid ya da 2D kabuk) + sonsuz düzlem. 0° = duvara dik (−n).
      </figcaption>
    </figure>
  );
}
