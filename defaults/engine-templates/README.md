# Engine-Templates für den Llama Dispatcher
#
# Was ist das hier?
# ────────────────
# Dieses Verzeichnis enthält Vorlagen für Engine-Konfigurationen.
# Eine "Engine" = eine konkrete llama.cpp-Implementierung (CUDA, Vulkan, SYCL, …)
# mit ihrem spezifischen Binärverzeichnis (bin_dir).
#
# Diese Templates werden NICHT direkt vom Dispatcher geladen.
# Sie dienen als Vorlage zum Kopieren in deine Instanz.
#
# So verwendest du sie:
# ─────────────────────
# 1. Kopiere die passende Template-Datei in dein Instanz-Verzeichnis:
#       cp defaults/engine-templates/vulkan.yaml instances/Laptop/engines/vulkan.yaml
#
# 2. Passe den bin_dir-Pfad in der kopierten Datei an.
#
# 3. Referenziere die Engine in deinen Profilen:
#       defaults:
#         model:  "gemma"
#         engine: "vulkan"
#
# Der Dispatcher sucht Engine-Konfigurationen in dieser Reihenfolge:
#   1. instances/<name>/engines/<engine>.yaml   ← deine maschinenspezifischen Werte
#   2. defaults/engine-templates/<engine>.yaml  ← Fallback (dieser Ordner)
#
# Warum ist das getrennt von den Modell-Defaults?
# ────────────────────────────────────────────────
# - defaults/models/  → sampling-Parameter, hardware-agnostisch, öffentlich versioniert
# - instances/<name>/engines/ → bin_dir und Backend-Flags, maschinenspezifisch, privat
#
# Jede neue llama.cpp-Version, jeder neue Treiber → nur eine Datei ändern.

