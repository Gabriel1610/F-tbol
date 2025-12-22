import flet as ft
from estilos import Estilos
from base_de_datos import BaseDeDatos
from ventana_mensaje import GestorMensajes

class TarjetaAcceso(ft.Container):
    def __init__(self, page: ft.Page):
        super().__init__()
        self.page_principal = page
        
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
        self.user_reg = ft.TextField(
            label="Nombre de usuario", 
            on_change=self._validar_registro, 
            **Estilos.INPUT_CONFIG
        )
        self.pass_reg = ft.TextField(
            label="Contraseña", 
            password=True, 
            can_reveal_password=True, 
            disabled=True, 
            on_change=self._validar_registro,
            **Estilos.INPUT_CONFIG
        )
        self.pass_rep = ft.TextField(
            label="Repetir contraseña", 
            password=True, 
            disabled=True, 
            on_change=self._validar_registro,
            **Estilos.INPUT_CONFIG
        )
        
        sep = ft.Divider(height=40, thickness=2, color="white")

        # --- CAMPOS INGRESO ---
        self.user_ing = ft.TextField(
            label="Nombre de usuario", 
            on_change=self._validar_ingreso,
            **Estilos.INPUT_CONFIG
        )
        self.pass_ing = ft.TextField(
            label="Contraseña", 
            password=True, 
            can_reveal_password=True, 
            disabled=True, 
            on_change=self._validar_ingreso,
            **Estilos.INPUT_CONFIG
        )

        # --- BOTONES ---
        # CORRECCIÓN: Usamos diccionarios de estados para los colores
        
        # 1. Botón Registrarse (Borde)
        self.btn_reg = ft.OutlinedButton(
            text="Registrarse", 
            width=140, 
            disabled=True,
            style=ft.ButtonStyle(
                # Color del texto: Gris si disabled, Blanco si normal
                color={
                    ft.ControlState.DISABLED: "grey",
                    ft.ControlState.DEFAULT: Estilos.COLOR_BLANCO
                },
                # Borde: Gris si disabled, Blanco si normal
                side={
                    ft.ControlState.DISABLED: ft.BorderSide(2, "grey"),
                    ft.ControlState.DEFAULT: ft.BorderSide(2, Estilos.COLOR_BLANCO)
                }
            ), 
            on_click=self._registrar
        )
        
        # 2. Botón Ingresar (Relleno)
        self.btn_ing = ft.ElevatedButton(
            text="Ingresar", 
            width=140, 
            disabled=True,
            style=ft.ButtonStyle(
                # Color de fondo: Gris si disabled, Blanco si normal
                bgcolor={
                    ft.ControlState.DISABLED: "grey",
                    ft.ControlState.DEFAULT: Estilos.COLOR_BLANCO
                },
                # Color del texto: Negro si disabled (para contraste), Rojo si normal
                color={
                    ft.ControlState.DISABLED: "black",
                    ft.ControlState.DEFAULT: Estilos.COLOR_ROJO_CAI
                }
            ),
            on_click=self._ingresar
        )

        row_btns = ft.Row([self.btn_reg, self.btn_ing], alignment=ft.MainAxisAlignment.CENTER, spacing=20)

        self.content = ft.Column(
            controls=[
                ft.Container(content=t_reg, alignment=ft.alignment.center),
                self.user_reg, self.pass_reg, self.pass_rep,
                sep,
                ft.Container(content=t_ing, alignment=ft.alignment.center),
                self.user_ing, self.pass_ing,
                ft.Container(height=20),
                row_btns
            ],
            spacing=15
        )

    # --- LÓGICA DE VALIDACIÓN EN CASCADA (REGISTRO) ---
    def _validar_registro(self, e):
        # 1. Usuario -> Pass 1
        if not self.user_reg.value:
            self.pass_reg.value = ""
            self.pass_reg.disabled = True
            self.pass_rep.value = ""
            self.pass_rep.disabled = True
            self.btn_reg.disabled = True
        else:
            self.pass_reg.disabled = False

        # 2. Pass 1 -> Pass 2
        if not self.pass_reg.value or self.pass_reg.disabled:
            self.pass_rep.value = ""
            self.pass_rep.disabled = True
            self.btn_reg.disabled = True
        else:
            self.pass_rep.disabled = False

        # 3. Pass 2 -> Botón
        if self.pass_rep.value and not self.pass_rep.disabled:
            self.btn_reg.disabled = False
        else:
            self.btn_reg.disabled = True

        self.update()

    # --- LÓGICA DE VALIDACIÓN EN CASCADA (INGRESO) ---
    def _validar_ingreso(self, e):
        # 1. Usuario -> Pass
        if not self.user_ing.value:
            self.pass_ing.value = ""
            self.pass_ing.disabled = True
            self.btn_ing.disabled = True
        else:
            self.pass_ing.disabled = False

        # 2. Pass -> Botón
        if self.pass_ing.value and not self.pass_ing.disabled:
            self.btn_ing.disabled = False
        else:
            self.btn_ing.disabled = True

        self.update()

    def _registrar(self, e):
        usuario = self.user_reg.value.strip()
        contra1 = self.pass_reg.value
        contra2 = self.pass_rep.value
        
        if not usuario or not contra1 or not contra2:
            return 

        if contra1 != contra2:
            mensaje_error = (
                "Las contraseñas no coinciden.\n\n"
                "Recuerde que el sistema distingue entre mayúsculas y minúsculas."
            )
            GestorMensajes.mostrar(self.page_principal, "Error de Contraseña", mensaje_error, "error")
            return

        try:
            self.db.insertar_usuario(usuario, contra1)
            GestorMensajes.mostrar(self.page_principal, "Registro Exitoso", f"Usuario {usuario} creado.", "exito")
            
            # Reset
            self.user_reg.value = ""
            self._validar_registro(None)
            
        except Exception as error:
            GestorMensajes.mostrar(self.page_principal, "Error de Registro", str(error), "error")

    def _ingresar(self, e):
        usuario = self.user_ing.value.strip()
        password = self.pass_ing.value
        
        if not usuario or not password:
             return

        try:
            exito = self.db.validar_usuario(usuario, password)
            if exito:
                GestorMensajes.mostrar(self.page_principal, "Bienvenido", f"Hola {usuario}, acceso concedido.", "exito")
            else:
                GestorMensajes.mostrar(self.page_principal, "Acceso Denegado", "Usuario o contraseña incorrectos.", "error")
        except Exception as error:
             GestorMensajes.mostrar(self.page_principal, "Error de Sistema", str(error), "error")