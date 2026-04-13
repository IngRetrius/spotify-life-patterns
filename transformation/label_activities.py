"""
Etiquetado heuristico de actividades por sesion.

Cada sesion recibe una etiqueta basada en reglas que combinan:
- duration_minutes: duracion total de la sesion
- hour_of_day: hora de inicio (0-23)
- day_of_week: dia de la semana (0=lunes, 6=domingo)
- n_tracks: cantidad de canciones
- n_skips: canciones no completadas (< 50% escuchado)

Nota: las reglas originalmente incluian audio features (BPM, energy, valence).
Dado que el endpoint /audio-features esta restringido (403), las reglas
se basan unicamente en patrones temporales y de comportamiento.

Cada regla retorna un (label, confidence_score):
- confidence_score 1.0 = todas las condiciones cumplen
- confidence_score 0.7 = condiciones parciales
- Se aplica la regla con mayor confidence_score

Uso:
    python transformation/label_activities.py
"""

import sys
import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
import os

load_dotenv()


# ── Conexion ──────────────────────────────────────────────────────────────────

def get_db_connection():
    return psycopg2.connect(
        host="aws-1-us-east-1.pooler.supabase.com",
        port=6543,
        user="postgres.ofjjslcrzzllzaiiygya",
        password=os.getenv("SUPABASE_DB_PASSWORD"),
        dbname="postgres",
        sslmode="require",
    )


# ── Carga de datos ────────────────────────────────────────────────────────────

def load_sessions_with_features(conn) -> pd.DataFrame:
    """Une sessions con session_features en un solo DataFrame."""
    query = """
        SELECT
            s.session_id,
            s.duration_minutes,
            s.n_tracks,
            s.hour_of_day,
            s.day_of_week,
            sf.n_skips
        FROM sessions s
        LEFT JOIN session_features sf ON s.session_id = sf.session_id
    """
    df = pd.read_sql(query, conn)
    df["n_skips"] = df["n_skips"].fillna(0).astype(int)
    return df


# ── Reglas heuristicas ────────────────────────────────────────────────────────

def rule_ducha(row: pd.Series) -> float:
    """
    Ducha: sesion corta, sin pausas, en horario tipico de aseo.
    La incapacidad de interactuar con el telefono genera 0 skips
    y una duracion acotada.
    """
    score = 0.0
    if 5 <= row["duration_minutes"] <= 15:
        score += 0.4
    if row["n_skips"] == 0:
        score += 0.3
    if row["hour_of_day"] in range(6, 10) or row["hour_of_day"] in range(21, 24):
        score += 0.3
    return score


def rule_gimnasio(row: pd.Series) -> float:
    """
    Gimnasio: sesion larga sin interrupciones, dias habituales de ejercicio.
    """
    score = 0.0
    if 40 <= row["duration_minutes"] <= 100:
        score += 0.4
    if row["n_skips"] <= 2:
        score += 0.3
    if row["day_of_week"] in [0, 1, 2, 3, 4]:   # lunes a viernes
        score += 0.15
    if row["hour_of_day"] in list(range(5, 9)) + list(range(17, 21)):
        score += 0.15
    return score


def rule_moto(row: pd.Series) -> float:
    """
    Moto/transporte: sesion continua sin skips (no puede interactuar),
    duracion variable segun el trayecto.
    """
    score = 0.0
    if 10 <= row["duration_minutes"] <= 60:
        score += 0.4
    if row["n_skips"] == 0:
        score += 0.4
    if row["n_tracks"] >= 3:
        score += 0.2
    return score


def rule_trabajo(row: pd.Series) -> float:
    """
    Trabajo/concentracion: sesion muy larga en horario laboral entre semana.
    La musica de fondo genera pocos skips.
    """
    score = 0.0
    if row["duration_minutes"] > 60:
        score += 0.4
    if row["hour_of_day"] in range(8, 19):
        score += 0.3
    if row["day_of_week"] in [0, 1, 2, 3, 4]:
        score += 0.2
    if row["n_skips"] <= 3:
        score += 0.1
    return score


def rule_descanso(row: pd.Series) -> float:
    """
    Descanso/noche: sesion en horario nocturno.
    Puede ser larga (peliculas, antes de dormir) o corta.
    """
    score = 0.0
    if row["hour_of_day"] >= 22 or row["hour_of_day"] <= 1:
        score += 0.5
    if row["duration_minutes"] > 20:
        score += 0.3
    if row["n_skips"] <= 2:
        score += 0.2
    return score


RULES = {
    "ducha":     rule_ducha,
    "gimnasio":  rule_gimnasio,
    "moto":      rule_moto,
    "trabajo":   rule_trabajo,
    "descanso":  rule_descanso,
}

MIN_CONFIDENCE = 0.4   # si ninguna regla supera este umbral -> "desconocido"


def classify_session(row: pd.Series) -> tuple[str, float]:
    """
    Aplica todas las reglas y retorna la etiqueta con mayor confidence_score.
    Si ninguna supera el umbral minimo, retorna 'desconocido'.
    """
    scores = {label: fn(row) for label, fn in RULES.items()}
    best_label = max(scores, key=scores.get)
    best_score = scores[best_label]

    if best_score < MIN_CONFIDENCE:
        return "desconocido", best_score

    return best_label, round(best_score, 2)


# ── Escritura en base de datos ────────────────────────────────────────────────

UPSERT_LABELS_SQL = """
    INSERT INTO activity_labels (session_id, activity_label, confidence_score, labeling_method)
    VALUES (%(session_id)s, %(activity_label)s, %(confidence_score)s, %(labeling_method)s)
    ON CONFLICT (session_id) DO UPDATE SET
        activity_label   = EXCLUDED.activity_label,
        confidence_score = EXCLUDED.confidence_score;
"""


def upsert_labels(cursor, labels: list[dict]) -> None:
    if not labels:
        return
    psycopg2.extras.execute_batch(cursor, UPSERT_LABELS_SQL, labels, page_size=100)


# ── Orquestacion ──────────────────────────────────────────────────────────────

def run() -> None:
    print("=== Etiquetado de actividades ===")

    conn = get_db_connection()
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        df = load_sessions_with_features(conn)

        if df.empty:
            print("No hay sesiones con features. Corre los pasos anteriores primero.")
            return

        labels = []
        for _, row in df.iterrows():
            label, confidence = classify_session(row)
            labels.append({
                "session_id":       row["session_id"],
                "activity_label":   label,
                "confidence_score": confidence,
                "labeling_method":  "heuristic",
            })

        upsert_labels(cursor, labels)
        conn.commit()

        print(f"{len(labels)} sesiones etiquetadas:\n")
        print(f"  {'Sesion':<12} {'Duracion':>10} {'Hora':>6} {'Skips':>6}  {'Actividad':<12} {'Score':>6}")
        print(f"  {'-'*60}")
        for i, (_, row) in enumerate(df.iterrows()):
            lbl = labels[i]
            print(
                f"  {lbl['session_id'][:8]}...  "
                f"{row['duration_minutes']:>8.1f}m  "
                f"{row['hour_of_day']:>4}h  "
                f"{row['n_skips']:>5}  "
                f"  {lbl['activity_label']:<12}  "
                f"{lbl['confidence_score']:>5.2f}"
            )

        print(f"\nResumen: {len(labels)} etiquetas escritas en activity_labels.")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        sys.exit(1)

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    run()
