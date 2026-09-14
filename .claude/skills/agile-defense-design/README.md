# Agile Defense — Design System

A design-system scaffold for **Agile Defense**, a defense & national-security
technology contractor. Built from the attached Figma component library and
tokens, supplemented with live brand assets (logos, iconography, photography)
pulled from agiledefense.com.

## About the brand

Agile Defense delivers **digital transformation, data analytics, and cyber
capabilities** to U.S. government and defense customers (DISA, NGA, ONI,
TSA, Navy, Army, and more). Their flagship brand line — *"Always Evolving"* —
runs the homepage hero, and a sub-brand called **Agile Labs** houses their
product-facing offerings (Discovery, Builder, Flow, Platform, Workforce,
Mission Impact, Mission Applications).

The visual system is disciplined and muscular: **deep navy canvases,
red-accent typography set huge, zero rounded corners on cards, and flat
block iconography**. It reads as serious, institutional, and modern — no
glossy gradients, no playful illustration, no emoji.

## Source materials

- `reference/component-library.html` — authored component library from the
  attached Figma (file **hTaNhoLLA0ohAzc3bX66RE**). Contains every named
  component with working CSS.
- `reference/design-tokens.json` — JSON token dump (colors, type scale,
  spacing, layout, component specs).
- `assets/` — logos, capability icons, hero photography pulled from
  `https://agiledefense.com` (WordPress media library).

Original Figma: `https://www.figma.com/design/hTaNhoLLA0ohAzc3bX66RE`
(reader may or may not have access).

## Index

| Path                             | What it is                                                        |
| -------------------------------- | ----------------------------------------------------------------- |
| `colors_and_type.css`            | Token layer — CSS vars for color, type scale, spacing, layout.    |
| `assets/`                        | Logos, capability icons, hero photography.                        |
| `reference/component-library.html` | Original Figma-exported component library (dark + light demos). |
| `reference/design-tokens.json`   | Raw token JSON.                                                   |
| `preview/`                       | Individual cards that populate the Design System tab.             |
| `ui_kits/marketing/`             | Marketing-site UI kit (homepage + capability page).               |
| `ui_kits/agile-labs/`            | Agile Labs product page UI kit (Mission Impact, problems grid).   |
| `SKILL.md`                       | Front-matter skill file so this can be used as an Agent Skill.    |

---

## Content fundamentals

**Voice.** Third-person institutional, confident, outcome-focused. The reader
is addressed as "you" only in direct CTAs ("We'd love to hear from you",
"Transform your organization"); everything else is "we / our / Agile Defense".
No first-person singular, no casual contractions beyond the usual ("we're",
"you're").

**Casing.** Title Case for headings and CTAs. All-caps only for navbar items
and small CTAs ("LEARN MORE", "JOIN OUR TEAM", "GET STARTED", "VIEW ALL
NEWS"). Sub-headings and eyebrow labels use Sentence Case.

**Emphasis pattern.** A recurring two-word headline where the *first* word is
bold and the *second* is light/medium — e.g. **"Always** Evolving",
**"Purpose-Driven** Solutions", **"A Culture of** Innovation", **"Advancing**
Together". Treat this as a deliberate motif, not an accident.

**Sentence length.** Short declarative sentences. Mission-first framing:
*what we do → for whom → why it matters.* Typical body example:

> "Agile Defense stands at the forefront of innovation, driving advanced
> capabilities and solutions tailored to the most critical national security
> and civilian missions."

**Jargon level.** Acronym-heavy where appropriate (CAC, DISA, FedRAMP, NIPR,
SaaS) — the audience is government IT. Don't spell them out; trust the reader.

**Product-page pattern (Agile Labs).** Concrete problem statements ("Pages
That Never Load", "Blocked Mission Files", "Login & CAC Loops") paired with
Challenge → Our Approach → Result detail panels. Copy is direct and names
real pain ("If you're hearing your users call it 'Nevermenlo'…"). Stats are
given as hard percentages with short labels.

**No emoji. No exclamation points.** Period.

---

## Visual foundations

### Color

Two dominant canvases: **deep navy (#061033)** or **pure white**. Cards on
both themes are always **navy (#0b2451)** — even on light pages the cards
flip to dark, which gives the light theme its characteristic "navy blocks on
white" rhythm. Red (`#d23c3a`) is the single accent color — used for the
CTA button, for stat values, and for accent words in headlines. Stat cards
introduce a bounded palette of secondary accents: light blue, orange,
mid-blue, red, vivid blue.

### Typography

**Helvetica Neue** for everything. Weights in play: 400 / 500 / 700. The
scale is unusually wide: a 125 px "Hero" size for the brand word, 96 px for
stat display, then 64 / 40 / 32 / 24 / 20 / 17 / 14. Body copy at 17 px /
400 is on the large side, which matches the 1728-px design width.

### Layout

Fixed **1728 px** canvas; content container caps at **1488 px**; narrow
content column at **726 px**. Two primary grids: 3-column feature cards
(~476 px each) and 2-column wide cards (~729 px). Gutters are always
24 px. Section padding is generous — `64 px` vertical, `120 px` horizontal.

### Backgrounds & imagery

Full-bleed photography on hero sections only (server rooms, command
centers, military imagery — cool color temperature, dark, documentary).
The abstract "A" letterform vector (1115×624) appears as a background
decoration on multiple sections — subtle, right-aligned, low-contrast.
No repeating patterns. No gradients on page canvases, but featured cards
use a `#1f3864 → #061033` vertical gradient with a low-opacity image overlay.

### Corner radii

**Zero.** Every card, button, stat block, sidebar icon is a sharp rectangle.
Small 4 / 8 px radii exist in tokens but are effectively unused in the
delivered components. Keep it sharp — rounded corners break the system.

### Shadows

None. The system relies on color contrast (navy on navy, navy on white)
rather than elevation cues.

### Borders

Hairline dividers use `rgba(255,255,255,0.1)` on dark and `rgba(0,0,0,0.1)`
on light. Cards have no borders at all.

### Hover / press

Not formally specified in the Figma source. Safe defaults:
- Hover on buttons/links: brightness ↑ 8% or opacity 0.85.
- Press: opacity 0.7.
- No movement or scaling. No box-shadow pops. Keep it flat.

### Animation

None in the static comps. Use restrained fades or 150–200 ms opacity
transitions at most. This brand does not bounce.

### Transparency & blur

Used only for the hero gradient overlay on background images (darken the
lower half so white/red headlines stay legible). No frosted-glass panels.

---

## Iconography

Agile Defense uses two icon systems in parallel:

1. **Brand capability icons** (SVG, ~80×80). Three custom icons live on the
   homepage for Digital Transformation / Data Analytics / Cyber. These are
   flat, single-color red-on-navy, geometric. Copied to `assets/`:
   - `icon-digital-transformation.svg`
   - `icon-data-analytics.svg`
   - `icon-cyber.svg`

2. **Product-UI icons** (inline SVG, 20/24/32/48 px). White-stroke or
   white-fill geometric glyphs — cards, arrows, checks, chevrons, plus
   signs. In the Figma component library these are hand-drawn per component
   rather than pulled from a library. Stroke weight is **1.5–2 px** at the
   target render size; corners are sharp, caps are butt-not-round.

**CDN substitute.** For convenience in prototypes you can substitute
**Lucide** (same 1.5/2-px stroke, same flat-geometric family) where a
one-off glyph is needed. Flag any substitution in-context.

**Emoji.** Never used. Do not introduce them.

**Unicode glyphs.** The only non-icon glyphs in the system are the
dropdown chevron on nav items, drawn as an SVG triangle with `clip-path`
(see `.nav-item-dropdown::after` in the component library).

**Logo.** `assets/logo.svg` is the two-color mark (red triangle + white
wordmark). `assets/logo-invert.svg` is the inverted treatment for dark
canvases. Never re-color either mark.

---

## Asset substitutions / caveats

- **Fonts.** Helvetica Neue is not shipped with the system. On machines
  without it the stack falls through to Helvetica → Arial. If you need a
  web-safe 1:1 you must license & self-host Neue; Inter is listed as the
  secondary face but will not match metrics exactly. Flag to user if
  metrics drift matters.
- **Background decoration.** The abstract "A" letterform vectors described
  in `reference/design-tokens.json` (`bg-decoration`, 1115×624) aren't
  included as a standalone asset — they're drawn inline in the Figma comps.
  Not re-created here; request from brand if needed.
- **Hover/press states.** Not specified by the source; assumptions above are
  our best-guess defaults.

---

## Ask for the user

Most of this system was lifted directly from the attached Figma + token
files, so coverage is tight. Please review:

1. **Hover / press states** — do you have canonical interaction specs we
   should encode, or should we keep the conservative defaults?
2. **Fonts** — do you have a licensed Helvetica Neue web-font bundle you can
   share, or should we switch the primary face to a web-safe substitute?
3. **Brand illustrations** — the "A" letterform background decoration is
   referenced but not packaged. Is there a canonical SVG we should ingest?
4. **UI kit coverage** — currently two kits (marketing + Agile Labs product
   page). Do you need the full site (About, Careers, News) or additional
   product-page layouts?
