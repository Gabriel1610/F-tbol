import mysql.connector
import logging
from mysql.connector import errorcode
# Importamos Argon2 para el hashing moderno
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# Configuración del Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseDeDatos:
    def __init__(self):
        # Inicializamos el Hasher de Argon2
        # time_cost, memory_cost y parallelism se configuran por defecto a valores seguros
        self.ph = PasswordHasher()

        # Configuración para TiDB Cloud
        self.config = {
            'user': '3XY8PLHt12tsDbZ.root',       
            'password': 'TU_CONTRASEÑA_AQUI',     # <--- RECUERDA PONER TU CLAVE DE TiDB
            'host': 'gateway01.us-east-1.prod.aws.tidbcloud.com', 
            'port': 4000,                         
            'database': 'independiente',          
            'raise_on_warnings': True,
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
                raise Exception("No se pudo conectar al servidor de Base de Datos.")

    def insertar_usuario(self, username, password):
        """
        Hashea la contraseña con Argon2 antes de guardarla.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            # --- HASHING MODERNO (Argon2) ---
            # Esto genera un string que incluye el algoritmo, el costo, la sal y el hash.
            # Ejemplo: $argon2id$v=19$m=65536,t=3,p=4$KBd...$d9...
            password_hash = self.ph.hash(password)

            sql = "INSERT INTO usuarios (username, password) VALUES (%s, %s)"
            valores = (username, password_hash)

            cursor.execute(sql, valores)
            conexion.commit()
            
            logger.info(f"Usuario '{username}' registrado exitosamente.")
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

    def validar_usuario(self, username, password):
        """
        Verifica la contraseña usando Argon2.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor(dictionary=True)
            
            # Obtenemos el hash guardado (que ya incluye la sal)
            sql = "SELECT password FROM usuarios WHERE username = %s"
            cursor.execute(sql, (username,))
            usuario = cursor.fetchone()
            
            if usuario:
                hash_guardado = usuario['password']
                try:
                    # Argon2 verifica si el password coincide con el hash guardado
                    # Si coincide, devuelve True (o el hash si es necesario actualizarlo)
                    # Si NO coincide, lanza una excepción VerifyMismatchError
                    self.ph.verify(hash_guardado, password)
                    return True
                except VerifyMismatchError:
                    # La contraseña es incorrecta
                    return False
            
            # Si no se encuentra el usuario
            return False
            
        except Exception as e:
            logger.error(f"Error validando usuario: {e}")
            raise Exception("Error al validar credenciales.")
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()