"""
Orquestador del pipeline completo.

Ejecuta los 6 pasos en orden:
  1. Ingesta de plays
  2. Ingesta de audio features
  3. Ingesta de artistas
  4. Construccion de sesiones
  5. Calculo de features por sesion
  6. Etiquetado de actividades

Por que existe este script:
- Punto de entrada unico para correr todo el pipeline de una vez
- Facilita el debug: si un paso falla, los anteriores no se revierten
- Muestra el tiempo de cada paso (util para optimizar en el futuro)

Uso:
    python scripts/run_pipeline.py              # pipeline completo
    python scripts/run_pipeline.py --from 4     # solo transformacion (pasos 4-6)
"""

import sys
import time
import argparse

# Importamos los modulos de cada paso
sys.path.insert(0, ".")

from ingestion.ingest_plays          import run as run_plays
from ingestion.ingest_audio_features import run as run_audio_features
from ingestion.ingest_artists        import run as run_artists
from transformation.build_sessions   import run as run_build_sessions
from transformation.compute_features import run as run_compute_features
from transformation.label_activities import run as run_label_activities


STEPS = [
    (1, "Ingesta de plays",          run_plays),
    (2, "Ingesta de audio features", run_audio_features),
    (3, "Ingesta de artistas",       run_artists),
    (4, "Construccion de sesiones",  run_build_sessions),
    (5, "Features por sesion",       run_compute_features),
    (6, "Etiquetado de actividades", run_label_activities),
]


def run(from_step: int = 1) -> None:
    print("=" * 50)
    print("   SPOTIFY LIFE PATTERNS — PIPELINE COMPLETO")
    print("=" * 50)

    pipeline_start = time.time()
    failed = False

    for step_num, step_name, step_fn in STEPS:
        if step_num < from_step:
            print(f"\n[{step_num}/6] {step_name} — omitido")
            continue

        print(f"\n[{step_num}/6] {step_name}")
        print("-" * 40)
        step_start = time.time()

        try:
            step_fn()
            elapsed = time.time() - step_start
            print(f"[OK] {elapsed:.1f}s")
        except SystemExit:
            # Los scripts llaman sys.exit(1) en error
            print(f"[FALLO] Paso {step_num} fallo. Deteniendo pipeline.")
            failed = True
            break

    total = time.time() - pipeline_start
    print("\n" + "=" * 50)
    if failed:
        print(f"Pipeline FALLIDO en {total:.1f}s")
        sys.exit(1)
    else:
        print(f"Pipeline COMPLETO en {total:.1f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline completo de Spotify Life Patterns")
    parser.add_argument(
        "--from", dest="from_step", type=int, default=1,
        help="Paso desde el que empezar (1-6). Default: 1 (todo)"
    )
    args = parser.parse_args()
    run(from_step=args.from_step)
