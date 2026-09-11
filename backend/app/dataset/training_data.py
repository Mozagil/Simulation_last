"""Surrogate eğitimi için düğüm bazlı veri seti üretimi.

NEDEN VAR: `.frd` ASCII ve eğitimde gerekmeyen çok şey içeriyor (tam gerilme
tensörü, başlık blokları, formatlama). Ölçüm (7205 düğümlü tet10 referans
vakası): ham `.frd` ~5.4 MB/run, bu modülün ürettiği `.npz` ~0.72 MB. 20.000
run'da 108 GB ile 14 GB farkı.

İkinci ve daha önemli fayda: eğitimde her epoch'ta ASCII parse etmek veri
yükleme darboğazı yaratır. `.npz` float32 ve rastgele erişilebilir.

İKİ AŞAMALI YAZIM: Düğüm GİRDİLERİ (BC bayrakları, malzeme) `.inp` yazılırken
üretilir, çünkü sınır koşulu → düğüm eşlemesi (`nsets`) yalnız orada eldedir.
Düğüm ÇIKTILARI (deplasman, von Mises) çözümden sonra eklenir. Alternatif —
çözüm sonrası nset'leri yeniden hesaplamak — hem yavaş hem de iki yol
arasında sessiz tutarsızlık riski taşırdı.

GRAF ŞEMASI (bkz. ROADMAP Faz 0.5): mesh bir graftır. Eleman boyutu parametre
olduğu için düğüm sayısı run'dan run'a değişir; bu yüzden sabit boyutlu
vektör isteyen PCA/POD elenmiş, mesh-graf (GNN) mimarisi seçilmiştir.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

#: Düğüm girdi kanallarının SIRASI. Eğitim kodu bu sıraya güvenir; değişirse
#: eski `.npz` dosyaları sessizce yanlış yorumlanır, o yüzden sürümlenir.
NODE_INPUT_CHANNELS = (
    "x",
    "y",
    "z",
    "fixed_ux",      # 1 = bu DOF sabitlenmiş
    "fixed_uy",
    "fixed_uz",
    "fixed_rot",     # kabukta dönme DOF'ları da sabit mi (solidde daima 0)
    "load_fx",       # düğüme düşen kuvvet bileşeni (N)
    "load_fy",
    "load_fz",
    "youngs_modulus_mpa",
    "poisson_ratio",
    "density_tonne_mm3",
    "shell_thickness_mm",  # solidde 0
)

NODE_OUTPUT_CHANNELS = ("u_x", "u_y", "u_z", "von_mises_mpa")

#: Modal çıktı kanalları — mod BAŞINA düğüm bazlı şekil.
MODE_OUTPUT_CHANNELS = ("u_x", "u_y", "u_z")

DATASET_SCHEMA_VERSION = 2


def build_node_inputs(
    node_coords: list[tuple[float, float, float]],
    bcs: list[dict[str, Any]],
    nsets: dict[str, list[int]],
    materials: list[dict[str, Any]],
    dimension: int,
    shell_thickness: float,
    resolve_node_ids,
) -> np.ndarray:
    """Düğüm başına girdi matrisi (n_nodes × len(NODE_INPUT_CHANNELS)).

    `resolve_node_ids`: `_resolve_bc_node_ids` fonksiyonu — CAD vertex'ini
    POINT_ nset'i üzerinden mesh düğümüne çeviren mantık burada YENİDEN
    YAZILMAZ, çağıran tarafından geçilir. (O mantıkta daha önce sessiz bir
    hata bulundu; tek bir yerde kalması önemli.)
    """
    n = len(node_coords)
    X = np.zeros((n, len(NODE_INPUT_CHANNELS)), dtype=np.float32)

    # --- Koordinatlar ---
    for i, (x, y, z) in enumerate(node_coords):
        X[i, 0] = x
        X[i, 1] = y
        X[i, 2] = z

    idx = {name: k for k, name in enumerate(NODE_INPUT_CHANNELS)}

    def nodes_of(bc: dict[str, Any]) -> list[int]:
        """BC'nin hedeflediği mesh düğüm numaraları (1-based)."""
        out: list[int] = []
        for fid in bc.get("face_ids") or []:
            out.extend(nsets.get(f"FACE_{int(fid)}") or [])
        for eid in bc.get("edge_ids") or []:
            out.extend(nsets.get(f"EDGE_{int(eid)}") or [])
        out.extend(resolve_node_ids(bc, nsets))
        return list(dict.fromkeys(out))

    for bc in bcs:
        btype = str(bc.get("type") or "").lower()
        targets = nodes_of(bc)
        if not targets:
            continue

        if btype == "fixed":
            for nid in targets:
                i = nid - 1
                if 0 <= i < n:
                    X[i, idx["fixed_ux"]] = 1.0
                    X[i, idx["fixed_uy"]] = 1.0
                    X[i, idx["fixed_uz"]] = 1.0
                    # Kabukta ankastre mesnet dönmeleri de kısıtlar (1..6).
                    # Bu ayrım gerçek bir hatanın kaynağıydı: yalnız
                    # ötelemeler sabitlenince kabuk kenar etrafında serbestçe
                    # dönüyordu. Model için anlamlı bir girdi.
                    X[i, idx["fixed_rot"]] = 1.0 if dimension == 2 else 0.0

        elif btype == "displacement":
            dofs = bc.get("dofs") or {}
            for nid in targets:
                i = nid - 1
                if not (0 <= i < n):
                    continue
                for dof in dofs:
                    d = int(dof)
                    if d == 1:
                        X[i, idx["fixed_ux"]] = 1.0
                    elif d == 2:
                        X[i, idx["fixed_uy"]] = 1.0
                    elif d == 3:
                        X[i, idx["fixed_uz"]] = 1.0

        elif btype == "cload":
            # Toplam kuvvet düğümlere EŞİT bölünür — `.inp` yazıcısıyla aynı
            # kural. Düğüm başına düşen değeri yazmak, toplamı yazmaktan
            # daha doğru bir girdi: model yerel etkiyi görür.
            k = len(targets)
            fx = float(bc.get("fx") or 0.0) / k
            fy = float(bc.get("fy") or 0.0) / k
            fz = float(bc.get("fz") or 0.0) / k
            for nid in targets:
                i = nid - 1
                if 0 <= i < n:
                    X[i, idx["load_fx"]] += fx
                    X[i, idx["load_fy"]] += fy
                    X[i, idx["load_fz"]] += fz

    # --- Malzeme ---
    # SINIRLAMA: çok parçalı modelde parça başına malzeme düğümlere
    # eşlenmiyor, ilk malzeme tüm düğümlere yayılıyor. Faz 0.4/0.5'te tek
    # parçalı şablonlarla çalışılacağı için şimdilik yeterli; çok parçalı
    # vakalar geldiğinde elset → düğüm eşlemesi gerekecek.
    if materials:
        m = materials[0]
        E_mpa = float(m.get("youngs_modulus") or 0.0) / 1e6
        nu = float(m.get("poisson_ratio") or 0.0)
        rho = float(m.get("density") or 0.0) * 1e-12
        X[:, idx["youngs_modulus_mpa"]] = E_mpa
        X[:, idx["poisson_ratio"]] = nu
        X[:, idx["density_tonne_mm3"]] = rho

    if dimension == 2:
        X[:, idx["shell_thickness_mm"]] = float(shell_thickness)

    return X


def write_inputs(path: Path, X: np.ndarray, connectivity: np.ndarray | None) -> None:
    """Girdi matrisini ve graf bağlantısını `.inp` yanına yazar."""
    np.savez_compressed(
        path,
        schema_version=np.int32(DATASET_SCHEMA_VERSION),
        node_inputs=X,
        input_channels=np.array(NODE_INPUT_CHANNELS),
        connectivity=connectivity if connectivity is not None else np.zeros((0, 0), np.int32),
    )
    logger.info("Eğitim girdileri yazıldı: %s (%d düğüm)", path, X.shape[0])


def normalize_mode_shape(vectors: np.ndarray) -> tuple[np.ndarray, float]:
    """Mod şeklini birim maksimum büyüklüğe normalize eder.

    KRİTİK: mod şekilleri ÖZVEKTÖRDÜR, mutlak genlikleri fiziksel anlam
    taşımaz — çözücü keyfi normalize eder ve aynı fiziksel mod iki run'da
    kat kat farklı genlikte gelebilir. Ham haliyle hedef olarak verilirse
    model öğrenilemez bir büyüklüğü öğrenmeye çalışır ve hata metriği
    anlamsızlaşır.

    Ölçek çarpanı ayrıca döndürülür: atılmaz, çünkü ileride mod katılım
    faktörü / efektif kütle gibi büyüklükler gerekirse geri hesaplanabilsin.
    """
    mags = np.linalg.norm(vectors, axis=1)
    peak = float(mags.max()) if mags.size else 0.0
    if peak <= 1e-30:
        return vectors.astype(np.float32), 0.0
    return (vectors / peak).astype(np.float32), peak


def write_modal_sample(
    inputs_path: Path,
    out_path: Path,
    node_order: list[int],
    modes: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Modal eğitim örneği: mod başına şekil + frekans.

    STATİKTEN FARKI: çıktı tek bir alan değil, MOD BAŞINA bir alan artı
    skaler frekans. Statik şemaya zorla sığdırmak, modal `.frd`'de gerilme
    bloğu olmadığı ve `displacement` yalnız son modu tuttuğu için "sıfır
    gerilmeli statik çözüm" gibi görünen anlamsız bir örnek üretiyordu.

    Mod şekilleri `normalize_mode_shape` ile birim maksimuma çekilir.

    MOD SIRASI UYARISI: burada saklanan sıra çözücünün döndürdüğü sıradır.
    İki farklı geometride aynı indeksteki modun aynı FİZİKSEL mod olduğu
    GARANTİ DEĞİLDİR (kesit oranı değişince eğilme modları yer değiştirir).
    Eğitim kodu modları indekse göre eşleştirecekse bunu bilerek yapmalı;
    şekil korelasyonuna (MAC) dayalı eşleştirme daha güvenlidir.
    """
    if not inputs_path.is_file():
        logger.warning("Eğitim girdileri bulunamadı: %s", inputs_path)
        return None
    if not modes:
        logger.warning("Modal örnek atlandı: mod yok")
        return None

    with np.load(inputs_path, allow_pickle=False) as z:
        X = z["node_inputs"]
        connectivity = z["connectivity"]

    n = X.shape[0]
    if len(node_order) != n:
        logger.warning(
            "Modal örnek atlandı — düğüm sayısı uyuşmuyor: girdi=%d, sonuç=%d",
            n,
            len(node_order),
        )
        return None

    shapes = np.zeros((len(modes), n, 3), dtype=np.float32)
    freqs = np.zeros(len(modes), dtype=np.float32)
    scales = np.zeros(len(modes), dtype=np.float32)
    for k, m in enumerate(modes):
        vecs = np.asarray(m.get("displacement_vectors") or [], dtype=np.float64)
        if vecs.shape != (n, 3):
            logger.warning("Modal örnek atlandı — mod %d şekli hizasız", k + 1)
            return None
        shapes[k], scales[k] = normalize_mode_shape(vecs)
        f = m.get("frequency_hz")
        freqs[k] = float(f) if f is not None else np.nan

    np.savez_compressed(
        out_path,
        schema_version=np.int32(DATASET_SCHEMA_VERSION),
        analysis_type=np.array("modal"),
        node_inputs=X,
        input_channels=np.array(NODE_INPUT_CHANNELS),
        mode_shapes=shapes,
        mode_frequencies_hz=freqs,
        mode_scale_factors=scales,
        mode_output_channels=np.array(MODE_OUTPUT_CHANNELS),
        connectivity=connectivity,
        node_ids=np.array(node_order, dtype=np.int32),
    )
    info = {
        "path": str(out_path),
        "nodes": n,
        "modes": len(modes),
        "bytes": out_path.stat().st_size,
    }
    logger.info(
        "Modal eğitim örneği yazıldı: %s (%d düğüm, %d mod, %d B)",
        out_path,
        n,
        len(modes),
        info["bytes"],
    )
    return info


def write_training_sample(
    inputs_path: Path,
    out_path: Path,
    node_order: list[int],
    disp_vectors: list[list[float]],
    von_mises: list[float],
) -> dict[str, Any] | None:
    """Statik eğitim örneği: girdiler + düğüm başına deplasman ve von Mises.

    `node_order` `.frd`'den gelen düğüm sırasıdır ve `.inp`'teki 1-based
    sırayla eşleşmelidir. Eşleşmezse ÖRNEK YAZILMAZ: hizasız bir eğitim
    örneği, eksik örnekten çok daha kötüdür — model yanlış düğümün cevabını
    öğrenir ve bu hiçbir metrikte görünmez.
    """
    if not inputs_path.is_file():
        logger.warning("Eğitim girdileri bulunamadı: %s", inputs_path)
        return None

    with np.load(inputs_path, allow_pickle=False) as z:
        X = z["node_inputs"]
        connectivity = z["connectivity"]

    n = X.shape[0]
    if len(node_order) != n:
        logger.warning(
            "Eğitim örneği atlandı — düğüm sayısı uyuşmuyor: girdi=%d, sonuç=%d",
            n,
            len(node_order),
        )
        return None

    Y = np.zeros((n, len(NODE_OUTPUT_CHANNELS)), dtype=np.float32)
    for i in range(n):
        dv = disp_vectors[i] if i < len(disp_vectors) else (0.0, 0.0, 0.0)
        Y[i, 0] = dv[0]
        Y[i, 1] = dv[1]
        Y[i, 2] = dv[2]
        Y[i, 3] = von_mises[i] if i < len(von_mises) else 0.0

    np.savez_compressed(
        out_path,
        schema_version=np.int32(DATASET_SCHEMA_VERSION),
        analysis_type=np.array("static"),
        node_inputs=X,
        node_outputs=Y,
        input_channels=np.array(NODE_INPUT_CHANNELS),
        output_channels=np.array(NODE_OUTPUT_CHANNELS),
        connectivity=connectivity,
        node_ids=np.array(node_order, dtype=np.int32),
    )
    info = {
        "path": str(out_path),
        "nodes": n,
        "bytes": out_path.stat().st_size,
    }
    logger.info("Eğitim örneği yazıldı: %s (%d düğüm, %d B)", out_path, n, info["bytes"])
    return info


def gzip_frd(frd_path: Path) -> Path | None:
    """`.frd`'yi gzip'leyip orijinali siler.

    KAYIPSIZ bilerek: kayıplı sıkıştırma (femzip vb.) görselleştirme için
    sorun değil ama eğitim etiketi olarak tehlikeli — modelin hatasıyla
    sıkıştırmanın hatası birbirine karışır ve modelin gerçek doğruluğu
    ölçülemez hale gelir.

    Arşiv olarak tutuluyor: ileride farklı bir çıktı gerekirse (ör. tam
    gerilme tensörü) yeniden çözmek zorunda kalınmasın.
    """
    import gzip
    import shutil as _shutil

    if not frd_path.is_file():
        return None
    gz = frd_path.with_suffix(frd_path.suffix + ".gz")
    try:
        with frd_path.open("rb") as src, gzip.open(gz, "wb", compresslevel=6) as dst:
            _shutil.copyfileobj(src, dst)
        before = frd_path.stat().st_size
        after = gz.stat().st_size
        frd_path.unlink()
        logger.info(
            "FRD sıkıştırıldı: %s (%.1f MB -> %.1f MB, %.1fx)",
            gz,
            before / 1e6,
            after / 1e6,
            before / after if after else 0,
        )
        return gz
    except OSError as exc:  # noqa: BLE001 — sıkıştırma çözümü bozmasın
        logger.warning("FRD sıkıştırılamadı: %s", exc)
        return None
