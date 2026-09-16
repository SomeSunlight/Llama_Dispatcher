# Harness Adapters

ContextCanon is harness- and model-independent.

`CONTEXT.md` is the compact official entry view into a node's Official Context Package. Harness-specific files are generated adapters that direct a particular tool to that entry view.

`CONTEXT.md` is deliberately self-describing: it states that Rules apply to every task in the Node and explains how to evaluate Topics and load Required versus Optional targets. Adapters therefore stay small and do not need to duplicate those semantics.

## Design rule

Canonical project context and project code must not depend on Codex, goose, Copilot, Claude, or another particular harness.

Do not copy the full project context into every harness-specific file. An adapter should be as small as the harness allows and contain only the mechanics needed to enter ContextCanon correctly.

## Gateway nodes

A harness adapter should enter the Context Node that applies at its filesystem scope. It should not bypass a minimal Gateway merely because a deeper node contains more information.

For a repository with a root Gateway, root adapters enter that Gateway. Topics can then route framework, product, release, or other task-specific work to deeper Nodes without changing which governance the Gateway itself publishes.

This keeps harness behavior mechanical and lets ContextCanon decide how much context a task needs.

## AGENTS.md

ContextCanon can generate `AGENTS.md` as a shared entry point for harnesses that support it.

A generated adapter points the harness to the applicable `CONTEXT.md` rather than duplicating the complete package. This is the preferred path whenever a harness can attach `AGENTS.md` to its requests.

OpenAI documents `AGENTS.md` as persistent repository guidance for Codex, including hierarchical files scoped by directory.

OpenAI references:
- https://openai.com/index/introducing-codex/
- https://openai.com/index/unrolling-the-codex-agent-loop/

## GitHub Copilot in JetBrains

ContextCanon uses the same generated `AGENTS.md` entry point for GitHub Copilot in JetBrains instead of generating a second Copilot-specific instruction file.

In JetBrains, verify under **Tools → GitHub Copilot → Customizations** that **Use AGENTS.md file** is enabled. In the tested Copilot configuration this setting states that instructions from `AGENTS.md` are attached to all chat requests.

ContextCanon therefore relies on this harness configuration for Copilot. If a Copilot installation does not consume `AGENTS.md`, configure the harness to do so rather than duplicating the canonical entry instructions in another repository file.

This keeps the integration simple: one generated agent entry file points to one self-describing `CONTEXT.md`.

## goose

Current goose documentation lists the default `CONTEXT_FILE_NAMES` value as `[".goosehints"]` and allows custom/multiple filenames.

ContextCanon therefore generates a small `.goosehints` adapter that points to the applicable `CONTEXT.md`, instead of assuming goose automatically loads `AGENTS.md`.

goose reference:
- https://github.com/block/goose/blob/main/documentation/docs/guides/environment-variables.md

## Other harnesses

Additional adapters should be added only after verifying the harness's current behavior and configuration.

Harness configuration changes faster than the ContextCanon semantic model. Compatibility therefore belongs in this dedicated adapter layer rather than in project governance, canonical context semantics, or project code.
