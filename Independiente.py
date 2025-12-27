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
        
        self._actualizar_estado_goles() 
        
        if self.fila_partido_ref:
            self.fila_partido_ref.selected = False
            self.fila_partido_ref.color = None
            try: self.fila_partido_ref.update()
            except: pass
            
        self.fila_partido_ref = None
        self.partido_seleccionado_id = None # Partido deseleccionado
        
        # --- LÓGICA ETIQUETA ---
        # No hay partido seleccionado -> etiqueta oculta
        self.txt_instruccion.visible = False
        
        self.page.update()

    def _actualizar_estado_goles(self):
        """
        Habilita o deshabilita los inputs de goles según la fecha y hora.
        Reglas: Deshabilitar si es futuro, si no tiene fecha/hora, o si la hora es 00:00.
        """
        deshabilitar = False
        
        fecha = self.date_picker.value
        hora = self.time_picker.value
        
        # 1. Sin fecha seleccionada
        if not fecha:
            deshabilitar = True
        
        # 2. Sin horario (texto '---') o hora 00:00:00
        elif self.txt_hora_display.value == "---" or (hora and hora.hour == 0 and hora.minute == 0):
            deshabilitar = True
            
        # 3. Fecha en el futuro
        else:
            # Combinamos para comparar con ahora
            # Si hora es None (caso raro si pasó el check de '---'), usamos min
            hora_ref = hora if hora else datetime.min.time()
            fecha_hora = datetime.combine(fecha, hora_ref)
            
            if fecha_hora > datetime.now():
                deshabilitar = True

        # Aplicar estado a los inputs
        self.input_goles_cai.disabled = deshabilitar
        self.input_goles_rival.disabled = deshabilitar
        
        # Si se deshabilitan, limpiamos los valores para evitar confusiones
        if deshabilitar:
            self.input_goles_cai.value = ""
            self.input_goles_rival.value = ""
            
        self.page.update()

    def _bloquear_ui_torneos(self, ocupado: bool):
        """Bloquea UI de torneos y setea SU bandera específica"""
        self.procesando_torneos = ocupado # <--- ÚNICA BANDERA QUE TOCAMOS AQUÍ
        
        # Inputs y Botones
        self.input_torneo_nombre.disabled = ocupado
        self.dd_torneo_anio.disabled = ocupado
        self.btn_add_torneo.disabled = ocupado
        self.btn_edit_torneo.disabled = ocupado
        self.btn_del_torneo.disabled = ocupado
        self.btn_clean_torneo.disabled = ocupado
        
        self.page.update()

    def _bloquear_ui_partidos(self, ocupado: bool):
        """Bloquea UI de partidos y setea SU bandera específica"""
        self.procesando_partidos = ocupado # <--- ÚNICA BANDERA QUE TOCAMOS AQUÍ
        
        # Inputs y Botones
        self.input_rival.disabled = ocupado
        self.input_goles_cai.disabled = ocupado
        self.input_goles_rival.disabled = ocupado
        self.btn_pick_date.disabled = ocupado
        self.btn_pick_time.disabled = ocupado
        self.btn_add_partido.disabled = ocupado
        self.btn_edit_partido.disabled = ocupado
        self.btn_del_partido.disabled = ocupado
        self.btn_clean_partido.disabled = ocupado
        
        self.page.update()

    def _toggle_ver_futuros(self, e):
        """Alterna entre ver todos los partidos o solo los futuros"""
        self.solo_futuros = not self.solo_futuros
        
        # Actualizamos el aspecto del botón según el estado
        if self.solo_futuros:
            self.btn_ver_futuros.text = "Ver Todos"
            self.btn_ver_futuros.bgcolor = "blue"
            self.btn_ver_futuros.icon = ft.Icons.LIST
        else:
            self.btn_ver_futuros.text = "Por jugar"
            self.btn_ver_futuros.bgcolor = "#333333"
            self.btn_ver_futuros.icon = ft.Icons.UPCOMING
            
        self.btn_ver_futuros.update()
        
        # Recargamos solo la tabla de partidos
        self._recargar_datos(actualizar_partidos=True)

    def _cambiar_filtro_tiempo(self, nuevo_filtro):
        """
        Gestiona el grupo de filtros de Tiempo (Todos, Futuros, Jugados).
        Estos son EXCLUYENTES entre sí.
        """
        self.filtro_pron_tiempo = nuevo_filtro
        
        # Actualizar colores botones del grupo tiempo
        self.btn_pron_todos.bgcolor = "blue" if nuevo_filtro == 'todos' else "#333333"
        self.btn_pron_por_jugar.bgcolor = "blue" if nuevo_filtro == 'futuros' else "#333333"
        self.btn_pron_jugados.bgcolor = "blue" if nuevo_filtro == 'jugados' else "#333333"
        
        self.btn_pron_todos.update()
        self.btn_pron_por_jugar.update()
        self.btn_pron_jugados.update()
        
        self._actualizar_titulo_pronosticos()
        self._recargar_datos(actualizar_pronosticos=True)

    def _gestionar_accion_boton_filtro(self, tipo):
        """
        Gestiona la lógica 'toggle' de los botones específicos (Torneo, Equipo, Usuario).
        - Si el filtro ya está activo -> Lo desactiva (limpia variable y botón negro).
        - Si no está activo -> Abre el modal para seleccionar.
        """
        if tipo == 'torneo':
            if self.filtro_pron_torneo is not None:
                # Desactivar
                self.filtro_pron_torneo = None
                self.btn_pron_por_torneo.bgcolor = "#333333"
                self.btn_pron_por_torneo.update()
                self._actualizar_titulo_pronosticos()
                self._recargar_datos(actualizar_pronosticos=True)
            else:
                # Abrir Modal
                self._abrir_selector_torneo_pronosticos(None)
                
        elif tipo == 'equipo':
            if self.filtro_pron_equipo is not None:
                # Desactivar
                self.filtro_pron_equipo = None
                self.btn_pron_por_equipo.bgcolor = "#333333"
                self.btn_pron_por_equipo.update()
                self._actualizar_titulo_pronosticos()
                self._recargar_datos(actualizar_pronosticos=True)
            else:
                # Abrir Modal
                self._abrir_selector_equipo_pronosticos(None)
                
        elif tipo == 'usuario':
            if self.filtro_pron_usuario is not None:
                # Desactivar
                self.filtro_pron_usuario = None
                self.btn_pron_por_usuario.bgcolor = "#333333"
                self.btn_pron_por_usuario.update()
                self._actualizar_titulo_pronosticos()
                self._recargar_datos(actualizar_pronosticos=True)
            else:
                # Abrir Modal
                self._abrir_selector_usuario_pronosticos(None)

    def _actualizar_titulo_pronosticos(self):
        """Construye el título dinámico basado en TODOS los filtros activos."""
        partes = []
        
        # Parte Tiempo
        if self.filtro_pron_tiempo == 'todos': partes.append("Todos")
        elif self.filtro_pron_tiempo == 'futuros': partes.append("Por Jugar")
        elif self.filtro_pron_tiempo == 'jugados': partes.append("Finalizados")
        
        # Partes Específicas
        detalles = []
        if self.filtro_pron_torneo: detalles.append(self.filtro_pron_torneo)
        if self.filtro_pron_equipo: detalles.append(f"vs {self.filtro_pron_equipo}")
        if self.filtro_pron_usuario: detalles.append(f"de {self.filtro_pron_usuario}")
        
        titulo = "Pronósticos: " + " - ".join(partes)
        if detalles:
            titulo += " (" + ", ".join(detalles) + ")"
            
        self.txt_titulo_pronosticos.value = titulo
        self.txt_titulo_pronosticos.update()

    # --- PANTALLA 2: MENÚ PRINCIPAL ---
    def _ir_a_menu_principal(self, usuario):
        self.page.controls.clear()
        self.page.bgcolor = Estilos.COLOR_ROJO_CAI
        
        self.usuario_actual = usuario
        
        # --- BANDERAS DE ESTADO ---
        self.cargando_partidos = False
        self.cargando_torneos = False
        self.procesando_partidos = False 
        self.procesando_torneos = False
        self.editando_torneo = False 
        
        # Variables de Ordenamiento
        self.pronosticos_sort_col_index = None
        self.pronosticos_sort_asc = True
        
        # Filtros Partidos
        self.filtro_partidos = 'futuros'
        self.filtro_edicion_id = None 
        self.filtro_rival_id = None 

        # --- VARIABLES DE FILTROS PRONÓSTICOS ---
        self.filtro_pron_tiempo = 'todos' 
        self.filtro_pron_torneo = None 
        self.filtro_pron_equipo = None 
        self.filtro_pron_usuario = None 
        
        # Variables para Modales
        self.cache_ediciones_modal = [] 
        self.cache_rivales_modal = [] 
        self.temp_campeonato_sel = None 
        self.temp_anio_sel = None
        self.temp_rival_sel_id = None 
        self.temp_rival_sel_nombre = None
        self.temp_usuario_sel = None
        
        # Variables de selección UI
        self.edicion_seleccionada_id = None
        self.fila_seleccionada_ref = None
        self.partido_seleccionado_id = None
        self.fila_partido_ref = None
        
        # Variable para selección de pronóstico
        self.partido_a_pronosticar_id = None
        self.fila_pronostico_ref = None
        
        # Inicializar Selectores
        self.date_picker = ft.DatePicker(on_change=self._fecha_cambiada, confirm_text="Seleccionar", cancel_text="Cancelar")
        self.time_picker = ft.TimePicker(on_change=self._hora_cambiada, confirm_text="Seleccionar", cancel_text="Cancelar")
        self.page.overlay.extend([self.date_picker, self.time_picker])

        self.page.appbar = ft.AppBar(
            leading=ft.Icon(ft.Icons.SECURITY, color=Estilos.COLOR_ROJO_CAI),
            leading_width=40,
            title=ft.Text(f"Bienvenido, {usuario}", weight=ft.FontWeight.BOLD, color=Estilos.COLOR_ROJO_CAI),
            center_title=False, bgcolor="white", 
            actions=[ft.IconButton(icon=ft.Icons.LOGOUT, tooltip="Cerrar Sesión", icon_color=Estilos.COLOR_ROJO_CAI, on_click=self._cerrar_sesion), ft.Container(width=10)]
        )

        # --- CONTROLES FORMULARIO PRONÓSTICOS ---
        self.input_pred_cai = ft.TextField(label="Goles CAI", width=80, text_align=ft.TextAlign.CENTER, keyboard_type=ft.KeyboardType.NUMBER, max_length=2, bgcolor="#2D2D2D", border_color="white24", color="white", on_change=self._validar_solo_numeros)
        self.input_pred_rival = ft.TextField(label="Goles Rival", width=110, text_align=ft.TextAlign.CENTER, keyboard_type=ft.KeyboardType.NUMBER, max_length=2, bgcolor="#2D2D2D", border_color="white24", color="white", on_change=self._validar_solo_numeros)
        self.btn_pronosticar = ft.ElevatedButton("Pronosticar", icon=ft.Icons.SPORTS_SOCCER, bgcolor="green", color="white", on_click=self._guardar_pronostico)

        # --- DEFINICIÓN DE COLUMNAS ---
        columnas_partidos = [ft.DataColumn(ft.Container(content=ft.Text("Vs (Rival)", color="white", weight=ft.FontWeight.BOLD), width=250, alignment=ft.alignment.center_left)), ft.DataColumn(ft.Container(content=ft.Text("Resultado", color="white", weight=ft.FontWeight.BOLD), width=80, alignment=ft.alignment.center)), ft.DataColumn(ft.Container(content=ft.Text("Fecha y Hora", color="white", weight=ft.FontWeight.BOLD), width=140, alignment=ft.alignment.center_left)), ft.DataColumn(ft.Container(content=ft.Text("Torneo", color="yellow", weight=ft.FontWeight.BOLD), width=150, alignment=ft.alignment.center_left)), ft.DataColumn(ft.Container(content=ft.Text("Tu pronóstico", color="cyan", weight=ft.FontWeight.BOLD), width=100, alignment=ft.alignment.center)), ft.DataColumn(ft.Container(content=ft.Text("Tus puntos", color="green", weight=ft.FontWeight.BOLD), width=80, alignment=ft.alignment.center))]

        columnas_pronosticos = [
            ft.DataColumn(ft.Container(content=ft.Text("Vs (Rival)", color="white", weight=ft.FontWeight.BOLD), width=250, alignment=ft.alignment.center_left), on_sort=self._ordenar_tabla_pronosticos), 
            ft.DataColumn(ft.Container(content=ft.Text("Fecha y Hora", color="white", weight=ft.FontWeight.BOLD), width=140, alignment=ft.alignment.center_left), on_sort=self._ordenar_tabla_pronosticos), 
            ft.DataColumn(ft.Container(content=ft.Text("Torneo", color="yellow", weight=ft.FontWeight.BOLD), width=150, alignment=ft.alignment.center_left), on_sort=self._ordenar_tabla_pronosticos), 
            ft.DataColumn(ft.Container(content=ft.Text("Resultado", color="white", weight=ft.FontWeight.BOLD), width=80, alignment=ft.alignment.center), on_sort=self._ordenar_tabla_pronosticos), 
            ft.DataColumn(ft.Container(content=ft.Text("Usuario", color="white", weight=ft.FontWeight.BOLD), width=100, alignment=ft.alignment.center_left), on_sort=self._ordenar_tabla_pronosticos), 
            ft.DataColumn(ft.Container(content=ft.Text("Pronóstico", color="cyan", weight=ft.FontWeight.BOLD), width=80, alignment=ft.alignment.center), on_sort=self._ordenar_tabla_pronosticos), 
            ft.DataColumn(ft.Container(content=ft.Text("Fecha Predicción", color="white70", weight=ft.FontWeight.BOLD), width=140, alignment=ft.alignment.center_left), on_sort=self._ordenar_tabla_pronosticos), 
            ft.DataColumn(ft.Container(content=ft.Text("Puntos", color="green", weight=ft.FontWeight.BOLD), width=60, alignment=ft.alignment.center), numeric=True, on_sort=self._ordenar_tabla_pronosticos)
        ]

        columnas_estadisticas = [ft.DataColumn(ft.Text("Puesto", color="white", weight=ft.FontWeight.BOLD), numeric=True), ft.DataColumn(ft.Container(content=ft.Text("Usuario", color="white", weight=ft.FontWeight.BOLD), width=80, alignment=ft.alignment.center_left)), ft.DataColumn(ft.Text("Puntos\nTotales", color="yellow", weight=ft.FontWeight.BOLD), numeric=True), ft.DataColumn(ft.Text("Pts.\nGanador", color="white"), numeric=True), ft.DataColumn(ft.Text("Pts.\nGoles CAI", color="white"), numeric=True), ft.DataColumn(ft.Text("Pts.\nGoles Rival", color="white"), numeric=True)]

        # --- DEFINICIÓN DE NUEVA TABLA: TORNEOS GANADOS ---
        columnas_copas = [
            ft.DataColumn(ft.Text("Puesto", color="white", weight=ft.FontWeight.BOLD), numeric=True),
            ft.DataColumn(ft.Container(content=ft.Text("Usuario", color="white", weight=ft.FontWeight.BOLD), width=200, alignment=ft.alignment.center_left)),
            ft.DataColumn(ft.Container(content=ft.Text("Torneos ganados", color="yellow", weight=ft.FontWeight.BOLD), width=150, alignment=ft.alignment.center), numeric=True)
        ]

        # --- DEFINICIÓN DE TABLAS ---
        self.tabla_estadisticas_header = ft.DataTable(width=600, bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(top_left=8, top_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_color="black", heading_row_height=70, data_row_max_height=0, column_spacing=15, columns=columnas_estadisticas, rows=[])
        self.tabla_estadisticas = ft.DataTable(width=600, bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(bottom_left=8, bottom_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_height=0, data_row_max_height=60, column_spacing=15, columns=columnas_estadisticas, rows=[])
        
        self.tabla_copas_header = ft.DataTable(width=450, bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(top_left=8, top_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_color="black", heading_row_height=70, data_row_max_height=0, column_spacing=20, columns=columnas_copas, rows=[])
        self.tabla_copas = ft.DataTable(width=450, bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(bottom_left=8, bottom_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_height=0, data_row_max_height=60, column_spacing=20, columns=columnas_copas, rows=[])

        self.tabla_partidos_header = ft.DataTable(bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(top_left=8, top_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_color="black", heading_row_height=70, data_row_max_height=0, column_spacing=20, columns=columnas_partidos, rows=[])
        self.tabla_partidos = ft.DataTable(bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(bottom_left=8, bottom_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_height=0, data_row_max_height=60, column_spacing=20, columns=columnas_partidos, rows=[])

        self.tabla_pronosticos_header = ft.DataTable(bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(top_left=8, top_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_color="black", heading_row_height=70, data_row_max_height=0, column_spacing=20, columns=columnas_pronosticos, rows=[])
        
        self.tabla_pronosticos = ft.DataTable(
            bgcolor="#2D2D2D", 
            border=ft.border.all(1, "white10"), 
            border_radius=ft.border_radius.only(bottom_left=8, bottom_right=8), 
            vertical_lines=ft.border.BorderSide(1, "white10"), 
            horizontal_lines=ft.border.BorderSide(1, "white10"), 
            heading_row_height=0, 
            data_row_max_height=60, 
            column_spacing=20, 
            columns=columnas_pronosticos, 
            sort_column_index=self.pronosticos_sort_col_index,
            sort_ascending=self.pronosticos_sort_asc,
            rows=[]
        )
        
        self.tabla_partidos_admin = ft.DataTable(bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=8, vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_color="black", heading_row_height=70, data_row_max_height=60, column_spacing=20, show_checkbox_column=False, columns=[ft.DataColumn(ft.Container(content=ft.Text("Vs (Rival)", color="white", weight=ft.FontWeight.BOLD), width=250, alignment=ft.alignment.center_left)), ft.DataColumn(ft.Container(content=ft.Text("Resultado", color="white", weight=ft.FontWeight.BOLD), width=80, alignment=ft.alignment.center)), ft.DataColumn(ft.Container(content=ft.Text("Fecha y Hora", color="white", weight=ft.FontWeight.BOLD), width=140, alignment=ft.alignment.center_left)), ft.DataColumn(ft.Container(content=ft.Text("Torneo", color="yellow", weight=ft.FontWeight.BOLD), width=230, alignment=ft.alignment.center_left))], rows=[])
        self.tabla_torneos = ft.DataTable(width=450, bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=8, vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_color="black", heading_row_height=60, data_row_max_height=50, column_spacing=20, show_checkbox_column=False, columns=[ft.DataColumn(ft.Container(content=ft.Text("Nombre", color="white", weight=ft.FontWeight.BOLD), width=250, alignment=ft.alignment.center_left)), ft.DataColumn(ft.Container(content=ft.Text("Año", color="yellow", weight=ft.FontWeight.BOLD), width=80, alignment=ft.alignment.center_left), numeric=True)], rows=[])

        # --- BARRAS DE CARGA ---
        self.loading = ft.ProgressBar(width=400, color="amber", bgcolor="#222222", visible=True)
        self.loading_partidos = ft.ProgressBar(width=400, color="amber", bgcolor="#222222", visible=False) 
        self.loading_pronosticos = ft.ProgressBar(width=400, color="amber", bgcolor="#222222", visible=False) 
        self.loading_admin = ft.ProgressBar(width=400, color="amber", bgcolor="#222222", visible=False)
        self.loading_torneos_admin = ft.ProgressBar(width=400, color="amber", bgcolor="#222222", visible=False) 

        # --- TÍTULOS DINÁMICOS ---
        self.txt_titulo_partidos = ft.Text("Partidos por jugar", size=28, weight=ft.FontWeight.BOLD, color="white")
        self.txt_titulo_pronosticos = ft.Text("Todos los pronósticos", size=28, weight=ft.FontWeight.BOLD, color="white") 

        # --- BOTONES FILTROS PARTIDOS ---
        self.btn_todos = ft.ElevatedButton("Todos", icon=ft.Icons.LIST, bgcolor="#333333", color="white", on_click=lambda _: self._cambiar_filtro('todos'))
        self.btn_jugados = ft.ElevatedButton("Jugados", icon=ft.Icons.HISTORY, bgcolor="#333333", color="white", on_click=lambda _: self._cambiar_filtro('jugados'))
        self.btn_por_jugar = ft.ElevatedButton("Por jugar", icon=ft.Icons.UPCOMING, bgcolor="blue", color="white", on_click=lambda _: self._cambiar_filtro('futuros'))
        self.btn_por_torneo = ft.ElevatedButton("Por torneo", icon=ft.Icons.EMOJI_EVENTS, bgcolor="#333333", color="white", on_click=self._abrir_selector_torneo)
        self.btn_sin_pronosticar = ft.ElevatedButton("Sin pronosticar", icon=ft.Icons.EVENT_BUSY, bgcolor="#333333", color="white", on_click=lambda _: self._cambiar_filtro('sin_pronosticar'))
        self.btn_por_equipo = ft.ElevatedButton("Por equipo", icon=ft.Icons.GROUPS, bgcolor="#333333", color="white", on_click=self._abrir_selector_equipo)

        # --- BOTONES FILTROS PRONÓSTICOS ---
        self.btn_pron_todos = ft.ElevatedButton("Todos", icon=ft.Icons.LIST, bgcolor="blue", color="white", on_click=lambda _: self._cambiar_filtro_tiempo('todos'))
        self.btn_pron_por_jugar = ft.ElevatedButton("Por jugar", icon=ft.Icons.UPCOMING, bgcolor="#333333", color="white", on_click=lambda _: self._cambiar_filtro_tiempo('futuros'))
        self.btn_pron_jugados = ft.ElevatedButton("Jugados", icon=ft.Icons.HISTORY, bgcolor="#333333", color="white", on_click=lambda _: self._cambiar_filtro_tiempo('jugados'))
        
        self.btn_pron_por_torneo = ft.ElevatedButton("Por torneo", icon=ft.Icons.EMOJI_EVENTS, bgcolor="#333333", color="white", on_click=lambda _: self._gestionar_accion_boton_filtro('torneo'))
        self.btn_pron_por_equipo = ft.ElevatedButton("Por equipo", icon=ft.Icons.GROUPS, bgcolor="#333333", color="white", on_click=lambda _: self._gestionar_accion_boton_filtro('equipo'))
        self.btn_pron_por_usuario = ft.ElevatedButton("Por usuario", icon=ft.Icons.PERSON, bgcolor="#333333", color="white", on_click=lambda _: self._gestionar_accion_boton_filtro('usuario'))

        # --- CONTROLES FORMULARIO PARTIDOS ---
        self.txt_instruccion = ft.Text("1. Seleccione un Torneo en la tabla inferior", size=12, italic=True, color="yellow", visible=False)
        self.input_rival = ft.TextField(hint_text="Ej: Racing Club", width=200, height=40, text_size=14, content_padding=10, bgcolor="#2D2D2D", border_color="white24", color="white")
        self.txt_fecha_display = ft.Text("---", color="white70", size=13)
        self.txt_hora_display = ft.Text("---", color="white70", size=13)
        self.input_goles_cai = ft.TextField(width=60, height=40, content_padding=10, bgcolor="#2D2D2D", border_color="white24", color="white", keyboard_type=ft.KeyboardType.NUMBER, input_filter=ft.InputFilter(allow=True, regex_string=r"[0-9]", replacement_string=""))
        self.input_goles_rival = ft.TextField(width=60, height=40, content_padding=10, bgcolor="#2D2D2D", border_color="white24", color="white", keyboard_type=ft.KeyboardType.NUMBER, input_filter=ft.InputFilter(allow=True, regex_string=r"[0-9]", replacement_string=""))

        self.btn_pick_date = ft.IconButton(icon=ft.Icons.CALENDAR_MONTH, icon_color="yellow", tooltip="Elegir Fecha", on_click=lambda _: self.page.open(self.date_picker))
        self.btn_pick_time = ft.IconButton(icon=ft.Icons.ACCESS_TIME, icon_color="yellow", tooltip="Elegir Hora", on_click=lambda _: self.page.open(self.time_picker))

        self.btn_add_partido = ft.IconButton(icon=ft.Icons.ADD_CIRCLE, icon_color="green", tooltip="Agregar Partido", on_click=self._agregar_partido, icon_size=40)
        self.btn_edit_partido = ft.IconButton(icon=ft.Icons.EDIT, icon_color="blue", tooltip="Editar Partido", on_click=self._editar_partido)
        self.btn_del_partido = ft.IconButton(icon=ft.Icons.DELETE, icon_color="red", tooltip="Eliminar Partido", on_click=self._eliminar_partido)
        self.btn_clean_partido = ft.IconButton(icon=ft.Icons.CLEANING_SERVICES, icon_color="grey", tooltip="Limpiar Formulario", on_click=self._limpiar_formulario_partido)

        # --- CONTROLES FORMULARIO TORNEOS ---
        self.input_torneo_nombre = ft.TextField(hint_text="Nombre Torneo", width=180, height=40, text_size=14, content_padding=10, bgcolor="#2D2D2D", border_color="white24", color="white")
        hoy = datetime.now()
        anios_disponibles = sorted(list({(hoy - timedelta(days=30)).year, (hoy + timedelta(days=30)).year}))
        self.dd_torneo_anio = ft.Dropdown(width=120, content_padding=5, text_size=14, bgcolor="#2D2D2D", border_color="white24", color="white", options=[ft.dropdown.Option(str(a)) for a in anios_disponibles])
        if len(anios_disponibles) == 1: self.dd_torneo_anio.value = str(anios_disponibles[0])

        self.btn_add_torneo = ft.IconButton(icon=ft.Icons.ADD_CIRCLE, icon_color="green", tooltip="Agregar Nuevo", on_click=self._agregar_torneo, icon_size=40)
        self.btn_edit_torneo = ft.IconButton(icon=ft.Icons.EDIT, icon_color="blue", tooltip="Editar Seleccionado", on_click=self._editar_torneo)
        self.btn_del_torneo = ft.IconButton(icon=ft.Icons.DELETE, icon_color="red", tooltip="Eliminar Seleccionado", on_click=self._eliminar_torneo)
        self.btn_clean_torneo = ft.IconButton(icon=ft.Icons.CLEANING_SERVICES, icon_color="grey", tooltip="Limpiar Formulario", on_click=self._limpiar_formulario_torneo)

        # --- PESTAÑAS ---
        lista_pestanas = [
            # Pestaña Estadísticas
            ft.Tab(
                text="Estadísticas", 
                icon="bar_chart", 
                content=ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text("Tabla de Posiciones", size=28, weight=ft.FontWeight.BOLD, color="white"), 
                            self.loading, 
                            # TABLA RANKING
                            ft.Container(
                                height=260, 
                                content=ft.Column(
                                    spacing=0, 
                                    controls=[
                                        self.tabla_estadisticas_header, 
                                        ft.Container(
                                            height=180, 
                                            content=ft.Column(
                                                controls=[self.tabla_estadisticas], 
                                                scroll=ft.ScrollMode.ALWAYS
                                            )
                                        )
                                    ]
                                )
                            ),
                            ft.Container(height=10),
                            ft.Text("Torneos ganados", size=24, weight=ft.FontWeight.BOLD, color="white"),
                            # TABLA TORNEOS GANADOS
                            ft.Container(
                                height=260, 
                                content=ft.Column(
                                    spacing=0, 
                                    controls=[
                                        self.tabla_copas_header, 
                                        ft.Container(
                                            height=180, 
                                            content=ft.Column(
                                                controls=[self.tabla_copas], 
                                                scroll=ft.ScrollMode.ALWAYS
                                            )
                                        )
                                    ]
                                )
                            )
                        ], 
                        scroll=ft.ScrollMode.AUTO, 
                        horizontal_alignment=ft.CrossAxisAlignment.START
                    ), 
                    padding=20, 
                    alignment=ft.alignment.top_left
                )
            ),
            
            # Pestaña Partidos
            ft.Tab(text="Partidos", icon="sports_soccer", content=ft.Container(content=ft.Column(controls=[self.txt_titulo_partidos, self.loading_partidos, ft.Row(vertical_alignment=ft.CrossAxisAlignment.START, controls=[ft.Container(height=380, content=ft.Row(controls=[ft.Column(spacing=0, controls=[self.tabla_partidos_header, ft.Container(height=310, content=ft.Column(controls=[self.tabla_partidos], scroll=ft.ScrollMode.ALWAYS))])], scroll=ft.ScrollMode.ALWAYS)), ft.Container(width=10), ft.Container(width=200, padding=10, border=ft.border.all(1, "white10"), border_radius=8, bgcolor="#1E1E1E", content=ft.Column(horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=15, controls=[ft.Text("Tu Pronóstico", size=16, weight=ft.FontWeight.BOLD), self.input_pred_cai, self.input_pred_rival, self.btn_pronosticar]))]), ft.Container(height=10), ft.Row(controls=[self.btn_todos, self.btn_por_jugar, self.btn_jugados, self.btn_por_torneo, self.btn_sin_pronosticar, self.btn_por_equipo], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.CENTER)], scroll=ft.ScrollMode.AUTO, horizontal_alignment=ft.CrossAxisAlignment.START), padding=20, alignment=ft.alignment.top_left)),
            
            # Pestaña Pronósticos
            ft.Tab(
                text="Pronósticos", 
                icon="list_alt", 
                content=ft.Container(
                    content=ft.Column(
                        controls=[
                            self.txt_titulo_pronosticos,
                            self.loading_pronosticos, 
                            
                            ft.Container(
                                height=440,
                                content=ft.Column(
                                    spacing=0,
                                    controls=[
                                        self.tabla_pronosticos_header, 
                                        ft.Container(
                                            height=360,
                                            content=ft.Column(
                                                controls=[self.tabla_pronosticos],
                                                scroll=ft.ScrollMode.ALWAYS 
                                            )
                                        )
                                    ]
                                )
                            ),
                            # FILA DE BOTONES
                            ft.Container(height=10),
                            ft.Row(
                                controls=[
                                    self.btn_pron_todos,
                                    self.btn_pron_por_jugar,
                                    self.btn_pron_jugados,
                                    self.btn_pron_por_torneo,
                                    self.btn_pron_por_equipo,
                                    self.btn_pron_por_usuario
                                ],
                                alignment=ft.MainAxisAlignment.START,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER
                            )
                        ], 
                        scroll=ft.ScrollMode.AUTO, 
                        horizontal_alignment=ft.CrossAxisAlignment.START
                    ), 
                    padding=20, 
                    alignment=ft.alignment.top_left
                )
            ),
            
            ft.Tab(text="Configuración", icon="settings", content=ft.Container(content=ft.Column(controls=[ft.Icon(name="settings_applications", size=80, color="white"), ft.Text("Configuración", size=30, color="white")], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER), alignment=ft.alignment.center))
        ]

        if usuario == "Gabriel":
            lista_pestanas.append(ft.Tab(text="Administración", icon="admin_panel_settings", content=ft.Container(padding=0, alignment=ft.alignment.top_left, content=ft.Column(scroll=ft.ScrollMode.AUTO, controls=[ft.Container(padding=20, content=ft.Column(controls=[ft.Row(vertical_alignment=ft.CrossAxisAlignment.START, controls=[ft.Column(controls=[self.loading_admin, ft.Text("Partidos Registrados", size=20, weight=ft.FontWeight.BOLD, color="white"), ft.Container(content=ft.Column(scroll=ft.ScrollMode.ALWAYS, controls=[self.tabla_partidos_admin]), height=350, width=720),]), ft.Container(width=30), ft.Container(width=380, padding=20, border=ft.border.all(1, "white24"), border_radius=10, bgcolor="#1E1E1E", content=ft.Column(tight=True, spacing=15, controls=[ft.Text("Agregar / Editar Partido", size=18, weight=ft.FontWeight.BOLD, color="white"), ft.Divider(color="white24"), self.txt_instruccion, ft.Row(controls=[ft.Text("Rival:", width=60, color="white", weight=ft.FontWeight.BOLD), self.input_rival], alignment=ft.MainAxisAlignment.START), ft.Row(controls=[ft.Text("Fecha:", width=50, color="white", weight=ft.FontWeight.BOLD), self.btn_pick_date, self.txt_fecha_display, ft.Container(width=10), ft.Text("Hora:", width=45, color="white", weight=ft.FontWeight.BOLD), self.btn_pick_time, self.txt_hora_display], alignment=ft.MainAxisAlignment.START), ft.Row(controls=[ft.Text("Goles CAI:", width=80, color="white", weight=ft.FontWeight.BOLD), self.input_goles_cai]), ft.Row(controls=[ft.Text("Goles Rival:", width=80, color="white", weight=ft.FontWeight.BOLD), self.input_goles_rival]), ft.Container(height=10), ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[self.btn_add_partido, ft.Row(spacing=5, controls=[self.btn_edit_partido, self.btn_del_partido, self.btn_clean_partido])])]))]), ft.Container(height=40), ft.Row(vertical_alignment=ft.CrossAxisAlignment.START, controls=[ft.Column(controls=[self.loading_torneos_admin, ft.Text("Torneos Registrados", size=20, weight=ft.FontWeight.BOLD, color="white"), ft.Container(content=ft.Column(scroll=ft.ScrollMode.ALWAYS, controls=[self.tabla_torneos]), height=300, width=480)]), ft.Container(width=30), ft.Container(width=450, padding=20, border=ft.border.all(1, "white24"), border_radius=10, bgcolor="#1E1E1E", content=ft.Column(tight=True, spacing=15, controls=[ft.Text("Gestión de Torneos", size=18, weight=ft.FontWeight.BOLD, color="white"), ft.Divider(color="white24"), ft.Row(controls=[self.input_torneo_nombre, self.dd_torneo_anio], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), ft.Container(height=10), ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[self.btn_add_torneo, ft.Row(spacing=5, controls=[self.btn_edit_torneo, self.btn_del_torneo, self.btn_clean_torneo])])]))])]))]))))

        mis_pestanas = ft.Tabs(selected_index=0, animation_duration=300, expand=True, indicator_color="white", label_color="white", unselected_label_color="white54", divider_color="white", tabs=lista_pestanas)
        self.page.add(mis_pestanas)
        
        self._recargar_datos(actualizar_partidos=True, actualizar_torneos=True, actualizar_admin=True, actualizar_pronosticos=True, actualizar_ranking=True)

    def _ordenar_tabla_pronosticos(self, e):
        """Maneja el evento de ordenar columnas en la tabla de pronósticos"""
        # Si clica la misma columna, invierte el orden. Si es nueva, resetea a Ascendente.
        if self.pronosticos_sort_col_index == e.column_index:
            self.pronosticos_sort_asc = not self.pronosticos_sort_asc
        else:
            self.pronosticos_sort_col_index = e.column_index
            self.pronosticos_sort_asc = True
            
        # Actualizamos la tabla para mostrar la flecha de orden inmediatamente
        self.tabla_pronosticos.sort_column_index = self.pronosticos_sort_col_index
        self.tabla_pronosticos.sort_ascending = self.pronosticos_sort_asc
        self.tabla_pronosticos.update()
        
        # Recargamos datos aplicando el orden
        self._recargar_datos(actualizar_pronosticos=True)

    def _seleccionar_partido_para_pronostico(self, e):
        """Selecciona un partido en la tabla del usuario para pronosticar."""
        if self.cargando_partidos: return

        fila_cliqueada = e.control
        
        # Guardar ID seleccionado
        self.partido_a_pronosticar_id = fila_cliqueada.data
        
        # Efecto visual de selección
        for fila in self.tabla_partidos.rows:
            if fila == fila_cliqueada:
                fila.selected = True
                fila.color = ft.Colors.with_opacity(0.5, "blue")
                self.fila_pronostico_ref = fila
            else:
                fila.selected = False
                fila.color = None
                
        self.page.update()

    def _guardar_pronostico(self, e):
        """Valida y guarda el pronóstico ingresado."""
        def _tarea():
            self.loading_partidos.visible = True
            self.page.update()
            
            try:
                # Validaciones
                if not self.partido_a_pronosticar_id:
                    GestorMensajes.mostrar(self.page, "Atención", "Seleccione un partido de la tabla.", "error")
                    self.loading_partidos.visible = False
                    self.page.update()
                    return
                
                gc_str = self.input_pred_cai.value.strip()
                gr_str = self.input_pred_rival.value.strip()
                
                if not gc_str or not gr_str:
                    GestorMensajes.mostrar(self.page, "Atención", "Ingrese ambos resultados.", "error")
                    self.loading_partidos.visible = False
                    self.page.update()
                    return
                
                # Insertar en BD
                bd = BaseDeDatos()
                bd.insertar_pronostico(self.usuario_actual, self.partido_a_pronosticar_id, int(gc_str), int(gr_str))
                
                GestorMensajes.mostrar(self.page, "Éxito", "Pronóstico guardado.", "exito")
                
                # Limpiar inputs
                self.input_pred_cai.value = ""
                self.input_pred_rival.value = ""
                
                # CORRECCIÓN: Solo actualizar partidos y pronósticos globales. Ranking NO se toca.
                self._recargar_datos(actualizar_partidos=True, actualizar_pronosticos=True, actualizar_ranking=False)
                
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", f"No se pudo guardar: {ex}", "error")
                self.loading_partidos.visible = False
                self.page.update()

        threading.Thread(target=_tarea, daemon=True).start()

    def _validar_solo_numeros(self, e):
        """
        Valida que el input solo contenga números.
        Permite borrar el contenido sin bloquearse.
        """
        if e.control.value:
            # Filtramos solo dígitos
            valor_limpio = "".join(filter(str.isdigit, e.control.value))
            # Si hubo cambios (había letras o símbolos), actualizamos
            if valor_limpio != e.control.value:
                e.control.value = valor_limpio
                e.control.update()

    def _abrir_selector_usuario_pronosticos(self, e):
        self.lv_usuarios = ft.ListView(expand=True, spacing=5, height=300)
        self.btn_ver_usuario = ft.ElevatedButton("Ver", icon=ft.Icons.VISIBILITY, disabled=True, on_click=self._confirmar_filtro_usuario_pronosticos)
        
        def _cargar_usuarios_modal():
            try:
                bd = BaseDeDatos()
                usuarios = bd.obtener_usuarios() 
                controles = []
                for usuario in usuarios:
                    controles.append(ft.ListTile(title=ft.Text(usuario, size=14), data=usuario, on_click=self._seleccionar_usuario_modal, bgcolor="#2D2D2D", shape=ft.RoundedRectangleBorder(radius=5)))
                self.lv_usuarios.controls = controles
                self.lv_usuarios.update()
            except Exception as ex:
                print(f"Error cargando modal usuarios: {ex}")

        contenido_modal = ft.Container(width=400, height=400, content=ft.Column(controls=[ft.Text("Seleccione un Usuario", weight=ft.FontWeight.BOLD), ft.Container(content=self.lv_usuarios, border=ft.border.all(1, "white24"), border_radius=5, padding=5, expand=True)]))

        self.dlg_modal_usuario = ft.AlertDialog(modal=True, title=ft.Text("Filtrar por Usuario"), content=contenido_modal, actions=[ft.TextButton("Cancelar", on_click=lambda e: self.page.close(self.dlg_modal_usuario)), self.btn_ver_usuario], actions_alignment=ft.MainAxisAlignment.END)
        self.page.open(self.dlg_modal_usuario)
        threading.Thread(target=_cargar_usuarios_modal, daemon=True).start()

    def _seleccionar_usuario_modal(self, e):
        """Al clickear un usuario, se habilita el botón ver."""
        usuario_sel = e.control.data
        self.temp_usuario_sel = usuario_sel
        
        # Resaltar selección
        for c in self.lv_usuarios.controls:
            c.bgcolor = "blue" if c.data == usuario_sel else "#2D2D2D"
        self.lv_usuarios.update()
        
        self.btn_ver_usuario.disabled = False
        self.btn_ver_usuario.update()

    def _cambiar_filtro_pronosticos(self, nuevo_filtro):
        """Gestiona el cambio de filtros en la pestaña Pronósticos"""
        self.filtro_pronosticos = nuevo_filtro
        
        # Resetear filtros específicos si cambia la categoría principal
        if nuevo_filtro != 'torneo':
            self.filtro_pron_torneo_nombre = None
        if nuevo_filtro != 'equipo':
            self.filtro_pron_rival_nombre = None
        if nuevo_filtro != 'usuario':
            self.filtro_pron_usuario = None
            
        # Actualizar títulos
        if nuevo_filtro == 'todos':
            self.txt_titulo_pronosticos.value = "Todos los pronósticos"
        elif nuevo_filtro == 'futuros':
            self.txt_titulo_pronosticos.value = "Pronósticos por jugar"
        elif nuevo_filtro == 'jugados':
            self.txt_titulo_pronosticos.value = "Pronósticos finalizados"
        
        self.txt_titulo_pronosticos.update()
        
        # Actualizar colores botones
        self.btn_pron_todos.bgcolor = "blue" if nuevo_filtro == 'todos' else "#333333"
        self.btn_pron_por_jugar.bgcolor = "blue" if nuevo_filtro == 'futuros' else "#333333"
        self.btn_pron_jugados.bgcolor = "blue" if nuevo_filtro == 'jugados' else "#333333"
        self.btn_pron_por_torneo.bgcolor = "blue" if nuevo_filtro == 'torneo' else "#333333"
        self.btn_pron_por_equipo.bgcolor = "blue" if nuevo_filtro == 'equipo' else "#333333"
        self.btn_pron_por_usuario.bgcolor = "blue" if nuevo_filtro == 'usuario' else "#333333"
        
        self.btn_pron_todos.update()
        self.btn_pron_por_jugar.update()
        self.btn_pron_jugados.update()
        self.btn_pron_por_torneo.update()
        self.btn_pron_por_equipo.update()
        self.btn_pron_por_usuario.update()
        
        # Recargar solo pronósticos
        self._recargar_datos(actualizar_pronosticos=True)

    def _abrir_selector_torneo_pronosticos(self, e):
        # Reutilizamos el mismo diseño del modal, pero cambiamos la acción del botón "Ver"
        self.lv_torneos = ft.ListView(expand=True, spacing=5, height=200)
        self.lv_anios = ft.ListView(expand=True, spacing=5, height=200)
        
        # El botón llama a _confirmar_filtro_torneo_pronosticos
        self.btn_ver_torneo = ft.ElevatedButton("Ver", icon=ft.Icons.VISIBILITY, disabled=True, on_click=self._confirmar_filtro_torneo_pronosticos)
        
        def _cargar_datos_modal():
            try:
                bd = BaseDeDatos()
                ediciones = bd.obtener_ediciones()
                self.cache_ediciones_modal = ediciones
                nombres_unicos = sorted(list(set(e[1] for e in ediciones)))
                
                controles = []
                for nombre in nombres_unicos:
                    controles.append(ft.ListTile(title=ft.Text(nombre, size=14), data=nombre, on_click=self._seleccionar_campeonato_modal, bgcolor="#2D2D2D", shape=ft.RoundedRectangleBorder(radius=5)))
                self.lv_torneos.controls = controles
                self.lv_torneos.update()
            except Exception as ex:
                print(f"Error cargando modal: {ex}")

        contenido_modal = ft.Container(width=500, height=300, content=ft.Row(controls=[ft.Column(expand=1, controls=[ft.Text("Torneo", weight=ft.FontWeight.BOLD), ft.Container(content=self.lv_torneos, border=ft.border.all(1, "white24"), border_radius=5, padding=5)]), ft.VerticalDivider(width=20, color="white24"), ft.Column(expand=1, controls=[ft.Text("Año", weight=ft.FontWeight.BOLD), ft.Container(content=self.lv_anios, border=ft.border.all(1, "white24"), border_radius=5, padding=5)])]))

        self.dlg_modal = ft.AlertDialog(modal=True, title=ft.Text("Filtrar por Torneo"), content=contenido_modal, actions=[ft.TextButton("Cancelar", on_click=lambda e: self.page.close(self.dlg_modal)), self.btn_ver_torneo], actions_alignment=ft.MainAxisAlignment.END)
        self.page.open(self.dlg_modal)
        threading.Thread(target=_cargar_datos_modal, daemon=True).start()

    def _confirmar_filtro_torneo_pronosticos(self, e):
        """Confirma selección torneo (COMBINABLE)"""
        if self.temp_campeonato_sel and self.temp_anio_sel:
            # 1. Guardar filtro
            self.filtro_pron_torneo = f"{self.temp_campeonato_sel} {self.temp_anio_sel}"
            
            # 2. Actualizar visual botón a AZUL
            self.btn_pron_por_torneo.bgcolor = "blue"
            self.btn_pron_por_torneo.update()
            
            # 3. Cerrar y recargar (acumulando filtros)
            self._actualizar_titulo_pronosticos()
            self.page.close(self.dlg_modal)
            self._recargar_datos(actualizar_pronosticos=True)

    def _confirmar_filtro_equipo_pronosticos(self, e):
        """Confirma selección equipo (COMBINABLE)"""
        if self.temp_rival_sel_nombre:
            self.filtro_pron_equipo = self.temp_rival_sel_nombre
            
            self.btn_pron_por_equipo.bgcolor = "blue"
            self.btn_pron_por_equipo.update()
            
            self._actualizar_titulo_pronosticos()
            self.page.close(self.dlg_modal_equipo)
            self._recargar_datos(actualizar_pronosticos=True)

    def _confirmar_filtro_usuario_pronosticos(self, e):
        """Confirma selección usuario (COMBINABLE)"""
        if self.temp_usuario_sel:
            self.filtro_pron_usuario = self.temp_usuario_sel
            
            self.btn_pron_por_usuario.bgcolor = "blue"
            self.btn_pron_por_usuario.update()
            
            self._actualizar_titulo_pronosticos()
            self.page.close(self.dlg_modal_usuario)
            self._recargar_datos(actualizar_pronosticos=True)

    def _abrir_selector_equipo_pronosticos(self, e):
        self.lv_equipos = ft.ListView(expand=True, spacing=5, height=300)
        # El botón llama a _confirmar_filtro_equipo_pronosticos
        self.btn_ver_equipo = ft.ElevatedButton("Ver", icon=ft.Icons.VISIBILITY, disabled=True, on_click=self._confirmar_filtro_equipo_pronosticos)
        
        def _cargar_rivales_modal():
            try:
                bd = BaseDeDatos()
                rivales = bd.obtener_rivales() 
                controles = []
                for id_rival, nombre in rivales:
                    controles.append(ft.ListTile(title=ft.Text(nombre, size=14), data=id_rival, on_click=self._seleccionar_rival_modal, bgcolor="#2D2D2D", shape=ft.RoundedRectangleBorder(radius=5)))
                self.lv_equipos.controls = controles
                self.lv_equipos.update()
            except Exception as ex:
                print(f"Error cargando modal equipos: {ex}")

        contenido_modal = ft.Container(width=400, height=400, content=ft.Column(controls=[ft.Text("Seleccione un Equipo", weight=ft.FontWeight.BOLD), ft.Container(content=self.lv_equipos, border=ft.border.all(1, "white24"), border_radius=5, padding=5, expand=True)]))

        self.dlg_modal_equipo = ft.AlertDialog(modal=True, title=ft.Text("Filtrar por Equipo"), content=contenido_modal, actions=[ft.TextButton("Cancelar", on_click=lambda e: self.page.close(self.dlg_modal_equipo)), self.btn_ver_equipo], actions_alignment=ft.MainAxisAlignment.END)
        self.page.open(self.dlg_modal_equipo)
        threading.Thread(target=_cargar_rivales_modal, daemon=True).start()

    def _recargar_datos(self, actualizar_partidos=False, actualizar_torneos=False, actualizar_admin=False, actualizar_pronosticos=False, actualizar_ranking=False):
        # Activamos las banderas correspondientes
        if actualizar_partidos:
            self.cargando_partidos = True
        if actualizar_torneos:
            self.cargando_torneos = True
            
        if not any([actualizar_partidos, actualizar_torneos, actualizar_admin, actualizar_pronosticos, actualizar_ranking]):
            return

        if actualizar_ranking:
            self.loading.visible = True
        if actualizar_partidos:
            self.loading_partidos.visible = True
            self._bloquear_botones_filtros(True) 
        if actualizar_pronosticos: 
            self.loading_pronosticos.visible = True
        if actualizar_admin:
            self.loading_admin.visible = True 
        if actualizar_torneos:
            self.loading_torneos_admin.visible = True
        
        if actualizar_pronosticos:
             self.tabla_pronosticos.sort_column_index = self.pronosticos_sort_col_index
             self.tabla_pronosticos.sort_ascending = self.pronosticos_sort_asc

        self.page.update()
        
        def _tarea_en_segundo_plano():
            time.sleep(0.5)
            
            if actualizar_torneos:
                self.fila_seleccionada_ref = None
                self.edicion_seleccionada_id = None
            if actualizar_admin: 
                self.fila_partido_ref = None
                self.partido_seleccionado_id = None
            if actualizar_partidos: 
                self.fila_pronostico_ref = None
                self.partido_a_pronosticar_id = None

            try:
                bd = BaseDeDatos()
                
                # --- 0. RANKING Y COPAS ---
                if actualizar_ranking:
                    # Ranking General
                    datos_ranking = bd.obtener_ranking()
                    filas_tabla_ranking = []
                    for i, fila in enumerate(datos_ranking, start=1):
                        filas_tabla_ranking.append(ft.DataRow(cells=[
                            ft.DataCell(ft.Text(f"{i}º", weight=ft.FontWeight.BOLD, color="white")), 
                            ft.DataCell(ft.Container(content=ft.Text(str(fila[0]), weight=ft.FontWeight.BOLD, color="white", no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS), width=80, alignment=ft.alignment.center_left)), 
                            ft.DataCell(ft.Text(str(fila[1]), weight=ft.FontWeight.BOLD, color="yellow", size=16)), 
                            ft.DataCell(ft.Text(str(fila[2]), color="white70")), 
                            ft.DataCell(ft.Text(str(fila[3]), color="white70")), 
                            ft.DataCell(ft.Text(str(fila[4]), color="white70"))
                        ]))
                    self.tabla_estadisticas.rows = filas_tabla_ranking
                    
                    # NUEVO: Tabla Torneos Ganados
                    datos_copas = bd.obtener_torneos_ganados()
                    filas_copas = []
                    for i, fila in enumerate(datos_copas, start=1):
                        usuario_copa = fila[0]
                        cantidad_copas = fila[1]
                        filas_copas.append(ft.DataRow(cells=[
                            ft.DataCell(ft.Text(f"{i}º", weight=ft.FontWeight.BOLD, color="white")),
                            ft.DataCell(ft.Container(content=ft.Text(str(usuario_copa), weight=ft.FontWeight.BOLD, color="white"), width=200, alignment=ft.alignment.center_left)),
                            ft.DataCell(ft.Container(content=ft.Text(str(cantidad_copas), weight=ft.FontWeight.BOLD, color="yellow", size=16), width=150, alignment=ft.alignment.center))
                        ]))
                    self.tabla_copas.rows = filas_copas

                # --- 1. TABLAS DE USUARIO (SOLO PARTIDOS) ---
                if actualizar_partidos:
                    datos_partidos_user = bd.obtener_partidos(
                        self.usuario_actual, 
                        filtro=self.filtro_partidos, 
                        edicion_id=self.filtro_edicion_id,
                        rival_id=self.filtro_rival_id
                    )
                    filas_tabla_partidos = []
                    for fila in datos_partidos_user:
                        p_id = fila[0]
                        rival = fila[1]
                        fecha_obj = fila[2]
                        torneo = fila[3]
                        gc = fila[4]
                        gr = fila[5]
                        fecha_display_str = fila[7] 
                        pred_cai = fila[8]
                        pred_rival = fila[9]
                        puntos_usuario = fila[10] 

                        if gc is not None and gr is not None:
                            texto_resultado = f"{gc} a {gr}"
                        else: texto_resultado = "-"
                        if pred_cai is not None and pred_rival is not None:
                            texto_pronostico = f"{pred_cai} a {pred_rival}"
                        else: texto_pronostico = "-"
                        if puntos_usuario is None:
                            texto_puntos = "-"
                        else: texto_puntos = f"{puntos_usuario}"

                        filas_tabla_partidos.append(ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(content=ft.Text(str(rival), weight=ft.FontWeight.BOLD, color="white", no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS), width=250, alignment=ft.alignment.center_left)), 
                                ft.DataCell(ft.Container(content=ft.Text(texto_resultado, color="white", weight=ft.FontWeight.BOLD), alignment=ft.alignment.center)),
                                ft.DataCell(ft.Text(fecha_display_str, color="white70")), 
                                ft.DataCell(ft.Container(content=ft.Text(str(torneo), color="yellow", weight=ft.FontWeight.BOLD), width=150, alignment=ft.alignment.center_left)),
                                ft.DataCell(ft.Container(content=ft.Text(texto_pronostico, color="cyan", weight=ft.FontWeight.BOLD), alignment=ft.alignment.center)),
                                ft.DataCell(ft.Container(content=ft.Text(texto_puntos, color="green", weight=ft.FontWeight.BOLD, size=15), alignment=ft.alignment.center))
                            ],
                            data=p_id, on_select_changed=self._seleccionar_partido_para_pronostico, selected=False
                        ))
                    self.tabla_partidos.rows = filas_tabla_partidos

                # --- 1.B CARGAR PRONÓSTICOS (LÓGICA COMBINADA) ---
                if actualizar_pronosticos:
                    datos_pronosticos = bd.obtener_todos_pronosticos()
                    ahora = datetime.now()
                    
                    # 1. FILTRO DE TIEMPO
                    if self.filtro_pron_tiempo == 'futuros':
                         datos_pronosticos = [d for d in datos_pronosticos if isinstance(d[1], datetime) and d[1] > ahora]
                    elif self.filtro_pron_tiempo == 'jugados':
                         datos_pronosticos = [d for d in datos_pronosticos if isinstance(d[1], datetime) and d[1] <= ahora]
                    
                    # 2. FILTROS ESPECÍFICOS
                    if self.filtro_pron_torneo:
                         datos_pronosticos = [d for d in datos_pronosticos if str(d[2]) == self.filtro_pron_torneo]
                    
                    if self.filtro_pron_equipo:
                         datos_pronosticos = [d for d in datos_pronosticos if str(d[0]) == self.filtro_pron_equipo]
                         
                    if self.filtro_pron_usuario:
                         datos_pronosticos = [d for d in datos_pronosticos if str(d[5]) == self.filtro_pron_usuario]
                    
                    # 3. ORDENAMIENTO
                    if self.pronosticos_sort_col_index is not None:
                        idx = self.pronosticos_sort_col_index
                        reverse_manual = not self.pronosticos_sort_asc 
                        key_func = None
                        if idx == 0: key_func = lambda x: str(x[0]).lower() 
                        elif idx == 1: key_func = lambda x: x[1] if isinstance(x[1], datetime) else datetime.min 
                        elif idx == 2: key_func = lambda x: str(x[2]).lower() 
                        elif idx == 3: key_func = lambda x: (x[3] if x[3] is not None else -1) 
                        elif idx == 4: key_func = lambda x: str(x[5]).lower() 
                        elif idx == 5: key_func = lambda x: (x[6] if x[6] is not None else -1) 
                        elif idx == 6: key_func = lambda x: x[9] if isinstance(x[9], datetime) else datetime.min
                        elif idx == 7: key_func = lambda x: (x[8] if x[8] is not None else -1)
                        if key_func:
                            datos_pronosticos.sort(key=key_func, reverse=reverse_manual)
                    else:
                        reversa = True 
                        if self.filtro_pron_tiempo == 'futuros':
                            reversa = False
                        datos_pronosticos.sort(key=lambda x: x[1] if isinstance(x[1], datetime) else datetime.min, reverse=reversa)

                    filas_tabla_pronosticos = []
                    for fila in datos_pronosticos:
                        rival = fila[0]
                        fecha = fila[1]
                        torneo = fila[2]
                        gc = fila[3]
                        gr = fila[4]
                        user = fila[5]
                        pgc = fila[6]
                        pgr = fila[7]
                        puntos = fila[8]
                        fecha_pred = fila[9]

                        if isinstance(fecha, datetime):
                            if fecha.hour == 0 and fecha.minute == 0:
                                txt_fecha = fecha.strftime("%d/%m/%Y s. h.") 
                            else:
                                txt_fecha = fecha.strftime("%d/%m/%Y %H:%M") 
                        else:
                            txt_fecha = str(fecha)
                        
                        if isinstance(fecha_pred, datetime):
                            txt_fecha_pred = fecha_pred.strftime("%d/%m/%Y %H:%M") 
                        else:
                            txt_fecha_pred = str(fecha_pred) if fecha_pred else "-"

                        if gc is not None and gr is not None: txt_res = f"{gc} a {gr}"
                        else: txt_res = "-"
                        if pgc is not None and pgr is not None: txt_pron = f"{pgc} a {pgr}"
                        else: txt_pron = "-"
                        
                        if puntos is None: 
                            txt_puntos = "-"
                            color_puntos = "white"
                        elif puntos == 0:
                            txt_puntos = "0"
                            color_puntos = "white" 
                        else:
                            txt_puntos = f"+{puntos}"
                            color_puntos = "green"

                        filas_tabla_pronosticos.append(ft.DataRow(cells=[
                            ft.DataCell(ft.Container(content=ft.Text(str(rival), weight=ft.FontWeight.BOLD, color="white", no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS), width=250, alignment=ft.alignment.center_left)), 
                            ft.DataCell(ft.Text(txt_fecha, color="white70")), 
                            ft.DataCell(ft.Container(content=ft.Text(str(torneo), color="yellow", weight=ft.FontWeight.BOLD), width=150, alignment=ft.alignment.center_left)),
                            ft.DataCell(ft.Container(content=ft.Text(txt_res, color="white", weight=ft.FontWeight.BOLD), alignment=ft.alignment.center)),
                            ft.DataCell(ft.Container(content=ft.Text(str(user), color="white", weight=ft.FontWeight.BOLD), width=100, alignment=ft.alignment.center_left)),
                            ft.DataCell(ft.Container(content=ft.Text(txt_pron, color="cyan", weight=ft.FontWeight.BOLD), alignment=ft.alignment.center)),
                            ft.DataCell(ft.Container(content=ft.Text(txt_fecha_pred, color="white70"), width=140, alignment=ft.alignment.center_left)),
                            ft.DataCell(ft.Container(content=ft.Text(txt_puntos, color=color_puntos, size=16, weight=ft.FontWeight.BOLD), alignment=ft.alignment.center))
                        ]))
                    self.tabla_pronosticos.rows = filas_tabla_pronosticos

                # --- 2. TABLA ADMIN ---
                if actualizar_admin:
                    datos_admin = bd.obtener_partidos(self.usuario_actual, filtro='todos')
                    filas_tabla_admin = [] 
                    for fila in datos_admin:
                        p_id = fila[0]
                        rival = fila[1]
                        fecha_obj = fila[2]
                        torneo = fila[3]
                        gc = fila[4]
                        gr = fila[5]
                        ed_id = fila[6]
                        fecha_display_str = fila[7] 
                        if gc is not None and gr is not None: texto_resultado = f"{gc} a {gr}"
                        else: texto_resultado = "-"

                        filas_tabla_admin.append(ft.DataRow(cells=[ft.DataCell(ft.Container(content=ft.Text(str(rival), weight=ft.FontWeight.BOLD, color="white", no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS), width=250, alignment=ft.alignment.center_left)), ft.DataCell(ft.Container(content=ft.Text(texto_resultado, color="white", weight=ft.FontWeight.BOLD), alignment=ft.alignment.center)), ft.DataCell(ft.Text(fecha_display_str, color="white70")), ft.DataCell(ft.Container(content=ft.Text(str(torneo), color="yellow", weight=ft.FontWeight.BOLD), width=230, alignment=ft.alignment.center_left))], data={'id': p_id, 'rival': rival, 'fecha': fecha_obj, 'goles_cai': gc, 'goles_rival': gr, 'edicion_id': ed_id}, on_select_changed=self._seleccionar_partido, selected=False))
                    self.tabla_partidos_admin.rows = filas_tabla_admin

                # --- 3. TORNEOS ---
                if actualizar_torneos:
                    datos_ediciones = bd.obtener_ediciones()
                    filas_torneos = []
                    for ed in datos_ediciones:
                        ed_id = ed[0]
                        nombre = ed[1]
                        anio = ed[2]
                        filas_torneos.append(ft.DataRow(cells=[ft.DataCell(ft.Container(content=ft.Text(str(nombre), color="white", weight=ft.FontWeight.BOLD), width=250, alignment=ft.alignment.center_left)), ft.DataCell(ft.Text(str(anio), color="yellow", weight=ft.FontWeight.BOLD))], data=ed_id, on_select_changed=self._seleccionar_torneo, selected=False))
                    self.tabla_torneos.rows = filas_torneos

            except Exception as e:
                print(f"Error recargando datos: {e}")
            
            finally:
                self.editando_torneo = False
                self.loading.visible = False
                self.loading_partidos.visible = False
                self.loading_pronosticos.visible = False 
                self.loading_admin.visible = False
                self.loading_torneos_admin.visible = False
                
                if actualizar_partidos:
                    self.cargando_partidos = False
                    self._bloquear_botones_filtros(False) 
                
                if actualizar_torneos:
                    self.cargando_torneos = False
                    
                self.page.update()

        threading.Thread(target=_tarea_en_segundo_plano, daemon=True).start()

    def _abrir_selector_equipo(self, e):
        """Abre un diálogo modal para seleccionar un equipo rival."""
        
        # Lista vacía
        self.lv_equipos = ft.ListView(expand=True, spacing=5, height=300)
        self.btn_ver_equipo = ft.ElevatedButton("Ver", icon=ft.Icons.VISIBILITY, disabled=True, on_click=self._confirmar_filtro_equipo)
        
        # Cargar datos en hilo aparte
        def _cargar_rivales_modal():
            try:
                bd = BaseDeDatos()
                rivales = bd.obtener_rivales() # [(id, nombre), ...]
                self.cache_rivales_modal = rivales 
                
                controles = []
                for id_rival, nombre in rivales:
                    controles.append(
                        ft.ListTile(
                            title=ft.Text(nombre, size=14),
                            data=id_rival, # Guardamos el ID en data
                            on_click=self._seleccionar_rival_modal,
                            bgcolor="#2D2D2D",
                            shape=ft.RoundedRectangleBorder(radius=5)
                        )
                    )
                self.lv_equipos.controls = controles
                self.lv_equipos.update()
            except Exception as ex:
                print(f"Error cargando modal equipos: {ex}")

        # Contenedor del Modal
        contenido_modal = ft.Container(
            width=400,
            height=400,
            content=ft.Column(
                controls=[
                    ft.Text("Seleccione un Equipo", weight=ft.FontWeight.BOLD),
                    ft.Container(
                        content=self.lv_equipos,
                        border=ft.border.all(1, "white24"),
                        border_radius=5,
                        padding=5,
                        expand=True
                    )
                ]
            )
        )

        self.dlg_modal_equipo = ft.AlertDialog(
            modal=True,
            title=ft.Text("Filtrar por Equipo"),
            content=contenido_modal,
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self.page.close(self.dlg_modal_equipo)),
                self.btn_ver_equipo
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self.page.open(self.dlg_modal_equipo)
        threading.Thread(target=_cargar_rivales_modal, daemon=True).start()

    def _seleccionar_rival_modal(self, e):
        """Al clickear un equipo, se habilita el botón ver."""
        id_sel = e.control.data
        titulo_control = e.control.title.value
        
        self.temp_rival_sel_id = id_sel
        self.temp_rival_sel_nombre = titulo_control
        
        # Resaltar selección
        for c in self.lv_equipos.controls:
            c.bgcolor = "blue" if c.data == id_sel else "#2D2D2D"
        self.lv_equipos.update()
        
        self.btn_ver_equipo.disabled = False
        self.btn_ver_equipo.update()

    def _confirmar_filtro_equipo(self, e):
        """Confirma la selección y recarga la tabla."""
        if self.temp_rival_sel_id:
            self.filtro_partidos = 'equipo'
            self.filtro_rival_id = self.temp_rival_sel_id
            
            # Actualizar Título
            self.txt_titulo_partidos.value = f"Partidos contra {self.temp_rival_sel_nombre}"
            self.txt_titulo_partidos.update()
            
            # Actualizar botones
            self.btn_todos.bgcolor = "#333333"
            self.btn_jugados.bgcolor = "#333333"
            self.btn_por_jugar.bgcolor = "#333333"
            self.btn_por_torneo.bgcolor = "#333333"
            self.btn_sin_pronosticar.bgcolor = "#333333"
            self.btn_por_equipo.bgcolor = "blue"
            
            self.btn_todos.update()
            self.btn_jugados.update()
            self.btn_por_jugar.update()
            self.btn_por_torneo.update()
            self.btn_sin_pronosticar.update()
            self.btn_por_equipo.update()
            
            self.page.close(self.dlg_modal_equipo)
            self._recargar_datos(actualizar_partidos=True)

    def _cambiar_filtro(self, nuevo_filtro):
        """
        Cambia el filtro de partidos y actualiza los botones y el título.
        """
        self.filtro_partidos = nuevo_filtro
            
        # Si cambiamos el tipo de filtro, limpiamos los filtros específicos anteriores
        if nuevo_filtro != 'torneo':
            self.filtro_edicion_id = None
        if nuevo_filtro != 'equipo':
            self.filtro_rival_id = None
            
        # Actualizar Título
        if self.filtro_partidos == 'todos':
            self.txt_titulo_partidos.value = "Todos los partidos"
        elif self.filtro_partidos == 'futuros':
            self.txt_titulo_partidos.value = "Partidos por jugar"
        elif self.filtro_partidos == 'jugados':
            self.txt_titulo_partidos.value = "Partidos jugados"
        elif self.filtro_partidos == 'sin_pronosticar':
            self.txt_titulo_partidos.value = "Partidos sin pronosticar"
            
        self.txt_titulo_partidos.update()
            
        # Actualizar aspecto visual (Solo uno azul)
        self.btn_todos.bgcolor = "blue" if self.filtro_partidos == 'todos' else "#333333"
        self.btn_jugados.bgcolor = "blue" if self.filtro_partidos == 'jugados' else "#333333"
        self.btn_por_jugar.bgcolor = "blue" if self.filtro_partidos == 'futuros' else "#333333"
        self.btn_por_torneo.bgcolor = "blue" if self.filtro_partidos == 'torneo' else "#333333"
        self.btn_sin_pronosticar.bgcolor = "blue" if self.filtro_partidos == 'sin_pronosticar' else "#333333"
        self.btn_por_equipo.bgcolor = "blue" if self.filtro_partidos == 'equipo' else "#333333"
            
        self.btn_todos.update()
        self.btn_jugados.update()
        self.btn_por_jugar.update()
        self.btn_por_torneo.update()
        self.btn_sin_pronosticar.update()
        self.btn_por_equipo.update()
        
        # CORRECCIÓN: Solo partidos. Nada más.
        self._recargar_datos(actualizar_partidos=True, actualizar_ranking=False)

    def _abrir_selector_torneo(self, e):
        """Abre un diálogo modal para seleccionar Torneo y Año"""
        
        # Siempre abrimos el modal para elegir un torneo nuevo
        self.lv_torneos = ft.ListView(expand=True, spacing=5, height=200)
        self.lv_anios = ft.ListView(expand=True, spacing=5, height=200)
        self.btn_ver_torneo = ft.ElevatedButton("Ver", icon=ft.Icons.VISIBILITY, disabled=True, on_click=self._confirmar_filtro_torneo)
        
        def _cargar_datos_modal():
            try:
                bd = BaseDeDatos()
                ediciones = bd.obtener_ediciones()
                self.cache_ediciones_modal = ediciones
                
                nombres_unicos = sorted(list(set(e[1] for e in ediciones)))
                
                controles = []
                for nombre in nombres_unicos:
                    controles.append(
                        ft.ListTile(
                            title=ft.Text(nombre, size=14),
                            data=nombre,
                            on_click=self._seleccionar_campeonato_modal,
                            bgcolor="#2D2D2D",
                            shape=ft.RoundedRectangleBorder(radius=5)
                        )
                    )
                self.lv_torneos.controls = controles
                self.lv_torneos.update()
            except Exception as ex:
                print(f"Error cargando modal: {ex}")

        contenido_modal = ft.Container(
            width=500,
            height=300,
            content=ft.Row(
                controls=[
                    ft.Column(
                        expand=1,
                        controls=[
                            ft.Text("Torneo", weight=ft.FontWeight.BOLD),
                            ft.Container(content=self.lv_torneos, border=ft.border.all(1, "white24"), border_radius=5, padding=5)
                        ]
                    ),
                    ft.VerticalDivider(width=20, color="white24"),
                    ft.Column(
                        expand=1,
                        controls=[
                            ft.Text("Año", weight=ft.FontWeight.BOLD),
                            ft.Container(content=self.lv_anios, border=ft.border.all(1, "white24"), border_radius=5, padding=5)
                        ]
                    )
                ]
            )
        )

        self.dlg_modal = ft.AlertDialog(
            modal=True,
            title=ft.Text("Filtrar por Torneo"),
            content=contenido_modal,
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self.page.close(self.dlg_modal)),
                self.btn_ver_torneo
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self.page.open(self.dlg_modal)
        threading.Thread(target=_cargar_datos_modal, daemon=True).start()

    def _seleccionar_campeonato_modal(self, e):
        """Al clickear un torneo, filtra y muestra sus años disponibles"""
        nombre_sel = e.control.data
        self.temp_campeonato_sel = nombre_sel
        
        # Resaltar selección visualmente
        for c in self.lv_torneos.controls:
            c.bgcolor = "blue" if c.data == nombre_sel else "#2D2D2D"
        self.lv_torneos.update()
        
        # Filtrar años
        anios = sorted([ed[2] for ed in self.cache_ediciones_modal if ed[1] == nombre_sel], reverse=True)
        
        # Llenar lista de años
        controles_anios = []
        for anio in anios:
            controles_anios.append(
                ft.ListTile(
                    title=ft.Text(str(anio), size=14),
                    data=anio,
                    on_click=self._seleccionar_anio_modal,
                    bgcolor="#2D2D2D",
                    shape=ft.RoundedRectangleBorder(radius=5)
                )
            )
        self.lv_anios.controls = controles_anios
        self.lv_anios.update()
        
        # Resetear selección de año y botón
        self.temp_anio_sel = None
        self.btn_ver_torneo.disabled = True
        self.btn_ver_torneo.update()

    def _seleccionar_anio_modal(self, e):
        """Al clickear un año, habilita el botón Ver"""
        anio_sel = e.control.data
        self.temp_anio_sel = anio_sel
        
        # Resaltar selección
        for c in self.lv_anios.controls:
            c.bgcolor = "blue" if c.data == anio_sel else "#2D2D2D"
        self.lv_anios.update()
        
        self.btn_ver_torneo.disabled = False
        self.btn_ver_torneo.update()

    
    def _confirmar_filtro_torneo(self, e):
        """Busca el ID de la edición seleccionada y aplica el filtro"""
        if self.temp_campeonato_sel and self.temp_anio_sel:
            edicion_encontrada = None
            for ed in self.cache_ediciones_modal:
                if ed[1] == self.temp_campeonato_sel and ed[2] == self.temp_anio_sel:
                    edicion_encontrada = ed[0] 
                    break
            
            if edicion_encontrada:
                self.filtro_partidos = 'torneo'
                self.filtro_edicion_id = edicion_encontrada
                
                # Actualizar Título
                self.txt_titulo_partidos.value = f"Partidos del torneo {self.temp_campeonato_sel} {self.temp_anio_sel}"
                self.txt_titulo_partidos.update()
                
                # Actualizar botones
                self.btn_todos.bgcolor = "#333333"
                self.btn_jugados.bgcolor = "#333333"
                self.btn_por_jugar.bgcolor = "#333333"
                self.btn_por_torneo.bgcolor = "blue"
                self.btn_sin_pronosticar.bgcolor = "#333333"
                
                self.btn_todos.update()
                self.btn_jugados.update()
                self.btn_por_jugar.update()
                self.btn_por_torneo.update()
                self.btn_sin_pronosticar.update()
                
                self.page.close(self.dlg_modal)
                self._recargar_datos(actualizar_partidos=True)

    # --- FUNCIONES ABM TORNEOS ---
    def _limpiar_formulario_torneo(self, e=None):
        """Limpia inputs, deselecciona la fila y resetea variables"""
        self.input_torneo_nombre.value = ""
        if self.dd_torneo_anio.options:
             self.dd_torneo_anio.value = self.dd_torneo_anio.options[0].key
             
        if self.fila_seleccionada_ref:
            self.fila_seleccionada_ref.selected = False
            self.fila_seleccionada_ref.color = None
            try:
                self.fila_seleccionada_ref.update()
            except: pass
            
        self.fila_seleccionada_ref = None
        self.edicion_seleccionada_id = None # Torneo deseleccionado
        
        # --- LÓGICA ETIQUETA ---
        # Si hay partido seleccionado Y NO hay torneo seleccionado -> Mostrar
        if self.partido_seleccionado_id is not None:
            self.txt_instruccion.visible = True
        else:
            self.txt_instruccion.visible = False
        
        self.page.update()

    def _agregar_torneo(self, e):
        def _tarea():
            self.loading_torneos_admin.visible = True # Feedback visual inmediato
            self.page.update()
            self._bloquear_ui_torneos(True)
            try:
                nombre = self.input_torneo_nombre.value.strip()
                anio_str = self.dd_torneo_anio.value

                if not nombre or not anio_str:
                    GestorMensajes.mostrar(self.page, "Atención", "Complete nombre y año.", "error")
                    self.loading_torneos_admin.visible = False
                    self.page.update()
                    return
                
                bd = BaseDeDatos()
                bd.crear_torneo(nombre, int(anio_str))
                GestorMensajes.mostrar(self.page, "Éxito", "Torneo creado.", "exito")
                self._limpiar_formulario_torneo()
                
                self._recargar_datos(actualizar_torneos=True, actualizar_partidos=False)
                
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", str(ex), "error")
                self.loading_torneos_admin.visible = False
                self.page.update()
            finally:
                self._bloquear_ui_torneos(False)

        threading.Thread(target=_tarea, daemon=True).start()

    def _bloquear_botones_filtros(self, bloquear):
        """Habilita o deshabilita los botones de filtro de partidos."""
        self.btn_todos.disabled = bloquear
        self.btn_jugados.disabled = bloquear
        self.btn_por_jugar.disabled = bloquear
        self.btn_por_torneo.disabled = bloquear
        self.btn_sin_pronosticar.disabled = bloquear

    def _editar_torneo(self, e):
        def _tarea():
            self.loading_torneos_admin.visible = True
            self.loading_partidos.visible = True 
            self.loading_admin.visible = True 
            self.page.update()
            
            self._bloquear_ui_torneos(True)
            self.procesando_partidos = True 
            
            self.editando_torneo = True

            try:
                if not self.edicion_seleccionada_id:
                    GestorMensajes.mostrar(self.page, "Atención", "Seleccione un torneo para editar.", "error")
                    self.loading_torneos_admin.visible = False
                    self.loading_partidos.visible = False
                    self.loading_admin.visible = False
                    self.editando_torneo = False 
                    self.page.update()
                    return

                nombre = self.input_torneo_nombre.value.strip()
                anio_str = self.dd_torneo_anio.value
                
                if not nombre or not anio_str:
                     GestorMensajes.mostrar(self.page, "Error", "Complete todos los campos.", "error")
                     self.loading_torneos_admin.visible = False
                     self.loading_partidos.visible = False
                     self.loading_admin.visible = False
                     self.editando_torneo = False 
                     self.page.update()
                     return

                bd = BaseDeDatos()
                bd.editar_torneo(self.edicion_seleccionada_id, nombre, int(anio_str))
                GestorMensajes.mostrar(self.page, "Éxito", "Torneo modificado.", "exito")
                self._limpiar_formulario_torneo()
                
                # RECARGA: Actualiza todo (Torneos, Partidos User y Partidos Admin)
                self._recargar_datos(actualizar_torneos=True, actualizar_partidos=True, actualizar_admin=True)
                
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", str(ex), "error")
                self.loading_torneos_admin.visible = False
                self.loading_partidos.visible = False
                self.loading_admin.visible = False
                self.editando_torneo = False 
                self.page.update()
            finally:
                self._bloquear_ui_torneos(False)
                self.procesando_partidos = False

        threading.Thread(target=_tarea, daemon=True).start()

    def _eliminar_torneo(self, e):
        def _tarea():
            self.loading_torneos_admin.visible = True
            self.page.update()
            self._bloquear_ui_torneos(True)
            try:
                if not self.edicion_seleccionada_id:
                    GestorMensajes.mostrar(self.page, "Atención", "Seleccione un torneo para eliminar.", "error")
                    self.loading_torneos_admin.visible = False
                    self.page.update()
                    return

                bd = BaseDeDatos()
                bd.eliminar_torneo(self.edicion_seleccionada_id)
                GestorMensajes.mostrar(self.page, "Éxito", "Torneo eliminado.", "exito")
                self._limpiar_formulario_torneo()
                
                self._recargar_datos(actualizar_torneos=True, actualizar_partidos=False)
                
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", str(ex), "error")
                self.loading_torneos_admin.visible = False
                self.page.update()
            finally:
                self._bloquear_ui_torneos(False)
        
        threading.Thread(target=_tarea, daemon=True).start()

    def _agregar_partido(self, e):
        def _tarea_agregar_partido():
            self.loading_admin.visible = True
            self.loading_partidos.visible = True 
            self.page.update()
            
            self._bloquear_ui_partidos(True) 
            
            try:
                if not self.edicion_seleccionada_id:
                    GestorMensajes.mostrar(self.page, "Atención", "Debe seleccionar un Torneo.", "error")
                    self.loading_admin.visible = False 
                    self.loading_partidos.visible = False
                    self.page.update()
                    return

                rival = self.input_rival.value.strip()
                fecha = self.date_picker.value 
                hora = self.time_picker.value  
                goles_cai_str = self.input_goles_cai.value.strip()
                goles_rival_str = self.input_goles_rival.value.strip()

                if not rival:
                    GestorMensajes.mostrar(self.page, "Atención", "Debe ingresar el nombre del rival.", "error")
                    self.loading_admin.visible = False
                    self.loading_partidos.visible = False
                    self.page.update()
                    return
                
                if not fecha:
                    GestorMensajes.mostrar(self.page, "Atención", "Debe seleccionar la fecha del partido.", "error")
                    self.loading_admin.visible = False
                    self.loading_partidos.visible = False
                    self.page.update()
                    return

                if hora and self.txt_hora_display.value != "---":
                    hora_final = hora
                else:
                    hora_final = datetime.min.time()

                fecha_hora_partido = datetime.combine(fecha, hora_final)
                ahora = datetime.now()
                
                bd = BaseDeDatos()

                if bd.existe_partido_fecha(fecha.date()):
                    GestorMensajes.mostrar(self.page, "Error", "Ya existe un partido registrado en esa fecha.", "error")
                    self.loading_admin.visible = False
                    self.loading_partidos.visible = False
                    self.page.update()
                    return

                goles_cai = None
                goles_rival = None

                if fecha_hora_partido < ahora:
                    if not goles_cai_str or not goles_rival_str:
                        GestorMensajes.mostrar(self.page, "Faltan Resultados", "Obligatorio ingresar goles para partidos pasados.", "error")
                        self.loading_admin.visible = False
                        self.loading_partidos.visible = False
                        self.page.update()
                        return
                    try:
                        goles_cai = int(goles_cai_str)
                        goles_rival = int(goles_rival_str)
                    except ValueError:
                        GestorMensajes.mostrar(self.page, "Error", "Los goles deben ser números enteros.", "error")
                        self.loading_admin.visible = False
                        self.loading_partidos.visible = False
                        self.page.update()
                        return
                else:
                    if goles_cai_str and goles_rival_str:
                        try:
                            goles_cai = int(goles_cai_str)
                            goles_rival = int(goles_rival_str)
                        except ValueError:
                            GestorMensajes.mostrar(self.page, "Error", "Los goles deben ser números enteros.", "error")
                            self.loading_admin.visible = False
                            self.loading_partidos.visible = False
                            self.page.update()
                            return
                    elif goles_cai_str or goles_rival_str:
                        GestorMensajes.mostrar(self.page, "Error", "Si ingresa goles, complete ambos campos.", "error")
                        self.loading_admin.visible = False
                        self.loading_partidos.visible = False
                        self.page.update()
                        return

                bd.insertar_partido(rival, fecha_hora_partido, goles_cai, goles_rival, edicion_id=self.edicion_seleccionada_id)
                GestorMensajes.mostrar(self.page, "Éxito", "Partido agregado correctamente.", "exito")
                self._limpiar_formulario_partido()
                
                # RECARGA: Actualiza ambas tablas
                self._recargar_datos(actualizar_partidos=True, actualizar_admin=True)

            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", f"Ocurrió un error al guardar: {ex}", "error")
                self.loading_admin.visible = False
                self.loading_partidos.visible = False
                self.page.update()
            finally:
                self._bloquear_ui_partidos(False) 

        threading.Thread(target=_tarea_agregar_partido, daemon=True).start()

    def _editar_partido(self, e):
        def _tarea():
            self.loading_admin.visible = True
            self.loading_partidos.visible = True 
            self.page.update()
            
            self._bloquear_ui_partidos(True)
            try:
                if not self.partido_seleccionado_id:
                    GestorMensajes.mostrar(self.page, "Atención", "Seleccione un partido para editar.", "error")
                    self.loading_admin.visible = False
                    self.loading_partidos.visible = False
                    self.page.update()
                    return
                
                if not self.edicion_seleccionada_id:
                    GestorMensajes.mostrar(self.page, "Atención", "Seleccione el Torneo correspondiente.", "error")
                    self.loading_admin.visible = False
                    self.loading_partidos.visible = False
                    self.page.update()
                    return

                rival = self.input_rival.value.strip()
                fecha = self.date_picker.value
                hora = self.time_picker.value
                gc_str = self.input_goles_cai.value.strip()
                gr_str = self.input_goles_rival.value.strip()

                if not rival or not fecha:
                    GestorMensajes.mostrar(self.page, "Error", "Complete rival y fecha.", "error")
                    self.loading_admin.visible = False
                    self.loading_partidos.visible = False
                    self.page.update()
                    return

                if hora and self.txt_hora_display.value != "---":
                    hora_final = hora
                else:
                    hora_final = datetime.min.time()

                fecha_hora = datetime.combine(fecha, hora_final)
                
                gc = int(gc_str) if gc_str else None
                gr = int(gr_str) if gr_str else None

                bd = BaseDeDatos()
                bd.editar_partido(self.partido_seleccionado_id, rival, fecha_hora, gc, gr, self.edicion_seleccionada_id)
                
                bd.eliminar_rivales_huerfanos()
                
                GestorMensajes.mostrar(self.page, "Éxito", "Partido modificado.", "exito")
                self._limpiar_formulario_partido()
                
                # CORRECCIÓN: Como admin tocó un partido, actualizamos TODO, incluyendo Ranking.
                self._recargar_datos(actualizar_partidos=True, actualizar_admin=True, actualizar_ranking=True)
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", str(ex), "error")
                self.loading_admin.visible = False
                self.loading_partidos.visible = False
                self.page.update()
            finally:
                self._bloquear_ui_partidos(False)

        threading.Thread(target=_tarea, daemon=True).start()

    def _eliminar_partido(self, e):
        def _tarea():
            self.loading_admin.visible = True
            self.loading_partidos.visible = True 
            self.page.update()
            
            self._bloquear_ui_partidos(True)
            try:
                if not self.partido_seleccionado_id:
                    GestorMensajes.mostrar(self.page, "Atención", "Seleccione un partido para eliminar.", "error")
                    self.loading_admin.visible = False
                    self.loading_partidos.visible = False
                    self.page.update()
                    return

                bd = BaseDeDatos()
                bd.eliminar_partido(self.partido_seleccionado_id)
                
                bd.eliminar_rivales_huerfanos()
                
                GestorMensajes.mostrar(self.page, "Éxito", "Partido eliminado.", "exito")
                self._limpiar_formulario_partido()
                
                # RECARGA: Actualiza ambas tablas
                self._recargar_datos(actualizar_partidos=True, actualizar_admin=True)
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", str(ex), "error")
                self.loading_admin.visible = False
                self.loading_partidos.visible = False
                self.page.update()
            finally:
                self._bloquear_ui_partidos(False)

        threading.Thread(target=_tarea, daemon=True).start()

    def _fecha_cambiada(self, e):
        """Actualiza el texto con la fecha seleccionada y valida goles"""
        if self.date_picker.value:
            self.txt_fecha_display.value = self.date_picker.value.strftime("%d/%m/%Y")
            self._actualizar_estado_goles() # <--- NUEVA LLAMADA
            self.page.update()

    def _hora_cambiada(self, e):
        """Actualiza el texto con la hora seleccionada y valida goles"""
        if self.time_picker.value:
            self.txt_hora_display.value = self.time_picker.value.strftime("%H:%M")
            self._actualizar_estado_goles() # <--- NUEVA LLAMADA
            self.page.update()

    def _seleccionar_torneo(self, e):
        if self.cargando_torneos or self.procesando_torneos:
            GestorMensajes.mostrar(self.page, "Espere", "Actualizando lista de torneos...", "info")
            return

        fila_cliqueada = e.control
        
        for fila in self.tabla_torneos.rows:
            if fila == fila_cliqueada:
                fila.selected = True
                fila.color = ft.Colors.with_opacity(0.5, Estilos.COLOR_ROJO_CAI)
                self.fila_seleccionada_ref = fila 
                self.edicion_seleccionada_id = fila.data # Torneo seleccionado
            else:
                fila.selected = False
                fila.color = None

        nombre_torneo = fila_cliqueada.cells[0].content.content.value 
        anio_torneo = fila_cliqueada.cells[1].content.value

        self.input_torneo_nombre.value = nombre_torneo
        self.dd_torneo_anio.value = str(anio_torneo)
        
        # --- LÓGICA ETIQUETA ---
        # Se seleccionó torneo -> etiqueta oculta
        self.txt_instruccion.visible = False
        
        self.page.update()

    def _seleccionar_partido(self, e):
        # 1. Validación de Bloqueo
        if self.cargando_partidos or self.procesando_partidos:
            GestorMensajes.mostrar(self.page, "Espere", "Actualizando lista de partidos...", "info")
            return

        fila_cliqueada = e.control
        
        datos_partido = fila_cliqueada.data
        edicion_id_objetivo = datos_partido['edicion_id']

        # 2. Selección Iterativa TABLA PARTIDOS
        for fila in self.tabla_partidos_admin.rows:
            if fila == fila_cliqueada:
                fila.selected = True
                fila.color = ft.Colors.with_opacity(0.5, Estilos.COLOR_ROJO_CAI)
                self.fila_partido_ref = fila
                self.partido_seleccionado_id = datos_partido['id']
                
                # Cargar formulario Partido
                self.input_rival.value = datos_partido['rival']
                if datos_partido['fecha']:
                    self.date_picker.value = datos_partido['fecha']
                    self.time_picker.value = datos_partido['fecha'].time()
                    self.txt_fecha_display.value = datos_partido['fecha'].strftime("%d/%m/%Y")
                    self.txt_hora_display.value = datos_partido['fecha'].strftime("%H:%M")
                
                self.input_goles_cai.value = str(datos_partido['goles_cai']) if datos_partido['goles_cai'] is not None else ""
                self.input_goles_rival.value = str(datos_partido['goles_rival']) if datos_partido['goles_rival'] is not None else ""
                
            else:
                fila.selected = False
                fila.color = None

        # 3. Selección Automática TABLA TORNEOS (Sincronización)
        for fila_torneo in self.tabla_torneos.rows:
            if fila_torneo.data == edicion_id_objetivo:
                fila_torneo.selected = True
                fila_torneo.color = ft.Colors.with_opacity(0.5, Estilos.COLOR_ROJO_CAI)
                self.fila_seleccionada_ref = fila_torneo
                self.edicion_seleccionada_id = edicion_id_objetivo
                
                nombre_torneo = fila_torneo.cells[0].content.content.value 
                anio_torneo = fila_torneo.cells[1].content.value
                self.input_torneo_nombre.value = nombre_torneo
                self.dd_torneo_anio.value = str(anio_torneo)
            else:
                fila_torneo.selected = False
                fila_torneo.color = None

        # --- LÓGICA ETIQUETA ---
        # Si seleccionamos partido -> se auto-seleccionó torneo -> etiqueta oculta
        self.txt_instruccion.visible = False
        
        self._actualizar_estado_goles()
        self.page.update()

    def _cargar_datos_async(self):
        # Activamos bandera de carga antes de iniciar el hilo
        self.cargando_datos = True 
        
        def _tarea_en_segundo_plano():
            time.sleep(0.5) 
            
            # Limpiamos referencias
            self.fila_seleccionada_ref = None
            self.edicion_seleccionada_id = None
            self.fila_partido_ref = None
            self.partido_seleccionado_id = None

            try:
                bd = BaseDeDatos()
                if not self.editando_torneo:
                    datos_ranking = bd.obtener_ranking()
                datos_partidos = bd.obtener_partidos()
                datos_ediciones = bd.obtener_ediciones()

                # --- PROCESAR DATOS (CÓDIGO IGUAL AL ANTERIOR) ---
                filas_tabla_ranking = []
                for i, fila in enumerate(datos_ranking, start=1):
                    filas_tabla_ranking.append(ft.DataRow(cells=[ft.DataCell(ft.Text(f"{i}º", weight=ft.FontWeight.BOLD, color="white")), ft.DataCell(ft.Container(content=ft.Text(str(fila[0]), weight=ft.FontWeight.BOLD, color="white", no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS), width=80, alignment=ft.alignment.center_left)), ft.DataCell(ft.Text(str(fila[1]), weight=ft.FontWeight.BOLD, color="yellow", size=16)), ft.DataCell(ft.Text(str(fila[2]), color="white70")), ft.DataCell(ft.Text(str(fila[3]), color="white70")), ft.DataCell(ft.Text(str(fila[4]), color="white70"))]))

                filas_tabla_partidos = []
                filas_tabla_admin = [] 
                for fila in datos_partidos:
                    p_id = fila[0]
                    rival = fila[1]
                    fecha_obj = fila[2]
                    torneo = fila[3]
                    gc = fila[4]
                    gr = fila[5]
                    ed_id = fila[6]
                    fecha_str = fecha_obj.strftime("%d/%m/%Y %H:%M") if fecha_obj else "Sin fecha"

                    filas_tabla_partidos.append(ft.DataRow(cells=[ft.DataCell(ft.Container(content=ft.Text(str(rival), weight=ft.FontWeight.BOLD, color="white", no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS), width=100, alignment=ft.alignment.center_left)), ft.DataCell(ft.Text(fecha_str, color="white70")), ft.DataCell(ft.Container(content=ft.Text(str(torneo), color="yellow", weight=ft.FontWeight.BOLD), width=150, alignment=ft.alignment.center_left))]))
                    
                    filas_tabla_admin.append(
                        ft.DataRow(
                            cells=[ft.DataCell(ft.Container(content=ft.Text(str(rival), weight=ft.FontWeight.BOLD, color="white", no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS), width=100, alignment=ft.alignment.center_left)), ft.DataCell(ft.Text(fecha_str, color="white70")), ft.DataCell(ft.Container(content=ft.Text(str(torneo), color="yellow", weight=ft.FontWeight.BOLD), width=150, alignment=ft.alignment.center_left))],
                            data={'id': p_id, 'rival': rival, 'fecha': fecha_obj, 'goles_cai': gc, 'goles_rival': gr, 'edicion_id': ed_id},
                            on_select_changed=self._seleccionar_partido,
                            selected=False
                        )
                    )

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
                
            except Exception as e:
                print(f"Error: {e}")
            
            finally:
                self.loading.visible = False
                self.cargando_datos = False # LIBERAMOS LA BANDERA
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