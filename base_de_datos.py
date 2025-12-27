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

    def obtener_ranking(self, edicion_id=None):
        """
        Calcula el ranking. 
        Si edicion_id es None, calcula el global.
        Si se pasa un ID, filtra los puntos solo para los partidos de ese torneo.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor() 

            # Condición de filtro extra para el JOIN
            filtro_torneo = ""
            params = []
            
            if edicion_id is not None:
                filtro_torneo = " AND p.edicion_id = %s "
                params.append(edicion_id)

            sql = f"""
            SELECT 
                u.username,
                
                -- Columna 2: Puntos Totales
                COALESCE(SUM(
                    (CASE WHEN SIGN(p.goles_independiente - p.goles_rival) = SIGN(pr.pred_goles_independiente - pr.pred_goles_rival) THEN {PUNTOS} ELSE 0 END) +
                    (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                    (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END)
                ), 0) AS total,

                -- Columna 3: Puntos por Ganador
                COALESCE(SUM(CASE WHEN SIGN(p.goles_independiente - p.goles_rival) = SIGN(pr.pred_goles_independiente - pr.pred_goles_rival) THEN {PUNTOS} ELSE 0 END), 0) AS pts_ganador,

                -- Columna 4: Puntos por Goles Independiente
                COALESCE(SUM(CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END), 0) AS pts_cai,

                -- Columna 5: Puntos por Goles Rival
                COALESCE(SUM(CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END), 0) AS pts_rival

            FROM usuarios u
            -- Subconsulta para último pronóstico
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
            
            -- JOIN con Partidos aplicando el filtro de torneo si existe
            LEFT JOIN partidos p ON pr.partido_id = p.id AND p.goles_independiente IS NOT NULL {filtro_torneo}
            
            GROUP BY u.id, u.username
            ORDER BY total DESC;
            """
            
            cursor.execute(sql, tuple(params))
            resultados = cursor.fetchall()
            return resultados

        except Exception as e:
            logger.error(f"Error calculando ranking en BD: {e}")
            return []
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

    def _obtener_id_rival(self, cursor, nombre_rival):
        """
        Método auxiliar: Busca el ID de un rival por su nombre.
        Si el rival no existe en la tabla 'rivales', lo crea y devuelve el nuevo ID.
        """
        # 1. Intentar buscar el ID si ya existe
        sql_buscar = "SELECT id FROM rivales WHERE nombre = %s"
        cursor.execute(sql_buscar, (nombre_rival,))
        resultado = cursor.fetchone()
        
        if resultado:
            return resultado[0] # Retorna el ID existente
        else:
            # 2. Si no existe, crearlo
            sql_crear = "INSERT INTO rivales (nombre) VALUES (%s)"
            cursor.execute(sql_crear, (nombre_rival,))
            return cursor.lastrowid # Retorna el ID recién creado
    
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
        Inserta un nuevo pronóstico en la base de datos para el usuario y partido indicados.
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
            
            # 2. Insertar el pronóstico
            sql = """
                INSERT INTO pronosticos (usuario_id, partido_id, pred_goles_independiente, pred_goles_rival)
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(sql, (usuario_id, partido_id, pred_cai, pred_rival))
            conexion.commit()
            return True

        except Exception as e:
            logger.error(f"Error insertando pronóstico: {e}")
            raise e
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

    def eliminar_rivales_huerfanos(self):
        """
        Elimina de la base de datos todos los rivales que no tienen
        ningún partido asociado.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            # Usamos una subconsulta: Borrar de rivales SI su ID NO ESTÁ en la lista de rival_id de partidos
            sql = """
            DELETE FROM rivales 
            WHERE id NOT IN (SELECT DISTINCT rival_id FROM partidos)
            """
            
            cursor.execute(sql)
            filas_afectadas = cursor.rowcount
            conexion.commit()
            
            logger.info(f"Se eliminaron {filas_afectadas} rivales huérfanos.")
            return filas_afectadas

        except Exception as e:
            logger.error(f"Error eliminando rivales huérfanos: {e}")
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def editar_partido(self, id_partido, rival_nombre, fecha_hora, goles_cai, goles_rival, edicion_id):
        """
        Actualiza un partido.
        Lógica de Nombres:
        - Si el nombre nuevo NO existe: RENOMBRA el rival en la tabla 'rivales' (corrige typos globalmente).
        - Si el nombre nuevo YA existe: CAMBIA la referencia (rival_id) del partido.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            # 1. Obtener el ID del rival actual del partido
            cursor.execute("SELECT rival_id FROM partidos WHERE id = %s", (id_partido,))
            row = cursor.fetchone()
            if not row:
                raise Exception("El partido no existe.")
            rival_id_actual = row[0]

            # 2. Verificar si el nuevo nombre ya existe como otro rival diferente
            # Buscamos si existe un rival con ese nombre PERO que no sea el mismo ID que ya tenemos
            sql_check = "SELECT id FROM rivales WHERE nombre = %s AND id != %s"
            cursor.execute(sql_check, (rival_nombre, rival_id_actual))
            row_existente = cursor.fetchone()

            if row_existente:
                # CASO A: El nombre ya existe (ej: Cambiar 'Lanús' por 'Vélez' que ya existe)
                # No podemos renombrar Lanús a Vélez. Cambiamos la referencia del partido.
                nuevo_rival_id = row_existente[0]
                
                sql = """
                    UPDATE partidos 
                    SET rival_id = %s, fecha_hora = %s, goles_independiente = %s, goles_rival = %s, edicion_id = %s
                    WHERE id = %s
                """
                valores = (nuevo_rival_id, fecha_hora, goles_cai, goles_rival, edicion_id, id_partido)
                cursor.execute(sql, valores)
                
            else:
                # CASO B: El nombre no existe (ej: Corregir 'Racng' a 'Racing')
                # Aquí MODIFICAMOS el nombre en la tabla rivales.
                # Esto actualiza el nombre para este partido y todos los demás que jueguen contra este rival.
                
                # Paso 1: Renombrar el rival
                sql_rival = "UPDATE rivales SET nombre = %s WHERE id = %s"
                cursor.execute(sql_rival, (rival_nombre, rival_id_actual))
                
                # Paso 2: Actualizar el resto de datos del partido (fecha, goles, etc.)
                # Nota: No tocamos rival_id porque sigue siendo el mismo ID, solo cambió su nombre.
                sql_partido = """
                    UPDATE partidos 
                    SET fecha_hora = %s, goles_independiente = %s, goles_rival = %s, edicion_id = %s
                    WHERE id = %s
                """
                valores = (fecha_hora, goles_cai, goles_rival, edicion_id, id_partido)
                cursor.execute(sql_partido, valores)

            conexion.commit()
            return True

        except Exception as e:
            logger.error(f"Error editando partido: {e}")
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_torneos_ganados(self):
        """
        Calcula cuántos torneos ha ganado cada usuario.
        Solo cuenta torneos marcados como FINALIZADOS (e.finalizado = TRUE).
        Incluye a todos los usuarios, mostrando 0 si no ganaron ninguno.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

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
                WHERE p.goles_independiente IS NOT NULL 
                  AND e.finalizado = TRUE  -- SOLO TORNEOS FINALIZADOS
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
            
            cursor.execute(sql)
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

    def eliminar_partido(self, id_partido):
        """
        Elimina un partido por su ID.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            cursor.execute("DELETE FROM partidos WHERE id = %s", (id_partido,))
            conexion.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error eliminando partido: {e}")
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def existe_partido_fecha(self, fecha):
        """
        Verifica si ya existe un partido en la fecha indicada (sin importar la hora).
        Recibe un objeto date.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            # Comparamos solo la parte de la FECHA (DATE) para ignorar la hora
            sql = "SELECT id FROM partidos WHERE DATE(fecha_hora) = %s"
            cursor.execute(sql, (fecha,))
            resultado = cursor.fetchone()
            
            return resultado is not None # Retorna True si ya existe

        except Exception as e:
            logger.error(f"Error verificando existencia de partido: {e}")
            return False 
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def insertar_partido(self, rival, fecha_hora, goles_cai, goles_rival, edicion_id=1):
        """
        Inserta un nuevo partido gestionando automáticamente el ID del rival.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            # 1. Obtener el ID del rival (lo busca o lo crea)
            rival_id = self._obtener_id_rival(cursor, rival)

            # 2. Insertar el partido usando el ID
            sql = """
                INSERT INTO partidos (rival_id, fecha_hora, goles_independiente, goles_rival, edicion_id)
                VALUES (%s, %s, %s, %s, %s)
            """
            valores = (rival_id, fecha_hora, goles_cai, goles_rival, edicion_id)
            
            cursor.execute(sql, valores)
            conexion.commit()
            return True

        except Exception as e:
            logger.error(f"Error insertando partido: {e}")
            raise e
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

    def eliminar_torneo(self, id_edicion):
        """
        Elimina una edición. Fallará si tiene partidos asociados (FK RESTRICT).
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            cursor.execute("DELETE FROM ediciones WHERE id = %s", (id_edicion,))
            conexion.commit()
            return True
            
        except mysql.connector.IntegrityError as e:
            # Error 1451: Cannot delete or update a parent row (foreign key constraint fails)
            if e.errno == 1451:
                raise Exception("No se puede eliminar el torneo porque tiene partidos asociados. Elimine los partidos primero.")
            raise e
        except Exception as e:
            logger.error(f"Error eliminando torneo: {e}")
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def editar_torneo(self, id_edicion, nuevo_nombre, nuevo_anio, nuevo_finalizado):
        """
        Actualiza una edición existente, incluyendo su estado de finalización.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            # 1. Gestionar AÑO
            cursor.execute("SELECT id FROM anios WHERE numero = %s", (nuevo_anio,))
            res_anio = cursor.fetchone()
            if res_anio:
                anio_id = res_anio[0]
            else:
                cursor.execute("INSERT INTO anios (numero) VALUES (%s)", (nuevo_anio,))
                anio_id = cursor.lastrowid

            # 2. Gestionar CAMPEONATO
            cursor.execute("SELECT id FROM campeonatos WHERE nombre = %s", (nuevo_nombre,))
            res_camp = cursor.fetchone()
            if res_camp:
                campeonato_id = res_camp[0]
            else:
                cursor.execute("INSERT INTO campeonatos (nombre) VALUES (%s)", (nuevo_nombre,))
                campeonato_id = cursor.lastrowid

            # 3. ACTUALIZAR la edición
            try:
                sql = "UPDATE ediciones SET campeonato_id = %s, anio_id = %s, finalizado = %s WHERE id = %s"
                cursor.execute(sql, (campeonato_id, anio_id, nuevo_finalizado, id_edicion))
                conexion.commit()
                return True
            except mysql.connector.IntegrityError as e:
                if e.errno == 1062:
                    raise Exception(f"Ya existe otro torneo registrado como '{nuevo_nombre} {nuevo_anio}'.")
                raise e

        except Exception as e:
            logger.error(f"Error editando torneo: {e}")
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def crear_torneo(self, nombre_campeonato, anio, finalizado=False):
        """
        Crea una edición de torneo.
        Si el 'año' o el 'campeonato' (nombre) no existen, los crea automáticamente.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            # 1. Gestionar el AÑO
            cursor.execute("SELECT id FROM anios WHERE numero = %s", (anio,))
            res_anio = cursor.fetchone()
            if res_anio:
                anio_id = res_anio[0]
            else:
                cursor.execute("INSERT INTO anios (numero) VALUES (%s)", (anio,))
                anio_id = cursor.lastrowid

            # 2. Gestionar el CAMPEONATO
            cursor.execute("SELECT id FROM campeonatos WHERE nombre = %s", (nombre_campeonato,))
            res_camp = cursor.fetchone()
            if res_camp:
                campeonato_id = res_camp[0]
            else:
                cursor.execute("INSERT INTO campeonatos (nombre) VALUES (%s)", (nombre_campeonato,))
                campeonato_id = cursor.lastrowid

            # 3. Insertar la EDICIÓN con el campo finalizado
            try:
                sql = "INSERT INTO ediciones (campeonato_id, anio_id, finalizado) VALUES (%s, %s, %s)"
                cursor.execute(sql, (campeonato_id, anio_id, finalizado))
                conexion.commit()
                return True
            except mysql.connector.IntegrityError as e:
                if e.errno == 1062: 
                    raise Exception(f"El torneo '{nombre_campeonato} {anio}' ya existe.")
                raise e

        except Exception as e:
            logger.error(f"Error creando torneo: {e}")
            raise e
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