"""
Script de verificacion de credenciales de Spotify.

Ejecutar una sola vez para confirmar que el CLIENT_ID, CLIENT_SECRET
y REDIRECT_URI estan bien configurados y que el token OAuth funciona.

La primera vez abre el navegador para que autorices la app.
Despues guarda el token en .cache y no vuelve a pedir autorizacion.

Uso:
    python scripts/test_spotify_auth.py
"""

import sys
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
import os

load_dotenv()

def main():
    print("Iniciando verificacion de credenciales de Spotify...")
    print()

    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")

    if not all([client_id, client_secret, redirect_uri]):
        print("ERROR: Faltan variables en .env")
        print(f"  SPOTIFY_CLIENT_ID:     {'OK' if client_id else 'FALTA'}")
        print(f"  SPOTIFY_CLIENT_SECRET: {'OK' if client_secret else 'FALTA'}")
        print(f"  SPOTIFY_REDIRECT_URI:  {'OK' if redirect_uri else 'FALTA'}")
        sys.exit(1)

    print(f"  CLIENT_ID:    {client_id[:8]}...{client_id[-4:]}")
    print(f"  REDIRECT_URI: {redirect_uri}")
    print()
    print("Abriendo navegador para autorizar la app...")
    print("(Si ya autorizaste antes, esto es instantaneo)")
    print()

    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope="user-read-recently-played",
        cache_path=".cache",
    ))

    # Llamada minima para verificar que el token funciona
    user = sp.current_user()
    print(f"Autenticado como: {user['display_name']} ({user['id']})")
    print()

    # Traer 1 track reciente para confirmar el scope
    recent = sp.current_user_recently_played(limit=1)
    items = recent.get("items", [])

    if items:
        track = items[0]["track"]
        played_at = items[0]["played_at"]
        print(f"Ultimo track reproducido:")
        print(f"  {track['name']} - {track['artists'][0]['name']}")
        print(f"  Reproducido: {played_at}")
    else:
        print("No se encontraron tracks recientes (esto es normal si no has escuchado nada).")

    print()
    print("Credenciales verificadas correctamente.")
    print("El token quedo guardado en .cache para proximas ejecuciones.")

if __name__ == "__main__":
    main()
