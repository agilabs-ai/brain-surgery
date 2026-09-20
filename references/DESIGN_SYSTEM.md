# Brain Surgery report design system

Brain Surgery is an AGI Labs product surface. The approved ZIP owns its visual treatment and
copy; runtime schemas and evidence still determine which states and claims can render.

## Tokens

- Background: `#FFFFFF`
- Primary text: `#050505`
- Muted text: `#6B6B6B`
- Border: `#E5E5E5`
- Accent: product blue `#154CFF`
- Soft accent: `#EEF3FF`
- Font: Inter/system sans fallback
- Radius: 9px for controls; 12–14px only for report containers

No gradients, medical green, neon palette, decorative shadows, or new brand typography.

## Hierarchy

For a read-only scan:

1. inventory/reach state and scan completeness
2. confirmed, suspected, and observational findings
3. local evidence and the explicit share boundary

For an earned paired comparison:

1. measured current → tested task or trial pass rate
2. one-sentence, state-aware interpretation
3. workflow-level evidence, including ties and regressions
4. detailed local evidence and the explicit share/apply boundaries

The local and public summary should look almost identical. Privacy comes from a smaller public payload, not from visually hiding private elements.

## Brain gauge

The left hemisphere represents current task or trial pass rate in black; the right hemisphere
represents the tested rate in product blue. Fill height is data-driven. The bottom rule repeats
the same comparison in a minimal linear gauge. A scan-only report does not use this visual to
imply uplift. A model matrix appears only when all of its cells have real replay evidence.

Unknown data is an unknown state, not 0%.
