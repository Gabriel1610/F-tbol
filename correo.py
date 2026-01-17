import smtplib
import ssl
from email.message import EmailMessage
import random
import threading

class GestorCorreo:
    def __init__(self):
        # TUS CREDENCIALES
        self.email_emisor = "gabrielydeindependiente@gmail.com"  # Tu correo de Gmail
        # Aquí pega la contraseña de aplicación de 16 letras que generaste en la captura
        self.email_password = "vjpz rjcz nkgq zqaq" 
        
    def generar_codigo(self):
        """Genera un código numérico de 6 dígitos."""
        return str(random.randint(100000, 999999))

    def enviar_codigo_recuperacion(self, email_destino, codigo):
        """Envía el correo saltando la verificación estricta de SSL."""
        def _enviar():
            try:
                msg = EmailMessage()
                msg['Subject'] = "Recuperación de Contraseña - Club A. Independiente"
                msg['From'] = self.email_emisor
                msg['To'] = email_destino
                
                cuerpo = f"""
                Hola,
                
                Has solicitado restablecer tu contraseña.
                Tu código de verificación es: {codigo}
                
                Este código expira en 15 minutos.
                Si no fuiste tú, ignora este mensaje.
                """
                msg.set_content(cuerpo)

                # --- CORRECCIÓN SSL ---
                # Creamos un contexto que ignora errores de certificado (útil para evitar bloqueos de Antivirus)
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE

                # Usamos ese contexto "permisivo"
                with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context) as smtp:
                    smtp.login(self.email_emisor, self.email_password)
                    smtp.send_message(msg)
                
                print(f"Correo enviado exitosamente a {email_destino}")
                
            except Exception as e:
                print(f"Error enviando correo: {e}")
                # Opcional: Podrías guardar este error en un log si lo tuvieras

        threading.Thread(target=_enviar, daemon=True).start()