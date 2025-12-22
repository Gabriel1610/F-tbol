import flet as ft

class Estilos:
    """Colores y configuraciones del Club Atlético Independiente"""
    
    # Paleta de Colores
    COLOR_ROJO_CAI = "#E30613" 
    COLOR_BLANCO = "#FFFFFF"
    COLOR_NEGRO = "#000000"
    
    # Tema de la Tarjeta
    COLOR_FONDO_CARD = COLOR_ROJO_CAI
    COLOR_TEXTO = COLOR_BLANCO
    COLOR_BORDE = COLOR_BLANCO
    
    # Configuración centralizada de Inputs
    INPUT_CONFIG = {
        "label_style": ft.TextStyle(color=COLOR_BLANCO), 
        "border_color": COLOR_BLANCO,
        "cursor_color": COLOR_BLANCO,
        "text_style": ft.TextStyle(color=COLOR_BLANCO),
        "focused_border_color": COLOR_NEGRO, 
        "border_radius": 10,
        "text_size": 14,
        "content_padding": 15
    }