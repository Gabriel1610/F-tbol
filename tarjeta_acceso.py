import flet as ft
import time
from estilos import Estilos
from base_de_datos import BaseDeDatos
import threading
from ventana_mensaje import GestorMensajes
from ventana_carga import VentanaCarga
from correo import GestorCorreo

class TarjetaAcceso(ft.Container):
    def __init__(self, page: ft.Page, on_login_success):
        super().__init__()
        self.page_principal = page
        self.on_login_success = on_login_success 
        
        self.width = 500
        self.padding = 40
        self.bgcolor = Estilos.COLOR_FONDO_CARD
        self.border_radius = 20
        self.border = ft.border.all(2, Estilos.COLOR_BLANCO)
        self.shadow = ft.BoxShadow(spread_radius=1, blur_radius=20, color="#80000000")
        
        self.db = BaseDeDatos()
        self._crear_contenido()

    def _crear_contenido(self):
        t_reg = ft.Text("NUEVO USUARIO", size=20, weight=ft.FontWeight.BOLD, color=Estilos.COLOR_BLANCO)
        t_ing = ft.Text("YA TENGO CUENTA", size=20, weight=ft.FontWeight.BOLD, color=Estilos.COLOR_BLANCO)

        # --- CAMPOS REGISTRO ---
        self.user_reg = ft.TextField(label="Nombre de usuario", on_change=self._validar_registro, **Estilos.INPUT_CONFIG)
        
        # NUEVO CAMPO EMAIL
        self.email_reg = ft.TextField(label="Correo Electrónico", on_change=self._validar_registro, **Estilos.INPUT_CONFIG)
        
        self.pass_reg = ft.TextField(label="Contraseña", password=True, can_reveal_password=True, disabled=True, on_change=self._validar_registro, **Estilos.INPUT_CONFIG)
        self.pass_rep = ft.TextField(label="Repetir contraseña", password=True, disabled=True, on_change=self._validar_registro, **Estilos.INPUT_CONFIG)
        
        sep = ft.Divider(height=40, thickness=2, color="white")

        # --- CAMPOS INGRESO ---
        self.user_ing = ft.TextField(label="Nombre de usuario o correo electrónico", on_change=self._validar_ingreso, **Estilos.INPUT_CONFIG)
        self.pass_ing = ft.TextField(label="Contraseña", password=True, can_reveal_password=True, disabled=True, on_change=self._validar_ingreso, **Estilos.INPUT_CONFIG)

        # NUEVO LINK RECUPERAR
        self.btn_olvide = ft.TextButton("¿Olvidaste tu contraseña?", style=ft.ButtonStyle(color="white70"), on_click=self._iniciar_flujo_recuperacion)

        # --- BOTONES ---
        self.btn_reg = ft.OutlinedButton(
            text="Verificar y Registrar", 
            width=220, # <--- CAMBIADO DE 160 A 220
            disabled=True,
            style=ft.ButtonStyle(color={ft.ControlState.DISABLED: "grey", ft.ControlState.DEFAULT: Estilos.COLOR_BLANCO}, side={ft.ControlState.DISABLED: ft.BorderSide(2, "grey"), ft.ControlState.DEFAULT: ft.BorderSide(2, Estilos.COLOR_BLANCO)}), 
            on_click=self._iniciar_proceso_registro 
        )
        
        self.btn_ing = ft.ElevatedButton(
            text="Ingresar", 
            width=140, 
            disabled=True,
            style=ft.ButtonStyle(bgcolor={ft.ControlState.DISABLED: "grey", ft.ControlState.DEFAULT: Estilos.COLOR_BLANCO}, color={ft.ControlState.DISABLED: "black", ft.ControlState.DEFAULT: Estilos.COLOR_ROJO_CAI}),
            on_click=self._ingresar
        )

        row_btns = ft.Row([self.btn_reg, self.btn_ing], alignment=ft.MainAxisAlignment.CENTER, spacing=20)

        self.content = ft.Column(
            controls=[
                ft.Container(content=t_reg, alignment=ft.alignment.center),
                self.user_reg, 
                self.email_reg, 
                self.pass_reg, self.pass_rep,
                sep,
                ft.Container(content=t_ing, alignment=ft.alignment.center),
                self.user_ing, self.pass_ing,
                ft.Container(content=self.btn_olvide, alignment=ft.alignment.center_right),
                ft.Container(height=10),
                row_btns
            ],
            spacing=15
        )

    # --- VALIDACIONES (Sin cambios) ---
    def _validar_registro(self, e):
        # Validar Usuario
        if not self.user_reg.value:
            self.email_reg.disabled = True
            self.email_reg.value = ""
            self._desactivar_todo_registro()
        else:
            self.email_reg.disabled = False

        # Validar Email (Simple check de contenido)
        if not self.email_reg.value or self.email_reg.disabled:
            self.pass_reg.disabled = True
            self.pass_reg.value = ""
        else:
            self.pass_reg.disabled = False
            
        # Validar Pass 1
        if not self.pass_reg.value or self.pass_reg.disabled:
            self.pass_rep.disabled = True
            self.pass_rep.value = ""
        else:
            self.pass_rep.disabled = False

        # Validar Pass 2 y Botón Final
        if self.pass_rep.value and not self.pass_rep.disabled:
            self.btn_reg.disabled = False
        else:
            self.btn_reg.disabled = True
        self.update()

    def _desactivar_todo_registro(self):
        """Helper para limpiar campos dependientes"""
        self.pass_reg.value = ""
        self.pass_reg.disabled = True
        self.pass_rep.value = ""
        self.pass_rep.disabled = True
        self.btn_reg.disabled = True

    def _iniciar_proceso_registro(self, e):
        """Paso 1: Valida disponibilidad, envía código y abre modal."""
        usuario = self.user_reg.value.strip()
        email = self.email_reg.value.strip()
        contra1 = self.pass_reg.value
        contra2 = self.pass_rep.value
        
        if contra1 != contra2:
            GestorMensajes.mostrar(self.page_principal, "Error", "Las contraseñas no coinciden.", "error")
            return
        
        if "@" not in email or "." not in email:
            GestorMensajes.mostrar(self.page_principal, "Error", "Formato de correo inválido.", "error")
            return

        # Función interna para proceso asíncrono
        def _proceso():
            try:
                VentanaCarga.mostrar(self.page_principal, "Verificando disponibilidad...")
                
                # 1. Verificar en BD si usuario/email están libres
                self.db.verificar_disponibilidad(usuario, email)
                
                # 2. Generar Código
                gestor = GestorCorreo()
                codigo = gestor.generar_codigo()
                
                # 3. Enviar Correo
                VentanaCarga.mostrar(self.page_principal, "Enviando código de verificación...")
                
                # --- CAMBIO AQUÍ: Usamos es_registro=True ---
                gestor.enviar_codigo(email, codigo, es_registro=True)
                
                VentanaCarga.cerrar(self.page_principal)
                
                # 4. Mostrar Modal para ingresar código
                # Pasamos los datos (user, pass, email, codigo_generado) al modal para usarlos si acierta
                self._mostrar_modal_codigo_registro(usuario, contra1, email, codigo)
                
            except Exception as ex:
                VentanaCarga.cerrar(self.page_principal)
                GestorMensajes.mostrar(self.page_principal, "Error", str(ex), "error")

        import threading
        threading.Thread(target=_proceso, daemon=True).start()

    def _mostrar_modal_codigo_registro(self, user, password, email, codigo_real):
        # Función interna para borrar el error apenas se escribe algo nuevo
        def _limpiar_error(e):
            if input_codigo.error_text:
                input_codigo.error_text = None
                input_codigo.update()

        input_codigo = ft.TextField(
            label="Código de 6 dígitos", 
            text_align="center", 
            max_length=6, 
            width=200,
            on_change=_limpiar_error 
        )
        
        def _verificar_y_guardar(e):
            codigo_ingresado = input_codigo.value
            # 1. Cerramos el modal de código temporalmente
            self.page_principal.close(dlg)

            def _proceso_verificacion():
                try:
                    # 2. Mostramos animación de carga
                    VentanaCarga.mostrar(self.page_principal, "Verificando código...")
                    time.sleep(1.0) # Pausa estética para que el usuario vea que se está procesando

                    # 3. Validamos
                    if codigo_ingresado == codigo_real:
                        VentanaCarga.cerrar(self.page_principal)
                        # Llamamos a la función final (que tiene su propia carga para la BD)
                        self._insertar_usuario_final(user, password, email)
                    else:
                        # Error: Cerramos carga y reabrimos el modal avisando el error
                        VentanaCarga.cerrar(self.page_principal)
                        GestorMensajes.mostrar(self.page_principal, "Error", "Código incorrecto", "error")
                        
                        input_codigo.value = codigo_ingresado # Mantenemos lo que escribió
                        input_codigo.error_text = "Código incorrecto"
                        self.page_principal.open(dlg)
                
                except Exception as ex:
                    VentanaCarga.cerrar(self.page_principal)
                    GestorMensajes.mostrar(self.page_principal, "Error de Sistema", str(ex), "error")
                    self.page_principal.open(dlg)

            # Ejecutamos en segundo plano para no congelar la ventana
            threading.Thread(target=_proceso_verificacion, daemon=True).start()

        dlg = ft.AlertDialog(
            title=ft.Text("Verificar Correo"),
            content=ft.Column([
                ft.Text(f"Hemos enviado un código a:\n{email}"),
                ft.Container(height=10),
                input_codigo
            ], height=120, tight=True),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self.page_principal.close(dlg)),
                ft.ElevatedButton("Verificar y Registrar", on_click=_verificar_y_guardar, bgcolor="green", color="white")
            ],
            modal=True
        )
        self.page_principal.open(dlg)

    def _insertar_usuario_final(self, user, password, email):
        try:
            VentanaCarga.mostrar(self.page_principal, "Finalizando registro...")
            self.db.insertar_usuario(user, password, email)
            VentanaCarga.cerrar(self.page_principal)
            
            GestorMensajes.mostrar(self.page_principal, "Éxito", f"Bienvenido {user}. Ya puedes ingresar.", "exito")
            # Limpiar campos
            self.user_reg.value = ""
            self.email_reg.value = ""
            self.pass_reg.value = ""
            self.pass_rep.value = ""
            self._validar_registro(None)
            
        except Exception as e:
            VentanaCarga.cerrar(self.page_principal)
            GestorMensajes.mostrar(self.page_principal, "Error Fatal", str(e), "error")
    
    def _iniciar_flujo_recuperacion(self, e):
        """Paso 1: Pedir Usuario"""
        input_user = ft.TextField(label="Tu nombre de usuario", width=250)
        
        def _buscar_email(e):
            username = input_user.value.strip()
            if not username: return
            self.page_principal.close(dlg_user)
            self._enviar_codigo_recuperacion(username)

        dlg_user = ft.AlertDialog(
            title=ft.Text("Recuperar Contraseña"),
            content=ft.Column([ft.Text("Ingresa tu nombre de usuario para buscar tu correo asociado."), input_user], tight=True, height=100),
            actions=[ft.ElevatedButton("Buscar", on_click=_buscar_email)]
        )
        self.page_principal.open(dlg_user)

    def _enviar_codigo_recuperacion(self, username):
        """Paso 2: Buscar Email, Generar Código y Guardar en BD"""
        def _proceso():
            try:
                VentanaCarga.mostrar(self.page_principal, "Buscando usuario...")
                email = self.db.obtener_email_usuario(username)
                
                if not email:
                    VentanaCarga.cerrar(self.page_principal)
                    GestorMensajes.mostrar(self.page_principal, "Error", "Usuario no encontrado o sin email registrado.", "error")
                    return

                # Generar y Guardar
                gestor = GestorCorreo()
                codigo = gestor.generar_codigo()
                
                # GUARDAMOS EL TOKEN EN LA BD
                self.db.guardar_token_recuperacion(username, codigo)
                
                # Enviar
                VentanaCarga.mostrar(self.page_principal, f"Enviando correo a {email[:3]}***...")
                
                # --- CAMBIO AQUÍ: Usamos es_registro=False ---
                # Antes decía: gestor.enviar_codigo_recuperacion(email, codigo)
                gestor.enviar_codigo(email, codigo, es_registro=False)
                
                VentanaCarga.cerrar(self.page_principal)
                
                # Ir al paso 3
                self._pedir_codigo_recuperacion(username, email)
                
            except Exception as ex:
                VentanaCarga.cerrar(self.page_principal)
                GestorMensajes.mostrar(self.page_principal, "Error", str(ex), "error")

        import threading
        threading.Thread(target=_proceso, daemon=True).start()

    def _pedir_codigo_recuperacion(self, username, email):
        """Paso 3: Validar código ingresado contra la BD con animación de carga"""
        
        def _limpiar_error(e):
            if input_code.error_text:
                input_code.error_text = None
                input_code.update()

        input_code = ft.TextField(
            label="Código", 
            text_align="center", 
            max_length=6,
            on_change=_limpiar_error
        )
        
        def _validar(e):
            codigo_ingresado = input_code.value
            # 1. Cerramos el modal de código
            self.page_principal.close(dlg_code)

            def _proceso_validacion():
                try:
                    # 2. Animación de carga
                    VentanaCarga.mostrar(self.page_principal, "Verificando...")
                    time.sleep(1.0) # Pausa estética

                    # 3. Validación contra Base de Datos
                    self.db.validar_token_recuperacion(username, codigo_ingresado)
                    
                    # Si pasa (no lanza error):
                    VentanaCarga.cerrar(self.page_principal)
                    self._pedir_nueva_contrasena(username)
                    
                except Exception as ex:
                    # Si falla:
                    VentanaCarga.cerrar(self.page_principal)
                    GestorMensajes.mostrar(self.page_principal, "Error", str(ex), "error")
                    
                    # Reabrimos el modal para que intente de nuevo
                    input_code.value = codigo_ingresado
                    input_code.error_text = str(ex)
                    self.page_principal.open(dlg_code)

            threading.Thread(target=_proceso_validacion, daemon=True).start()

        dlg_code = ft.AlertDialog(
            title=ft.Text("Código de Verificación"),
            content=ft.Column([ft.Text(f"Ingresa el código enviado a {email}"), input_code], tight=True, height=120),
            actions=[ft.ElevatedButton("Verificar", on_click=_validar)]
        )
        self.page_principal.open(dlg_code)

    def _pedir_nueva_contrasena(self, username):
        """Paso 4: Cambiar la contraseña con animación de carga"""
        
        # Función interna para borrar el error apenas se escribe algo nuevo
        def _limpiar_error(e):
            if p1.error_text:
                p1.error_text = None
                p1.update()

        p1 = ft.TextField(
            label="Nueva contraseña", 
            password=True, 
            can_reveal_password=True,
            on_change=_limpiar_error # <--- AGREGADO: Limpia error al escribir
        )
        p2 = ft.TextField(
            label="Repetir contraseña", 
            password=True,
            on_change=_limpiar_error # <--- AGREGADO: Limpia error al escribir
        )
        
        def _cambiar(e):
            if not p1.value or p1.value != p2.value:
                p1.error_text = "No coinciden o está vacío"
                p1.update()
                return
            
            # Función para ejecutar en segundo plano
            def _proceso_cambio():
                try:
                    # 1. Mostrar animación
                    VentanaCarga.mostrar(self.page_principal, "Actualizando contraseña...")
                    time.sleep(1.0) # Pausa estética

                    # 2. Llamada a Base de Datos
                    self.db.cambiar_contrasena(username, p1.value)
                    
                    # 3. Éxito: Cerrar carga y modal
                    VentanaCarga.cerrar(self.page_principal)
                    self.page_principal.close(dlg_pass)
                    
                    GestorMensajes.mostrar(self.page_principal, "Éxito", "Contraseña actualizada. Ya puedes ingresar.", "exito")
                    
                except Exception as ex:
                    # Error: Cerrar carga y mostrar mensaje
                    VentanaCarga.cerrar(self.page_principal)
                    GestorMensajes.mostrar(self.page_principal, "Error", str(ex), "error")

            # Ejecutar el hilo
            threading.Thread(target=_proceso_cambio, daemon=True).start()

        dlg_pass = ft.AlertDialog(
            title=ft.Text("Restablecer Contraseña"),
            content=ft.Column([p1, p2], tight=True, height=150),
            actions=[ft.ElevatedButton("Cambiar Contraseña", on_click=_cambiar)]
        )
        self.page_principal.open(dlg_pass)

    def _validar_ingreso(self, e):
        if not self.user_ing.value:
            self.pass_ing.value = ""
            self.pass_ing.disabled = True
            self.btn_ing.disabled = True
        else:
            self.pass_ing.disabled = False

        if self.pass_ing.value and not self.pass_ing.disabled:
            self.btn_ing.disabled = False
        else:
            self.btn_ing.disabled = True
        self.update()

    # --- LOGICA CON VENTANA DE CARGA ---
    def _registrar(self, e):
        usuario = self.user_reg.value.strip()
        contra1 = self.pass_reg.value
        contra2 = self.pass_rep.value
        
        if not usuario or not contra1 or not contra2: return 

        if contra1 != contra2:
            mensaje = "Las contraseñas no coinciden.\nRecuerde distinguir mayúsculas y minúsculas."
            GestorMensajes.mostrar(self.page_principal, "Error de Contraseña", mensaje, "error")
            return

        try:
            # 1. MOSTRAR CARGA
            VentanaCarga.mostrar(self.page_principal, "Registrando usuario...")
            
            # Pequeña pausa técnica para asegurar que la ventana se dibuje antes de que la BD congele el proceso
            time.sleep(0.1) 

            # 2. OPERACIÓN PESADA
            self.db.insertar_usuario(usuario, contra1)
            
            # (El finally se encarga de cerrar la carga aquí)
            
            GestorMensajes.mostrar(self.page_principal, "Registro Exitoso", f"Usuario {usuario} creado.", "exito")
            self.user_reg.value = ""
            self._validar_registro(None)

        except Exception as error:
            GestorMensajes.mostrar(self.page_principal, "Error de Registro", str(error), "error")
        
        finally:
            # 3. CERRAR CARGA SIEMPRE (Haya error o no)
            VentanaCarga.cerrar(self.page_principal)

    def _ingresar(self, e):
        usuario_input = self.user_ing.value.strip()
        password = self.pass_ing.value
        
        if not usuario_input or not password: return

        try:
            # 1. MOSTRAR CARGA
            # El mensaje se mantendrá visible mientras se procesa todo
            VentanaCarga.mostrar(self.page_principal, "Iniciando sesión...")
            time.sleep(0.1)

            # 2. OPERACIÓN PESADA (Validar contra BD)
            nombre_real_usuario = self.db.validar_usuario(usuario_input, password)
            
            # 3. CAMBIO DE PANTALLA
            # Llamamos a la función de éxito MIENTRAS la ventana de carga sigue abierta.
            # Esto construirá el menú principal por detrás del mensaje de carga.
            if self.on_login_success:
                self.on_login_success(nombre_real_usuario)

            # 4. CERRAR CARGA
            # Recién ahora, cuando el menú ya está listo, quitamos el mensaje.
            VentanaCarga.cerrar(self.page_principal)
        
        except ValueError as ve:
            # Si hay error de validación, cerramos la carga para mostrar el mensaje
            VentanaCarga.cerrar(self.page_principal)
            GestorMensajes.mostrar(self.page_principal, "Advertencia", str(ve), "error")

        except Exception as error:
            # Si hay error técnico, cerramos la carga para mostrar el mensaje
            VentanaCarga.cerrar(self.page_principal)
            GestorMensajes.mostrar(self.page_principal, "Error de Sistema", f"Fallo técnico: {error}", "error")