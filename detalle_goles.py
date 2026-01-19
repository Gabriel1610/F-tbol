import requests
import json
from datetime import datetime

# --- CONFIGURACIÓN ---
ID_INDEPENDIENTE = 10078
ID_LIGA_PROFESIONAL = 10128
ID_COPA_LIGA = 10315

# URLs
URL_API_TEAMS = "https://www.fotmob.com/api/teams"
URL_API_LEAGUES = "https://www.fotmob.com/api/leagues"
URL_API_DETALLE = "https://www.fotmob.com/api/matchDetails"

# HEADERS (Copiados de tu Independiente.py que funciona bien)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

def buscar_partidos_historicos():
    """
    Busca partidos retrocediendo desde 2025 hasta 2023.
    Maneja errores de API vacía (None) para no romperse.
    """
    print("🔍 Iniciando búsqueda de historial...")
    
    todos_los_partidos = []
    
    # 1. Intentamos primero con la API de Equipos (Por si trae historial reciente)
    try:
        resp = requests.get(URL_API_TEAMS, headers=HEADERS, params={"id": ID_INDEPENDIENTE, "ccode3": "ARG"}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data:
                fixtures = data.get("fixtures") or {}
                # Buscamos en todas las listas posibles
                fuentes = [
                    fixtures.get("results", []),
                    fixtures.get("fixtures", []),
                    fixtures.get("allFixtures", [])
                ]
                # A veces allFixtures es dict
                if isinstance(fixtures.get("allFixtures"), dict):
                    for v in fixtures.get("allFixtures").values():
                        if isinstance(v, list): fuentes.append(v)

                for lista in fuentes:
                    if not lista: continue
                    for m in lista:
                        if isinstance(m, dict) and m.get("status", {}).get("finished"):
                            # Verificar que sea de Independiente (ID 10078)
                            if m.get("home", {}).get("id") == ID_INDEPENDIENTE or m.get("away", {}).get("id") == ID_INDEPENDIENTE:
                                todos_los_partidos.append(m)
    except Exception as e:
        print(f"   [!] Error en carga standard: {e}")

    # 2. Si no encontramos suficientes (menos de 5), buscamos en LIGAS ESPECÍFICAS (2025, 2024)
    if len(todos_los_partidos) < 5:
        anios_a_buscar = ["2025", "2024", "2023"]
        torneos = [
            (ID_LIGA_PROFESIONAL, "Liga Profesional"), 
            (ID_COPA_LIGA, "Copa de la Liga")
        ]
        
        for anio in anios_a_buscar:
            if len(todos_los_partidos) >= 5: break
            print(f"   -> Buscando en temporada {anio}...")
            
            for id_liga, nombre_torneo in torneos:
                try:
                    params = {
                        "id": id_liga, 
                        "season": anio, 
                        "ccode3": "ARG", # Importante para evitar null
                        "timezone": "America/Argentina/Buenos_Aires"
                    }
                    resp = requests.get(URL_API_LEAGUES, headers=HEADERS, params=params, timeout=10)
                    
                    if resp.status_code != 200: continue
                    
                    data = resp.json()
                    
                    # --- CORRECCIÓN CRÍTICA: SI DATA ES NONE, SALTAR ---
                    if not data: 
                        # print(f"      (API vacía para {nombre_torneo} {anio})")
                        continue
                        
                    matches_obj = data.get("matches") or {}
                    all_matches = matches_obj.get("allMatches") or []
                    
                    for m in all_matches:
                        if not isinstance(m, dict): continue
                        
                        # Filtro ID Independiente
                        try:
                            hid = int(m.get("home", {}).get("id") or 0)
                            aid = int(m.get("away", {}).get("id") or 0)
                        except: continue
                        
                        if hid == ID_INDEPENDIENTE or aid == ID_INDEPENDIENTE:
                            if m.get("status", {}).get("finished"):
                                # Evitar duplicados
                                if not any(p['id'] == m['id'] for p in todos_los_partidos):
                                    m['torneo_nombre'] = f"{nombre_torneo} {anio}"
                                    todos_los_partidos.append(m)
                                    
                except Exception as e:
                    print(f"      Error leyendo {nombre_torneo} {anio}: {e}")
                    continue

    # Ordenar por fecha (UTC time string) descendente
    todos_los_partidos.sort(key=lambda x: x.get("status", {}).get("utcTime", ""), reverse=True)
    return todos_los_partidos

def obtener_detalle_goles(match_id):
    """Consulta el endpoint de detalle para sacar minuto y autor."""
    try:
        resp = requests.get(URL_API_DETALLE, headers=HEADERS, params={"matchId": match_id}, timeout=10)
        if resp.status_code != 200: return

        data = resp.json()
        if not data: return # Validación anti-crash

        content = data.get("content") or {}
        match_facts = content.get("matchFacts") or {}
        events_obj = match_facts.get("events") or {}
        
        if isinstance(events_obj, list): events = events_obj
        else: events = events_obj.get("events", [])

        hubo_goles = False
        for ev in events:
            if not isinstance(ev, dict): continue
            
            tipo = ev.get("type")
            if tipo in ["Goal", "PenaltyGoal", "OwnGoal"]:
                hubo_goles = True
                minuto = ev.get("time", 0)
                
                # Nombre jugador seguro
                p_obj = ev.get("player") or {}
                if isinstance(p_obj, dict): jugador = p_obj.get("name", "Desconocido")
                else: jugador = "Desconocido"
                
                # Equipo
                es_local = ev.get("isHome", False)
                tag = "(L)" if es_local else "(V)"
                
                # Extra
                extra = ""
                if tipo == "PenaltyGoal": extra = " (Penal)"
                if tipo == "OwnGoal": extra = " (En contra)"
                
                print(f"      ⚽ {minuto}' {jugador}{extra} {tag}")
        
        if not hubo_goles:
            print("      (0-0)")

    except Exception as e:
        print(f"      [Error recuperando goles: {e}]")

def main():
    partidos = buscar_partidos_historicos()
    
    if not partidos:
        print("\n❌ No se encontraron partidos tras escanear 2023-2026.")
        return

    # Tomar los últimos 5
    ultimos_5 = partidos[:5]
    
    print(f"\n✅ Se encontraron {len(partidos)} partidos.")
    print(f"📊 Detalle de los últimos {len(ultimos_5)} partidos:\n")
    
    for match in ultimos_5:
        match_id = match.get('id')
        if not match_id: continue
        
        # Datos visuales
        torneo = match.get("torneo_nombre")
        if not torneo:
            torneo = match.get("league", {}).get("name", "Torneo")
            
        home = match.get("home", {}).get("name", "Local")
        away = match.get("away", {}).get("name", "Visita")
        score = match.get("status", {}).get("scoreStr", "-")
        
        # Fecha simple
        fecha_raw = match.get("status", {}).get("utcTime", "")
        fecha_str = fecha_raw.split("T")[0] if "T" in fecha_raw else fecha_raw

        print(f"📅 {fecha_str} | {home} vs {away} ({score})")
        print(f"   🏆 {torneo}")
        
        obtener_detalle_goles(match_id)
        print("-" * 50)

if __name__ == "__main__":
    main()