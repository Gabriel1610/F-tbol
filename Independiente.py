import flet as ft
import os
from tarjeta_acceso import TarjetaAcceso

# Constantes
NOMBRE_ICONO = "Escudo.ico"

class SistemaIndependiente:
    def __init__(self, page: ft.Page):
        self.page = page
        self._configurar_ventana()
        self._construir_interfaz()

    def _configurar_ventana(self):
        self.page.title = "Sistema Club Atlético Independiente"
        
        carpeta_actual = os.path.dirname(os.path.abspath(__file__))
        ruta_icono = os.path.join(carpeta_actual, NOMBRE_ICONO)
        self.page.window.icon = ruta_icono
        
        self.page.theme_mode = ft.ThemeMode.DARK 
        self.page.bgcolor = "#121212" 
        self.page.padding = 0
        
        self.page.window.maximized = True
        self.page.update()
        
        self.page.vertical_alignment = ft.MainAxisAlignment.CENTER
        self.page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    def _construir_interfaz(self):
        # --- AQUÍ ESTÁ EL CAMBIO ---
        # Le pasamos 'self.page' a la tarjeta para que pueda mostrar alertas
        self.tarjeta = TarjetaAcceso(self.page)

        self.btn_salir = ft.IconButton(
            icon="close",
            icon_color="white",
            bgcolor="#333333", 
            on_click=lambda e: self.page.window.close()
        )

        layout = ft.Stack(
            controls=[
                self.tarjeta, 
                ft.Container(content=self.btn_salir, right=10, top=10)
            ],
            expand=True
        )

        self.page.add(layout)


if __name__ == "__main__":
    def main(page: ft.Page):
        app = SistemaIndependiente(page)
    
    ft.app(target=main)