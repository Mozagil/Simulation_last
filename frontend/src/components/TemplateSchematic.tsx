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
