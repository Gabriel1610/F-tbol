import flet as ft
import os
import threading
from tarjeta_acceso import TarjetaAcceso
from estilos import Estilos
from base_de_datos import BaseDeDatos

# Constantes
NOMBRE_ICONO = "Escudo.ico"

class SistemaIndependiente:
    def __init__(self, page: ft.Page):
        self.page = page
        self._configurar_ventana()
        self._construir_interfaz_login()

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

    # --- PANTALLA 1: LOGIN ---
    def _construir_interfaz_login(self):
        self.page.appbar = None
        
        self.tarjeta = TarjetaAcceso(self.page, on_login_success=self._ir_a_menu_principal)

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
    
    # --- PANTALLA 2: MENÚ PRINCIPAL ---
    def _ir_a_menu_principal(self, usuario):
        self.page.controls.clear()
        self.page.bgcolor = Estilos.COLOR_ROJO_CAI
        
        # Barra Superior
        self.page.appbar = ft.AppBar(
            leading=ft.Icon(ft.Icons.SECURITY, color=Estilos.COLOR_ROJO_CAI),
            leading_width=40,
            title=ft.Text(f"Bienvenido {usuario}", weight=ft.FontWeight.BOLD, color=Estilos.COLOR_ROJO_CAI),
            center_title=False,
            bgcolor="white", 
            actions=[
                ft.IconButton(
                    icon=ft.Icons.LOGOUT, 
                    tooltip="Cerrar Sesión", 
                    icon_color=Estilos.COLOR_ROJO_CAI,
                    on_click=self._cerrar_sesion
                ),
                ft.Container(width=10)
            ]
        )

        # --- DEFINICIÓN DE LA TABLA ---
        self.tabla_estadisticas = ft.DataTable(
            width=600, # <--- AGREGA ESTO: Limita el ancho total para que no se estire
            bgcolor="#2D2D2D",
            border=ft.border.all(1, "white10"),
            border_radius=8,
            vertical_lines=ft.border.BorderSide(1, "white10"),
            horizontal_lines=ft.border.BorderSide(1, "white10"),
            heading_row_color="black",
            heading_row_height=70,
            data_row_max_height=60,
            column_spacing=15, 
            columns=[
                # Col 0: Puesto
                ft.DataColumn(ft.Text("Puesto", color="white", weight=ft.FontWeight.BOLD), numeric=True),
                
                # Col 1: Usuario 
                ft.DataColumn(
                    ft.Container(
                        content=ft.Text("Usuario", color="white", weight=ft.FontWeight.BOLD),
                        width=80, # <--- CAMBIA ESTO: De 100 a 80
                        alignment=ft.alignment.center_left
                    )
                ),
                
                # Resto de columnas...
                ft.DataColumn(ft.Text("Puntos\nTotales", color="yellow", weight=ft.FontWeight.BOLD), numeric=True),
                ft.DataColumn(ft.Text("Pts.\nGanador", color="white"), numeric=True),
                ft.DataColumn(ft.Text("Pts.\nGoles CAI", color="white"), numeric=True),
                ft.DataColumn(ft.Text("Pts.\nGoles Rival", color="white"), numeric=True),
            ],
            rows=[] 
        )

        self.loading = ft.ProgressBar(width=400, color="amber", bgcolor="#222222", visible=True)

        # Definimos las pestañas
        lista_pestanas = [
            ft.Tab(
                text="Estadísticas",
                icon="bar_chart",
                content=ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text("Tabla de Posiciones", size=28, weight=ft.FontWeight.BOLD, color="white"),
                            self.loading,
                            self.tabla_estadisticas,
                        ],
                        scroll=ft.ScrollMode.AUTO,
                        horizontal_alignment=ft.CrossAxisAlignment.START, 
                    ),
                    padding=20,
                    alignment=ft.alignment.top_left 
                )
            ),
            
            ft.Tab(
                text="Configuración",
                icon="settings",
                content=ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Icon(name="settings_applications", size=80, color="white"),
                            ft.Text("Configuración", size=30, color="white"),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    alignment=ft.alignment.center
                )
            ),
        ]

        if usuario == "Gabriel":
            lista_pestanas.append(
                ft.Tab(
                    text="Administración",
                    icon="admin_panel_settings",
                    content=ft.Container(
                        content=ft.Column(
                            controls=[
                                ft.Icon(name="gavel", size=80, color="white"),
                                ft.Text("Panel Admin", size=30, color="white"),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        alignment=ft.alignment.center
                    )
                )
            )

        mis_pestanas = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            expand=True, 
            indicator_color="white", 
            label_color="white",
            unselected_label_color="white54",
            divider_color="white",
            tabs=lista_pestanas 
        )

        self.page.add(mis_pestanas)
        
        # Lanzar hilo de carga
        hilo_carga = threading.Thread(target=self._cargar_datos_async, daemon=True)
        hilo_carga.start()

    def _cargar_datos_async(self):
        try:
            bd = BaseDeDatos()
            datos_ranking = bd.obtener_ranking()

            filas_tabla = []
            
            for i, fila in enumerate(datos_ranking, start=1):
                filas_tabla.append(
                    ft.DataRow(
                        cells=[
                            # Puesto
                            ft.DataCell(ft.Text(f"{i}º", weight=ft.FontWeight.BOLD, color="white")), 
                            
                            # Usuario:
                            ft.DataCell(
                                ft.Container(
                                    content=ft.Text(str(fila[0]), weight=ft.FontWeight.BOLD, color="white", no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS),
                                    width=100, # Debe coincidir con el ancho del encabezado
                                    alignment=ft.alignment.center_left
                                )
                            ), 
                            
                            # Datos numéricos
                            ft.DataCell(ft.Text(str(fila[1]), weight=ft.FontWeight.BOLD, color="yellow", size=16)), 
                            ft.DataCell(ft.Text(str(fila[2]), color="white70")), 
                            ft.DataCell(ft.Text(str(fila[3]), color="white70")), 
                            ft.DataCell(ft.Text(str(fila[4]), color="white70")), 
                        ]
                    )
                )
            
            self.tabla_estadisticas.rows = filas_tabla
            self.loading.visible = False
            self.page.update()
            
        except Exception as e:
            print(f"Error cargando datos en segundo plano: {e}")
            self.loading.visible = False
            self.page.update()

    def _cerrar_sesion(self, e):
        self.page.controls.clear()
        self.page.bgcolor = "#121212" 
        self._construir_interfaz_login()
        self.page.update()

if __name__ == "__main__":
    def main(page: ft.Page):
        app = SistemaIndependiente(page)
    
    ft.app(target=main)