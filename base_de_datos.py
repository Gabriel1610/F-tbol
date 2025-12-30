import mysql.connector
import logging
from datetime import datetime
import sys
import os # IMPORTANTE: Para encontrar el certificado
from mysql.connector import errorcode
# Importamos Argon2 para el hashing moderno
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

PUNTOS = 3
MÁXIMA_CANTIDAD_DE_PUNTOS = 9

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

    def insertar_usuario(self, username, password):
        """
        Hashea la contraseña con Argon2 y guarda fecha local del sistema.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            # Hashing
            password_hash = self.ph.hash(password)

            # Obtenemos la hora actual de TU sistema (Argentina)
            fecha_actual = datetime.now()

            # Modificamos la consulta para incluir fecha_registro explícitamente
            sql = "INSERT INTO usuarios (username, password, fecha_registro) VALUES (%s, %s, %s)"
            
            # Pasamos fecha_actual como tercer valor
            valores = (username, password_hash, fecha_actual)

            cursor.execute(sql, valores)
            conexion.commit()
            
            logger.info(f"Usuario '{username}' registrado exitosamente el {fecha_actual}.")
            return True

        except mysql.connector.IntegrityError as err:
            if err.errno == 1062: 
                logger.warning(f"Intento de registro duplicado para: {username}")
                raise Exception("El nombre de usuario ya existe. Por favor elija otro.")
            else:
                raise Exception(f"Error de integridad en datos: {err}")

        except mysql.connector.Error as err:
            logger.error(f"Error de base de datos: {err}")
            raise Exception("Ocurrió un error interno al intentar guardar los datos.")
            
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

    def obtener_partidos(self, usuario, filtro='todos', edicion_id=None, rival_id=None):
        """
        Obtiene la lista de partidos filtrada y ordenada.
        Parámetros:
            usuario (str): Usuario actual.
            filtro (str): 'todos', 'jugados', 'futuros', 'torneo', 'sin_pronosticar', 'equipo'.
            edicion_id (int): ID de la edición (necesario si filtro='torneo').
            rival_id (int): ID del rival (necesario si filtro='equipo').
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            filtro_sql = ""
            orden_sql = "DESC" 
            
            # Parametros base para la query (usuario aparece 2 veces en subconsulta)
            params = [usuario, usuario]

            if filtro == 'futuros':
                filtro_sql = "WHERE p.fecha_hora > NOW()"
                orden_sql = "ASC"
            elif filtro == 'jugados':
                filtro_sql = "WHERE p.fecha_hora <= NOW()"
                orden_sql = "DESC"
            elif filtro == 'sin_pronosticar':
                filtro_sql = "WHERE p.fecha_hora > NOW() AND pr.pred_goles_independiente IS NULL"
                orden_sql = "ASC"
            elif filtro == 'torneo' and edicion_id is not None:
                filtro_sql = "WHERE p.edicion_id = %s"
                orden_sql = "ASC"
                params.append(edicion_id)
            elif filtro == 'equipo' and rival_id is not None:
                # Nuevo filtro por Rival
                filtro_sql = "WHERE p.rival_id = %s"
                orden_sql = "DESC" # Pedido: descendente por Fecha y Hora
                params.append(rival_id)

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
                CASE 
                    WHEN p.goles_independiente IS NULL THEN NULL 
                    WHEN pr.pred_goles_independiente IS NULL THEN 0 
                    ELSE
                        (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN SIGN(p.goles_independiente - p.goles_rival) = SIGN(pr.pred_goles_independiente - pr.pred_goles_rival) THEN {PUNTOS} ELSE 0 END)
                END as tus_puntos
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
            
            {filtro_sql}
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
        Calcula la evolución del ranking partido a partido.
        Maneja empates: Si varios usuarios tienen los mismos puntos, comparten el mejor puesto.
        Ejemplo: Juan(50) -> 1º, José(45) -> 2º, Pedro(45) -> 2º.
        Retorna: 
            - cantidad_partidos (int)
            - total_usuarios_sistema (int)
            - historial (dict): {usuario: [puesto_fecha_1, puesto_fecha_2...]}
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            # 1. Contar total de usuarios para escalar el gráfico
            cursor.execute("SELECT COUNT(*) FROM usuarios")
            total_usuarios = cursor.fetchone()[0]

            # 2. Obtener partidos JUGADOS de la edición ordenados por fecha
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

            # 3. Obtener todos los usuarios
            cursor.execute("SELECT id, username FROM usuarios")
            usuarios_bd = cursor.fetchall()
            
            puntos_acumulados = {u[0]: 0 for u in usuarios_bd} 
            mapa_nombres = {u[0]: u[1] for u in usuarios_bd}
            historial_grafico = {user: [] for user in usuarios_seleccionados}

            # 4. Iterar partido a partido
            for partido_id in partidos:
                # Obtener puntos de ESTA fecha
                sql_puntos = f"""
                    SELECT 
                        pr.usuario_id,
                        (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN SIGN(p.goles_independiente - p.goles_rival) = SIGN(pr.pred_goles_independiente - pr.pred_goles_rival) THEN {PUNTOS} ELSE 0 END) as puntos
                    FROM pronosticos pr
                    JOIN partidos p ON pr.partido_id = p.id
                    WHERE p.id = %s
                """
                cursor.execute(sql_puntos, (partido_id,))
                resultados = cursor.fetchall()

                # Sumar al acumulado global
                for uid, pts in resultados:
                    if uid in puntos_acumulados:
                        puntos_acumulados[uid] += pts

                # --- CÁLCULO DE RANKING CON EMPATES ---
                # Ordenar lista de (id, puntos) de mayor a menor
                ranking_ordenado = sorted(puntos_acumulados.items(), key=lambda x: x[1], reverse=True)
                
                mapa_puestos = {}
                puntos_anteriores = -1
                puesto_actual = 0
                
                for i, (uid, pts) in enumerate(ranking_ordenado):
                    # Si los puntos son distintos al anterior, el puesto es su posición real en la lista (índice + 1)
                    if pts != puntos_anteriores:
                        puesto_actual = i + 1
                        puntos_anteriores = pts
                    # Si los puntos son iguales, se mantiene el 'puesto_actual' (el mejor del grupo empatado)
                    
                    mapa_puestos[uid] = puesto_actual

                # Guardar el puesto calculado para los usuarios seleccionados
                for usuario_target in usuarios_seleccionados:
                    # Buscar ID del nombre de usuario
                    target_id = next((k for k, v in mapa_nombres.items() if v == usuario_target), None)
                    if target_id:
                        puesto = mapa_puestos.get(target_id)
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
        Calcula cuántos torneos ha ganado cada usuario.
        - Solo cuenta torneos marcados como FINALIZADOS (e.finalizado = TRUE).
        - Si anio is not None, solo cuenta los torneos finalizados de ese año.
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
            WITH PuntosPorUsuarioEdicion AS (
                SELECT 
                    u.username,
                    p.edicion_id,
                    SUM(
                        (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN SIGN(p.goles_independiente - p.goles_rival) = SIGN(pr.pred_goles_independiente - pr.pred_goles_rival) THEN {PUNTOS} ELSE 0 END)
                    ) as total_puntos
                FROM usuarios u
                JOIN pronosticos pr ON u.id = pr.usuario_id
                JOIN partidos p ON pr.partido_id = p.id
                JOIN ediciones e ON p.edicion_id = e.id
                JOIN anios a ON e.anio_id = a.id  -- Join necesario para filtrar por año
                WHERE p.goles_independiente IS NOT NULL 
                  AND e.finalizado = TRUE
                  {filtro_anio} -- Inyección del filtro
                GROUP BY u.username, p.edicion_id
            ),
            MaximosPorEdicion AS (
                SELECT edicion_id, MAX(total_puntos) as max_pts
                FROM PuntosPorUsuarioEdicion
                GROUP BY edicion_id
            ),
            GanadoresPorEdicion AS (
                SELECT p.username, p.edicion_id
                FROM PuntosPorUsuarioEdicion p
                JOIN MaximosPorEdicion m ON p.edicion_id = m.edicion_id AND p.total_puntos = m.max_pts
                WHERE m.max_pts > 0
            )
            SELECT 
                u.username,
                COUNT(g.edicion_id) as copas
            FROM usuarios u
            LEFT JOIN GanadoresPorEdicion g ON u.username = g.username
            GROUP BY u.username
            ORDER BY copas DESC, u.username ASC
            """
            
            cursor.execute(sql, tuple(params))
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

    def obtener_todos_pronosticos(self):
        """
        Obtiene el listado de TODOS los pronósticos (historial completo).
        Incluye la fecha en la que se realizó la predicción.
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
                    ELSE
                        (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN SIGN(p.goles_independiente - p.goles_rival) = SIGN(pr.pred_goles_independiente - pr.pred_goles_rival) THEN {PUNTOS} ELSE 0 END)
                END as puntos,
                pr.fecha_prediccion  -- [NUEVO CAMPO: Índice 9]
            FROM pronosticos pr  -- JOIN Directo (Trae todos los registros)
            JOIN partidos p ON pr.partido_id = p.id
            JOIN usuarios u ON pr.usuario_id = u.id
            JOIN rivales r ON p.rival_id = r.id
            JOIN ediciones e ON p.edicion_id = e.id
            JOIN campeonatos c ON e.campeonato_id = c.id
            JOIN anios a ON e.anio_id = a.id
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

    def obtener_ranking(self, edicion_id=None, anio=None):
        """
        Calcula el ranking incluyendo estadísticas de participación y anticipación.
        Retorna una lista extendida con la tasa de pronósticos y el tiempo promedio.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor() 

            params = []

            # 1. Filtros de Partidos Jugados
            if edicion_id is not None:
                sql_partidos_filtrados = """
                    SELECT id, goles_independiente, goles_rival, fecha_hora 
                    FROM partidos 
                    WHERE goles_independiente IS NOT NULL AND edicion_id = %s
                """
                params.append(edicion_id)
            elif anio is not None:
                sql_partidos_filtrados = """
                    SELECT p.id, p.goles_independiente, p.goles_rival, p.fecha_hora
                    FROM partidos p
                    JOIN ediciones e ON p.edicion_id = e.id 
                    JOIN anios a ON e.anio_id = a.id 
                    WHERE p.goles_independiente IS NOT NULL AND a.numero = %s
                """
                params.append(anio)
            else:
                sql_partidos_filtrados = """
                    SELECT id, goles_independiente, goles_rival, fecha_hora
                    FROM partidos 
                    WHERE goles_independiente IS NOT NULL
                """

            # 2. Obtener Total de Partidos Jugados en el contexto (para el promedio)
            cursor.execute(f"SELECT COUNT(*) FROM ({sql_partidos_filtrados}) as t", tuple(params))
            total_partidos_contexto = cursor.fetchone()[0]
            
            if total_partidos_contexto == 0:
                total_partidos_contexto = 1 # Evitar división por cero

            # 3. Query Principal
            # Se agrega: p1.fecha_prediccion a la subquery de pronósticos
            # Se agrega: COUNT(p.id) para contar pronósticos hechos sobre partidos jugados
            # Se agrega: AVG(TIMESTAMPDIFF) para calcular anticipación promedio
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

                -- [5] Cantidad de pronósticos hechos
                COUNT(p.id) as cant_pronosticos,
                
                -- [6] Promedio de segundos de anticipación (Fecha Partido - Fecha Pronóstico)
                AVG(TIMESTAMPDIFF(SECOND, pr.fecha_prediccion, p.fecha_hora)) as avg_anticipacion_segundos

            FROM usuarios u
            
            LEFT JOIN (
                SELECT p1.usuario_id, p1.partido_id, p1.pred_goles_independiente, p1.pred_goles_rival, p1.fecha_prediccion
                FROM pronosticos p1
                INNER JOIN (
                    SELECT usuario_id, partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    GROUP BY usuario_id, partido_id
                ) p2 ON p1.usuario_id = p2.usuario_id 
                    AND p1.partido_id = p2.partido_id 
                    AND p1.fecha_prediccion = p2.max_fecha
            ) pr ON u.id = pr.usuario_id
            
            LEFT JOIN ({sql_partidos_filtrados}) p ON pr.partido_id = p.id
            
            GROUP BY u.id, u.username
            ORDER BY total DESC, avg_anticipacion_segundos DESC, cant_pronosticos ASC;
            """
            
            cursor.execute(sql, tuple(params))
            filas = cursor.fetchall()
            
            # Procesamos el resultado para calcular la tasa de participación en Python
            resultados_procesados = []
            for row in filas:
                # row índices: 0:user, 1:total, 2:gan, 3:cai, 4:riv, 5:cant_pron, 6:avg_sec
                cant_pronosticos = row[5]
                promedio_participacion = cant_pronosticos / total_partidos_contexto
                
                # Agregamos el promedio al final de la fila (índice 7)
                lista_row = list(row)
                lista_row.append(promedio_participacion)
                resultados_procesados.append(lista_row)
                
            return resultados_procesados

        except Exception as e:
            logger.error(f"Error calculando ranking en BD: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def validar_usuario(self, username, password):
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor(dictionary=True)
            
            sql = "SELECT password FROM usuarios WHERE username = %s"
            cursor.execute(sql, (username,))
            usuario = cursor.fetchone()
            
            if usuario:
                hash_guardado = usuario['password']
                try:
                    self.ph.verify(hash_guardado, password)
                    return True
                except VerifyMismatchError:
                    return False
            return False
            
        except Exception as e:
            logger.error(f"Error validando usuario: {e}")
            # --- MODIFICACIÓN: Lanzar el error real al usuario ---
            raise Exception(f"Fallo técnico: {e}")
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()