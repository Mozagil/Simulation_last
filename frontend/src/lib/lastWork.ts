/**
 * 1.23 B3b — son crash çalışması (tarayıcıda, kullanıcı başına kolaylık).
 *
 * Crash sekmesinde geometri yüklenince kaydedilir: geometri + (geçmişten yüklendiyse)
 * koşu no + mesh boyutu. F5'te `auto` açıksa kendiliğinden yeniden açılır; "Yeni Case
 * Başlat" `auto`'yu kapatır (kayıt durur, boş ekranda "Son çalışmayı aç" ile açılır).
 * Paneldeki kaydedilmemiş düzenlemeler burada yok — koşu yüklemesi koşunun kendi kurulumunu
 * getirir. Depolama yoksa / bozuksa sessizce yok sayılır.
 */

export interface LastWork {
  geometryId: number;
  name: string;
  runId: number | null;
  dim: 2 | 3 | null;
  auto: boolean;
}

const KEY = "crashLastWork";

export function readLastWork(): LastWork | null {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const v = JSON.parse(raw) as Partial<LastWork>;
    if (typeof v.geometryId !== "number" || !(v.geometryId > 0)) return null;
    return {
      geometryId: v.geometryId,
      name: typeof v.name === "string" && v.name ? v.name : `geometri #${v.geometryId}`,
      runId: typeof v.runId === "number" && v.runId > 0 ? v.runId : null,
      dim: v.dim === 2 || v.dim === 3 ? v.dim : null,
      auto: v.auto !== false,
    };
  } catch {
    return null;
  }
}

export function saveLastWork(w: LastWork) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(w));
  } catch {
    /* depolama yoksa yalnız bu oturum */
  }
}

/** "Yeni Case Başlat": kayıt kalır, F5'te kendiliğinden açılmaz. */
export function pauseLastWork() {
  const w = readLastWork();
  if (w) saveLastWork({ ...w, auto: false });
}

/** Son çalışma etiketi: "koşu #325 · geometri #4277" ya da dosya adı. */
export function lastWorkLabel(w: LastWork): string {
  return w.runId ? `koşu #${w.runId} · geometri #${w.geometryId}` : w.name;
}
