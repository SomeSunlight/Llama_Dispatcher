# Engine Templates for the Llama Dispatcher
#
# What is this?
# ────────────────
# This directory contains templates for engine configurations.
# An "Engine" = a specific llama.cpp implementation (CUDA, Vulkan, SYCL, ...)
# with its specific binary directory (bin_dir).
#
# These templates are NOT loaded directly by the Dispatcher.
# They serve as templates for copying into your instance.
#
# How to use them:
# ─────────────────────
# 1. Copy the appropriate template file to your instance directory:
#       cp defaults/engine-templates/vulkan.yaml instances/Laptop/engines/vulkan.yaml
#
# 2. Adjust the bin_dir path in the copied file.
#
# 3. Reference the engine in your profiles:
#       defaults:
#         model:  "gemma"
#         engine: "vulkan"
#
# The Dispatcher searches for engine configurations in this order:
#   1. instances/<name>/engines/<engine>.yaml   ← your machine-specific values
#   2. defaults/engine-templates/<engine>.yaml  ← Fallback (this directory)
#
# Why is this separate from model defaults?
# ────────────────────────────────────────────────
# - defaults/models/  → sampling parameters, hardware-agnostic, publicly versioned
# - instances/<name>/engines/ → bin_dir and backend flags, machine-specific, private
#
# Every new llama.cpp version, every new driver → change only one file.
