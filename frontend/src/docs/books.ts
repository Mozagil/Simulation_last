/**
 * Belgeler penceresinin "kitapları" (sekmeler): Crash · Durability · ML
 * (kullanıcı 2026-10-08). Her kitap aynı düzende gösterilir: bölümler
 * (öğe tablosu + görsel), isteğe bağlı hazır senaryolar, LS-DYNA eşleme
 * tablosu, örnekler ve eğitim testleri; arama ve PDF indirme ortaktır.
 */
import { DYNA_EQUIV } from "../lib/dynaKeywords";
import { CRASH_DOC, CRASH_SCENARIOS, type DocScenario, type DocSection } from "./crashDoc";
import { CRASH_TRAINING, TRAINING_RECORD, type TrainingGroup } from "./crashTraining";
import { ML_DOC, ML_EXAMPLES } from "./mlDoc";
import { DURABILITY_DOC, DURABILITY_TEMPLATES } from "./durabilityDoc";
import { DURABILITY_TRAINING, DURABILITY_TRAINING_RECORD } from "./durabilityTraining";

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

export const DURABILITY_BOOK: DocBook = {
  id: "durability",
  tab: "Durability",
  title: "Durability (CalculiX)",
  subtitle: "Her adım, düğme ve kart: ne yapar, hangi durumda, CalculiX girdi kartı — statik, NLGEOM, plastisite ve modal.",
  searchPlaceholder: "Ara: NLGEOM, *CLOAD, Jacobian, S-N, modal…",
  note:
    "Kart sütunu CalculiX .inp dosyasına yazılan karttır. “Ne zaman” satırları tipik kullanımı anlatır; değer ve karar mühendisindir.",
  cardHeader: "CalculiX",
  dynaColumn: false,
  sections: DURABILITY_DOC,
  scenarios: {
    title: "Durability şablonları",
    intro: "Kayıtlı şablonlar: ne modelledikleri, gelen bölgeler, varsayılan sınır koşulları ve analitik referans.",
    rows: DURABILITY_TEMPLATES.map((t) => ({
      id: t.id,
      title: t.title,
      template: t.group,
      setup: t.models,
      features: t.regions,
      validation: t.defaultBcs,
      reference: t.reference,
    })),
  },
  training: {
    title: "Eğitim testleri (D1–D16)",
    intro: `Modele göre sıralı: her model grubun başında bir kez kurulur; ardından gelen her test bir öncekinden yalnız tek şeyi değiştirir. ${DURABILITY_TRAINING_RECORD}`,
    groups: DURABILITY_TRAINING,
  },
};

export const ML_BOOK: DocBook = {
  id: "ml",
  tab: "ML",
  title: "ML Stüdyo (vekil model)",
  subtitle: "DOE, veri seti, vekil model, CV skorları ve tahmin — durability ve crash, gerçek örneklerle.",
  searchPlaceholder: "Ara: LHS, R², aralık dışı, korpus, kiriş…",
  note:
    "Vekil model FEA'nın yerini almaz; eğitildiği aralıkta hızlı tahmin verir. Skorlar ve oranlar veridir — " +
    "modeli kullanma kararı mühendisindir.",
  cardHeader: "API / dosya",
  dynaColumn: false,
  sections: ML_DOC,
  examples: {
    title: "Örnekler (gerçek koşulardan)",
    intro: "Bu projede eğitilmiş modellerden sayılar — her örnekte kurulum, girdiler, hedefler, sonuçlar ve çıkarılan ders.",
    rows: ML_EXAMPLES,
  },
};

/** Sekme sırası; diğer kitaplar içerikleri hazır oldukça eklenir. */
export const DOC_BOOKS: DocBook[] = [CRASH_BOOK, DURABILITY_BOOK, ML_BOOK];
