"""FSAR built-in tools."""

from src.tools.builtin.run_command import RunCommandTool
from src.tools.builtin.file_ops import FileOpsTool
from src.tools.builtin.edit import EditTool
from src.tools.builtin.process import ProcessTool
from src.tools.builtin.web_tools import WebSearchTool, WebFetchTool
from src.tools.builtin.app_control import AppControlTool
from src.tools.builtin.image_analyze import ImageAnalyzeTool
from src.tools.builtin.pdf_analyze import PdfAnalyzeTool
from src.tools.builtin.experience_tools import (
    ExperienceViewTool, LearnExperienceTool, ListExperiencesTool, RememberFactTool,
)
from src.tools.builtin.update_emotion import UpdateEmotionTool

__all__ = [
    "RunCommandTool",
    "FileOpsTool",
    "EditTool",
    "ProcessTool",
    "WebSearchTool",
    "WebFetchTool",
    "AppControlTool",
    "ImageAnalyzeTool",
    "PdfAnalyzeTool",
    "ExperienceViewTool",
    "LearnExperienceTool",
    "ListExperiencesTool",
    "RememberFactTool",
    "UpdateEmotionTool",
]

# Note: the `update_emotion` FUNCTION is intentionally NOT re-exported here.
# Re-exporting a function with the same name as its module replaces
# sys.modules[...update_emotion] with the function, breaking tests that
# import the module. The Tool wrapper class is exported instead — it
# delegates to the function internally.
