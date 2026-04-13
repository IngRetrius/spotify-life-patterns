# Capa de Visualización — Decisiones de diseño

> Este archivo documenta el razonamiento detrás de cada decisión del dashboard.
> Es la respuesta a "¿por qué diseñaste la visualización así?" en una entrevista.

---

## Por qué Streamlit y no Power BI, Metabase o Grafana

Las alternativas más comunes para dashboards de datos:

| Herramienta | Por qué se descartó |
|---|---|
| Power BI / Tableau | Requieren licencia, no se deployan como código, difícil de versionar |
| Metabase / Grafana | Excelentes para equipos de operaciones, no para portfolios de ingeniería |
| Dash (Plotly) | Más flexible, pero requiere más boilerplate para un resultado similar |
| Flask + D3.js | Control total, pero el costo de desarrollo es desproporcionado para este caso |
| **Streamlit** | Se deploya con una línea, el código es Python puro, se versiona en git como cualquier script |

La ventaja clave de Streamlit en un portfolio de Data Engineering es que **el dashboard es
código**. Un entrevistador puede leer `app.py` y entender exactamente cómo se construyó
la visualización, qué queries se hacen, cómo se manejan las dependencias de datos.

Con Power BI o Metabase, eso no es posible.

---

## Por qué `queries.py` separado de `app.py`

Toda la lógica SQL vive en `dashboard/queries.py`. El `app.py` solo define el layout.

```
dashboard/
├── app.py       ← qué se muestra y cómo (layout, CSS, charts)
└── queries.py   ← qué datos se traen y cómo (SQL, engine, transformaciones)
```

**Razón principal: separación de responsabilidades.**

Si cambia el schema de la base de datos (por ejemplo, se agrega una columna),
solo hay que modificar `queries.py`. El layout de `app.py` no se toca.

Si en el futuro se migra de Supabase a otro motor (BigQuery, Redshift),
se reescribe `queries.py` y `app.py` queda intacto.

Esto también hace que las queries sean testeables de forma aislada:
```bash
# Verificar que todas las queries funcionan sin lanzar el servidor Streamlit
python -c "
from dashboard.queries import get_engine, load_kpis, load_sessions
engine = get_engine()
print(load_kpis(engine))
print(load_sessions(engine).shape)
"
```

---

## `@st.cache_resource` vs `@st.cache_data`

Streamlit tiene dos tipos de caché con propósitos distintos:

| Decorator | Para qué sirve | Cuándo se invalida |
|---|---|---|
| `@st.cache_resource` | Objetos que no se pueden serializar (conexiones, modelos ML) | Solo al reiniciar el servidor |
| `@st.cache_data` | Datos serializables (DataFrames, dicts, listas) | Al cambiar los argumentos o al expirar el TTL |

En el dashboard se usan así:

```python
@st.cache_resource
def _engine():
    # El engine de SQLAlchemy gestiona un pool de conexiones.
    # Crearlo una vez y reutilizarlo evita abrir una nueva conexion
    # en cada interaccion del usuario con la pagina.
    return get_engine()

@st.cache_data
def _sessions():
    # El DataFrame se cachea en memoria.
    # Cada vez que un usuario abre la pagina obtiene los mismos datos
    # sin hacer una query adicional a Supabase.
    return load_sessions(_engine())
```

**Por qué no usar `@st.cache_data` para el engine:**
El engine contiene un pool de conexiones activas que no se puede serializar (pickle).
Intentarlo lanza un error. `@st.cache_resource` está diseñado exactamente para esto.

**Por qué no usar `@st.cache_resource` para los DataFrames:**
`@st.cache_resource` comparte el objeto entre todos los usuarios sin copiarlo.
Si una función modificara el DataFrame (aunque aquí no ocurre), todos los usuarios
verían el dato modificado. `@st.cache_data` hace una copia por cada usuario.

---

## Por qué SQLAlchemy y no psycopg2 directo

```python
# Forma que genera un warning en pandas >= 2.0:
df = pd.read_sql(query, psycopg2_conn)

# Forma correcta:
df = pd.read_sql(query, sqlalchemy_engine)
```

A partir de pandas 2.0, `read_sql` requiere un engine de SQLAlchemy o una URL de
conexión. Pasar una conexión psycopg2 cruda genera un `UserWarning` y en versiones
futuras de pandas dejará de funcionar.

Además, SQLAlchemy gestiona automáticamente un **pool de conexiones**: en lugar de
abrir y cerrar una conexión TCP por cada query, reutiliza las existentes. Con el
pooler de Supabase (modo transaction, puerto 6543) esto reduce la latencia notablemente.

---

## El patrón `_get_password()` — dos fuentes de credenciales

El dashboard necesita funcionar en dos ambientes con formas distintas de pasar secretos:

| Ambiente | Cómo se leen las credenciales |
|---|---|
| Local | `python-dotenv` carga `.env` como variables de entorno → `os.getenv()` |
| Streamlit Cloud | Los secrets del dashboard se acceden via `st.secrets`, NO son env vars automáticas |

```python
def _get_password() -> str:
    # 1. Intenta como variable de entorno (funciona local con .env)
    password = os.getenv("SUPABASE_DB_PASSWORD")

    # 2. Si no esta, intenta Streamlit Cloud secrets
    if not password:
        try:
            import streamlit as st
            password = st.secrets.get("SUPABASE_DB_PASSWORD")
        except Exception:
            pass

    # 3. Si no hay en ninguna fuente, falla con un mensaje claro
    if not password:
        raise EnvironmentError(
            "SUPABASE_DB_PASSWORD not found. "
            "Set it in .env (local) or Streamlit Cloud secrets (deploy)."
        )
    return password
```

Este patrón evita tener dos versiones del archivo de conexión (una para local, una para
deploy) y hace explícito el orden de prioridad de fuentes.

---

## Por qué la conversión de timezone ocurre en SQL y no en Python

```sql
-- En queries.py:
s.start_time AT TIME ZONE 'America/Bogota' AS start_time
```

La alternativa sería traer el timestamp en UTC y convertirlo en Python:
```python
df["start_time"] = df["start_time"].dt.tz_convert("America/Bogota")
```

Se eligió SQL por dos razones:

1. **Los datos llegan ya en el timezone correcto.** El DataFrame no necesita ser
   manipulado después de cargarse — lo que lees es lo que el usuario ve.

2. **Centraliza la lógica de presentación en un solo lugar.** Cualquier query que
   exponga timestamps al usuario los convierte en la misma capa (SQL), en vez de
   depender de que cada fragmento de código Python recuerde hacer la conversión.

La regla general: guarda siempre en UTC, convierte al timezone del usuario en la
capa de presentación. Aquí esa capa es la query SQL del dashboard.

---

## Por qué Plotly y no Altair (el default de Streamlit)

Streamlit incluye Altair como visualización integrada. Se eligió Plotly porque:

| Característica | Altair | Plotly |
|---|---|---|
| Interactividad (hover, zoom, pan) | Limitada | Completa |
| Customización de tooltips | Declarativa, verbose | Directa con `hovertemplate` |
| Gráficos 3D y mapas | No | Sí (útil en fases futuras) |
| Ecosistema | Vega-Altair | Amplio, bien documentado |

Para un portfolio que muestra patrones de comportamiento, la interactividad de Plotly
permite al visitante explorar los datos (por ejemplo, hovear una sesión y ver su
duración exacta), lo cual hace la presentación más convincente.

---

## Por qué no hay botón de actualizar datos

El dashboard no tiene un botón "Refresh". Los datos se cargan al abrir la página
y se sirven desde caché hasta que el servidor se reinicia.

**Justificación para este caso:**
- El pipeline corre cada 6 horas via GitHub Actions. Los datos no cambian en tiempo real.
- Agregar un botón de refresh requeriría llamar `st.cache_data.clear()`, lo que invalida
  el caché para todos los usuarios simultáneamente.
- Para el volumen actual (4 sesiones), la latencia de una query directa es mínima,
  pero el patrón con caché es correcto para escalar a cientos de sesiones sin
  saturar el pooler de Supabase con requests redundantes.

Cuando el dataset crezca significativamente, se puede agregar un parámetro `ttl`
al decorador de caché:
```python
@st.cache_data(ttl=3600)  # invalida cada hora automaticamente
def _sessions():
    return load_sessions(_engine())
```

---

## Por qué AT TIME ZONE genera `timestamp without time zone` en pandas

Un detalle técnico relevante: cuando PostgreSQL aplica `AT TIME ZONE` a un
`TIMESTAMPTZ`, el resultado es un `timestamp without time zone` (el offset ya
fue aplicado, la zona ya no está embebida en el valor).

Pandas lee esto como un datetime naive (sin tzinfo). Por eso en `app.py`:
```python
pd.to_datetime(df["start_time"]).dt.strftime("%b %d, %Y  %H:%M")
```
No hace falta llamar `.dt.tz_localize()` ni `.dt.tz_convert()` — el valor
ya está en hora de Bogotá, aunque no tenga el offset explícito.

---

## Resumen ejecutivo para entrevistas

Cuatro principios aplicados en esta capa:

1. **Separación UI / datos**
   `queries.py` contiene todo el SQL. `app.py` solo define el layout.
   Cambiar el schema no requiere tocar la presentación, y viceversa.

2. **Caché por tipo de objeto**
   `@st.cache_resource` para el pool de conexiones (no serializable),
   `@st.cache_data` para los DataFrames (serializable, copiado por usuario).

3. **Credenciales agnósticas al ambiente**
   Un solo `_get_password()` funciona local (dotenv) y en Streamlit Cloud (st.secrets)
   sin necesidad de dos versiones del archivo de conexión.

4. **Timezone en la capa correcta**
   UTC en la base de datos, conversión al timezone del usuario en la query SQL.
   El DataFrame que llega a Python ya está en hora local, sin transformaciones adicionales.

> Respuesta corta para entrevista:
> "Separé queries de UI para que el schema pueda evolucionar sin tocar el layout.
> Usé cache_resource para el engine (pool de conexiones) y cache_data para los
> DataFrames, que es la distinción correcta que Streamlit espera. Los secretos se
> leen de dotenv en local y de st.secrets en producción — un solo código para dos
> ambientes."
