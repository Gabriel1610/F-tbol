import os
import subprocess
import shutil
import time
import stat
import datetime
import sys  # <--- [NUEVO] Necesario para encontrar el Python del venv

# --- CONFIGURACIÓN DEL PROYECTO ---
NOMBRE_ARCHIVO = 'Independiente'  # Nombre del script principal (sin .py)
NOMBRE_ICONO = 'Escudo.ico'       # El ícono de la ventana
ARCHIVO_SSL = 'isrgrootx1.pem'    # El certificado necesario para la BD

# Detectamos la ruta donde está este script
DIRECTORIO_BASE = os.path.dirname(os.path.abspath(__file__))
RUTA_DIST = os.path.join(DIRECTORIO_BASE, 'dist')
RUTA_BUILD = os.path.join(DIRECTORIO_BASE, 'build')
RUTA_SPEC = os.path.join(DIRECTORIO_BASE, f"{NOMBRE_ARCHIVO}.spec")

# Rutas absolutas a los archivos
RUTA_ICONO_ABS = os.path.join(DIRECTORIO_BASE, NOMBRE_ICONO)
RUTA_SSL_ABS = os.path.join(DIRECTORIO_BASE, ARCHIVO_SSL)

def limpiar_pyinstaller():
    """Elimina carpetas y archivos temporales."""
    print("Limpiando archivos temporales anteriores...")

    def on_rm_error(func, path, exc_info):
        os.chmod(path, stat.S_IWRITE)
        try:
            func(path)
        except Exception:
            pass

    if os.path.exists(RUTA_SPEC):
        try: os.remove(RUTA_SPEC)
        except: pass

    if os.path.exists(RUTA_DIST):
        try: shutil.rmtree(RUTA_DIST, onerror=on_rm_error)
        except: pass

    if os.path.exists(RUTA_BUILD):
        try: shutil.rmtree(RUTA_BUILD, onerror=on_rm_error)
        except: pass
            
    time.sleep(1)

def obtener_diferencia_tiempo(momento1, momento2):
    """Calcula la duración del proceso."""
    diferencia = momento2 - momento1
    horas, resto = divmod(diferencia.seconds, 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{horas:02}:{minutos:02}:{segundos:02}"

def ejecutar_pyinstaller():
    """Ejecuta el comando para crear el ejecutable."""
    ruta_script_principal = os.path.join(DIRECTORIO_BASE, f"{NOMBRE_ARCHIVO}.py")
    
    print(f"\nEjecutando PyInstaller sobre: {ruta_script_principal}")
    print("Esto puede tardar unos minutos...\n")

    if not os.path.exists(RUTA_ICONO_ABS):
        print(f"ADVERTENCIA: No se encuentra el ícono {NOMBRE_ICONO}")
    if not os.path.exists(RUTA_SSL_ABS):
        print(f"ERROR CRÍTICO: No se encuentra el certificado {ARCHIVO_SSL}")
        return False

    comando = [
        # --- [CORRECCIÓN CRÍTICA] ---
        # Usamos el python actual (del venv) para llamar al módulo PyInstaller
        # Esto evita el error "FileNotFoundError"
        sys.executable, "-m", "PyInstaller", 
        
        "--noconsole",          
        "--onefile",            
        f"--name={NOMBRE_ARCHIVO}",
        f"--icon={RUTA_ICONO_ABS}",
        
        # --- ARCHIVOS ADJUNTOS (DATA) ---
        f"--add-data={RUTA_SSL_ABS};.",   # Certificado SSL
        f"--add-data={RUTA_ICONO_ABS};.", # Ícono
        
        # --- LA SOLUCIÓN DEFINITIVA ---
        "--collect-all=mysql", 
        "--collect-all=mysql.connector",
        
        # --- IMPORTACIONES OCULTAS ADICIONALES ---
        "--hidden-import=flet",
        "--hidden-import=argon2",
        "--hidden-import=datetime",
        
        ruta_script_principal
    ]

    inicio = datetime.datetime.now()
    print("Inicio de compilación: " + inicio.strftime("%H:%M:%S"))

    # Ejecutamos el comando
    # shell=True a veces ayuda en Windows, pero con sys.executable no suele ser necesario
    resultado = subprocess.run(comando, capture_output=True, text=True)

    fin = datetime.datetime.now()
    duracion = obtener_diferencia_tiempo(inicio, fin)
    
    print(f"Fin de compilación: {fin.strftime('%H:%M:%S')} (Duración: {duracion})")

    if resultado.returncode == 0:
        print(">> El ejecutable se creó correctamente.")
        return True
    else:
        print("\n>> ERROR EN PYINSTALLER:")
        # Mostramos las últimas líneas del error para no saturar la consola
        print(resultado.stderr[-5000:]) 
        return False

def mover_y_limpiar():
    """Mueve el exe a la carpeta raíz y borra carpetas temporales."""
    exe_origen = os.path.join(RUTA_DIST, f"{NOMBRE_ARCHIVO}.exe")
    exe_destino = os.path.join(DIRECTORIO_BASE, f"{NOMBRE_ARCHIVO}.exe")

    if os.path.exists(exe_destino):
        try:
            os.remove(exe_destino)
        except PermissionError:
            print("ERROR: No se pudo borrar el ejecutable anterior. ¡CIERRA EL PROGRAMA SI ESTÁ ABIERTO!")
            return False

    if os.path.exists(exe_origen):
        shutil.move(exe_origen, exe_destino)
        print(f"Ejecutable movido a: {exe_destino}")
        
        time.sleep(1)
        shutil.rmtree(RUTA_DIST, ignore_errors=True)
        shutil.rmtree(RUTA_BUILD, ignore_errors=True)
        if os.path.exists(RUTA_SPEC):
            os.remove(RUTA_SPEC)
        
        print("Archivos temporales eliminados.")
        return True
    else:
        print("No se encontró el archivo en dist/.")
        return False

# --- BLOQUE PRINCIPAL ---
if __name__ == "__main__":
    empezó_el_programa = datetime.datetime.now()
    print(f"--- GENERADOR DE EJECUTABLE CAI: {NOMBRE_ARCHIVO} ---\n")
    
    limpiar_pyinstaller()
    
    if ejecutar_pyinstaller():
        if mover_y_limpiar():
            print("\n" + "="*40)
            print(" ¡PROCESO COMPLETADO CON ÉXITO! :D")
            print("="*40)
        else:
            print("\nHubo un problema moviendo el archivo final.")
    else:
        print("\nNo se pudo generar el ejecutable :(")