"""0.5.5 kalite seti: seçilen şablondan ~200 örnek, kapalı formla tarama.

Amaç veri toplamak DEĞİL, veri hattının güvenilir olduğunu kanıtlamak: her
örnek şablonun analitik çözümüyle karşılaştırılır ve `quality.classify_case`
ile etiketlenir. Bu yüzden yalnız analitiği olan şablonlar kabul edilir.

Aralıklar ŞABLONA ÖZGÜ ve sabittir (şema varsayılanının ±%20'si, ankastre
kirişte elle ayarlanmış). Kullanıcının form aralıkları bilerek kullanılmaz:
kalite seti bir REFERANS settir, aynı tohum + aynı aralıkla her zaman aynı
200 örneği üretmeli ki farklı zamanlardaki koşular karşılaştırılabilsin.
Kendi aralıklarını taramak isteyen "DOE başlat"ı örnek sayısını 200 yaparak
kullanır.

`material_ids` birden fazla verilirse örnekler malzemelere dengeli dağılır
(LHS kesikli boyut; 200 örnek + 2 malzeme = 100/100). Doğrusal statikte E
yalnız deplasmanı etkiler (σ ≈ E'den bağımsız), ama E model girdisinde olduğu
için tek malzemeyle eğitilen surrogate başka malzemeye genelleyemez.
"""

from __future__ import annotations

from app.doe.sampling import BcScenario, DoeSpec
from app.templates import GeometryTemplate, get_template

QUALITY_SET_N = 200
QUALITY_SET_SEED = 2026

#: Şema varsayılanının çevresinde taranacak yarı-genişlik.
_SPREAD = 0.2

#: Elle ayarlanmış aralıklar. Ankastre kiriş Faz 0'ın doğrulama vakası;
#: L/T ≥ 5 şablon kısıtı sağlansın diye alt/üst sınırlar seçilmiş
#: (min L / max T = 450/12 = 37.5).
_GEOMETRY_OVERRIDES: dict[str, dict[str, tuple[float, float]]] = {
    "cantilever_beam": {
        "length": (450.0, 700.0),
        "thickness": (8.0, 12.0),
        "width": (35.0, 70.0),
    },
}

#: Yük katsayısı aralığı: şablonun varsayılan yükü bununla ölçeklenir.
#: Yönü ve tipi korur, her şablonda çalışır (cload, pressure, bearing).
_LOAD_SCALE = (0.4, 1.6)


class QualitySetError(ValueError):
    """Şablon kalite seti için uygun değil."""


def _geometry_ranges(template: GeometryTemplate) -> dict[str, tuple[float, float]]:
    override = _GEOMETRY_OVERRIDES.get(template.id)
    if override is not None:
        return dict(override)
    ranges: dict[str, tuple[float, float]] = {}
    for name, prop in template.params_schema()["properties"].items():
        if prop.get("type") not in ("number", "integer"):
            continue  # enum alanları varsayılanda sabit kalır
        default = prop.get("default")
        if not isinstance(default, (int, float)) or default <= 0:
            continue
        ranges[name] = (default * (1 - _SPREAD), default * (1 + _SPREAD))
    if not ranges:
        raise QualitySetError(f"Şablon '{template.id}' için taranacak sayısal parametre yok.")
    return ranges


def quality_spec(
    template_id: str,
    material_ids: list[int],
    *,
    run_solver: bool = False,
    n_samples: int = QUALITY_SET_N,
    seed: int = QUALITY_SET_SEED,
) -> DoeSpec:
    """Seçilen şablon için kalite seti tanımı.

    Geçersiz parametre kombinasyonları örnekleme sırasında elenip yerine yenisi
    çekilir (bkz. `sample_spec`), bu yüzden ±%20 aralık şablon kısıtlarıyla
    çelişse bile set tam sayıda örnekle çıkar.
    """
    if not material_ids:
        raise ValueError("material_ids boş olamaz.")
    template = get_template(template_id)
    if template.analytic is None:
        raise QualitySetError(
            f"Şablon '{template_id}' için kapalı form çözüm yok; kalite seti "
            "sonuçları analitikle karşılaştırmaya dayanır."
        )
    if not template.default_bcs:
        raise QualitySetError(f"Şablon '{template_id}' varsayılan sınır koşulu tanımlamıyor.")

    return DoeSpec(
        name=f"kalite-{n_samples} {template.id}",
        template_id=template.id,
        seed=seed,
        n_samples=n_samples,
        geometry=_geometry_ranges(template),
        # Oranlı mesh: geometri tarandıkça çözünürlük sabit kalsın. Mutlak mm'de
        # aynı fizik %9.6–%21.8 gerilme sapması veriyor ve bazı örnekler mesh
        # yüzünden uyarı tetikliyor — kalite raporu okunamaz hale geliyor.
        element_ratio=template.default_element_ratio,
        load_scale=_LOAD_SCALE,
        material_ids=list(material_ids),
        bc_scenarios=[
            BcScenario(name="varsayilan", bcs=[dict(bc) for bc in template.default_bcs])
        ],
        dimension=3,
        element_scheme="tet",
        analysis_type="static",
        run_solver=run_solver,
    )


def cantilever_quality_spec(material_ids: list[int], *, run_solver: bool = False) -> DoeSpec:
    """Geriye dönük uyumluluk: Faz 0 doğrulama vakasının referans seti."""
    return quality_spec("cantilever_beam", material_ids, run_solver=run_solver)
