import mysql.connector
import logging
import hashlib
from mysql.connector import errorcode

# Configuración del Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseDeDatos:
    def __init__(self):
        # Configuración para TiDB Cloud (Extraída de tus capturas)
        self.config = {
            'user': '3XY8PLHt12tsDbZ.root',       # Tu usuario del Cluster0
            'password': 'TU_CONTRASEÑA_AQUI',     # <--- Escribe aquí tu contraseña real
            'host': 'gateway01.us-east-1.prod.aws.tidbcloud.com', # Host de AWS
            'port': 4000,                         # TiDB usa el puerto 4000 (no el 3306)
            'database': 'independiente',          # Nombre de la BD según tu captura
            'raise_on_warnings': True,
            
            # --- SEGURIDAD SSL (OBLIGATORIO) ---
            # TiDB requiere conexión segura. Asegúrate de tener el archivo .pem 
            # descargado en la misma carpeta del proyecto.
            'ssl_ca': 'isrgrootx1.pem',           
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
                raise Exception("Error de autenticación con la Base de Datos.")
            elif err.errno == errorcode.ER_BAD_DB_ERROR:
                logger.error("La base de datos no existe.")
                raise Exception("La Base de Datos especificada no existe.")
            else:
                logger.error(f"Error de conexión: {err}")
                raise Exception("No se pudo conectar al servidor de Base de Datos. Verifique su conexión.")

    def insertar_usuario(self, username, password):
        """
        Inserta un nuevo usuario en la tabla.
        Retorna True si fue exitoso.
        Lanza excepciones específicas si falla.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            # 1. Hashear la contraseña (Seguridad básica)
            # Usamos SHA-256 para no guardar texto plano
            password_hash = hashlib.sha256(password.encode()).hexdigest()

            sql = "INSERT INTO usuarios (username, password) VALUES (%s, %s)"
            valores = (username, password_hash)

            cursor.execute(sql, valores)
            conexion.commit()
            
            logger.info(f"Usuario '{username}' registrado exitosamente.")
            return True

        except mysql.connector.IntegrityError as err:
            # Capturamos error de duplicados (username UNIQUE)
            if err.errno == 1062: # Código de error para Duplicate Entry
                logger.warning(f"Intento de registro duplicado para: {username}")
                raise Exception("El nombre de usuario ya existe. Por favor elija otro.")
            else:
                raise Exception(f"Error de integridad en datos: {err}")

        except mysql.connector.Error as err:
            logger.error(f"Error de base de datos: {err}")
            raise Exception("Ocurrió un error interno al intentar guardar los datos.")
            
        except Exception as e:
            # Re-lanzar la excepción genérica (conexión, etc) para que la UI la capture
            raise e
            
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def validar_usuario(self, username, password):
        """Función extra para el Login (Ingreso)"""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor(dictionary=True)
            
            sql = "SELECT password FROM usuarios WHERE username = %s"
            cursor.execute(sql, (username,))
            usuario = cursor.fetchone()
            
            if usuario:
                hash_ingresado = hashlib.sha256(password.encode()).hexdigest()
                if hash_ingresado == usuario['password']:
                    return True
            return False
            
        except Exception as e:
            logger.error(f"Error validando usuario: {e}")
            raise Exception("Error al validar credenciales.")
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()