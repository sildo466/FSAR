"""FSAR tool system."""

from src.tools.registry import Tool, ToolRegistry
from src.tools.builtin import (
    RunCommandTool,
    FileOpsTool,
    EditTool,
    ProcessTool,
    WebSearchTool,
    WebFetchTool,
    AppControlTool,
    ImageAnalyzeTool,
    PdfAnalyzeTool,
    ExperienceViewTool,
    LearnExperienceTool,
    ListExperiencesTool,
    RememberFactTool,
)


def create_default_registry() -> ToolRegistry:
    """Create a ToolRegistry with all built-in tools registered."""
    registry = ToolRegistry()
    registry.register(RunCommandTool())
    registry.register(FileOpsTool())
    registry.register(EditTool())
    registry.register(ProcessTool())
    registry.register(WebSearchTool())
    registry.register(WebFetchTool())
    registry.register(AppControlTool())
    registry.register(ImageAnalyzeTool())
    registry.register(PdfAnalyzeTool())
    registry.register(ExperienceViewTool())
    registry.register(LearnExperienceTool())
    registry.register(ListExperiencesTool())
    registry.register(RememberFactTool())
    return registry


__all__ = [
    "Tool",
    "ToolRegistry",
    "create_default_registry",
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
