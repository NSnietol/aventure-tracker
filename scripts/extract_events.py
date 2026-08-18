#!/usr/bin/env python3
"""Script to extract events from calendar images.

Uses Gemini (cloud) by default, or Ollama (local) as fallback.
Skips images that have already been processed (content-based deduplication).
"""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Load .env file
from dotenv import load_dotenv
load_dotenv()


def process_single_image(args: tuple) -> dict:
    """Process a single image (for thread pool).
    
    Args:
        args: Tuple of (image_path, agency, month, provider, cache_path, force)
    
    Returns:
        Dict with results.
    """
    from aventure_tracker.services.extraction.extractor import (
        ImageEventExtractor,
        ExtractionConfig,
        ModelProvider,
    )
    from aventure_tracker.services.extraction.cache import ExtractionCache
    
    image_path, agency, month, provider, cache_path, force = args
    
    # Check cache first (unless force is True)
    cache = ExtractionCache(cache_path)
    if not force:
        cached = cache.get_cached(image_path)
        if cached:
            return {
                "path": image_path,
                "cached": True,
                "events_count": cached.events_count,
                "is_cover": cached.is_cover,
            }
    
    # Not cached or force=True, process the image
    config = ExtractionConfig(provider=provider)
    extractor = ImageEventExtractor(config=config)
    
    result = extractor.extract_from_image(image_path, agency, month)
    
    # Cache the result if successful
    if result.success:
        cache.add(result)
    
    return {
        "path": image_path,
        "result": result,
        "cached": False,
    }


def run_extraction_parallel(
    source_dir: Path,
    agency: str,
    month: str,
    workers: int = 3,
    provider: str = "gemini",
    force: bool = False,
    cache_path: Path | None = None,
) -> None:
    """Run parallel extraction using thread pool.
    
    Args:
        source_dir: Directory with images (already organized).
        agency: Agency name.
        month: Month name.
        workers: Number of parallel workers.
        provider: Model provider (gemini or ollama).
        force: If True, ignore cache and reprocess all images.
        cache_path: Path to cache file.
    """
    from aventure_tracker.services.extraction.organizer import detect_file_type
    from aventure_tracker.services.extraction.extractor import ModelProvider
    from aventure_tracker.services.extraction.cache import ExtractionCache
    
    model_provider = ModelProvider.GEMINI if provider == "gemini" else ModelProvider.OLLAMA
    
    if cache_path is None:
        cache_path = Path("data/extraction_cache.yaml")
    
    cache = ExtractionCache(cache_path)
    
    print(f"\nProcesando imágenes de: {source_dir}")
    print(f"Agencia: {agency}, Mes: {month}")
    print(f"Provider: {provider}, Workers: {workers}")
    print("-" * 50)

    # Collect valid image files
    image_files = []
    skipped_cached = 0
    
    for file_path in sorted(source_dir.iterdir()):
        if file_path.name.startswith("."):
            continue
        # Use magic bytes to detect real images
        detected_type = detect_file_type(file_path)
        if detected_type:
            if not force and cache.is_processed(file_path):
                skipped_cached += 1
            else:
                image_files.append(file_path)
        else:
            print(f"   ⚠️  Ignorando {file_path.name} (tipo no reconocido)")

    if skipped_cached > 0:
        print(f"⏭️  {skipped_cached} imágenes ya procesadas (en cache)")

    if not image_files:
        if skipped_cached > 0:
            print("✅ Todas las imágenes ya fueron procesadas")
        else:
            print("❌ No se encontraron imágenes válidas")
        return

    print(f"\n📷 {len(image_files)} imágenes nuevas a procesar\n")

    total_events = 0
    total_time = 0
    cached_count = 0

    # Prepare args for thread pool
    task_args = [
        (img_path, agency, month, model_provider, cache_path, force)
        for img_path in image_files
    ]

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
                
                if data.get("cached"):
                    # This shouldn't happen often since we pre-filter
                    cached_count += 1
                    events_count = data["events_count"]
                    if events_count > 0:
                        print(f"⏭️  {img_path.name}: {events_count} eventos (cache)")
                        total_events += events_count
                    else:
                        print(f"⏭️  {img_path.name}: Portada (cache)")
                    continue
                
                result = data["result"]
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
    if total_time > 0:
        print(f"Tiempo de procesamiento: {total_time/1000:.1f}s (sum)")
        print(f"Tiempo real (paralelo):  {wall_time:.1f}s")
        if wall_time > 0:
            print(f"Speedup: {total_time/1000/wall_time:.1f}x")
    
    # Show cache stats
    stats = cache.get_stats()
    print(f"\n📊 Cache: {stats['total_images']} imágenes, {stats['total_events']} eventos totales")


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
    parser.add_argument(
        "--provider",
        type=str,
        choices=["gemini", "ollama"],
        default="gemini",
        help="Modelo a usar: gemini (cloud, rápido) u ollama (local, lento)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignorar cache y reprocesar todas las imágenes",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Limpiar cache antes de procesar",
    )
    parser.add_argument(
        "--cache-stats",
        action="store_true",
        help="Mostrar estadísticas del cache y salir",
    )
    args = parser.parse_args()

    from aventure_tracker.services.extraction.cache import ExtractionCache
    
    cache_path = Path("data/extraction_cache.yaml")
    cache = ExtractionCache(cache_path)

    # Handle cache-only commands
    if args.cache_stats:
        stats = cache.get_stats()
        print("📊 Estadísticas del cache:")
        print(f"   Total imágenes: {stats['total_images']}")
        print(f"   Total eventos:  {stats['total_events']}")
        print(f"   Portadas:       {stats['covers']}")
        print(f"\n   Por agencia:")
        for agency, count in stats['by_agency'].items():
            print(f"      {agency}: {count} imágenes")
        return 0

    if args.clear_cache:
        if args.agency:
            count = cache.clear_agency(args.agency)
            print(f"🗑️  Cache limpiado: {count} entradas de {args.agency}")
        else:
            count = cache.clear()
            print(f"🗑️  Cache limpiado: {count} entradas totales")
        if not args.source.exists():
            return 0

    print("🔍 Verificando configuración...\n")

    # Check provider requirements
    if args.provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("❌ GEMINI_API_KEY no configurada")
            print("\n1. Obtén tu API key en: https://aistudio.google.com/apikey")
            print("2. Agrégala a .env: GEMINI_API_KEY=tu_key_aquí")
            return 1
        print("✅ Gemini API key configurada")
    else:
        # Check Ollama
        import subprocess
        try:
            result = subprocess.run(["which", "ollama"], capture_output=True, text=True)
            if result.returncode != 0:
                print("❌ Ollama no está instalado")
                return 1
            print("✅ Ollama instalado")
            
            import requests
            try:
                response = requests.get("http://localhost:11434/api/tags", timeout=2)
                if response.status_code != 200:
                    raise Exception()
                print("✅ Ollama server corriendo")
            except Exception:
                print("❌ Ollama server no está corriendo. Ejecuta: ollama serve")
                return 1
        except Exception as e:
            print(f"❌ Error verificando Ollama: {e}")
            return 1

    # Check source directory
    if not args.source.exists():
        print(f"\n❌ Directorio no encontrado: {args.source}")
        print(f"\nCrea el directorio inbox con subdirectorios por agencia:")
        print(f"  mkdir -p inbox/brutal inbox/medellin-bungee")
        return 1

    # Discover agencies or use specified one
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
        return 1

    print(f"\n📁 Agencias encontradas: {', '.join(agencies)}")

    # Run extraction for each agency
    for agency, agency_dir in zip(agencies, agency_dirs):
        if not agency_dir.exists():
            print(f"\n⚠️  Directorio no encontrado: {agency_dir}")
            continue
        
        run_extraction_parallel(
            source_dir=agency_dir,
            agency=agency,
            month=args.month,
            workers=args.workers,
            provider=args.provider,
            force=args.force,
            cache_path=cache_path,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
