# AutoImmune Research Console: design record

Read first by any session that changes `frontend/`. Oxfords (`oxfords/skills/oxfords/SKILL.md`) governs what this leaves open.

- Reading as: research console for a B.Tech jury and the project team, used on laptops at 1366-1920 wide, so both themes, dense.
- Colour: `node oxfords/skills/oxfords/scripts/palette.mjs Tideline --mode light --ground white` and `--mode dark`; tokens in `frontend/src/styles/globals.css`, exposed through `frontend/tailwind.config.js` (wrapped in `color-mix` so `/opacity` modifiers work). No hand-written colours.
- Theme: `data-theme` on `<html>`, set before paint in `frontend/index.html`, toggled by `ThemeToggle`; follows the OS until the viewer chooses.
- Type: system font stack, one family. Console scale 28 (page title) / 20 (section) / 16 / 14 (body) / 12-11 (meta). Monospace only for code, ids, formulas and figures.
- Radius: one tier, Tailwind `rounded` (4px) for controls, panels and tables.
- Spacing: multiples of 4; 48px between page sections, 16px inside a section.
- Icons: lucide-react, 14-18px beside text, stroke 1.75. Used sparingly.
- Charts (`frontend/src/components/research/charts.tsx`): plain SVG bars, lines and points from `--series-*` (AI-written = series 1, hand-built = series 2); every value labelled directly; axis values and grid lines always.
- Focus: the global `*:focus-visible` outline in `globals.css`. Do not combine a Tailwind `ring-*` focus with `shadow-1`: in dark mode `--shadow-1` is `none`, which voids the whole box-shadow and hides the ring.
- Exception: page headings use Title Case ("Risk Estimation") to match the existing navigation labels.
- Exception: the scroll effects (landing tunnel and ink features, Overview glyph portal and case-study carousel) are deliberate motion pieces requested by the team; the research pages (Risk Estimation, Validation Cost) stay static.
