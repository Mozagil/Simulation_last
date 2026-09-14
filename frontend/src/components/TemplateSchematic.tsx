/** Şablon seçicinin üstünde, geometrinin neye benzediğini gösteren şema. */

interface TemplateSchematicProps {
  templateId: string;
}

export default function TemplateSchematic({ templateId }: TemplateSchematicProps) {
  if (templateId === "cantilever_beam") {
    return <CantileverBeamSchematic />;
  }
  if (templateId === "simply_supported_beam") {
    return <SimplySupportedBeamSchematic />;
  }
  if (templateId === "plate_with_hole") {
    return <PlateWithHoleSchematic />;
  }
  if (templateId === "dogbone") {
    return <DogboneSchematic />;
  }
  if (templateId === "thick_walled_tube") {
    return <ThickWalledTubeSchematic />;
  }
  if (templateId === "torsion_shaft") {
    return <TorsionShaftSchematic />;
  }
  return null;
}

function CantileverBeamSchematic() {
  return (
    <figure className="template-schematic">
      <svg
        viewBox="0 0 300 150"
        role="img"
        aria-label="Ankastre kiriş: sol uç duvara tutturulmuş, sağ uçta aşağı yük F; L uzunluk, T kalınlık, W genişlik"
      >
        <defs>
          <pattern
            id="wall-hatch"
            width="6"
            height="6"
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(45)"
          >
            <line x1="0" y1="0" x2="0" y2="6" className="template-schematic-hatch" />
          </pattern>
        </defs>

        {/* Duvar (hatch) */}
        <rect x="8" y="16" width="24" height="100" className="template-schematic-wall" />
        <rect x="8" y="16" width="24" height="100" fill="url(#wall-hatch)" />
        <text x="20" y="144" textAnchor="middle" className="template-schematic-caption">
          ankastre
        </text>

        {/*
          İzometrik dikdörtgen kutu.
          Ön-alt-sol (32,88) — uzunluk +x, kalınlık −y, genişlik (+22,−16).
        */}
        <polygon points="32,68 208,68 230,52 54,52" className="template-schematic-face-top" />
        <polygon points="32,68 208,68 208,88 32,88" className="template-schematic-face-side" />
        <polygon points="208,68 230,52 230,72 208,88" className="template-schematic-face-end" />

        {/* T */}
        <line x1="26" y1="68" x2="26" y2="88" className="template-schematic-dim" />
        <text x="20" y="81" textAnchor="end" className="template-schematic-label">
          T
        </text>

        {/* L */}
        <line x1="32" y1="108" x2="208" y2="108" className="template-schematic-dim" />
        <polyline points="32,104 32,112" className="template-schematic-dim" />
        <polyline points="208,104 208,112" className="template-schematic-dim" />
        <text x="120" y="122" textAnchor="middle" className="template-schematic-label">
          L
        </text>

        {/* W */}
        <line x1="236" y1="52" x2="252" y2="64" className="template-schematic-dim" />
        <text x="256" y="60" className="template-schematic-label">
          W
        </text>

        {/* F (−y) */}
        <line x1="208" y1="88" x2="208" y2="122" className="template-schematic-load" />
        <polygon points="208,128 202,116 214,116" className="template-schematic-load-head" />
        <text x="218" y="114" className="template-schematic-label">
          F
        </text>
      </svg>
    </figure>
  );
}

function SimplySupportedBeamSchematic() {
  return (
    <figure className="template-schematic">
      <svg
        viewBox="0 0 300 150"
        role="img"
        aria-label="Basit mesnetli kiriş: iki uçta mesnet, açıklık ortasında aşağı tekil yük F; L uzunluk, T kalınlık, W genişlik"
      >
        {/* Kiriş */}
        <polygon points="28,70 220,70 242,54 50,54" className="template-schematic-face-top" />
        <polygon points="28,70 220,70 220,88 28,88" className="template-schematic-face-side" />
        <polygon points="220,70 242,54 242,72 220,88" className="template-schematic-face-end" />

        {/* Mesnet üçgenleri */}
        <polygon points="28,88 18,108 38,108" className="template-schematic-load-head" />
        <polygon points="220,88 210,108 230,108" className="template-schematic-load-head" />
        <text x="28" y="122" textAnchor="middle" className="template-schematic-caption">
          mesnet
        </text>
        <text x="220" y="122" textAnchor="middle" className="template-schematic-caption">
          mesnet
        </text>

        {/* L / T / W */}
        <line x1="28" y1="132" x2="220" y2="132" className="template-schematic-dim" />
        <polyline points="28,128 28,136" className="template-schematic-dim" />
        <polyline points="220,128 220,136" className="template-schematic-dim" />
        <text x="124" y="146" textAnchor="middle" className="template-schematic-label">
          L
        </text>
        <line x1="22" y1="70" x2="22" y2="88" className="template-schematic-dim" />
        <text x="16" y="82" textAnchor="end" className="template-schematic-label">
          T
        </text>
        <line x1="248" y1="54" x2="264" y2="66" className="template-schematic-dim" />
        <text x="268" y="62" className="template-schematic-label">
          W
        </text>

        {/* Orta nokta F — üstten aşağı */}
        <line x1="124" y1="22" x2="124" y2="48" className="template-schematic-load" />
        <polygon points="124,54 118,42 130,42" className="template-schematic-load-head" />
        <text x="136" y="36" className="template-schematic-label">
          F
        </text>
      </svg>
    </figure>
  );
}

function PlateWithHoleSchematic() {
  return (
    <figure className="template-schematic">
      <svg
        viewBox="0 0 300 150"
        role="img"
        aria-label="Delikli plaka: merkezi dairesel delik, x yönünde çekme F; H uzunluk, W genişlik, d çap"
      >
        {/* Plaka (üstten bakış) */}
        <rect x="50" y="28" width="200" height="90" className="template-schematic-face-side" />
        <circle cx="150" cy="73" r="18" className="template-schematic-hole" />

        {/* Çekme okları */}
        <line x1="28" y1="73" x2="48" y2="73" className="template-schematic-load" />
        <polygon points="50,73 40,68 40,78" className="template-schematic-load-head" />
        <line x1="272" y1="73" x2="252" y2="73" className="template-schematic-load" />
        <polygon points="250,73 260,68 260,78" className="template-schematic-load-head" />
        <text x="22" y="68" textAnchor="middle" className="template-schematic-label">
          F
        </text>
        <text x="280" y="68" textAnchor="middle" className="template-schematic-label">
          F
        </text>

        <line x1="50" y1="128" x2="250" y2="128" className="template-schematic-dim" />
        <text x="150" y="142" textAnchor="middle" className="template-schematic-label">
          H
        </text>
        <line x1="40" y1="28" x2="40" y2="118" className="template-schematic-dim" />
        <text x="28" y="78" textAnchor="end" className="template-schematic-label">
          W
        </text>
        <text x="172" y="70" className="template-schematic-label">
          d
        </text>
      </svg>
    </figure>
  );
}

function DogboneSchematic() {
  return (
    <figure className="template-schematic">
      <svg
        viewBox="0 0 300 150"
        role="img"
        aria-label="Çekme numunesi dogbone: tutamaklar geniş, ölçü kesiti dar, uçlardan çekme F; b ölçü genişliği, B tutamak, L0 ölçü boyu"
      >
        <path
          d="M40,48 L70,48 Q85,48 90,58 L90,58 L210,58 Q215,48 230,48 L260,48 L260,102 L230,102 Q215,102 210,92 L90,92 Q85,102 70,102 L40,102 Z"
          className="template-schematic-face-side"
        />
        <line x1="22" y1="75" x2="38" y2="75" className="template-schematic-load" />
        <polygon points="40,75 30,70 30,80" className="template-schematic-load-head" />
        <line x1="278" y1="75" x2="262" y2="75" className="template-schematic-load" />
        <polygon points="260,75 270,70 270,80" className="template-schematic-load-head" />
        <text x="18" y="70" className="template-schematic-label">
          F
        </text>
        <text x="282" y="70" className="template-schematic-label">
          F
        </text>
        <text x="150" y="52" textAnchor="middle" className="template-schematic-label">
          b
        </text>
        <text x="50" y="42" className="template-schematic-label">
          B
        </text>
        <line x1="90" y1="118" x2="210" y2="118" className="template-schematic-dim" />
        <text x="150" y="134" textAnchor="middle" className="template-schematic-label">
          L0
        </text>
      </svg>
    </figure>
  );
}

function ThickWalledTubeSchematic() {
  return (
    <figure className="template-schematic">
      <svg
        viewBox="0 0 300 150"
        role="img"
        aria-label="Kalın cidarlı boru: iç yarıçap a, dış yarıçap b, iç cidarda basınç p"
      >
        <circle cx="150" cy="72" r="52" className="template-schematic-face-side" />
        <circle cx="150" cy="72" r="26" className="template-schematic-hole" />

        <line x1="150" y1="72" x2="202" y2="72" className="template-schematic-dim" />
        <text x="186" y="66" className="template-schematic-label">
          b
        </text>
        <line x1="150" y1="72" x2="168" y2="94" className="template-schematic-dim" />
        <text x="172" y="98" className="template-schematic-label">
          a
        </text>

        <line x1="150" y1="58" x2="150" y2="48" className="template-schematic-load" />
        <polygon points="150,42 146,52 154,52" className="template-schematic-load-head" />
        <line x1="164" y1="72" x2="174" y2="72" className="template-schematic-load" />
        <polygon points="180,72 170,68 170,76" className="template-schematic-load-head" />
        <line x1="150" y1="86" x2="150" y2="96" className="template-schematic-load" />
        <polygon points="150,102 146,92 154,92" className="template-schematic-load-head" />
        <text x="150" y="28" textAnchor="middle" className="template-schematic-label">
          p
        </text>
      </svg>
    </figure>
  );
}

function TorsionShaftSchematic() {
  return (
    <figure className="template-schematic">
      <svg
        viewBox="0 0 300 150"
        role="img"
        aria-label="Burulma mili: sol uç ankastre, sağ uçta moment T; L boy, R yarıçap"
      >
        <defs>
          <pattern
            id="wall-hatch-shaft"
            width="6"
            height="6"
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(45)"
          >
            <line x1="0" y1="0" x2="0" y2="6" className="template-schematic-hatch" />
          </pattern>
        </defs>

        <rect x="8" y="28" width="24" height="88" className="template-schematic-wall" />
        <rect x="8" y="28" width="24" height="88" fill="url(#wall-hatch-shaft)" />
        <text x="20" y="140" textAnchor="middle" className="template-schematic-caption">
          ankastre
        </text>

        <polygon points="32,48 208,48 220,36 44,36" className="template-schematic-face-top" />
        <polygon points="32,48 208,48 208,96 32,96" className="template-schematic-face-side" />
        <ellipse cx="208" cy="72" rx="14" ry="24" className="template-schematic-face-end" />

        <line x1="32" y1="112" x2="208" y2="112" className="template-schematic-dim" />
        <polyline points="32,108 32,116" className="template-schematic-dim" />
        <polyline points="208,108 208,116" className="template-schematic-dim" />
        <text x="120" y="128" textAnchor="middle" className="template-schematic-label">
          L
        </text>
        <line x1="236" y1="48" x2="236" y2="96" className="template-schematic-dim" />
        <text x="246" y="76" className="template-schematic-label">
          R
        </text>

        <path
          d="M222,52 A18,28 0 0 1 222,92"
          fill="none"
          className="template-schematic-load"
        />
        <polygon points="226,90 214,90 222,100" className="template-schematic-load-head" />
        <text x="248" y="42" className="template-schematic-label">
          T
        </text>
      </svg>
    </figure>
  );
}
