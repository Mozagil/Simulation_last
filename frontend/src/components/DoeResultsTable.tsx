/** Bir DOE çalışmasının skaler sonuç tablosu.
 *
 * Tek tek run'a girip kontura bakmak bir örnek için yeterli; 200 örneklik
 * sette dağılımı ancak tabloda görürsün. Sütunlar: değişen parametreler,
 * skalerler, analitik sapma, kalite etiketi. Başlığa tıklayınca sıralanır —
 * "en çok sapan hangisi" sorusunun cevabı bir tıkla gelir.
 *
 * Sabit tutulan parametreler tabloda tekrar edilmez, üstte bir satırda yazılır.
 */

import { useMemo, useState } from "react";
import type { DoeResultRow, DoeResults } from "../api/doe";

type SortKey = { group: "param" | "scalar" | "meta"; key: string };

function cellValue(row: DoeResultRow, sort: SortKey): number | string | null {
  if (sort.group === "param") return row.params[sort.key] ?? null;
  if (sort.group === "scalar") return row.scalars[sort.key] ?? null;
  if (sort.key === "index") return row.index;
  if (sort.key === "element_size") return row.element_size;
  if (sort.key === "dev_displacement_pct") return row.dev_displacement_pct;
  if (sort.key === "dev_von_mises_pct") return row.dev_von_mises_pct;
  return row.quality;
}

function fmt(value: number | string | null, digits = 3): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (value !== 0 && (Math.abs(value) >= 1e5 || Math.abs(value) < 1e-3)) {
    return value.toExponential(2);
  }
  return String(Number(value.toFixed(digits)));
}

function fmtPct(value: number | null): string {
  if (value === null || value === undefined) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

interface DoeResultsTableProps {
  results: DoeResults;
  onOpenRun?: (runId: number) => void;
}

export default function DoeResultsTable({ results, onOpenRun }: DoeResultsTableProps) {
  const [sort, setSort] = useState<SortKey>({ group: "meta", key: "index" });
  const [asc, setAsc] = useState(true);

  const rows = useMemo(() => {
    const copy = [...results.rows];
    copy.sort((a, b) => {
      const va = cellValue(a, sort);
      const vb = cellValue(b, sort);
      // Boş değerler daima sonda — sıralama yönü ne olursa olsun.
      if (va === null && vb === null) return a.index - b.index;
      if (va === null) return 1;
      if (vb === null) return -1;
      const cmp = typeof va === "number" && typeof vb === "number"
        ? va - vb
        : String(va).localeCompare(String(vb));
      return asc ? cmp : -cmp;
    });
    return copy;
  }, [results.rows, sort, asc]);

  function toggle(next: SortKey) {
    if (next.group === sort.group && next.key === sort.key) setAsc((v) => !v);
    else {
      setSort(next);
      setAsc(true);
    }
  }

  function header(label: string, next: SortKey) {
    const active = next.group === sort.group && next.key === sort.key;
    return (
      <th key={`${next.group}.${next.key}`} scope="col">
        <button type="button" className="doe-table-sort" onClick={() => toggle(next)}>
          {label}
          {active ? (asc ? " ▲" : " ▼") : ""}
        </button>
      </th>
    );
  }

  const scalarKeys = Object.keys(results.scalar_columns);
  const constants = Object.entries(results.constant_params);

  if (results.rows.length === 0) {
    return <p className="filename">Bu çalışmada örnek yok.</p>;
  }

  return (
    <div className="doe-results">
      {constants.length > 0 && (
        <p className="filename">
          Sabit: {constants.map(([k, v]) => `${k} ${fmt(v)}`).join(" · ")}
        </p>
      )}

      <div className="doe-table-scroll">
        <table className="doe-table">
          <thead>
            <tr>
              {header("#", { group: "meta", key: "index" })}
              {results.param_columns.map((p) => header(p, { group: "param", key: p }))}
              {header("Eleman", { group: "meta", key: "element_size" })}
              {scalarKeys.map((k) =>
                header(results.scalar_columns[k], { group: "scalar", key: k }),
              )}
              {header("Δ deplasman", { group: "meta", key: "dev_displacement_pct" })}
              {header("Δ VM", { group: "meta", key: "dev_von_mises_pct" })}
              {header("Durum", { group: "meta", key: "quality" })}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.index}
                className={r.quality === "ok" ? undefined : "doe-table-row-flagged"}
                onClick={() => r.run_id !== null && onOpenRun?.(r.run_id)}
                title={r.message ?? r.analytic_skipped ?? undefined}
              >
                <td>{r.index}</td>
                {results.param_columns.map((p) => (
                  <td key={p}>{fmt(r.params[p])}</td>
                ))}
                <td>{fmt(r.element_size, 2)}</td>
                {scalarKeys.map((k) => (
                  <td key={k}>{fmt(r.scalars[k])}</td>
                ))}
                <td title={r.analytic_skipped ?? undefined}>
                  {fmtPct(r.dev_displacement_pct)}
                </td>
                <td title={r.analytic_skipped ?? undefined}>{fmtPct(r.dev_von_mises_pct)}</td>
                <td>{r.quality}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={1 + results.param_columns.length + 1}>min / ort / maks</td>
              {scalarKeys.map((k) => {
                const s = results.stats[k];
                return (
                  <td key={k}>
                    {s ? `${fmt(s.min)} / ${fmt(s.mean)} / ${fmt(s.max)}` : "—"}
                  </td>
                );
              })}
              {(["dev_displacement_pct", "dev_von_mises_pct"] as const).map((k) => {
                const s = results.stats[k];
                return (
                  <td key={k}>
                    {s ? `${fmtPct(s.min)} / ${fmtPct(s.mean)} / ${fmtPct(s.max)}` : "—"}
                  </td>
                );
              })}
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
