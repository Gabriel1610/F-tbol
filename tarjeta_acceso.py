import flet as ft
from estilos import Estilos
from base_de_datos import BaseDeDatos
from ventana_mensaje import GestorMensajes

class TarjetaAcceso(ft.Container):
    def __init__(self):
        super().__init__()
        self.width = 500
        self.padding = 40
        self.bgcolor = Estilos.COLOR_FONDO_CARD
        self.border_radius = 20
        self.border = ft.border.all(2, Estilos.COLOR_BLANCO)
        self.shadow = ft.BoxShadow(spread_radius=1, blur_radius=20, color="#80000000")
        
        # Instanciamos la base de datos
        self.db = BaseDeDatos()
        
        self._crear_contenido()

    def _crear_contenido(self):
        t_reg = ft.Text("NUEVO USUARIO", size=20, weight=ft.FontWeight.BOLD, color=Estilos.COLOR_BLANCO)
        t_ing = ft.Text("YA TENGO CUENTA", size=20, weight=ft.FontWeight.BOLD, color=Estilos.COLOR_BLANCO)

        self.user_reg = ft.TextField(label="Nombre de usuario", **Estilos.INPUT_CONFIG)
        self.pass_reg = ft.TextField(label="Contraseña", password=True, can_reveal_password=True, **Estilos.INPUT_CONFIG)
        self.pass_rep = ft.TextField(label="Repetir contraseña", password=True, **Estilos.INPUT_CONFIG)
        
        sep = ft.Divider(height=40, thickness=2, color="white")

        self.user_ing = ft.TextField(label="Nombre de usuario", **Estilos.INPUT_CONFIG)
        self.pass_ing = ft.TextField(label="Contraseña", password=True, can_reveal_password=True, **Estilos.INPUT_CONFIG)

        btn_reg = ft.OutlinedButton(
            text="Registrarse", 
            width=140, 
            style=ft.ButtonStyle(color=Estilos.COLOR_BLANCO, side=ft.BorderSide(2, Estilos.COLOR_BLANCO)), 
            on_click=self._registrar
        )
        
        btn_ing = ft.ElevatedButton(
            text="Ingresar", 
            width=140, 
            bgcolor=Estilos.COLOR_BLANCO, 
            color=Estilos.COLOR_ROJO_CAI, 
            on_click=self._ingresar
        )

        row_btns = ft.Row([btn_reg, btn_ing], alignment=ft.MainAxisAlignment.CENTER, spacing=20)

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

    def _registrar(self, e):
        # 1. Obtener datos
        usuario = self.user_reg.value.strip()
        contra1 = self.pass_reg.value
        contra2 = self.pass_rep.value
        
        # 2. Validaciones básicas
        if not usuario or not contra1 or not contra2:
            GestorMensajes.mostrar(self.page, "Error de Datos", "Por favor, complete todos los campos de registro.", "error")
            return

        if contra1 != contra2:
            GestorMensajes.mostrar(self.page, "Contraseñas no coinciden", "Las contraseñas ingresadas no son iguales.", "error")
            return

        # 3. Intentar insertar en BD
        try:
            self.db.insertar_usuario(usuario, contra1)
            
            # Éxito
            GestorMensajes.mostrar(self.page, "Registro Exitoso", f"El usuario {usuario} ha sido creado correctamente.", "exito")
            
            # Limpiar campos
            self.user_reg.value = ""
            self.pass_reg.value = ""
            self.pass_rep.value = ""
            self.user_reg.update()
            self.pass_reg.update()
            self.pass_rep.update()
            
        except Exception as error:
            # Capturamos el error que viene de base_de_datos.py
            mensaje_error = str(error)
            GestorMensajes.mostrar(self.page, "Error de Registro", mensaje_error, "error")

    def _ingresar(self, e):
        usuario = self.user_ing.value.strip()
        password = self.pass_ing.value
        
        if not usuario or not password:
             GestorMensajes.mostrar(self.page, "Datos Incompletos", "Ingrese usuario y contraseña.", "error")
             return

        try:
            exito = self.db.validar_usuario(usuario, password)
            if exito:
                GestorMensajes.mostrar(self.page, "Bienvenido", f"Hola {usuario}, has ingresado al sistema.", "exito")
                # Aquí podrías cambiar de página o cerrar la ventana de login
            else:
                GestorMensajes.mostrar(self.page, "Acceso Denegado", "Usuario o contraseña incorrectos.", "error")
        except Exception as error:
             GestorMensajes.mostrar(self.page, "Error de Sistema", str(error), "error")