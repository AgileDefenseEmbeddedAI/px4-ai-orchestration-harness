---
name: agile-defense-design
description: Use this skill to generate well-branded interfaces and assets for Agile Defense, either for production or throwaway prototypes/mocks/etc. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping.
user-invocable: true
---

Read the README.md file within this skill, and explore the other available files.

Key files to start with:
- `README.md` — brand context, voice, visual foundations, iconography, and
  caveats.
- `colors_and_type.css` — token layer. Import this before your own styles so
  you inherit the CSS vars and `.t-*` semantic type classes.
- `assets/` — logos, capability icons, hero photography.
- `reference/component-library.html` — the full authored component library
  with working CSS for every named component. Use this as your source of
  truth when building new screens.
- `ui_kits/marketing/` — homepage recreation; JSX components for navbar,
  hero, capability cards, culture section, CTAs, footer.
- `ui_kits/agile-labs/` — product page recreation; JSX components for the
  Mission Impact sidebar + detail pattern, stat grid, stats banner.

If creating visual artifacts (slides, mocks, throwaway prototypes), copy
assets out of `assets/` and produce static HTML files for the user to view.
If working on production code, you can copy assets and read the rules here
to become an expert in designing with this brand.

If the user invokes this skill without any other guidance, ask them what
they want to build or design, ask some clarifying questions, and act as an
expert designer who outputs HTML artifacts or production code, depending on
the need.

**Hard rules inherited from the brand:**
- Corners are sharp. No rounded cards. 4/8 px radii exist only as tokens.
- No emoji. No exclamation points.
- No shadows for elevation — rely on navy-on-navy or navy-on-white contrast.
- Helvetica Neue is the primary face; fall through Helvetica → Arial.
- Red `#d23c3a` is a single accent — don't introduce new accent colors.
- The "first word bold, second word medium" two-word headline is a motif;
  use it when it fits.
