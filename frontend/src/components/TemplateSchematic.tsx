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
  if (templateId === "i_beam") {
    return <IBeamSchematic />;
  }
  if (templateId === "box_tube") {
    return <BoxTubeSchematic />;
  }
  if (templateId === "circular_tube") {
    return <CircularTubeSchematic />;
  }
  if (templateId === "l_angle") {
    return <LAngleSchematic />;
  }
  if (templateId === "notched_bar") {
    return <NotchedBarSchematic />;
  }
  if (templateId === "keyway_shaft") {
    return <KeywayShaftSchematic />;
  }
  if (templateId === "t_bracket") {
    return <TBracketSchematic />;
  }
  if (templateId === "l_bracket_bolted") {
    return <LBracketBoltedSchematic />;
  }
  if (templateId === "flange") {
    return <FlangeSchematic />;
  }
  if (templateId === "stepped_shaft") {
    return <SteppedShaftSchematic />;
  }
  if (templateId === "crash_box_shell") {
    return <CrashBoxShellSchematic />;
  }
  if (templateId === "crash_box_plate") {
    return <CrashBoxPlateSchematic />;
  }
  if (templateId === "plate_ball_shell") {
    return <PlateBallSchematic />;
  }
  if (templateId === "taylor_bar") {
    return <TaylorBarSchematic />;
  }
  if (templateId === "drop_box_shell") {
    return <DropBoxSchematic />;
  }
  if (templateId === "pole_beam_shell") {
    return <PoleBeamSchematic />;
  }
  if (templateId === "rops_frame_shell") {
    return <RopsFrameSchematic />;
  }
  if (templateId === "s_rail_shell") {
    return <SRailSchematic />;
  }
  if (templateId === "door_beam_shell") {
    return <DoorBeamSchematic />;
  }
  if (templateId === "hopkinson_bar") {
    return <HopkinsonSchematic />;
  }
  if (templateId === "blast_plate_shell") {
    return <BlastPlateSchematic />;
  }
  if (templateId === "bucket_rock_shell") {
    return <BucketRockSchematic />;
  }
  if (templateId === "rocket") {
    return <RocketSchematic />;
  }
  if (templateId === "cfd_sphere") {
    return <CfdSphereSchematic />;
  }
  return null;
}

/* Crash şablonları (K0 sonrası): ana sayfada durability gibi şema. */

function ImpactArrow({ x1, x2, y, label }: { x1: number; x2: number; y: number; label: string }) {
  const dir = x2 < x1 ? -1 : 1;
  return (
    <g>
      <line x1={x1} y1={y} x2={x2 - dir * 6} y2={y} className="template-schematic-load" />
      <polygon
        points={`${x2},${y} ${x2 - dir * 8},${y - 4} ${x2 - dir * 8},${y + 4}`}
        className="template-schematic-load-head"
      />
      <text x={(x1 + x2) / 2} y={y - 6} textAnchor="middle" className="template-schematic-label">
        {label}
      </text>
    </g>
  );
}

function RigidWall({ x }: { x: number }) {
  return (
    <g>
      <defs>
        <pattern id="crash-wall-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="6" className="template-schematic-hatch" />
        </pattern>
      </defs>
      <rect x={x - 12} y="16" width="12" height="104" className="template-schematic-wall" />
      <rect x={x - 12} y="16" width="12" height="104" fill="url(#crash-wall-hatch)" />
    </g>
  );
}

function CrashBoxShellSchematic() {
  return (
    <figure className="template-schematic">
      <svg
        viewBox="0 0 300 150"
        role="img"
        aria-label="Crash box kabuk: açık uçlu kutu profil (orta yüzey), uzunluk L, kesit h × b, cidar t; ön uç rijit duvara v0 hızıyla çarpar"
      >
        <RigidWall x={40} />
        <text x="34" y="138" textAnchor="middle" className="template-schematic-caption">
          rijit duvar
        </text>
        {/* İzometrik açık kutu: ön uç x = 40 (kutu_on), arka uç (kutu_arka) */}
        <polygon points="40,70 220,70 242,54 62,54" className="template-schematic-face-top" />
        <polygon points="40,70 220,70 220,100 40,100" className="template-schematic-face-side" />
        <polygon points="220,70 242,54 242,84 220,100" className="template-schematic-face-end" />
        <polygon points="226,72 236,65 236,82 226,90" className="template-schematic-hole" />
        <text x="130" y="114" textAnchor="middle" className="template-schematic-label">L</text>
        <text x="252" y="80" className="template-schematic-label">h</text>
        <text x="236" y="48" className="template-schematic-label">b</text>
        <text x="200" y="64" className="template-schematic-caption">t</text>
        <text x="52" y="128" className="template-schematic-caption">kutu_on</text>
        <text x="200" y="128" className="template-schematic-caption">kutu_arka</text>
        <ImpactArrow x1={150} x2={92} y={36} label="v₀" />
      </svg>
    </figure>
  );
}

function CrashBoxPlateSchematic() {
  return (
    <figure className="template-schematic">
      <svg
        viewBox="0 0 300 150"
        role="img"
        aria-label="Crash box ve çarpma plakası: kutu (L, h, b, t) g aralıkla tp kalınlıklı plakaya doğru hareket eder; plaka kesiti m kadar aşar"
      >
        {/* Plaka (iki ayrı katı: plaka + kutu) */}
        <polygon points="40,24 52,24 74,8 62,8" className="template-schematic-face-top" />
        <polygon points="40,24 52,24 52,124 40,124" className="template-schematic-face-side" />
        <polygon points="52,24 74,8 74,108 52,124" className="template-schematic-face-end" />
        <text x="46" y="138" textAnchor="middle" className="template-schematic-label">tp</text>
        <text x="80" y="22" className="template-schematic-caption">m</text>
        {/* Kutu: g aralıkla */}
        <polygon points="64,70 230,70 252,54 86,54" className="template-schematic-face-top" />
        <polygon points="64,70 230,70 230,100 64,100" className="template-schematic-face-side" />
        <polygon points="230,70 252,54 252,84 230,100" className="template-schematic-face-end" />
        <polygon points="236,72 246,65 246,82 236,90" className="template-schematic-hole" />
        <text x="58" y="112" className="template-schematic-caption">g</text>
        <text x="148" y="114" textAnchor="middle" className="template-schematic-label">L</text>
        <text x="262" y="80" className="template-schematic-label">h</text>
        <text x="246" y="48" className="template-schematic-label">b</text>
        <text x="212" y="64" className="template-schematic-caption">t</text>
        <ImpactArrow x1={170} x2={112} y={36} label="v₀" />
      </svg>
    </figure>
  );
}

function PlateBallSchematic() {
  return (
    <figure className="template-schematic">
      <svg
        viewBox="0 0 300 150"
        role="img"
        aria-label="Plaka–küre: a × a kare plaka (kalınlık t), kenarları sabit; üstünde g boşlukla D çaplı rijit küre −z yönünde v0 hızıyla"
      >
        {/* Plaka (izometrik), kenarlar sabit */}
        <polygon points="40,104 210,104 260,78 90,78" className="template-schematic-face-top" />
        <polygon points="40,104 210,104 210,112 40,112" className="template-schematic-face-side" />
        <polygon points="210,104 260,78 260,86 210,112" className="template-schematic-face-end" />
        <text x="125" y="128" textAnchor="middle" className="template-schematic-label">a</text>
        <text x="268" y="86" className="template-schematic-label">t</text>
        <text x="40" y="140" className="template-schematic-caption">plaka_kenar sabit</text>
        {/* Küre */}
        <circle cx="150" cy="56" r="18" className="template-schematic-face-side" />
        <text x="174" y="50" className="template-schematic-label">D</text>
        <text x="158" y="84" className="template-schematic-caption">g</text>
        {/* −z hız */}
        <line x1="120" y1="14" x2="120" y2="44" className="template-schematic-load" />
        <polygon points="120,52 116,44 124,44" className="template-schematic-load-head" />
        <text x="100" y="30" className="template-schematic-label">v₀</text>
        <text x="200" y="40" className="template-schematic-caption">kure (rijit)</text>
      </svg>
    </figure>
  );
}

function CantileverBeamSchematic() {
  return (
    <figure className="template-schematic">
      <svg
        viewBox="0 0 300 150"
        role="img"
        aria-label="Ankastre kiriş: sol uç duvara tutturulmuş, sağ uçta aşağı yük F; L uzunluk, T kalınlık, W genişlik; isteğe bağlı kök filleti r, duvar kalınlığı tw ve taşması m"
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

        {/* Kök filleti (r > 0): duvar bloğu tw × (T+2m), kiriş köküne r yayı */}
        <path d="M32,60 Q32,68 40,68" className="template-schematic-dim" />
        <path d="M32,96 Q32,88 40,88" className="template-schematic-dim" />
        <text x="44" y="64" className="template-schematic-label">r</text>
        <text x="20" y="28" textAnchor="middle" className="template-schematic-caption">tw</text>
        <text x="46" y="104" className="template-schematic-caption">m</text>

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

function IBeamSchematic() {
  return (
    <figure className="template-schematic">
      <svg viewBox="0 0 300 150" role="img" aria-label="I-kesit kiriş: h yükseklik, b flanş, tw gövde, tf flanş kalınlığı">
        <rect x="110" y="28" width="80" height="16" className="template-schematic-face-side" />
        <rect x="140" y="44" width="20" height="56" className="template-schematic-face-side" />
        <rect x="110" y="100" width="80" height="16" className="template-schematic-face-side" />
        <text x="200" y="40" className="template-schematic-label">b</text>
        <text x="200" y="80" className="template-schematic-label">h</text>
        <text x="168" y="76" className="template-schematic-label">tw</text>
        <text x="200" y="112" className="template-schematic-label">tf</text>
      </svg>
    </figure>
  );
}

function BoxTubeSchematic() {
  return (
    <figure className="template-schematic">
      <svg viewBox="0 0 300 150" role="img" aria-label="Kutu profil: dış h ve b, cidar t">
        <rect x="90" y="32" width="120" height="80" className="template-schematic-face-side" />
        <rect x="110" y="48" width="80" height="48" className="template-schematic-hole" />
        <text x="220" y="48" className="template-schematic-label">h</text>
        <text x="150" y="128" textAnchor="middle" className="template-schematic-label">b</text>
        <text x="150" y="76" textAnchor="middle" className="template-schematic-label">t</text>
      </svg>
    </figure>
  );
}

function CircularTubeSchematic() {
  return (
    <figure className="template-schematic">
      <svg viewBox="0 0 300 150" role="img" aria-label="Dairesel tüp: dış R, iç r">
        <circle cx="150" cy="72" r="48" className="template-schematic-face-side" />
        <circle cx="150" cy="72" r="32" className="template-schematic-hole" />
        <text x="210" y="70" className="template-schematic-label">R</text>
        <text x="168" y="78" className="template-schematic-label">r</text>
      </svg>
    </figure>
  );
}

function LAngleSchematic() {
  return (
    <figure className="template-schematic">
      <svg viewBox="0 0 300 150" role="img" aria-label="L-köşebent: bacak a, kalınlık t">
        <rect x="90" y="28" width="18" height="90" className="template-schematic-face-side" />
        <rect x="90" y="100" width="90" height="18" className="template-schematic-face-side" />
        <text x="200" y="112" className="template-schematic-label">a</text>
        <text x="78" y="80" className="template-schematic-label">t</text>
      </svg>
    </figure>
  );
}

function NotchedBarSchematic() {
  return (
    <figure className="template-schematic">
      <svg viewBox="0 0 300 150" role="img" aria-label="Çentikli çubuk: karşılıklı U veya V çentik, çekme F">
        <path
          d="M40,40 L130,40 A16,16 0 0 1 162,40 L260,40 L260,110 L162,110 A16,16 0 0 1 130,110 L40,110 Z"
          className="template-schematic-face-side"
        />
        <text x="150" y="28" textAnchor="middle" className="template-schematic-label">U / V</text>
        <text x="22" y="80" className="template-schematic-label">F</text>
        <text x="272" y="80" className="template-schematic-label">F</text>
      </svg>
    </figure>
  );
}

function KeywayShaftSchematic() {
  return (
    <figure className="template-schematic">
      <svg viewBox="0 0 300 150" role="img" aria-label="Kama kanallı mil: yarıçap R, kama genişliği w ve derinliği h">
        <circle cx="150" cy="72" r="48" className="template-schematic-face-side" />
        <rect x="138" y="28" width="24" height="22" className="template-schematic-hole" />
        <text x="210" y="70" className="template-schematic-label">R</text>
        <text x="150" y="24" textAnchor="middle" className="template-schematic-label">w, h</text>
      </svg>
    </figure>
  );
}


function TBracketSchematic() {
  return (
    <figure className="template-schematic">
      <svg viewBox="0 0 300 150" role="img" aria-label="T-braket: sırt plakası h yükseklik, raf a uzunluk, kalınlık t, isteğe bağlı üçgen kaburga; raf ucunda aşağı yük F">
        <rect x="60" y="20" width="16" height="110" className="template-schematic-face-side" />
        <rect x="76" y="67" width="150" height="16" className="template-schematic-face-side" />
        <path d="M76,83 L136,83 L76,143 Z" className="template-schematic-face-side" strokeDasharray="4 3" />
        <text x="40" y="80" className="template-schematic-label">h</text>
        <text x="150" y="60" className="template-schematic-label">a</text>
        <text x="232" y="78" className="template-schematic-label">t</text>
        <text x="100" y="120" className="template-schematic-label">kaburga</text>
        <text x="226" y="105" className="template-schematic-label">F ↓</text>
      </svg>
    </figure>
  );
}

function LBracketBoltedSchematic() {
  return (
    <figure className="template-schematic">
      <svg viewBox="0 0 300 150" role="img" aria-label="Delikli L-braket: dik bacak hv, yatay bacak lh, kalınlık t, iki cıvata deliği d; yatay bacak ucunda aşağı yük F">
        <rect x="70" y="20" width="16" height="110" className="template-schematic-face-side" />
        <rect x="70" y="114" width="160" height="16" className="template-schematic-face-side" />
        <circle cx="78" cy="42" r="5" className="template-schematic-hole" />
        <circle cx="78" cy="62" r="5" className="template-schematic-hole" />
        <text x="50" y="80" className="template-schematic-label">hv</text>
        <text x="150" y="108" className="template-schematic-label">lh</text>
        <text x="94" y="46" className="template-schematic-label">d</text>
        <text x="236" y="126" className="template-schematic-label">F ↓</text>
      </svg>
    </figure>
  );
}

function FlangeSchematic() {
  return (
    <figure className="template-schematic">
      <svg viewBox="0 0 300 150" role="img" aria-label="Flanş: dış yarıçap R, boru deliği ri, cıvata çemberi Rb üzerinde n delik; boru deliğinden eksenel yük">
        <circle cx="150" cy="75" r="62" className="template-schematic-face-side" />
        <circle cx="150" cy="75" r="24" className="template-schematic-hole" />
        {[0, 60, 120, 180, 240, 300].map((deg) => (
          <circle
            key={deg}
            cx={150 + 45 * Math.cos((deg * Math.PI) / 180)}
            cy={75 + 45 * Math.sin((deg * Math.PI) / 180)}
            r="5"
            className="template-schematic-hole"
          />
        ))}
        <text x="218" y="40" className="template-schematic-label">R</text>
        <text x="150" y="79" textAnchor="middle" className="template-schematic-label">ri</text>
        <text x="200" y="118" className="template-schematic-label">Rb, n, d</text>
      </svg>
    </figure>
  );
}

function SteppedShaftSchematic() {
  return (
    <figure className="template-schematic">
      <svg viewBox="0 0 300 150" role="img" aria-label="Kademeli mil: büyük yarıçap R1 boy L1, küçük yarıçap R2 boy L2, omuzda fillet r; küçük uçta aşağı yük F">
        <rect x="40" y="45" width="110" height="60" className="template-schematic-face-side" />
        <path d="M150,45 L150,55 A8,8 0 0 0 158,63 L260,63 L260,87 L158,87 A8,8 0 0 0 150,95 L150,105 Z" className="template-schematic-face-side" />
        <text x="90" y="36" className="template-schematic-label">L1, R1</text>
        <text x="190" y="56" className="template-schematic-label">L2, R2</text>
        <text x="160" y="118" className="template-schematic-label">r</text>
        <text x="262" y="110" className="template-schematic-label">F ↓</text>
      </svg>
    </figure>
  );
}

function TaylorBarSchematic() {
  return (
    <figure className="template-schematic">
      <svg
        viewBox="0 0 300 150"
        role="img"
        aria-label="Taylor çubuğu: L0 boyunda D0 çaplı dolu silindir, ön yüzü rijit duvara v0 hızıyla çarpar"
      >
        <RigidWall x={52} />
        <text x="46" y="138" textAnchor="middle" className="template-schematic-caption">
          rijit duvar
        </text>
        {/* Silindir (yan görünüş + uç elipsleri) */}
        <rect x="52" y="58" width="170" height="36" className="template-schematic-face-side" />
        <ellipse cx="222" cy="76" rx="9" ry="18" className="template-schematic-face-end" />
        <ellipse cx="52" cy="76" rx="9" ry="18" className="template-schematic-face-top" />
        <text x="137" y="110" textAnchor="middle" className="template-schematic-label">L0</text>
        <text x="238" y="80" className="template-schematic-label">D0</text>
        <text x="64" y="128" className="template-schematic-caption">on_yuz</text>
        <text x="196" y="128" className="template-schematic-caption">arka_yuz</text>
        <ImpactArrow x1={170} x2={110} y={40} label="v₀" />
      </svg>
    </figure>
  );
}

function DropBoxSchematic() {
  return (
    <figure className="template-schematic">
      <svg
        viewBox="0 0 300 150"
        role="img"
        aria-label="Düşme testi: a × b × c kapalı kabuk kutu, rx / ry açılarıyla yönlenmiş, en alt nokta zeminden g yukarıda; H yüksekliğinden düşme, yerçekimi g"
      >
        <defs>
          <pattern id="drop-ground-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="6" className="template-schematic-hatch" />
          </pattern>
        </defs>
        <rect x="20" y="124" width="260" height="14" className="template-schematic-wall" />
        <rect x="20" y="124" width="260" height="14" fill="url(#drop-ground-hatch)" />
        <text x="150" y="148" textAnchor="middle" className="template-schematic-caption">zemin (rijit duvar z = 0)</text>
        {/* Köşe üstüne dönmüş kutu */}
        <g transform="rotate(-25 150 80)">
          <polygon points="110,70 190,70 206,58 126,58" className="template-schematic-face-top" />
          <polygon points="110,70 190,70 190,100 110,100" className="template-schematic-face-side" />
          <polygon points="190,70 206,58 206,88 190,100" className="template-schematic-face-end" />
        </g>
        <text x="150" y="52" className="template-schematic-label">a</text>
        <text x="214" y="70" className="template-schematic-label">c</text>
        <text x="196" y="44" className="template-schematic-label">b</text>
        <text x="64" y="70" className="template-schematic-caption">rx / ry</text>
        <text x="132" y="122" className="template-schematic-caption">g</text>
        {/* düşme oku */}
        <line x1="250" y1="16" x2="250" y2="64" className="template-schematic-load" />
        <polygon points="250,72 246,64 254,64" className="template-schematic-load-head" />
        <text x="258" y="44" className="template-schematic-label">H, g</text>
      </svg>
    </figure>
  );
}

function PoleBeamSchematic() {
  return (
    <figure className="template-schematic">
      <svg
        viewBox="0 0 300 150"
        role="img"
        aria-label="Direk yan çarpması: L boyunda dikdörtgen tüp kiriş (kesit h × b, cidar t), uçları rijit gövde + kütle, ortasında Ø D rijit direk; kiriş direğe v0 ile gelir"
      >
        {/* Üstten görünüş: kiriş y boyunca (yatay), direk ortada aşağıda */}
        <rect x="30" y="40" width="240" height="22" className="template-schematic-face-side" />
        <rect x="18" y="34" width="14" height="34" className="template-schematic-wall" />
        <rect x="268" y="34" width="14" height="34" className="template-schematic-wall" />
        <text x="25" y="28" textAnchor="middle" className="template-schematic-caption">uc_1 + m</text>
        <text x="275" y="28" textAnchor="middle" className="template-schematic-caption">uc_2 + m</text>
        <text x="150" y="36" textAnchor="middle" className="template-schematic-label">L</text>
        <text x="236" y="56" className="template-schematic-label">h</text>
        <circle cx="150" cy="102" r="26" className="template-schematic-hole" />
        <text x="150" y="106" textAnchor="middle" className="template-schematic-label">Ø D</text>
        <text x="182" y="80" className="template-schematic-caption">g</text>
        <text x="150" y="142" textAnchor="middle" className="template-schematic-caption">rijit direk (/RWALL/CYL, eksen z)</text>
        {/* v0 kiriş direğe doğru */}
        <line x1="80" y1="14" x2="80" y2="34" className="template-schematic-load" />
        <polygon points="80,40 76,32 84,32" className="template-schematic-load-head" />
        <text x="88" y="24" className="template-schematic-label">v₀</text>
      </svg>
    </figure>
  );
}

function RopsFrameSchematic() {
  return (
    <figure className="template-schematic">
      <svg
        viewBox="0 0 300 150"
        role="img"
        aria-label="ROPS portal çerçeve: W açıklıklı, H yüksekliğinde bükülmüş dikdörtgen tüp (kesit d × e, cidar t, büküm R); tabanlar sabit, sol üst köşeye yanal itme"
      >
        <defs>
          <pattern id="rops-ground-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="6" className="template-schematic-hatch" />
          </pattern>
        </defs>
        <rect x="40" y="128" width="220" height="10" className="template-schematic-wall" />
        <rect x="40" y="128" width="220" height="10" fill="url(#rops-ground-hatch)" />
        {/* Bükülmüş tüp ekseni: dikme – büküm – kiriş – büküm – dikme */}
        <path
          d="M90,128 L90,48 Q90,28 110,28 L190,28 Q210,28 210,48 L210,128"
          className="template-schematic-load"
          fill="none"
          strokeWidth="9"
          strokeLinejoin="round"
          opacity="0.35"
        />
        <path d="M90,128 L90,48 Q90,28 110,28 L190,28 Q210,28 210,48 L210,128" className="template-schematic-dim" fill="none" />
        <text x="150" y="20" textAnchor="middle" className="template-schematic-label">W</text>
        <text x="222" y="90" className="template-schematic-label">H</text>
        <text x="112" y="46" className="template-schematic-caption">R</text>
        <text x="150" y="146" textAnchor="middle" className="template-schematic-caption">tabanlar sabit (taban_1, taban_2)</text>
        {/* yanal itme sol üst köşeye */}
        <line x1="40" y1="36" x2="76" y2="36" className="template-schematic-load" />
        <polygon points="84,36 76,32 76,40" className="template-schematic-load-head" />
        <text x="38" y="28" className="template-schematic-label">F, v</text>
        <text x="96" y="62" className="template-schematic-caption">yuk</text>
      </svg>
    </figure>
  );
}

function SRailSchematic() {
  return (
    <figure className="template-schematic">
      <svg
        viewBox="0 0 300 150"
        role="img"
        aria-label="S-kiriş: düz L1, R yarıçaplı θ açılı iki ters büküm, düz L2; kesit h × b, cidar t; ön uç rijit duvara, arka uçta kılavuzlu kızak"
      >
        <RigidWall x={36} />
        <text x="30" y="138" textAnchor="middle" className="template-schematic-caption">rijit duvar</text>
        <path d="M36,110 L86,110 Q126,110 146,80 Q166,50 206,50 L262,50" className="template-schematic-load"
          fill="none" strokeWidth="12" opacity="0.35" />
        <path d="M36,110 L86,110 Q126,110 146,80 Q166,50 206,50 L262,50" className="template-schematic-dim" fill="none" />
        <rect x="262" y="38" width="18" height="24" className="template-schematic-wall" />
        <text x="271" y="32" textAnchor="middle" className="template-schematic-caption">kızak</text>
        <text x="60" y="126" className="template-schematic-label">L1</text>
        <text x="150" y="104" className="template-schematic-label">R, θ</text>
        <text x="228" y="70" className="template-schematic-label">L2</text>
        <ImpactArrow x1={250} x2={200} y={22} label="v₀" />
      </svg>
    </figure>
  );
}

function DoorBeamSchematic() {
  return (
    <figure className="template-schematic">
      <svg
        viewBox="0 0 300 150"
        role="img"
        aria-label="Kapı intrüzyonu: L boyunda darbe kirişi (kesit h × b, cidar t), iki ucu ankastre; ortasına Ø D rijit silindir g boşlukla, zorlanmış hızla iter"
      >
        <defs>
          <pattern id="door-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="6" className="template-schematic-hatch" />
          </pattern>
        </defs>
        <rect x="18" y="20" width="14" height="40" className="template-schematic-wall" />
        <rect x="18" y="20" width="14" height="40" fill="url(#door-hatch)" />
        <rect x="268" y="20" width="14" height="40" className="template-schematic-wall" />
        <rect x="268" y="20" width="14" height="40" fill="url(#door-hatch)" />
        <rect x="32" y="32" width="236" height="16" className="template-schematic-face-side" />
        <text x="150" y="26" textAnchor="middle" className="template-schematic-label">L</text>
        <text x="236" y="45" className="template-schematic-caption">h × b, t</text>
        <path d="M95,128 A55,55 0 0 1 205,128" className="template-schematic-hole" />
        <text x="150" y="118" textAnchor="middle" className="template-schematic-label">Ø D</text>
        <text x="158" y="60" className="template-schematic-caption">g</text>
        <line x1="150" y1="104" x2="150" y2="80" className="template-schematic-load" />
        <polygon points="150,72 146,80 154,80" className="template-schematic-load-head" />
        <text x="158" y="94" className="template-schematic-label">v</text>
        <text x="150" y="144" textAnchor="middle" className="template-schematic-caption">rijit silindir impaktör (yavaş itme)</text>
      </svg>
    </figure>
  );
}

function HopkinsonSchematic() {
  return (
    <figure className="template-schematic">
      <svg
        viewBox="0 0 300 150"
        role="img"
        aria-label="Hopkinson çubuğu: Ls boyunda çarpıcı, g boşlukla Li boyunda giriş çubuğuna v0 ile çarpar; aynı çap D; kuvvet Li/4 kesitinde"
      >
        <rect x="14" y="64" width="56" height="20" className="template-schematic-face-side" />
        <rect x="76" y="64" width="210" height="20" className="template-schematic-face-side" />
        <text x="42" y="58" textAnchor="middle" className="template-schematic-label">Ls</text>
        <text x="180" y="58" textAnchor="middle" className="template-schematic-label">Li</text>
        <text x="72" y="100" textAnchor="middle" className="template-schematic-caption">g</text>
        <text x="292" y="78" className="template-schematic-label">D</text>
        <line x1="128" y1="56" x2="128" y2="92" className="template-schematic-dim" strokeDasharray="3 2" />
        <text x="128" y="106" textAnchor="middle" className="template-schematic-caption">kesit Li/4</text>
        <ImpactArrow x1={14} x2={60} y={40} label="v₀" />
        <text x="150" y="132" textAnchor="middle" className="template-schematic-caption">σ = ρ·c·v₀/2, süre 2·Ls/c</text>
      </svg>
    </figure>
  );
}

function BlastPlateSchematic() {
  return (
    <figure className="template-schematic">
      <svg
        viewBox="0 0 300 150"
        role="img"
        aria-label="Patlama yüklü plaka: a × a kare plaka (t), dört kenarı ankastre; yüzeye Friedlander basınç darbesi Ps, td"
      >
        <polygon points="50,100 210,100 260,74 100,74" className="template-schematic-face-top" />
        <polygon points="50,100 210,100 210,108 50,108" className="template-schematic-face-side" />
        <text x="128" y="124" textAnchor="middle" className="template-schematic-label">a</text>
        <text x="266" y="82" className="template-schematic-label">t</text>
        <text x="40" y="140" className="template-schematic-caption">kenarlar ankastre</text>
        {[90, 130, 170, 210].map((x) => (
          <g key={x}>
            <line x1={x} y1="30" x2={x} y2="62" className="template-schematic-load" />
            <polygon points={`${x},70 ${x - 4},62 ${x + 4},62`} className="template-schematic-load-head" />
          </g>
        ))}
        <path d="M228,20 L228,60 M228,22 Q236,50 280,58" className="template-schematic-dim" fill="none" />
        <text x="238" y="18" className="template-schematic-caption">p(t): Ps, td, b</text>
      </svg>
    </figure>
  );
}

function BucketRockSchematic() {
  return (
    <figure className="template-schematic">
      <svg
        viewBox="0 0 300 150"
        role="img"
        aria-label="Kepçe / taş: R yarıçaplı φ açılı kavisli kepçe tabanı (W genişlik, t kalınlık), uç kenarları sabit; üstünde Ø D rijit taş v0 ile düşer"
      >
        <path d="M60,40 A130,130 0 0 0 240,40" className="template-schematic-load" fill="none" strokeWidth="8" opacity="0.35" />
        <path d="M60,40 A130,130 0 0 0 240,40" className="template-schematic-dim" fill="none" />
        <rect x="52" y="30" width="14" height="16" className="template-schematic-wall" />
        <rect x="234" y="30" width="14" height="16" className="template-schematic-wall" />
        <text x="44" y="26" className="template-schematic-caption">pim</text>
        <text x="236" y="26" className="template-schematic-caption">pim</text>
        <circle cx="150" cy="62" r="20" className="template-schematic-face-side" />
        <text x="176" y="58" className="template-schematic-label">Ø D</text>
        <text x="150" y="118" textAnchor="middle" className="template-schematic-label">R, φ, t</text>
        <line x1="150" y1="12" x2="150" y2="34" className="template-schematic-load" />
        <polygon points="150,42 146,34 154,34" className="template-schematic-load-head" />
        <text x="158" y="24" className="template-schematic-label">v₀</text>
        <text x="150" y="142" textAnchor="middle" className="template-schematic-caption">kavisli kepçe tabanı (W genişlik) + rijit taş</text>
      </svg>
    </figure>
  );
}

/* Akış (CFD) şablonu — R1 roket: yan görünüş, akış +x (soldan). */
function RocketSchematic() {
  return (
    <figure className="template-schematic">
      <svg
        viewBox="0 0 300 150"
        role="img"
        aria-label="Roket: Ln boyunda burun, D çaplı Lb boyunda gövde tüpü, kök veteri Cr, uç veteri Ct, açıklığı s olan kanatçıklar; akış soldan sağa"
      >
        {/* Burun (ogive) + gövde */}
        <path d="M 40 75 Q 62 58 92 61 L 92 89 Q 62 92 40 75 Z" className="template-schematic-face-top" />
        <rect x="92" y="61" width="160" height="28" className="template-schematic-face-side" />
        {/* Kanatçıklar (üst ve alt) */}
        <polygon points="212,61 252,61 252,35 236,35" className="template-schematic-face-end" />
        <polygon points="212,89 252,89 252,115 236,115" className="template-schematic-face-end" />
        <text x="66" y="54" textAnchor="middle" className="template-schematic-label">Ln</text>
        <text x="160" y="104" textAnchor="middle" className="template-schematic-label">Lb</text>
        <text x="258" y="79" className="template-schematic-label">D</text>
        <text x="232" y="130" textAnchor="middle" className="template-schematic-label">Cr</text>
        <text x="244" y="30" textAnchor="middle" className="template-schematic-label">Ct</text>
        <text x="262" y="50" className="template-schematic-label">s</text>
        <text x="40" y="128" className="template-schematic-caption">burun</text>
        <text x="132" y="128" className="template-schematic-caption">govde</text>
        <text x="180" y="22" className="template-schematic-caption">kanatcik</text>
        <text x="262" y="100" className="template-schematic-caption">taban</text>
        <ImpactArrow x1={4} x2={34} y={75} label="U" />
      </svg>
    </figure>
  );
}

/* Akış (CFD) doğrulama şablonu — küre (V-C2). */
function CfdSphereSchematic() {
  return (
    <figure className="template-schematic">
      <svg viewBox="0 0 300 150" role="img" aria-label="Küre: D çaplı küre, akış soldan sağa; Re = U·D/ν">
        <circle cx="160" cy="75" r="38" className="template-schematic-face-side" />
        <line x1="122" y1="125" x2="198" y2="125" className="template-schematic-dim" />
        <text x="160" y="140" textAnchor="middle" className="template-schematic-label">D</text>
        <text x="206" y="40" className="template-schematic-caption">kure</text>
        <ImpactArrow x1={30} x2={110} y={75} label="U" />
        <text x="250" y="80" textAnchor="middle" className="template-schematic-caption">Re = U·D/ν</text>
      </svg>
    </figure>
  );
}
