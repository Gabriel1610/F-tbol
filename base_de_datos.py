import mysql.connector
import logging
from datetime import datetime
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
        # Inicializamos el Hasher de Argon2
        self.ph = PasswordHasher()

        # --- SOLUCIÓN DEL ERROR SSL ---
        # Calculamos la ruta absoluta del archivo .pem para que Python lo encuentre sí o sí
        carpeta_actual = os.path.dirname(os.path.abspath(__file__))
        ruta_certificado = os.path.join(carpeta_actual, "isrgrootx1.pem")
        
        # Verificamos si el archivo existe (opcional, ayuda a depurar)
        if not os.path.exists(ruta_certificado):
            logger.error(f"NO SE ENCUENTRA EL CERTIFICADO EN: {ruta_certificado}")

        # Configuración para TiDB Cloud
        self.config = {
            'user': '3XY8PLHt12tsDbZ.root',       
            'password': 'mXv9F5VQGmRiYYZH',     # <--- ¡RECUERDA VOLVER A PEGAR TU CONTRASEÑA REAL AQUÍ!
            'host': 'gateway01.us-east-1.prod.aws.tidbcloud.com', 
            'port': 4000,                         
            'database': 'independiente',          
            'raise_on_warnings': True,
            
            # Pasamos la ruta completa del certificado
            'ssl_ca': ruta_certificado,           
            'ssl_verify_cert': True
        }

    def abrir(self):
        """Abre la conexión a la base de datos de forma segura."""
        try:
            conexion = mysql.connector.connect(**self.config)
            return conexion
        except mysql.connector.Error as err:
            if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
                logger.error("Usuario o contraseña de BD incorrectos.")
                raise Exception("Error de autenticación con la Base de Datos. Revise usuario y contraseña.")
            elif err.errno == errorcode.ER_BAD_DB_ERROR:
                logger.error("La base de datos no existe.")
                raise Exception("La Base de Datos especificada no existe.")
            else:
                # Mostramos el error técnico en la consola para depurar
                logger.error(f"Error de conexión detallado: {err}")
                
                # Mensaje amigable para el usuario
                if "SSL" in str(err):
                    raise Exception("Error de seguridad SSL. No se encuentra el certificado 'isrgrootx1.pem'.")
                else:
                    raise Exception("No se pudo conectar al servidor. Verifique su internet.")

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

    def obtener_partidos(self):
        """
        Obtiene la lista de partidos con todos sus datos para la gestión.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            # CAMBIO: Agregamos p.id, p.goles..., p.edicion_id al SELECT
            sql = """
            SELECT 
                p.id,
                p.rival,
                p.fecha_hora,
                CONCAT(c.nombre, ' ', a.numero) as torneo_completo,
                p.goles_independiente,
                p.goles_rival,
                p.edicion_id
            FROM partidos p
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
        Actualiza los datos de un partido existente.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            sql = """
                UPDATE partidos 
                SET rival = %s, fecha_hora = %s, goles_independiente = %s, goles_rival = %s, edicion_id = %s
                WHERE id = %s
            """
            valores = (rival, fecha_hora, goles_cai, goles_rival, edicion_id, id_partido)
            
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
        Inserta un nuevo partido.
        NOTA: Se usa edicion_id=1 por defecto al no haber selector en la UI.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            sql = """
                INSERT INTO partidos (rival, fecha_hora, goles_independiente, goles_rival, edicion_id)
                VALUES (%s, %s, %s, %s, %s)
            """
            valores = (rival, fecha_hora, goles_cai, goles_rival, edicion_id)
            
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
        """
        Verifica la contraseña usando Argon2.
        """
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
            raise Exception("Error al validar credenciales.")
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()