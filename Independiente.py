import flet as ft
import os
import time
import threading
from tarjeta_acceso import TarjetaAcceso
from estilos import Estilos
from base_de_datos import BaseDeDatos
from datetime import datetime, timedelta
from ventana_mensaje import GestorMensajes

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
    
    # --- FUNCIONES ABM PARTIDOS ---

    def _limpiar_formulario_partido(self, e=None):
        """Limpia los campos y la selección de partido"""
        self.input_rival.value = ""
        self.input_goles_cai.value = ""
        self.input_goles_rival.value = ""
        self.txt_fecha_display.value = "---"
        self.txt_hora_display.value = "---"
        self.date_picker.value = None
        self.time_picker.value = None
        
        if self.fila_partido_ref:
            self.fila_partido_ref.selected = False
            self.fila_partido_ref.color = None
            try: self.fila_partido_ref.update()
            except: pass
            
        self.fila_partido_ref = None
        self.partido_seleccionado_id = None
        
        self.page.update()

    def _seleccionar_partido(self, e):
        """Carga los datos del partido seleccionado en el formulario"""
        fila = e.control
        
        # Gestión visual
        if self.fila_partido_ref and self.fila_partido_ref != fila:
            self.fila_partido_ref.selected = False
            self.fila_partido_ref.color = None
            try: self.fila_partido_ref.update()
            except: pass

        fila.selected = True
        fila.color = ft.colors.with_opacity(0.5, Estilos.COLOR_ROJO_CAI)
        
        self.fila_partido_ref = fila
        
        # Recuperamos el diccionario con TODOS los datos del partido (lo guardamos en data)
        datos = fila.data # {id, rival, fecha, goles_cai, goles_rival, edicion_id}
        self.partido_seleccionado_id = datos['id']
        
        # Cargar formulario
        self.input_rival.value = datos['rival']
        
        if datos['fecha']:
            self.date_picker.value = datos['fecha'] # Guardamos el objeto datetime real
            self.time_picker.value = datos['fecha'].time()
            self.txt_fecha_display.value = datos['fecha'].strftime("%d/%m/%Y")
            self.txt_hora_display.value = datos['fecha'].strftime("%H:%M")
        
        # Goles (pueden ser None)
        self.input_goles_cai.value = str(datos['goles_cai']) if datos['goles_cai'] is not None else ""
        self.input_goles_rival.value = str(datos['goles_rival']) if datos['goles_rival'] is not None else ""
        
        # Nota: Idealmente deberíamos autoseleccionar el torneo en la otra tabla, 
        # pero para mantenerlo simple, solo exigiremos seleccionar torneo al guardar.
        
        self.page.update()

    def _editar_partido(self, e):
        """Hilo para editar partido"""
        def _tarea():
            if not self.partido_seleccionado_id:
                GestorMensajes.mostrar(self.page, "Atención", "Seleccione un partido para editar.", "error")
                return
            
            if not self.edicion_seleccionada_id:
                GestorMensajes.mostrar(self.page, "Atención", "Debe seleccionar la Edición del Torneo (tabla inferior) a la que pertenece este partido.", "error")
                return

            rival = self.input_rival.value.strip()
            fecha = self.date_picker.value
            hora = self.time_picker.value
            gc_str = self.input_goles_cai.value.strip()
            gr_str = self.input_goles_rival.value.strip()

            if not rival or not fecha or not hora:
                GestorMensajes.mostrar(self.page, "Error", "Complete rival, fecha y hora.", "error")
                return

            fecha_hora = datetime.combine(fecha, hora)
            gc = int(gc_str) if gc_str else None
            gr = int(gr_str) if gr_str else None

            try:
                bd = BaseDeDatos()
                bd.editar_partido(self.partido_seleccionado_id, rival, fecha_hora, gc, gr, self.edicion_seleccionada_id)
                GestorMensajes.mostrar(self.page, "Éxito", "Partido modificado.", "exito")
                self._limpiar_formulario_partido()
                self._cargar_datos_async()
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", str(ex), "error")

        threading.Thread(target=_tarea, daemon=True).start()

    def _eliminar_partido(self, e):
        """Hilo para eliminar partido"""
        def _tarea():
            if not self.partido_seleccionado_id:
                GestorMensajes.mostrar(self.page, "Atención", "Seleccione un partido para eliminar.", "error")
                return

            try:
                bd = BaseDeDatos()
                bd.eliminar_partido(self.partido_seleccionado_id)
                GestorMensajes.mostrar(self.page, "Éxito", "Partido eliminado.", "exito")
                self._limpiar_formulario_partido()
                self._cargar_datos_async()
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", str(ex), "error")

        threading.Thread(target=_tarea, daemon=True).start()

    # --- PANTALLA 2: MENÚ PRINCIPAL ---
    def _ir_a_menu_principal(self, usuario):
        self.page.controls.clear()
        self.page.bgcolor = Estilos.COLOR_ROJO_CAI
        
        # Variables de estado para Torneos
        self.edicion_seleccionada_id = None
        self.fila_seleccionada_ref = None
        
        # Variables de estado para Partidos (NUEVAS)
        self.partido_seleccionado_id = None
        self.fila_partido_ref = None
        
        # Inicializar Selectores
        self.date_picker = ft.DatePicker(on_change=self._fecha_cambiada, confirm_text="Seleccionar", cancel_text="Cancelar")
        self.time_picker = ft.TimePicker(on_change=self._hora_cambiada, confirm_text="Seleccionar", cancel_text="Cancelar")
        self.page.overlay.extend([self.date_picker, self.time_picker])

        # Barra Superior
        self.page.appbar = ft.AppBar(
            leading=ft.Icon(ft.Icons.SECURITY, color=Estilos.COLOR_ROJO_CAI),
            leading_width=40,
            title=ft.Text(f"Bienvenido {usuario}", weight=ft.FontWeight.BOLD, color=Estilos.COLOR_ROJO_CAI),
            center_title=False, bgcolor="white", 
            actions=[ft.IconButton(icon=ft.Icons.LOGOUT, tooltip="Cerrar Sesión", icon_color=Estilos.COLOR_ROJO_CAI, on_click=self._cerrar_sesion), ft.Container(width=10)]
        )

        # --- TABLAS (Estadísticas, Partidos, Admin Partidos, Torneos) ---
        self.tabla_estadisticas = ft.DataTable(width=600, bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=8, vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_color="black", heading_row_height=70, data_row_max_height=60, column_spacing=15, columns=[ft.DataColumn(ft.Text("Puesto", color="white", weight=ft.FontWeight.BOLD), numeric=True), ft.DataColumn(ft.Container(content=ft.Text("Usuario", color="white", weight=ft.FontWeight.BOLD), width=80, alignment=ft.alignment.center_left)), ft.DataColumn(ft.Text("Puntos\nTotales", color="yellow", weight=ft.FontWeight.BOLD), numeric=True), ft.DataColumn(ft.Text("Pts.\nGanador", color="white"), numeric=True), ft.DataColumn(ft.Text("Pts.\nGoles CAI", color="white"), numeric=True), ft.DataColumn(ft.Text("Pts.\nGoles Rival", color="white"), numeric=True)], rows=[])
        
        self.tabla_partidos = ft.DataTable(width=450, bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=8, vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_color="black", heading_row_height=70, data_row_max_height=60, column_spacing=20, columns=[ft.DataColumn(ft.Container(content=ft.Text("Vs (Rival)", color="white", weight=ft.FontWeight.BOLD), width=100, alignment=ft.alignment.center_left)), ft.DataColumn(ft.Container(content=ft.Text("Fecha y Hora", color="white", weight=ft.FontWeight.BOLD), width=140, alignment=ft.alignment.center_left)), ft.DataColumn(ft.Container(content=ft.Text("Torneo", color="yellow", weight=ft.FontWeight.BOLD), width=150, alignment=ft.alignment.center_left))], rows=[])
        
        # TABLA ADMIN PARTIDOS (Configurada para selección)
        self.tabla_partidos_admin = ft.DataTable(
            width=450, bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=8, 
            vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), 
            heading_row_color="black", heading_row_height=70, data_row_max_height=60, column_spacing=20, 
            show_checkbox_column=False, # Selección por fila
            columns=[
                ft.DataColumn(ft.Container(content=ft.Text("Vs (Rival)", color="white", weight=ft.FontWeight.BOLD), width=100, alignment=ft.alignment.center_left)), 
                ft.DataColumn(ft.Container(content=ft.Text("Fecha y Hora", color="white", weight=ft.FontWeight.BOLD), width=140, alignment=ft.alignment.center_left)), 
                ft.DataColumn(ft.Container(content=ft.Text("Torneo", color="yellow", weight=ft.FontWeight.BOLD), width=150, alignment=ft.alignment.center_left))
            ], rows=[])
        
        self.tabla_torneos = ft.DataTable(
            width=450, bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=8,
            vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"),
            heading_row_color="black", heading_row_height=60, data_row_max_height=50, column_spacing=20,
            show_checkbox_column=False, 
            columns=[
                ft.DataColumn(ft.Container(content=ft.Text("Nombre", color="white", weight=ft.FontWeight.BOLD), width=250, alignment=ft.alignment.center_left)),
                ft.DataColumn(ft.Container(content=ft.Text("Año", color="yellow", weight=ft.FontWeight.BOLD), width=80, alignment=ft.alignment.center_left), numeric=True)
            ], rows=[])

        self.loading = ft.ProgressBar(width=400, color="amber", bgcolor="#222222", visible=True)

        # --- CONTROLES FORMULARIO ---
        self.input_rival = ft.TextField(hint_text="Ej: Racing Club", width=200, height=40, text_size=14, content_padding=10, bgcolor="#2D2D2D", border_color="white24", color="white")
        self.txt_fecha_display = ft.Text("---", color="white70", size=13)
        self.txt_hora_display = ft.Text("---", color="white70", size=13)
        self.input_goles_cai = ft.TextField(width=60, height=40, content_padding=10, bgcolor="#2D2D2D", border_color="white24", color="white", keyboard_type=ft.KeyboardType.NUMBER, input_filter=ft.InputFilter(allow=True, regex_string=r"[0-9]", replacement_string=""))
        self.input_goles_rival = ft.TextField(width=60, height=40, content_padding=10, bgcolor="#2D2D2D", border_color="white24", color="white", keyboard_type=ft.KeyboardType.NUMBER, input_filter=ft.InputFilter(allow=True, regex_string=r"[0-9]", replacement_string=""))

        self.input_torneo_nombre = ft.TextField(hint_text="Nombre Torneo", width=180, height=40, text_size=14, content_padding=10, bgcolor="#2D2D2D", border_color="white24", color="white")
        hoy = datetime.now()
        anios_disponibles = sorted(list({(hoy - timedelta(days=30)).year, (hoy + timedelta(days=30)).year}))
        self.dd_torneo_anio = ft.Dropdown(width=120, content_padding=5, text_size=14, bgcolor="#2D2D2D", border_color="white24", color="white", options=[ft.dropdown.Option(str(a)) for a in anios_disponibles])
        if len(anios_disponibles) == 1: self.dd_torneo_anio.value = str(anios_disponibles[0])

        # --- PESTAÑAS ---
        lista_pestanas = [
            ft.Tab(text="Estadísticas", icon="bar_chart", content=ft.Container(content=ft.Column(controls=[ft.Text("Tabla de Posiciones", size=28, weight=ft.FontWeight.BOLD, color="white"), self.loading, self.tabla_estadisticas], scroll=ft.ScrollMode.AUTO, horizontal_alignment=ft.CrossAxisAlignment.START), padding=20, alignment=ft.alignment.top_left)),
            ft.Tab(text="Partidos", icon="sports_soccer", content=ft.Container(content=ft.Column(controls=[ft.Text("Partidos", size=28, weight=ft.FontWeight.BOLD, color="white"), self.tabla_partidos], scroll=ft.ScrollMode.AUTO, horizontal_alignment=ft.CrossAxisAlignment.START), padding=20, alignment=ft.alignment.top_left)),
            ft.Tab(text="Configuración", icon="settings", content=ft.Container(content=ft.Column(controls=[ft.Icon(name="settings_applications", size=80, color="white"), ft.Text("Configuración", size=30, color="white")], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER), alignment=ft.alignment.center))
        ]

        if usuario == "Gabriel":
            lista_pestanas.append(
                ft.Tab(
                    text="Administración",
                    icon="admin_panel_settings",
                    content=ft.Container(
                        padding=0, alignment=ft.alignment.top_left,
                        content=ft.Column(
                            scroll=ft.ScrollMode.AUTO, 
                            controls=[
                                ft.Container(
                                    padding=20,
                                    content=ft.Row(
                                        vertical_alignment=ft.CrossAxisAlignment.START,
                                        controls=[
                                            # COLUMNA IZQUIERDA
                                            ft.Column(
                                                controls=[
                                                    ft.Text("Partidos Registrados", size=20, weight=ft.FontWeight.BOLD, color="white"),
                                                    ft.Container(content=ft.Column(controls=[self.tabla_partidos_admin], scroll=ft.ScrollMode.ALWAYS), height=350, width=480),
                                                    ft.Container(height=20),
                                                    ft.Text("Torneos Registrados", size=20, weight=ft.FontWeight.BOLD, color="white"),
                                                    ft.Container(content=ft.Column(controls=[self.tabla_torneos], scroll=ft.ScrollMode.ALWAYS), height=300, width=480)
                                                ]
                                            ),
                                            ft.Container(width=30), 

                                            # COLUMNA DERECHA: FORMULARIOS
                                            ft.Column(
                                                controls=[
                                                    # FORM 1: PARTIDOS (BOTONERA ACTUALIZADA)
                                                    ft.Container(
                                                        width=350, padding=20, border=ft.border.all(1, "white24"), border_radius=10, bgcolor="#1E1E1E",
                                                        content=ft.Column(tight=True, spacing=15, controls=[
                                                            ft.Text("Agregar / Editar Partido", size=18, weight=ft.FontWeight.BOLD, color="white"),
                                                            ft.Divider(color="white24"),
                                                            ft.Text("1. Seleccione un Torneo en la tabla inferior", size=12, italic=True, color="yellow"),
                                                            ft.Row(controls=[ft.Text("Rival:", width=60, color="white", weight=ft.FontWeight.BOLD), self.input_rival], alignment=ft.MainAxisAlignment.START),
                                                            ft.Row(controls=[ft.Text("Fecha:", width=50, color="white", weight=ft.FontWeight.BOLD), ft.IconButton(icon=ft.Icons.CALENDAR_MONTH, icon_color="yellow", tooltip="Elegir Fecha", on_click=lambda _: self.page.open(self.date_picker)), self.txt_fecha_display, ft.Container(width=10), ft.Text("Hora:", width=45, color="white", weight=ft.FontWeight.BOLD), ft.IconButton(icon=ft.Icons.ACCESS_TIME, icon_color="yellow", tooltip="Elegir Hora", on_click=lambda _: self.page.open(self.time_picker)), self.txt_hora_display], alignment=ft.MainAxisAlignment.START),
                                                            ft.Row(controls=[ft.Text("Goles CAI:", width=80, color="white", weight=ft.FontWeight.BOLD), self.input_goles_cai]),
                                                            ft.Row(controls=[ft.Text("Goles Rival:", width=80, color="white", weight=ft.FontWeight.BOLD), self.input_goles_rival]),
                                                            ft.Container(height=10),
                                                            
                                                            # BOTONERA PARTIDOS
                                                            ft.Row(
                                                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                                                controls=[
                                                                    ft.IconButton(icon=ft.Icons.ADD_CIRCLE, icon_color="green", tooltip="Agregar Partido", on_click=self._agregar_partido, icon_size=40),
                                                                    ft.Row(spacing=5, controls=[
                                                                        ft.IconButton(icon=ft.Icons.EDIT, icon_color="blue", tooltip="Editar Partido", on_click=self._editar_partido),
                                                                        ft.IconButton(icon=ft.Icons.DELETE, icon_color="red", tooltip="Eliminar Partido", on_click=self._eliminar_partido),
                                                                        ft.IconButton(icon=ft.Icons.CLEANING_SERVICES, icon_color="grey", tooltip="Limpiar Formulario", on_click=self._limpiar_formulario_partido),
                                                                    ])
                                                                ]
                                                            )
                                                        ])
                                                    ),
                                                    ft.Container(height=20),

                                                    # FORM 2: TORNEOS
                                                    ft.Container(
                                                        width=350, padding=20, border=ft.border.all(1, "white24"), border_radius=10, bgcolor="#1E1E1E",
                                                        content=ft.Column(tight=True, spacing=15, controls=[
                                                            ft.Text("Gestión de Torneos", size=18, weight=ft.FontWeight.BOLD, color="white"),
                                                            ft.Divider(color="white24"),
                                                            ft.Row(controls=[self.input_torneo_nombre, self.dd_torneo_anio], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                                                            ft.Container(height=10),
                                                            ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[
                                                                ft.IconButton(icon=ft.Icons.ADD_CIRCLE, icon_color="green", tooltip="Agregar Nuevo", on_click=self._agregar_torneo, icon_size=40),
                                                                ft.Row(spacing=5, controls=[
                                                                    ft.IconButton(icon=ft.Icons.EDIT, icon_color="blue", tooltip="Editar Seleccionado", on_click=self._editar_torneo),
                                                                    ft.IconButton(icon=ft.Icons.DELETE, icon_color="red", tooltip="Eliminar Seleccionado", on_click=self._eliminar_torneo),
                                                                    ft.IconButton(icon=ft.Icons.CLEANING_SERVICES, icon_color="grey", tooltip="Limpiar Formulario", on_click=self._limpiar_formulario_torneo),
                                                                ])
                                                            ])
                                                        ])
                                                    )
                                                ]
                                            )
                                        ]
                                    )
                                )
                            ]
                        )
                    )
                )
            )

        mis_pestanas = ft.Tabs(selected_index=0, animation_duration=300, expand=True, indicator_color="white", label_color="white", unselected_label_color="white54", divider_color="white", tabs=lista_pestanas)
        self.page.add(mis_pestanas)
        
        self._cargar_datos_async()

    # --- FUNCIONES ABM TORNEOS ---
    
    def _limpiar_formulario_torneo(self, e=None):
        """Limpia inputs, deselecciona la fila y resetea variables"""
        self.input_torneo_nombre.value = ""
        # Reseteamos el dropdown (opcional: dejarlo en el primero o vacío)
        if self.dd_torneo_anio.options:
             self.dd_torneo_anio.value = self.dd_torneo_anio.options[0].key
             
        # Deselección visual de la tabla
        if self.fila_seleccionada_ref:
            self.fila_seleccionada_ref.selected = False
            self.fila_seleccionada_ref.color = None
            try:
                self.fila_seleccionada_ref.update()
            except: pass
            
        self.fila_seleccionada_ref = None
        self.edicion_seleccionada_id = None
        
        self.page.update()

    def _agregar_torneo(self, e):
        """Hilo para crear torneo"""
        def _tarea():
            nombre = self.input_torneo_nombre.value.strip()
            anio_str = self.dd_torneo_anio.value

            if not nombre or not anio_str:
                GestorMensajes.mostrar(self.page, "Atención", "Complete nombre y año.", "error")
                return
            
            try:
                bd = BaseDeDatos()
                bd.crear_torneo(nombre, int(anio_str))
                GestorMensajes.mostrar(self.page, "Éxito", "Torneo creado.", "exito")
                self._limpiar_formulario_torneo() # Limpia al terminar
                self._cargar_datos_async()
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", str(ex), "error")

        threading.Thread(target=_tarea, daemon=True).start()

    def _editar_torneo(self, e):
        """Hilo para editar torneo seleccionado"""
        def _tarea():
            if not self.edicion_seleccionada_id:
                GestorMensajes.mostrar(self.page, "Atención", "Seleccione un torneo de la tabla para editar.", "error")
                return

            nombre = self.input_torneo_nombre.value.strip()
            anio_str = self.dd_torneo_anio.value
            
            if not nombre or not anio_str:
                 GestorMensajes.mostrar(self.page, "Error", "Complete todos los campos.", "error")
                 return

            try:
                bd = BaseDeDatos()
                bd.editar_torneo(self.edicion_seleccionada_id, nombre, int(anio_str))
                GestorMensajes.mostrar(self.page, "Éxito", "Torneo modificado.", "exito")
                self._limpiar_formulario_torneo()
                self._cargar_datos_async()
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", str(ex), "error")
        
        threading.Thread(target=_tarea, daemon=True).start()

    def _eliminar_torneo(self, e):
        """Hilo para eliminar torneo seleccionado"""
        def _tarea():
            if not self.edicion_seleccionada_id:
                GestorMensajes.mostrar(self.page, "Atención", "Seleccione un torneo para eliminar.", "error")
                return

            try:
                bd = BaseDeDatos()
                bd.eliminar_torneo(self.edicion_seleccionada_id)
                GestorMensajes.mostrar(self.page, "Éxito", "Torneo eliminado.", "exito")
                self._limpiar_formulario_torneo()
                self._cargar_datos_async()
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", str(ex), "error")
        
        threading.Thread(target=_tarea, daemon=True).start()

    def _agregar_partido(self, e):
        """Valida y agrega un partido a la base de datos en un hilo secundario"""
        
        def _tarea_agregar_partido():
            # 0. VALIDACIÓN: Verificar que haya seleccionado un torneo
            # Usamos self.edicion_seleccionada_id para mantener la coherencia con la tabla de torneos
            if not self.edicion_seleccionada_id:
                GestorMensajes.mostrar(self.page, "Atención", "Debe seleccionar un Torneo de la tabla 'Torneos Registrados'.", "error")
                return

            # 1. Obtener datos de los controles
            rival = self.input_rival.value.strip()
            fecha = self.date_picker.value 
            hora = self.time_picker.value  
            
            goles_cai_str = self.input_goles_cai.value.strip()
            goles_rival_str = self.input_goles_rival.value.strip()

            # 2. Validaciones Básicas
            if not rival:
                GestorMensajes.mostrar(self.page, "Atención", "Debe ingresar el nombre del rival.", "error")
                return
            
            if not fecha or not hora:
                GestorMensajes.mostrar(self.page, "Atención", "Debe seleccionar la fecha y la hora del partido.", "error")
                return

            fecha_hora_partido = datetime.combine(fecha, hora)
            ahora = datetime.now()
            
            bd = BaseDeDatos()

            # 3. Validar duplicados en la misma fecha
            if bd.existe_partido_fecha(fecha.date()):
                GestorMensajes.mostrar(self.page, "Error", "Ya existe un partido registrado en esa fecha.", "error")
                return

            # 4. Lógica de Goles
            goles_cai = None
            goles_rival = None

            if fecha_hora_partido < ahora:
                # Partido Pasado: Goles obligatorios
                if not goles_cai_str or not goles_rival_str:
                    GestorMensajes.mostrar(self.page, "Faltan Resultados", "Al ser un partido pasado, es obligatorio ingresar los goles.", "error")
                    return
                try:
                    goles_cai = int(goles_cai_str)
                    goles_rival = int(goles_rival_str)
                except ValueError:
                    GestorMensajes.mostrar(self.page, "Error", "Los goles deben ser números enteros.", "error")
                    return
            else:
                # Partido Futuro: Goles opcionales
                if goles_cai_str and goles_rival_str:
                    try:
                        goles_cai = int(goles_cai_str)
                        goles_rival = int(goles_rival_str)
                    except ValueError:
                        GestorMensajes.mostrar(self.page, "Error", "Los goles deben ser números enteros.", "error")
                        return
                elif goles_cai_str or goles_rival_str:
                    GestorMensajes.mostrar(self.page, "Error", "Si ingresa goles, debe completar ambos campos.", "error")
                    return

            # 5. Insertar en Base de Datos
            try:
                # Pasamos el ID del torneo seleccionado (self.edicion_seleccionada_id)
                bd.insertar_partido(
                    rival, 
                    fecha_hora_partido, 
                    goles_cai, 
                    goles_rival, 
                    edicion_id=self.edicion_seleccionada_id 
                )
                
                GestorMensajes.mostrar(self.page, "Éxito", "Partido agregado correctamente.", "exito")
                
                # Limpiar campos
                self.input_rival.value = ""
                self.input_goles_cai.value = ""
                self.input_goles_rival.value = ""
                self.txt_fecha_display.value = "---"
                self.txt_hora_display.value = "---"
                self.date_picker.value = None
                self.time_picker.value = None
                
                self.page.update()
                self._cargar_datos_async()

            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", f"Ocurrió un error al guardar: {ex}", "error")

        # Lanzamos el hilo
        threading.Thread(target=_tarea_agregar_partido, daemon=True).start()

    def _fecha_cambiada(self, e):
        """Actualiza el texto con la fecha seleccionada"""
        if self.date_picker.value:
            self.txt_fecha_display.value = self.date_picker.value.strftime("%d/%m/%Y")
            self.page.update()

    def _hora_cambiada(self, e):
        """Actualiza el texto con la hora seleccionada"""
        if self.time_picker.value:
            # TimePicker devuelve objeto time, formateamos a HH:MM
            self.txt_hora_display.value = self.time_picker.value.strftime("%H:%M")
            self.page.update()

    def _seleccionar_torneo(self, e):
        fila_cliqueada = e.control
        
        # 1. Gestión visual (apagar anterior, encender nueva)
        if self.fila_seleccionada_ref and self.fila_seleccionada_ref != fila_cliqueada:
            self.fila_seleccionada_ref.selected = False
            self.fila_seleccionada_ref.color = None 
            try: self.fila_seleccionada_ref.update()
            except: pass

        fila_cliqueada.selected = True
        fila_cliqueada.color = ft.Colors.with_opacity(0.5, Estilos.COLOR_ROJO_CAI)
        
        self.fila_seleccionada_ref = fila_cliqueada
        self.edicion_seleccionada_id = fila_cliqueada.data

        # --- NUEVO: CARGAR DATOS AL FORMULARIO ---
        # Celda 0 es un Container -> Content -> Text
        nombre_torneo = fila_cliqueada.cells[0].content.content.value 
        # Celda 1 es un Text directo (según tu última definición corregida)
        anio_torneo = fila_cliqueada.cells[1].content.value

        self.input_torneo_nombre.value = nombre_torneo
        self.dd_torneo_anio.value = str(anio_torneo)
        
        self.page.update()

    def _cargar_datos_async(self):
        def _tarea_en_segundo_plano():
            time.sleep(0.5) 
            
            # Limpiamos referencias
            self.fila_seleccionada_ref = None
            self.edicion_seleccionada_id = None
            self.fila_partido_ref = None
            self.partido_seleccionado_id = None

            try:
                bd = BaseDeDatos()
                datos_ranking = bd.obtener_ranking()
                datos_partidos = bd.obtener_partidos()
                datos_ediciones = bd.obtener_ediciones()

                # --- RANKING (Igual) ---
                filas_tabla_ranking = []
                for i, fila in enumerate(datos_ranking, start=1):
                    filas_tabla_ranking.append(ft.DataRow(cells=[ft.DataCell(ft.Text(f"{i}º", weight=ft.FontWeight.BOLD, color="white")), ft.DataCell(ft.Container(content=ft.Text(str(fila[0]), weight=ft.FontWeight.BOLD, color="white", no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS), width=80, alignment=ft.alignment.center_left)), ft.DataCell(ft.Text(str(fila[1]), weight=ft.FontWeight.BOLD, color="yellow", size=16)), ft.DataCell(ft.Text(str(fila[2]), color="white70")), ft.DataCell(ft.Text(str(fila[3]), color="white70")), ft.DataCell(ft.Text(str(fila[4]), color="white70"))]))

                # --- PARTIDOS ---
                filas_tabla_partidos = []
                filas_tabla_admin = [] 
                
                for fila in datos_partidos:
                    # fila ahora trae: (id, rival, fecha, torneo, goles_cai, goles_rival, edicion_id)
                    p_id = fila[0]
                    rival = fila[1]
                    fecha_obj = fila[2]
                    torneo = fila[3]
                    gc = fila[4]
                    gr = fila[5]
                    ed_id = fila[6]
                    
                    fecha_str = fecha_obj.strftime("%d/%m/%Y %H:%M") if fecha_obj else "Sin fecha"

                    # 1. Tabla Usuario (Solo lectura)
                    filas_tabla_partidos.append(ft.DataRow(cells=[ft.DataCell(ft.Container(content=ft.Text(str(rival), weight=ft.FontWeight.BOLD, color="white", no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS), width=100, alignment=ft.alignment.center_left)), ft.DataCell(ft.Text(fecha_str, color="white70")), ft.DataCell(ft.Container(content=ft.Text(str(torneo), color="yellow", weight=ft.FontWeight.BOLD), width=150, alignment=ft.alignment.center_left))]))
                    
                    # 2. Tabla Admin (Con datos ocultos para editar)
                    filas_tabla_admin.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(content=ft.Text(str(rival), weight=ft.FontWeight.BOLD, color="white", no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS), width=100, alignment=ft.alignment.center_left)), 
                                ft.DataCell(ft.Text(fecha_str, color="white70")), 
                                ft.DataCell(ft.Container(content=ft.Text(str(torneo), color="yellow", weight=ft.FontWeight.BOLD), width=150, alignment=ft.alignment.center_left))
                            ],
                            # Guardamos TODOS los datos necesarios para editar en un diccionario
                            data={
                                'id': p_id,
                                'rival': rival,
                                'fecha': fecha_obj,
                                'goles_cai': gc,
                                'goles_rival': gr,
                                'edicion_id': ed_id
                            },
                            on_select_changed=self._seleccionar_partido,
                            selected=False
                        )
                    )

                # --- TORNEOS (Igual) ---
                filas_torneos = []
                for ed in datos_ediciones:
                    ed_id = ed[0]
                    nombre = ed[1]
                    anio = ed[2]
                    filas_torneos.append(ft.DataRow(cells=[ft.DataCell(ft.Container(content=ft.Text(str(nombre), color="white", weight=ft.FontWeight.BOLD), width=250, alignment=ft.alignment.center_left)), ft.DataCell(ft.Text(str(anio), color="yellow", weight=ft.FontWeight.BOLD))], data=ed_id, on_select_changed=self._seleccionar_torneo, selected=False))

                self.tabla_estadisticas.rows = filas_tabla_ranking
                self.tabla_partidos.rows = filas_tabla_partidos
                self.tabla_partidos_admin.rows = filas_tabla_admin
                self.tabla_torneos.rows = filas_torneos
                
                self.loading.visible = False
                self.page.update()
                
            except Exception as e:
                print(f"Error cargando datos en segundo plano: {e}")
                self.loading.visible = False
                self.page.update()

        threading.Thread(target=_tarea_en_segundo_plano, daemon=True).start()

    def _cerrar_sesion(self, e):
        self.page.controls.clear()
        self.page.bgcolor = "#121212" 
        self._construir_interfaz_login()
        self.page.update()

if __name__ == "__main__":
    def main(page: ft.Page):
        app = SistemaIndependiente(page)
    
    ft.app(target=main)