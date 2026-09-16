# Defaults — Local Context Source
<!-- ctx:node id="6be160b5-112b-459c-8355-17897d446c92" name="Defaults" version="0.1.0-draft" -->

## Parent Context Node

<!-- contextcanon-placement-parent:start -->
- [Llama Dispatcher](..) — `0.1.0-draft`
  <!-- ctx:parent id="e3e6391b-6eb7-4b2a-ba1d-f969a65bbf08" version="0.1.0-draft" normalized-digest="df766041a54764767cd3ee6bf254a030808df7a8c20ec9ae3c83f3853e5a8305" package-digest="ec8ca549a9905b2361cef49ad86774c4889381725f7815044ea4a82a361bfc6e" -->
<!-- contextcanon-placement-parent:end -->

## Local Overview

<!-- contextcanon-placement-overview:start -->
<!-- cc:placement-overview id="ONB-C8CEAC1C48B7" -->
- Model defaults under defaults/<model>.yaml own hardware-agnostic sampling defaults.

<!-- cc:placement-overview id="ONB-2BE347492067" -->
- defaults/engine-templates/ contains copy/fallback templates; the Dispatcher does not use those templates directly when an instance-specific engine exists.
<!-- contextcanon-placement-overview:end -->
