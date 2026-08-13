---
name: Akiha Technical Interface
colors:
  surface: '#131317'
  surface-dim: '#131317'
  surface-bright: '#39393e'
  surface-container-lowest: '#0e0e12'
  surface-container-low: '#1b1b20'
  surface-container: '#1f1f24'
  surface-container-high: '#2a292e'
  surface-container-highest: '#353439'
  on-surface: '#e4e1e8'
  on-surface-variant: '#c7c5d1'
  inverse-surface: '#e4e1e8'
  inverse-on-surface: '#303035'
  outline: '#918f9b'
  outline-variant: '#464650'
  surface-tint: '#bfc2ff'
  primary: '#bfc2ff'
  on-primary: '#252969'
  primary-container: '#878bd1'
  on-primary-container: '#1e2262'
  inverse-primary: '#54589a'
  secondary: '#bfc2ff'
  on-secondary: '#252969'
  secondary-container: '#3c4081'
  on-secondary-container: '#abaff8'
  tertiary: '#e0c561'
  on-tertiary: '#3a3000'
  tertiary-container: '#c3aa49'
  on-tertiary-container: '#4c3e00'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#e0e0ff'
  primary-fixed-dim: '#bfc2ff'
  on-primary-fixed: '#0e1154'
  on-primary-fixed-variant: '#3c4081'
  secondary-fixed: '#e0e0ff'
  secondary-fixed-dim: '#bfc2ff'
  on-secondary-fixed: '#0e1154'
  on-secondary-fixed-variant: '#3c4081'
  tertiary-fixed: '#fde17a'
  tertiary-fixed-dim: '#e0c561'
  on-tertiary-fixed: '#221b00'
  on-tertiary-fixed-variant: '#554600'
  background: '#131317'
  on-background: '#e4e1e8'
  surface-variant: '#353439'
typography:
  display-lg:
    fontFamily: Geist
    fontSize: 32px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: -0.02em
  display-md:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.3'
  headline-sm:
    fontFamily: Geist
    fontSize: 18px
    fontWeight: '500'
    lineHeight: '1.4'
  body-base:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.6'
  body-sm:
    fontFamily: Geist
    fontSize: 13px
    fontWeight: '400'
    lineHeight: '1.5'
  code-label:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: '1.0'
    letterSpacing: 0.05em
  label-caps:
    fontFamily: Geist
    fontSize: 11px
    fontWeight: '600'
    lineHeight: '1.0'
    letterSpacing: 0.08em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  base: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  gutter: 16px
  margin: 24px
---

## Brand & Style

The design system is engineered for high-performance technical environments, prioritizing focus, clarity, and rapid information processing. It targets developers, engineers, and technical power users who require a sophisticated, low-fatigue workspace.

The aesthetic follows a **Modern-Technical** approach, blending elements of **Minimalism** with **Geist-inspired utilitarianism**. It avoids unnecessary ornamentation, relying on precise geometry, subtle depth, and a strictly functional color hierarchy. The emotional response is one of controlled authority and surgical precision. 

Key stylistic pillars include:
- **Depth through layering:** Utilizing specific background tiers rather than heavy shadows to define hierarchy.
- **State-driven chrome:** Using specific accent colors to indicate active communication states (Listening/Speaking).
- **Reduced visual noise:** High-contrast text against a deep, neutral palette to ensure legibility during extended use.

## Colors

This design system utilizes a sophisticated dark-mode palette designed for technical durability. 

- **Foundations:** The `#1A1D24` background provides a stable, low-glare base. Surfaces like cards and inputs use `#2C303C` to sit slightly above the base layer.
- **Accents:** The Primary Accent (`#7B7FC4`) is reserved for high-priority actions and active navigation states. The Highlight (`#9599E0`) is used for focus indicators and structural headers.
- **Communication States:** Specialized colors define the voice interface logic. Use `#5B6FD4` (Listening) for active input detection and `#B6BADF` (Speaking) for system output feedback.
- **Feedback:** Semantic colors for Success and Error are desaturated to maintain harmony with the cool-toned primary palette.

## Typography

The typography system is built on **Geist**, emphasizing its monolinear strokes and technical appearance. 

- **Scale:** All font sizes follow a tight scale to maximize information density. 
- **Mono Integration:** While Geist is the primary face, **JetBrains Mono** (or a similar monospace font) is used for metadata, system status, and technical labels to reinforce the "instrument cluster" feel.
- **Hierarchy:** Use `label-caps` for section headers in sidebars and `text-muted` (`#9A9FB5`) for inactive or secondary information. `text-primary` (`#E8E9EE`) should be strictly reserved for interactive content and primary reading text.

## Layout & Spacing

The layout operates on a **4px baseline grid**, ensuring all components align with mathematical precision.

- **Structure:** Use a fluid-width main content area with fixed-width side panels (standardized at 240px or 280px). 
- **Density:** This design system favors "Comfortable Density." Gutters are maintained at `16px` to keep distinct functional blocks separate, while internal padding within components (like buttons or list items) should use `8px` (horizontal) and `4px` (vertical) for a compact look.
- **Alignment:** All containers should align to the grid edges. Avoid centering content in large viewports; keep information left-aligned to follow standard technical documentation patterns.

## Elevation & Depth

Elevation is conveyed through **Tonal Layering** and **Subtle Outlines** rather than traditional drop shadows.

1.  **Level 0 (Floor):** `#1A1D24` — The main application background.
2.  **Level 1 (Surface):** `#2C303C` — Used for cards, inputs, and primary panels.
3.  **Level 2 (Hover/Active):** `#22252E` — A subtle shift used for interactive states or nested containers.
4.  **Borders:** Use `#3A3F52` for standard structural borders. For active focus or "High Alert" components, use the Highlight color (`#9599E0`) with a 1px solid stroke.

Shadows, if used, must be "Sharp Ambient": `0px 2px 4px rgba(0, 0, 0, 0.4)`, used only for floating menus or modals to separate them from the Level 1 surface.

## Shapes

The shape language is "Soft-Technical." By utilizing a base **4px (`0.25rem`) corner radius**, the UI feels modern and accessible without losing its structured, professional edge.

- **Small Components:** Buttons, checkboxes, and input fields use the base 4px radius.
- **Large Containers:** Cards and main panel sections use 8px (`rounded-lg`) to provide a clear visual encasement of content.
- **Selection Indicators:** Tab highlights and active menu pills should use a 4px radius to match the components they reside within.

## Components

- **Buttons:** 
  - *Primary:* Solid `#7B7FC4` with `#E8E9EE` text. 
  - *Secondary:* Solid `#2C303C` with a `#3A3F52` border.
  - *Ghost:* No background, `#9A9FB5` text, shifting to `#E8E9EE` on hover.
- **Inputs:** Background `#2C303C` with a 1px border of `#3A3F52`. Focus state shifts border to `#9599E0`. Text should be `body-sm`.
- **Status Indicators:** 
  - *Listening:* A 2px pulse or solid border of `#4A5FC7`.
  - *Speaking:* A glow effect or background tint using `#B6BADF` at 20% opacity.
- **Cards:** Background `#2C303C`, no shadow, 1px border of `#3A3F52`.
- **Lists:** Items use `#1A1D24` (transparent) background, shifting to `#22252E` on hover. Active selection uses a 2px left-accent bar of `#7B7FC4`.
- **Scrollbars:** Track is transparent; thumb is `#3A3F52` with a 4px radius.