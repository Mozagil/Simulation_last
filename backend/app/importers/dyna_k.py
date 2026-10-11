"""LS-DYNA keyword dosyası (.k / .dyn) okuyucu — 1.21a.

Yalnız içe aktarma: dosya okunur ve ara modele (`DynaModel`) çevrilir;
keyword dosyası yazılmaz (`docs/LICENSING.md#ls-dyna-keyword-içe-aktarma`).
Radioss kartlarına çeviri ayrı adım (1.21b).

Birimler dosyadaki gibi kalır: keyword dosyası birim sistemini taşımaz,
dönüşüm mühendisin kararıdır. Eleman düğümleri ham haliyle tutulur
(dejenere üçgen / tetra / prizma ayrımı çeviri adımına bırakılır).

Desteklenen keyword'ler: *KEYWORD, *TITLE, *INCLUDE, *END, *NODE,
*ELEMENT_SHELL, *ELEMENT_SOLID, *PART, *SECTION_SHELL(_TITLE),
*SECTION_SOLID(_TITLE), *MAT_001 / *MAT_ELASTIC, *MAT_020 / *MAT_RIGID,
*MAT_024 / *MAT_PIECEWISE_LINEAR_PLASTICITY (hepsi _TITLE ile de),
*DEFINE_CURVE(_TITLE). Diğerleri `skipped` içinde sayılır;
atlanan *MAT_* bloklarının MID'i `mat_keywords`'e yazılır (rapor için).
Satır biçimleri: sabit genişlik (kısa), uzun ("+" eki ya da
*KEYWORD LONG=Y) ve virgüllü serbest biçim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED_SUFFIXES = (".k", ".dyn", ".key")
_MAX_INCLUDE_DEPTH = 10

# Kısa biçim alan genişlikleri; uzun biçimde hepsi 20.
_NODE_WIDTHS = (8, 16, 16, 16, 8, 8)
_ELEMENT_WIDTH = 8
_CARD_WIDTH = 10
_LONG_WIDTH = 20


class DynaParseError(ValueError):
    """Dosya okunamadı ya da bir kart çözülemedi (dosya:satır ile)."""


@dataclass
class DynaPart:
    pid: int
    title: str
    secid: int
    mid: int


@dataclass
class DynaShellSection:
    secid: int
    elform: int
    thickness: tuple[float, float, float, float]


@dataclass
class DynaSolidSection:
    secid: int
    elform: int


@dataclass
class DynaMat024:
    """*MAT_024 ham değerleri (dosya birimlerinde)."""

    mid: int
    title: str
    ro: float
    e: float
    pr: float
    sigy: float
    etan: float
    fail: float
    tdel: float
    c: float
    p: float
    lcss: int
    lcsr: int
    vp: float
    eps: tuple[float, ...]
    es: tuple[float, ...]


@dataclass
class DynaMatElastic:
    """*MAT_001 ham değerleri."""

    mid: int
    title: str
    ro: float
    e: float
    pr: float
    da: float
    db: float
    k: float


@dataclass
class DynaMatRigid:
    """*MAT_020 ham değerleri (CMO/CON1/CON2: kütle merkezi kısıtı)."""

    mid: int
    title: str
    ro: float
    e: float
    pr: float
    cmo: float
    con1: float
    con2: float


@dataclass
class DynaCurve:
    """*DEFINE_CURVE; SFA/SFO/OFFA/OFFO uygulanmış noktalar."""

    lcid: int
    title: str
    points: list[tuple[float, float]]


@dataclass
class DynaModel:
    title: str = ""
    nodes: dict[int, tuple[float, float, float]] = field(default_factory=dict)
    # eid -> (pid, düğümler) — kabukta 4, solidde 8 ham düğüm
    shells: dict[int, tuple[int, tuple[int, ...]]] = field(default_factory=dict)
    solids: dict[int, tuple[int, tuple[int, ...]]] = field(default_factory=dict)
    parts: dict[int, DynaPart] = field(default_factory=dict)
    shell_sections: dict[int, DynaShellSection] = field(default_factory=dict)
    solid_sections: dict[int, DynaSolidSection] = field(default_factory=dict)
    mats_024: dict[int, DynaMat024] = field(default_factory=dict)
    mats_001: dict[int, DynaMatElastic] = field(default_factory=dict)
    mats_020: dict[int, DynaMatRigid] = field(default_factory=dict)
    curves: dict[int, DynaCurve] = field(default_factory=dict)
    # MID -> keyword adı (okunan ve atlanan tüm *MAT_* blokları)
    mat_keywords: dict[int, str] = field(default_factory=dict)
    # keyword adı -> atlanan blok sayısı
    skipped: dict[str, int] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, object]:
        return {
            "title": self.title,
            "nodes": len(self.nodes),
            "shells": len(self.shells),
            "solids": len(self.solids),
            "parts": len(self.parts),
            "shell_sections": len(self.shell_sections),
            "solid_sections": len(self.solid_sections),
            "mats_024": len(self.mats_024),
            "mats_001": len(self.mats_001),
            "mats_020": len(self.mats_020),
            "curves": len(self.curves),
            "skipped": dict(sorted(self.skipped.items())),
            "files": list(self.files),
            "warnings": list(self.warnings),
        }


@dataclass
class _Line:
    text: str
    where: str  # "dosya:satır"


@dataclass
class _Block:
    name: str  # büyük harf, ekler ("+", "-", "%") ayrılmış
    long: bool
    i10: bool
    where: str
    lines: list[_Line]


# --- alan çözme ---------------------------------------------------------


def _split(line: _Line, widths: tuple[int, ...]) -> list[str]:
    text = line.text.rstrip("\r\n")
    if "," in text:
        return [t.strip() for t in text.split(",")]
    out: list[str] = []
    pos = 0
    for w in widths:
        out.append(text[pos : pos + w].strip())
        pos += w
    return out


def _widths(n: int, short: int, long: bool) -> tuple[int, ...]:
    return (_LONG_WIDTH if long else short,) * n


def _int(fields: list[str], i: int, line: _Line, default: int = 0) -> int:
    raw = fields[i] if i < len(fields) else ""
    if raw == "":
        return default
    try:
        value = float(raw.replace("d", "e").replace("D", "E"))
    except ValueError:
        raise DynaParseError(f"{line.where}: tamsayı beklendi, '{raw}' okundu") from None
    if value != int(value):
        raise DynaParseError(f"{line.where}: tamsayı beklendi, '{raw}' okundu")
    return int(value)


def _float(fields: list[str], i: int, line: _Line, default: float = 0.0) -> float:
    raw = fields[i] if i < len(fields) else ""
    if raw == "":
        return default
    try:
        return float(raw.replace("d", "e").replace("D", "E"))
    except ValueError:
        raise DynaParseError(f"{line.where}: sayı beklendi, '{raw}' okundu") from None


# --- dosya → bloklar ----------------------------------------------------


def _read_text(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise DynaParseError(f"{path.name}: okunamadı ({exc})") from exc
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _parse_keyword(raw: str) -> tuple[str, bool, bool]:
    tokens = raw[1:].split()
    name = tokens[0].upper() if tokens else ""
    long = i10 = False
    while name and name[-1] in "+-%":
        long |= name[-1] == "+"
        i10 |= name[-1] == "%"
        name = name[:-1]
    for tok in tokens[1:]:
        long |= tok == "+"
        i10 |= tok == "%"
    return name, long, i10


def _blocks(text: str, label: str) -> list[_Block]:
    blocks: list[_Block] = []
    current: _Block | None = None
    for no, raw in enumerate(text.splitlines(), start=1):
        if raw.startswith("$"):
            continue
        where = f"{label}:{no}"
        if raw.startswith("*"):
            name, long, i10 = _parse_keyword(raw)
            current = _Block(name, long, i10, where, [_Line(raw, where)])
            blocks.append(current)
        elif current is not None:
            current.lines.append(_Line(raw, where))
    return blocks


# --- keyword okuyucular -------------------------------------------------


def _data(block: _Block) -> list[_Line]:
    """Başlık satırı hariç, boş satırlar atılmış veri kartları."""
    return [ln for ln in block.lines[1:] if ln.text.strip()]


def _read_nodes(block: _Block, model: DynaModel) -> None:
    widths = _widths(6, 0, True) if block.long else _NODE_WIDTHS
    for ln in _data(block):
        f = _split(ln, widths)
        nid = _int(f, 0, ln)
        if nid in model.nodes:
            raise DynaParseError(f"{ln.where}: düğüm {nid} ikinci kez tanımlı")
        model.nodes[nid] = (_float(f, 1, ln), _float(f, 2, ln), _float(f, 3, ln))


def _read_shells(block: _Block, model: DynaModel) -> None:
    widths = _widths(10, _ELEMENT_WIDTH, block.long)
    for ln in _data(block):
        f = _split(ln, widths)
        eid, pid = _int(f, 0, ln), _int(f, 1, ln)
        nodes = tuple(_int(f, i, ln) for i in range(2, 6))
        if any(_int(f, i, ln) for i in range(6, 10)):
            model.warnings.append(
                f"{ln.where}: kabuk {eid} 4'ten fazla düğüm taşıyor; ilk 4 alındı"
            )
        if eid in model.shells or eid in model.solids:
            raise DynaParseError(f"{ln.where}: eleman {eid} ikinci kez tanımlı")
        model.shells[eid] = (pid, nodes)


def _read_solids(block: _Block, model: DynaModel) -> None:
    widths = _widths(10, _ELEMENT_WIDTH, block.long)
    lines = _data(block)
    i = 0
    while i < len(lines):
        ln = lines[i]
        f = _split(ln, widths)
        eid, pid = _int(f, 0, ln), _int(f, 1, ln)
        node_fields = [_int(f, k, ln) for k in range(2, 10)]
        i += 1
        if not any(node_fields):
            # İki kartlı biçim: ikinci satırda düğümler (N1..N10).
            if i >= len(lines):
                raise DynaParseError(f"{ln.where}: solid {eid} düğüm kartı eksik")
            nl = lines[i]
            nf = _split(nl, widths)
            node_fields = [_int(nf, k, nl) for k in range(8)]
            if any(_int(nf, k, nl) for k in range(8, 10)):
                model.warnings.append(
                    f"{nl.where}: solid {eid} 8'den fazla düğüm taşıyor; ilk 8 alındı"
                )
            i += 1
        if eid in model.solids or eid in model.shells:
            raise DynaParseError(f"{ln.where}: eleman {eid} ikinci kez tanımlı")
        model.solids[eid] = (pid, tuple(node_fields))


def _read_parts(block: _Block, model: DynaModel) -> None:
    # Kart çiftleri: başlık + (PID SECID MID ...). Başlık boş olabilir.
    lines = block.lines[1:]
    widths = _widths(8, _CARD_WIDTH, block.long)
    while lines and not lines[-1].text.strip():
        lines.pop()
    if len(lines) % 2:
        raise DynaParseError(f"{block.where}: *PART kart sayısı tek ({len(lines)})")
    for k in range(0, len(lines), 2):
        title_ln, ln = lines[k], lines[k + 1]
        f = _split(ln, widths)
        pid = _int(f, 0, ln)
        if pid in model.parts:
            raise DynaParseError(f"{ln.where}: part {pid} ikinci kez tanımlı")
        model.parts[pid] = DynaPart(
            pid=pid,
            title=title_ln.text.strip(),
            secid=_int(f, 1, ln),
            mid=_int(f, 2, ln),
        )


def _read_shell_sections(block: _Block, model: DynaModel, titled: bool) -> None:
    lines = _data(block)
    widths = _widths(8, _CARD_WIDTH, block.long)
    i = 0
    while i < len(lines):
        if titled:
            i += 1
        if i + 1 >= len(lines):
            raise DynaParseError(f"{block.where}: *SECTION_SHELL kartı eksik")
        c1, c2 = lines[i], lines[i + 1]
        f1, f2 = _split(c1, widths), _split(c2, widths)
        secid = _int(f1, 0, c1)
        nip = _int(f1, 3, c1, default=2)
        icomp = _int(f1, 6, c1)
        t1 = _float(f2, 0, c2)
        thick = tuple(_float(f2, k, c2, default=t1) for k in range(1, 4))
        model.shell_sections[secid] = DynaShellSection(
            secid=secid, elform=_int(f1, 1, c1, default=2), thickness=(t1, *thick)
        )
        i += 2
        if icomp == 1:
            n_angle_cards = -(-max(nip, 1) // 8)
            model.warnings.append(
                f"{c1.where}: kesit {secid} katman açıları (ICOMP=1) okunmadı"
            )
            i += n_angle_cards


def _read_solid_sections(block: _Block, model: DynaModel, titled: bool) -> None:
    lines = _data(block)
    widths = _widths(8, _CARD_WIDTH, block.long)
    i = 0
    while i < len(lines):
        if titled:
            i += 1
        if i >= len(lines):
            raise DynaParseError(f"{block.where}: *SECTION_SOLID kartı eksik")
        c1 = lines[i]
        f1 = _split(c1, widths)
        secid = _int(f1, 0, c1)
        model.solid_sections[secid] = DynaSolidSection(
            secid=secid, elform=_int(f1, 1, c1, default=1)
        )
        i += 1


def _names(*bases: str) -> tuple[str, ...]:
    return tuple(n for b in bases for n in (b, f"{b}_TITLE"))


_MAT_001_NAMES = _names("MAT_001", "MAT_ELASTIC")
_MAT_020_NAMES = _names("MAT_020", "MAT_RIGID")
_MAT_024_NAMES = _names("MAT_024", "MAT_PIECEWISE_LINEAR_PLASTICITY")


def _cards(block: _Block) -> list[_Line]:
    """Başlık hariç kartlar; boş satır da kart sayılır (varsayılan değerler),
    yalnız sondaki boş satırlar atılır."""
    lines = list(block.lines[1:])
    while lines and not lines[-1].text.strip():
        lines.pop()
    return lines


def _mat_chunks(
    block: _Block, model: DynaModel, ncards: int
) -> list[tuple[str, int, list[tuple[_Line, list[str]]]]]:
    """*MAT_* bloğunu malzeme başına (başlık, MID, [(kart, alanlar)]) böler;
    MID'i `mat_keywords`'e kaydeder. Yazılmamış son kartlar varsayılan."""
    lines = _cards(block)
    widths = _widths(8, _CARD_WIDTH, block.long)
    titled = block.name.endswith("_TITLE")
    per = ncards + (1 if titled else 0)
    if 0 < len(lines) < per:
        lines += [_Line("", lines[-1].where)] * (per - len(lines))
    if not lines or len(lines) % per:
        raise DynaParseError(
            f"{block.where}: *{block.name} kart sayısı {len(lines)} ({per}'in katı değil)"
        )
    out = []
    for k in range(0, len(lines), per):
        title = lines[k].text.strip() if titled else ""
        cards = [(ln, _split(ln, widths)) for ln in lines[k + per - ncards : k + per]]
        c1, f1 = cards[0]
        mid = _int(f1, 0, c1)
        if mid in model.mat_keywords:
            raise DynaParseError(f"{c1.where}: malzeme {mid} ikinci kez tanımlı")
        model.mat_keywords[mid] = block.name
        out.append((title, mid, cards))
    return out


def _read_mat_024(block: _Block, model: DynaModel) -> None:
    for title, mid, cards in _mat_chunks(block, model, 4):
        (c1, f1), (c2, f2), (c3, f3), (c4, f4) = cards
        model.mats_024[mid] = DynaMat024(
            mid=mid,
            title=title,
            ro=_float(f1, 1, c1),
            e=_float(f1, 2, c1),
            pr=_float(f1, 3, c1),
            sigy=_float(f1, 4, c1),
            etan=_float(f1, 5, c1),
            fail=_float(f1, 6, c1, default=1.0e21),
            tdel=_float(f1, 7, c1),
            c=_float(f2, 0, c2),
            p=_float(f2, 1, c2),
            lcss=_int(f2, 2, c2),
            lcsr=_int(f2, 3, c2),
            vp=_float(f2, 4, c2),
            eps=tuple(_float(f3, i, c3) for i in range(8)),
            es=tuple(_float(f4, i, c4) for i in range(8)),
        )


def _read_mat_001(block: _Block, model: DynaModel) -> None:
    for title, mid, cards in _mat_chunks(block, model, 1):
        ((c1, f1),) = cards
        model.mats_001[mid] = DynaMatElastic(
            mid=mid,
            title=title,
            ro=_float(f1, 1, c1),
            e=_float(f1, 2, c1),
            pr=_float(f1, 3, c1),
            da=_float(f1, 4, c1),
            db=_float(f1, 5, c1),
            k=_float(f1, 6, c1),
        )


def _read_mat_020(block: _Block, model: DynaModel) -> None:
    for title, mid, cards in _mat_chunks(block, model, 3):
        (c1, f1), (c2, f2), _ = cards
        model.mats_020[mid] = DynaMatRigid(
            mid=mid,
            title=title,
            ro=_float(f1, 1, c1),
            e=_float(f1, 2, c1),
            pr=_float(f1, 3, c1),
            cmo=_float(f2, 0, c2),
            con1=_float(f2, 1, c2),
            con2=_float(f2, 2, c2),
        )


def _note_other_mat(block: _Block, model: DynaModel) -> None:
    """Çevrilmeyen *MAT_*: yalnız MID'i (ilk kartın ilk alanı) kaydedilir."""
    lines = _data(block)
    if block.name.endswith("_TITLE"):
        lines = lines[1:]
    if not lines:
        return
    f = _split(lines[0], _widths(1, _CARD_WIDTH, block.long))
    try:
        model.mat_keywords.setdefault(_int(f, 0, lines[0]), block.name)
    except DynaParseError:
        pass  # alfanümerik MID vb. — rapor için önemsiz


def _read_curve(block: _Block, model: DynaModel, titled: bool) -> None:
    lines = _data(block)
    title = ""
    if titled:
        title = lines[0].text.strip() if lines else ""
        lines = lines[1:]
    if not lines:
        raise DynaParseError(f"{block.where}: *DEFINE_CURVE kartı eksik")
    c1 = lines[0]
    f1 = _split(c1, _widths(8, _CARD_WIDTH, block.long))
    lcid = _int(f1, 0, c1)
    sfa = _float(f1, 2, c1) or 1.0
    sfo = _float(f1, 3, c1) or 1.0
    offa, offo = _float(f1, 4, c1), _float(f1, 5, c1)
    pts: list[tuple[float, float]] = []
    for ln in lines[1:]:
        f = _split(ln, _widths(2, 20, block.long))
        pts.append((sfa * (_float(f, 0, ln) + offa), sfo * (_float(f, 1, ln) + offo)))
    if lcid in model.curves:
        raise DynaParseError(f"{c1.where}: eğri {lcid} ikinci kez tanımlı")
    model.curves[lcid] = DynaCurve(lcid=lcid, title=title, points=pts)


# --- ana giriş ----------------------------------------------------------


def _skip(model: DynaModel, name: str) -> None:
    model.skipped[name] = model.skipped.get(name, 0) + 1


def _read_file(
    path: Path,
    root: Path,
    model: DynaModel,
    state: dict[str, bool],
    visited: set[Path],
    depth: int,
) -> None:
    label = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.name
    model.files.append(label)
    for block in _blocks(_read_text(path), label):
        name = block.name
        if name == "END":
            return
        if block.i10 or state["i10"]:
            model.warnings.append(f"{block.where}: *{name} I10 biçimi desteklenmiyor; atlandı")
            _skip(model, name)
            continue
        if state["long"]:
            block.long = True
        if name == "KEYWORD":
            opts = block.lines[0].text.upper().replace(" ", "")
            state["long"] = "LONG=Y" in opts or "LONG=S" in opts
            state["i10"] = "I10=Y" in opts
        elif name == "TITLE":
            data = _data(block)
            model.title = data[0].text.strip() if data else ""
        elif name == "INCLUDE":
            for ln in _data(block):
                _include(ln, path, root, model, state, visited, depth)
        elif name == "NODE":
            _read_nodes(block, model)
        elif name == "ELEMENT_SHELL":
            _read_shells(block, model)
        elif name == "ELEMENT_SOLID":
            _read_solids(block, model)
        elif name == "PART":
            _read_parts(block, model)
        elif name in ("SECTION_SHELL", "SECTION_SHELL_TITLE"):
            _read_shell_sections(block, model, titled=name.endswith("_TITLE"))
        elif name in ("SECTION_SOLID", "SECTION_SOLID_TITLE"):
            _read_solid_sections(block, model, titled=name.endswith("_TITLE"))
        elif name in _MAT_024_NAMES:
            _read_mat_024(block, model)
        elif name in _MAT_001_NAMES:
            _read_mat_001(block, model)
        elif name in _MAT_020_NAMES:
            _read_mat_020(block, model)
        elif name in ("DEFINE_CURVE", "DEFINE_CURVE_TITLE"):
            _read_curve(block, model, titled=name.endswith("_TITLE"))
        elif name.startswith("MAT_"):
            _note_other_mat(block, model)
            _skip(model, name)
        else:
            _skip(model, name)


def _include(
    ln: _Line,
    current: Path,
    root: Path,
    model: DynaModel,
    state: dict[str, bool],
    visited: set[Path],
    depth: int,
) -> None:
    name = ln.text.strip()
    target = (current.parent / name).resolve()
    # Yüklenen dosya sunucu yolu gösteremez: yalnız ana dosyanın klasörü.
    if not target.is_relative_to(root):
        model.warnings.append(f"{ln.where}: *INCLUDE '{name}' ana klasör dışında; atlandı")
        return
    if not target.is_file():
        model.warnings.append(f"{ln.where}: *INCLUDE '{name}' bulunamadı")
        return
    if target in visited:
        model.warnings.append(f"{ln.where}: *INCLUDE '{name}' döngüsel; atlandı")
        return
    if depth >= _MAX_INCLUDE_DEPTH:
        raise DynaParseError(f"{ln.where}: *INCLUDE derinliği {_MAX_INCLUDE_DEPTH}'u aştı")
    visited.add(target)
    _read_file(target, root, model, state, visited, depth + 1)


def _check_references(model: DynaModel) -> None:
    for kind, elems in (("kabuk", model.shells), ("solid", model.solids)):
        missing_parts = sorted({pid for pid, _ in elems.values()} - model.parts.keys())
        if missing_parts:
            model.warnings.append(f"{kind} elemanların part'ı tanımsız: {missing_parts[:10]}")
        missing_nodes = sorted(
            {n for _, nodes in elems.values() for n in nodes if n} - model.nodes.keys()
        )
        if missing_nodes:
            model.warnings.append(
                f"{kind} elemanlarda tanımsız düğüm ({len(missing_nodes)}): {missing_nodes[:10]}"
            )
    sections = model.shell_sections.keys() | model.solid_sections.keys()
    for part in model.parts.values():
        if part.secid not in sections:
            model.warnings.append(f"part {part.pid}: kesit {part.secid} tanımsız")


def read_keyword_file(path: str | Path) -> DynaModel:
    """`.k` / `.dyn` dosyasını (ve *INCLUDE'larını) okuyup ara modele çevirir."""
    main = Path(path).resolve()
    if main.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise DynaParseError(
            f"{main.name}: desteklenen uzantılar {', '.join(SUPPORTED_SUFFIXES)}"
        )
    model = DynaModel()
    _read_file(main, main.parent, model, {"long": False, "i10": False}, {main}, 0)
    _check_references(model)
    return model
