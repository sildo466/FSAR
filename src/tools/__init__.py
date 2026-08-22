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
    UpdateEmotionTool,
    RouterTool,
    SkillRunTool,
    SkillReviewTool,
    SkillListTool,
    CuScreenshotTool,
    CuScreenSizeTool,
    CuActiveWindowTool,
    CuClickTool,
    CuDoubleClickTool,
    CuScrollTool,
    CuTypeTool,
    CuKeypressTool,
)
from src.utils.fsar_config import FsarConfig


def create_default_registry(config: FsarConfig | None = None) -> ToolRegistry:
    """Create a ToolRegistry with all built-in tools registered."""
    registry = ToolRegistry()
    config = config or FsarConfig()
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
    registry.register(UpdateEmotionTool())
    registry.register(RouterTool())
    registry.register(SkillRunTool(config))
    registry.register(SkillReviewTool(config))
    registry.register(SkillListTool(config))
    registry.register(CuScreenshotTool())
    registry.register(CuScreenSizeTool())
    registry.register(CuActiveWindowTool())
    registry.register(CuClickTool())
    registry.register(CuDoubleClickTool())
    registry.register(CuScrollTool())
    registry.register(CuTypeTool())
    registry.register(CuKeypressTool())
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
    "UpdateEmotionTool",
    "RouterTool",
    "SkillRunTool",
    "SkillReviewTool",
    "SkillListTool",
    "CuScreenshotTool",
    "CuScreenSizeTool",
    "CuActiveWindowTool",
    "CuClickTool",
    "CuDoubleClickTool",
    "CuScrollTool",
    "CuTypeTool",
    "CuKeypressTool",
]
