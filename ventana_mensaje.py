import flet as ft
from estilos import Estilos

class GestorMensajes:
    """Clase estática para mostrar mensajes modales con estilo del CAI"""

    @staticmethod
    def mostrar(page: ft.Page, titulo: str, mensaje: str, tipo: str = "info"):
        """
        Tipos: 'info', 'error', 'exito'
        """
        
        # --- 1. Definición de Iconos y Colores (Igual que antes) ---
        if tipo == "error":
            icono = "error_outline"
            color_icono = Estilos.COLOR_ROJO_CAI
            titulo_color = Estilos.COLOR_ROJO_CAI
        elif tipo == "exito":
            icono = "check_circle_outline"
            color_icono = "green" 
            titulo_color = Estilos.COLOR_BLANCO
        else:
            icono = "info_outline"
            color_icono = Estilos.COLOR_BLANCO
            titulo_color = Estilos.COLOR_BLANCO

        # Declaramos la variable 'dialogo' antes
        dialogo = None

        def cerrar_dialogo(e):
            if dialogo:
                page.close(dialogo)

        # --- 2. Crear el Botón (Lo definimos antes para usarlo en el contenido) ---
        boton = ft.ElevatedButton(
            text="Aceptar",
            style=ft.ButtonStyle(
                color=Estilos.COLOR_BLANCO,
                bgcolor=Estilos.COLOR_ROJO_CAI
            ),
            on_click=cerrar_dialogo
        )

        # --- 3. Creamos el contenido del diálogo (Estructura modificada) ---
        contenido = ft.Column(
            tight=True, # Se ajusta al contenido
            controls=[
                # Fila del Título e Icono
                ft.Row(
                    controls=[
                        ft.Icon(icono, color=color_icono, size=40),
                        ft.Text(titulo, size=20, weight=ft.FontWeight.BOLD, color=titulo_color)
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER
                ),
                ft.Divider(color="grey"),
                # Texto del mensaje
                ft.Text(mensaje, size=16, color=Estilos.COLOR_BLANCO),
                
                # Espaciador vertical
                ft.Container(height=20),
                
                # --- CAMBIO CLAVE: El botón ahora es parte del contenido ---
                # Lo metemos en una Row para alinearlo a la derecha
                ft.Row(
                    controls=[boton],
                    alignment=ft.MainAxisAlignment.END # Alineado a la derecha
                )
            ]
        )


        # --- 4. Crear el diálogo ---
        dialogo = ft.AlertDialog(
            modal=True,
            title_padding=0,
            content_padding=0, # Quitamos padding externo del contenido
            
            # El contenido principal es nuestro contenedor oscuro
            content=ft.Container(
                content=contenido,
                width=450, # Aumentamos un poco el ancho (antes 400)
                bgcolor="#2d2d2d", # Color de fondo del recuadro
                border_radius=15,
                padding=25 # Padding interno del recuadro
            ),
            
            # --- CAMBIO CLAVE: Eliminamos 'actions' y 'actions_alignment' ---
            # actions=[boton],  <-- ESTO SE ELIMINÓ
            
            bgcolor="transparent", # El fondo del diálogo nativo es transparente
        )

        page.open(dialogo)