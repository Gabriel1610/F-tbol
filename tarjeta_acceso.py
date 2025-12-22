import flet as ft
import time # Importamos time para dar un micro respiro a la UI
from estilos import Estilos
from base_de_datos import BaseDeDatos
from ventana_mensaje import GestorMensajes
from ventana_carga import VentanaCarga # <--- IMPORTAMOS LA NUEVA CLASE

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
        self.btn_reg = ft.OutlinedButton(
            text="Registrarse", 
            width=140, 
            disabled=True,
            style=ft.ButtonStyle(
                color={
                    ft.ControlState.DISABLED: "grey",
                    ft.ControlState.DEFAULT: Estilos.COLOR_BLANCO
                },
                side={
                    ft.ControlState.DISABLED: ft.BorderSide(2, "grey"),
                    ft.ControlState.DEFAULT: ft.BorderSide(2, Estilos.COLOR_BLANCO)
                }
            ), 
            on_click=self._registrar
        )
        
        self.btn_ing = ft.ElevatedButton(
            text="Ingresar", 
            width=140, 
            disabled=True,
            style=ft.ButtonStyle(
                bgcolor={
                    ft.ControlState.DISABLED: "grey",
                    ft.ControlState.DEFAULT: Estilos.COLOR_BLANCO
                },
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

    # --- VALIDACIONES (Sin cambios) ---
    def _validar_registro(self, e):
        if not self.user_reg.value:
            self.pass_reg.value = ""
            self.pass_reg.disabled = True
            self.pass_rep.value = ""
            self.pass_rep.disabled = True
            self.btn_reg.disabled = True
        else:
            self.pass_reg.disabled = False

        if not self.pass_reg.value or self.pass_reg.disabled:
            self.pass_rep.value = ""
            self.pass_rep.disabled = True
            self.btn_reg.disabled = True
        else:
            self.pass_rep.disabled = False

        if self.pass_rep.value and not self.pass_rep.disabled:
            self.btn_reg.disabled = False
        else:
            self.btn_reg.disabled = True
        self.update()

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
        usuario = self.user_ing.value.strip()
        password = self.pass_ing.value
        
        if not usuario or not password: return

        try:
            # 1. MOSTRAR CARGA
            VentanaCarga.mostrar(self.page_principal, "Iniciando sesión...")
            time.sleep(0.1)

            # 2. OPERACIÓN PESADA
            exito = self.db.validar_usuario(usuario, password)
            
            # IMPORTANTE: Cerramos la carga ANTES de cambiar de pantalla o mostrar error
            VentanaCarga.cerrar(self.page_principal) 

            if exito:
                if self.on_login_success:
                    self.on_login_success(usuario)
            else:
                GestorMensajes.mostrar(self.page_principal, "Acceso Denegado", "Usuario o contraseña incorrectos.", "error")
        
        except Exception as error:
            # Si hubo error, nos aseguramos de cerrar la carga también
            VentanaCarga.cerrar(self.page_principal)
            GestorMensajes.mostrar(self.page_principal, "Error de Sistema", str(error), "error")