#!/usr/bin/env python3
"""Script to extract events from calendar images.

This script:
1. Checks if Ollama is installed
2. Checks if minicpm-v model is available
3. Starts Ollama if not running
4. Organizes images by agency (fixing extensions via magic bytes)
5. Runs parallel extraction using thread pool
"""

import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def process_single_image(args: tuple) -> dict:
    """Process a single image (for thread pool).
    
    Args:
        args: Tuple of (image_path, extractor, agency, month)
    
    Returns:
        Dict with results.
    """
    from aventure_tracker.services.image_event_extractor import ImageEventExtractor
    
    image_path, agency, month = args
    extractor = ImageEventExtractor()
    
    result = extractor.extract_from_image(image_path, agency, month)
    
    return {
        "path": image_path,
        "result": result,
    }


def run_extraction_parallel(
    source_dir: Path,
    agency: str,
    month: str,
    workers: int = 3,
) -> None:
    """Run parallel extraction using thread pool.
    
    Args:
        source_dir: Directory with images (already organized).
        agency: Agency name.
        month: Month name.
        workers: Number of parallel workers.
    """
    from aventure_tracker.services.file_organizer import detect_file_type
    
    print(f"\nProcesando imágenes de: {source_dir}")
    print(f"Agencia: {agency}, Mes: {month}, Workers: {workers}")
    print("-" * 50)

    # Collect valid image files
    image_files = []
    for file_path in sorted(source_dir.iterdir()):
        if file_path.name.startswith("."):
            continue
        # Use magic bytes to detect real images
        detected_type = detect_file_type(file_path)
        if detected_type:
            image_files.append(file_path)
        else:
            print(f"   ⚠️  Ignorando {file_path.name} (tipo no reconocido)")

    if not image_files:
        print("❌ No se encontraron imágenes válidas")
        return

    print(f"\n📷 {len(image_files)} imágenes a procesar\n")

    total_events = 0
    total_time = 0
    results_list = []

    # Prepare args for thread pool
    task_args = [(img_path, agency, month) for img_path in image_files]

    start_time = time.time()

    # Process in parallel
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_path = {
            executor.submit(process_single_image, args): args[0]
            for args in task_args
        }

        for future in as_completed(future_to_path):
            img_path = future_to_path[future]
            try:
                data = future.result()
                result = data["result"]
                results_list.append(data)

                total_time += result.processing_time_ms

                if result.success:
                    if result.events:
                        print(f"✅ {img_path.name}: {len(result.events)} eventos ({result.processing_time_ms}ms)")
                        for event in result.events:
                            sold = " [AGOTADO]" if event.sold_out else ""
                            print(f"   • {event.name}: {event.date_start.day}-{event.date_end.day}/{event.date_start.month}, ${event.price:,}{sold}")
                        total_events += len(result.events)
                    else:
                        print(f"📄 {img_path.name}: Portada/sin eventos ({result.processing_time_ms}ms)")
                else:
                    print(f"❌ {img_path.name}: {result.error}")

            except Exception as e:
                print(f"❌ {img_path.name}: Error: {e}")

    wall_time = time.time() - start_time

    print("\n" + "=" * 50)
    print(f"TOTAL: {total_events} eventos extraídos")
    print(f"Tiempo de procesamiento: {total_time/1000:.1f}s (sum)")
    print(f"Tiempo real (paralelo):  {wall_time:.1f}s")
    print(f"Speedup: {total_time/1000/wall_time:.1f}x")


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Extraer eventos de imágenes de calendarios")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("inbox"),
        help="Directorio con las imágenes organizadas por agencia (default: inbox)",
    )
    parser.add_argument(
        "--agency",
        type=str,
        default=None,
        help="Procesar solo esta agencia (default: todas)",
    )
    parser.add_argument(
        "--month",
        type=str,
        default="agosto",
        help="Mes por defecto",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Número de threads paralelos (default: 3)",
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
        print(f"\nCrea el directorio inbox con subdirectorios por agencia:")
        print(f"  mkdir -p inbox/brutal inbox/medellin-bungee")
        print(f"  # Luego copia las imágenes a cada subdirectorio")
        return 1

    # 5. Discover agencies or use specified one
    if args.agency:
        agencies = [args.agency]
        agency_dirs = [args.source / args.agency]
    else:
        agency_dirs = [
            d for d in args.source.iterdir() 
            if d.is_dir() and not d.name.startswith(".")
        ]
        agencies = [d.name for d in agency_dirs]

    if not agencies:
        print(f"\n❌ No se encontraron agencias en {args.source}")
        print(f"\nEstructura esperada:")
        print(f"  {args.source}/brutal/imagen1.jpg")
        print(f"  {args.source}/medellin-bungee/imagen2.png")
        return 1

    print(f"\n📁 Agencias encontradas: {', '.join(agencies)}")

    # 6. Run extraction for each agency
    for agency, agency_dir in zip(agencies, agency_dirs):
        if not agency_dir.exists():
            print(f"\n⚠️  Directorio no encontrado: {agency_dir}")
            continue
        
        run_extraction_parallel(
            source_dir=agency_dir,
            agency=agency,
            month=args.month,
            workers=args.workers,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
