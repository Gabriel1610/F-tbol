import os
import subprocess
import shutil
import time
import stat
import datetime

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
    """Elimina carpetas y archivos temporales con manejo de errores de permisos."""
    print("Limpiando archivos temporales anteriores...")

    def on_rm_error(func, path, exc_info):
        os.chmod(path, stat.S_IWRITE)
        try:
            func(path)
        except Exception:
            pass

    # Borrar archivo .spec
    if os.path.exists(RUTA_SPEC):
        try:
            os.remove(RUTA_SPEC)
        except PermissionError:
            print(f"Advertencia: No se pudo borrar {RUTA_SPEC} (está en uso).")

    # Borrar carpeta dist
    if os.path.exists(RUTA_DIST):
        try:
            shutil.rmtree(RUTA_DIST, onerror=on_rm_error)
        except Exception as e:
            print(f"Advertencia: No se pudo eliminar la carpeta 'dist'. Razón: {e}")
            print(f">> Asegúrate de cerrar '{NOMBRE_ARCHIVO}.exe' antes de compilar.")

    # Borrar carpeta build
    if os.path.exists(RUTA_BUILD):
        try:
            shutil.rmtree(RUTA_BUILD, onerror=on_rm_error)
        except Exception:
            pass
            
    time.sleep(1)

def obtener_diferencia_tiempo(momento1, momento2):
    """Calcula la duración del proceso."""
    if momento1 > momento2:
        diferencia = momento1 - momento2
    else:
        diferencia = momento2 - momento1
    
    horas, resto = divmod(diferencia.seconds, 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{horas:02}:{minutos:02}:{segundos:02}"

def ejecutar_pyinstaller():
    """Ejecuta el comando para crear el ejecutable."""
    ruta_script_principal = os.path.join(DIRECTORIO_BASE, f"{NOMBRE_ARCHIVO}.py")
    
    print(f"\nEjecutando PyInstaller sobre: {ruta_script_principal}")
    print("Esto puede tardar unos minutos...\n")

    # Comprobación de archivos necesarios
    if not os.path.exists(RUTA_ICONO_ABS):
        print(f"ADVERTENCIA: No se encuentra el ícono {NOMBRE_ICONO}")
    if not os.path.exists(RUTA_SSL_ABS):
        print(f"ERROR CRÍTICO: No se encuentra el certificado {ARCHIVO_SSL}")
        return False

    comando = [
        "pyinstaller", 
        "--noconsole",          # Sin consola negra de fondo
        "--onefile",            # Todo en un solo archivo .exe
        f"--name={NOMBRE_ARCHIVO}",
        f"--icon={RUTA_ICONO_ABS}",
        
        # --- ARCHIVOS ADJUNTOS (DATA) ---
        # Sintaxis Windows: "origen;destino"
        # El destino "." significa la raíz temporal donde corre el exe
        f"--add-data={RUTA_SSL_ABS};.",   # Incluir Certificado SSL
        f"--add-data={RUTA_ICONO_ABS};.", # Incluir Ícono como recurso
        
        # --- IMPORTACIONES OCULTAS ---
        # Flet y Argon2 a veces no son detectados automáticamente
        "--hidden-import=flet",
        "--hidden-import=mysql.connector",
        "--hidden-import=argon2",
        "--hidden-import=datetime",
        
        ruta_script_principal
    ]

    inicio = datetime.datetime.now()
    print("Inicio de compilación: " + inicio.strftime("%H:%M:%S"))

    # Ejecutamos el comando
    resultado = subprocess.run(comando, capture_output=True, text=True)

    fin = datetime.datetime.now()
    duracion = obtener_diferencia_tiempo(fin, inicio)
    
    print(f"Fin de compilación: {fin.strftime('%H:%M:%S')} (Duración: {duracion})")

    if resultado.returncode == 0:
        print(">> El ejecutable se creó correctamente.")
        return True
    else:
        print("\n>> ERROR EN PYINSTALLER:")
        # Mostramos solo las últimas lineas del error para no saturar
        print(resultado.stderr[-2000:]) 
        return False

def mover_y_limpiar():
    """Mueve el exe a la carpeta raíz y borra carpetas temporales."""
    exe_origen = os.path.join(RUTA_DIST, f"{NOMBRE_ARCHIVO}.exe")
    exe_destino = os.path.join(DIRECTORIO_BASE, f"{NOMBRE_ARCHIVO}.exe")

    # Si existe un exe viejo, lo borramos
    if os.path.exists(exe_destino):
        try:
            os.remove(exe_destino)
        except PermissionError:
            print("ERROR: No se pudo borrar el ejecutable anterior. ¿Está abierto?")
            return False

    if os.path.exists(exe_origen):
        shutil.move(exe_origen, exe_destino)
        print(f"Ejecutable movido a: {exe_destino}")
        
        time.sleep(1)
        
        # Limpiar carpetas generadas
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
    print(f"--- GENERADOR DE EJECUTABLE CAI: {NOMBRE_ARCHIVO} ---")
    
    limpiar_pyinstaller()
    
    exito_compilacion = ejecutar_pyinstaller()
    
    if exito_compilacion:
        if mover_y_limpiar():
            print("\n" + "="*40)
            print(" ¡PROCESO COMPLETADO CON ÉXITO! :D")
            print("="*40)
        else:
            print("\nHubo un problema moviendo el archivo final.")
    else:
        print("\nNo se pudo generar el ejecutable :(")

    tiempo_total = obtener_diferencia_tiempo(datetime.datetime.now(), empezó_el_programa)
    print(f"\nTiempo total de ejecución: {tiempo_total}")