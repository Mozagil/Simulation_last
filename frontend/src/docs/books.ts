/**
 * Belgeler penceresinin "kitapları" (sekmeler): Crash · Durability · ML
 * (kullanıcı 2026-10-08). Her kitap aynı düzende gösterilir: bölümler
 * (öğe tablosu + görsel), isteğe bağlı hazır senaryolar, LS-DYNA eşleme
 * tablosu, örnekler ve eğitim testleri; arama ve PDF indirme ortaktır.
 */
import { DYNA_EQUIV } from "../lib/dynaKeywords";
import { CRASH_DOC, CRASH_SCENARIOS, type DocScenario, type DocSection } from "./crashDoc";
import { CRASH_TRAINING, TRAINING_RECORD, type TrainingGroup } from "./crashTraining";

export interface DocExample {
  id: string;
  title: string;
  domain: "crash" | "durability";
  setup: string;
  inputs: string[];
  targets: string[];
  results: string[];
  lesson: string;
}

export interface DocBook {
  id: "crash" | "durability" | "ml";
  /** Sekme adı */
  tab: string;
  title: string;
  subtitle: string;
  searchPlaceholder: string;
  note: string;
  /** Öğe tablosunun kart sütunu başlığı (ör. OpenRadioss, CalculiX). */
  cardHeader: string;
  /** LS-DYNA ≈ sütunu gösterilsin mi (yalnız crash). */
  dynaColumn: boolean;
  sections: DocSection[];
  scenarios?: { title: string; intro: string; rows: DocScenario[] };
  dynaMap?: Record<string, string>;
  examples?: { title: string; intro: string; rows: DocExample[] };
  training?: { title: string; intro: string; groups: TrainingGroup[] };
}

export const CRASH_BOOK: DocBook = {
  id: "crash",
  tab: "Crash",
  title: "Crash (OpenRadioss)",
  subtitle: "Her özellik, düğme ve kart: ne yapar, hangi senaryoda, OpenRadioss kartı ve LS-DYNA karşılığı.",
  searchPlaceholder: "Ara: kızak, TYPE7, hourglass, *RIGIDWALL…",
  note:
    "LS-DYNA sütunu yaklaşık eşdeğer keyword adıdır (≈), yalnız bilgi amaçlı — bu projede LS-DYNA kullanılmaz. " +
    "“Ne zaman” satırları tipik kullanımı anlatır; değer ve karar mühendisindir.",
  cardHeader: "OpenRadioss",
  dynaColumn: true,
  sections: CRASH_DOC,
  scenarios: {
    title: "Hazır senaryolar (+ Yeni crash vakası)",
    intro: "Katalogdaki 15 örnek; her birinin kurulumu, kullandığı özellikler ve doğrulama ölçütü.",
    rows: CRASH_SCENARIOS,
  },
  dynaMap: DYNA_EQUIV,
  training: {
    title: "Eğitim testleri (T1–T18)",
    intro: `Modele göre sıralı: her model grubun başında bir kez kurulur; ardından gelen her test bir öncekinden yalnız tek şeyi değiştirir. ${TRAINING_RECORD}`,
    groups: CRASH_TRAINING,
  },
};

/** Sekme sırası; diğer kitaplar içerikleri hazır oldukça eklenir. */
export const DOC_BOOKS: DocBook[] = [CRASH_BOOK];
