#!/usr/bin/env python3
"""Script to extract events from calendar images.

This script:
1. Checks if Ollama is installed
2. Checks if minicpm-v model is available
3. Starts Ollama if not running
4. Runs the extraction pipeline
"""

import subprocess
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def check_ollama_installed() -> bool:
    """Check if Ollama is installed."""
    try:
        result = subprocess.run(
            ["which", "ollama"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except Exception:
        return False


def check_model_available(model: str = "minicpm-v") -> bool:
    """Check if the required model is downloaded."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
        )
        return model in result.stdout
    except Exception:
        return False


def check_ollama_running() -> bool:
    """Check if Ollama server is running."""
    try:
        import requests
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def start_ollama() -> bool:
    """Start Ollama server in background."""
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Wait for it to start
        for _ in range(10):
            time.sleep(1)
            if check_ollama_running():
                return True
        return False
    except Exception:
        return False


def pull_model(model: str = "minicpm-v") -> bool:
    """Download the model if not available."""
    print(f"Descargando modelo {model}... (esto puede tomar varios minutos)")
    try:
        result = subprocess.run(
            ["ollama", "pull", model],
            capture_output=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def run_extraction(source_dir: Path, agency: str, month: str) -> None:
    """Run the extraction pipeline."""
    from aventure_tracker.services.image_event_extractor import ImageEventExtractor

    extractor = ImageEventExtractor()
    
    print(f"\nProcesando imágenes de: {source_dir}")
    print(f"Agencia: {agency}, Mes: {month}")
    print("-" * 50)

    total_events = 0
    total_time = 0

    for image_path in sorted(source_dir.iterdir()):
        if image_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".txt", ".webp"}:
            print(f"\n📷 {image_path.name}")
            
            result = extractor.extract_from_image(image_path, agency, month)
            total_time += result.processing_time_ms

            if result.success:
                if result.events:
                    print(f"   ✅ {len(result.events)} eventos encontrados ({result.processing_time_ms}ms)")
                    for event in result.events:
                        sold = " [AGOTADO]" if event.sold_out else ""
                        print(f"      • {event.name}: {event.date_start.day}-{event.date_end.day}/{event.date_start.month}, ${event.price:,}{sold}")
                    total_events += len(result.events)
                else:
                    print(f"   📄 Portada/sin eventos ({result.processing_time_ms}ms)")
            else:
                print(f"   ❌ Error: {result.error}")

    print("\n" + "=" * 50)
    print(f"TOTAL: {total_events} eventos extraídos en {total_time/1000:.1f}s")


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Extraer eventos de imágenes de calendarios")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("agent-calendars/brutal"),
        help="Directorio con las imágenes",
    )
    parser.add_argument(
        "--agency",
        type=str,
        default="brutal-travel",
        help="Nombre de la agencia",
    )
    parser.add_argument(
        "--month",
        type=str,
        default="agosto",
        help="Mes por defecto",
    )
    args = parser.parse_args()

    print("🔍 Verificando dependencias...\n")

    # 1. Check Ollama installed
    if not check_ollama_installed():
        print("❌ Ollama no está instalado.")
        print("\nPara instalar Ollama:")
        print("  macOS:  brew install ollama")
        print("  Linux:  curl -fsSL https://ollama.com/install.sh | sh")
        print("  Web:    https://ollama.com/download")
        return 1

    print("✅ Ollama instalado")

    # 2. Check model available
    if not check_model_available("minicpm-v"):
        print("⚠️  Modelo minicpm-v no encontrado")
        if not pull_model("minicpm-v"):
            print("❌ No se pudo descargar el modelo")
            return 1
    
    print("✅ Modelo minicpm-v disponible")

    # 3. Check/start Ollama server
    if not check_ollama_running():
        print("⏳ Iniciando Ollama server...")
        if not start_ollama():
            print("❌ No se pudo iniciar Ollama")
            print("\nIntenta manualmente: ollama serve")
            return 1
    
    print("✅ Ollama server corriendo")

    # 4. Check source directory
    if not args.source.exists():
        print(f"\n❌ Directorio no encontrado: {args.source}")
        return 1

    # 5. Run extraction
    run_extraction(args.source, args.agency, args.month)

    return 0


if __name__ == "__main__":
    sys.exit(main())
