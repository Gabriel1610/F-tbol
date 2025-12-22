import flet as ft
from estilos import Estilos

class GestorMensajes:
    """Clase estática para mostrar mensajes modales con estilo del CAI"""

    @staticmethod
    def mostrar(page: ft.Page, titulo: str, mensaje: str, tipo: str = "info"):
        """
        Tipos: 'info', 'error', 'exito'
        """
        
        # Definir iconos y colores según el tipo
        if tipo == "error":
            icono = ft.icons.ERROR_OUTLINE
            color_icono = Estilos.COLOR_ROJO_CAI
            titulo_color = Estilos.COLOR_ROJO_CAI
        elif tipo == "exito":
            icono = ft.icons.CHECK_CIRCLE_OUTLINE
            color_icono = "green" # Verde para éxito, aunque no sea CAI, es estándar visual
            titulo_color = Estilos.COLOR_BLANCO
        else:
            icono = ft.icons.INFO_OUTLINE
            color_icono = Estilos.COLOR_BLANCO
            titulo_color = Estilos.COLOR_BLANCO

        # Creamos el contenido del diálogo
        contenido = ft.Column(
            tight=True,
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(icono, color=color_icono, size=40),
                        ft.Text(titulo, size=20, weight=ft.FontWeight.BOLD, color=titulo_color)
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER
                ),
                ft.Divider(color="grey"),
                ft.Text(mensaje, size=16, color=Estilos.COLOR_BLANCO)
            ]
        )

        def cerrar_dialogo(e):
            dialogo.open = False
            page.update()

        # Botón de acción
        boton = ft.ElevatedButton(
            text="Aceptar",
            style=ft.ButtonStyle(
                color=Estilos.COLOR_BLANCO,
                bgcolor=Estilos.COLOR_ROJO_CAI
            ),
            on_click=cerrar_dialogo
        )

        # Crear el diálogo
        dialogo = ft.AlertDialog(
            modal=True,
            title_padding=0,
            content_padding=20,
            content=ft.Container(
                content=contenido,
                width=400,
                # Usamos un gris muy oscuro (casi negro) para el fondo del popup
                bgcolor="#2d2d2d", 
                border_radius=10,
                padding=10
            ),
            actions=[boton],
            actions_alignment=ft.MainAxisAlignment.END,
            bgcolor=ft.colors.TRANSPARENT, # Hacemos transparente el fondo nativo para usar nuestro Container
        )

        page.dialog = dialogo
        dialogo.open = True
        page.update()