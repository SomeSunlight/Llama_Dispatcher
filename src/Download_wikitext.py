import urllib.request
import zipfile
import os
from pathlib import Path


def download_wikitext():
    url = "https://huggingface.co/datasets/ggml-org/ci/resolve/main/wikitext-2-raw-v1.zip"
    data_dir = Path("../data")
    zip_path = data_dir / "wikitext-2-raw-v1.zip"
    extract_dir = data_dir / "wikitext-2-raw"

    # Stelle sicher, dass das data Verzeichnis existiert
    data_dir.mkdir(parents=True, exist_ok=True)

    print(f"Lade Datensatz herunter von: {url} ...")
    urllib.request.urlretrieve(url, zip_path)
    print("Download abgeschlossen.")

    print("Entpacke Archiv...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)

    # Aufräumen
    os.remove(zip_path)

    # Der relevante Text für llama-perplexity ist die 'test' Datei
    target_file = extract_dir / "wikitext-2-raw" / "wiki.test.raw"
    final_dest = data_dir / "wikitext-2-raw.txt"

    if target_file.exists():
        target_file.rename(final_dest)
        print(f"Erfolg! Der Referenztext liegt nun bereit unter: {final_dest}")
    else:
        print("[FEHLER] Erwartete Textdatei im Archiv nicht gefunden.")


if __name__ == "__main__":
    download_wikitext()