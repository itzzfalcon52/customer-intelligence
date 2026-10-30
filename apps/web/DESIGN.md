---
name: Holdfast
description: A churn and retention copilot whose interface is a triage board of tagged accounts.
colors:
  field-50: '#f0f8f6'
  field-100: '#dcefeb'
  field-200: '#b9ded7'
  field-300: '#86c4ba'
  field-600: '#186d64'
  field-700: '#0f5a54'
  field-800: '#0c4a47'
  field-900: '#093936'
  field-950: '#052523'
  stock: '#f5f7f4'
  stock-200: '#e6eae5'
  stock-300: '#d3d9d3'
  wire: '#9aa6a2'
  wire-loop: '#c9cfcb'
  tag-red: '#d7262e'
  tag-amber: '#f2b91f'
  tag-slate: '#5e6a67'
  tag-ink: '#141615'
  stock-text: '#3b4441'
  muted-text: '#56615d'
  quiet-text: '#687370'
typography:
  display:
    fontFamily: 'Archivo Variable, system-ui, sans-serif'
    fontSize: 'clamp(3.2rem, 7.4vw, 6rem)'
    fontWeight: 860
    lineHeight: 0.86
    letterSpacing: '-0.03em'
    fontVariation: "'wdth' 66"
  headline:
    fontFamily: 'Archivo Variable, system-ui, sans-serif'
    fontSize: 'clamp(2.4rem, 5vw, 4.6rem)'
    fontWeight: 820
    lineHeight: 0.92
    letterSpacing: '-0.02em'
    fontVariation: "'wdth' 66"
  page-title:
    fontFamily: 'Archivo Variable, system-ui, sans-serif'
    fontSize: '42px'
    fontWeight: 840
    lineHeight: 0.95
    letterSpacing: '-0.015em'
    fontVariation: "'wdth' 68"
  title:
    fontFamily: 'Archivo Variable, system-ui, sans-serif'
    fontSize: '22px'
    fontWeight: 780
    lineHeight: 1.1
    fontVariation: "'wdth' 78"
  body:
    fontFamily: 'Archivo Variable, system-ui, sans-serif'
    fontSize: '17px'
    fontWeight: 400
    lineHeight: 1.625
  body-app:
    fontFamily: 'Archivo Variable, system-ui, sans-serif'
    fontSize: '14px'
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: 'Archivo Variable, system-ui, sans-serif'
    fontSize: '12px'
    fontWeight: 680
    letterSpacing: '0.06em'
  stamp:
    fontFamily: 'Martian Mono Variable, ui-monospace, monospace'
    fontSize: '11px'
    fontWeight: 600
    fontFeature: "'tnum'"
    fontVariation: "'wdth' 87.5"
rounded:
  none: '0px'
  clip: '2px'
  badge: '3px'
  control: '4px'
  card: '6px'
  full: '9999px'
spacing:
  gutter-sm: '20px'
  gutter: '32px'
  section: '96px'
  section-lg: '112px'
  nav: '72px'
  app-bar: '64px'
  app-sidebar: '256px'
components:
  button-tag:
    backgroundColor: '{colors.stock}'
    textColor: '{colors.tag-ink}'
    height: '44px'
    padding: '0 20px 0 24px'
  button-tag-ink:
    backgroundColor: '{colors.tag-ink}'
    textColor: '{colors.stock}'
    height: '44px'
    padding: '0 20px 0 24px'
  button-app-primary:
    backgroundColor: '{colors.field-700}'
    textColor: '{colors.stock}'
    height: '36px'
    padding: '0 14px 0 20px'
  button-app-primary-hover:
    backgroundColor: '{colors.field-800}'
  button-app-secondary:
    backgroundColor: '#ffffff'
    textColor: '{colors.tag-ink}'
    rounded: '{rounded.control}'
    height: '36px'
  nav-app:
    backgroundColor: '{colors.field-900}'
    textColor: '{colors.field-200}'
    width: '{spacing.app-sidebar}'
  nav-app-active:
    backgroundColor: '{colors.field-800}'
    textColor: '{colors.stock}'
  card-app:
    backgroundColor: '#ffffff'
    textColor: '{colors.tag-ink}'
    rounded: '{rounded.card}'
  badge:
    rounded: '{rounded.badge}'
    height: '24px'
    padding: '0 8px'
  input-field:
    backgroundColor: '#ffffff'
    textColor: '{colors.tag-ink}'
    height: '48px'
    padding: '0 14px'
  tag-mini:
    backgroundColor: '{colors.stock}'
    textColor: '{colors.tag-ink}'
    width: '214px'
---

# Design System: Holdfast

## Overview

**Creative North Star: "The Triage Board"**

Holdfast treats every customer account as a paper triage tag hung on a wire. The tag carries
a coloured bar (red to call first, amber to watch, slate for lower risk), a stamped rank and
score, ruled lines for the reasons, and a grommet where it hangs. The marketing site
(a Persuade surface) shows the board itself: a teal field ground, tag-stock objects tilting
on wires, strips of tags and stamps moving past, and passages that alternate between field,
stock and the deepest field-950.

The workspace (an Operate surface) inherits the same materials with restraint. The deep field
becomes the sidebar, tag stock becomes the canvas, condensed Archivo carries page titles,
measured numbers are stamped in Martian Mono, and risk is only ever red, amber or slate. It
stays calm and dense: there are no hanging-tag tilts or moving strips inside the app. The
world shows up as tag-cut primary buttons, a red hanging tab on the active nav item, triage
swatches beside ranks and the tag silhouette on the daily brief.

Visual rejections: generic SaaS gradients, glass, purple accents, green for "good risk", and
rounded pill buttons.

**Key Characteristics:**

- Teal field, tag stock and steel wire as the only materials.
- Three triage colours carry risk, always next to a text label.
- One width axis (Archivo 62–125%) expresses the role of each piece of text.
- Numbers are stamped, never set in the reading face.
- Loops pause off-screen and show their finished state under reduced motion.

## Colors

A deep teal field with paper-coloured tags and three triage inks.

### Primary

- **Field Teal** (#0f5a54, field-700): app primary buttons, links on stock, checks.
- **Deep Field** (#093936, field-900): the workspace sidebar and the daily brief card.
- **Board Field** (#0c4a47, field-800): marketing hero ground, hover for primary buttons.
- **Night Field** (#052523, field-950): the darkest marketing passage and shadow tint.

### Secondary

- **Call Red** (#d7262e, tag-red): high risk, the active nav tab, the brief's top bar,
  strike-throughs for withheld text, the text caret.
- **Watch Amber** (#f2b91f, tag-amber): elevated risk, one emphasised word per display
  heading, selection, focus rings, badges on the dark sidebar. Amber text on white uses the
  darker #a87a00 (amber-600) to keep 3:1.

### Neutral

- **Tag Stock** (#f5f7f4): workspace canvas and the tag paper.
- **Stock Shade** (#e6eae5) and **Stock Rule** (#d3d9d3): footers on tags, lower-risk swatches.
- **Wire** (#9aa6a2) and **Wire Loop** (#c9cfcb): wires, grommet rings, hairlines.
- **Tag Slate** (#5e6a67): lower risk and "not yet" bars.
- **Tag Ink** (#141615): headings and body text on stock, the dark Ask AI button.
- **Stock Text** (#3b4441): long reading text on tags.
- **Muted** (#56615d) and **Quiet** (#687370): secondary and tertiary text. Quiet is the
  lightest grey allowed for text on stock (4.5:1).

### Named Rules

**The Never-Green Rule.** Risk levels are red, amber or slate. Green never means "safe".

**The Amber Emphasis Rule.** Amber marks one word per display heading, selection, focus on
dark ground and small counts on dark ground. It is never a large fill except the marketing "Coming soon" band.

## Typography

**Display Font:** Archivo Variable (with system-ui)
**Body Font:** Archivo Variable at normal width
**Label/Mono Font:** Martian Mono Variable at 87.5% width

**Character:** one industrial grotesque stretched from narrow posters to normal reading text,
and a squared mono that reads like a label printer.

### Hierarchy

- **Display** (860, clamp(3.2rem, 7.4vw, 6rem), 0.86, width 66%): marketing hero headings.
- **Headline** (820, clamp(2.4rem, 5vw, 4.6rem), 0.92, width 66%): marketing section heads.
- **Page title** (840, 32px mobile / 42px desktop, 0.95, width 68%): workspace page headers.
- **Title** (740–780, 17–22px, width 74–82%): card titles, tag names.
- **Body** (400, 17px marketing / 14px app, 1.5–1.625): reading text, capped near 62ch.
- **Label** (680–820, 11–12px, 0.06–0.08em, uppercase): stat labels, sidebar groups.
- **Stamp** (Martian Mono 600–700, 11–26px, tabular): ranks, scores, stat values, counts.

### Named Rules

**The Width Axis Rule.** Width encodes role: 62–70% for display, 74–82% for titles, 86–88%
for names and the wordmark, 100% for reading text. Word spacing on condensed heads is
0.08–0.09em.

**The Stamp for Numbers Rule.** Every measured number (rank, score, count, metric) is set in
the stamp font with tabular figures.

## Layout

Marketing pages use a 1320px container (1100px for the brief and closing sections), 20px
side gutters on mobile and 32px from `sm`, sections at 96–112px, a 72px header and a 136px
top pad on subpages. The home hero is a 12-column grid split 5/7 at `lg`.

The workspace is a fixed 256px deep-field sidebar from `lg` (a slide-in drawer below), a
64px stock top bar with a hairline rule, and content at 16px / 32px gutters. Cards sit in
1–3 column grids with 24px gaps; tables run full card width with 48px rows. Breakpoints are
Tailwind's `sm` 640, `md` 768, `lg` 1024 and `xl` 1280.

## Elevation & Depth

Depth belongs to tags. Hanging tags and the daily brief use the tag shadows, which are tinted
with the night field. Workspace cards are flat white on stock, separated by a hairline ring
and the faintest card shadow; popovers and the command palette use the pop shadow.

### Shadow Vocabulary

- **Tag** (`0 1px 0 0 rgb(255 255 255/.6) inset, 0 2px 3px -1px rgb(5 37 35/.25), 0 18px 36px -12px rgb(5 37 35/.45)`): hanging tags and the brief card.
- **Tag lift** (`… 0 4px 6px -2px rgb(5 37 35/.3), 0 40px 70px -20px rgb(5 37 35/.6)`): the hero tag, pricing tag and 404 tag.
- **Card** (`0 1px 2px 0 rgb(5 37 35/.04), 0 1px 3px 0 rgb(5 37 35/.05)`): workspace cards.
- **Pop** (`0 10px 15px -3px rgb(5 37 35/.08), 0 24px 48px -12px rgb(5 37 35/.18)`): toasts, dialogs, the palette.

### Named Rules

**The Tag Shadow Only Rule.** Large lifted shadows belong to tag stock. Panels stay flat.

**The Metal-Only Gradients Rule.** Gradients appear only as metal: rails, clips and sheen.
There are no colour washes and no gradient text.

## Shapes

Corners are square or nearly square. Tailwind radii are remapped (`lg` 4px, `xl` 5px, `2xl`
6px, `3xl` 8px), so the app's rounded classes resolve to cut paper. The tag silhouette is a
clipped polygon, `polygon(14% 0, 86% 0, 100% 9%, 100% 100%, 0 100%, 0 9%)`, with a grommet
near the top. Buttons that act carry the tag point: a left-pointing clip,
`polygon(10px 0, 100% 0, 100% 100%, 10px 100%, 0 50%)` on the site and 8px in the app. Full
rounding is kept for grommets, step dots and avatars' rings.

**The Tag Silhouette Rule.** A tag is the cut-corner shape, a grommet, a coloured bar and
ruled stock. Use it for objects that represent an account or a decision, not for every card.

## Components

### Buttons

- **Shape:** the tag point on primary actions; square (4px) on secondary.
- **Primary (app):** field-700 on stock text, 36px tall, 20px left pad to clear the point;
  hover field-800.
- **Secondary:** white with a tag-ink 20% inset ring that deepens to 45% on hover.
- **Danger:** tag-red. **Dark:** tag-ink, used for Ask AI with an amber spark.
- **Marketing:** stock or tag-ink tag buttons, 44–48px tall.
- **Focus:** a 2px amber outline on the site and on deep-field surfaces (7:1); a 2px
  field-500 outline (#2b877b, 3.9:1) on stock and white in the workspace, where amber would
  fall below 3:1.

### Badges

- **Style:** 24px tall, 3px corners, inset ring, label weight 620. Status dots are small
  diamonds. Badges always use the sans face, even inside stamped values.

### Cards / Containers

- **Corner Style:** 6px.
- **Background:** white on the stock canvas.
- **Shadow Strategy:** the card shadow plus a hairline ring; no lift on hover.
- **Internal Padding:** 20–24px; headers in condensed title weight.

### Inputs / Fields

- **Style:** white, hairline ink ring, 4px corners; placeholders in Quiet grey.
- **Focus:** field-500 outline in the workspace, amber on the marketing site.

### Navigation

- **Workspace sidebar:** deep field, field-200 labels at 14px/580. The active item is
  field-800 with a 6px red tab hanging off the left edge. Group labels are uppercase
  field-300. Counts are amber chips with stamped digits.
- **Top bar:** tag stock with a hairline rule; the workspace switcher and worker status are
  square, hairline-ringed chips.
- **Marketing:** a clipboard rail with field-200 links and a stock active state.

### Tabs

Text tabs on a 2px stock rule; the active tab gets a 3px red bar sliding under it.

### Triage row (signature, workspace)

Each ranked account row starts with a small tag-shaped swatch (red, amber or stock-300)
beside the stamped rank, then the account, the Nemotron reason line, a text risk badge and a
stamped score bar.

### Daily brief (signature, workspace)

A deep-field card with the tag's cut corner at the top right, a grommet, a red top bar and the
Nemotron badge. It holds the checked headline, the call-first list and the recommended play.

### Hanging tag (signature, marketing)

A stock tag on a wire with a tilt and sway on pointer movement, a torn stub with the rank
stamp, and a tear interaction. It appears only on marketing pages.

## Do's and Don'ts

### Do:

- **Do** show risk as red, amber or slate, always with a text label beside the colour.
- **Do** set ranks, scores and stat values in Martian Mono with tabular figures.
- **Do** use condensed Archivo (66–68% width) at weight 820–860 for page and section heads.
- **Do** keep text greys at Quiet (#687370) or darker on stock and white.
- **Do** let every attract loop pause off-screen and settle complete under reduced motion.

### Don't:

- **Don't** use green to mean low risk or success in risk contexts.
- **Don't** put hanging-tag tilts, sway or moving strips inside the workspace.
- **Don't** use side-stripe borders on cards or rows; mark triage with the tag swatch.
- **Don't** use pill-shaped buttons, gradient text or colour-wash backgrounds.
- **Don't** put large lifted shadows on panels; they belong to tags.
