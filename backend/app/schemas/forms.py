from pydantic import BaseModel, Field


class LogoPosition(BaseModel):
    """Normalized position in the first/template page (0.0 to 1.0)."""

    x: float = Field(default=0.82, ge=0.0, le=1.0)
    y: float = Field(default=0.04, ge=0.0, le=1.0)


class LogoPlacement(LogoPosition):
    pass


class FormProcessRequest(BaseModel):
    template_names: list[str]
    position: LogoPosition = Field(default_factory=LogoPosition)
    logo_placements: list[LogoPlacement] = Field(default_factory=list)
    is_watermark: bool = False
    password: str | None = None
