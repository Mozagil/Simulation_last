repo: Mozagil/Simulation_last
branch: main
path: frontend/src

## Last sync

date: 2026-09-27T21:20:13Z

### Updated in this project

- Re-read the current ML modules (DoeSpecForm, DoeResultsTable, DoePanel, DatasetPanel, ConvergencePanel, surrogate/doe/convergence APIs).
- `ML Studio v2.dc.html`: three directions for the ML page — 1a pipeline, 1b parameter-space explorer, 1c notebook.

## Screen map

| Project screen | Built from |
| --- | --- |
| ML Studio v2.dc.html | components/DoeSpecForm.tsx, components/DoeResultsTable.tsx, components/DoePanel.tsx, components/DatasetPanel.tsx, components/ConvergencePanel.tsx, api/doe.ts, api/surrogate.ts, api/convergence.ts |
| Geometry Step.dc.html | frontend/src/App.tsx (geometry step), api/geometry.ts |
| Workbench v4.dc.html | frontend/src/App.tsx (analysisTab, steps, selection modes), components/CrashPanel.tsx, api/crash.ts, types.ts |
| ML Studio.dc.html | components/DoePanel.tsx, components/SurrogatePanel.tsx, components/DatasetPanel.tsx, api/doe.ts, api/surrogate.ts, api/dataset.ts |
| Workbench v3.dc.html | earlier iteration of the same sources |
| Sidebar Wireframes.dc.html | frontend/src/App.tsx, frontend/src/theme.css |
| Current App.dc.html | frontend/src/App.tsx, frontend/src/index.css, frontend/src/theme.css |

## Sync history

- 2026-09-15T10:20:00Z — Workbench v4 + first ML Studio.
- 2026-09-15T09:40:00Z — read Crash/DOE/Surrogate/Dataset/Template modules; Workbench v2 and v3.
- 2026-09-08T11:25:00Z — first import: current app recreation + three sidebar directions.
