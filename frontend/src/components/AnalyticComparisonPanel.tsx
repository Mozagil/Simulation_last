import {
  formatRelPercent,
  type AnalyticComparison,
} from "../templates/analyticCompare";

interface AnalyticComparisonPanelProps {
  comparison: AnalyticComparison;
}

export default function AnalyticComparisonPanel({ comparison }: AnalyticComparisonPanelProps) {
  return (
    <div className="analytic-compare">
      <p className="material-assignments-title">Analitik referans</p>
      {comparison.skipped ? (
        <p className="material-assign-hint">{comparison.reason}</p>
      ) : (
        <>
          <table className="analytic-compare-table">
            <thead>
              <tr>
                <th>Metrik</th>
                <th>Analitik</th>
                <th>FEA</th>
                <th>Sapma</th>
              </tr>
            </thead>
            <tbody>
              {comparison.metrics.map((m) => (
                <tr key={m.key} className={m.warn ? "analytic-compare-warn-row" : undefined}>
                  <td>
                    {m.label} ({m.unit})
                  </td>
                  <td>{m.analytic.toPrecision(4)}</td>
                  <td>{m.fea.toPrecision(4)}</td>
                  <td>
                    {formatRelPercent(m.rel_error)}
                    {m.warn ? " · eşik aşıldı" : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {comparison.warned && (
            <p className="error-message" role="alert">
              Sapma eşiği aşıldı.
            </p>
          )}
        </>
      )}
    </div>
  );
}
