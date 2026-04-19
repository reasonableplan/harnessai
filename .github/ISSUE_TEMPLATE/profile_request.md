---
name: Profile request
about: Request a new stack profile (e.g. go-chi, rust-axum, next.js, electron)
title: "[profile] "
labels: profile-request
---

## Stack
<!-- Language + framework. Be specific: "Go with chi router + pgx" not just "Go". -->

## Detection rules
<!-- Which files indicate this stack?
  - paths: [".", "backend/"]
  - files: [go.mod]
  - contains: { go.mod: ["chi"] }
-->

## Components
<!-- Which component types are mandatory for projects in this stack?
  - interface.http / core.logic / persistence / errors / ...
-->

## skeleton_sections
<!-- Which of the 20 standard section IDs does this stack need? Any new sections? -->

## toolchain
<!--
  test:   "..."
  lint:   "..."
  type:   "..."   # or null if the language has no static typing
  format: "..."
-->

## whitelist
<!--
  runtime: [list of allowed packages]
  dev:     [list of allowed dev/test packages]
  prefix_allowed: [prefix patterns like "@radix-ui/"]
-->

## Existing reference project
<!-- Link to a real project in this stack that you would dogfood against. -->
