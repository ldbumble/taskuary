# Dashboards

A dashboard is a report you look at. It reads the same deterministic sources a report reads (a query, a sheet, a file,
Taskuary's own tables). Its components come from one preset library, and they are bound to those sources' columns. The AI
writes the spec once, at setup (`compose.compose_dashboard`). After that, a scheduled run re-reads the sources, keeps the
rows (`dashboard_result`) and files one row under Reports. The page slices those rows.

- server: `taskuary/dashboards.py` (the spec, `taskuary_data`, a run) · `/api/dashboards/compose|preview|{sid}`
- page: `website/src/dashboard/` (`slice.js` cuts the rows, `charts.jsx` holds the presets, `Dashboard.jsx` lays them out) ·
  `DashboardEditor.jsx` (Reports → Dashboards) · `assistantCards.DashboardCard` (the canvas)

## The built-in one

**Taskuary at a glance** (`dashboards.GLANCE`) is to dashboards what the End of day checkup is to reports: every install gets
it (`store.SEEDED_REPORTS`, `Owner='template'`, deleting it is the off switch), and New dashboard offers it again under the
composer in one press (`/api/dashboards/templates`, drawn over the install's own rows). It reads only `taskuary_data` - mail,
`flow` (how far each message got: came in, triaged, on a task, its task closed), tasks, agent sessions (worker events) and
replies - so it draws with nothing connected. Nothing else sets it apart: it is a row under Reports → Dashboards like any
other, and it is edited in the same editor.

## Editing one

Every dashboard is configurable in `DashboardEditor.jsx`, the AI's draft included. The page is drawn at the top. Under it:

- **Sources** are a report's own source cards (`ReportsView.SourceCard`), laid out as a report's are, each with its date
  column. Changing a source reads the rows again (`/api/dashboards/preview`, once the typing stops).
- **What it shows** has one card per component: its preset, title, source, the bindings that preset takes
  (`dashboard/setup.js` `BINDS`), a where, its own window (the page's range, a fixed 7/30/90 days, or what is true now) and
  its width. The default range and the segment sit above the cards. A component edit redraws the same rows in place.

Save runs the same `dashboards.validate` as the composer, and reads the sources again when they changed.

## The presets

`stat` (a number - count, sum, avg, median, min or max - with an optional unit, its change against the previous period, a
sparkline) · `progress` (toward a target) · `line` / `area` (one
value over time) · `bar` (ranked categories, the tail folded into Other; or stages kept in a given `order`, each also said as a `share` of the
first) · `stacked` (categories or days split by a second
column) · `table` (sortable) · `list` (one line per item; a row that is a task or a message opens it).

The interactive layer: a date range (7 / 30 / 90 / All) and a segment filter re-slice every component. Pressing a bar, column,
day or tile shows the rows behind it. Every chart has a Table view, and every mark has a tooltip.

## The rules they follow

1. **One screen, the number first.** A dashboard leads with 2–4 numbers, then trends and rankings, then the detail, in at
   most 12 components. (Few, *Information Dashboard Design*, and "Why Most Dashboards Fail", 2007; the dashboard-playbook
   skill: 3–5 hero metrics, with detail kept for drill-down.)
2. **Data-ink.** Thin marks, hairline solid gridlines and recessive axes, with no 3-D, shadows on marks or decoration.
   (Tufte, *The Visual Display of Quantitative Information*; Few.)
3. **Pick the form by the job.** A single value is a tile, not a one-bar chart. Change over time is a line. A ranking is a
   horizontal bar. Part of a whole is a stack. There are no pies. (dataviz skill: choosing-a-form, anti-patterns.)
4. **One axis.** A chart never has two y-scales. Two measures get two charts. (dataviz skill, non-negotiables.)
5. **One palette, used in a fixed order.** There are six categorical slots, checked with the dataviz skill's validator
   against the Beacon paper. Light mode: worst adjacent CVD ΔE 9.2, normal-vision 17.2. Dark mode: 9.1 and 15.4. A seventh
   series folds into Other.
6. **Colour follows the entity, never its rank.** Slots are assigned from all of a source's rows before any filter, so a
   filter never repaints the series that remain. (dataviz skill.)
7. **Text never wears the series colour.** Values, labels and legends use the ink colours. The mark next to them carries the
   identity. Status colours are not used for series. (dataviz skill.)
8. **Two or more series always get a legend. A single series never does.** Labels are selective: a value at the tip of a
   bar, at the end of a line, never on every point. (dataviz skill, marks-and-anatomy.)
9. **Marks.** Bars are at most 24px (14px when ranked), rounded at the data end and square at the baseline. Lines are 2px.
   Dots are at least 8px with a 2px surface ring. Stacked segments have a 2px surface gap. (dataviz skill.)
10. **Tooltips add detail but never hold it back.** The value leads and the label follows. Every value is also reachable
    through the Table view, and keyboard focus shows what hover shows. (dataviz skill, interaction; WCAG 1.4.11.)
11. **Filters sit in one row, above everything they scope.** The date range comes first, as presets. A refetch keeps the
    frame, dimmed rather than replaced by a skeleton. (dataviz skill, interaction; Tremor and shadcn/ui chart patterns.)
12. **Numbers.** Values over 10,000 are shortened (12.9K, 4.2M). Large figures use proportional digits. Table columns and
    axis ticks use `tabular-nums`. (dataviz skill.)
13. **Responsive by container, not by window.** The grid is four columns on the canvas, two on a tablet, and on a phone the
    numbers sit two abreast with each chart full width.
14. **No AI at run time.** The spec is the only thing the model writes, and only from the presets. The owner sees it drawn
    over real rows before it is saved. (The report composer's fences: only connected types, a peek before any guess.)

Dark mode has its own selected values, waiting on `[data-theme="dark"]`. The app does not have a dark theme yet.
