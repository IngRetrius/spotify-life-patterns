"""
Etiquetado heuristico de actividades por sesion.

Actividades detectadas: ducha, gimnasio, tareas
(+ 'desconocido' cuando ninguna regla supera el umbral minimo)

Cada regla retorna un score entre 0 y 1.
Se elige la regla con mayor score.
Si ninguna supera MIN_CONFIDENCE -> 'desconocido'.

Senales disponibles (sin audio features por restriccion API):
- duration_minutes : duracion total de la sesion
- n_tracks         : cantidad de canciones
- n_skips          : canciones escuchadas menos del 50%
- hour_of_day      : hora de inicio (0-23)
- day_of_week      : dia (0=lunes, 6=domingo)

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

# ── Horarios por actividad ────────────────────────────────────────────────────
# Definidos como conjuntos para hacer la busqueda O(1)

SHOWER_HOURS     = set(range(6, 11))  | set(range(20, 24))  # 6-10h y 20-23h
GYM_HOURS        = set(range(5, 11))  | set(range(16, 23))  # 5-10h y 16-22h
NIGHT_STUDY_HOURS = set(range(22, 24)) | set(range(0, 6))   # 22-23h y 0-5h (madrugada)

MIN_CONFIDENCE = 0.4


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
    Ducha: sesion corta, sin skips, en horario de aseo.

    La condicion dominante es la duracion corta (5-20 min).
    El usuario no puede interactuar con el telefono -> 0 skips.
    Bonus si el horario es tipico de ducha (manana o noche).

    Max score: 0.5 + 0.3 + 0.2 = 1.0
    """
    score = 0.0
    if 5 <= row["duration_minutes"] <= 20:
        score += 0.5   # condicion principal — corta y acotada
    if row["n_skips"] == 0:
        score += 0.3   # no puede tocar el telefono en la ducha
    if row["hour_of_day"] in SHOWER_HOURS:
        score += 0.2   # horario tipico de aseo
    return score


def rule_gimnasio(row: pd.Series) -> float:
    """
    Gimnasio: duracion de entrenamiento + musica continua + horario de gym.

    Las tres condiciones juntas distinguen el gym del estudio nocturno:
    el gym rara vez ocurre a las 3am y suele tener pocos skips.

    Max score: 0.4 + 0.3 + 0.3 = 1.0
    """
    score = 0.0
    if 35 <= row["duration_minutes"] <= 110:
        score += 0.4   # duracion tipica de entrenamiento
    if row["n_skips"] <= 2:
        score += 0.3   # musica continua, no interrumpe el ejercicio
    if row["hour_of_day"] in GYM_HOURS:
        score += 0.3   # 5-10am o 4-10pm — horario real de gym
    return score


def rule_tareas(row: pd.Series) -> float:
    """
    Tareas/Trabajo: sesion larga con musica de fondo.

    La duracion larga es la senal principal.
    El bonus de madrugada (0-5am) diferencia el estudio nocturno
    del gimnasio: ambos pueden durar 60-100 min, pero el gym
    no ocurre a las 3am.

    Max score: 0.5 + 0.2 + 0.3 = 1.0
    """
    score = 0.0
    if row["duration_minutes"] > 40:
        score += 0.5   # sesiones largas = concentracion sostenida
    if row["n_skips"] <= 5:
        score += 0.2   # musica de fondo: pocos skips pero mas que gym
    if row["hour_of_day"] in NIGHT_STUDY_HOURS:
        score += 0.3   # madrugada = estudio/trabajo nocturno
    return score


RULES = {
    "ducha":    rule_ducha,
    "gimnasio": rule_gimnasio,
    "tareas":   rule_tareas,
}


def classify_session(row: pd.Series) -> tuple[str, float]:
    """
    Aplica las 3 reglas y retorna la etiqueta con mayor score.
    Si ninguna supera MIN_CONFIDENCE -> 'desconocido'.
    """
    scores = {label: fn(row) for label, fn in RULES.items()}
    best_label = max(scores, key=scores.get)
    best_score = round(scores[best_label], 2)

    if best_score < MIN_CONFIDENCE:
        return "desconocido", best_score

    return best_label, best_score


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
            print("No hay sesiones. Corre build_sessions.py primero.")
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
        print(f"  {'Sesion':<10} {'Dur':>8} {'Hora':>5} {'Skips':>6}  {'Actividad':<12} {'Score':>6}")
        print(f"  {'-'*55}")
        for i, (_, row) in enumerate(df.iterrows()):
            lbl = labels[i]
            print(
                f"  {lbl['session_id'][:8]}...  "
                f"{row['duration_minutes']:>6.1f}m  "
                f"{row['hour_of_day']:>3}h  "
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
