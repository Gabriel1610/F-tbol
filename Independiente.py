import flet as ft
import os
import time
import threading
import requests
import smtplib
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from tarjeta_acceso import TarjetaAcceso
from estilos import Estilos
from base_de_datos import BaseDeDatos
from datetime import datetime
from ventana_mensaje import GestorMensajes

# Constantes
NOMBRE_ICONO = "Escudo.ico"
MAXIMA_CANTIDAD_DE_PUNTOS = 9
ID_INDEPENDIENTE = 10078  # ID real de Independiente en FotMob
URL_API = "https://www.fotmob.com/api/teams"
CANT_PARTIDOS_A_SINCRONIZAR = 5
REMITENTE = "gabrielydeindependiente@gmail.com"
PASSWORD = "vjpz rjcz nkgq zqaq"
DÍAS_NOTIFICACIÓN = 3  # Días antes del partido para notificar

class SistemaIndependiente:
    def __init__(self, page: ft.Page):
        self.page = page
        self._configurar_ventana()
        self._construir_interfaz_login()
        threading.Thread(target=self._servicio_notificaciones_background, daemon=True).start()

    def _servicio_notificaciones_background(self):
        """
        Revisa si hay usuarios sin pronosticar partidos próximos y les envía un correo.
        Se ejecuta una sola vez al iniciar la app.
        """
        # Esperamos unos segundos para no ralentizar el inicio visual de la app
        time.sleep(5) 
        
        try:
            print("🔔 Verificando notificaciones pendientes...")
            bd = BaseDeDatos()
            pendientes = bd.obtener_pendientes_notificacion(dias=DÍAS_NOTIFICACIÓN)
            
            if not pendientes:
                print("   -> No hay notificaciones para enviar hoy.")
                return

            # Agrupar datos por usuario: {id_usuario: {'email': x, 'user': x, 'partidos': []}}
            usuarios_a_notificar = {}
            
            for fila in pendientes:
                uid, uname, email, rival, fecha = fila
                
                if uid not in usuarios_a_notificar:
                    usuarios_a_notificar[uid] = {
                        'username': uname,
                        'email': email,
                        'partidos': []
                    }
                
                # Formato legible de fecha
                fecha_str = fecha.strftime('%d/%m %H:%M')
                usuarios_a_notificar[uid]['partidos'].append(f"{rival} ({fecha_str})")

            # Enviar correos
            cantidad_enviados = 0
            
            for uid, datos in usuarios_a_notificar.items():
                destinatario = datos['email']
                username = datos['username']
                lista_partidos = "\n".join([f"- {p}" for p in datos['partidos']])
                
                asunto = "⚠️ Recordatorio: Partidos sin pronosticar - CAI"
                cuerpo = f"""Hola {username},

Te recordamos que faltan menos de {DÍAS_NOTIFICACIÓN} días para los siguientes partidos y aún no has cargado tu pronóstico:

{lista_partidos}

¡No te olvides de sumar puntos!
Ingresa a la aplicación para dejar tu resultado.

Saludos,
El Sistema.
                        """
                # Envío SMTP
                try:
                    msg = MIMEMultipart()
                    msg['From'] = REMITENTE
                    msg['To'] = destinatario
                    msg['Subject'] = asunto
                    msg.attach(MIMEText(cuerpo, 'plain'))
                    
                    server = smtplib.SMTP('smtp.gmail.com', 587)
                    server.starttls()
                    server.login(REMITENTE, PASSWORD)
                    server.send_message(msg)
                    server.quit()
                    
                    # Si se envió bien, actualizamos la BD para no molestar más hoy
                    bd.marcar_usuario_notificado(uid)
                    cantidad_enviados += 1
                    print(f"   -> Correo enviado a {username}")
                    
                except Exception as e_mail:
                    print(f"   [!] Error enviando a {username}: {e_mail}")

            if cantidad_enviados > 0:
                print(f"🔔 Se enviaron {cantidad_enviados} notificaciones exitosamente.")

        except Exception as e:
            print(f"Error en servicio de notificaciones: {e}")

    def _sincronizar_fixture_api(self):
        """
        Sincronización Inteligente:
        1. Pasado: Actualiza resultados SOLO si faltan.
        2. Futuro: Sincroniza próximos partidos.
        3. Finalización: Si un torneo tiene partidos jugados pero ya no tiene futuros, se marca como finalizado.
        """
        print("Iniciando sincronización (Lógica Estricta)...")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }
        
        params = {
            "id": ID_INDEPENDIENTE,
            "timezone": "America/Argentina/Buenos_Aires",
            "ccode3": "ARG"
        }
        
        bd = BaseDeDatos()
        
        try:
            response = requests.get(URL_API, headers=headers, params=params, timeout=15)
            if response.status_code != 200:
                print(f"Error API: Status {response.status_code}")
                return

            data = response.json()
            fixtures_obj = data.get("fixtures", {})
            partidos_unicos = {}

            # Recolección de datos
            def agregar_partidos(lista_origen):
                if not lista_origen: return
                for m in lista_origen:
                    if isinstance(m, dict):
                        m_id = m.get("id")
                        if m_id: partidos_unicos[m_id] = m

            agregar_partidos(fixtures_obj.get("results", []))
            agregar_partidos(fixtures_obj.get("fixtures", []))
            raw_all = fixtures_obj.get("allFixtures")
            if isinstance(raw_all, list): agregar_partidos(raw_all)
            elif isinstance(raw_all, dict):
                for val in raw_all.values():
                    if isinstance(val, list): agregar_partidos(val)

            if not partidos_unicos: return

            # Clasificación
            jugados = []
            por_jugar = []
            
            for match in partidos_unicos.values():
                datos = self._procesar_partido_fotmob(match)
                if not datos: continue
                
                status = match.get("status", {})
                finished = status.get("finished", False)
                cancelled = status.get("cancelled", False)
                
                if cancelled: continue 

                if finished:
                    jugados.append(datos)
                else:
                    por_jugar.append(datos)
            
            # Ordenamiento
            jugados.sort(key=lambda x: x['fecha'], reverse=True)
            por_jugar.sort(key=lambda x: x['fecha'], reverse=False)
            
            # --- NUEVA LÓGICA: REGLA DE 21:00 H (PLACEHOLDER) ---
            ahora = datetime.now()
            
            for i, p in enumerate(por_jugar):
                fecha = p['fecha']
                
                # Verificamos si la hora es exactamente 21:00:00
                if fecha.hour == 21 and fecha.minute == 0 and fecha.second == 0:
                    
                    # Condición 1: NO está en los próximos 3 partidos (índices 0, 1, 2 son los próximos)
                    no_es_proximo = (i >= 3)
                    
                    # Condición 2: Faltan más de 7 días
                    dias_faltantes = (fecha - ahora).days
                    es_lejano = (dias_faltantes > 7)
                    
                    if no_es_proximo or es_lejano:
                        # Cumple ambas condiciones: Es un placeholder -> Guardar como 00:00:00
                        p['fecha'] = fecha.replace(hour=0, minute=0, second=0, microsecond=0)
                        # print(f"DEBUG: Partido vs {p['rival']} marcado como S/H (Indice {i}, faltan {dias_faltantes} días)")

            # --- 1. ACTUALIZACIÓN DE PARTIDOS ---
            if jugados:
                print(f"Procesando {len(jugados)} partidos jugados...")
                bd.actualizar_resultados_pendientes(jugados)

            proximos_5 = por_jugar[:CANT_PARTIDOS_A_SINCRONIZAR]
            if proximos_5:
                print(f"Sincronizando próximos {len(proximos_5)} partidos...")
                bd.sincronizar_proximos_partidos(proximos_5)
            
            # --- 2. LÓGICA DE FINALIZACIÓN DE TORNEOS ---
            # Identificamos qué torneos tienen partidos en el futuro
            torneos_con_futuro = set()
            for p in por_jugar:
                torneos_con_futuro.add((p['torneo'], p['anio']))
            
            # Identificamos qué torneos tienen partidos en el pasado
            torneos_con_pasado = set()
            for p in jugados:
                torneos_con_pasado.add((p['torneo'], p['anio']))
            
            # Si un torneo está en el pasado pero NO en el futuro, asumimos que terminó
            posibles_finalizados = torneos_con_pasado - torneos_con_futuro
            
            if posibles_finalizados:
                print(f"Verificando finalización de {len(posibles_finalizados)} torneos...")
                for nombre, anio in posibles_finalizados:
                    # Llamamos a la BD para marcarlo como TRUE si existe
                    bd.marcar_edicion_finalizada(nombre, anio)

            print("Sincronización completada.")
            
        except Exception as e:
            print(f"Error crítico sincronizando FotMob: {e}")
        
        finally:
            if hasattr(self, 'dlg_cargando_inicio') and self.dlg_cargando_inicio.open:
                self.page.close(self.dlg_cargando_inicio)
            
            print("Cargando interfaz...")
            self._recargar_datos(
                actualizar_partidos=True, 
                actualizar_pronosticos=True, 
                actualizar_ranking=True,
                actualizar_copas=True, # Recargar copas por si alguno finalizó recién
                actualizar_admin=True 
            )

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

    def _toggle_sin_pronosticar(self, e):
        """Activa o desactiva el filtro 'Sin Pronosticar' sumándose a los demás."""
        self.filtro_sin_pronosticar = not self.filtro_sin_pronosticar
        self._actualizar_botones_partidos_visual()
        self._actualizar_titulo_partidos()
        self._recargar_datos(actualizar_partidos=True, actualizar_copas=False)

    def _gestionar_accion_boton_filtro(self, tipo):
        """
        Gestiona la lógica 'toggle' de los botones específicos (Torneo, Equipo, Usuario).
        - Si el filtro ya está activo -> Lo desactiva.
        - Si no está activo -> Abre el modal para seleccionar.
        """
        if tipo == 'torneo':
            if self.filtro_pron_torneo is not None:
                # Desactivar
                self.filtro_pron_torneo = None
                self._actualizar_botones_pronosticos_visual() # Pinta de nuevo los colores correctos
                self._actualizar_titulo_pronosticos()
                self._recargar_datos(actualizar_pronosticos=True)
            else:
                # Abrir Modal
                self._abrir_selector_torneo_pronosticos(None)
                
        elif tipo == 'equipo':
            if self.filtro_pron_equipo is not None:
                # Desactivar
                self.filtro_pron_equipo = None
                self._actualizar_botones_pronosticos_visual()
                self._actualizar_titulo_pronosticos()
                self._recargar_datos(actualizar_pronosticos=True)
            else:
                # Abrir Modal
                self._abrir_selector_equipo_pronosticos(None)
                
        elif tipo == 'usuario':
            if self.filtro_pron_usuario is not None:
                # Desactivar
                self.filtro_pron_usuario = None
                self._actualizar_botones_pronosticos_visual()
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

    def _abrir_modal_falso_profeta(self, e):
        """Muestra el ranking de 'Falso Profeta' (Quienes pronostican victoria y pierden/empatan)."""
        try:
            bd = BaseDeDatos()
            datos = bd.obtener_ranking_falso_profeta(self.filtro_ranking_edicion_id, self.filtro_ranking_anio)
            
            filas = []
            for i, fila in enumerate(datos, start=1):
                user = fila[0]
                victorias_pred = fila[1]
                porcentaje_acierto = fila[2]
                
                txt_porcentaje = f"{porcentaje_acierto:.1f}%".replace('.', ',')
                
                # En Falso Profeta, MENOS acierto es PEOR (Más falso profeta)
                if porcentaje_acierto <= 20: color_txt = "red"
                elif porcentaje_acierto <= 50: color_txt = "orange"
                else: color_txt = "green"
                
                filas.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(f"{i}º", color="white", weight=ft.FontWeight.BOLD)),
                    ft.DataCell(ft.Text(user, color="white")),
                    ft.DataCell(ft.Container(content=ft.Text(str(victorias_pred), color="cyan"), alignment=ft.alignment.center)),
                    ft.DataCell(ft.Container(content=ft.Text(txt_porcentaje, color=color_txt, weight=ft.FontWeight.BOLD), alignment=ft.alignment.center)),
                ]))

            tabla = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text("Pos")),
                    ft.DataColumn(ft.Text("Usuario")),
                    ft.DataColumn(ft.Text("Pred. Victoria", tooltip="Veces que dijo que ganábamos"), numeric=True),
                    ft.DataColumn(ft.Text("% Acierto", tooltip="Porcentaje de veces que realmente ganamos"), numeric=True),
                ],
                rows=filas,
                heading_row_color="black",
                data_row_color={"hoverED": "#1A1A1A"},
                border=ft.border.all(1, "white10"),
                column_spacing=20
            )
            
            dlg = ft.AlertDialog(
                title=ft.Text("Ranking Falso Profeta 🤡"),
                content=ft.Column([
                    # --- AQUÍ ESTÁ EL TEXTO NUEVO ---
                    ft.Text("Usuarios que más le erran cuando dicen que el Rojo va a ganar.", size=12, color="white70"),
                    
                    ft.Container(
                        height=400,
                        content=ft.Column(
                            controls=[tabla],
                            scroll=ft.ScrollMode.AUTO
                        )
                    )
                ], tight=True),
                actions=[ft.TextButton("Cerrar", on_click=lambda e: self.page.close(dlg))]
            )
            self.page.open(dlg)

        except Exception as ex:
            GestorMensajes.mostrar(self.page, "Error", f"No se pudo cargar falso profeta: {ex}", "error")

    def _seleccionar_fila_ranking(self, usuario):
        """Marca visualmente la fila sin recargar datos ni activar selección nativa."""
        # 1. Actualizar estado
        if self.usuario_seleccionado_ranking == usuario:
            self.usuario_seleccionado_ranking = None
        else:
            self.usuario_seleccionado_ranking = usuario
            
        # 2. Actualizar color manualmente
        for row in self.tabla_estadisticas.rows:
            if row.data == self.usuario_seleccionado_ranking:
                row.color = "#8B0000"
                # row.selected = True  <--- ¡ESTO NO LO PONGAS!
            else:
                row.color = None
                # row.selected = False <--- ESTO TAMPOCO
        
        self.tabla_estadisticas.update()

    def _seleccionar_fila_pronostico(self, row_key):
        """Marca visualmente la fila sin recargar datos ni activar selección nativa."""
        # 1. Actualizar estado
        if self.pronostico_seleccionado_key == row_key:
            self.pronostico_seleccionado_key = None
        else:
            self.pronostico_seleccionado_key = row_key
            
        # 2. Actualizar color manualmente
        for row in self.tabla_pronosticos.rows:
            if row.data == self.pronostico_seleccionado_key:
                row.color = "#8B0000"
            else:
                row.color = None
                
        self.tabla_pronosticos.update()

    def _seleccionar_fila_pronostico(self, row_key):
        """Marca visualmente la fila sin recargar datos ni activar selección nativa."""
        # 1. Actualizar estado
        if self.pronostico_seleccionado_key == row_key:
            self.pronostico_seleccionado_key = None
        else:
            self.pronostico_seleccionado_key = row_key
            
        # 2. Actualizar color manualmente
        for row in self.tabla_pronosticos.rows:
            if row.data == self.pronostico_seleccionado_key:
                row.color = "#8B0000"
            else:
                row.color = None
                
        self.tabla_pronosticos.update()

    # --- PANTALLA 2: MENÚ PRINCIPAL ---

    def _ir_a_menu_principal(self, usuario):
        self.page.controls.clear()
        self.page.bgcolor = Estilos.COLOR_ROJO_CAI
        self.usuario_actual = usuario
        
        # --- BANDERAS Y ESTADOS ---
        self.cargando_partidos = False
        self.cargando_torneos = False
        self.procesando_partidos = False 
        self.procesando_torneos = False
        self.editando_torneo = False 
        self.pronosticos_sort_col_index = None
        self.pronosticos_sort_asc = True
        self.filtro_partidos = 'futuros'
        self.filtro_edicion_id = None 
        self.filtro_rival_id = None 
        self.filtro_pron_tiempo = 'todos' 
        self.filtro_pron_torneo = None 
        self.filtro_pron_equipo = None 
        self.filtro_pron_usuario = None 
        self.filtro_ranking_edicion_id = None
        self.filtro_ranking_nombre = None
        self.filtro_ranking_anio = None
        self.cache_ediciones_modal = [] 
        self.cache_rivales_modal = [] 
        self.temp_campeonato_sel = None 
        self.temp_anio_sel = None
        self.temp_rival_sel_id = None 
        self.temp_rival_sel_nombre = None
        self.temp_usuario_sel = None
        self.edicion_seleccionada_id = None
        self.fila_seleccionada_ref = None
        self.partido_seleccionado_id = None
        self.fila_partido_ref = None
        self.partido_a_pronosticar_id = None
        self.fila_pronostico_ref = None
        self.rival_seleccionado_id = None
        self.chk_usuarios_grafico = [] 
        self.chk_usuarios_grafico_lp = [] 
        self.usuario_grafico_barra_sel = None 
        self.usuario_seleccionado_ranking = None
        self.pronostico_seleccionado_key = None

        # NUEVAS VARIABLES DE ESTADO PARA FILTROS CONJUNTOS
        self.filtro_temporal = 'futuros'      # 'todos', 'jugados', 'futuros'
        self.filtro_edicion_id = None         # ID o None
        self.filtro_rival_id = None           # ID o None
        self.filtro_sin_pronosticar = False   # True o False

        # Variables de caché y temporales (igual que antes)
        self.cache_ediciones_modal = [] 
        self.cache_rivales_modal = [] 
        self.temp_campeonato_sel = None 
        self.temp_anio_sel = None
        self.temp_rival_sel_id = None 
        self.temp_rival_sel_nombre = None

        # --- SELECTORES ---
        carpeta_actual = os.path.dirname(os.path.abspath(__file__))
        ruta_img = os.path.join(carpeta_actual, NOMBRE_ICONO)

        self.page.appbar = ft.AppBar(
            leading=ft.Container(content=ft.Image(src=ruta_img, fit=ft.ImageFit.CONTAIN), padding=5),
            leading_width=50,
            title=ft.Text(f"Bienvenido, {usuario}", weight=ft.FontWeight.BOLD, color=Estilos.COLOR_ROJO_CAI),
            center_title=False, bgcolor="white", 
            actions=[ft.IconButton(icon=ft.icons.LOGOUT, tooltip="Cerrar Sesión", icon_color=Estilos.COLOR_ROJO_CAI, on_click=self._cerrar_sesion), ft.Container(width=10)]
        )

        # --- BARRAS DE CARGA ---
        self.loading = ft.ProgressBar(width=400, color="amber", bgcolor="#222222", visible=True)
        self.loading_partidos = ft.ProgressBar(width=400, color="amber", bgcolor="#222222", visible=False) 
        self.loading_pronosticos = ft.ProgressBar(width=400, color="amber", bgcolor="#222222", visible=False) 
        self.loading_admin = ft.ProgressBar(width=400, color="amber", bgcolor="#222222", visible=False)
        self.loading_torneos_admin = ft.ProgressBar(width=400, color="amber", bgcolor="#222222", visible=False)
        self.loading_copas = ft.ProgressBar(width=400, color="amber", bgcolor="#222222", visible=False)
        
        # --- CONTENEDOR 1: FILTROS ---
        self.btn_ranking_torneo = ft.ElevatedButton("Por torneo", icon=ft.icons.EMOJI_EVENTS, bgcolor="#333333", color="white", width=140, height=30, style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), on_click=self._abrir_selector_torneo_ranking)
        self.btn_ranking_anio = ft.ElevatedButton("Por año", icon=ft.icons.CALENDAR_MONTH, bgcolor="#333333", color="white", width=140, height=30, style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), on_click=self._abrir_selector_anio_ranking)

        self.contenedor_filtro_torneo = ft.Container(padding=ft.padding.all(10), border=ft.border.all(1, "white24"), border_radius=8, bgcolor="#1E1E1E", content=ft.Column(spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER, controls=[ft.Text("Filtros", size=11, weight=ft.FontWeight.BOLD, color="white54"), self.btn_ranking_torneo, self.btn_ranking_anio]))

        # --- CONTENEDOR 2: GRÁFICOS DE LÍNEA ---
        self.btn_grafico_puestos = ft.ElevatedButton("Por puestos", icon=ft.icons.SHOW_CHART, bgcolor="#333333", color="white", width=140, height=30, style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), on_click=self._abrir_selector_grafico_puestos)
        self.btn_grafico_linea_puntos = ft.ElevatedButton("Por puntos", icon=ft.icons.SHOW_CHART, bgcolor="#333333", color="white", width=140, height=30, style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), on_click=self._abrir_selector_grafico_linea_puntos)

        self.contenedor_graficos = ft.Container(padding=ft.padding.all(10), border=ft.border.all(1, "white24"), border_radius=8, bgcolor="#1E1E1E", content=ft.Column(spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER, controls=[ft.Text("Gráficos de línea", size=11, weight=ft.FontWeight.BOLD, color="white54"), self.btn_grafico_puestos, self.btn_grafico_linea_puntos]))

        # --- CONTENEDOR 3: GRÁFICOS DE BARRA ---
        self.btn_grafico_barras_puntos = ft.ElevatedButton("Puntos por partidos", icon=ft.icons.BAR_CHART, bgcolor="#333333", color="white", width=140, height=45, style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), on_click=self._abrir_selector_grafico_barras)
        self.contenedor_graficos_barra = ft.Container(padding=ft.padding.all(10), border=ft.border.all(1, "white24"), border_radius=8, bgcolor="#1E1E1E", content=ft.Column(spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER, controls=[ft.Text("Gráficos de barra", size=11, weight=ft.FontWeight.BOLD, color="white54"), self.btn_grafico_barras_puntos]))

        # --- CONTENEDOR 4: RANKINGS (FUSIÓN ÍNDICES Y FALSO PROFETA) ---
        
        # ============================================================
        # 1. DEFINICIÓN DE BOTONES (Columna Izquierda)
        # ============================================================
        
        # Botón 1: Optimismo/Pesimismo
        self.btn_indice_opt_pes = ft.ElevatedButton(
            "Optimismo/Pesimismo", 
            icon="assessment", 
            bgcolor="#333333", 
            color="white", 
            width=180, 
            height=45, 
            style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), 
            on_click=self._abrir_modal_opt_pes
        )

        # Botón 2: Falso Profeta
        self.btn_ranking_fp = ft.ElevatedButton(
            "Falso profeta", 
            icon="new_releases", 
            bgcolor="#333333", 
            color="white", 
            width=140, 
            height=45, 
            style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), 
            on_click=self._abrir_modal_falso_profeta
        )

        # Botón 3: Mufa
        self.btn_mufa = ft.ElevatedButton(
            "Mufa", 
            icon="flash_on", 
            bgcolor="#333333", 
            color="white", 
            width=140, 
            height=45, 
            style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), 
            on_click=self._abrir_modal_mufa
        )

        # Botón 4: Mejor Predictor
        self.btn_mejor_predictor = ft.ElevatedButton(
            "Mejor predictor", 
            icon="precision_manufacturing", 
            bgcolor="#333333", 
            color="white", 
            width=140, 
            height=45, 
            style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), 
            on_click=self._abrir_modal_mejor_predictor
        )

        # Botón 5: Racha Actual
        self.btn_racha_actual = ft.ElevatedButton(
            "Racha actual", 
            icon="trending_up", 
            bgcolor="#333333", 
            color="white", 
            width=140, 
            height=45, 
            style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), 
            on_click=self._abrir_modal_racha_actual
        )
        
        # Botón 6: Racha Récord
        self.btn_racha_record = ft.ElevatedButton(
            "Racha récord", 
            icon="military_tech", 
            bgcolor="#333333", 
            color="white", 
            width=140, 
            height=45, 
            style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), 
            on_click=self._abrir_modal_racha_record
        )

        # ============================================================
        # 2. CONTENEDOR DE ÍNDICES (Layout de 3 filas)
        # ============================================================
        self.contenedor_indices = ft.Container(
            padding=ft.padding.all(10),
            border=ft.border.all(1, "white24"),
            border_radius=8,
            bgcolor="#1E1E1E",
            content=ft.Column(
                spacing=10,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("Rankings", size=11, weight=ft.FontWeight.BOLD, color="white54"),
                    
                    # Fila 1
                    ft.Row(
                        spacing=10,
                        alignment=ft.MainAxisAlignment.START,
                        scroll=ft.ScrollMode.AUTO,
                        controls=[
                            self.btn_indice_opt_pes,
                            self.btn_ranking_fp
                        ]
                    ),
                    
                    # Fila 2
                    ft.Row(
                        spacing=10,
                        alignment=ft.MainAxisAlignment.START,
                        scroll=ft.ScrollMode.AUTO,
                        controls=[
                            self.btn_mufa, 
                            self.btn_mejor_predictor
                        ]
                    ),
                    
                    # Fila 3
                    ft.Row(
                        spacing=10,
                        alignment=ft.MainAxisAlignment.START,
                        scroll=ft.ScrollMode.AUTO,
                        controls=[
                            self.btn_racha_actual,
                            self.btn_racha_record
                        ]
                    )
                ]
            )
        )

        # --- CONTROLES FORMULARIO PRONÓSTICOS ---
        self.input_pred_cai = ft.TextField(label="Goles CAI", width=80, text_align=ft.TextAlign.CENTER, keyboard_type=ft.KeyboardType.NUMBER, max_length=2, bgcolor="#2D2D2D", border_color="white24", color="white", on_change=self._validar_solo_numeros)
        self.input_pred_rival = ft.TextField(label="Goles Rival", width=110, text_align=ft.TextAlign.CENTER, keyboard_type=ft.KeyboardType.NUMBER, max_length=2, bgcolor="#2D2D2D", border_color="white24", color="white", on_change=self._validar_solo_numeros)
        self.btn_pronosticar = ft.ElevatedButton("Pronosticar", icon=ft.icons.SPORTS_SOCCER, bgcolor="green", color="white", on_click=self._guardar_pronostico)

        # --- TÍTULOS ---
        self.txt_titulo_ranking = ft.Text("Tabla de posiciones histórica", size=28, weight=ft.FontWeight.BOLD, color="white")
        self.txt_titulo_copas = ft.Text("Torneos ganados en la historia", size=24, weight=ft.FontWeight.BOLD, color="white")
        
        self.txt_titulo_partidos = ft.Text("Partidos por jugar", size=28, weight=ft.FontWeight.BOLD, color="white")
        self.txt_titulo_pronosticos = ft.Text("Todos los pronósticos", size=28, weight=ft.FontWeight.BOLD, color="white") 

        # --- BOTONES FILTROS (PESTAÑA PARTIDOS) ---
        # AHORA LLAMAN A _cambiar_filtro_tiempo_partidos
        self.btn_todos = ft.ElevatedButton("Todos", icon=ft.icons.LIST, bgcolor="#333333", color="white", on_click=lambda _: self._cambiar_filtro_tiempo_partidos('todos'))
        self.btn_jugados = ft.ElevatedButton("Jugados", icon=ft.icons.HISTORY, bgcolor="#333333", color="white", on_click=lambda _: self._cambiar_filtro_tiempo_partidos('jugados'))
        self.btn_por_jugar = ft.ElevatedButton("Por jugar", icon=ft.icons.UPCOMING, bgcolor="blue", color="white", on_click=lambda _: self._cambiar_filtro_tiempo_partidos('futuros'))
        
        # Estos ahora gestionan su propio estado toggle
        self.btn_por_torneo = ft.ElevatedButton("Por torneo", icon=ft.icons.EMOJI_EVENTS, bgcolor="#333333", color="white", on_click=self._abrir_selector_torneo)
        self.btn_sin_pronosticar = ft.ElevatedButton("Sin pronosticar", icon=ft.icons.EVENT_BUSY, bgcolor="#333333", color="white", on_click=self._toggle_sin_pronosticar)
        self.btn_por_equipo = ft.ElevatedButton("Por equipo", icon=ft.icons.GROUPS, bgcolor="#333333", color="white", on_click=self._abrir_selector_equipo)

        # --- BOTONES FILTROS (PESTAÑA PRONÓSTICOS) ---
        # AHORA LLAMAN A _cambiar_filtro_tiempo_pronosticos (Nombre más claro)
        self.btn_pron_todos = ft.ElevatedButton("Todos", icon=ft.icons.LIST, bgcolor="blue", color="white", on_click=lambda _: self._cambiar_filtro_tiempo_pronosticos('todos'))
        self.btn_pron_por_jugar = ft.ElevatedButton("Por jugar", icon=ft.icons.UPCOMING, bgcolor="#333333", color="white", on_click=lambda _: self._cambiar_filtro_tiempo_pronosticos('futuros'))
        self.btn_pron_jugados = ft.ElevatedButton("Jugados", icon=ft.icons.HISTORY, bgcolor="#333333", color="white", on_click=lambda _: self._cambiar_filtro_tiempo_pronosticos('jugados'))
        
        self.btn_pron_por_torneo = ft.ElevatedButton("Por torneo", icon=ft.icons.EMOJI_EVENTS, bgcolor="#333333", color="white", on_click=lambda _: self._gestionar_accion_boton_filtro('torneo'))
        self.btn_pron_por_equipo = ft.ElevatedButton("Por equipo", icon=ft.icons.GROUPS, bgcolor="#333333", color="white", on_click=lambda _: self._gestionar_accion_boton_filtro('equipo'))
        self.btn_pron_por_usuario = ft.ElevatedButton("Por usuario", icon=ft.icons.PERSON, bgcolor="#333333", color="white", on_click=lambda _: self._gestionar_accion_boton_filtro('usuario'))

        # --- COLUMNAS ---
        columnas_partidos = [
            ft.DataColumn(ft.Container(content=ft.Text("Vs (rival)", color="white", weight=ft.FontWeight.BOLD), width=250, alignment=ft.alignment.center)), 
            ft.DataColumn(ft.Container(content=ft.Text("Resultado", color="white", weight=ft.FontWeight.BOLD), width=80, alignment=ft.alignment.center)), 
            ft.DataColumn(ft.Container(content=ft.Text("Fecha y hora", color="white", weight=ft.FontWeight.BOLD), width=140, alignment=ft.alignment.center)), 
            ft.DataColumn(ft.Container(content=ft.Text("Torneo", color="yellow", weight=ft.FontWeight.BOLD), width=150, alignment=ft.alignment.center)), 
            ft.DataColumn(ft.Container(content=ft.Text("Tu pronóstico", color="cyan", weight=ft.FontWeight.BOLD), width=100, alignment=ft.alignment.center)), 
            ft.DataColumn(ft.Container(content=ft.Text("Tus puntos", color="green", weight=ft.FontWeight.BOLD), width=80, alignment=ft.alignment.center)),
            # NUEVA COLUMNA
            ft.DataColumn(ft.Container(content=ft.Text("Error\nabsoluto", color="red", weight=ft.FontWeight.BOLD, text_align="center"), width=80, alignment=ft.alignment.center), numeric=True)
        ]
        columnas_pronosticos = [
            ft.DataColumn(ft.Container(content=ft.Text("Vs (rival)", color="white", weight=ft.FontWeight.BOLD), width=250, alignment=ft.alignment.center), on_sort=self._ordenar_tabla_pronosticos), 
            ft.DataColumn(ft.Container(content=ft.Text("Fecha y hora", color="white", weight=ft.FontWeight.BOLD), width=140, alignment=ft.alignment.center), on_sort=self._ordenar_tabla_pronosticos), 
            ft.DataColumn(ft.Container(content=ft.Text("Torneo", color="yellow", weight=ft.FontWeight.BOLD), width=150, alignment=ft.alignment.center), on_sort=self._ordenar_tabla_pronosticos), 
            ft.DataColumn(ft.Container(content=ft.Text("Resultado", color="white", weight=ft.FontWeight.BOLD), width=80, alignment=ft.alignment.center), on_sort=self._ordenar_tabla_pronosticos), 
            ft.DataColumn(ft.Container(content=ft.Text("Usuario", color="white", weight=ft.FontWeight.BOLD), width=100, alignment=ft.alignment.center), on_sort=self._ordenar_tabla_pronosticos), 
            ft.DataColumn(ft.Container(content=ft.Text("Pronóstico", color="cyan", weight=ft.FontWeight.BOLD), width=80, alignment=ft.alignment.center), on_sort=self._ordenar_tabla_pronosticos), 
            ft.DataColumn(ft.Container(content=ft.Text("Fecha predicción", color="white70", weight=ft.FontWeight.BOLD), width=140, alignment=ft.alignment.center), on_sort=self._ordenar_tabla_pronosticos), 
            ft.DataColumn(ft.Container(content=ft.Text("Puntos", color="green", weight=ft.FontWeight.BOLD), width=60, alignment=ft.alignment.center), numeric=True, on_sort=self._ordenar_tabla_pronosticos),
            ft.DataColumn(ft.Container(content=ft.Text("Error\nabsoluto", color="red", weight=ft.FontWeight.BOLD, text_align="center"), width=80, alignment=ft.alignment.center), numeric=True, on_sort=self._ordenar_tabla_pronosticos)
        ]
        ancho_usuario = 110 
        columnas_estadisticas = [ft.DataColumn(ft.Container(content=ft.Text("Puesto", color="white", weight=ft.FontWeight.BOLD), width=60, alignment=ft.alignment.center)), ft.DataColumn(ft.Container(content=ft.Text("Usuario", color="white", weight=ft.FontWeight.BOLD), width=ancho_usuario, alignment=ft.alignment.center)), ft.DataColumn(ft.Container(content=ft.Text("Puntos\ntotales", color="yellow", weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER), width=100, alignment=ft.alignment.center)), ft.DataColumn(ft.Container(content=ft.Text("Pts.\nganador", color="white", text_align=ft.TextAlign.CENTER), width=120, alignment=ft.alignment.center)), ft.DataColumn(ft.Container(content=ft.Text("Pts.\ngoles CAI", color="white", text_align=ft.TextAlign.CENTER), width=120, alignment=ft.alignment.center)), ft.DataColumn(ft.Container(content=ft.Text("Pts.\ngoles rival", color="white", text_align=ft.TextAlign.CENTER), width=120, alignment=ft.alignment.center)), ft.DataColumn(ft.Container(content=ft.Text("Partidos\njugados", color="cyan", text_align=ft.TextAlign.CENTER), width=120, alignment=ft.alignment.center)), ft.DataColumn(ft.Container(content=ft.Text("Anticipación\npromedio", color="cyan", text_align=ft.TextAlign.CENTER), width=200, alignment=ft.alignment.center)), ft.DataColumn(ft.Container(content=ft.Text("Promedio\nintentos", color="cyan", text_align=ft.TextAlign.CENTER), width=80, alignment=ft.alignment.center)), ft.DataColumn(ft.Container(content=ft.Text("Efectividad\n(puntería)", color="green", text_align=ft.TextAlign.CENTER), width=100, alignment=ft.alignment.center))]
        columnas_copas = [ft.DataColumn(ft.Container(content=ft.Text("Puesto", color="white", weight=ft.FontWeight.BOLD), width=60, alignment=ft.alignment.center)), ft.DataColumn(ft.Container(content=ft.Text("Usuario", color="white", weight=ft.FontWeight.BOLD), width=ancho_usuario, alignment=ft.alignment.center)), ft.DataColumn(ft.Container(content=ft.Text("Torneos ganados", color="yellow", weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER), width=120, alignment=ft.alignment.center))]
        columnas_rivales = [ft.DataColumn(ft.Container(content=ft.Text("Nombre", color="white", weight=ft.FontWeight.BOLD), width=250, alignment=ft.alignment.center)), ft.DataColumn(ft.Container(content=ft.Text("Otro nombre", color="cyan", weight=ft.FontWeight.BOLD), width=250, alignment=ft.alignment.center))]

        # --- DEFINICIÓN DE TABLAS ---
        self.tabla_estadisticas_header = ft.DataTable(width=1450, bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(top_left=8, top_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_color="black", heading_row_height=70, data_row_max_height=0, column_spacing=15, columns=columnas_estadisticas, rows=[])
        self.tabla_estadisticas = ft.DataTable(width=1450, bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(bottom_left=8, bottom_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_height=0, data_row_max_height=60, column_spacing=15, columns=columnas_estadisticas, rows=[])
        self.tabla_copas_header = ft.DataTable(width=400, bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(top_left=8, top_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_color="black", heading_row_height=70, data_row_max_height=0, column_spacing=20, columns=columnas_copas, rows=[])
        self.tabla_copas = ft.DataTable(width=400, bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(bottom_left=8, bottom_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_height=0, data_row_max_height=60, column_spacing=20, columns=columnas_copas, rows=[])
        
        self.tabla_partidos_header = ft.DataTable(bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(top_left=8, top_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_color="black", heading_row_height=70, data_row_max_height=0, column_spacing=20, columns=columnas_partidos, rows=[])
        self.tabla_partidos = ft.DataTable(bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(bottom_left=8, bottom_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_height=0, data_row_max_height=60, column_spacing=20, columns=columnas_partidos, rows=[])
        self.tabla_pronosticos_header = ft.DataTable(bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(top_left=8, top_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_color="black", heading_row_height=70, data_row_max_height=0, column_spacing=20, columns=columnas_pronosticos, rows=[])
        self.tabla_pronosticos = ft.DataTable(bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(bottom_left=8, bottom_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_height=0, data_row_max_height=60, column_spacing=20, columns=columnas_pronosticos, sort_column_index=self.pronosticos_sort_col_index, sort_ascending=self.pronosticos_sort_asc, rows=[])
        self.tabla_rivales_header = ft.DataTable(bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(top_left=8, top_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_color="black", heading_row_height=60, data_row_max_height=0, column_spacing=20, columns=columnas_rivales, rows=[])
        self.tabla_rivales = ft.DataTable(bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(bottom_left=8, bottom_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_height=0, data_row_max_height=60, column_spacing=20, columns=columnas_rivales, rows=[])

        self.input_admin_nombre = ft.TextField(label="Nombre", width=250, bgcolor="#2D2D2D", color="white", border_color="white24")
        self.input_admin_otro = ft.TextField(label="Otro nombre", width=250, bgcolor="#2D2D2D", color="white", border_color="white24")
        self.btn_guardar_rival = ft.ElevatedButton("Guardar", icon=ft.icons.SAVE, bgcolor="green", color="white", on_click=self._guardar_rival_admin)

        self.contenedor_admin_rivales = ft.Container(content=ft.Column(controls=[self.input_admin_nombre, self.input_admin_otro, ft.Container(height=10), self.btn_guardar_rival], horizontal_alignment=ft.CrossAxisAlignment.CENTER), padding=20)

        # 0. Obtener datos actuales para mostrar
        email_actual_display = "Cargando..."
        try:
            bd = BaseDeDatos()
            email_bd = bd.obtener_email_usuario(self.usuario_actual)
            if email_bd: email_actual_display = email_bd
            else: email_actual_display = "No registrado"
        except:
            email_actual_display = "Error de conexión"

        # Etiquetas de información actual
        self.txt_info_user_actual = ft.Text(f"Usuario: {self.usuario_actual}", size=14, color="cyan", weight=ft.FontWeight.BOLD)
        self.txt_info_email_actual = ft.Text(f"Email: {email_actual_display}", size=14, color="cyan", weight=ft.FontWeight.BOLD)
        
        contenedor_info_actual = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon("info_outline", color="cyan"), # Icono corregido
                    self.txt_info_user_actual,
                    ft.Container(width=20),
                    ft.Icon("email_outlined", color="cyan"), # Icono corregido
                    self.txt_info_email_actual
                ]
            ),
            bgcolor="#2D2D2D",
            padding=10,
            border_radius=8,
            border=ft.border.all(1, "white10")
        )

        # 1. PANEL CONTRASEÑA
        self.input_conf_pass_1 = ft.TextField(label="Nueva contraseña", password=True, can_reveal_password=True, width=280, bgcolor="#2D2D2D", color="white", border_color="white24", label_style=ft.TextStyle(color="white70"), text_size=14)
        self.input_conf_pass_2 = ft.TextField(label="Repetir contraseña", password=True, can_reveal_password=True, width=280, bgcolor="#2D2D2D", color="white", border_color="white24", label_style=ft.TextStyle(color="white70"), text_size=14)
        self.btn_conf_guardar_pass = ft.ElevatedButton("Guardar nueva clave", icon="lock_reset", bgcolor="green", color="white", width=280, height=40, on_click=self._guardar_contrasena_config)

        self.frame_cambio_pass = ft.Container(
            content=ft.Column(controls=[
                ft.Row([ft.Icon("security", color="cyan"), ft.Text("Seguridad", size=16, weight=ft.FontWeight.BOLD, color="white")]),
                ft.Divider(color="white24"),
                ft.Text("Cambiar contraseña", size=12, color="white70"),
                self.input_conf_pass_1, self.input_conf_pass_2, ft.Container(height=10), self.btn_conf_guardar_pass
            ], spacing=10),
            padding=25, border=ft.border.all(1, "white24"), border_radius=10, bgcolor="#1E1E1E", width=350
        )

        # 2. PANEL EMAIL
        self.input_conf_email = ft.TextField(label="Nuevo correo", width=280, bgcolor="#2D2D2D", color="white", border_color="white24", label_style=ft.TextStyle(color="white70"), text_size=14, prefix_icon="email")
        self.btn_conf_guardar_email = ft.ElevatedButton("Enviar código", icon="send", bgcolor="blue", color="white", width=280, height=40, on_click=self._iniciar_cambio_email)

        self.frame_cambio_email = ft.Container(
            content=ft.Column(controls=[
                ft.Row([ft.Icon("alternate_email", color="cyan"), ft.Text("Contacto", size=16, weight=ft.FontWeight.BOLD, color="white")]),
                ft.Divider(color="white24"),
                ft.Text("Cambiar email", size=12, color="white70"),
                self.input_conf_email, ft.Container(height=10), self.btn_conf_guardar_email, ft.Container(height=60)
            ], spacing=10),
            padding=25, border=ft.border.all(1, "white24"), border_radius=10, bgcolor="#1E1E1E", width=350
        )

        # 3. PANEL USUARIO
        self.input_conf_usuario = ft.TextField(
            label="Nuevo nombre de usuario", 
            width=280, 
            bgcolor="#2D2D2D", 
            color="white", 
            border_color="white24", 
            label_style=ft.TextStyle(color="white70"), 
            text_size=14, 
            prefix_icon="person"
        )

        # --- CAMBIO AQUÍ ---
        self.btn_conf_guardar_usuario = ft.ElevatedButton(
            "Guardar cambio", # Texto inicial
            icon="save",      # Icono de guardar
            bgcolor="orange", 
            color="white", 
            width=280, 
            height=40, 
            on_click=self._guardar_nuevo_usuario # Nueva función directa
        )

        self.frame_cambio_usuario = ft.Container(
            content=ft.Column(controls=[
                ft.Row([ft.Icon("account_circle", color="cyan"), ft.Text("Identidad", size=16, weight=ft.FontWeight.BOLD, color="white")]),
                ft.Divider(color="white24"),
                ft.Text("Cambiar nombre de usuario", size=12, color="white70"),
                self.input_conf_usuario, 
                ft.Container(height=10), 
                self.btn_conf_guardar_usuario, 
                ft.Container(height=60)
            ], spacing=10),
            padding=25, border=ft.border.all(1, "white24"), border_radius=10, bgcolor="#1E1E1E", width=350
        )

        lista_pestanas = [
            ft.Tab(
                text="Estadísticas", icon="bar_chart",
                content=ft.Container(
                    padding=20, alignment=ft.alignment.top_left,
                    content=ft.Column(
                        scroll=ft.ScrollMode.AUTO, controls=[
                            self.txt_titulo_ranking, 
                            self.loading,
                            # 1. TABLA POSICIONES (SOLA)
                            ft.Row(
                                scroll=ft.ScrollMode.AUTO, # <--- SCROLL HORIZONTAL AGREGADO
                                controls=[
                                    ft.Column(
                                        spacing=0,
                                        controls=[
                                            self.tabla_estadisticas_header,
                                            ft.Container(
                                                height=240, 
                                                content=ft.Column(
                                                    scroll=ft.ScrollMode.ALWAYS, 
                                                    controls=[self.tabla_estadisticas]
                                                )
                                            )
                                        ]
                                    )
                                ]
                            ),
                            
                            ft.Container(height=20), # Espacio intermedio

                            # 2. FILA DE CONTENEDORES (Filtros, Gráficos, Rankings)
                            ft.Row(
                                alignment=ft.MainAxisAlignment.START,
                                vertical_alignment=ft.CrossAxisAlignment.START,
                                controls=[
                                    self.contenedor_filtro_torneo,
                                    ft.Container(width=20),
                                    self.contenedor_graficos,
                                    ft.Container(width=20),
                                    self.contenedor_graficos_barra,
                                    ft.Container(width=20),
                                    self.contenedor_indices # AHORA LLAMADO RANKINGS Y CONTIENE AMBOS BOTONES
                                ]
                            ),
                            
                            ft.Container(height=20), # Espacio intermedio

                            # 3. FILA INFERIOR: SOLO COPAS
                            ft.Row(
                                alignment=ft.MainAxisAlignment.START,
                                vertical_alignment=ft.CrossAxisAlignment.START,
                                controls=[
                                    # COLUMNA IZQUIERDA: TORNEOS GANADOS
                                    ft.Column(
                                        controls=[
                                            self.txt_titulo_copas,
                                            self.loading_copas,
                                            ft.Container(height=260, content=ft.Column(spacing=0, controls=[self.tabla_copas_header, ft.Container(height=240, content=ft.Column(scroll=ft.ScrollMode.ALWAYS, controls=[self.tabla_copas]))]))
                                        ]
                                    )
                                ]
                            )
                        ]
                    )
                )
            ),
            ft.Tab(
                text="Partidos", 
                icon="sports_soccer", 
                content=ft.Container(
                    content=ft.Column(
                        controls=[
                            self.txt_titulo_partidos, 
                            self.loading_partidos, 
                            
                            # --- CAMBIO: Alturas ajustadas para 5 filas ---
                            ft.Row(
                                scroll=ft.ScrollMode.ALWAYS, 
                                controls=[
                                    ft.Row(
                                        vertical_alignment=ft.CrossAxisAlignment.START, 
                                        controls=[
                                            # 1. La Tabla de Partidos
                                            ft.Container(
                                                height=370, # ANTES: 380 -> AHORA: 370 (70 header + 300 cuerpo)
                                                content=ft.Row(
                                                    controls=[
                                                        ft.Column(
                                                            spacing=0, 
                                                            controls=[
                                                                self.tabla_partidos_header, 
                                                                ft.Container(
                                                                    height=300, # ANTES: 310 -> AHORA: 300 (5 filas exactas)
                                                                    content=ft.Column(
                                                                        controls=[self.tabla_partidos], 
                                                                        scroll=ft.ScrollMode.ALWAYS
                                                                    )
                                                                )
                                                            ]
                                                        )
                                                    ], 
                                                    scroll=ft.ScrollMode.ALWAYS 
                                                )
                                            ), 
                                            
                                            ft.Container(width=10), 
                                            
                                            # 2. Panel de "Tu Pronóstico"
                                            ft.Container(
                                                width=200, 
                                                padding=10, 
                                                border=ft.border.all(1, "white10"), 
                                                border_radius=8, 
                                                bgcolor="#1E1E1E", 
                                                content=ft.Column(
                                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER, 
                                                    spacing=15, 
                                                    controls=[
                                                        ft.Text("Tu Pronóstico", size=16, weight=ft.FontWeight.BOLD), 
                                                        self.input_pred_cai, 
                                                        self.input_pred_rival, 
                                                        self.btn_pronosticar
                                                    ]
                                                )
                                            )
                                        ]
                                    )
                                ]
                            ),
                            # ----------------------------------------

                            ft.Container(height=10), 
                            
                            ft.Row(
                                controls=[self.btn_todos, self.btn_jugados, self.btn_por_jugar, self.btn_por_torneo, self.btn_sin_pronosticar, self.btn_por_equipo], 
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
            ft.Tab(
                text="Pronósticos", 
                icon="list_alt", 
                content=ft.Container(
                    content=ft.Column(
                        controls=[
                            self.txt_titulo_pronosticos, 
                            self.loading_pronosticos, 
                            
                            # --- CAMBIO: Alturas ajustadas para 5 filas ---
                            ft.Row(
                                controls=[
                                    ft.Container(
                                        height=370, # ANTES: 440 -> AHORA: 370
                                        content=ft.Column(
                                            spacing=0, 
                                            controls=[
                                                self.tabla_pronosticos_header, 
                                                ft.Container(
                                                    height=300, # ANTES: 360 -> AHORA: 300 (5 filas exactas)
                                                    content=ft.Column(
                                                        controls=[self.tabla_pronosticos], 
                                                        scroll=ft.ScrollMode.ALWAYS 
                                                    )
                                                )
                                            ]
                                        )
                                    )
                                ],
                                scroll=ft.ScrollMode.ALWAYS 
                            ),
                            
                            ft.Container(height=10), 
                            ft.Row(
                                controls=[self.btn_pron_todos, self.btn_pron_por_jugar, self.btn_pron_jugados, self.btn_pron_por_torneo, self.btn_pron_por_equipo, self.btn_pron_por_usuario], 
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
            ft.Tab(
                text="Configuración", 
                icon=ft.icons.SETTINGS, 
                content=ft.Container(
                    padding=30, 
                    alignment=ft.alignment.top_left,
                    content=ft.Column(
                        controls=[
                            ft.Text("Opciones de usuario", size=28, weight=ft.FontWeight.BOLD, color="white"),
                            contenedor_info_actual, # <--- AQUI SE MUESTRA LA INFO ACTUAL
                            ft.Container(height=20),
                            
                            ft.Row(
                                controls=[
                                    self.frame_cambio_pass,
                                    ft.Container(width=20),
                                    self.frame_cambio_email,
                                    ft.Container(width=20),
                                    self.frame_cambio_usuario # <--- NUEVO PANEL
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.START,
                                scroll=ft.ScrollMode.AUTO
                            )
                        ]
                    )
                )
            )
        ]

        if usuario == "Gabriel":
            lista_pestanas.append(ft.Tab(text="Administración", icon="admin_panel_settings", content=ft.Container(padding=20, alignment=ft.alignment.top_left, content=ft.Column(scroll=ft.ScrollMode.AUTO, controls=[ft.Text("Equipos", size=20, weight=ft.FontWeight.BOLD, color="white"), self.loading_admin, ft.Row(vertical_alignment=ft.CrossAxisAlignment.START, controls=[ft.Column(spacing=0, controls=[self.tabla_rivales_header, ft.Container(height=300, content=ft.Column(scroll=ft.ScrollMode.ALWAYS, controls=[self.tabla_rivales]))]), ft.Container(width=20), ft.Card(content=ft.Container(content=ft.Column([ft.Container(padding=10, content=ft.Text("Cambiar nombre", weight="bold", size=16)), self.contenedor_admin_rivales]), padding=10))])]))))

        self.dlg_cargando_inicio = ft.AlertDialog(modal=True, title=ft.Text("Actualizando información..."), content=ft.Column([ft.ProgressBar(width=300, color="amber", bgcolor="#222222"), ft.Container(height=10), ft.Text("Buscando nuevos partidos y resultados. Esto puede demorar unos segundos...")], height=100, alignment=ft.MainAxisAlignment.CENTER), actions=[])

        mis_pestanas = ft.Tabs(selected_index=0, expand=True, tabs=lista_pestanas)
        self.page.add(mis_pestanas)
        self.page.open(self.dlg_cargando_inicio)
        threading.Thread(target=self._sincronizar_fixture_api, daemon=True).start()
    
    def _guardar_nuevo_usuario(self, e):
        """
        Cambia el nombre de usuario directamente (sin email) verificando disponibilidad.
        """
        nuevo_user = self.input_conf_usuario.value.strip()
        
        # 1. Validaciones básicas
        if not nuevo_user:
            GestorMensajes.mostrar(self.page, "Atención", "Escriba un nombre.", "error")
            return
            
        if len(nuevo_user) < 3:
            GestorMensajes.mostrar(self.page, "Error", "El nombre debe tener al menos 3 caracteres.", "error")
            return

        if nuevo_user == self.usuario_actual:
            GestorMensajes.mostrar(self.page, "Atención", "El nombre es igual al actual.", "info")
            return

        def _tarea():
            # 2. Estado de Carga: "Verificando..."
            self.btn_conf_guardar_usuario.disabled = True
            self.btn_conf_guardar_usuario.text = "Verificando..." # <--- TEXTO SOLICITADO
            self.btn_conf_guardar_usuario.update()
            
            try:
                bd = BaseDeDatos()
                
                # A. Verificar disponibilidad
                bd.verificar_username_libre(nuevo_user)
                
                # B. Obtener ID del usuario actual para hacer el update
                id_user = bd.obtener_id_por_username(self.usuario_actual)
                
                if id_user:
                    # C. Realizar el cambio
                    bd.actualizar_username(id_user, nuevo_user)
                    
                    # D. Actualizar sesión y UI
                    old_name = self.usuario_actual
                    self.usuario_actual = nuevo_user
                    
                    # Actualizar título de ventana y etiqueta de info
                    self.page.appbar.title.value = f"Bienvenido, {self.usuario_actual}"
                    self.txt_info_user_actual.value = f"Usuario: {self.usuario_actual}"
                    
                    self.page.appbar.update()
                    self.txt_info_user_actual.update()
                    
                    GestorMensajes.mostrar(self.page, "Éxito", f"Nombre cambiado de {old_name} a {self.usuario_actual}", "exito")
                    
                    # Limpiar campo
                    self.input_conf_usuario.value = ""
                    self.input_conf_usuario.update()
                else:
                    raise Exception("No se pudo identificar al usuario actual.")
                    
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", f"No se pudo guardar: {ex}", "error")
            
            finally:
                # 3. Restaurar botón
                self.btn_conf_guardar_usuario.disabled = False
                self.btn_conf_guardar_usuario.text = "Guardar cambio"
                self.btn_conf_guardar_usuario.update()

        threading.Thread(target=_tarea, daemon=True).start()

    def _cambiar_filtro_tiempo_partidos(self, nuevo_tiempo):
        """
        Gestiona el grupo de filtros de Tiempo para PARTIDOS (Todos, Futuros, Jugados).
        Estos son EXCLUYENTES entre sí y modifican self.filtro_temporal.
        """
        self.filtro_temporal = nuevo_tiempo
        
        # Actualizamos visualmente los botones de Partidos
        self._actualizar_botones_partidos_visual()
        
        # Actualizamos título y recargamos la tabla Partidos
        self._actualizar_titulo_partidos()
        self._recargar_datos(actualizar_partidos=True, actualizar_copas=False)

    def _cambiar_filtro_tiempo_pronosticos(self, nuevo_filtro):
        """
        Gestiona el grupo de filtros de Tiempo para PRONÓSTICOS.
        Modifica self.filtro_pron_tiempo.
        """
        self.filtro_pron_tiempo = nuevo_filtro
        
        # Actualizamos visualmente los botones de Pronósticos
        self._actualizar_botones_pronosticos_visual()
        
        # Actualizamos título y recargamos la tabla Pronósticos
        self._actualizar_titulo_pronosticos()
        self._recargar_datos(actualizar_pronosticos=True)

    def _abrir_modal_opt_pes(self, e):
        """Abre la ventana modal con la tabla de Optimismo/Pesimismo."""
        
        titulo = "Índice de Optimismo/Pesimismo histórico"
        if self.filtro_ranking_nombre: 
             titulo = f"Optimismo/Pesimismo ({self.filtro_ranking_nombre})"
        elif self.filtro_ranking_anio:
             titulo = f"Optimismo/Pesimismo ({self.filtro_ranking_anio})"
             
        self.loading_modal = ft.ProgressBar(width=200, color="amber", bgcolor="#222222")
        
        columna_content = ft.Column(
            controls=[
                ft.Text(titulo, size=18, weight="bold", color="white"),
                ft.Container(height=10),
                self.loading_modal,
                ft.Container(height=50)
            ],
            height=150,
            width=650, # Un poco más ancho para la clasificación
            scroll=None
        )
        
        self.dlg_opt_pes = ft.AlertDialog(content=columna_content, modal=True)
        self.page.open(self.dlg_opt_pes)

        def _cargar():
            bd = BaseDeDatos()
            datos = bd.obtener_indice_optimismo_pesimismo(self.filtro_ranking_edicion_id, self.filtro_ranking_anio)
            
            filas = []
            for i, row in enumerate(datos, start=1):
                # row: [0] username, [1] indice_promedio (decimal o None)
                user = row[0]
                val = row[1]
                
                if val is None:
                    txt_val = "-"
                    clasificacion = "-"
                    color_val = "white"
                else:
                    indice = float(val)
                    txt_val = f"{indice:+.2f}".replace('.', ',')
                    
                    # Lógica de Clasificación
                    if indice >= 1.5:
                        clasificacion = "🔴 Muy optimista"
                        color_val = "red"
                    elif 0.5 <= indice < 1.5: # Hasta 1.4999...
                        clasificacion = "🙂 Optimista"
                        color_val = "orange"
                    elif -0.5 < indice < 0.5: # -0.49 a 0.49
                        clasificacion = "⚖️ Realista"
                        color_val = "cyan"
                    elif -1.5 < indice <= -0.5: # -1.49 a -0.5
                        clasificacion = "😐 Pesimista"
                        color_val = "indigo"
                    else: # <= -1.5
                        clasificacion = "🔵 Muy pesimista"
                        color_val = "blue"

                filas.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Container(content=ft.Text(f"{i}º", weight="bold", color="white"), width=50, alignment=ft.alignment.center)),
                    ft.DataCell(ft.Container(content=ft.Text(user, weight="bold", color="white"), width=150, alignment=ft.alignment.center_left)),
                    ft.DataCell(ft.Container(content=ft.Text(txt_val, weight="bold", color=color_val), width=150, alignment=ft.alignment.center)),
                    ft.DataCell(ft.Container(content=ft.Text(clasificacion, weight="bold", color="white"), width=150, alignment=ft.alignment.center_left)),
                ]))
            
            tabla = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Container(content=ft.Text("Puesto", weight="bold", color="white"), width=50, alignment=ft.alignment.center)),
                    ft.DataColumn(ft.Container(content=ft.Text("Usuario", weight="bold", color="white"), width=150, alignment=ft.alignment.center_left)),
                    ft.DataColumn(ft.Container(content=ft.Text("Optimismo/\nPesimismo", text_align="center", weight="bold", color="white"), width=150, alignment=ft.alignment.center), numeric=True),
                    ft.DataColumn(ft.Container(content=ft.Text("Clasificación", weight="bold", color="white"), width=150, alignment=ft.alignment.center_left)),
                ],
                rows=filas,
                heading_row_color="black",
                border=ft.border.all(1, "white10"),
                column_spacing=10,
                heading_row_height=60,
                data_row_max_height=50,
                data_row_min_height=50
            )
            
            columna_content.height = 340
            columna_content.width = 650
            
            columna_content.controls = [
                ft.Text(titulo, size=18, weight="bold", color="white"),
                ft.Container(height=10),
                ft.Column(
                    controls=[tabla],
                    height=220,
                    scroll=ft.ScrollMode.AUTO
                ),
                ft.Container(height=10),
                ft.Row([ft.ElevatedButton("Cerrar", on_click=lambda e: self.page.close(self.dlg_opt_pes))], alignment=ft.MainAxisAlignment.END)
            ]
            self.dlg_opt_pes.update()
            
        threading.Thread(target=_cargar, daemon=True).start()

    def _actualizar_botones_partidos_visual(self):
        """Actualiza colores. Ahora soporta combinaciones."""
        # Grupo Tiempo (Excluyentes)
        f_temp = self.filtro_temporal
        self.btn_todos.bgcolor = "blue" if f_temp == 'todos' else "#333333"
        self.btn_jugados.bgcolor = "blue" if f_temp == 'jugados' else "#333333"
        self.btn_por_jugar.bgcolor = "blue" if f_temp == 'futuros' else "#333333"
        
        # Grupo Filtros (Independientes)
        self.btn_por_torneo.bgcolor = "blue" if self.filtro_edicion_id is not None else "#333333"
        self.btn_sin_pronosticar.bgcolor = "blue" if self.filtro_sin_pronosticar else "#333333"
        self.btn_por_equipo.bgcolor = "blue" if self.filtro_rival_id is not None else "#333333"
        
        # Update individual
        self.btn_todos.update()
        self.btn_jugados.update()
        self.btn_por_jugar.update()
        self.btn_por_torneo.update()
        self.btn_sin_pronosticar.update()
        self.btn_por_equipo.update()

    def _procesar_partido_fotmob(self, match):
        """
        Extrae datos limpios de un objeto partido de FotMob con validaciones.
        CORREGIDO: Convierte UTC a Hora Argentina (UTC-3).
        """
        try:
            # Validación inicial de tipo
            if not isinstance(match, dict): return None

            # 1. FECHA Y STATUS
            status = match.get("status", {})
            if not isinstance(status, dict): return None 
            
            fecha_str = status.get("utcTime")
            if not fecha_str: return None
            
            # Limpieza fecha ISO
            fecha_str = fecha_str.replace("Z", "+00:00")
            try:
                # Importamos timedelta aquí para realizar la resta de horas
                from datetime import timedelta

                # 1. Convertimos string a datetime
                fecha_utc = datetime.fromisoformat(fecha_str)
                
                # 2. Restamos 3 horas para ajustar a Argentina y quitamos la zona horaria
                fecha_dt = fecha_utc.replace(tzinfo=None) - timedelta(hours=3)
                
            except ValueError:
                return None

            # --- DETECCIÓN DE HORARIO NO DEFINIDO (TEXTUAL) ---
            status_short = str(status.get("short", "")).lower()
            status_long = str(status.get("long", "")).lower()
            reason_short = str(status.get("reason", {}).get("short", "")).lower()
            reason_long = str(status.get("reason", {}).get("long", "")).lower()
            
            senales_tbd = [
                "tbd", "tbc", "to be defined", "time to be defined", 
                "postponed", "time tbd", "time tbc", "pending", 
                "awarded"
            ]
            
            is_time_defined = match.get("isTimeDefined", True)

            es_horario_tbd = (
                not is_time_defined or 
                status_short in senales_tbd or 
                reason_short in senales_tbd or
                any(senal in status_long for senal in senales_tbd) or
                any(senal in reason_long for senal in senales_tbd)
            )

            if es_horario_tbd:
                # Si es explícitamente TBD, forzamos las 00:00:00
                fecha_dt = fecha_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # 2. EQUIPOS
            home = match.get("home", {})
            away = match.get("away", {})
            
            # Asegurar IDs numéricos
            try:
                id_home = int(home.get("id") or 0)
            except: id_home = 0
            
            # Si Independiente no juega, ignorar
            if id_home != ID_INDEPENDIENTE and int(away.get("id") or 0) != ID_INDEPENDIENTE:
                return None

            # Extracción segura de nombres y goles
            score_str = status.get("scoreStr", "")
            finished = status.get("finished", False)
            
            goles_cai = None
            goles_rival = None

            if id_home == ID_INDEPENDIENTE:
                # LOCAL
                nombre_rival = away.get("name", "Rival Desconocido")
                if finished and score_str and " - " in score_str:
                    try:
                        partes = score_str.split(" - ")
                        goles_cai = int(partes[0])
                        goles_rival = int(partes[1])
                    except: pass
            else:
                # VISITANTE
                nombre_rival = home.get("name", "Rival Desconocido")
                if finished and score_str and " - " in score_str:
                    try:
                        partes = score_str.split(" - ")
                        goles_cai = int(partes[1]) # Invertido
                        goles_rival = int(partes[0])
                    except: pass

            # 3. TORNEO
            nombre_torneo = match.get("league", {}).get("name", "Liga Profesional")
            anio_temporada = str(fecha_dt.year)

            return {
                'rival': nombre_rival,
                'torneo': nombre_torneo,
                'anio': anio_temporada,
                'fecha': fecha_dt,
                'goles_cai': goles_cai,
                'goles_rival': goles_rival
            }

        except Exception as e:
            print(f"Error procesando item individual: {e}")
            return None

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

# --- FUNCIONES GRÁFICO DE BARRAS (PUNTOS) ---

    def _abrir_selector_grafico_barras(self, e):
        """Abre el modal para configurar el gráfico de barras de puntos."""
        self.lv_torneos_barra = ft.ListView(expand=True, spacing=5, height=150)
        self.lv_anios_barra = ft.ListView(expand=True, spacing=5, height=150)
        self.lv_usuarios_barra = ft.ListView(expand=True, spacing=5, height=150)
        
        self.temp_camp_barra = None
        self.temp_anio_barra = None
        self.usuario_grafico_barra_sel = None 
        
        self.btn_generar_grafico_barras = ft.ElevatedButton("Generar Gráfico", icon=ft.icons.BAR_CHART, disabled=True, on_click=self._generar_grafico_barras)

        def _cargar_datos():
            bd = BaseDeDatos()
            # 1. Torneos
            ediciones = bd.obtener_ediciones()
            self.cache_ediciones_modal = ediciones
            nombres_unicos = sorted(list(set(e[1] for e in ediciones)))
            
            controles_tor = []
            for nombre in nombres_unicos:
                controles_tor.append(ft.ListTile(title=ft.Text(nombre, size=14), data=nombre, on_click=self._sel_torneo_barra_modal, bgcolor="#2D2D2D"))
            self.lv_torneos_barra.controls = controles_tor
            
            # 2. Usuarios (Lista para seleccionar uno solo)
            usuarios = bd.obtener_usuarios()
            controles_usu = []
            for usu in usuarios:
                controles_usu.append(
                    ft.ListTile(
                        title=ft.Text(usu, size=14),
                        data=usu,
                        on_click=self._sel_usuario_barra_modal,
                        bgcolor="#2D2D2D"
                    )
                )
            self.lv_usuarios_barra.controls = controles_usu
            
            self.lv_torneos_barra.update()
            self.lv_usuarios_barra.update()

        col_tor = ft.Column(expand=1, controls=[ft.Text("1. Torneo", weight="bold"), ft.Container(content=self.lv_torneos_barra, border=ft.border.all(1, "white24"), border_radius=5)])
        col_anio = ft.Column(expand=1, controls=[ft.Text("2. Año", weight="bold"), ft.Container(content=self.lv_anios_barra, border=ft.border.all(1, "white24"), border_radius=5)])
        col_usu = ft.Column(expand=1, controls=[ft.Text("3. Un Usuario", weight="bold"), ft.Container(content=self.lv_usuarios_barra, border=ft.border.all(1, "white24"), border_radius=5)])

        contenido = ft.Container(width=700, height=300, content=ft.Row(controls=[col_tor, col_anio, col_usu], spacing=20))

        self.dlg_grafico_barras = ft.AlertDialog(modal=True, title=ft.Text("Configurar Gráfico de Puntos"), content=contenido, actions=[ft.TextButton("Cancelar", on_click=lambda e: self.page.close(self.dlg_grafico_barras)), self.btn_generar_grafico_barras])
        self.page.open(self.dlg_grafico_barras)
        threading.Thread(target=_cargar_datos, daemon=True).start()

    # --- FUNCIONES GRÁFICO DE LÍNEA POR PUNTOS ---

    def _abrir_selector_grafico_linea_puntos(self, e):
        """Abre el modal para configurar el gráfico de línea de puntos."""
        self.lv_torneos_graf_lp = ft.ListView(expand=True, spacing=5, height=150)
        self.lv_anios_graf_lp = ft.ListView(expand=True, spacing=5, height=150)
        self.lv_usuarios_graf_lp = ft.ListView(expand=True, spacing=5, height=150)
        
        self.temp_camp_graf_lp = None
        self.temp_anio_graf_lp = None
        self.chk_usuarios_grafico_lp = [] 
        
        self.btn_generar_grafico_lp = ft.ElevatedButton("Generar Gráfico", icon=ft.icons.SHOW_CHART, disabled=True, on_click=self._generar_grafico_linea_puntos)

        def _cargar_datos_lp():
            bd = BaseDeDatos()
            # 1. Torneos
            ediciones = bd.obtener_ediciones()
            self.cache_ediciones_modal = ediciones
            nombres_unicos = sorted(list(set(e[1] for e in ediciones)))
            
            controles_tor = []
            for nombre in nombres_unicos:
                controles_tor.append(ft.ListTile(title=ft.Text(nombre, size=14), data=nombre, on_click=self._sel_torneo_graf_lp_modal, bgcolor="#2D2D2D"))
            self.lv_torneos_graf_lp.controls = controles_tor
            
            # 2. Usuarios
            usuarios = bd.obtener_usuarios()
            controles_usu = []
            for usu in usuarios:
                chk = ft.Checkbox(label=usu, value=False, on_change=self._validar_seleccion_usuarios_grafico_lp)
                self.chk_usuarios_grafico_lp.append(chk)
                controles_usu.append(chk)
            self.lv_usuarios_graf_lp.controls = controles_usu
            
            self.lv_torneos_graf_lp.update()
            self.lv_usuarios_graf_lp.update()

        col_tor = ft.Column(expand=1, controls=[ft.Text("1. Torneo", weight="bold"), ft.Container(content=self.lv_torneos_graf_lp, border=ft.border.all(1, "white24"), border_radius=5)])
        col_anio = ft.Column(expand=1, controls=[ft.Text("2. Año", weight="bold"), ft.Container(content=self.lv_anios_graf_lp, border=ft.border.all(1, "white24"), border_radius=5)])
        col_usu = ft.Column(expand=1, controls=[ft.Text("3. Usuarios (Max 3)", weight="bold"), ft.Container(content=self.lv_usuarios_graf_lp, border=ft.border.all(1, "white24"), border_radius=5)])

        contenido = ft.Container(width=700, height=300, content=ft.Row(controls=[col_tor, col_anio, col_usu], spacing=20))

        self.dlg_grafico_lp = ft.AlertDialog(modal=True, title=ft.Text("Configurar Gráfico de Puntos (Línea)"), content=contenido, actions=[ft.TextButton("Cancelar", on_click=lambda e: self.page.close(self.dlg_grafico_lp)), self.btn_generar_grafico_lp])
        self.page.open(self.dlg_grafico_lp)
        threading.Thread(target=_cargar_datos_lp, daemon=True).start()

    def _sel_torneo_graf_lp_modal(self, e):
        nombre = e.control.data
        self.temp_camp_graf_lp = nombre
        
        for c in self.lv_torneos_graf_lp.controls: c.bgcolor = "blue" if c.data == nombre else "#2D2D2D"
        self.lv_torneos_graf_lp.update()
        
        anios = sorted([ed[2] for ed in self.cache_ediciones_modal if ed[1] == nombre], reverse=True)
        ctls = []
        for a in anios:
            ctls.append(ft.ListTile(title=ft.Text(str(a), size=14), data=a, on_click=self._sel_anio_graf_lp_modal, bgcolor="#2D2D2D"))
        self.lv_anios_graf_lp.controls = ctls
        self.lv_anios_graf_lp.update()
        
        self.temp_anio_graf_lp = None
        self._validar_btn_grafico_lp()

    def _sel_anio_graf_lp_modal(self, e):
        self.temp_anio_graf_lp = e.control.data
        for c in self.lv_anios_graf_lp.controls: c.bgcolor = "blue" if c.data == self.temp_anio_graf_lp else "#2D2D2D"
        self.lv_anios_graf_lp.update()
        self._validar_btn_grafico_lp()

    def _validar_seleccion_usuarios_grafico_lp(self, e):
        seleccionados = [c for c in self.chk_usuarios_grafico_lp if c.value]
        if len(seleccionados) > 3:
            e.control.value = False
            e.control.update()
            GestorMensajes.mostrar(self.page, "Límite", "Máximo 3 usuarios.", "info")
        self._validar_btn_grafico_lp()

    def _validar_btn_grafico_lp(self):
        sel_users = [c for c in self.chk_usuarios_grafico_lp if c.value]
        habilitar = self.temp_camp_graf_lp and self.temp_anio_graf_lp and len(sel_users) > 0
        self.btn_generar_grafico_lp.disabled = not habilitar
        self.btn_generar_grafico_lp.update()

    def _generar_grafico_linea_puntos(self, e):
        """Genera y muestra el gráfico de líneas de puntos acumulados."""
        usuarios_sel = [c.label for c in self.chk_usuarios_grafico_lp if c.value]
        
        edicion_id = None
        for ed in self.cache_ediciones_modal:
            if ed[1] == self.temp_camp_graf_lp and ed[2] == self.temp_anio_graf_lp:
                edicion_id = ed[0]
                break
        
        if not edicion_id: return

        def _tarea():
            bd = BaseDeDatos()
            cant_partidos, historial = bd.obtener_datos_evolucion_puntos(edicion_id, usuarios_sel)
            
            if cant_partidos == 0:
                GestorMensajes.mostrar(self.page, "Info", "No hay partidos jugados.", "info")
                return

            # Calcular máximo puntaje alcanzado para escalar eje Y
            max_puntos_alcanzado = 0
            for puntos in historial.values():
                if puntos:
                    max_puntos_alcanzado = max(max_puntos_alcanzado, max(puntos))
            
            altura_eje = max_puntos_alcanzado + 2 # Margen superior

            colores = [ft.Colors.CYAN, ft.Colors.AMBER, ft.Colors.PINK, ft.Colors.GREEN]
            data_series = []
            
            for i, user in enumerate(usuarios_sel):
                puntos_acum = historial.get(user, [])
                
                # Inicio en 0
                puntos_grafico = [ft.LineChartDataPoint(0, 0, tooltip="Inicio")]
                
                for idx_partido, pts in enumerate(puntos_acum):
                    puntos_grafico.append(
                        ft.LineChartDataPoint(
                            x=idx_partido + 1, 
                            y=pts,
                            tooltip=f"{pts} pts"
                        )
                    )
                
                data_series.append(
                    ft.LineChartData(
                        data_points=puntos_grafico,
                        stroke_width=4,
                        color=colores[i % len(colores)],
                        curved=False,
                        stroke_cap_round=True,
                        point=True 
                    )
                )

            # Eje Y Normal (0 abajo, Max arriba)
            labels_y = [ft.ChartAxisLabel(value=0, label=ft.Text("0", size=10, weight="bold"))]
            
            # Etiquetas cada 5 puntos o 3 si son pocos
            intervalo_y = 5 if altura_eje > 20 else 3
            for p in range(intervalo_y, int(altura_eje), intervalo_y):
                labels_y.append(
                    ft.ChartAxisLabel(
                        value=p, 
                        label=ft.Text(str(p), size=12)
                    )
                )

            # Intervalo X dinámico
            intervalo_x = 1
            if cant_partidos > 15: intervalo_x = 2
            if cant_partidos > 30: intervalo_x = 5

            chart = ft.LineChart(
                data_series=data_series,
                border=ft.border.all(1, ft.Colors.WHITE10),
                left_axis=ft.ChartAxis(
                    labels=labels_y,
                    labels_size=40,
                    title=ft.Text("Puntos Acumulados", size=14, italic=True),
                    title_size=30
                ),
                bottom_axis=ft.ChartAxis(
                    labels_interval=intervalo_x,
                    title=ft.Text("Partido N°", size=14, italic=True),
                    labels_size=40,
                ),
                tooltip_bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.BLACK),
                min_y=0,
                max_y=altura_eje,
                min_x=0,
                max_x=cant_partidos, 
                horizontal_grid_lines=ft.ChartGridLines(interval=intervalo_y, color=ft.Colors.WHITE10, width=1),
                expand=True,
            )
            
            items_leyenda = []
            for i, user in enumerate(usuarios_sel):
                items_leyenda.append(
                    ft.Row([
                        ft.Container(width=15, height=15, bgcolor=colores[i % 3], border_radius=3),
                        ft.Text(user, weight="bold", size=16)
                    ], spacing=5)
                )

            ancho = self.page.width - 50
            alto = self.page.height - 50

            contenido_final = ft.Container(
                width=ancho, height=alto,
                padding=20, bgcolor="#1E1E1E",
                content=ft.Column([
                    ft.Row(
                        controls=[
                            ft.Text(f"Evolución Puntos: {self.temp_camp_graf_lp} {self.temp_anio_graf_lp}", size=24, weight="bold"),
                            ft.IconButton(icon=ft.icons.CLOSE, on_click=lambda e: self.page.close(self.dlg_grafico_lp_full))
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    ),
                    ft.Container(content=chart, expand=True, padding=ft.padding.all(20)),
                    ft.Row(items_leyenda, alignment="center")
                ])
            )
            
            self.page.close(self.dlg_grafico_lp)
            self.dlg_grafico_lp_full = ft.AlertDialog(content=contenido_final, modal=True, inset_padding=10)
            self.page.open(self.dlg_grafico_lp_full)

        threading.Thread(target=_tarea, daemon=True).start()
        
    def _sel_torneo_barra_modal(self, e):
        nombre = e.control.data
        self.temp_camp_barra = nombre
        
        for c in self.lv_torneos_barra.controls: c.bgcolor = "blue" if c.data == nombre else "#2D2D2D"
        self.lv_torneos_barra.update()
        
        anios = sorted([ed[2] for ed in self.cache_ediciones_modal if ed[1] == nombre], reverse=True)
        ctls = []
        for a in anios:
            ctls.append(ft.ListTile(title=ft.Text(str(a), size=14), data=a, on_click=self._sel_anio_barra_modal, bgcolor="#2D2D2D"))
        self.lv_anios_barra.controls = ctls
        self.lv_anios_barra.update()
        
        self.temp_anio_barra = None
        self._validar_btn_grafico_barras()

    def _sel_anio_barra_modal(self, e):
        self.temp_anio_barra = e.control.data
        for c in self.lv_anios_barra.controls: c.bgcolor = "blue" if c.data == self.temp_anio_barra else "#2D2D2D"
        self.lv_anios_barra.update()
        self._validar_btn_grafico_barras()

    def _sel_usuario_barra_modal(self, e):
        self.usuario_grafico_barra_sel = e.control.data
        for c in self.lv_usuarios_barra.controls: c.bgcolor = "blue" if c.data == self.usuario_grafico_barra_sel else "#2D2D2D"
        self.lv_usuarios_barra.update()
        self._validar_btn_grafico_barras()

    def _validar_btn_grafico_barras(self):
        habilitar = self.temp_camp_barra and self.temp_anio_barra and self.usuario_grafico_barra_sel
        self.btn_generar_grafico_barras.disabled = not habilitar
        self.btn_generar_grafico_barras.update()

    def _generar_grafico_barras(self, e):
        edicion_id = None
        for ed in self.cache_ediciones_modal:
            if ed[1] == self.temp_camp_barra and ed[2] == self.temp_anio_barra:
                edicion_id = ed[0]
                break
        
        if not edicion_id: return

        def _tarea():
            bd = BaseDeDatos()
            puntos_lista = bd.obtener_historial_puntos_usuario(edicion_id, self.usuario_grafico_barra_sel)
            
            if not puntos_lista:
                GestorMensajes.mostrar(self.page, "Info", "No hay partidos jugados o pronósticos para este usuario.", "info")
                return

            # Crear datos para el gráfico de barras
            bar_groups = []
            for i, puntos in enumerate(puntos_lista):
                n_partido = i + 1
                color_barra = ft.Colors.BLUE
                if puntos == 0: color_barra = ft.Colors.GREY
                elif puntos == MAXIMA_CANTIDAD_DE_PUNTOS: color_barra = ft.Colors.GREEN # Color especial para puntaje perfecto
                
                bar_groups.append(
                    ft.BarChartGroup(
                        x=n_partido,
                        bar_rods=[
                            ft.BarChartRod(
                                from_y=0,
                                to_y=puntos,
                                width=20,
                                color=color_barra,
                                tooltip=f"{puntos} pts",
                                border_radius=3
                            )
                        ]
                    )
                )

            # Ejes
            chart = ft.BarChart(
                bar_groups=bar_groups,
                border=ft.border.all(1, ft.Colors.WHITE10),
                left_axis=ft.ChartAxis(
                    labels_size=40,
                    title=ft.Text("Puntos", size=14, italic=True),
                    title_size=40
                ),
                bottom_axis=ft.ChartAxis(
                    labels=[
                        ft.ChartAxisLabel(value=i+1, label=ft.Text(str(i+1), size=12)) for i in range(len(puntos_lista))
                    ],
                    labels_size=40,
                    title=ft.Text("Partido N°", size=14, italic=True),
                    title_size=40
                ),
                horizontal_grid_lines=ft.ChartGridLines(interval=1, color=ft.Colors.WHITE10, width=1),
                min_y=0,
                max_y=MAXIMA_CANTIDAD_DE_PUNTOS + 1, # Un poco de margen
                expand=True
            )

            # Pantalla Completa
            ancho = self.page.width - 50
            alto = self.page.height - 50

            contenido_final = ft.Container(
                width=ancho, height=alto,
                padding=20, bgcolor="#1E1E1E",
                content=ft.Column([
                    ft.Row(
                        controls=[
                            ft.Text(f"Puntos de {self.usuario_grafico_barra_sel}: {self.temp_camp_barra} {self.temp_anio_barra}", size=24, weight="bold"),
                            ft.IconButton(icon=ft.icons.CLOSE, on_click=lambda e: self.page.close(self.dlg_grafico_barras_full))
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    ),
                    ft.Container(content=chart, expand=True, padding=ft.padding.all(20))
                ])
            )
            
            self.page.close(self.dlg_grafico_barras)
            self.dlg_grafico_barras_full = ft.AlertDialog(content=contenido_final, modal=True, inset_padding=10)
            self.page.open(self.dlg_grafico_barras_full)

        threading.Thread(target=_tarea, daemon=True).start()

    def _abrir_modal_mejor_predictor(self, e):
        """Abre la ventana modal con la tabla de Mejor Predictor (Error Absoluto)."""
        
        titulo = "Ranking Mejor Predictor (Histórico)"
        if self.filtro_ranking_nombre: 
             titulo = f"Ranking Mejor Predictor ({self.filtro_ranking_nombre})"
        elif self.filtro_ranking_anio:
             titulo = f"Ranking Mejor Predictor ({self.filtro_ranking_anio})"
             
        self.loading_modal = ft.ProgressBar(width=200, color="amber", bgcolor="#222222")
        
        columna_content = ft.Column(
            controls=[
                ft.Text(titulo, size=18, weight="bold", color="white"),
                ft.Container(height=10),
                self.loading_modal,
                ft.Container(height=50)
            ],
            height=150,
            width=700, # Un poco más ancho para el título de la columna error
            scroll=None
        )
        
        self.dlg_mejor_predictor = ft.AlertDialog(content=columna_content, modal=True)
        self.page.open(self.dlg_mejor_predictor)

        def _cargar():
            bd = BaseDeDatos()
            datos = bd.obtener_ranking_mejor_predictor(self.filtro_ranking_edicion_id, self.filtro_ranking_anio)
            
            filas = []
            for i, row in enumerate(datos, start=1):
                # row: [0] username, [1] promedio_error (float/decimal)
                user = row[0]
                val = float(row[1])
                
                txt_val = f"{val:.2f}".replace('.', ',')
                
                # --- Lógica de Clasificación ---
                if val == 0:
                    clasificacion = "🎯 Predictor perfecto"
                    color_val = "cyan"
                elif val <= 1.0:
                    clasificacion = "👌 Muy preciso"
                    color_val = "green"
                elif val <= 2.0:
                    clasificacion = "👍 Aceptable"
                    color_val = "yellow"
                else: # > 2.0
                    clasificacion = "🎲 Poco realista / arriesgado"
                    color_val = "red"

                filas.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Container(content=ft.Text(f"{i}º", weight="bold", color="white"), width=50, alignment=ft.alignment.center)),
                    ft.DataCell(ft.Container(content=ft.Text(user, weight="bold", color="white"), width=150, alignment=ft.alignment.center_left)),
                    ft.DataCell(ft.Container(content=ft.Text(txt_val, weight="bold", color=color_val), width=180, alignment=ft.alignment.center)),
                    ft.DataCell(ft.Container(content=ft.Text(clasificacion, weight="bold", color="white"), width=200, alignment=ft.alignment.center_left)),
                ]))
            
            tabla = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Container(content=ft.Text("Puesto", weight="bold", color="white"), width=50, alignment=ft.alignment.center)),
                    ft.DataColumn(ft.Container(content=ft.Text("Usuario", weight="bold", color="white"), width=150, alignment=ft.alignment.center_left)),
                    ft.DataColumn(ft.Container(content=ft.Text("Promedio error\nabsoluto de goles", text_align="center", weight="bold", color="white"), width=180, alignment=ft.alignment.center), numeric=True),
                    ft.DataColumn(ft.Container(content=ft.Text("Clasificación", weight="bold", color="white"), width=200, alignment=ft.alignment.center_left)),
                ],
                rows=filas,
                heading_row_color="black",
                border=ft.border.all(1, "white10"),
                column_spacing=10,
                heading_row_height=60,
                data_row_max_height=50,
                data_row_min_height=50
            )
            
            columna_content.height = 340
            columna_content.width = 700
            
            columna_content.controls = [
                ft.Text(titulo, size=18, weight="bold", color="white"),
                ft.Container(height=10),
                ft.Column(
                    controls=[tabla],
                    height=220,
                    scroll=ft.ScrollMode.AUTO
                ),
                ft.Container(height=10),
                ft.Row([ft.ElevatedButton("Cerrar", on_click=lambda e: self.page.close(self.dlg_mejor_predictor))], alignment=ft.MainAxisAlignment.END)
            ]
            self.dlg_mejor_predictor.update()
            
        threading.Thread(target=_cargar, daemon=True).start()

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
                
                # CORRECCIÓN: Pronósticos no afectan copas históricas.
                self._recargar_datos(actualizar_partidos=True, actualizar_pronosticos=True, actualizar_ranking=False, actualizar_copas=False)
                
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", f"No se pudo guardar: {ex}", "error")
                self.loading_partidos.visible = False
                self.page.update()

        threading.Thread(target=_tarea, daemon=True).start()

    def _abrir_modal_racha_actual(self, e):
        """Abre la ventana modal con la Racha Actual."""
        
        # Título dinámico según filtro
        if self.filtro_ranking_nombre: 
             titulo = f"Racha actual ({self.filtro_ranking_nombre})"
        elif self.filtro_ranking_anio:
             titulo = f"Racha actual ({self.filtro_ranking_anio})"
        else:
             titulo = "Racha actual en la historia"
             
        self.loading_modal = ft.ProgressBar(width=200, color="amber", bgcolor="#222222")
        
        columna_content = ft.Column(
            controls=[
                ft.Text(titulo, size=18, weight="bold", color="white"),
                ft.Container(height=10),
                self.loading_modal,
                ft.Container(height=20)
            ],
            height=150,
            width=500,
            scroll=None
        )
        
        self.dlg_racha = ft.AlertDialog(content=columna_content, modal=True)
        self.page.open(self.dlg_racha)

        def _cargar():
            bd = BaseDeDatos()
            datos = bd.obtener_racha_actual(self.filtro_ranking_edicion_id, self.filtro_ranking_anio)
            
            filas = []
            for i, row in enumerate(datos, start=1):
                # row: (usuario, racha)
                user = row[0]
                racha = row[1]
                
                # Colorimetría
                color_racha = "white"
                if racha >= 5: color_racha = "cyan"     # Racha excelente
                elif racha >= 3: color_racha = "green"  # Racha buena
                elif racha == 0: color_racha = "red"    # Sin racha

                filas.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Container(content=ft.Text(f"{i}º", weight="bold", color="white"), width=50, alignment=ft.alignment.center)),
                    ft.DataCell(ft.Container(content=ft.Text(user, weight="bold", color="white"), width=150, alignment=ft.alignment.center_left)),
                    ft.DataCell(ft.Container(content=ft.Text(str(racha), weight="bold", color=color_racha), width=100, alignment=ft.alignment.center)),
                ]))
            
            tabla = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Container(content=ft.Text("Puesto", weight="bold", color="white"), width=50, alignment=ft.alignment.center)),
                    ft.DataColumn(ft.Container(content=ft.Text("Usuario", weight="bold", color="white"), width=150, alignment=ft.alignment.center_left)),
                    ft.DataColumn(ft.Container(content=ft.Text("Racha actual", text_align="center", weight="bold", color="white"), width=100, alignment=ft.alignment.center), numeric=True),
                ],
                rows=filas,
                heading_row_color="black",
                border=ft.border.all(1, "white10"),
                column_spacing=10,
                heading_row_height=60,
                data_row_max_height=50,
                data_row_min_height=50
            )
            
            # Ajuste de tamaño para mostrar datos + botón cerrar
            columna_content.height = 360
            columna_content.width = 500
            
            columna_content.controls = [
                ft.Text(titulo, size=18, weight="bold", color="white"),
                ft.Container(height=10),
                ft.Column(
                    controls=[tabla],
                    height=220,
                    scroll=ft.ScrollMode.AUTO
                ),
                ft.Container(height=10),
                ft.Row([ft.ElevatedButton("Cerrar", on_click=lambda e: self.page.close(self.dlg_racha))], alignment=ft.MainAxisAlignment.END)
            ]
            self.dlg_racha.update()
            
        threading.Thread(target=_cargar, daemon=True).start()

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
        self.btn_ver_usuario = ft.ElevatedButton("Ver", icon=ft.icons.VISIBILITY, disabled=True, on_click=self._confirmar_filtro_usuario_pronosticos)
        
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

    def _confirmar_filtro_torneo_pronosticos(self, e):
        if self.temp_campeonato_sel and self.temp_anio_sel:
            nombre_completo = f"{self.temp_campeonato_sel} {self.temp_anio_sel}"
            self.filtro_pron_torneo = nombre_completo
            
            # Actualizamos visual
            self._actualizar_botones_pronosticos_visual()
            
            self._actualizar_titulo_pronosticos()
            self.page.close(self.dlg_modal)
            self._recargar_datos(actualizar_pronosticos=True)

    def _abrir_selector_torneo_pronosticos(self, e):
        # Reutilizamos el mismo diseño del modal, pero cambiamos la acción del botón "Ver"
        self.lv_torneos = ft.ListView(expand=True, spacing=5, height=200)
        self.lv_anios = ft.ListView(expand=True, spacing=5, height=200)
        
        # El botón llama a _confirmar_filtro_torneo_pronosticos
        self.btn_ver_torneo = ft.ElevatedButton("Ver", icon=ft.icons.VISIBILITY, disabled=True, on_click=self._confirmar_filtro_torneo_pronosticos)
        
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

    def _confirmar_filtro_equipo_pronosticos(self, e):
        if self.temp_rival_sel_nombre:
            self.filtro_pron_equipo = self.temp_rival_sel_nombre
            
            self._actualizar_botones_pronosticos_visual()
            
            self._actualizar_titulo_pronosticos()
            self.page.close(self.dlg_modal_equipo)
            self._recargar_datos(actualizar_pronosticos=True)

    def _confirmar_filtro_usuario_pronosticos(self, e):
        """Confirma selección usuario (COMBINABLE)"""
        if self.temp_usuario_sel:
            self.filtro_pron_usuario = self.temp_usuario_sel
            
            self._actualizar_botones_pronosticos_visual()
            
            self._actualizar_titulo_pronosticos()
            self.page.close(self.dlg_modal_usuario)
            self._recargar_datos(actualizar_pronosticos=True)

    def _abrir_selector_equipo_pronosticos(self, e):
        self.lv_equipos = ft.ListView(expand=True, spacing=5, height=300)
        # El botón llama a _confirmar_filtro_equipo_pronosticos
        self.btn_ver_equipo = ft.ElevatedButton("Ver", icon=ft.icons.VISIBILITY, disabled=True, on_click=self._confirmar_filtro_equipo_pronosticos)
        
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

    def _seleccionar_anio_ranking_modal(self, e):
        anio_sel = e.control.data
        self.temp_anio_sel = anio_sel # Reutilizamos variable temporal
        
        for c in self.lv_anios_ranking.controls:
            c.bgcolor = "blue" if c.data == anio_sel else "#2D2D2D"
        self.lv_anios_ranking.update()
        
        self.btn_ver_anio.disabled = False
        self.btn_ver_anio.update()

    def _seleccionar_partido_click(self, id_partido):
        """
        Simula la selección de una fila tipo 'Treeview'.
        Recibe el ID del partido desde el evento on_click de la celda.
        """
        # Si toco el mismo que ya estaba seleccionado, lo desmarco
        if self.partido_a_pronosticar_id == id_partido:
            self.partido_a_pronosticar_id = None
            self.input_pred_cai.value = ""
            self.input_pred_rival.value = ""
            
            # Desmarcar todo (quitar color)
            for row in self.tabla_partidos.rows:
                row.color = None
            self.page.update()
            return

        # Nueva selección
        self.partido_a_pronosticar_id = id_partido
        
        # Iteramos filas para pintar la correcta y leer sus datos
        for row in self.tabla_partidos.rows:
            if row.data == id_partido:
                row.color = "#8B0000" # Rojo oscuro
                
                # Intentamos leer el pronóstico visual de la celda 4
                try:
                    # Estructura: DataCell -> Container -> Text -> value
                    texto_celda = row.cells[4].content.content.value
                    if " a " in texto_celda:
                        partes = texto_celda.split(" a ")
                        self.input_pred_cai.value = partes[0]
                        self.input_pred_rival.value = partes[1]
                    else:
                        self.input_pred_cai.value = ""
                        self.input_pred_rival.value = ""
                except:
                    self.input_pred_cai.value = ""
                    self.input_pred_rival.value = ""
            else:
                row.color = None
        
        self.page.update()

    def _guardar_contrasena_config(self, e):
        """Valida y guarda el cambio de contraseña desde Configuración."""
        p1 = self.input_conf_pass_1.value
        p2 = self.input_conf_pass_2.value

        # 1. Validaciones básicas
        if not p1 or not p2:
            GestorMensajes.mostrar(self.page, "Error", "Debe completar ambos campos.", "error")
            return
        
        if p1 != p2:
            GestorMensajes.mostrar(self.page, "Error", "Las contraseñas no coinciden.", "error")
            return

        # Opcional: Validar longitud mínima
        if len(p1) < 4:
            GestorMensajes.mostrar(self.page, "Error", "La contraseña es muy corta.", "error")
            return

        # 2. Proceso en segundo plano
        def _tarea():
            # Deshabilitar botón para evitar doble clic
            self.btn_conf_guardar_pass.disabled = True
            self.btn_conf_guardar_pass.update()
            
            try:
                bd = BaseDeDatos()
                # Reutilizamos la función existente en tu BD
                bd.cambiar_contrasena(self.usuario_actual, p1)
                
                GestorMensajes.mostrar(self.page, "Éxito", "Contraseña actualizada correctamente.", "exito")
                
                # Limpiar campos
                self.input_conf_pass_1.value = ""
                self.input_conf_pass_2.value = ""
                self.input_conf_pass_1.update()
                self.input_conf_pass_2.update()
                
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", f"No se pudo cambiar: {ex}", "error")
            
            finally:
                self.btn_conf_guardar_pass.disabled = False
                self.btn_conf_guardar_pass.update()

        threading.Thread(target=_tarea, daemon=True).start()

    def _abrir_modal_mufa(self, e):
        """Muestra el ranking de 'Mufa' (Quienes aciertan más derrotas)."""
        try:
            bd = BaseDeDatos()
            datos = bd.obtener_ranking_mufa(self.filtro_ranking_edicion_id, self.filtro_ranking_anio)
            
            filas = []
            for i, fila in enumerate(datos, start=1):
                user = fila[0]
                pred_derrotas = fila[1]
                aciertos = fila[2]
                porcentaje = fila[3]
                
                txt_porcentaje = f"{porcentaje:.1f}%".replace('.', ',')
                
                # Rojo si acierta mucho las derrotas (Muy mufa)
                if porcentaje >= 50: color_txt = "red"
                elif porcentaje >= 20: color_txt = "orange"
                else: color_txt = "green" 
                
                filas.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(f"{i}º", color="white", weight=ft.FontWeight.BOLD)),
                    ft.DataCell(ft.Text(user, color="white")),
                    ft.DataCell(ft.Container(content=ft.Text(str(pred_derrotas), color="cyan"), alignment=ft.alignment.center)),
                    ft.DataCell(ft.Container(content=ft.Text(str(aciertos), color="white"), alignment=ft.alignment.center)),
                    ft.DataCell(ft.Container(content=ft.Text(txt_porcentaje, color=color_txt, weight=ft.FontWeight.BOLD), alignment=ft.alignment.center)),
                ]))

            tabla = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text("Pos")),
                    ft.DataColumn(ft.Text("Usuario")),
                    ft.DataColumn(ft.Text("Pred. Derrota", tooltip="Veces que pronosticó que perdíamos"), numeric=True),
                    ft.DataColumn(ft.Text("Acertadas", tooltip="Veces que pronosticó derrota y PERDIMOS"), numeric=True),
                    ft.DataColumn(ft.Text("% Mufa", tooltip="Porcentaje de derrotas acertadas"), numeric=True),
                ],
                rows=filas,
                heading_row_color="black",
                data_row_color={"hoverED": "#1A1A1A"},
                border=ft.border.all(1, "white10"),
                column_spacing=20
            )
            
            dlg = ft.AlertDialog(
                title=ft.Text("Ranking Mufa 🌩️"),
                content=ft.Column([
                    ft.Text("Usuarios que más aciertan cuando pronostican que el Rojo pierde.", size=12, color="white70"),
                    # CORRECCIÓN: Quitamos 'scroll' del Container y agregamos un Column interno con scroll
                    ft.Container(
                        height=400,
                        content=ft.Column(
                            controls=[tabla],
                            scroll=ft.ScrollMode.AUTO # Aquí sí va el scroll
                        )
                    )
                ], tight=True),
                actions=[ft.TextButton("Cerrar", on_click=lambda e: self.page.close(dlg))]
            )
            self.page.open(dlg)

        except Exception as ex:
            GestorMensajes.mostrar(self.page, "Error", f"No se pudo cargar mufa: {ex}", "error")
            return
        
    def _seleccionar_rival_admin(self, id_rival):
        """Maneja el clic en la tabla de administración de equipos (Sin Recarga de BD)."""
        self.rival_seleccionado_id = id_rival
        
        # Recorrer filas para pintar la correcta y extraer datos de la UI
        encontrado = False
        for row in self.tabla_rivales.rows:
            if row.data == id_rival:
                row.color = "#8B0000" # Pintar Rojo Oscuro
                
                # Extraer datos visuales de las celdas (Cell 0: Nombre, Cell 1: Otro Nombre)
                # Estructura visual: DataCell -> Container -> Text -> value
                try:
                    nombre_ui = row.cells[0].content.content.value
                    otro_ui = row.cells[1].content.content.value
                    
                    self.input_admin_nombre.value = nombre_ui
                    self.input_admin_otro.value = otro_ui
                    self.input_admin_nombre.update()
                    self.input_admin_otro.update()
                except Exception as e:
                    print(f"Error leyendo datos de la fila: {e}")
                
                encontrado = True
            else:
                row.color = None # Despintar las otras
        
        if encontrado:
            self.tabla_rivales.update()

    def _guardar_rival_admin(self, e):
        """Guarda los cambios con validaciones y recarga tablas (sin Ranking)."""
        if not self.rival_seleccionado_id:
            GestorMensajes.mostrar(self.page, "Error", "Seleccione un equipo de la tabla.", "error")
            return
            
        nombre = self.input_admin_nombre.value.strip()
        otro = self.input_admin_otro.value.strip()
        
        # VALIDACIONES
        if not nombre:
            GestorMensajes.mostrar(self.page, "Error", "El nombre es obligatorio.", "error")
            return

        if not otro:
            GestorMensajes.mostrar(self.page, "Error", "El 'Otro nombre' no puede estar vacío.", "error")
            return

        if nombre.lower() == otro.lower():
            GestorMensajes.mostrar(self.page, "Error", "El 'Otro nombre' debe ser distinto al 'Nombre'.", "error")
            return

        def _guardar():
            # 1. Mostrar animaciones de carga INMEDIATAMENTE (sin vaciar tablas aún)
            self.loading_partidos.visible = True
            self.loading_pronosticos.visible = True
            self.loading_admin.visible = True
            self.page.update()
            
            # 2. Guardar en BD
            try:
                bd = BaseDeDatos()
                bd.actualizar_rival(self.rival_seleccionado_id, nombre, otro)
                
                GestorMensajes.mostrar(self.page, "Éxito", "Equipo actualizado.", "exito")
                
                # Limpiar formulario
                self.rival_seleccionado_id = None
                self.input_admin_nombre.value = ""
                self.input_admin_otro.value = ""
                
                # 3. Recargar tablas afectadas (Partidos, Pronósticos, Equipos)
                # IMPORTANTE: actualizar_ranking=False para no tocar la tabla de posiciones
                self._recargar_datos(
                    actualizar_partidos=True, 
                    actualizar_pronosticos=True, 
                    actualizar_ranking=False, # No recargar ranking
                    actualizar_admin=True,    # Recargar tabla de equipos
                    actualizar_copas=False
                )
                
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", f"No se pudo guardar: {ex}", "error")
                # Si hubo error, ocultamos las barras que prendimos
                self.loading_partidos.visible = False
                self.loading_pronosticos.visible = False
                self.loading_admin.visible = False
                self.page.update()

        threading.Thread(target=_guardar, daemon=True).start()

    def _guardar_contrasena_config(self, e):
        """
        Valida y guarda el cambio de contraseña desde la pestaña Configuración.
        """
        p1 = self.input_conf_pass_1.value
        p2 = self.input_conf_pass_2.value

        # --- 1. Validaciones Visuales ---
        if not p1 or not p2:
            GestorMensajes.mostrar(self.page, "Atención", "Por favor, complete ambos campos.", "error")
            return
        
        if p1 != p2:
            GestorMensajes.mostrar(self.page, "Error", "Las contraseñas no coinciden.", "error")
            # Opcional: Marcar bordes en rojo
            self.input_conf_pass_1.border_color = "red"
            self.input_conf_pass_2.border_color = "red"
            self.input_conf_pass_1.update()
            self.input_conf_pass_2.update()
            return
        else:
            # Restaurar bordes si coinciden
            self.input_conf_pass_1.border_color = "white24"
            self.input_conf_pass_2.border_color = "white24"
            self.input_conf_pass_1.update()
            self.input_conf_pass_2.update()

        if len(p1) < 4:
            GestorMensajes.mostrar(self.page, "Seguridad", "La contraseña es muy corta (mínimo 4 caracteres).", "info")
            return

        # --- 2. Guardado en Segundo Plano ---
        def _tarea():
            # Deshabilitar botón para evitar doble clic
            self.btn_conf_guardar_pass.disabled = True
            self.btn_conf_guardar_pass.text = "Guardando..."
            self.btn_conf_guardar_pass.update()
            
            try:
                bd = BaseDeDatos()
                # Usamos la función cambiar_contrasena que ya tienes en base_de_datos.py
                # (Sirve tanto para recuperar como para cambiar estando logueado)
                bd.cambiar_contrasena(self.usuario_actual, p1)
                
                GestorMensajes.mostrar(self.page, "Éxito", "Contraseña actualizada correctamente.", "exito")
                
                # Limpiar campos
                self.input_conf_pass_1.value = ""
                self.input_conf_pass_2.value = ""
                self.input_conf_pass_1.update()
                self.input_conf_pass_2.update()
                
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", f"No se pudo cambiar: {ex}", "error")
            
            finally:
                # Rehabilitar botón
                self.btn_conf_guardar_pass.disabled = False
                self.btn_conf_guardar_pass.text = "Guardar nueva clave"
                self.btn_conf_guardar_pass.update()

        threading.Thread(target=_tarea, daemon=True).start()

    def _recargar_datos(self, actualizar_partidos=False, actualizar_pronosticos=False, actualizar_ranking=False, actualizar_copas=True, actualizar_admin=False):
        """
        Recarga los datos de las tablas solicitadas en segundo plano.
        """
        if actualizar_partidos: self.cargando_partidos = True
            
        if not any([actualizar_partidos, actualizar_pronosticos, actualizar_ranking, actualizar_admin]):
            return

        # --- SPINNERS ---
        if actualizar_ranking: self.loading.visible = True
        if actualizar_ranking and actualizar_copas and self.filtro_ranking_edicion_id is None: 
            self.loading_copas.visible = True 
        if actualizar_partidos: 
            self.loading_partidos.visible = True
            self._bloquear_botones_filtros(True) 
        if actualizar_pronosticos: 
            self.loading_pronosticos.visible = True
            self.tabla_pronosticos.sort_column_index = self.pronosticos_sort_col_index
            self.tabla_pronosticos.sort_ascending = self.pronosticos_sort_asc
        if actualizar_admin: self.loading_admin.visible = True
        
        self.page.update()

        def _tarea_en_segundo_plano():
            time.sleep(0.5) 
            try:
                bd = BaseDeDatos()
                
                # ------------------------------------------
                # 1. RANKING (Formato de Anticipación Corregido)
                # ------------------------------------------
                if actualizar_ranking:
                    datos_ranking = bd.obtener_ranking(self.filtro_ranking_edicion_id, self.filtro_ranking_anio)
                    filas_ranking = []
                    for i, fila in enumerate(datos_ranking, start=1):
                        user = fila[0]
                        total = fila[1]
                        promedio_intentos = fila[7]
                        efectividad = fila[8]
                        
                        # --- NUEVA LÓGICA DE FORMATO PARA ANTICIPACIÓN ---
                        raw_seconds = fila[6]
                        
                        if raw_seconds is not None:
                            val_sec = float(raw_seconds)
                            
                            # Cálculos matemáticos
                            dias = int(val_sec // 86400)
                            resto = val_sec % 86400
                            horas = int(resto // 3600)
                            resto %= 3600
                            minutos = int(resto // 60)
                            segundos = resto % 60
                            
                            # Formato de texto para días (singular/plural)
                            txt_dias = "1 día" if dias == 1 else f"{dias} días"
                            
                            # Formato final: "X días HH:MM:SS.ss h"
                            # :02d -> Rellena con ceros a 2 dígitos enteros (ej: 03)
                            # :05.2f -> Rellena con ceros a 2 enteros, punto y 2 decimales (ej: 05.23)
                            txt_ant = f"{txt_dias} {horas:02d}:{minutos:02d}:{segundos:05.2f} h"
                        else:
                            txt_ant = "0 días 00:00:00.00 h"

                        txt_intentos = f"{promedio_intentos:.2f}".replace('.', ',')
                        txt_efectividad = f"{efectividad:.2f} %".replace('.', ',')

                        color_fila = "#8B0000" if user == self.usuario_seleccionado_ranking else None
                        
                        evento_click = lambda e, u=user: self._seleccionar_fila_ranking(u)

                        filas_ranking.append(ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(content=ft.Text(f"{i}º", weight=ft.FontWeight.BOLD, color="white"), width=60, alignment=ft.alignment.center, on_click=evento_click)),
                                ft.DataCell(ft.Container(content=ft.Text(user, weight=ft.FontWeight.BOLD, color="white"), width=110, alignment=ft.alignment.center_left, on_click=evento_click)),
                                ft.DataCell(ft.Container(content=ft.Text(str(total), weight=ft.FontWeight.BOLD, color="yellow", size=16), width=100, alignment=ft.alignment.center, on_click=evento_click)),
                                ft.DataCell(ft.Container(content=ft.Text(str(fila[2]), color="white"), width=120, alignment=ft.alignment.center, on_click=evento_click)),
                                ft.DataCell(ft.Container(content=ft.Text(str(fila[3]), color="white"), width=120, alignment=ft.alignment.center, on_click=evento_click)),
                                ft.DataCell(ft.Container(content=ft.Text(str(fila[4]), color="white"), width=120, alignment=ft.alignment.center, on_click=evento_click)),
                                ft.DataCell(ft.Container(content=ft.Text(str(fila[5]), color="cyan", weight=ft.FontWeight.BOLD), width=120, alignment=ft.alignment.center, on_click=evento_click)),
                                # Celda de Anticipación con el nuevo texto
                                ft.DataCell(ft.Container(content=ft.Text(txt_ant, color="cyan", size=12), width=200, alignment=ft.alignment.center, on_click=evento_click)),
                                ft.DataCell(ft.Container(content=ft.Text(txt_intentos, color="cyan"), width=80, alignment=ft.alignment.center, on_click=evento_click)),
                                ft.DataCell(ft.Container(content=ft.Text(txt_efectividad, color="green", weight=ft.FontWeight.BOLD), width=100, alignment=ft.alignment.center, on_click=evento_click)),
                            ],
                            color=color_fila,
                            data=user 
                        ))
                    self.tabla_estadisticas.rows = filas_ranking

                # ------------------------------------------
                # 2. COPAS
                # ------------------------------------------
                if actualizar_copas and self.filtro_ranking_edicion_id is None:
                    datos_copas = bd.obtener_torneos_ganados(self.filtro_ranking_anio)
                    filas_copas = []
                    for i, fila in enumerate(datos_copas, start=1):
                        user = fila[0]
                        copas = fila[1]
                        filas_copas.append(ft.DataRow(cells=[
                            ft.DataCell(ft.Container(content=ft.Text(f"{i}º", weight=ft.FontWeight.BOLD, color="white"), width=60, alignment=ft.alignment.center)),
                            ft.DataCell(ft.Container(content=ft.Text(user, weight=ft.FontWeight.BOLD, color="white"), width=110, alignment=ft.alignment.center_left)),
                            ft.DataCell(ft.Container(content=ft.Text(str(copas), weight=ft.FontWeight.BOLD, color="yellow", size=16), width=120, alignment=ft.alignment.center)),
                        ]))
                    self.tabla_copas.rows = filas_copas

                # ------------------------------------------
                # 3. PARTIDOS
                # ------------------------------------------
                if actualizar_partidos:
                    datos_partidos_user = bd.obtener_partidos(
                        self.usuario_actual, 
                        filtro_tiempo=self.filtro_temporal, 
                        edicion_id=self.filtro_edicion_id, 
                        rival_id=self.filtro_rival_id, 
                        solo_sin_pronosticar=self.filtro_sin_pronosticar
                    )
                    filas_tabla_partidos = []
                    for fila in datos_partidos_user:
                        p_id = fila[0]
                        rival = fila[1]
                        torneo = fila[3]
                        gc = fila[4]
                        gr = fila[5]
                        fecha_display_str = fila[7] 
                        pred_cai = fila[8]
                        pred_rival = fila[9]
                        puntos_usuario = fila[10] 
                        error_abs = fila[11]

                        if gc is not None and gr is not None: texto_resultado = f"{gc} a {gr}"
                        else: texto_resultado = "-"
                        if pred_cai is not None and pred_rival is not None: texto_pronostico = f"{pred_cai} a {pred_rival}"
                        else: texto_pronostico = "-"
                        if puntos_usuario is None: texto_puntos = "-"
                        else: texto_puntos = f"{puntos_usuario}"

                        if error_abs is None:
                            txt_error = "-"
                            color_error = "white70"
                        else:
                            val_err = int(error_abs)
                            txt_error = str(val_err)
                            if val_err == 0: color_error = "cyan"
                            elif val_err <= 2: color_error = "green"
                            elif val_err <= 4: color_error = "yellow"
                            else: color_error = "red"

                        color_fila = "#8B0000" if p_id == self.partido_a_pronosticar_id else None

                        evt_click = lambda e, id=p_id: self._seleccionar_partido_click(id)

                        filas_tabla_partidos.append(ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(content=ft.Text(str(rival), weight=ft.FontWeight.BOLD, color="white", no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS), width=250, alignment=ft.alignment.center_left, on_click=evt_click)), 
                                ft.DataCell(ft.Container(content=ft.Text(texto_resultado, color="white", weight=ft.FontWeight.BOLD), alignment=ft.alignment.center, on_click=evt_click)),
                                ft.DataCell(ft.Container(content=ft.Text(fecha_display_str, color="white70"), width=140, alignment=ft.alignment.center_left, on_click=evt_click)), 
                                ft.DataCell(ft.Container(content=ft.Text(str(torneo), color="yellow", weight=ft.FontWeight.BOLD), width=150, alignment=ft.alignment.center_left, on_click=evt_click)),
                                ft.DataCell(ft.Container(content=ft.Text(texto_pronostico, color="cyan", weight=ft.FontWeight.BOLD), alignment=ft.alignment.center, on_click=evt_click)),
                                ft.DataCell(ft.Container(content=ft.Text(texto_puntos, color="green", weight=ft.FontWeight.BOLD, size=15), alignment=ft.alignment.center, on_click=evt_click)),
                                ft.DataCell(ft.Container(content=ft.Text(txt_error, color=color_error, weight=ft.FontWeight.BOLD, size=14), alignment=ft.alignment.center, on_click=evt_click))
                            ],
                            data=p_id,
                            color=color_fila 
                        ))
                    self.tabla_partidos.rows = filas_tabla_partidos

                # ------------------------------------------
                # 4. PRONÓSTICOS
                # ------------------------------------------
                if actualizar_pronosticos:
                    datos_raw = bd.obtener_todos_pronosticos()
                    filas_filtradas = []
                    
                    for row in datos_raw:
                        fecha_partido = row[1]
                        ahora = datetime.now()
                        if self.filtro_pron_tiempo == 'futuros' and fecha_partido <= ahora: continue
                        if self.filtro_pron_tiempo == 'jugados' and fecha_partido > ahora: continue
                        
                        if self.filtro_pron_torneo and self.filtro_pron_torneo != row[2]: continue
                        if self.filtro_pron_equipo and self.filtro_pron_equipo != row[0]: continue
                        if self.filtro_pron_usuario and self.filtro_pron_usuario != row[5]: continue
                        
                        gc, gr = row[3], row[4]
                        pc, pr = row[6], row[7]
                        pts, err_abs = row[8], row[10]
                        
                        res_txt = f"{gc}-{gr}" if gc is not None else "-"
                        pron_txt = f"{pc}-{pr}"
                        
                        if fecha_partido.time().strftime('%H:%M:%S') == '00:00:00': fecha_disp = fecha_partido.strftime('%d/%m/%Y')
                        else: fecha_disp = fecha_partido.strftime('%d/%m/%Y %H:%M')
                            
                        fecha_pred_disp = row[9].strftime('%d/%m %H:%M') if row[9] else "-"
                        puntos_disp = str(pts) if pts is not None else "-"
                        
                        if err_abs is not None:
                            val_err = int(err_abs)
                            err_disp = str(val_err)
                            if val_err == 0: color_err = "cyan"
                            elif val_err <= 2: color_err = "green"
                            elif val_err <= 4: color_err = "yellow"
                            else: color_err = "red"
                        else:
                            err_disp = "-"
                            color_err = "white70"

                        # ID ÚNICO
                        row_key = hash(row)
                        color_fila_pron = "#8B0000" if row_key == self.pronostico_seleccionado_key else None
                        
                        evt_click_pron = lambda e, k=row_key: self._seleccionar_fila_pronostico(k)

                        filas_filtradas.append(ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(content=ft.Text(row[0], color="white", weight=ft.FontWeight.BOLD), width=250, alignment=ft.alignment.center_left, on_click=evt_click_pron)),
                                ft.DataCell(ft.Container(content=ft.Text(fecha_disp, color="white"), width=140, alignment=ft.alignment.center, on_click=evt_click_pron)),
                                ft.DataCell(ft.Container(content=ft.Text(row[2], color="yellow"), width=150, alignment=ft.alignment.center_left, on_click=evt_click_pron)),
                                ft.DataCell(ft.Container(content=ft.Text(res_txt, color="white", weight=ft.FontWeight.BOLD), width=80, alignment=ft.alignment.center, on_click=evt_click_pron)),
                                ft.DataCell(ft.Container(content=ft.Text(row[5], color="white", weight=ft.FontWeight.BOLD), width=100, alignment=ft.alignment.center_left, on_click=evt_click_pron)),
                                ft.DataCell(ft.Container(content=ft.Text(pron_txt, color="cyan", weight=ft.FontWeight.BOLD), width=80, alignment=ft.alignment.center, on_click=evt_click_pron)),
                                ft.DataCell(ft.Container(content=ft.Text(fecha_pred_disp, color="white70"), width=140, alignment=ft.alignment.center, on_click=evt_click_pron)),
                                ft.DataCell(ft.Container(content=ft.Text(puntos_disp, color="green", weight=ft.FontWeight.BOLD), width=60, alignment=ft.alignment.center, on_click=evt_click_pron)),
                                ft.DataCell(ft.Container(content=ft.Text(err_disp, color=color_err, weight=ft.FontWeight.BOLD), width=80, alignment=ft.alignment.center, on_click=evt_click_pron)),
                            ],
                            color=color_fila_pron,
                            data=row_key 
                        ))
                    
                    if self.pronosticos_sort_col_index is not None:
                        idx = self.pronosticos_sort_col_index
                        reverse_sort = not self.pronosticos_sort_asc
                        def key_sort(row):
                            try:
                                val = row.cells[idx].content.content.value
                                if idx in [7, 8]: return float(val) if val != "-" else -999
                                if idx in [1, 6]:
                                    try:
                                        if ":" in val:
                                            if val.count("/") == 2: return datetime.strptime(val, "%d/%m/%Y %H:%M")
                                            return datetime.strptime(val, "%d/%m %H:%M")
                                        return datetime.strptime(val, "%d/%m/%Y")
                                    except: return val
                                return str(val).lower()
                            except: return ""
                        filas_filtradas.sort(key=key_sort, reverse=reverse_sort)
                    
                    self.tabla_pronosticos.rows = filas_filtradas

                # ------------------------------------------
                # 5. ADMINISTRACIÓN
                # ------------------------------------------
                if actualizar_admin:
                    datos_rivales = bd.obtener_rivales_completo()
                    filas_admin = []
                    for fila in datos_rivales:
                        r_id = fila[0]
                        nombre = fila[1]
                        otro = fila[2] if fila[2] else ""
                        color_row = "#8B0000" if r_id == self.rival_seleccionado_id else None
                        
                        filas_admin.append(ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(content=ft.Text(nombre, color="white"), width=250, alignment=ft.alignment.center_left, on_click=lambda e, id=r_id: self._seleccionar_rival_admin(id))),
                                ft.DataCell(ft.Container(content=ft.Text(otro, color="cyan"), width=250, alignment=ft.alignment.center_left, on_click=lambda e, id=r_id: self._seleccionar_rival_admin(id))),
                            ],
                            data=r_id,
                            color=color_row
                        ))
                    self.tabla_rivales.rows = filas_admin

            except Exception as e:
                print(f"Error recargando datos: {e}")
            
            finally:
                self.loading.visible = False
                self.loading_copas.visible = False 
                self.loading_partidos.visible = False
                self.loading_pronosticos.visible = False 
                self.loading_admin.visible = False
                
                if actualizar_partidos: 
                    self.cargando_partidos = False
                    self._bloquear_botones_filtros(False) 
                    self._actualizar_botones_partidos_visual()
                if actualizar_pronosticos:
                    self._actualizar_botones_pronosticos_visual()
                    
                self.page.update()

        threading.Thread(target=_tarea_en_segundo_plano, daemon=True).start()

    def _abrir_modal_racha_record(self, e):
        """Abre la ventana modal con la Racha Récord."""
        
        # Título dinámico
        if self.filtro_ranking_nombre: 
             titulo = f"Racha récord ({self.filtro_ranking_nombre})"
        elif self.filtro_ranking_anio:
             titulo = f"Racha récord ({self.filtro_ranking_anio})"
        else:
             titulo = "Racha récord en la historia"
             
        self.loading_modal = ft.ProgressBar(width=200, color="amber", bgcolor="#222222")
        
        columna_content = ft.Column(
            controls=[
                ft.Text(titulo, size=18, weight="bold", color="white"),
                ft.Container(height=10),
                self.loading_modal,
                ft.Container(height=20)
            ],
            height=150,
            width=500,
            scroll=None
        )
        
        self.dlg_racha_record = ft.AlertDialog(content=columna_content, modal=True)
        self.page.open(self.dlg_racha_record)

        def _cargar():
            bd = BaseDeDatos()
            datos = bd.obtener_racha_record(self.filtro_ranking_edicion_id, self.filtro_ranking_anio)
            
            filas = []
            for i, row in enumerate(datos, start=1):
                # row: (usuario, racha_maxima)
                user = row[0]
                racha = row[1]
                
                # Colorimetría para destacar récords altos
                color_racha = "white"
                if racha >= 10: color_racha = "purple"
                elif racha >= 7: color_racha = "cyan"
                elif racha >= 4: color_racha = "green"

                filas.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Container(content=ft.Text(f"{i}º", weight="bold", color="white"), width=50, alignment=ft.alignment.center)),
                    ft.DataCell(ft.Container(content=ft.Text(user, weight="bold", color="white"), width=150, alignment=ft.alignment.center_left)),
                    ft.DataCell(ft.Container(content=ft.Text(str(racha), weight="bold", color=color_racha), width=100, alignment=ft.alignment.center)),
                ]))
            
            tabla = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Container(content=ft.Text("Puesto", weight="bold", color="white"), width=50, alignment=ft.alignment.center)),
                    ft.DataColumn(ft.Container(content=ft.Text("Usuario", weight="bold", color="white"), width=150, alignment=ft.alignment.center_left)),
                    ft.DataColumn(ft.Container(content=ft.Text("Racha récord", text_align="center", weight="bold", color="white"), width=100, alignment=ft.alignment.center), numeric=True),
                ],
                rows=filas,
                heading_row_color="black",
                border=ft.border.all(1, "white10"),
                column_spacing=10,
                heading_row_height=60,
                data_row_max_height=50,
                data_row_min_height=50
            )
            
            columna_content.height = 360
            columna_content.width = 500
            
            columna_content.controls = [
                ft.Text(titulo, size=18, weight="bold", color="white"),
                ft.Container(height=10),
                ft.Column(
                    controls=[tabla],
                    height=220,
                    scroll=ft.ScrollMode.AUTO
                ),
                ft.Container(height=10),
                ft.Row([ft.ElevatedButton("Cerrar", on_click=lambda e: self.page.close(self.dlg_racha_record))], alignment=ft.MainAxisAlignment.END)
            ]
            self.dlg_racha_record.update()
            
        threading.Thread(target=_cargar, daemon=True).start()

    def _iniciar_cambio_email(self, e):
        """Valida el email, verifica disponibilidad y envía código."""
        nuevo_email = self.input_conf_email.value.strip()
        
        # 1. Validaciones
        if not nuevo_email or "@" not in nuevo_email or "." not in nuevo_email:
            GestorMensajes.mostrar(self.page, "Error", "Ingrese un correo válido.", "error")
            return

        def _tarea_envio():
            self.btn_conf_guardar_email.disabled = True
            self.btn_conf_guardar_email.text = "Enviando..."
            self.btn_conf_guardar_email.update()
            
            try:
                bd = BaseDeDatos()
                
                # --- CORRECCIÓN AQUÍ ---
                # Usamos la nueva función que ignora tu propio usuario y solo mira si el email está ocupado por otros
                bd.verificar_email_libre(nuevo_email, self.usuario_actual) 
                
                # Generar código
                self.codigo_verificacion_temp = str(random.randint(100000, 999999))
                self.email_pendiente_cambio = nuevo_email
                
                if REMITENTE == "tu_correo@gmail.com":
                    print(f"--- MODO DEBUG: EL CÓDIGO ES {self.codigo_verificacion_temp} ---")
                else:
                    msg = MIMEMultipart()
                    msg['From'] = REMITENTE
                    msg['To'] = nuevo_email
                    msg['Subject'] = "Código de verificación - Sistema CAI"
                    cuerpo = f"Hola {self.usuario_actual},\n\nTu código para cambiar el correo es: {self.codigo_verificacion_temp}\n\nSi no solicitaste esto, ignora este mensaje."
                    msg.attach(MIMEText(cuerpo, 'plain'))
                    
                    server = smtplib.SMTP('smtp.gmail.com', 587)
                    server.starttls()
                    server.login(REMITENTE, PASSWORD)
                    server.send_message(msg)
                    server.quit()

                # Abrir Modal de validación
                self._abrir_modal_codigo_email()
                
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", f"No se pudo enviar: {ex}", "error")
            finally:
                self.btn_conf_guardar_email.disabled = False
                self.btn_conf_guardar_email.text = "Enviar código"
                self.btn_conf_guardar_email.update()

        threading.Thread(target=_tarea_envio, daemon=True).start()

    def _abrir_modal_codigo_email(self):
        """Abre el popup para ingresar el código recibido."""
        self.input_codigo_verif = ft.TextField(
            label="Código de 6 dígitos", 
            text_align=ft.TextAlign.CENTER, 
            max_length=6, 
            width=200,
            bgcolor="#2D2D2D",
            border_color="cyan",
            on_change=self._limpiar_error_codigo  # <--- AGREGADO: Limpia error al escribir
        )
        
        # Guardamos el botón en self para poder modificarlo luego (loading)
        self.btn_confirmar_codigo = ft.ElevatedButton(
            "Confirmar", 
            bgcolor="green", 
            color="white", 
            on_click=self._confirmar_cambio_email
        )
        
        self.dlg_validar_email = ft.AlertDialog(
            modal=True,
            title=ft.Text("Verificar Correo"),
            content=ft.Column(
                [
                    ft.Text(f"Se envió un código a:\n{self.email_pendiente_cambio}", size=12, color="white70", text_align="center"),
                    ft.Container(height=10),
                    self.input_codigo_verif
                ],
                height=120,
                width=300,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self.page.close(self.dlg_validar_email)),
                self.btn_confirmar_codigo # <--- Usamos la variable creada arriba
            ],
            actions_alignment=ft.MainAxisAlignment.CENTER
        )
        self.page.open(self.dlg_validar_email)

    def _limpiar_error_codigo(self, e):
        """Limpia el mensaje de error visual cuando el usuario escribe."""
        if self.input_codigo_verif.error_text is not None:
            self.input_codigo_verif.error_text = None
            self.input_codigo_verif.border_color = "cyan"
            self.input_codigo_verif.update()

    def _confirmar_cambio_email(self, e):
        """Verifica el código y actualiza la BD con animación de carga."""
        
        def _tarea_verificacion():
            # 1. Estado de Carga (Animación visual)
            self.btn_confirmar_codigo.disabled = True
            self.btn_confirmar_codigo.text = "Verificando..."
            self.input_codigo_verif.disabled = True # Bloquear input mientras carga
            
            self.btn_confirmar_codigo.update()
            self.input_codigo_verif.update()
            
            # Pequeña pausa artificial para que el usuario alcance a leer "Verificando..."
            # (opcional, pero mejora la UX si la BD es muy rápida)
            time.sleep(0.5) 

            codigo_ingresado = self.input_codigo_verif.value.strip()
            
            if codigo_ingresado == self.codigo_verificacion_temp:
                try:
                    bd = BaseDeDatos()
                    bd.actualizar_email_usuario(self.usuario_actual, self.email_pendiente_cambio)
                    
                    self.page.close(self.dlg_validar_email)
                    GestorMensajes.mostrar(self.page, "Éxito", "Correo electrónico actualizado correctamente.", "exito")
                    
                    # Limpiar campo original
                    self.input_conf_email.value = ""
                    self.input_conf_email.update()
                    
                except Exception as ex:
                    # Error de base de datos
                    self.page.close(self.dlg_validar_email)
                    GestorMensajes.mostrar(self.page, "Error", f"Error en base de datos: {ex}", "error")
            else:
                # Código Incorrecto: Restaurar controles y mostrar error
                self.btn_confirmar_codigo.disabled = False
                self.btn_confirmar_codigo.text = "Confirmar"
                self.input_codigo_verif.disabled = False
                
                self.input_codigo_verif.border_color = "red"
                self.input_codigo_verif.error_text = "Código incorrecto"
                
                self.btn_confirmar_codigo.update()
                self.input_codigo_verif.update()

        # Ejecutar en hilo secundario
        threading.Thread(target=_tarea_verificacion, daemon=True).start()

    def _abrir_selector_torneo(self, e):
        """
        Lógica TOGGLE:
        - Si ya hay un torneo filtrado, se DESAPLICA (vuelve a gris).
        - Si no hay torneo, abre el modal para elegir uno.
        """
        if self.filtro_edicion_id is not None:
            # Desactivar filtro
            self.filtro_edicion_id = None
            self._actualizar_botones_partidos_visual()
            self._actualizar_titulo_partidos()
            self._recargar_datos(actualizar_partidos=True, actualizar_copas=False)
        else:
            # Abrir modal (código original de carga del modal)
            self.lv_torneos = ft.ListView(expand=True, spacing=5, height=200)
            self.lv_anios = ft.ListView(expand=True, spacing=5, height=200)
            self.btn_ver_torneo = ft.ElevatedButton("Ver", icon=ft.icons.VISIBILITY, disabled=True, on_click=self._confirmar_filtro_torneo)
            
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
            self.dlg_modal = ft.AlertDialog(modal=True, title=ft.Text("Filtrar Partidos por Torneo"), content=contenido_modal, actions=[ft.TextButton("Cancelar", on_click=lambda e: self.page.close(self.dlg_modal)), self.btn_ver_torneo], actions_alignment=ft.MainAxisAlignment.END)
            self.page.open(self.dlg_modal)
            threading.Thread(target=_cargar_datos_modal, daemon=True).start()

    def _confirmar_filtro_torneo(self, e):
        """Confirma la selección del torneo y lo aplica (sumándose a otros filtros)."""
        if self.temp_campeonato_sel and self.temp_anio_sel:
            edicion_encontrada = None
            for ed in self.cache_ediciones_modal:
                if ed[1] == self.temp_campeonato_sel and ed[2] == self.temp_anio_sel:
                    edicion_encontrada = ed[0] 
                    break
            
            if edicion_encontrada:
                self.filtro_edicion_id = edicion_encontrada
                # NO reseteamos los otros filtros
                
                self._actualizar_titulo_partidos()
                self._actualizar_botones_partidos_visual()
                self.page.close(self.dlg_modal)
                self._recargar_datos(actualizar_partidos=True, actualizar_copas=False)

    def _abrir_selector_equipo(self, e):
        """
        Lógica TOGGLE:
        - Si ya hay equipo filtrado, se DESAPLICA.
        - Si no, abre modal.
        """
        if self.filtro_rival_id is not None:
            # Desactivar
            self.filtro_rival_id = None
            self.temp_rival_sel_nombre = None # Limpiar nombre para el título
            self._actualizar_botones_partidos_visual()
            self._actualizar_titulo_partidos()
            self._recargar_datos(actualizar_partidos=True, actualizar_copas=False)
        else:
            # Abrir modal
            self.lv_equipos = ft.ListView(expand=True, spacing=5, height=300)
            self.btn_ver_equipo = ft.ElevatedButton("Ver", icon=ft.icons.VISIBILITY, disabled=True, on_click=self._confirmar_filtro_equipo)
            
            def _cargar_rivales_modal():
                try:
                    bd = BaseDeDatos()
                    rivales = bd.obtener_rivales() 
                    self.cache_rivales_modal = rivales 
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

    def _actualizar_botones_pronosticos_visual(self):
        """Actualiza el color de todos los botones de la pestaña Pronósticos según el filtro activo."""
        # Grupo Tiempo (Excluyentes)
        ft_tiempo = self.filtro_pron_tiempo
        self.btn_pron_todos.bgcolor = "blue" if ft_tiempo == 'todos' else "#333333"
        self.btn_pron_por_jugar.bgcolor = "blue" if ft_tiempo == 'futuros' else "#333333"
        self.btn_pron_jugados.bgcolor = "blue" if ft_tiempo == 'jugados' else "#333333"
        
        # Grupo Específicos (Independientes)
        # Se pintan si la variable del filtro NO es None (está activa)
        self.btn_pron_por_torneo.bgcolor = "blue" if self.filtro_pron_torneo else "#333333"
        self.btn_pron_por_equipo.bgcolor = "blue" if self.filtro_pron_equipo else "#333333"
        self.btn_pron_por_usuario.bgcolor = "blue" if self.filtro_pron_usuario else "#333333"
        
        # Forzar actualización individual para asegurar el cambio visual
        self.btn_pron_todos.update()
        self.btn_pron_por_jugar.update()
        self.btn_pron_jugados.update()
        self.btn_pron_por_torneo.update()
        self.btn_pron_por_equipo.update()
        self.btn_pron_por_usuario.update()

    def _actualizar_titulo_partidos(self):
        """Genera el título dinámico combinando todos los filtros activos."""
        partes = []
        
        # 1. Tiempo
        if self.filtro_temporal == 'todos': partes.append("Todos los partidos")
        elif self.filtro_temporal == 'futuros': partes.append("Partidos por jugar")
        elif self.filtro_temporal == 'jugados': partes.append("Partidos jugados")
        
        detalles = []
        # 2. Sin Pronosticar
        if self.filtro_sin_pronosticar:
            detalles.append("sin pronosticar")
            
        # 3. Torneo
        if self.filtro_edicion_id:
            # Como no guardamos el nombre del torneo en la variable de filtro ID, 
            # usamos las variables temporales si están frescas, o simplificamos el título.
            if self.temp_campeonato_sel:
                detalles.append(f"{self.temp_campeonato_sel} {self.temp_anio_sel}")
            else:
                detalles.append("torneo seleccionado")

        # 4. Equipo
        if self.filtro_rival_id:
            if self.temp_rival_sel_nombre:
                detalles.append(f"vs {self.temp_rival_sel_nombre}")
            else:
                detalles.append("vs equipo")

        titulo = partes[0]
        if detalles:
            titulo += " (" + ", ".join(detalles) + ")"
            
        self.txt_titulo_partidos.value = titulo
        self.txt_titulo_partidos.update()

    def _confirmar_filtro_equipo(self, e):
        """Confirma selección equipo."""
        if self.temp_rival_sel_id:
            self.filtro_rival_id = self.temp_rival_sel_id
            
            self._actualizar_titulo_partidos()
            self._actualizar_botones_partidos_visual()
            self.page.close(self.dlg_modal_equipo)
            self._recargar_datos(actualizar_partidos=True, actualizar_copas=False)

    # --- FUNCIONES GRÁFICO DE PUESTOS ---

    def _abrir_selector_grafico_puestos(self, e):
        """Abre el modal para configurar el gráfico de evolución de puestos."""
        self.lv_torneos_graf = ft.ListView(expand=True, spacing=5, height=150)
        self.lv_anios_graf = ft.ListView(expand=True, spacing=5, height=150)
        self.lv_usuarios_graf = ft.ListView(expand=True, spacing=5, height=150)
        
        self.temp_camp_graf = None
        self.temp_anio_graf = None
        self.chk_usuarios_grafico = [] 
        
        self.btn_generar_grafico = ft.ElevatedButton("Generar Gráfico", icon=ft.icons.SHOW_CHART, disabled=True, on_click=self._generar_grafico_puestos)

        def _cargar_datos():
            bd = BaseDeDatos()
            # 1. Torneos y Años
            ediciones = bd.obtener_ediciones()
            self.cache_ediciones_modal = ediciones
            nombres_unicos = sorted(list(set(e[1] for e in ediciones)))
            
            controles_tor = []
            for nombre in nombres_unicos:
                # CORRECCIÓN: Se eliminó density="compact"
                controles_tor.append(ft.ListTile(title=ft.Text(nombre, size=14), data=nombre, on_click=self._sel_torneo_graf_modal, bgcolor="#2D2D2D"))
            self.lv_torneos_graf.controls = controles_tor
            
            # 2. Usuarios
            usuarios = bd.obtener_usuarios()
            controles_usu = []
            for usu in usuarios:
                chk = ft.Checkbox(label=usu, value=False, on_change=self._validar_seleccion_usuarios_grafico)
                self.chk_usuarios_grafico.append(chk)
                controles_usu.append(chk)
            self.lv_usuarios_graf.controls = controles_usu
            
            self.lv_torneos_graf.update()
            self.lv_usuarios_graf.update()

        col_tor = ft.Column(expand=1, controls=[ft.Text("1. Torneo", weight="bold"), ft.Container(content=self.lv_torneos_graf, border=ft.border.all(1, "white24"), border_radius=5)])
        col_anio = ft.Column(expand=1, controls=[ft.Text("2. Año", weight="bold"), ft.Container(content=self.lv_anios_graf, border=ft.border.all(1, "white24"), border_radius=5)])
        col_usu = ft.Column(expand=1, controls=[ft.Text("3. Usuarios (Max 3)", weight="bold"), ft.Container(content=self.lv_usuarios_graf, border=ft.border.all(1, "white24"), border_radius=5)])

        contenido = ft.Container(width=700, height=300, content=ft.Row(controls=[col_tor, col_anio, col_usu], spacing=20))

        self.dlg_grafico = ft.AlertDialog(modal=True, title=ft.Text("Configurar Gráfico de Evolución"), content=contenido, actions=[ft.TextButton("Cancelar", on_click=lambda e: self.page.close(self.dlg_grafico)), self.btn_generar_grafico])
        self.page.open(self.dlg_grafico)
        threading.Thread(target=_cargar_datos, daemon=True).start()

    def _sel_torneo_graf_modal(self, e):
        """Selecciona torneo en el modal de gráfico y carga años."""
        nombre = e.control.data
        self.temp_camp_graf = nombre
        
        # Resaltar
        for c in self.lv_torneos_graf.controls: c.bgcolor = "blue" if c.data == nombre else "#2D2D2D"
        self.lv_torneos_graf.update()
        
        # Filtrar años
        anios = sorted([ed[2] for ed in self.cache_ediciones_modal if ed[1] == nombre], reverse=True)
        ctls = []
        for a in anios:
            # CORRECCIÓN: Se eliminó density="compact"
            ctls.append(ft.ListTile(title=ft.Text(str(a), size=14), data=a, on_click=self._sel_anio_graf_modal, bgcolor="#2D2D2D"))
        self.lv_anios_graf.controls = ctls
        self.lv_anios_graf.update()
        
        self.temp_anio_graf = None
        self._validar_btn_grafico()

    def _sel_anio_graf_modal(self, e):
        self.temp_anio_graf = e.control.data
        for c in self.lv_anios_graf.controls: c.bgcolor = "blue" if c.data == self.temp_anio_graf else "#2D2D2D"
        self.lv_anios_graf.update()
        self._validar_btn_grafico()

    def _validar_seleccion_usuarios_grafico(self, e):
        seleccionados = [c for c in self.chk_usuarios_grafico if c.value]
        if len(seleccionados) > 3:
            e.control.value = False
            e.control.update()
            GestorMensajes.mostrar(self.page, "Límite", "Máximo 3 usuarios.", "info")
        self._validar_btn_grafico()

    def _validar_btn_grafico(self):
        sel_users = [c for c in self.chk_usuarios_grafico if c.value]
        habilitar = self.temp_camp_graf and self.temp_anio_graf and len(sel_users) > 0
        self.btn_generar_grafico.disabled = not habilitar
        self.btn_generar_grafico.update()

    def _generar_grafico_puestos(self, e):
        """Genera y muestra el gráfico de líneas con ejes optimizados y visibles."""
        usuarios_sel = [c.label for c in self.chk_usuarios_grafico if c.value]
        
        edicion_id = None
        for ed in self.cache_ediciones_modal:
            if ed[1] == self.temp_camp_graf and ed[2] == self.temp_anio_graf:
                edicion_id = ed[0]
                break
        
        if not edicion_id: return

        def _tarea():
            bd = BaseDeDatos()
            cant_partidos, total_usuarios, historial = bd.obtener_datos_evolucion_puestos(edicion_id, usuarios_sel)
            
            if cant_partidos == 0:
                GestorMensajes.mostrar(self.page, "Info", "No hay datos de partidos jugados.", "info")
                return

            # 1. Determinar el rango del eje Y
            # Buscamos el peor puesto registrado en este historial para no hacer un gráfico gigante si son pocos
            peor_puesto_registrado = 1
            for puestos in historial.values():
                if puestos:
                    peor_puesto_registrado = max(peor_puesto_registrado, max(puestos))
            
            # Altura = Peor puesto + 1 (para que el puesto más bajo no quede pegado al suelo)
            altura_eje = peor_puesto_registrado + 1
            
            colores = [ft.Colors.CYAN, ft.Colors.AMBER, ft.Colors.PINK, ft.Colors.GREEN]
            data_series = []
            
            # 2. Construir líneas
            for i, user in enumerate(usuarios_sel):
                puestos = historial.get(user, [])
                
                # Punto de inicio (0, 0)
                puntos_grafico = [ft.LineChartDataPoint(0, 0, tooltip="Inicio")]
                
                for idx_partido, puesto in enumerate(puestos):
                    # Fórmula para invertir visualmente: Arriba el 1, Abajo el mayor.
                    valor_y = altura_eje - puesto
                    
                    puntos_grafico.append(
                        ft.LineChartDataPoint(
                            x=idx_partido + 1, 
                            y=valor_y,
                            tooltip=f"{puesto}º" # Tooltip muestra el puesto real
                        )
                    )
                
                data_series.append(
                    ft.LineChartData(
                        data_points=puntos_grafico,
                        stroke_width=4,
                        color=colores[i % len(colores)],
                        curved=False,
                        stroke_cap_round=True,
                        point=True 
                    )
                )

            # 3. Etiquetas Eje Y (TODAS)
            labels_y = [ft.ChartAxisLabel(value=0, label=ft.Text("Inicio", size=10, weight="bold"))]
            
            # Mostramos TODOS los puestos involucrados
            for p in range(1, peor_puesto_registrado + 1):
                val_y = altura_eje - p 
                labels_y.append(
                    ft.ChartAxisLabel(
                        value=val_y, 
                        label=ft.Text(f"{p}º", size=14 if p==1 else 12, weight="bold" if p==1 else "normal")
                    )
                )

            # 4. Intervalo Eje X dinámico (para que no se amontonen si hay muchos)
            intervalo_x = 1
            if cant_partidos > 15: intervalo_x = 2
            if cant_partidos > 30: intervalo_x = 5

            # 5. Configuración del Gráfico
            chart = ft.LineChart(
                data_series=data_series,
                border=ft.border.all(1, ft.Colors.WHITE10),
                # EJE IZQUIERDO
                left_axis=ft.ChartAxis(
                    labels=labels_y,
                    labels_size=50, # Espacio reservado para texto "1º", "10º"
                ),
                # EJE INFERIOR
                bottom_axis=ft.ChartAxis(
                    labels_interval=intervalo_x,
                    title=ft.Text("Partido N°", size=14, italic=True),
                    labels_size=40, # AUMENTADO: Espacio para que no se corten los números ni el título
                ),
                tooltip_bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.BLACK),
                min_y=0,
                max_y=altura_eje + 0.2, # Un poquito de aire arriba
                min_x=0,
                max_x=cant_partidos, 
                horizontal_grid_lines=ft.ChartGridLines(interval=1, color=ft.Colors.WHITE10, width=1),
                expand=True,
            )
            
            # Leyenda
            items_leyenda = []
            for i, user in enumerate(usuarios_sel):
                items_leyenda.append(
                    ft.Row([
                        ft.Container(width=15, height=15, bgcolor=colores[i % 3], border_radius=3),
                        ft.Text(user, weight="bold", size=16)
                    ], spacing=5)
                )

            # --- PANTALLA COMPLETA ---
            ancho = self.page.width - 50
            alto = self.page.height - 50

            contenido_final = ft.Container(
                width=ancho, height=alto,
                padding=20, bgcolor="#1E1E1E",
                content=ft.Column([
                    ft.Row(
                        controls=[
                            ft.Text(f"Evolución: {self.temp_camp_graf} {self.temp_anio_graf}", size=24, weight="bold"),
                            ft.IconButton(icon=ft.icons.CLOSE, on_click=lambda e: self.page.close(self.dlg_grafico_full))
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    ),
                    # Agregamos padding al contenedor del gráfico para evitar cortes en bordes
                    ft.Container(content=chart, expand=True, padding=ft.padding.all(20)),
                    ft.Row(items_leyenda, alignment="center")
                ])
            )
            
            self.page.close(self.dlg_grafico)
            
            self.dlg_grafico_full = ft.AlertDialog(content=contenido_final, modal=True, inset_padding=10)
            self.page.open(self.dlg_grafico_full)

        threading.Thread(target=_tarea, daemon=True).start()

    def _abrir_selector_torneo_ranking(self, e):
        # --- 1. LÓGICA DE TOGGLE ---
        # Si ya hay un torneo filtrado, lo quitamos
        if self.filtro_ranking_edicion_id is not None:
            self.filtro_ranking_edicion_id = None
            self.filtro_ranking_nombre = None
            
            # Restaurar títulos
            self.txt_titulo_ranking.value = "Tabla de posiciones histórica"
            # OJO: No tocamos título de copas ni tabla de copas
            self.txt_titulo_ranking.update()
            
            # Apagar botón visualmente
            self.btn_ranking_torneo.bgcolor = "#333333"
            self.btn_ranking_torneo.update()
            
            # Recargar datos globales SIN TOCAR COPAS
            self._recargar_datos(actualizar_ranking=True, actualizar_copas=False)
            return

        # --- 2. SI NO ESTÁ ACTIVO, ABRIMOS EL MODAL ---
        self.lv_torneos = ft.ListView(expand=True, spacing=5, height=200)
        self.lv_anios = ft.ListView(expand=True, spacing=5, height=200)
        
        self.btn_ver_torneo = ft.ElevatedButton("Ver", icon=ft.icons.VISIBILITY, disabled=True, on_click=self._confirmar_filtro_torneo_ranking)
        
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

        self.dlg_modal = ft.AlertDialog(modal=True, title=ft.Text("Filtrar Ranking por Torneo"), content=contenido_modal, actions=[ft.TextButton("Cancelar", on_click=lambda e: self.page.close(self.dlg_modal)), self.btn_ver_torneo], actions_alignment=ft.MainAxisAlignment.END)
        self.page.open(self.dlg_modal)
        threading.Thread(target=_cargar_datos_modal, daemon=True).start()

    def _abrir_selector_anio_ranking(self, e):
        # --- 1. LÓGICA DE TOGGLE ---
        # Si ya hay un año filtrado, lo quitamos
        if self.filtro_ranking_anio is not None:
            self.filtro_ranking_anio = None
            
            # Restaurar títulos
            self.txt_titulo_ranking.value = "Tabla de posiciones histórica"
            self.txt_titulo_copas.value = "Torneos ganados en la historia"
            self.txt_titulo_ranking.update()
            self.txt_titulo_copas.update()
            
            # Apagar botón visualmente
            self.btn_ranking_anio.bgcolor = "#333333"
            self.btn_ranking_anio.update()
            
            # Recargar datos globales
            self._recargar_datos(actualizar_ranking=True)
            return

        # --- 2. SI NO ESTÁ ACTIVO, ABRIMOS EL MODAL ---
        self.lv_anios_ranking = ft.ListView(expand=True, spacing=5, height=300)
        self.btn_ver_anio = ft.ElevatedButton("Ver", icon=ft.icons.VISIBILITY, disabled=True, on_click=self._confirmar_filtro_anio_ranking)
        
        def _cargar_anios():
            try:
                bd = BaseDeDatos()
                anios = bd.obtener_anios()
                controles = []
                for id_anio, numero in anios:
                    controles.append(
                        ft.ListTile(
                            title=ft.Text(str(numero), size=14),
                            data=numero, 
                            on_click=self._seleccionar_anio_ranking_modal,
                            bgcolor="#2D2D2D",
                            shape=ft.RoundedRectangleBorder(radius=5)
                        )
                    )
                self.lv_anios_ranking.controls = controles
                self.lv_anios_ranking.update()
            except Exception as ex:
                print(f"Error cargando modal años: {ex}")

        contenido_modal = ft.Container(
            width=300,
            height=300,
            content=ft.Column(
                controls=[
                    ft.Text("Seleccione un Año", weight=ft.FontWeight.BOLD),
                    ft.Container(
                        content=self.lv_anios_ranking,
                        border=ft.border.all(1, "white24"),
                        border_radius=5,
                        padding=5,
                        expand=True
                    )
                ]
            )
        )

        self.dlg_modal_anio = ft.AlertDialog(
            modal=True,
            title=ft.Text("Filtrar por Año"),
            content=contenido_modal,
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self.page.close(self.dlg_modal_anio)),
                self.btn_ver_anio
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self.page.open(self.dlg_modal_anio)
        threading.Thread(target=_cargar_anios, daemon=True).start()

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

    def _confirmar_filtro_torneo_ranking(self, e):
        """Busca el ID de la edición seleccionada y aplica el filtro al ranking"""
        if self.temp_campeonato_sel and self.temp_anio_sel:
            edicion_encontrada = None
            for ed in self.cache_ediciones_modal:
                if ed[1] == self.temp_campeonato_sel and ed[2] == self.temp_anio_sel:
                    edicion_encontrada = ed[0] 
                    break
            
            if edicion_encontrada:
                # 1. Establecer filtro Torneo
                self.filtro_ranking_edicion_id = edicion_encontrada
                self.filtro_ranking_nombre = f"{self.temp_campeonato_sel} {self.temp_anio_sel}"
                
                # 2. BORRAR filtro Año (Exclusividad)
                self.filtro_ranking_anio = None
                
                # 3. Actualizar Título
                self.txt_titulo_ranking.value = f"Tabla de posiciones {self.filtro_ranking_nombre}"
                self.txt_titulo_ranking.update()
                
                # 4. Actualizar Botones (Uno azul, el otro negro)
                self.btn_ranking_torneo.bgcolor = "blue"
                self.btn_ranking_anio.bgcolor = "#333333" # Apagar el otro
                
                self.btn_ranking_torneo.update()
                self.btn_ranking_anio.update()
                
                self.page.close(self.dlg_modal)
                # IMPORTANTE: No actualizar Copas
                self._recargar_datos(actualizar_ranking=True, actualizar_copas=False)

    def _confirmar_filtro_anio_ranking(self, e):
        """Confirma el filtro por año y borra el de torneo"""
        if self.temp_anio_sel:
            # 1. Establecer filtro Año
            self.filtro_ranking_anio = self.temp_anio_sel
            
            # 2. BORRAR filtro Torneo (Exclusividad)
            self.filtro_ranking_edicion_id = None 
            self.filtro_ranking_nombre = None
            
            # 3. Actualizar Títulos
            self.txt_titulo_ranking.value = f"Tabla de posiciones {self.filtro_ranking_anio}"
            self.txt_titulo_copas.value = f"Torneos ganados {self.filtro_ranking_anio}" # Nuevo título
            self.txt_titulo_ranking.update()
            self.txt_titulo_copas.update()
            
            # 4. Actualizar Botones (Uno azul, el otro negro)
            self.btn_ranking_anio.bgcolor = "blue"
            self.btn_ranking_torneo.bgcolor = "#333333" # Apagar el otro
            
            self.btn_ranking_anio.update()
            self.btn_ranking_torneo.update()
            
            self.page.close(self.dlg_modal_anio)
            self._recargar_datos(actualizar_ranking=True)

    def _bloquear_botones_filtros(self, bloquear):
        """Habilita o deshabilita los botones de filtro de partidos."""
        self.btn_todos.disabled = bloquear
        self.btn_jugados.disabled = bloquear
        self.btn_por_jugar.disabled = bloquear
        self.btn_por_torneo.disabled = bloquear
        self.btn_sin_pronosticar.disabled = bloquear
        self.btn_por_equipo.disabled = bloquear

    def _cerrar_sesion(self, e):
        self.page.controls.clear()
        self.page.bgcolor = "#121212" 
        self._construir_interfaz_login()
        self.page.update()

if __name__ == "__main__":
    def main(page: ft.Page):
        app = SistemaIndependiente(page)
    
    ft.app(target=main)