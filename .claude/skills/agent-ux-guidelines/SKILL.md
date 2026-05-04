---
name: ux-guidelines
description: Designsystem og UX for drivstoffprisene.no. Bruk ved UI/UX-endringer, nye komponenter, styling, eller endringer i kart, liste, stasjonskort, modal eller admin.
user-invocable: false
---

# Designsystem – drivstoffprisene.no

Bruk ALLTID disse reglene for visuell konsistens.
Prosjektet er **vanilla JS PWA**, mørkt tema, mobilfirst.

## Teknisk stack
- **Vanilla JS** — ingen framework, ingen build-steg for JS
- **Leaflet** for kart
- **CSS custom properties** fra `public/css/tokens.css`
- **System-font** — `-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`
- **Ingen i18n** — norsk tekst hardkodet

## Farger og tokens (`public/css/tokens.css`)

```css
--color-bg: #0f172a          /* Sidebakgrunn */
--color-card-bg: #111827     /* Kort og paneler */
--color-border: #1f2937      /* Subtil kant */
--color-accent: #3b82f6      /* Blå – primæraksent, fokus, aktiv */
--color-accent-soft: rgba(59, 130, 246, 0.15)
--color-text: #e5e7eb        /* Primærtekst */
--color-muted: #94a3b8       /* Sekundærtekst, plassholder */
--color-success: #22c55e     /* Grønn – fersk pris */
--color-success-soft: rgba(34, 197, 94, 0.2)
--color-error: #ef4444       /* Rød – feil, gammel pris */
--color-error-soft: rgba(239, 68, 68, 0.2)
--color-fuel: #f59e0b        /* Amber – drivstoffpris, fremhevet info */
--color-fuel-soft: rgba(245, 158, 11, 0.15)

--space-xs: 0.25rem  --space-sm: 0.5rem  --space-md: 1rem  --space-lg: 1.5rem
--font-xs: 0.7rem    --font-sm: 0.78rem  --font-base: 0.9rem  --font-md: 1.05rem
--radius-sm: 6px     --radius-md: 10px   --radius-full: 999px
--border-color: rgba(148,163,184,0.12)
--border-color-medium: rgba(148,163,184,0.3)
--shadow-md: 0 4px 16px rgba(0,0,0,0.4)
--transition-base: 200ms ease
--z-overlay: 20  --z-modal: 30  --z-toast: 40
```

**Aldri bruk hardkodede hex-farger** — bruk alltid CSS-variablene.

## Touch og tilgjengelighet

- **Touch-targets:** minimum 44x44px — `button { min-height: 44px }` er satt globalt, men bredd MÅ også sikres
- **Fokus:** `:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px }` — ikke fjern focus-ring
- **Skip-link:** `#skip-link` finnes og skal ikke fjernes
- **SR-only:** `.sr-only` for skjermleser-tekst på ikontomme knapper
- **Ingen horizontal scroll** på mobil (320px minimum)
- **`touch-action: manipulation`** og `-webkit-tap-highlight-color: transparent` på alle knapper

## Topbar

```css
position: fixed; top: 0; height: 48px;
background: rgba(15, 23, 42, 0.92); backdrop-filter: blur(8px);
border-bottom: 1px solid var(--border-color);
z-index: var(--z-overlay);
```

## Kart-knapper (floating action buttons)

```css
position: absolute; right: 14px;
width: 44px; height: 44px; border-radius: 50%;
background: rgba(15, 23, 42, 0.92); backdrop-filter: blur(8px);
border: 1px solid var(--border-color-medium);
box-shadow: var(--shadow-md);
min-height: unset; /* overstyr global button min-height */
```

Stacking bruker CSS-variabel `--kart-btn-index` for `top`-beregning.

## Modaler / bottom sheets

```css
/* Overlay */
position: fixed; inset: 0;
background: rgba(0,0,0,0.6); backdrop-filter: blur(4px);
z-index: var(--z-modal);

/* Panel */
background: var(--color-card-bg);
border-radius: var(--radius-md);
box-shadow: var(--shadow-md);
```

## Prisfarger

- **Fersk pris (< 24t):** `--color-success`
- **Gammel pris (> 24t):** `--color-error` / `--color-muted`
- **Fremhevet pris:** `--color-fuel`
- **Aldri vis pris uten tidspunkt-kontekst**

## Statusindikatorer

- Suksess: `--color-success` + `--color-success-soft` bakgrunn
- Feil: `--color-error` + `--color-error-soft` bakgrunn
- Advarsel/gammel pris: `--color-fuel` + `--color-fuel-soft` bakgrunn

## Søk og input

```css
border: 1px solid var(--border-color-medium);
border-radius: var(--radius-sm);
padding: var(--space-sm) var(--space-md);
background: var(--color-bg);
color: var(--color-text);
```
Fokus-tilstand: `border-color: var(--color-accent)` + aksent-box-shadow.

## Anti-patterns

1. **Hardkodede farger** — bruk alltid tokens
2. **Touch-target under 44px** — bruk padding for å kompensere
3. **Fjerne focus-ring** — `outline: none` er forbudt uten `:focus-visible`-erstatning
4. **Nye z-index-verdier uten token** — bruk `--z-overlay`, `--z-modal`, `--z-toast`
5. **Nye fontstørrelser** — bruk `--font-xs/sm/base/md`
6. **Ny `border-radius`** — bruk `--radius-sm/md/full`
