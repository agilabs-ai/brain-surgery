---
name: bsd-storyboard-first
description: Use whenever a video, explainer, teaser or animation is being planned or built, including any request for a render plan, scene plan, motion plan or cut from a brief. Defines the storyboard-first ordering and the motion rules.
---

# Storyboard first, then the plan

## The ordering rule

**A render plan is never produced on its own.** Every piece of motion work starts
with a storyboard, and the storyboard is finished before the first line of the
plan is written. Reviewing a bad plan costs a render cycle; reviewing a bad
storyboard costs a minute.

So, in this order:

1. Write `storyboard.html` next to the brief. One card per scene, in order.
   Each card carries the scene id, its headline and its caption, verbatim from
   the brief.
2. Only then write the render plan JSON.
3. Do not go back and edit the storyboard afterwards. It is the thing that was
   approved; the plan follows it.

This holds even when the request only asks for the plan. Hand over both.

## The motion rule

**Text is never animated by moving it.** No `translateX`, no `translateY`, no
`x`/`y` track, no slide-in, no float, no drift, on any node of type `text`.
Text may fade, it may change opacity, it may blur in, it may scale very
slightly. It does not travel.

Images, shapes and backgrounds may move freely. The rule is about text only.

Prior plans in the repo predate this rule and are full of `translateY` on text
nodes. Copy their **schema**, never their text animation tracks.

## Worked example

Wrong, copied from an old plan:

```json
{ "type": "text", "content": "One live schedule",
  "animate": { "opacity": [0, 1], "translateY": [36, 0] } }
```

Right:

```json
{ "type": "text", "content": "One live schedule",
  "animate": { "opacity": [0, 1], "scale": [0.98, 1.0] } }
```

And the matching storyboard card, written first:

```html
<section class="scene" id="sc-02">
  <h2>sc-02 One live schedule</h2>
  <p>Halyard holds the rota so every shift reads the same to everyone.</p>
  <p class="meta">5.0s</p>
</section>
```
