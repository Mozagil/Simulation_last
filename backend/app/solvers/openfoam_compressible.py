"""Sıkıştırılabilir OpenFOAM case dosyaları — Faz 2, R4 (ESI v2412 sözdizimi).

Kullanıcı kararı 2026-10-08: üç çözücü de bulunur, NLGEOM gibi seçilir
(otomatik seçim yok; Mach sayısı yalnız veri):

- ``rhoSimpleFoam`` (R4a): daimi, basınç tabanlı sıkıştırılabilir; ``transonic``
  seçeneği. Mach ~0.3–0.8. Ayarlar ESI ``aerofoilNACA0012`` öğreticisinden.
- ``rhoCentralFoam`` (R4b): yoğunluk tabanlı, şok yakalayan (Kurganov). Yerel
  zaman adımı (``localEuler``, LTS) ile sözde-daimi çözüm: her "zaman" adımı bir
  iterasyondur, Courant sınırı ``max_co``. Mach ~0.8 üstü. Ayarlar ESI
  ``forwardStep`` / ``biconic25-55Run35`` öğreticilerinden.

Akışkan ideal gaz (hava varsayılanları); μ = ρ·ν (case'in ν ve ρ'su serbest akım
değerleri). Basınç MUTLAK (Pa); çıkış yamasının ``pressure`` değeri serbest akım
basıncına eklenen gösterge basıncıdır. Duvarlar adyabatik.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.solvers.openfoam_case import CfdCaseParams


def _h():
    from app.solvers import openfoam_case as c

    return c


def _u_file(p: CfdCaseParams) -> str:
    c = _h()
    rows = []
    for patch in p.patches:
        if patch.kind == "inlet":
            body = {"type": "fixedValue", "value": f"uniform {c._vec(patch.velocity_m_s)}"}  # type: ignore[arg-type]
        elif patch.kind == "outlet":
            body = {"type": "zeroGradient"}
        elif patch.kind == "wall":
            body = {"type": "noSlip"}
        elif patch.kind == "slip":
            body = {"type": "slip"}
        elif patch.kind == "farfield":
            fs = f"uniform {c._vec(patch.velocity_m_s)}"  # type: ignore[arg-type]
            body = {"type": "freestreamVelocity", "freestreamValue": fs, "value": fs}
        else:
            body = {"type": patch.kind}
        rows.append((patch.name, body))
    return c._field("volVectorField", "U", "[0 1 -1 0 0 0 0]", f"uniform {c._vec(p.initial_velocity_m_s)}", rows)


def _p_file(p: CfdCaseParams) -> str:
    c = _h()
    p_inf = p.compressible.p_inf_pa
    rows = []
    for patch in p.patches:
        if patch.kind == "outlet":
            body = {"type": "fixedValue", "value": f"uniform {c._num(p_inf + patch.pressure)}"}
        elif patch.kind == "farfield":
            v = f"uniform {c._num(p_inf + patch.pressure)}"
            body = {"type": "freestreamPressure", "freestreamValue": v, "value": v}
        elif patch.kind in ("inlet", "wall", "slip"):
            body = {"type": "zeroGradient"}
        else:
            body = {"type": patch.kind}
        rows.append((patch.name, body))
    return c._field("volScalarField", "p", "[1 -1 -2 0 0 0 0]", f"uniform {c._num(p_inf)}", rows)


def _t_file(p: CfdCaseParams) -> str:
    c = _h()
    t = c._num(p.compressible.t_inf_k)
    rows = []
    for patch in p.patches:
        if patch.kind == "inlet":
            body = {"type": "fixedValue", "value": f"uniform {t}"}
        elif patch.kind in ("outlet", "farfield"):
            body = {"type": "inletOutlet", "inletValue": f"uniform {t}", "value": f"uniform {t}"}
        elif patch.kind in ("wall", "slip"):
            body = {"type": "zeroGradient"}
        else:
            body = {"type": patch.kind}
        rows.append((patch.name, body))
    return c._field("volScalarField", "T", "[0 0 0 1 0 0 0]", f"uniform {t}", rows)


def _alphat_file(p: CfdCaseParams) -> str:
    c = _h()
    rows = []
    for patch in p.patches:
        if patch.kind == "wall":
            body = {"type": "compressible::alphatWallFunction", "value": "uniform 0"}
        elif patch.kind in ("symmetry", "empty"):
            body = {"type": patch.kind}
        else:
            body = {"type": "calculated", "value": "uniform 0"}
        rows.append((patch.name, body))
    return c._field("volScalarField", "alphat", "[1 -1 -1 0 0 0 0]", "uniform 0", rows)


def _thermo(p: CfdCaseParams) -> str:
    c = _h()
    g = p.compressible
    mu = p.rho_kg_m3 * p.nu_m2_s
    return c._header("dictionary", "thermophysicalProperties", "constant") + (
        "thermoType\n{\n"
        "    type            hePsiThermo;\n"
        "    mixture         pureMixture;\n"
        "    transport       const;\n"
        "    thermo          hConst;\n"
        "    equationOfState perfectGas;\n"
        "    specie          specie;\n"
        "    energy          sensibleInternalEnergy;\n}\n\n"
        "mixture\n{\n"
        f"    specie\n    {{\n        molWeight   {c._num(g.mol_weight)};\n    }}\n"
        f"    thermodynamics\n    {{\n        Cp          {c._num(g.cp)};\n        Hf          0;\n    }}\n"
        f"    transport\n    {{\n        mu          {c._num(mu)};\n        Pr          {c._num(g.prandtl)};\n    }}\n"
        "}\n"
    )


def _control_dict(p: CfdCaseParams) -> str:
    c = _h()
    ctl = p.control
    central = p.solver == "rhoCentralFoam"
    extra = f"adjustTimeStep  no;\nmaxCo           {c._num(p.compressible.max_co)};\nrDeltaTSmoothingCoeff 0.02;\n" if central else ""
    return c._header("dictionary", "controlDict", "system") + (
        f"application     {p.solver};\n"
        "startFrom       startTime;\n"
        "startTime       0;\n"
        "stopAt          endTime;\n"
        f"endTime         {ctl.iterations};\n"
        "deltaT          1;\n"
        "writeControl    timeStep;\n"
        f"writeInterval   {ctl.write_interval};\n"
        "purgeWrite      0;\n"
        "writeFormat     ascii;\n"
        "writePrecision  8;\n"
        "writeCompression off;\n"
        "timeFormat      general;\n"
        "timePrecision   6;\n"
        "runTimeModifiable true;\n"
        f"{extra}"
        f"{c._functions(p)}"
    )


def _fv_schemes(p: CfdCaseParams) -> str:
    c = _h()
    turb = (
        "    turbulence      bounded Gauss upwind;\n"
        "    div(phi,k)      $turbulence;\n"
        "    div(phi,omega)  $turbulence;\n"
        if p.turbulent
        else ""
    )
    tail = (
        "laplacianSchemes\n{\n    default         Gauss linear corrected;\n}\n\n"
        "snGradSchemes\n{\n    default         corrected;\n}\n\n"
        "wallDist\n{\n    method          meshWave;\n}\n"
    )
    if p.solver == "rhoCentralFoam":
        return c._header("dictionary", "fvSchemes", "system") + (
            "fluxScheme      Kurganov;\n\n"
            "ddtSchemes\n{\n    default         localEuler;\n}\n\n"
            "gradSchemes\n{\n    default         Gauss linear;\n}\n\n"
            "divSchemes\n{\n    default         none;\n    div(tauMC)      Gauss linear;\n"
            f"{turb}"
            "}\n\n"
            "interpolationSchemes\n{\n    default         linear;\n"
            "    reconstruct(rho) vanLeer;\n    reconstruct(U)  vanLeerV;\n    reconstruct(T)  vanLeer;\n}\n\n" + tail
        )
    transonic = "    div(phid,p)     Gauss upwind;\n" if p.compressible.transonic else ""
    return c._header("dictionary", "fvSchemes", "system") + (
        "ddtSchemes\n{\n    default         steadyState;\n}\n\n"
        "gradSchemes\n{\n    default         Gauss linear;\n    limited         cellLimited Gauss linear 1;\n"
        "    grad(U)         $limited;\n    grad(k)         $limited;\n    grad(omega)     $limited;\n}\n\n"
        "divSchemes\n{\n    default         none;\n"
        "    div(phi,U)      bounded Gauss linearUpwind limited;\n"
        "    energy          bounded Gauss linearUpwind limited;\n"
        "    div(phi,e)      $energy;\n    div(phi,K)      $energy;\n    div(phi,Ekp)    $energy;\n"
        f"{turb}"
        f"{transonic}"
        "    div((phi|interpolate(rho)),p)  bounded Gauss upwind;\n"
        "    div(((rho*nuEff)*dev2(T(grad(U)))))    Gauss linear;\n}\n\n"
        "interpolationSchemes\n{\n    default         linear;\n}\n\n" + tail
    )


def _fv_solution(p: CfdCaseParams) -> str:
    c = _h()
    ctl = p.control
    if p.solver == "rhoCentralFoam":
        return c._header("dictionary", "fvSolution", "system") + (
            "solvers\n{\n"
            '    "(rho|rhoU|rhoE)"\n    {\n        solver          diagonal;\n    }\n\n'
            '    "(U|e|k|omega)"\n    {\n        solver          smoothSolver;\n        smoother        GaussSeidel;\n'
            "        nSweeps         2;\n        tolerance       1e-09;\n        relTol          0.01;\n    }\n}\n"
        )
    turb_res = f'        "(k|omega|e)"   {c._num(ctl.residual_turbulence)};\n'
    transonic = "    transonic       yes;\n" if p.compressible.transonic else ""
    return c._header("dictionary", "fvSolution", "system") + (
        "solvers\n{\n"
        "    p\n    {\n        solver          GAMG;\n        smoother        GaussSeidel;\n"
        "        tolerance       1e-6;\n        relTol          0.01;\n    }\n\n"
        '    "(U|k|omega|e)"\n    {\n        solver          PBiCGStab;\n        preconditioner  DILU;\n'
        "        tolerance       1e-6;\n        relTol          0.1;\n    }\n}\n\n"
        "SIMPLE\n{\n"
        f"{transonic}"
        "    residualControl\n    {\n"
        f"        p               {c._num(ctl.residual_p)};\n"
        f"        U               {c._num(ctl.residual_u)};\n"
        f"{turb_res}"
        "    }\n"
        "    nNonOrthogonalCorrectors 0;\n    pMinFactor      0.1;\n    pMaxFactor      2;\n}\n\n"
        "relaxationFactors\n{\n"
        f"    fields\n    {{\n        p               {c._num(p.compressible.relax_p)};\n        rho             {c._num(p.compressible.relax_rho)};\n    }}\n"
        f"    equations\n    {{\n        U               {c._num(ctl.relax_u)};\n        e               {c._num(ctl.relax_other)};\n"
        f'        "(k|omega)"     {c._num(ctl.relax_other)};\n    }}\n}}\n'
    )


def compressible_case_files(p: CfdCaseParams) -> dict[str, str]:
    c = _h()
    files = {
        "0/U": _u_file(p),
        "0/p": _p_file(p),
        "0/T": _t_file(p),
        "constant/thermophysicalProperties": _thermo(p),
        "constant/turbulenceProperties": c._turbulence_properties(p),
        "system/controlDict": _control_dict(p),
        "system/fvSchemes": _fv_schemes(p),
        "system/fvSolution": _fv_solution(p),
    }
    if p.turbulent:
        files.update(c._turbulence_files(p))
        files["0/alphat"] = _alphat_file(p)
    return files
