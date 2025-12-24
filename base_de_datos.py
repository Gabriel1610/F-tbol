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

    def obtener_ranking(self):
        """
        Calcula el ranking directamente en la Base de Datos.
        Utiliza la constante PUNTOS definida al inicio del archivo.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor() 

            # CAMBIOS IMPORTANTES:
            # 1. Usamos COALESCE(SUM(...), 0) para que devuelva 0 en lugar de None si no hay puntos.
            # 2. Usamos LEFT JOIN para traer a TODOS los usuarios, tengan o no predicciones.
            # 3. La condición "goles_independiente IS NOT NULL" se mueve al ON del JOIN. 
            #    Esto evita filtrar a los usuarios que no tienen partidos jugados aun.
            
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
            LEFT JOIN pronosticos pr ON u.id = pr.usuario_id
            -- Aquí está el truco: Filtramos que el partido se haya jugado EN EL JOIN, no en el WHERE
            LEFT JOIN partidos p ON pr.partido_id = p.id AND p.goles_independiente IS NOT NULL
            
            GROUP BY u.id, u.username
            ORDER BY total DESC;
            """
            
            cursor.execute(sql)
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
        
    def obtener_partidos(self):
        """
        Obtiene la lista de partidos uniendo con la tabla de rivales.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            sql = """
            SELECT 
                p.id,
                r.nombre,  -- CAMBIO: Traemos el nombre desde la tabla rivales
                p.fecha_hora,
                CONCAT(c.nombre, ' ', a.numero) as torneo_completo,
                p.goles_independiente,
                p.goles_rival,
                p.edicion_id,
                CASE 
                    WHEN TIME(p.fecha_hora) = '00:00:00' THEN DATE_FORMAT(p.fecha_hora, '%d/%m/%Y s. h.')
                    ELSE DATE_FORMAT(p.fecha_hora, '%d/%m/%Y %H:%i')
                END as fecha_display
            FROM partidos p
            JOIN rivales r ON p.rival_id = r.id  -- CAMBIO: JOIN con la nueva tabla
            JOIN ediciones e ON p.edicion_id = e.id
            JOIN campeonatos c ON e.campeonato_id = c.id
            JOIN anios a ON e.anio_id = a.id
            ORDER BY p.fecha_hora DESC
            """
            
            cursor.execute(sql)
            resultados = cursor.fetchall()
            return resultados

        except Exception as e:
            logger.error(f"Error obteniendo partidos: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def editar_partido(self, id_partido, rival, fecha_hora, goles_cai, goles_rival, edicion_id):
        """
        Actualiza un partido, gestionando el cambio de nombre de rival si es necesario.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            # 1. Obtener el ID del rival (lo busca o lo crea si cambió el nombre)
            rival_id = self._obtener_id_rival(cursor, rival)

            # 2. Actualizar usando el ID
            sql = """
                UPDATE partidos 
                SET rival_id = %s, fecha_hora = %s, goles_independiente = %s, goles_rival = %s, edicion_id = %s
                WHERE id = %s
            """
            valores = (rival_id, fecha_hora, goles_cai, goles_rival, edicion_id, id_partido)
            
            cursor.execute(sql, valores)
            conexion.commit()
            return True

        except Exception as e:
            logger.error(f"Error editando partido: {e}")
            raise e
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
        Obtiene las ediciones de torneos (ID, Nombre, Año).
        Ordenado por año descendente y nombre.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            sql = """
            SELECT e.id, c.nombre, a.numero
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

    def editar_torneo(self, id_edicion, nuevo_nombre, nuevo_anio):
        """
        Actualiza una edición existente.
        Busca/Crea el campeonato y el año, y actualiza la referencia en la tabla ediciones.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            # 1. Gestionar AÑO (Igual que en crear)
            cursor.execute("SELECT id FROM anios WHERE numero = %s", (nuevo_anio,))
            res_anio = cursor.fetchone()
            if res_anio:
                anio_id = res_anio[0]
            else:
                cursor.execute("INSERT INTO anios (numero) VALUES (%s)", (nuevo_anio,))
                anio_id = cursor.lastrowid

            # 2. Gestionar CAMPEONATO (Igual que en crear)
            cursor.execute("SELECT id FROM campeonatos WHERE nombre = %s", (nuevo_nombre,))
            res_camp = cursor.fetchone()
            if res_camp:
                campeonato_id = res_camp[0]
            else:
                cursor.execute("INSERT INTO campeonatos (nombre) VALUES (%s)", (nuevo_nombre,))
                campeonato_id = cursor.lastrowid

            # 3. ACTUALIZAR la edición
            try:
                sql = "UPDATE ediciones SET campeonato_id = %s, anio_id = %s WHERE id = %s"
                cursor.execute(sql, (campeonato_id, anio_id, id_edicion))
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

    def crear_torneo(self, nombre_campeonato, anio):
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
            # Verificamos si existe, si no, lo insertamos.
            cursor.execute("SELECT id FROM anios WHERE numero = %s", (anio,))
            res_anio = cursor.fetchone()
            if res_anio:
                anio_id = res_anio[0]
            else:
                cursor.execute("INSERT INTO anios (numero) VALUES (%s)", (anio,))
                anio_id = cursor.lastrowid

            # 2. Gestionar el CAMPEONATO (Nombre)
            # Verificamos si existe, si no, lo insertamos.
            cursor.execute("SELECT id FROM campeonatos WHERE nombre = %s", (nombre_campeonato,))
            res_camp = cursor.fetchone()
            if res_camp:
                campeonato_id = res_camp[0]
            else:
                cursor.execute("INSERT INTO campeonatos (nombre) VALUES (%s)", (nombre_campeonato,))
                campeonato_id = cursor.lastrowid

            # 3. Insertar la EDICIÓN (La unión de ambos)
            # Usamos INSERT IGNORE o manejamos el error si ya existe esa combinación
            try:
                sql = "INSERT INTO ediciones (campeonato_id, anio_id) VALUES (%s, %s)"
                cursor.execute(sql, (campeonato_id, anio_id))
                conexion.commit()
                return True
            except mysql.connector.IntegrityError as e:
                if e.errno == 1062: # Duplicate entry
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