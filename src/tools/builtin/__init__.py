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
]

# Note: update_emotion is intentionally NOT re-exported here. Re-exporting the
# function with the same name as the module replaces sys.modules[...update_emotion]
# with the function, breaking tests that import the module.
# from src.tools.builtin.update_emotion import update_emotion
