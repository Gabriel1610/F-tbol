import mysql.connector
import logging
from datetime import datetime, timedelta
import sys
import os # IMPORTANTE: Para encontrar el certificado
from mysql.connector import errorcode
# Importamos Argon2 para el hashing moderno
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

PUNTOS = 3
MÁXIMA_CANTIDAD_DE_PUNTOS = 9
MAYOR_ENTERO = 999999999

# Configuración del Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseDeDatos:
    def __init__(self):
        self.ph = PasswordHasher()

        # --- SOLUCIÓN DEL ERROR EN EL EXE ---
        # Detectamos si estamos corriendo en el ejecutable (frozen) o en el script normal
        if getattr(sys, 'frozen', False):
            # Si es EXE, PyInstaller guarda los archivos en sys._MEIPASS
            carpeta_actual = sys._MEIPASS
        else:
            # Si es script .py, usamos la ruta normal
            carpeta_actual = os.path.dirname(os.path.abspath(__file__))
            
        ruta_certificado = os.path.join(carpeta_actual, "isrgrootx1.pem")
        
        if not os.path.exists(ruta_certificado):
            logger.error(f"NO SE ENCUENTRA EL CERTIFICADO EN: {ruta_certificado}")

        self.config = {
            'user': '3XY8PLHt12tsDbZ.root',       
            'password': 'mXv9F5VQGmRiYYZH', 
            'host': 'gateway01.us-east-1.prod.aws.tidbcloud.com', 
            'port': 4000,                         
            'database': 'independiente',          
            'raise_on_warnings': True,
            'ssl_ca': ruta_certificado,           
            'ssl_verify_cert': True,
            'use_pure': True
        }

    def abrir(self):
        """Abre la conexión a la base de datos de forma segura."""
        try:
            conexion = mysql.connector.connect(**self.config)
            return conexion
        except mysql.connector.Error as err:
            # --- MODIFICACIÓN: Mostrar el error técnico completo en el EXE ---
            msg = str(err)
            if "SSL" in msg:
                # Intenta mostrar dónde está buscando el certificado para depurar
                raise Exception(f"Error SSL: {msg}\nRuta buscada: {self.config.get('ssl_ca')}")
            else:
                raise Exception(f"Error de Conexión: {msg}")

    def obtener_rivales_completo(self):
        """
        Obtiene ID, Nombre y Otro Nombre de todos los rivales.
        Usado para la tabla de administración.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            sql = "SELECT id, nombre, otro_nombre FROM rivales ORDER BY nombre ASC"
            cursor.execute(sql)
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error obteniendo rivales completo: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
    
    def actualizar_rival(self, id_rival, nuevo_nombre, nuevo_otro_nombre):
        """
        Actualiza el nombre y el nombre alternativo de un rival.
        Maneja la conversión de cadena vacía a NULL para la base de datos.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            # Si el string está vacío, guardamos NULL (None en Python)
            val_otro = nuevo_otro_nombre if nuevo_otro_nombre and nuevo_otro_nombre.strip() else None
            
            sql = "UPDATE rivales SET nombre = %s, otro_nombre = %s WHERE id = %s"
            cursor.execute(sql, (nuevo_nombre, val_otro, id_rival))
            conexion.commit()
            return True
        except mysql.connector.IntegrityError as e:
            if e.errno == 1062:
                raise Exception("Ya existe un equipo con ese nombre u otro nombre.")
            raise e
        except Exception as e:
            logger.error(f"Error actualizando rival: {e}")
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    # --- REEMPLAZAR ESTA FUNCIÓN ---
    def insertar_usuario(self, username, password, email):
        """
        Inserta usuario con email. 
        Se asume que la validación del código ya se hizo en el frontend antes de llamar a esto.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            password_hash = self.ph.hash(password)
            fecha_actual = datetime.now()

            # AHORA INCLUIMOS EL EMAIL
            sql = "INSERT INTO usuarios (username, password, email, fecha_registro) VALUES (%s, %s, %s, %s)"
            valores = (username, password_hash, email, fecha_actual)

            cursor.execute(sql, valores)
            conexion.commit()
            
            logger.info(f"Usuario '{username}' registrado exitosamente.")
            return True

        except mysql.connector.IntegrityError as err:
            if err.errno == 1062: 
                raise Exception("El nombre de usuario o el correo ya están registrados.")
            else:
                raise Exception(f"Error de integridad: {err}")
        except Exception as e:
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    # --- AGREGAR ESTAS FUNCIONES NUEVAS AL FINAL DE LA CLASE ---

    def verificar_disponibilidad(self, username, email):
        """Verifica si el usuario o el email ya existen antes de enviar el código."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            sql = "SELECT username, email FROM usuarios WHERE username = %s OR email = %s"
            cursor.execute(sql, (username, email))
            resultado = cursor.fetchone()
            
            if resultado:
                # Si encontró algo, devolvemos qué fue lo que encontró para dar un error preciso
                encontrado_user = resultado[0]
                encontrado_email = resultado[1]
                if encontrado_user == username:
                    raise Exception("El nombre de usuario ya está en uso.")
                if encontrado_email == email:
                    raise Exception("El correo electrónico ya está registrado.")
            return True # Está disponible
            
        except Exception as e:
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_email_usuario(self, username):
        """Obtiene el email de un usuario para la recuperación."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            sql = "SELECT email FROM usuarios WHERE username = %s"
            cursor.execute(sql, (username,))
            res = cursor.fetchone()
            if res:
                return res[0]
            return None
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def guardar_token_recuperacion(self, username, token):
        """Guarda el código de recuperación en la BD con 15 min de validez."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            # Calculamos expiración (Ahora + 15 minutos)
            expiracion = datetime.now() + timedelta(minutes=15)
            
            sql = "UPDATE usuarios SET token_recuperacion = %s, token_expiracion = %s WHERE username = %s"
            cursor.execute(sql, (token, expiracion, username))
            conexion.commit()
            return True
        except Exception as e:
            logger.error(f"Error guardando token: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def validar_token_recuperacion(self, username, token):
        """Verifica si el token coincide y no ha expirado."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            sql = "SELECT token_expiracion FROM usuarios WHERE username = %s AND token_recuperacion = %s"
            cursor.execute(sql, (username, token))
            res = cursor.fetchone()
            
            if res:
                expiracion = res[0]
                if expiracion and expiracion > datetime.now():
                    return True # Válido
                else:
                    raise Exception("El código ha expirado.")
            else:
                raise Exception("Código incorrecto.")
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def cambiar_contrasena(self, username, nueva_password):
        """Actualiza la contraseña y limpia el token."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            password_hash = self.ph.hash(nueva_password)
            
            # Actualizamos pass y borramos el token usado
            sql = "UPDATE usuarios SET password = %s, token_recuperacion = NULL, token_expiracion = NULL WHERE username = %s"
            cursor.execute(sql, (password_hash, username))
            conexion.commit()
            return True
        except Exception as e:
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_rivales(self):
        """
        Obtiene la lista de todos los rivales (ID, Nombre) ordenados alfabéticamente.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            sql = "SELECT id, nombre FROM rivales ORDER BY nombre ASC"
            cursor.execute(sql)
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error obteniendo rivales: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def insertar_pronostico(self, username, partido_id, pred_cai, pred_rival):
        """
        Inserta un nuevo pronóstico enviando explícitamente la fecha y hora 
        del sistema local donde se ejecuta el programa.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            # 1. Obtener ID del Usuario a partir del username
            cursor.execute("SELECT id FROM usuarios WHERE username = %s", (username,))
            res_user = cursor.fetchone()
            if not res_user:
                raise Exception("Usuario no encontrado.")
            usuario_id = res_user[0]
            
            # 2. Capturar fecha y hora del sistema actual
            fecha_local = datetime.now()
            
            # 3. Insertar el pronóstico pasando la fecha local explícitamente
            sql = """
                INSERT INTO pronosticos (usuario_id, partido_id, pred_goles_independiente, pred_goles_rival, fecha_prediccion)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (usuario_id, partido_id, pred_cai, pred_rival, fecha_local))
            conexion.commit()
            return True

        except Exception as e:
            logger.error(f"Error insertando pronóstico: {e}")
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
    
    def actualizar_resultados_pendientes(self, lista_jugados):
        """
        Regla Pasado: Solo actualiza resultados si el partido YA existe en la BD
        y tiene los goles en NULL. NO crea partidos nuevos ni rivales nuevos.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            count = 0
            for datos in lista_jugados:
                # 1. Buscamos el Rival (Solo lectura, no creamos si no existe)
                cursor.execute("SELECT id FROM rivales WHERE nombre = %s OR otro_nombre = %s LIMIT 1", (datos['rival'], datos['rival']))
                res_rival = cursor.fetchone()
                if not res_rival: continue # Si no conocemos al rival, el partido no existe en nuestra BD. Saltamos.
                rival_id = res_rival[0]

                # 2. Buscamos la Edición (Solo lectura)
                cursor.execute("SELECT id FROM campeonatos WHERE nombre = %s", (datos['torneo'],))
                res_camp = cursor.fetchone()
                if not res_camp: continue
                
                # Manejo simple de año string
                anio_str = str(datos['anio']).split("-")[0]
                cursor.execute("SELECT id FROM anios WHERE numero = %s", (anio_str,))
                res_anio = cursor.fetchone()
                if not res_anio: continue

                cursor.execute("SELECT id FROM ediciones WHERE campeonato_id = %s AND anio_id = %s", (res_camp[0], res_anio[0]))
                res_edicion = cursor.fetchone()
                if not res_edicion: continue
                edicion_id = res_edicion[0]

                # 3. Intentamos ACTUALIZAR solo si los goles están vacíos (NULL)
                # La fecha también se actualiza por si hubo corrección horaria post-partido
                if datos['goles_cai'] is not None:
                    sql = """
                        UPDATE partidos 
                        SET goles_independiente = %s, goles_rival = %s, fecha_hora = %s
                        WHERE rival_id = %s AND edicion_id = %s AND goles_independiente IS NULL
                    """
                    cursor.execute(sql, (datos['goles_cai'], datos['goles_rival'], datos['fecha'], rival_id, edicion_id))
                    if cursor.rowcount > 0:
                        count += 1

            conexion.commit()
            return count > 0

        except Exception as e:
            logger.error(f"Error actualizando pendientes: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def sincronizar_proximos_partidos(self, lista_futuros):
        """
        Regla Futuro (Próximos 5):
        - Si existe: Actualiza fecha y hora.
        - Si no existe: Lo agrega (creando rival/torneo si hace falta).
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            cambios = False
            for datos in lista_futuros:
                rival_nombre = datos['rival']
                torneo_nombre = datos['torneo']
                anio_numero = str(datos['anio']).split("-")[0]
                fecha_hora = datos['fecha']

                # --- A. GESTIÓN DE RIVAL (Buscar o Crear) ---
                cursor.execute("SELECT id FROM rivales WHERE nombre = %s OR otro_nombre = %s LIMIT 1", (rival_nombre, rival_nombre))
                res_rival = cursor.fetchone()
                if res_rival:
                    rival_id = res_rival[0]
                else:
                    cursor.execute("INSERT INTO rivales (nombre) VALUES (%s)", (rival_nombre,))
                    rival_id = cursor.lastrowid

                # --- B. GESTIÓN DE TORNEO/AÑO (Buscar o Crear) ---
                cursor.execute("SELECT id FROM campeonatos WHERE nombre = %s", (torneo_nombre,))
                res_camp = cursor.fetchone()
                if res_camp: camp_id = res_camp[0]
                else:
                    cursor.execute("INSERT INTO campeonatos (nombre) VALUES (%s)", (torneo_nombre,))
                    camp_id = cursor.lastrowid

                cursor.execute("SELECT id FROM anios WHERE numero = %s", (anio_numero,))
                res_anio = cursor.fetchone()
                if res_anio: anio_id = res_anio[0]
                else:
                    cursor.execute("INSERT INTO anios (numero) VALUES (%s)", (anio_numero,))
                    anio_id = cursor.lastrowid

                cursor.execute("SELECT id FROM ediciones WHERE campeonato_id = %s AND anio_id = %s", (camp_id, anio_id))
                res_ed = cursor.fetchone()
                if res_ed: edicion_id = res_ed[0]
                else:
                    cursor.execute("INSERT INTO ediciones (campeonato_id, anio_id, finalizado) VALUES (%s, %s, FALSE)", (camp_id, anio_id))
                    edicion_id = cursor.lastrowid

                # --- C. GESTIÓN DEL PARTIDO (Upsert Lógico) ---
                cursor.execute("SELECT id FROM partidos WHERE rival_id = %s AND edicion_id = %s", (rival_id, edicion_id))
                res_partido = cursor.fetchone()

                if res_partido:
                    # SI EXISTE: Solo actualizamos la fecha/hora
                    partido_id = res_partido[0]
                    cursor.execute("UPDATE partidos SET fecha_hora = %s WHERE id = %s", (fecha_hora, partido_id))
                    if cursor.rowcount > 0: cambios = True
                else:
                    # SI NO EXISTE: Lo insertamos (Goles en NULL por defecto)
                    cursor.execute("INSERT INTO partidos (rival_id, edicion_id, fecha_hora) VALUES (%s, %s, %s)", (rival_id, edicion_id, fecha_hora))
                    cambios = True

            conexion.commit()
            return cambios

        except Exception as e:
            logger.error(f"Error sincronizando futuros: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_partidos(self, usuario, filtro_tiempo='futuros', edicion_id=None, rival_id=None, solo_sin_pronosticar=False):
        """
        Obtiene la lista de partidos aplicando filtros acumulativos.
        - filtro_tiempo: 'todos', 'futuros', 'jugados'
        - edicion_id: ID del torneo (opcional)
        - rival_id: ID del equipo (opcional)
        - solo_sin_pronosticar: Booleano
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            # Parametros base para las subconsultas de usuario
            params = [usuario, usuario]
            
            # Lista de condiciones WHERE. Arrancamos con 1=1 para concatenar con AND
            condiciones = ["1=1"]

            # 1. Filtro de Tiempo (Excluyente entre sí)
            if filtro_tiempo == 'futuros':
                condiciones.append("p.fecha_hora > DATE_SUB(NOW(), INTERVAL 3 HOUR)")
                orden_sql = "ASC"
            elif filtro_tiempo == 'jugados':
                condiciones.append("p.fecha_hora <= DATE_SUB(NOW(), INTERVAL 3 HOUR)")
                orden_sql = "DESC"
            else: # 'todos'
                orden_sql = "ASC" if filtro_tiempo == 'futuros' else "DESC"

            # 2. Filtro Torneo (Acumulativo)
            if edicion_id is not None:
                condiciones.append("p.edicion_id = %s")
                params.append(edicion_id)

            # 3. Filtro Equipo (Acumulativo)
            if rival_id is not None:
                condiciones.append("p.rival_id = %s")
                params.append(rival_id)

            # 4. Filtro Sin Pronosticar (Acumulativo)
            if solo_sin_pronosticar:
                condiciones.append("p.fecha_hora > DATE_SUB(NOW(), INTERVAL 3 HOUR)") # Redundancia de seguridad
                condiciones.append("pr.pred_goles_independiente IS NULL")

            # Unir condiciones
            where_clause = " WHERE " + " AND ".join(condiciones)

            sql = f"""
            SELECT 
                p.id,
                r.nombre,
                p.fecha_hora,
                CONCAT(c.nombre, ' ', a.numero) as torneo_completo,
                p.goles_independiente,
                p.goles_rival,
                p.edicion_id,
                CASE 
                    WHEN TIME(p.fecha_hora) = '00:00:00' THEN DATE_FORMAT(p.fecha_hora, '%d/%m/%Y s. h.')
                    ELSE DATE_FORMAT(p.fecha_hora, '%d/%m/%Y %H:%i')
                END as fecha_display,
                pr.pred_goles_independiente, 
                pr.pred_goles_rival,
                -- PUNTOS
                CASE 
                    WHEN p.goles_independiente IS NULL THEN NULL 
                    WHEN pr.pred_goles_independiente IS NULL THEN 0 
                    ELSE
                        (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN SIGN(p.goles_independiente - p.goles_rival) = SIGN(pr.pred_goles_independiente - pr.pred_goles_rival) THEN {PUNTOS} ELSE 0 END)
                END as tus_puntos,
                
                -- ERROR ABSOLUTO
                CASE 
                    WHEN p.goles_independiente IS NULL OR pr.pred_goles_independiente IS NULL THEN NULL
                    ELSE
                        ABS(CAST(p.goles_independiente AS SIGNED) - CAST(pr.pred_goles_independiente AS SIGNED)) + 
                        ABS(CAST(p.goles_rival AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED))
                END as error_absoluto

            FROM partidos p
            JOIN rivales r ON p.rival_id = r.id
            JOIN ediciones e ON p.edicion_id = e.id
            JOIN campeonatos c ON e.campeonato_id = c.id
            JOIN anios a ON e.anio_id = a.id
            LEFT JOIN (
                SELECT 
                    p1.partido_id, 
                    p1.pred_goles_independiente, 
                    p1.pred_goles_rival
                FROM pronosticos p1
                INNER JOIN (
                    SELECT partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    WHERE usuario_id = (SELECT id FROM usuarios WHERE username = %s)
                    GROUP BY partido_id
                ) p2 ON p1.partido_id = p2.partido_id AND p1.fecha_prediccion = p2.max_fecha
                WHERE p1.usuario_id = (SELECT id FROM usuarios WHERE username = %s)
            ) pr ON p.id = pr.partido_id
            
            {where_clause}
            ORDER BY p.fecha_hora {orden_sql}
            """
            
            cursor.execute(sql, tuple(params))
            resultados = cursor.fetchall()
            return resultados

        except Exception as e:
            logger.error(f"Error obteniendo partidos: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close() 

    def obtener_datos_evolucion_puestos(self, edicion_id, usuarios_seleccionados):
        """
        Calcula la evolución del ranking aplicando los nuevos criterios:
        1. Puntos (Mayor).
        2. Partidos Pronosticados (Mayor).
        3. Anticipación (Mayor).
        4. Promedio de intentos (Menor).
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            # 1. Contar total de usuarios
            cursor.execute("SELECT COUNT(*) FROM usuarios")
            total_usuarios = cursor.fetchone()[0]

            # 2. Obtener partidos JUGADOS ordenados por fecha
            sql_partidos = """
                SELECT id 
                FROM partidos 
                WHERE edicion_id = %s AND goles_independiente IS NOT NULL 
                ORDER BY fecha_hora ASC
            """
            cursor.execute(sql_partidos, (edicion_id,))
            partidos = [row[0] for row in cursor.fetchall()]

            if not partidos:
                return 0, total_usuarios, {}

            # 3. Obtener usuarios y estructuras
            cursor.execute("SELECT id, username FROM usuarios")
            usuarios_bd = cursor.fetchall()
            
            ids_usuarios = [u[0] for u in usuarios_bd]
            mapa_nombres = {u[0]: u[1] for u in usuarios_bd}
            
            # Acumuladores
            puntos_acumulados = {uid: 0 for uid in ids_usuarios} 
            suma_anticipacion = {uid: 0 for uid in ids_usuarios}
            cant_partidos_jugados = {uid: 0 for uid in ids_usuarios} # Criterio 2
            total_intentos_acumulados = {uid: 0 for uid in ids_usuarios} # Criterio 4
            
            historial_grafico = {user: [] for user in usuarios_seleccionados}

            # 4. Iterar partido a partido
            for partido_id in partidos:
                # Consulta para obtener: Puntos, Anticipación y Cantidad de Intentos en ESTE partido
                sql_datos_partido = f"""
                    SELECT 
                        pr.usuario_id,
                        -- Puntos (usando último pronóstico)
                        (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN SIGN(p.goles_independiente - p.goles_rival) = SIGN(pr.pred_goles_independiente - pr.pred_goles_rival) THEN {PUNTOS} ELSE 0 END) as puntos,
                        -- Anticipación (usando último pronóstico)
                        TIMESTAMPDIFF(SECOND, pr.fecha_prediccion, p.fecha_hora) as segundos_anticipacion,
                        -- Conteo de intentos totales para este partido
                        (SELECT COUNT(*) FROM pronosticos WHERE usuario_id = pr.usuario_id AND partido_id = %s) as intentos_match
                    FROM pronosticos pr
                    JOIN (
                        SELECT usuario_id, MAX(fecha_prediccion) as max_fecha
                        FROM pronosticos
                        WHERE partido_id = %s
                        GROUP BY usuario_id
                    ) last_pred ON pr.usuario_id = last_pred.usuario_id 
                        AND pr.fecha_prediccion = last_pred.max_fecha
                    JOIN partidos p ON pr.partido_id = p.id
                    WHERE p.id = %s AND pr.partido_id = %s
                """
                cursor.execute(sql_datos_partido, (partido_id, partido_id, partido_id, partido_id))
                resultados = cursor.fetchall()

                # Actualizar acumulados
                for uid, pts, segs, intentos in resultados:
                    if uid in puntos_acumulados:
                        puntos_acumulados[uid] += pts
                        val_sec = segs if segs is not None else 0
                        suma_anticipacion[uid] += val_sec
                        cant_partidos_jugados[uid] += 1
                        total_intentos_acumulados[uid] += intentos

                # --- CÁLCULO DE RANKING DEL MOMENTO ---
                def get_sort_key(uid):
                    pts = puntos_acumulados[uid]
                    partidos_jug = cant_partidos_jugados[uid]
                    
                    if partidos_jug > 0:
                        # Promedio de anticipación
                        avg_ant = suma_anticipacion[uid] / partidos_jug
                        # Promedio de intentos (Queremos MENOR es mejor)
                        # Usamos negativo para que al ordenar reverse=True (DESC), el valor -1.0 gane a -2.0
                        avg_intentos = -(total_intentos_acumulados[uid] / partidos_jug)
                    else:
                        avg_ant = 0
                        # Si no jugó, pierde en criterio 2, el 4 ya no importa tanto, ponemos algo neutro
                        avg_intentos = 0

                    # Tupla de Ordenamiento:
                    # 1. Puntos (Max)
                    # 2. Partidos Jugados (Max) -> "Más participó gana"
                    # 3. Anticipación (Max)
                    # 4. Promedio Intentos (Max Negativo -> Menor promedio real)
                    return (pts, partidos_jug, avg_ant, avg_intentos)

                # Ordenar
                ranking_ordenado = sorted(ids_usuarios, key=get_sort_key, reverse=True)
                
                # Asignar puestos
                mapa_puestos = {}
                prev_key = None
                puesto_actual = 0
                
                for i, uid in enumerate(ranking_ordenado):
                    current_key = get_sort_key(uid)
                    if current_key != prev_key:
                        puesto_actual = i + 1
                        prev_key = current_key
                    mapa_puestos[uid] = puesto_actual

                # Guardar en historial
                for usuario_target in usuarios_seleccionados:
                    target_id = next((k for k, v in mapa_nombres.items() if v == usuario_target), None)
                    if target_id:
                        puesto = mapa_puestos.get(target_id, total_usuarios)
                        historial_grafico[usuario_target].append(puesto)

            return len(partidos), total_usuarios, historial_grafico

        except Exception as e:
            logger.error(f"Error evolución: {e}")
            return 0, 0, {}
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_datos_evolucion_puntos(self, edicion_id, usuarios_seleccionados):
        """
        Calcula la evolución de PUNTOS acumulados partido a partido.
        Retorna: 
            - cantidad_partidos (int)
            - historial (dict): {usuario: [puntos_acum_fecha_1, puntos_acum_fecha_2...]}
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            # 1. Obtener partidos JUGADOS de la edición ordenados por fecha
            sql_partidos = """
                SELECT id 
                FROM partidos 
                WHERE edicion_id = %s AND goles_independiente IS NOT NULL 
                ORDER BY fecha_hora ASC
            """
            cursor.execute(sql_partidos, (edicion_id,))
            partidos = [row[0] for row in cursor.fetchall()]

            if not partidos:
                return 0, {}

            if not usuarios_seleccionados:
                return len(partidos), {}

            # 2. Obtener IDs de usuarios seleccionados
            # Creamos una cadena de placeholders '%s' según la cantidad de usuarios
            placeholders = ','.join(['%s'] * len(usuarios_seleccionados))
            sql_ids = f"SELECT id, username FROM usuarios WHERE username IN ({placeholders})"
            cursor.execute(sql_ids, tuple(usuarios_seleccionados))
            users_data = cursor.fetchall()
            
            # Mapa ID -> Nombre y Acumulador {ID: 0}
            mapa_id_nombre = {u[0]: u[1] for u in users_data}
            puntos_acumulados = {u[0]: 0 for u in users_data}
            historial_grafico = {name: [] for name in usuarios_seleccionados}

            # 3. Iterar partido a partido
            for partido_id in partidos:
                # Obtener puntos de ESTE partido solo para los usuarios seleccionados
                if not mapa_id_nombre: break
                
                ids_in_clause = ','.join(map(str, mapa_id_nombre.keys()))
                
                sql_puntos = f"""
                    SELECT 
                        pr.usuario_id,
                        (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN SIGN(p.goles_independiente - p.goles_rival) = SIGN(pr.pred_goles_independiente - pr.pred_goles_rival) THEN {PUNTOS} ELSE 0 END) as puntos
                    FROM pronosticos pr
                    JOIN partidos p ON pr.partido_id = p.id
                    WHERE p.id = %s AND pr.usuario_id IN ({ids_in_clause})
                """
                cursor.execute(sql_puntos, (partido_id,))
                resultados = cursor.fetchall() 
                
                # Crear diccionario temporal para este partido {uid: puntos}
                puntos_fecha = {row[0]: row[1] for row in resultados}

                # Actualizar acumulados y guardar en historial
                for uid, nombre in mapa_id_nombre.items():
                    pts_ganados = puntos_fecha.get(uid, 0) # Si no pronosticó, suma 0
                    puntos_acumulados[uid] += pts_ganados
                    historial_grafico[nombre].append(puntos_acumulados[uid])

            return len(partidos), historial_grafico

        except Exception as e:
            logger.error(f"Error evolución puntos: {e}")
            return 0, {}
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_historial_puntos_usuario(self, edicion_id, usuario):
        """
        Obtiene una lista ordenada de puntos obtenidos por un usuario.
        Filtra solo el ÚLTIMO pronóstico realizado por partido para evitar duplicados en el gráfico.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            sql = f"""
            SELECT 
                CASE 
                    WHEN p.goles_independiente IS NULL THEN 0
                    WHEN pr.pred_goles_independiente IS NULL THEN 0
                    ELSE
                        (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN SIGN(p.goles_independiente - p.goles_rival) = SIGN(pr.pred_goles_independiente - pr.pred_goles_rival) THEN {PUNTOS} ELSE 0 END)
                END as puntos
            FROM partidos p
            -- Subconsulta para obtener SOLO el último pronóstico del usuario para cada partido
            LEFT JOIN (
                SELECT p1.partido_id, p1.pred_goles_independiente, p1.pred_goles_rival
                FROM pronosticos p1
                INNER JOIN (
                    SELECT partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    WHERE usuario_id = (SELECT id FROM usuarios WHERE username = %s)
                    GROUP BY partido_id
                ) p2 ON p1.partido_id = p2.partido_id AND p1.fecha_prediccion = p2.max_fecha
                WHERE p1.usuario_id = (SELECT id FROM usuarios WHERE username = %s)
            ) pr ON p.id = pr.partido_id
            WHERE p.edicion_id = %s 
              AND p.goles_independiente IS NOT NULL
            ORDER BY p.fecha_hora ASC
            """
            
            # Pasamos 'usuario' dos veces (para las subconsultas) y luego 'edicion_id'
            cursor.execute(sql, (usuario, usuario, edicion_id))
            resultados = cursor.fetchall()
            
            return [row[0] for row in resultados]

        except Exception as e:
            logger.error(f"Error obteniendo historial puntos: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()  

    def obtener_torneos_ganados(self, anio=None):
        """
        Calcula cuántos torneos ha ganado cada usuario aplicando los 4 criterios de desempate:
        1. Puntos (Mayor). 
        2. Cantidad Partidos Pronosticados (Mayor). 
        3. Anticipación Promedio (Mayor). 
        4. Eficiencia / Promedio Intentos (Menor).
        
        Solo cuenta torneos finalizados (e.finalizado = TRUE).
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            params = []
            filtro_anio = ""
            
            if anio is not None:
                filtro_anio = " AND a.numero = %s "
                params.append(anio)

            sql = f"""
            WITH LatestPredictions AS (
                -- CTE 1: Calcula Puntos, Cantidad de Partidos y Anticipación (usando el ÚLTIMO pronóstico)
                SELECT 
                    pr.usuario_id,
                    p.edicion_id,
                    SUM(
                        (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN SIGN(p.goles_independiente - p.goles_rival) = SIGN(pr.pred_goles_independiente - pr.pred_goles_rival) THEN {PUNTOS} ELSE 0 END)
                    ) as total_puntos,
                    COUNT(p.id) as cant_partidos,
                    AVG(TIMESTAMPDIFF(SECOND, pr.fecha_prediccion, p.fecha_hora)) as avg_anticipacion
                FROM pronosticos pr
                INNER JOIN (
                    -- Filtro para obtener solo el último pronóstico por partido/usuario
                    SELECT usuario_id, partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    GROUP BY usuario_id, partido_id
                ) last_pr ON pr.usuario_id = last_pr.usuario_id 
                         AND pr.partido_id = last_pr.partido_id 
                         AND pr.fecha_prediccion = last_pr.max_fecha
                JOIN partidos p ON pr.partido_id = p.id
                JOIN ediciones e ON p.edicion_id = e.id
                JOIN anios a ON e.anio_id = a.id
                WHERE p.goles_independiente IS NOT NULL 
                  AND e.finalizado = TRUE
                  {filtro_anio}
                GROUP BY pr.usuario_id, p.edicion_id
            ),
            TotalAttempts AS (
                -- CTE 2: Calcula el total de intentos (historial) para el desempate de eficiencia
                SELECT 
                    pr.usuario_id,
                    p.edicion_id,
                    COUNT(*) as total_intentos
                FROM pronosticos pr
                JOIN partidos p ON pr.partido_id = p.id
                JOIN ediciones e ON p.edicion_id = e.id
                JOIN anios a ON e.anio_id = a.id
                WHERE e.finalizado = TRUE
                  {filtro_anio}
                GROUP BY pr.usuario_id, p.edicion_id
            ),
            RankedUsers AS (
                -- CTE 3: Aplica el RANK() con los 4 criterios
                SELECT 
                    lp.usuario_id,
                    lp.edicion_id,
                    RANK() OVER (
                        PARTITION BY lp.edicion_id 
                        ORDER BY 
                            lp.total_puntos DESC,           -- 1. Más Puntos
                            lp.cant_partidos DESC,          -- 2. Más Partidos Jugados
                            lp.avg_anticipacion DESC,       -- 3. Mayor Anticipación
                            (COALESCE(ta.total_intentos, 0) / NULLIF(lp.cant_partidos, 0)) ASC -- 4. Menor Promedio Intentos
                    ) as ranking
                FROM LatestPredictions lp
                JOIN TotalAttempts ta ON lp.usuario_id = ta.usuario_id AND lp.edicion_id = ta.edicion_id
            )
            -- Consulta Final: Cuenta cuántas veces quedó 1º cada usuario
            SELECT 
                u.username,
                COUNT(r.edicion_id) as copas
            FROM usuarios u
            LEFT JOIN RankedUsers r ON u.id = r.usuario_id AND r.ranking = 1
            GROUP BY u.id, u.username
            ORDER BY copas DESC, u.username ASC
            """
            
            # Duplicamos params porque filtro_anio se usa 2 veces (en LatestPredictions y TotalAttempts)
            cursor.execute(sql, tuple(params * 2))
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error obteniendo historial de campeones: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
            
    def obtener_usuarios(self):
        """Obtiene la lista de nombres de usuario registrados."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            # Ordenamos alfabéticamente
            cursor.execute("SELECT username FROM usuarios ORDER BY username ASC")
            # Retornamos una lista simple de strings
            return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error obteniendo usuarios: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
    
    def obtener_racha_actual(self, edicion_id=None, anio=None):
        """
        Calcula la racha actual (partidos consecutivos sumando puntos).
        Si el torneo finalizó, calcula la racha con la que el usuario terminó el torneo.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            params = []
            filtro_sql = ""

            if edicion_id is not None:
                filtro_sql = " AND p.edicion_id = %s "
                params.append(edicion_id)
            elif anio is not None:
                filtro_sql = " AND a.numero = %s "
                params.append(anio)

            # Lógica:
            # 1. Obtenemos TODOS los partidos jugados (goles no nulos) del filtro.
            # 2. Cruzamos con Usuarios para evaluar partido a partido.
            # 3. Ordenamos por Fecha DESC (Del último partido jugado hacia atrás).
            sql = f"""
            SELECT 
                u.username,
                p.fecha_hora,
                CASE 
                    WHEN pr.pred_goles_independiente IS NULL THEN 0 -- Si no pronosticó, rompe racha
                    ELSE
                        (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN SIGN(p.goles_independiente - p.goles_rival) = SIGN(pr.pred_goles_independiente - pr.pred_goles_rival) THEN {PUNTOS} ELSE 0 END)
                END as puntos
            FROM usuarios u
            CROSS JOIN partidos p 
            JOIN ediciones e ON p.edicion_id = e.id
            JOIN anios a ON e.anio_id = a.id
            LEFT JOIN (
                SELECT p1.usuario_id, p1.partido_id, p1.pred_goles_independiente, p1.pred_goles_rival
                FROM pronosticos p1
                INNER JOIN (
                    SELECT usuario_id, partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    GROUP BY usuario_id, partido_id
                ) p2 ON p1.usuario_id = p2.usuario_id 
                    AND p1.partido_id = p2.partido_id 
                    AND p1.fecha_prediccion = p2.max_fecha
            ) pr ON u.id = pr.usuario_id AND p.id = pr.partido_id
            WHERE 
                p.goles_independiente IS NOT NULL -- Solo partidos que ya se jugaron
                {filtro_sql}
            ORDER BY u.username ASC, p.fecha_hora DESC
            """
            
            cursor.execute(sql, tuple(params))
            resultados = cursor.fetchall()
            
            # --- Cálculo de Racha ---
            rachas = []
            
            if resultados:
                usuario_actual = None
                racha_actual = 0
                racha_activa = True 
                
                for row in resultados:
                    user = row[0]
                    puntos = row[2]
                    
                    if user != usuario_actual:
                        # Guardar racha del usuario anterior
                        if usuario_actual is not None:
                            rachas.append((usuario_actual, racha_actual))
                        
                        # Iniciar nuevo usuario
                        usuario_actual = user
                        racha_actual = 0
                        racha_activa = True
                        
                        # Evaluamos el partido MÁS RECIENTE del filtro
                        if puntos > 0:
                            racha_actual += 1
                        else:
                            racha_activa = False # Si falló el último, racha actual es 0
                    else:
                        # Partidos anteriores (hacia atrás en el tiempo)
                        if racha_activa:
                            if puntos > 0:
                                racha_actual += 1
                            else:
                                racha_activa = False # Se cortó la racha aquí
                
                # Guardar el último usuario del loop
                if usuario_actual is not None:
                    rachas.append((usuario_actual, racha_actual))

            # Ordenar por quien tiene la racha activa más larga
            return sorted(rachas, key=lambda x: x[1], reverse=True)

        except Exception as e:
            logger.error(f"Error calculando racha actual: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
               
    def obtener_racha_record(self, edicion_id=None, anio=None):
        """
        Calcula la MEJOR racha (récord) de partidos consecutivos sumando puntos en la historia (o filtro).
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            params = []
            filtro_sql = ""

            if edicion_id is not None:
                filtro_sql = " AND p.edicion_id = %s "
                params.append(edicion_id)
            elif anio is not None:
                filtro_sql = " AND a.numero = %s "
                params.append(anio)

            # Query: Misma estructura que racha actual, pero ordenado por Fecha ASCENDENTE
            # para poder calcular la continuidad desde el principio.
            sql = f"""
            SELECT 
                u.username,
                p.fecha_hora,
                CASE 
                    WHEN pr.pred_goles_independiente IS NULL THEN 0
                    ELSE
                        (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN SIGN(p.goles_independiente - p.goles_rival) = SIGN(pr.pred_goles_independiente - pr.pred_goles_rival) THEN {PUNTOS} ELSE 0 END)
                END as puntos
            FROM usuarios u
            CROSS JOIN partidos p 
            JOIN ediciones e ON p.edicion_id = e.id
            JOIN anios a ON e.anio_id = a.id
            LEFT JOIN (
                SELECT p1.usuario_id, p1.partido_id, p1.pred_goles_independiente, p1.pred_goles_rival
                FROM pronosticos p1
                INNER JOIN (
                    SELECT usuario_id, partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    GROUP BY usuario_id, partido_id
                ) p2 ON p1.usuario_id = p2.usuario_id 
                    AND p1.partido_id = p2.partido_id 
                    AND p1.fecha_prediccion = p2.max_fecha
            ) pr ON u.id = pr.usuario_id AND p.id = pr.partido_id
            WHERE 
                p.goles_independiente IS NOT NULL
                {filtro_sql}
            ORDER BY u.username ASC, p.fecha_hora ASC
            """
            
            cursor.execute(sql, tuple(params))
            resultados = cursor.fetchall()
            
            # --- Algoritmo para encontrar el MAX streak por usuario ---
            mapa_maximos = {} # {username: max_racha}
            
            if resultados:
                usuario_actual = None
                racha_temporal = 0
                
                for row in resultados:
                    user = row[0]
                    puntos = row[2]
                    
                    if user != usuario_actual:
                        # Cambio de usuario, reseteamos contadores
                        usuario_actual = user
                        racha_temporal = 0
                        if user not in mapa_maximos:
                            mapa_maximos[user] = 0
                    
                    if puntos > 0:
                        racha_temporal += 1
                        # Si la racha actual supera al máximo guardado, actualizamos
                        if racha_temporal > mapa_maximos[user]:
                            mapa_maximos[user] = racha_temporal
                    else:
                        # Cortó racha
                        racha_temporal = 0
            
            # Convertir diccionario a lista de tuplas para ordenar
            lista_final = [(k, v) for k, v in mapa_maximos.items()]
            
            # Ordenar por racha récord descendente
            return sorted(lista_final, key=lambda x: x[1], reverse=True)

        except Exception as e:
            logger.error(f"Error calculando racha récord: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_todos_pronosticos(self):
        """
        Obtiene el listado de TODOS los pronósticos.
        Muestra Puntos y Error Absoluto SOLO si es el último pronóstico del usuario para ese partido.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            sql = f"""
            SELECT 
                r.nombre,
                p.fecha_hora,
                CONCAT(c.nombre, ' ', a.numero) as torneo,
                p.goles_independiente,
                p.goles_rival,
                u.username,
                pr.pred_goles_independiente,
                pr.pred_goles_rival,
                
                -- CÁLCULO DE PUNTOS
                CASE 
                    WHEN p.goles_independiente IS NULL THEN NULL
                    -- Si la fecha de ESTE pronóstico es anterior a la última registrada -> NULL
                    WHEN pr.fecha_prediccion < latest.max_fecha THEN NULL
                    ELSE
                        (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN SIGN(p.goles_independiente - p.goles_rival) = SIGN(pr.pred_goles_independiente - pr.pred_goles_rival) THEN {PUNTOS} ELSE 0 END)
                END as puntos,
                
                pr.fecha_prediccion,
                
                -- ERROR ABSOLUTO
                CASE 
                    WHEN p.goles_independiente IS NULL OR pr.pred_goles_independiente IS NULL THEN NULL
                    -- Si es un pronóstico antiguo -> NULL
                    WHEN pr.fecha_prediccion < latest.max_fecha THEN NULL
                    ELSE
                        ABS(CAST(p.goles_independiente AS SIGNED) - CAST(pr.pred_goles_independiente AS SIGNED)) + 
                        ABS(CAST(p.goles_rival AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED))
                END as error_absoluto

            FROM pronosticos pr  
            JOIN partidos p ON pr.partido_id = p.id
            JOIN usuarios u ON pr.usuario_id = u.id
            JOIN rivales r ON p.rival_id = r.id
            JOIN ediciones e ON p.edicion_id = e.id
            JOIN campeonatos c ON e.campeonato_id = c.id
            JOIN anios a ON e.anio_id = a.id
            
            -- JOIN para identificar cuál es la fecha del ÚLTIMO pronóstico para cada usuario/partido
            INNER JOIN (
                SELECT usuario_id, partido_id, MAX(fecha_prediccion) as max_fecha
                FROM pronosticos
                GROUP BY usuario_id, partido_id
            ) latest ON pr.usuario_id = latest.usuario_id AND pr.partido_id = latest.partido_id
            
            ORDER BY p.fecha_hora DESC, pr.fecha_prediccion DESC
            """
            
            cursor.execute(sql)
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error obteniendo pronósticos: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_estadisticas_estilo_pronostico(self, usuario, edicion_id=None, anio=None):
        """
        Obtiene estadísticas para el gráfico de torta de 'Estilo de Pronóstico'.
        Considera partidos PASADOS para determinar si hubo pronóstico o no.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            params = [usuario, usuario] # Para las subconsultas de pronósticos
            filtro_sql = ""

            # Filtros dinámicos
            if edicion_id is not None:
                filtro_sql += " AND p.edicion_id = %s "
                params.append(edicion_id)
            elif anio is not None:
                filtro_sql += " AND a.numero = %s "
                params.append(anio)

            sql = f"""
            SELECT 
                -- Total partidos jugados en el periodo
                COUNT(p.id) as total_partidos,
                
                -- Cantidad sin pronóstico (partidos pasados donde no hay predicción)
                SUM(CASE WHEN pr.pred_goles_independiente IS NULL THEN 1 ELSE 0 END) as sin_pronostico,
                
                -- Cantidad Victorias pronosticadas
                SUM(CASE WHEN pr.pred_goles_independiente > pr.pred_goles_rival THEN 1 ELSE 0 END) as pred_victoria,
                
                -- Cantidad Empates pronosticados
                SUM(CASE WHEN pr.pred_goles_independiente = pr.pred_goles_rival THEN 1 ELSE 0 END) as pred_empate,
                
                -- Cantidad Derrotas pronosticadas
                SUM(CASE WHEN pr.pred_goles_independiente < pr.pred_goles_rival THEN 1 ELSE 0 END) as pred_derrota

            FROM partidos p
            JOIN ediciones e ON p.edicion_id = e.id
            JOIN anios a ON e.anio_id = a.id
            
            -- Left Join para ver si el usuario pronosticó (solo el último pronóstico)
            LEFT JOIN (
                SELECT p1.partido_id, p1.pred_goles_independiente, p1.pred_goles_rival
                FROM pronosticos p1
                INNER JOIN (
                    SELECT partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    WHERE usuario_id = (SELECT id FROM usuarios WHERE username = %s)
                    GROUP BY partido_id
                ) p2 ON p1.partido_id = p2.partido_id AND p1.fecha_prediccion = p2.max_fecha
                WHERE p1.usuario_id = (SELECT id FROM usuarios WHERE username = %s)
            ) pr ON p.id = pr.partido_id
            
            WHERE 
                p.goles_independiente IS NOT NULL -- Solo partidos que ya se jugaron (historia)
                {filtro_sql}
            """
            
            cursor.execute(sql, tuple(params))
            return cursor.fetchone()

        except Exception as e:
            logger.error(f"Error obteniendo estadísticas estilo pronóstico: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
    
    def obtener_estadisticas_tendencia_pronostico(self, usuario, edicion_id=None, anio=None):
        """
        Calcula la cantidad de partidos en cada categoría de tendencia (Optimismo/Pesimismo)
        para un usuario, basado en la diferencia de goles pronosticada vs real.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            params = [usuario, usuario]
            filtro_sql = ""

            if edicion_id is not None:
                filtro_sql += " AND p.edicion_id = %s "
                params.append(edicion_id)
            elif anio is not None:
                filtro_sql += " AND a.numero = %s "
                params.append(anio)

            # Fórmula del índice: (Pred_CAI - Pred_Rival) - (Real_CAI - Real_Rival)
            # >= 1.5: Muy Optimista
            # 0.5 a 1.5: Optimista
            # -0.5 a 0.5: Realista
            # -1.5 a -0.5: Pesimista
            # <= -1.5: Muy Pesimista
            
            sql = f"""
            SELECT 
                COUNT(p.id) as total_partidos,
                
                -- 1. Sin Pronóstico
                SUM(CASE WHEN pr.pred_goles_independiente IS NULL THEN 1 ELSE 0 END) as sin_pronostico,
                
                -- 2. Muy Optimista (>= 1.5)
                SUM(CASE 
                    WHEN pr.pred_goles_independiente IS NOT NULL AND 
                         ((CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) - 
                          (CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED))) >= 1.5 
                    THEN 1 ELSE 0 END) as muy_optimista,
                    
                -- 3. Optimista (0.5 <= x < 1.5)
                SUM(CASE 
                    WHEN pr.pred_goles_independiente IS NOT NULL AND 
                         ((CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) - 
                          (CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED))) >= 0.5 AND
                         ((CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) - 
                          (CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED))) < 1.5
                    THEN 1 ELSE 0 END) as optimista,
                    
                -- 4. Realista (-0.5 < x < 0.5)
                SUM(CASE 
                    WHEN pr.pred_goles_independiente IS NOT NULL AND 
                         ((CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) - 
                          (CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED))) > -0.5 AND
                         ((CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) - 
                          (CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED))) < 0.5
                    THEN 1 ELSE 0 END) as realista,
                    
                -- 5. Pesimista (-1.5 < x <= -0.5)
                SUM(CASE 
                    WHEN pr.pred_goles_independiente IS NOT NULL AND 
                         ((CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) - 
                          (CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED))) > -1.5 AND
                         ((CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) - 
                          (CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED))) <= -0.5
                    THEN 1 ELSE 0 END) as pesimista,

                -- 6. Muy Pesimista (<= -1.5)
                SUM(CASE 
                    WHEN pr.pred_goles_independiente IS NOT NULL AND 
                         ((CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) - 
                          (CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED))) <= -1.5 
                    THEN 1 ELSE 0 END) as muy_pesimista

            FROM partidos p
            JOIN ediciones e ON p.edicion_id = e.id
            JOIN anios a ON e.anio_id = a.id
            
            LEFT JOIN (
                SELECT p1.partido_id, p1.pred_goles_independiente, p1.pred_goles_rival
                FROM pronosticos p1
                INNER JOIN (
                    SELECT partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    WHERE usuario_id = (SELECT id FROM usuarios WHERE username = %s)
                    GROUP BY partido_id
                ) p2 ON p1.partido_id = p2.partido_id AND p1.fecha_prediccion = p2.max_fecha
                WHERE p1.usuario_id = (SELECT id FROM usuarios WHERE username = %s)
            ) pr ON p.id = pr.partido_id
            
            WHERE 
                p.goles_independiente IS NOT NULL
                {filtro_sql}
            """
            
            cursor.execute(sql, tuple(params))
            return cursor.fetchone()

        except Exception as e:
            logger.error(f"Error obteniendo estadísticas tendencia: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
    
    def obtener_administradores(self):
        """
        Devuelve una lista con los usernames de los usuarios con tipo 'administrador'.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            sql = "SELECT username FROM usuarios WHERE tipo = 'administrador'"
            cursor.execute(sql)
            
            # fetchall devuelve una lista de tuplas [(user1,), (user2,)]
            # Usamos comprensión de listas para sacar el string limpio
            return [fila[0] for fila in cursor.fetchall()]
            
        except Exception as e:
            logger.error(f"Error obteniendo administradores: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_ranking_mayores_errores(self, usuario=None, edicion_id=None, anio=None):
        """
        Obtiene el listado de los pronósticos con mayor error absoluto.
        Trae un límite ampliado (50) para procesar el Top 10 con empates en la aplicación.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            params = []
            filtro_sql = ""

            # Filtros Opcionales
            if usuario:
                filtro_sql += " AND u.username = %s "
                params.append(usuario)
            
            if edicion_id is not None:
                filtro_sql += " AND p.edicion_id = %s "
                params.append(edicion_id)
            elif anio is not None:
                filtro_sql += " AND a.numero = %s "
                params.append(anio)

            sql = f"""
            SELECT 
                u.username,
                r.nombre,
                p.fecha_hora,
                pr.fecha_prediccion,
                pr.pred_goles_independiente,
                pr.pred_goles_rival,
                p.goles_independiente,
                p.goles_rival,
                -- Cálculo del Error Absoluto
                (ABS(CAST(p.goles_independiente AS SIGNED) - CAST(pr.pred_goles_independiente AS SIGNED)) + 
                 ABS(CAST(p.goles_rival AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED))) as error_absoluto

            FROM pronosticos pr
            JOIN partidos p ON pr.partido_id = p.id
            JOIN usuarios u ON pr.usuario_id = u.id
            JOIN rivales r ON p.rival_id = r.id
            JOIN ediciones e ON p.edicion_id = e.id
            JOIN anios a ON e.anio_id = a.id
            
            INNER JOIN (
                SELECT usuario_id, partido_id, MAX(fecha_prediccion) as max_fecha
                FROM pronosticos
                GROUP BY usuario_id, partido_id
            ) latest ON pr.usuario_id = latest.usuario_id AND pr.partido_id = latest.partido_id AND pr.fecha_prediccion = latest.max_fecha

            WHERE 
                p.goles_independiente IS NOT NULL
                {filtro_sql}
            
            ORDER BY error_absoluto DESC, p.fecha_hora DESC
            LIMIT 50 
            """
            # LIMIT 50: Traemos suficientes para calcular el Top 10 + empates en Python
            
            cursor.execute(sql, tuple(params))
            return cursor.fetchall()

        except Exception as e:
            logger.error(f"Error obteniendo mayores errores: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
            
    def obtener_estadisticas_firmeza_pronostico(self, usuario, edicion_id=None, anio=None):
        """
        Calcula estadísticas sobre la cantidad de veces que el usuario cambió su pronóstico
        para partidos del PASADO.
        Categorías:
        - 1 intento: Firme
        - 2 intentos: Dudoso
        - 3+ intentos: Cambiante
        - 0 intentos (o NULL): No participativo
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            # --- CORRECCIÓN AQUÍ: Solo un usuario en la lista ---
            params = [usuario] 
            filtro_sql = ""

            if edicion_id is not None:
                filtro_sql += " AND p.edicion_id = %s "
                params.append(edicion_id)
            elif anio is not None:
                filtro_sql += " AND a.numero = %s "
                params.append(anio)

            sql = f"""
            SELECT 
                COUNT(p.id) as total_partidos,
                
                -- 0. Sin Pronóstico (No participativo)
                SUM(CASE WHEN stats.cant_intentos IS NULL OR stats.cant_intentos = 0 THEN 1 ELSE 0 END) as sin_pronostico,
                
                -- 1. Firme (Exactamente 1 intento)
                SUM(CASE WHEN stats.cant_intentos = 1 THEN 1 ELSE 0 END) as firme,
                
                -- 2. Dudoso (Exactamente 2 intentos)
                SUM(CASE WHEN stats.cant_intentos = 2 THEN 1 ELSE 0 END) as dudoso,
                
                -- 3. Cambiante (3 o más intentos)
                SUM(CASE WHEN stats.cant_intentos >= 3 THEN 1 ELSE 0 END) as cambiante

            FROM partidos p
            JOIN ediciones e ON p.edicion_id = e.id
            JOIN anios a ON e.anio_id = a.id
            
            -- Subconsulta: Contar cuántos registros tiene el usuario por partido
            LEFT JOIN (
                SELECT partido_id, COUNT(*) as cant_intentos
                FROM pronosticos
                WHERE usuario_id = (SELECT id FROM usuarios WHERE username = %s)
                GROUP BY partido_id
            ) stats ON p.id = stats.partido_id
            
            WHERE 
                p.goles_independiente IS NOT NULL -- Solo partidos jugados (historial)
                {filtro_sql}
            """
            
            cursor.execute(sql, tuple(params))
            return cursor.fetchone()

        except Exception as e:
            logger.error(f"Error obteniendo estadísticas firmeza: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_ediciones(self):
        """
        Obtiene las ediciones de torneos (ID, Nombre, Año, Finalizado).
        Ordenado por año descendente y nombre.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            # AGREGAMOS e.finalizado a la consulta
            sql = """
            SELECT e.id, c.nombre, a.numero, e.finalizado
            FROM ediciones e
            JOIN campeonatos c ON e.campeonato_id = c.id
            JOIN anios a ON e.anio_id = a.id
            ORDER BY a.numero DESC, c.nombre ASC
            """
            
            cursor.execute(sql)
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error obteniendo ediciones: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_anios(self):
        """Obtiene la lista de años disponibles en la base de datos."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            cursor.execute("SELECT id, numero FROM anios ORDER BY numero DESC")
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error obteniendo años: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def marcar_edicion_finalizada(self, nombre_torneo, numero_anio):
        """
        Marca una edición como finalizada (finalizado = TRUE) en la base de datos.
        Se llama cuando la API detecta que ya no hay partidos futuros para este torneo.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            # 1. Buscar ID del Campeonato
            cursor.execute("SELECT id FROM campeonatos WHERE nombre = %s", (nombre_torneo,))
            res_camp = cursor.fetchone()
            
            # 2. Buscar ID del Año (Manejo de string/int)
            anio_str = str(numero_anio).split("-")[0]
            cursor.execute("SELECT id FROM anios WHERE numero = %s", (anio_str,))
            res_anio = cursor.fetchone()

            if res_camp and res_anio:
                camp_id = res_camp[0]
                anio_id = res_anio[0]
                
                # 3. Actualizar a FINALIZADO solo si aún no lo está
                sql = """
                    UPDATE ediciones 
                    SET finalizado = TRUE 
                    WHERE campeonato_id = %s AND anio_id = %s AND finalizado = FALSE
                """
                cursor.execute(sql, (camp_id, anio_id))
                
                if cursor.rowcount > 0:
                    logger.info(f"Torneo marcado como FINALIZADO: {nombre_torneo} {anio_str}")
                    return True
            return False

        except Exception as e:
            logger.error(f"Error finalizando edición en BD: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_ranking_mufa(self, edicion_id=None, anio=None):
        """
        Calcula el porcentaje de MUFA.
        Mufa = Usuario que pronostica derrota y el equipo PIERDE.
        Fórmula: (Derrotas Acertadas / Total Predicciones de Derrota) * 100
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            params = []
            filtro_sql = ""

            if edicion_id is not None:
                filtro_sql = " AND p.edicion_id = %s "
                params.append(edicion_id)
            elif anio is not None:
                filtro_sql = " AND a.numero = %s "
                params.append(anio)

            sql = f"""
            SELECT 
                u.username,
                stats.predicciones_derrota,
                stats.derrotas_acertadas,
                stats.porcentaje_mufa
            FROM usuarios u
            INNER JOIN (
                SELECT 
                    pr.usuario_id,
                    COUNT(*) as predicciones_derrota,
                    -- CAMBIO CLAVE: Contamos cuando REALMENTE PERDIÓ (Goles CAI < Goles Rival)
                    SUM(CASE WHEN p.goles_independiente < p.goles_rival THEN 1 ELSE 0 END) as derrotas_acertadas,
                    -- Cálculo de porcentaje
                    (SUM(CASE WHEN p.goles_independiente < p.goles_rival THEN 1 ELSE 0 END) / COUNT(*)) * 100 as porcentaje_mufa
                FROM pronosticos pr
                INNER JOIN (
                    SELECT usuario_id, partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    GROUP BY usuario_id, partido_id
                ) p2 ON pr.usuario_id = p2.usuario_id 
                    AND pr.partido_id = p2.partido_id 
                    AND pr.fecha_prediccion = p2.max_fecha
                JOIN partidos p ON pr.partido_id = p.id
                JOIN ediciones e ON p.edicion_id = e.id
                JOIN anios a ON e.anio_id = a.id
                WHERE 
                    p.goles_independiente IS NOT NULL
                    AND pr.pred_goles_independiente < pr.pred_goles_rival -- FILTRO: Solo cuando pronosticó derrota
                    {filtro_sql}
                GROUP BY pr.usuario_id
            ) stats ON u.id = stats.usuario_id
            
            ORDER BY 
                stats.porcentaje_mufa DESC,      -- El mayor % es el MÁS MUFA
                stats.predicciones_derrota DESC, -- Desempate por cantidad
                u.username ASC
            """
            
            cursor.execute(sql, tuple(params))
            return cursor.fetchall()

        except Exception as e:
            logger.error(f"Error calculando ranking mufa: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
            
    def obtener_ranking_falso_profeta(self, edicion_id=None, anio=None):
        """
        Ranking de Falso Profeta.
        CAMBIO: Se usa INNER JOIN para excluir usuarios que nunca pronosticaron victoria.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            params = []
            filtro_sql = ""

            if edicion_id is not None:
                filtro_sql = " AND p.edicion_id = %s "
                params.append(edicion_id)
            elif anio is not None:
                filtro_sql = " AND a.numero = %s "
                params.append(anio)

            sql = f"""
            SELECT 
                u.username,
                stats.victorias_pronosticadas,
                stats.porcentaje_acierto
            FROM usuarios u
            INNER JOIN ( -- CAMBIO: INNER JOIN excluye a los que no están en esta subconsulta
                SELECT 
                    pr.usuario_id,
                    COUNT(*) as victorias_pronosticadas,
                    (SUM(CASE WHEN p.goles_independiente > p.goles_rival THEN 1 ELSE 0 END) / COUNT(*)) * 100 as porcentaje_acierto
                FROM pronosticos pr
                INNER JOIN (
                    SELECT usuario_id, partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    GROUP BY usuario_id, partido_id
                ) p2 ON pr.usuario_id = p2.usuario_id 
                    AND pr.partido_id = p2.partido_id 
                    AND pr.fecha_prediccion = p2.max_fecha
                JOIN partidos p ON pr.partido_id = p.id
                JOIN ediciones e ON p.edicion_id = e.id
                JOIN anios a ON e.anio_id = a.id
                WHERE 
                    p.goles_independiente IS NOT NULL
                    AND pr.pred_goles_independiente > pr.pred_goles_rival -- FILTRO: Solo victorias pronosticadas
                    {filtro_sql}
                GROUP BY pr.usuario_id
            ) stats ON u.id = stats.usuario_id
            
            ORDER BY 
                stats.porcentaje_acierto ASC, 
                stats.victorias_pronosticadas DESC,
                u.username ASC
            """
            
            cursor.execute(sql, tuple(params))
            return cursor.fetchall()

        except Exception as e:
            logger.error(f"Error calculando ranking falso profeta: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()  

    def obtener_ranking(self, edicion_id=None, anio=None):
        """
        Calcula el ranking de usuarios.
        
        LÓGICA DE ANTICIPACIÓN (Actualizada):
        - Solo considera partidos del PASADO (fecha < ahora).
        - Los partidos futuros NO cuentan (ni suman ni restan).
        - Si un partido del pasado no se pronosticó, cuenta como 0 segundos.
        - Si no hay partidos jugados en el torneo, el promedio es 0 para todos.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor() 

            params = []
            
            # --- FILTROS DE EDICIÓN O AÑO ---
            condicion_filtro = ""
            if edicion_id is not None:
                condicion_filtro = " AND e.id = %s "
                params.append(edicion_id)
            elif anio is not None:
                condicion_filtro = " AND a.numero = %s "
                params.append(anio)
            
            # SQL Scope Jugados (Para Puntos y Efectividad)
            sql_scope_jugados = f"""
                SELECT p.id, p.goles_independiente, p.goles_rival, p.fecha_hora
                FROM partidos p
                JOIN ediciones e ON p.edicion_id = e.id 
                JOIN anios a ON e.anio_id = a.id 
                WHERE p.goles_independiente IS NOT NULL {condicion_filtro}
            """

            # ---------------------------------------------------------------
            # QUERY PRINCIPAL
            # ---------------------------------------------------------------
            sql = f"""
            SELECT 
                u.username,
                
                -- [1] Puntos Totales
                COALESCE(SUM(
                    (CASE WHEN SIGN(p.goles_independiente - p.goles_rival) = SIGN(pr.pred_goles_independiente - pr.pred_goles_rival) THEN {PUNTOS} ELSE 0 END) +
                    (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                    (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END)
                ), 0) AS total,

                -- [2-4] Desglose Puntos
                COALESCE(SUM(CASE WHEN SIGN(p.goles_independiente - p.goles_rival) = SIGN(pr.pred_goles_independiente - pr.pred_goles_rival) THEN {PUNTOS} ELSE 0 END), 0) AS pts_ganador,
                COALESCE(SUM(CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END), 0) AS pts_cai,
                COALESCE(SUM(CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END), 0) AS pts_rival,

                -- [5] Cantidad de partidos jugados (para efectividad)
                COUNT(p.id) as cant_pronosticos,
                
                -- [6] ANTICIPACIÓN PROMEDIO (SOLO PASADO)
                COALESCE(MAX(anti.promedio_segundos), 0) as avg_anticipacion_segundos,
                
                -- [7] Promedio de intentos
                COALESCE(MAX(att.total_intentos), 0) as total_intentos_raw,

                -- [8] Aciertos Exactos
                COALESCE(SUM(CASE WHEN p.goles_independiente = pr.pred_goles_independiente AND p.goles_rival = pr.pred_goles_rival THEN 1 ELSE 0 END), 0) as cant_exactos

            FROM usuarios u
            
            -- JOIN 1: ANTICIPACIÓN (Lógica Estricta: Solo Pasado)
            LEFT JOIN (
                SELECT 
                    u_sub.id as uid,
                    SUM(
                        CASE 
                            -- Si pronosticó, calculamos la diferencia
                            WHEN pr_all.fecha_prediccion IS NOT NULL THEN TIMESTAMPDIFF(SECOND, pr_all.fecha_prediccion, p_all.fecha_hora)
                            -- Si NO pronosticó y es partido pasado, penalización máxima (0 segundos de anticipación)
                            ELSE 0 
                        END
                    ) / COUNT(p_all.id) as promedio_segundos
                FROM usuarios u_sub
                -- Cruzamos usuarios con TODOS los partidos del filtro que ya sean PASADO
                CROSS JOIN partidos p_all
                JOIN ediciones e ON p_all.edicion_id = e.id
                JOIN anios a ON e.anio_id = a.id
                
                -- Unimos con el ÚLTIMO pronóstico disponible
                LEFT JOIN (
                    SELECT p1.usuario_id, p1.partido_id, p1.fecha_prediccion
                    FROM pronosticos p1
                    INNER JOIN (
                        SELECT usuario_id, partido_id, MAX(fecha_prediccion) as max_fecha
                        FROM pronosticos
                        GROUP BY usuario_id, partido_id
                    ) p2 ON p1.usuario_id = p2.usuario_id 
                        AND p1.partido_id = p2.partido_id 
                        AND p1.fecha_prediccion = p2.max_fecha
                ) pr_all ON u_sub.id = pr_all.usuario_id AND p_all.id = pr_all.partido_id
                
                WHERE 
                    1=1 {condicion_filtro} -- Filtro torneo/año
                    AND p_all.fecha_hora < DATE_SUB(NOW(), INTERVAL 3 HOUR) -- SOLO PARTIDOS DEL PASADO
                
                GROUP BY u_sub.id
            ) anti ON u.id = anti.uid

            -- JOIN 2: PUNTOS (Solo Partidos Jugados y con Resultado)
            LEFT JOIN (
                SELECT p1.usuario_id, p1.partido_id, p1.pred_goles_independiente, p1.pred_goles_rival
                FROM pronosticos p1
                INNER JOIN (
                    SELECT usuario_id, partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    GROUP BY usuario_id, partido_id
                ) p2 ON p1.usuario_id = p2.usuario_id 
                    AND p1.partido_id = p2.partido_id 
                    AND p1.fecha_prediccion = p2.max_fecha
            ) pr ON u.id = pr.usuario_id
            
            LEFT JOIN ({sql_scope_jugados}) p ON pr.partido_id = p.id
            
            -- JOIN 3: INTENTOS
            LEFT JOIN (
                SELECT pr2.usuario_id, COUNT(*) as total_intentos
                FROM pronosticos pr2
                JOIN ({sql_scope_jugados}) p_scope ON pr2.partido_id = p_scope.id
                GROUP BY pr2.usuario_id
            ) att ON u.id = att.usuario_id
            
            GROUP BY u.id, u.username
            ORDER BY 
                total DESC,
                cant_pronosticos DESC,
                avg_anticipacion_segundos DESC, 
                (COALESCE(MAX(att.total_intentos), 0) / NULLIF(COUNT(p.id), 0)) ASC;
            """
            
            # Parametros x3: 1 para Anti, 1 para Puntos, 1 para Intentos
            cursor.execute(sql, tuple(params * 3))
            filas = cursor.fetchall()
            
            resultados_procesados = []
            for row in filas:
                cant_pronosticos = row[5]
                total_intentos = row[7]
                cant_exactos = row[8]
                
                if cant_pronosticos > 0:
                    promedio_intentos = total_intentos / cant_pronosticos
                    efectividad = (cant_exactos / cant_pronosticos) * 100
                else:
                    promedio_intentos = 0
                    efectividad = 0.0
                
                lista_row = list(row[:7])
                lista_row.append(promedio_intentos) 
                lista_row.append(efectividad)
                resultados_procesados.append(lista_row)
                
            return resultados_procesados

        except Exception as e:
            logger.error(f"Error calculando ranking en BD: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_indice_optimismo_pesimismo(self, edicion_id=None, anio=None):
        """
        Calcula el índice unificado de Optimismo/Pesimismo mostrando a TODOS los usuarios.
        Formula: (Pred_CAI - Pred_Rival) - (Real_CAI - Real_Rival)
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            params = []
            filtro_sql = ""

            # Filtros se aplican a la subconsulta de partidos jugados
            if edicion_id is not None:
                filtro_sql = " AND p.edicion_id = %s "
                params.append(edicion_id)
            elif anio is not None:
                filtro_sql = " AND a.numero = %s "
                params.append(anio)

            sql = f"""
            SELECT 
                u.username,
                stats.indice_promedio
            FROM usuarios u
            LEFT JOIN (
                SELECT 
                    pr.usuario_id,
                    AVG(
                        (CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) - 
                        (CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED))
                    ) as indice_promedio
                FROM pronosticos pr
                INNER JOIN (
                    -- Último pronóstico por partido
                    SELECT usuario_id, partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    GROUP BY usuario_id, partido_id
                ) p2 ON pr.usuario_id = p2.usuario_id 
                    AND pr.partido_id = p2.partido_id 
                    AND pr.fecha_prediccion = p2.max_fecha
                JOIN partidos p ON pr.partido_id = p.id
                JOIN ediciones e ON p.edicion_id = e.id
                JOIN anios a ON e.anio_id = a.id
                WHERE 
                    p.goles_independiente IS NOT NULL
                    {filtro_sql}
                GROUP BY pr.usuario_id
            ) stats ON u.id = stats.usuario_id
            ORDER BY 
                CASE WHEN stats.indice_promedio IS NULL THEN 1 ELSE 0 END, -- Nulos al final (o principio según preferencia)
                stats.indice_promedio DESC, 
                u.username ASC
            """
            
            cursor.execute(sql, tuple(params))
            return cursor.fetchall()

        except Exception as e:
            logger.error(f"Error calculando indice opt/pes: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
    
    def obtener_ranking_mejor_predictor(self, edicion_id=None, anio=None):
        """
        Calcula el Ranking de Mejor Predictor basado en el Error Absoluto de Goles.
        Fórmula por partido: |G_Real_CAI - G_Pred_CAI| + |G_Real_Rival - G_Pred_Rival|
        El ranking se ordena por el PROMEDIO de ese error (ASCENDENTE, menor es mejor).
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            params = []
            filtro_sql = ""

            if edicion_id is not None:
                filtro_sql = " AND p.edicion_id = %s "
                params.append(edicion_id)
            elif anio is not None:
                filtro_sql = " AND a.numero = %s "
                params.append(anio)

            sql = f"""
            SELECT 
                u.username,
                stats.promedio_error
            FROM usuarios u
            INNER JOIN (
                SELECT 
                    pr.usuario_id,
                    -- Calculamos el promedio del error absoluto sumado de ambos equipos
                    AVG(
                        ABS(CAST(p.goles_independiente AS SIGNED) - CAST(pr.pred_goles_independiente AS SIGNED)) + 
                        ABS(CAST(p.goles_rival AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED))
                    ) as promedio_error
                FROM pronosticos pr
                INNER JOIN (
                    -- Solo el último pronóstico por partido
                    SELECT usuario_id, partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    GROUP BY usuario_id, partido_id
                ) p2 ON pr.usuario_id = p2.usuario_id 
                    AND pr.partido_id = p2.partido_id 
                    AND pr.fecha_prediccion = p2.max_fecha
                JOIN partidos p ON pr.partido_id = p.id
                JOIN ediciones e ON p.edicion_id = e.id
                JOIN anios a ON e.anio_id = a.id
                WHERE 
                    p.goles_independiente IS NOT NULL -- Solo partidos jugados
                    {filtro_sql}
                GROUP BY pr.usuario_id
            ) stats ON u.id = stats.usuario_id
            
            ORDER BY 
                stats.promedio_error ASC, -- Menor error es mejor
                u.username ASC
            """
            
            cursor.execute(sql, tuple(params))
            return cursor.fetchall()

        except Exception as e:
            logger.error(f"Error calculando ranking mejor predictor: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_pendientes_notificacion(self, dias=5):
        """
        Obtiene una lista de usuarios que tienen partidos sin pronosticar 
        en los próximos 'dias' y que NO han sido notificados hoy.
        Retorna: Lista de tuplas (id_usuario, username, email, rival_nombre, fecha_partido)
        
        AJUSTE HORARIO: Se resta 3 horas a NOW() para compensar el horario de TiDB.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            # La lógica es:
            # 1. Traer partidos futuros dentro del rango de días.
            # 2. Cruzar con usuarios que tienen email.
            # 3. Filtrar usuarios notificados HOY (usando hora ajustada).
            # 4. Excluir combinaciones (Usuario-Partido) que YA tienen pronóstico.
            
            sql = f"""
            SELECT 
                DISTINCT u.id, 
                u.username, 
                u.email, 
                r.nombre, 
                p.fecha_hora
            FROM partidos p
            JOIN rivales r ON p.rival_id = r.id
            CROSS JOIN usuarios u
            LEFT JOIN pronosticos pr ON p.id = pr.partido_id AND u.id = pr.usuario_id
            WHERE 
                -- Filtro de partidos próximos (Ajustado a hora ARG)
                p.fecha_hora >= DATE_SUB(NOW(), INTERVAL 3 HOUR)
                AND p.fecha_hora <= DATE_ADD(DATE_SUB(NOW(), INTERVAL 3 HOUR), INTERVAL %s DAY)
                
                AND pr.id IS NULL -- Que NO tenga pronóstico
                AND u.email IS NOT NULL -- Que tenga email
                
                -- Verificación de última notificación (Ajustado a fecha ARG)
                -- Si 'fecha_ultima_notificacion' es NULL O es de un día anterior al "Hoy Argentino"
                AND (
                    u.fecha_ultima_notificacion IS NULL 
                    OR DATE(u.fecha_ultima_notificacion) < DATE(DATE_SUB(NOW(), INTERVAL 3 HOUR))
                )
            ORDER BY u.id, p.fecha_hora ASC
            """
            
            cursor.execute(sql, (dias,))
            return cursor.fetchall()

        except Exception as e:
            logger.error(f"Error obteniendo pendientes notificación: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def marcar_usuario_notificado(self, usuario_id):
        """Actualiza la fecha de última notificación a 'ahora'."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            sql = "UPDATE usuarios SET fecha_ultima_notificacion = DATE_SUB(NOW(), INTERVAL 3 HOUR) WHERE id = %s"
            cursor.execute(sql, (usuario_id,))
            conexion.commit()
            return True
        except Exception as e:
            logger.error(f"Error marcando notificado: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def validar_usuario(self, input_identificador, password):
        """
        Verifica si el texto ingresado coincide con un Usuario O un Email.
        Retorna el 'username' real si la contraseña es correcta.
        Lanza excepciones con mensajes específicos para la UI.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor(dictionary=True)
            
            # Búsqueda dual: Nombre de usuario O Correo
            sql = "SELECT username, password FROM usuarios WHERE username = %s OR email = %s"
            cursor.execute(sql, (input_identificador, input_identificador))
            usuario = cursor.fetchone()
            
            # --- VALIDACIÓN 1: EXISTENCIA ---
            if not usuario:
                # Mensaje específico solicitado
                raise ValueError("El texto ingresado no corresponde a ningún nombre de usuario ni correo electrónico registrado.")
            
            # --- VALIDACIÓN 2: CONTRASEÑA ---
            hash_guardado = usuario['password']
            try:
                self.ph.verify(hash_guardado, password)
                # Retornamos el username real para que el sistema cargue los datos correctos
                return usuario['username']
            except VerifyMismatchError:
                raise ValueError("La contraseña es incorrecta.")
            
        except ValueError as ve:
            # Re-lanzamos los errores de validación (usuario no existe / contraseña mal)
            raise ve
        except Exception as e:
            logger.error(f"Error validando usuario: {e}")
            raise Exception(f"Fallo técnico en base de datos: {e}")
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def verificar_username_libre(self, nuevo_username):
        """Verifica que el nuevo nombre de usuario no esté ocupado."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            sql = "SELECT id FROM usuarios WHERE username = %s"
            cursor.execute(sql, (nuevo_username,))
            if cursor.fetchone():
                raise Exception("El nombre de usuario ya está en uso.")
            return True
        except Exception as e:
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def actualizar_username(self, id_usuario, nuevo_username):
        """Actualiza el nombre de usuario."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            sql = "UPDATE usuarios SET username = %s WHERE id = %s"
            cursor.execute(sql, (nuevo_username, id_usuario))
            conexion.commit()
            return True
        except Exception as e:
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_id_por_username(self, username):
        """Obtiene el ID numérico de un usuario."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            cursor.execute("SELECT id FROM usuarios WHERE username = %s", (username,))
            res = cursor.fetchone()
            return res[0] if res else None
        except Exception:
            return None
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
            
    def actualizar_email_usuario(self, username, nuevo_email):
        """Actualiza el correo electrónico del usuario."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            # Verificar que el email no lo esté usando otro usuario
            sql_check = "SELECT id FROM usuarios WHERE email = %s AND username != %s"
            cursor.execute(sql_check, (nuevo_email, username))
            if cursor.fetchone():
                raise Exception("El correo ya está en uso por otra cuenta.")

            sql = "UPDATE usuarios SET email = %s WHERE username = %s"
            cursor.execute(sql, (nuevo_email, username))
            conexion.commit()
            return True
        except Exception as e:
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
    
    def verificar_email_libre(self, nuevo_email, usuario_actual):
        """
        Verifica si un email está disponible para cambio (que no lo tenga OTRO usuario).
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            # Buscamos si existe el email PERO asociado a un usuario DISTINTO al actual
            sql = "SELECT username FROM usuarios WHERE email = %s AND username != %s"
            cursor.execute(sql, (nuevo_email, usuario_actual))
            resultado = cursor.fetchone()
            
            if resultado:
                raise Exception("El correo electrónico ya está registrado por otra cuenta.")
                
            return True 
            
        except Exception as e:
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
            
