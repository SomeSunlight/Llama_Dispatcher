# Defaults — Local Context Source
<!-- ctx:node id="6be160b5-112b-459c-8355-17897d446c92" name="Defaults" version="0.1.1-draft" -->

<!-- contextcanon:format Node
Format: Node metadata follows the # title: ctx:node id="..." name="..." version="...". Preserve existing identity.
Details: CONTEXT-format.md
-->

<!-- contextcanon:source-help:intro:start -->
Edit this local Context source; ContextCanon generates CONTEXT.md from it.
Some sections use a strict syntax. The comments below show the expected format.
New Rules, Topics and Resources receive IDs automatically during build; preserve existing IDs.
See [the source format guide](CONTEXT-format.md) for examples and editing instructions.
<!-- contextcanon:source-help:intro:end -->

## Context Imports

<!-- contextcanon:format Context Imports
Format: - [Name](location) — `version` — `relationship=parent|reference`; optional indented Why:, then ctx:source metadata. Preserve exact pins; use source list/adopt/update for package identity.
Details: CONTEXT-format.md
-->

<!-- contextcanon-placement-parent:start -->
- [Llama Dispatcher](..) — `0.1.2-draft` — `relationship=parent`
  <!-- ctx:source id="e3e6391b-6eb7-4b2a-ba1d-f969a65bbf08" version="0.1.2-draft" normalized-digest="ef5444bb73d49f4914fe680cedc8ad0679da599ed4c7ef68ca910be9969620fa" package-digest="21c98f31b5b1bb1c552f6a1c1a1cdeb853ad2f899ddb37db6e66b0aa678bcb4f" -->
<!-- contextcanon-placement-parent:end -->

## Local Overview

<!-- contextcanon:format Local Overview
Format: Ordinary Markdown orientation, local to this Node. Any existing placement identity follows its paragraph/item; do not change it.
Details: CONTEXT-format.md
-->

<!-- contextcanon-placement-overview:start -->
- Model defaults under defaults/<model>.yaml own hardware-agnostic sampling defaults.
  <!-- cc:placement-overview id="ONB-C8CEAC1C48B7" -->

- defaults/engine-templates/ contains copy/fallback templates; the Dispatcher does not use those templates directly when an instance-specific engine exists.
  <!-- cc:placement-overview id="ONB-2BE347492067" -->
<!-- contextcanon-placement-overview:end -->
