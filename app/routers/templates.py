from fastapi import APIRouter
from app.schemas.template import TemplateConfig

router = APIRouter(
    prefix="/api/v1/templates",
    tags=["Templates"]
)

templates_db = [
    TemplateConfig(
        id="tpl-001",
        nombre="Revisor de documentos",
        descripcion="Analiza documentos y detecta puntos importantes.",
        caso_uso="Revisión de contratos, informes o documentos legales.",
        tiempo_estimado="2 minutos",
        categoria="análisis",
        favorito=True
    ),
    TemplateConfig(
        id="tpl-002",
        nombre="Extractor de datos",
        descripcion="Extrae información estructurada desde textos o archivos.",
        caso_uso="Extracción de fechas, nombres, montos o datos clave.",
        tiempo_estimado="3 minutos",
        categoria="automatización",
        favorito=False
    ),
    TemplateConfig(
        id="tpl-003",
        nombre="Generador de resúmenes",
        descripcion="Resume contenido largo en ideas claras y breves.",
        caso_uso="Resumen de reportes, artículos o documentos internos.",
        tiempo_estimado="2 minutos",
        categoria="síntesis",
        favorito=False
    ),
    TemplateConfig(
        id="tpl-004",
        nombre="Consolidador multi-fuente",
        descripcion="Une información de varias fuentes en una sola respuesta.",
        caso_uso="Consolidación de datos desde documentos, APIs o reportes.",
        tiempo_estimado="4 minutos",
        categoria="análisis",
        favorito=False
    ),
    TemplateConfig(
        id="tpl-005",
        nombre="Asistente de decisiones",
        descripcion="Ayuda a comparar opciones y recomendar una decisión.",
        caso_uso="Evaluación de alternativas de negocio o procesos internos.",
        tiempo_estimado="3 minutos",
        categoria="automatización",
        favorito=True
    ),
]


@router.get("/")
def list_templates():
    return {
        "templates": templates_db
    }