# Engine Templates for the Llama Dispatcher

This directory contains templates for backend/hardware configuration. An engine describes the llama.cpp implementation used on a machine (CUDA, Vulkan, SYCL, ...), including backend flags and process environment that must accompany that backend.

The templates are fallbacks/examples. Instance-specific engines normally live under `instances/<name>/engines/`.

## Create an instance engine

1. Copy or create the appropriate engine file in the instance:

   ```bash
   cp defaults/engine-templates/vulkan.yaml instances/Laptop/engines/vulkan-intel.yaml
   ```

2. Keep a standalone `bin_dir` fallback when useful. A launcher/runtime manager may override it explicitly with Dispatcher `--bin-dir PATH`, so Windows and WSL do not need duplicate profiles merely because the compiled llama.cpp directory differs.

3. Put backend/hardware environment in the engine instead of requiring the operator to remember shell exports:

   ```yaml
   bin_dir: "c:\\llama.cpp\\server\\server_vulkan"

   environment:
     GGML_VK_VISIBLE_DEVICES: "0"

   common:
     n-gpu-layers: 99
     split-mode: none
   ```

   For another backend the same mechanism can carry, for example:

   ```yaml
   environment:
     ONEAPI_DEVICE_SELECTOR: "level_zero:0"
   ```

   Dispatcher applies this environment while it runs the corresponding llama.cpp operation and restores the previous Dispatcher-process environment afterwards. The caller does not need to set these values in PowerShell, Bash, `.bashrc`, or `.profile`.

4. Reference the engine from a profile or ensemble:

   ```yaml
   defaults:
     model: "gemma"
     engine: "vulkan-intel"
   ```

The Dispatcher searches engine configuration in this order:

1. `instances/<name>/engines/<engine>.yaml` — instance hardware/backend policy;
2. `defaults/engine-templates/<engine>.yaml` — public fallback/template.

## Ownership

- model defaults: model/sampling behavior that is hardware-agnostic;
- engine: backend flags, device policy, optional standalone `bin_dir`, and required child-process environment;
- launcher/runtime manager: concrete machine-local binary/model roots supplied explicitly at process start.

`environment:` is Dispatcher policy and is never forwarded to llama.cpp as a CLI argument. Invalid environment names or non-scalar values fail clearly.
