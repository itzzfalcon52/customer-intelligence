# Marketing frontend

The marketing site lives in `apps/web`. It uses the existing React 19, TypeScript,
Vite and React Router setup. It does not change backend services or uploaded data.
This milestone is the public-facing product story; the upload/train/score workspace
will be built separately against the actual API contracts.

## Run it

From the repository root, select working Node 22 on this machine:

```sh
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
pnpm dev:web
```

Open <http://127.0.0.1:5173>. The marketing pages do not require FastAPI, a worker,
or Nebius credentials. The existing `/api` development proxy remains available
for future app screens. Never put provider credentials in `VITE_*` variables.

## Pages and their boundaries

| URL            | Purpose              | Current behavior                                                                 |
| -------------- | -------------------- | -------------------------------------------------------------------------------- |
| `/`            | Product story        | Interactive customer-priority preview, workflow, copilot, roadmap, FAQ           |
| `/features`    | Platform and roadmap | Filter built backend capabilities versus planned connected signals and actions   |
| `/pricing`     | Commercial direction | Three preview offerings; no announced prices, billing, checkout or purchase flow |
| `/login`       | Login UI             | Better Auth email/password account flow                                          |
| `/signup`      | Signup UI            | Better Auth email/password account flow                                          |
| Any other path | Recovery             | Friendly 404 with a working home link                                            |

Email/password accounts now use the new `apps/backend` Better Auth service. Signup
signs in immediately, without email verification. See [account setup](auth.md).
The `/app` workspace now includes the core ML workflow, jobs, results, scoring and evidence chat.
See [workspace guide](workspace.md) for feature coverage, data boundaries and startup.

The tour's companies and signals are fictional. It illustrates the proposed SaaS
retention workflow, including future usage signals and reviewed actions. It is not a
live analysis, a customer testimonial or evidence that any intervention reduces churn.
“Built today” means implemented backend capabilities, not a finished app workspace.

## Current structure (October 29, 2026 rebuild)

The whole frontend was rebuilt on Tailwind CSS v4, Motion and cmdk. The sections below this one
describe the earlier marketing build and are kept only as history.

- **Styles:** `src/index.css` holds Tailwind and the theme tokens. It is the only stylesheet;
  `src/styles/` was removed.
- **Marketing:**
  - `components/SiteLayout.tsx` provides the header, mobile menu and footer.
  - `components/Logo.tsx` is the logo.
  - `components/ProductPreview.tsx` is a static workspace preview with labelled synthetic
    values.
  - `pages/HomePage`, `FeaturesPage`, `PricingPage`, `AuthPage` and `NotFoundPage`.
  - Copy stays in `lib/content.ts`.
- **Workspace:**
  - `workspace/Shell.tsx` provides the sidebar, top bar, command palette, Ask drawer and toasts.
  - `workspace/ui.tsx` and `style.ts` are the component kit.
  - `workspace/workflow.ts` and `workflow-ui.tsx` hold the step model, demo pipeline, stepper
    and next-step card.
  - Pages are in `workspace/pages/`: Overview, Data, Churn, Models, Scores, Plays,
    Investigate, Analyses, Copilot, Manage.
- **Design rules:** `apps/web/DESIGN.md`.

The Manrope files in `public/fonts/` are no longer referenced.

## How the pieces connect (earlier build)

`main.tsx` mounts React and imports the style entry point. `App.tsx` declares the
routes. `SiteLayout.tsx` supplies the shared header, mobile menu, footer and native
dialog. Its outlet renders the selected page; the outlet context provides `openDemo`
so each page can open the same tour without passing callbacks through every component.

| Location                            | Responsibility                                                        |
| ----------------------------------- | --------------------------------------------------------------------- |
| `src/pages/`                        | Page-level sections and page-specific UI                              |
| `src/components/Brand.tsx`          | Shared logo and wordmark                                              |
| `src/components/OrbitArt.tsx`       | Original native SVG scene and bounded pointer motion                  |
| `src/components/SignalExplorer.tsx` | Illustrative three-stage tour, tabs and conversation-budget slider    |
| `src/components/DemoDialog.tsx`     | Native modal, Escape dismissal and body-scroll restoration            |
| `src/components/FinalCTA.tsx`       | Reusable closing call to action                                       |
| `src/hooks/usePageEffects.ts`       | Page title, route scroll/focus and one-shot section reveals           |
| `src/lib/content.ts`                | Capability/roadmap copy and shared FAQ                                |
| `src/lib/authValidation.ts`         | Zod field validation shared by account forms                          |
| `src/styles/`                       | Base tokens, shared layout, landing, page, auth and responsive styles |
| `public/fonts/`                     | Two self-hosted Latin font subsets and the Manrope open-font license  |

For copy changes, start with `content.ts` and the appropriate page. For colors and
spacing, start with the CSS variables in `styles/base.css`. Responsive rules are last
in the style import order so their overrides are predictable. Account UI is loaded
on demand, keeping its validation library out of the initial landing-page chunk.

## Motion and accessibility

The site has no video background, WebGL renderer or animation dependency. The orbit
is SVG; continuous motion changes transforms, not layout. Pointer movement is capped
to one pending animation frame and confined to the illustration. The primary scene
pauses its looping motion when off-screen. Reveals use IntersectionObserver and
stop observing after the section becomes visible. Fonts are local, with `swap` and
a fallback face; there is no runtime request to an external font service.

Reduced-motion preferences disable animation, transitions and pointer transforms.
The menu exposes its expanded state. The tour uses a native dialog for focus trapping;
Escape closes it. Tabs support Left/Right/Home/End keys and roving focus. The range
input supports normal keyboard controls. FAQ disclosure uses native `details` elements.
Forms have labels, linked field errors, first-error focus and an explicit result message.
A skip link, route titles, and focus on route change support keyboard navigation.

## Verify changes

```sh
pnpm --filter @ci/web lint
pnpm --filter @ci/web check-types
pnpm --filter @ci/web test
pnpm --filter @ci/web build
```

Four focused validation tests cover malformed email, password length boundaries,
and preserving intentional password whitespace.
Browser checks should cover mobile navigation, all five routes, feature filters,
FAQ expansion, modal focus/Escape, keyboard tabs, the budget slider, signup/login/logout and the local preview. Check horizontal overflow at phone,
tablet and desktop widths. Check the production preview as well as development.

The first implementation was checked in the local browser at phone and desktop
widths. No speed score or universal “lag-free” guarantee is claimed; measure on
real target devices before shipping. The build may emit harmless annotation warnings
from the existing Zod package; these do not represent type, lint or application errors.

## Next frontend milestone

Create a distinct `/app` workspace and use typed API contracts from `docs/backend.md`:
upload/profile → task confirmation → job progress → measured results → scoring →
ranked shortlist → evidence copilot. Keep illustrative marketing data separate from
API responses. Add identity and workspace authorization before public hosting.

For production hosting, configure an SPA fallback to `index.html` for direct route
visits. Deployment, payments, CRM authorization and outbound actions are outside this
marketing pass. No new site or external hosting project was created.

## Landing page refinement — October 12

The landing page now uses a centered purple/lime hero and a customer-priority preview.
`RetentionPreview.tsx` holds fictional account examples and a local selection state;
selecting a row updates the explanation and SVG chart without a network request.
`HomePage.tsx` composes the workflow, copilot, roadmap, FAQ and closing invitation.
`styles/saas.css` owns the new landing styles and shared header refinements. It loads
after existing styles; the older landing styles still support the shared product tour.

Primary landing buttons open the product tour. The preview does not claim live
customer results, and planned integrations are labeled. The new layout adds no
dependencies or runtime animation library. Mobile stacks the customer list and
explanation; reduced-motion preferences disable transitions.
