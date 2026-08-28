---
name: sports-dataviz
description: Use when building any chart, court visualization, heatmap, or tactical view in apps/web — the visual design system and dataviz conventions specific to this product's premium sports-analytics aesthetic.
---

# Sports data visualization

## Aesthetic mandate

Premium sports analytics + broadcast graphics + high-end analyst workstation. Not a generic SaaS dashboard full of cards. Graphite/dark-neutral background, subtly differentiated surfaces, strong typographic hierarchy (Geist Sans/Mono unless there's a demonstrable reason otherwise), one electric accent color for primary emphasis, separate semantic colors (success/error/warning) that don't compete with the accent, consistent spacing, high information density that stays legible.

## Visualization priority order

1. **2D top-down tactical court first.** More reliable and cheaper to get right than 3D, and covers most coaching use cases: player positions, rotations, serve origin/target, attack origin/destination, ball trajectory, movement traces, heatmaps, attack/serve zones, setter distribution, sideout-by-rotation, point timeline.
2. **3D only when it encodes real information** the 2D view can't — e.g. Technique Lab's skeleton view when a valid 3D reconstruction exists (Phase B biomechanics). Three.js/R3F is not a default; justify each use.

## Tooling

D3 for scales/geometry/data-driven positioning. SVG for vector, accessible, relatively low-element-count visuals (court markings, player tokens, trajectories). Canvas for high-element-count animation (many simultaneous trajectories/heatmap frames) where SVG would get slow. Motion for micro-interactions only — every animation must communicate something (time passing, a transition, a selection, a causal link), never pure decoration. Always implement `prefers-reduced-motion` as a real fallback, not an afterthought.

## The click-through requirement

Every number/mark in a visualization must be able to resolve back to `Statistic → Events → Rallies → Video` (see `docs/architecture/DATA_FLOW.md`). Build this into the component API from the start (e.g. every data point carries its source event/rally IDs) rather than bolting it on later.

## Accessibility & responsiveness

Desktop-first (this is an analyst workstation tool) but responsive at reasonable breakpoints. Keyboard-operable. Loading/error/empty states are not optional — a coach staring at a blank chart with no explanation is a real failure, not a minor polish gap.
