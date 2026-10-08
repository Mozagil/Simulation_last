"""OpenFOAM case yazıcı — Faz 2.1 (ESI v2412 sözdizimi).

Parametrelerden daimi, sıkıştırılamaz bir ``simpleFoam`` vakasının
``0/``, ``constant/`` ve ``system/`` dosyalarını üretir. Mesh (``constant/polyMesh``)
bu modülün işi değildir: 2.3'te ``blockMesh``, 2.5'te ``snappyHexMesh`` gelir;
yazıcı yalnız mesh'in yama (patch) adlarını bilir.

Birimler SI. Basınç OpenFOAM'un sıkıştırılamaz çözücülerindeki gibi
kinematiktir (p/ρ, m²/s²); ρ yalnız sonuç okumada (kuvvet, Δp) kullanılır.

Değerler mühendisindir: şema yalnız fiziksel geçerliliği denetler.
Varsayılanlar (çözücü ayarları, şemalar) resmi ``pitzDaily`` öğretici
vakasından alınmıştır.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

#: ``slip``: kaymalı duvar (tünel yanları; mesh yaması ``patch`` türünde kalır).
PatchKind = Literal["inlet", "outlet", "wall", "slip", "symmetry", "empty"]
TurbulenceModel = Literal["laminar", "kOmegaSST"]

#: k-ω SST için ω = √k / (Cμ^¼ · L)
C_MU = 0.09

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class CfdPatch(BaseModel):
    """Mesh'teki bir yama ve sınır koşulu türü."""

    name: str
    kind: PatchKind
    #: Giriş hızı (m/s) — yalnız ``inlet``.
    velocity_m_s: tuple[float, float, float] | None = None
    #: Çıkış statik basıncı, kinematik (m²/s²) — yalnız ``outlet``.
    pressure: float = 0.0

    @field_validator("name")
    @classmethod
    def _name_ok(cls, v: str) -> str:
        if not _NAME.match(v):
            raise ValueError(f"Yama adı '{v}' OpenFOAM için geçersiz (harf/rakam/_; rakamla başlamaz).")
        return v

    @model_validator(mode="after")
    def _inlet_velocity(self) -> "CfdPatch":
        if self.kind == "inlet":
            if self.velocity_m_s is None:
                raise ValueError(f"'{self.name}' girişinde hız (velocity_m_s) gerekli.")
            if not all(math.isfinite(c) for c in self.velocity_m_s):
                raise ValueError(f"'{self.name}' giriş hızı sonlu olmalı.")
        if not math.isfinite(self.pressure):
            raise ValueError(f"'{self.name}' basıncı sonlu olmalı.")
        return self


class CfdTurbulence(BaseModel):
    model: TurbulenceModel = "laminar"
    #: Giriş türbülans yoğunluğu I (0–1): k = 1.5·(|U|·I)²
    intensity: float = Field(0.05, gt=0, le=1)
    #: Türbülans uzunluk ölçeği L (m): ω = √k / (Cμ^¼·L)
    length_scale_m: float = Field(0.01, gt=0)


class CfdControl(BaseModel):
    """SIMPLE döngüsü; varsayılanlar pitzDaily."""

    iterations: int = Field(2000, gt=0)
    write_interval: int = Field(100, gt=0)
    residual_p: float = Field(1e-2, gt=0)
    residual_u: float = Field(1e-3, gt=0)
    residual_turbulence: float = Field(1e-3, gt=0)
    relax_u: float = Field(0.9, gt=0, le=1)
    relax_other: float = Field(0.9, gt=0, le=1)


class CfdForces(BaseModel):
    """Kuvvet / moment / katsayılar (2.4). Referans değerler mühendisindir.

    Cd = Fd / (½·ρ·U²·A), Cl benzer; Cm = M / (½·ρ·U²·A·l). Moment ``cofr_m``
    noktasına göre (basınç merkezi için). Sıkıştırılamazda ρ = case ρ.
    """

    patches: list[str] = Field(min_length=1)
    #: Birden çok yamada her yama için ayrı kuvvet (roket: burun / gövde / kanatçık).
    per_patch: bool = True
    cofr_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    drag_dir: tuple[float, float, float] = (1.0, 0.0, 0.0)
    lift_dir: tuple[float, float, float] = (0.0, 1.0, 0.0)
    pitch_axis: tuple[float, float, float] = (0.0, 0.0, 1.0)
    u_ref_m_s: float = Field(gt=0)
    l_ref_m: float = Field(gt=0)
    a_ref_m2: float = Field(gt=0)
    #: Kuvvet geçmişinin son N iterasyonunun ortalaması ve salınımı (veri).
    average_last: int = Field(50, gt=0)

    @model_validator(mode="after")
    def _dirs_ok(self) -> "CfdForces":
        for name in ("drag_dir", "lift_dir", "pitch_axis"):
            v = getattr(self, name)
            if not all(math.isfinite(c) for c in v) or math.hypot(*v) < 1e-12:
                raise ValueError(f"{name} sıfır olmayan sonlu bir vektör olmalı.")
        return self


class CfdCaseParams(BaseModel):
    #: Kinematik viskozite ν (m²/s)
    nu_m2_s: float = Field(gt=0)
    #: Yoğunluk ρ (kg/m³) — kuvvet / Δp dönüşümü için (2.4).
    rho_kg_m3: float = Field(1.0, gt=0)
    patches: list[CfdPatch] = Field(min_length=1)
    turbulence: CfdTurbulence = Field(default_factory=CfdTurbulence)
    control: CfdControl = Field(default_factory=CfdControl)
    #: İç alanın başlangıç hızı (m/s)
    initial_velocity_m_s: tuple[float, float, float] = (0.0, 0.0, 0.0)
    #: Alan ortalaması basıncı izlenecek yamalar (2.3; ör. inlet, outlet → Δp).
    monitor_patches: list[str] = Field(default_factory=list)
    #: Kuvvet / katsayı izleme (2.4) — dış akışta gövde yamaları.
    forces: CfdForces | None = None

    @model_validator(mode="after")
    def _patches_ok(self) -> "CfdCaseParams":
        names = [p.name for p in self.patches]
        dup = sorted({n for n in names if names.count(n) > 1})
        if dup:
            raise ValueError(f"Yama adları tekrar ediyor: {', '.join(dup)}")
        unknown = sorted(set(self.monitor_patches) - set(names))
        if self.forces is not None:
            unknown += sorted(set(self.forces.patches) - set(names))
        if unknown:
            raise ValueError(f"İzlenen yama mesh yama listesinde yok: {', '.join(unknown)}")
        kinds = {p.kind for p in self.patches}
        if "inlet" not in kinds or "outlet" not in kinds:
            raise ValueError("En az bir giriş (inlet) ve bir çıkış (outlet) yaması gerekli.")
        return self

    @property
    def turbulent(self) -> bool:
        return self.turbulence.model != "laminar"


# --------------------------------------------------------------- yazım yardımcıları


def _num(x: float) -> str:
    return f"{x:.6g}"


def _vec(v: tuple[float, float, float]) -> str:
    return f"({_num(v[0])} {_num(v[1])} {_num(v[2])})"


def _header(cls: str, obj: str, location: str | None = None) -> str:
    loc = f'    location    "{location}";\n' if location else ""
    return (
        "/*--------------------------------*- C++ -*----------------------------------*\\\n"
        "  SimSurrogate — OpenFOAM (ESI) case, otomatik üretildi\n"
        "\\*---------------------------------------------------------------------------*/\n"
        "FoamFile\n{\n"
        "    version     2.0;\n"
        "    format      ascii;\n"
        f"    class       {cls};\n"
        f"{loc}"
        f"    object      {obj};\n"
        "}\n\n"
    )


def _block(name: str, body: dict[str, str], indent: int = 4) -> str:
    pad = " " * indent
    lines = [f"{pad}{name}", f"{pad}{{"]
    for k, v in body.items():
        lines.append(f"{pad}    {k:<15} {v};")
    lines.append(f"{pad}}}")
    return "\n".join(lines)


def _field(cls: str, obj: str, dims: str, internal: str, patches: list[tuple[str, dict[str, str]]]) -> str:
    out = _header(cls, obj, "0")
    out += f"dimensions      {dims};\n\ninternalField   {internal};\n\nboundaryField\n{{\n"
    out += "\n".join(_block(name, body) for name, body in patches)
    out += "\n}\n"
    return out


def inlet_turbulence(speed: float, t: CfdTurbulence) -> tuple[float, float]:
    """Girişte (k, ω): k = 1.5·(|U|·I)², ω = √k / (Cμ^¼·L)."""
    k = 1.5 * (speed * t.intensity) ** 2
    omega = math.sqrt(k) / (C_MU**0.25 * t.length_scale_m) if k > 0 else 0.0
    return k, omega


# ------------------------------------------------------------------- dosyalar


def _u_file(p: CfdCaseParams) -> str:
    rows = []
    for patch in p.patches:
        if patch.kind == "inlet":
            body = {"type": "fixedValue", "value": f"uniform {_vec(patch.velocity_m_s)}"}  # type: ignore[arg-type]
        elif patch.kind == "outlet":
            body = {"type": "zeroGradient"}
        elif patch.kind == "wall":
            body = {"type": "noSlip"}
        elif patch.kind == "slip":
            body = {"type": "slip"}
        else:
            body = {"type": patch.kind}
        rows.append((patch.name, body))
    return _field("volVectorField", "U", "[0 1 -1 0 0 0 0]", f"uniform {_vec(p.initial_velocity_m_s)}", rows)


def _p_file(p: CfdCaseParams) -> str:
    rows = []
    for patch in p.patches:
        if patch.kind == "outlet":
            body = {"type": "fixedValue", "value": f"uniform {_num(patch.pressure)}"}
        elif patch.kind in ("inlet", "wall", "slip"):
            body = {"type": "zeroGradient"}
        else:
            body = {"type": patch.kind}
        rows.append((patch.name, body))
    return _field("volScalarField", "p", "[0 2 -2 0 0 0 0]", "uniform 0", rows)


def _turbulence_files(p: CfdCaseParams) -> dict[str, str]:
    inlets = {pt.name: inlet_turbulence(math.hypot(*pt.velocity_m_s), p.turbulence) for pt in p.patches if pt.kind == "inlet"}  # type: ignore[misc]
    k0 = max(k for k, _ in inlets.values())
    w0 = max(w for _, w in inlets.values())
    files: dict[str, str] = {}
    for obj, dims, internal, inlet_idx, wall in (
        ("k", "[0 2 -2 0 0 0 0]", k0, 0, "kqRWallFunction"),
        ("omega", "[0 0 -1 0 0 0 0]", w0, 1, "omegaWallFunction"),
    ):
        rows = []
        for patch in p.patches:
            if patch.kind == "inlet":
                body = {"type": "fixedValue", "value": f"uniform {_num(inlets[patch.name][inlet_idx])}"}
            elif patch.kind in ("outlet", "slip"):
                body = {"type": "zeroGradient"}
            elif patch.kind == "wall":
                body = {"type": wall, "value": f"uniform {_num(internal)}"}
            else:
                body = {"type": patch.kind}
            rows.append((patch.name, body))
        files[f"0/{obj}"] = _field("volScalarField", obj, dims, f"uniform {_num(internal)}", rows)
    rows = []
    for patch in p.patches:
        if patch.kind == "wall":
            body = {"type": "nutkWallFunction", "value": "uniform 0"}
        elif patch.kind in ("symmetry", "empty"):
            body = {"type": patch.kind}
        else:
            body = {"type": "calculated", "value": "uniform 0"}
        rows.append((patch.name, body))
    files["0/nut"] = _field("volScalarField", "nut", "[0 2 -1 0 0 0 0]", "uniform 0", rows)
    return files


def _transport(p: CfdCaseParams) -> str:
    return _header("dictionary", "transportProperties", "constant") + (
        f"transportModel  Newtonian;\n\nnu              {_num(p.nu_m2_s)};\n"
    )


def _turbulence_properties(p: CfdCaseParams) -> str:
    out = _header("dictionary", "turbulenceProperties", "constant")
    if not p.turbulent:
        return out + "simulationType  laminar;\n"
    return out + (
        "simulationType  RAS;\n\nRAS\n{\n"
        f"    RASModel        {p.turbulence.model};\n"
        "    turbulence      on;\n"
        "    printCoeffs     on;\n}\n"
    )


def _control_dict(p: CfdCaseParams) -> str:
    c = p.control
    return _header("dictionary", "controlDict", "system") + (
        "application     simpleFoam;\n"
        "startFrom       startTime;\n"
        "startTime       0;\n"
        "stopAt          endTime;\n"
        f"endTime         {c.iterations};\n"
        "deltaT          1;\n"
        "writeControl    timeStep;\n"
        f"writeInterval   {c.write_interval};\n"
        "purgeWrite      0;\n"
        "writeFormat     ascii;\n"
        "writePrecision  6;\n"
        "writeCompression off;\n"
        "timeFormat      general;\n"
        "timePrecision   6;\n"
        "runTimeModifiable true;\n"
        f"{_functions(p)}"
    )


def _functions(p: CfdCaseParams) -> str:
    """İzleme fonksiyonları → postProcessing/<ad>/0/*.dat (sonuç okuma).

    ``pAvg_<yama>``: yama alan ortalaması basınç; ``uMax``: alandaki en büyük |U|.
    """
    blocks = []
    for name in p.monitor_patches:
        blocks.append(
            f"    pAvg_{name}\n    {{\n"
            "        type            surfaceFieldValue;\n"
            "        libs            (fieldFunctionObjects);\n"
            "        writeControl    timeStep;\n"
            "        writeInterval   1;\n"
            "        log             false;\n"
            "        writeFields     false;\n"
            "        regionType      patch;\n"
            f"        name            {name};\n"
            "        operation       areaAverage;\n"
            "        fields          (p);\n"
            "    }"
        )
    blocks.append(
        "    uMax\n    {\n"
        "        type            fieldMinMax;\n"
        "        libs            (fieldFunctionObjects);\n"
        "        writeControl    timeStep;\n"
        "        writeInterval   1;\n"
        "        log             false;\n"
        "        mode            magnitude;\n"
        "        fields          (U);\n"
        "    }"
    )
    if p.forces is not None:
        blocks.extend(_force_blocks(p))
    return "\nfunctions\n{\n" + "\n\n".join(blocks) + "\n}\n"


def _fv_schemes(p: CfdCaseParams) -> str:
    turb = (
        "    turbulence      bounded Gauss limitedLinear 1;\n"
        "    div(phi,k)      $turbulence;\n"
        "    div(phi,omega)  $turbulence;\n"
        if p.turbulent
        else ""
    )
    return _header("dictionary", "fvSchemes", "system") + (
        "ddtSchemes\n{\n    default         steadyState;\n}\n\n"
        "gradSchemes\n{\n    default         Gauss linear;\n}\n\n"
        "divSchemes\n{\n"
        "    default         none;\n"
        "    div(phi,U)      bounded Gauss linearUpwind grad(U);\n"
        f"{turb}"
        "    div((nuEff*dev2(T(grad(U))))) Gauss linear;\n"
        "}\n\n"
        "laplacianSchemes\n{\n    default         Gauss linear corrected;\n}\n\n"
        "interpolationSchemes\n{\n    default         linear;\n}\n\n"
        "snGradSchemes\n{\n    default         corrected;\n}\n\n"
        "wallDist\n{\n    method          meshWave;\n}\n"
    )


def _fv_solution(p: CfdCaseParams) -> str:
    c = p.control
    fields = "(U|k|omega)" if p.turbulent else "U"
    turb_res = f'        "(k|omega)"     {_num(c.residual_turbulence)};\n' if p.turbulent else ""
    return _header("dictionary", "fvSolution", "system") + (
        "solvers\n{\n"
        "    p\n    {\n"
        "        solver          GAMG;\n"
        "        tolerance       1e-06;\n"
        "        relTol          0.1;\n"
        "        smoother        GaussSeidel;\n    }\n\n"
        f'    "{fields}"\n    {{\n'
        "        solver          smoothSolver;\n"
        "        smoother        symGaussSeidel;\n"
        "        tolerance       1e-05;\n"
        "        relTol          0.1;\n    }\n}\n\n"
        "SIMPLE\n{\n"
        "    nNonOrthogonalCorrectors 0;\n"
        "    consistent      yes;\n\n"
        "    residualControl\n    {\n"
        f"        p               {_num(c.residual_p)};\n"
        f"        U               {_num(c.residual_u)};\n"
        f"{turb_res}"
        "    }\n}\n\n"
        "relaxationFactors\n{\n    equations\n    {\n"
        f"        U               {_num(c.relax_u)};\n"
        f'        ".*"            {_num(c.relax_other)};\n'
        "    }\n}\n"
    )


def case_files(params: CfdCaseParams) -> dict[str, str]:
    """Göreli yol → dosya içeriği (diske yazmadan; testler için)."""
    files = {
        "0/U": _u_file(params),
        "0/p": _p_file(params),
        "constant/transportProperties": _transport(params),
        "constant/turbulenceProperties": _turbulence_properties(params),
        "system/controlDict": _control_dict(params),
        "system/fvSchemes": _fv_schemes(params),
        "system/fvSolution": _fv_solution(params),
    }
    if params.turbulent:
        files.update(_turbulence_files(params))
    return files


def write_case(params: CfdCaseParams, case_dir: Path) -> list[Path]:
    """Dosyaları ``case_dir`` altına yazar; yazılan yolları döndürür.

    Var olan ``constant/polyMesh`` ve ``system/blockMeshDict`` gibi mesh
    dosyalarına dokunmaz.
    """
    written = []
    for rel, text in case_files(params).items():
        path = Path(case_dir) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(path)
    return written


def _force_blocks(p: CfdCaseParams) -> list[str]:
    """``coeffs`` (forceCoeffs, tüm gövde), ``forces_total`` ve yama başına ``forces_<yama>``."""
    f = p.forces
    assert f is not None
    rho = _num(p.rho_kg_m3)

    def forces(name: str, patches: list[str]) -> str:
        return (
            f"    {name}\n    {{\n"
            "        type            forces;\n"
            "        libs            (forces);\n"
            "        writeControl    timeStep;\n"
            "        writeInterval   1;\n"
            "        log             false;\n"
            f"        patches         ({' '.join(patches)});\n"
            "        rho             rhoInf;\n"
            f"        rhoInf          {rho};\n"
            f"        CofR            {_vec(f.cofr_m)};\n"
            "    }"
        )

    out = [
        "    coeffs\n    {\n"
        "        type            forceCoeffs;\n"
        "        libs            (forces);\n"
        "        writeControl    timeStep;\n"
        "        writeInterval   1;\n"
        "        log             false;\n"
        f"        patches         ({' '.join(f.patches)});\n"
        "        rho             rhoInf;\n"
        f"        rhoInf          {rho};\n"
        f"        CofR            {_vec(f.cofr_m)};\n"
        f"        liftDir         {_vec(f.lift_dir)};\n"
        f"        dragDir         {_vec(f.drag_dir)};\n"
        f"        pitchAxis       {_vec(f.pitch_axis)};\n"
        f"        magUInf         {_num(f.u_ref_m_s)};\n"
        f"        lRef            {_num(f.l_ref_m)};\n"
        f"        Aref            {_num(f.a_ref_m2)};\n"
        "    }",
        forces("forces_total", f.patches),
    ]
    if f.per_patch and len(f.patches) > 1:
        out.extend(forces(f"forces_{name}", [name]) for name in f.patches)
    return out
