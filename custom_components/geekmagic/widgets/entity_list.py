"""Entity list widget for GeekMagic displays."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from ..const import PLACEHOLDER_NAME, PLACEHOLDER_VALUE
from .attribute_list import LabelValueRow
from .base import Widget, WidgetConfig
from .components import (
    THEME_TEXT_PRIMARY,
    THEME_TEXT_SECONDARY,
    Column,
    Component,
    Icon,
    Row,
    Text,
)
from .entity import _get_entity_icon
from .helpers import translate_binary_state

if TYPE_CHECKING:
    from ..render_context import RenderContext
    from .state import EntityState, WidgetState


@dataclass
class EntityListDisplay(Component):
    """Entity list display component."""

    items: list[tuple[str, str, str | None]] = field(default_factory=list)  # (label, value, icon)
    title: str | None = None

    def measure(self, ctx: RenderContext, max_width: int, max_height: int) -> tuple[int, int]:
        return (max_width, max_height)

    def render(self, ctx: RenderContext, x: int, y: int, width: int, height: int) -> None:
        """Render list with optional title and label/value rows."""
        padding = max(2, int(min(width, height) * 0.05))
        icon_size = max(10, min(16, int(min(width, height) * 0.12)))
        row_gap = max(4, int(min(width, height) * 0.03))
        list_gap = max(2, int(min(width, height) * 0.02))
        show_title = bool(self.title) and width >= 100
        title_text = self.title.upper() if self.title else ""
        rows: list[Component] = []

        if show_title:
            rows.append(
                Text(
                    text=title_text,
                    font="tertiary",
                    color=THEME_TEXT_SECONDARY,
                    align="start",
                    truncate=True,
                )
            )

        for label, value, icon in self.items:
            row_children: list[Component] = []
            if icon:
                row_children.append(Icon(name=icon, size=icon_size, color=THEME_TEXT_SECONDARY))
            row_children.append(
                LabelValueRow(
                    label=label,
                    value=value,
                    label_color=THEME_TEXT_SECONDARY,
                    value_color=THEME_TEXT_PRIMARY,
                    gap=row_gap,
                )
            )
            rows.append(Row(children=row_children, gap=row_gap, align="center", justify="start"))

        if not rows:
            rows.append(Text(text=PLACEHOLDER_VALUE, font="secondary", color=THEME_TEXT_PRIMARY))

        Column(
            children=rows,
            gap=list_gap + 1 if show_title else list_gap,
            padding=padding,
            align="stretch",
            justify="start",
        ).render(ctx, x, y, width, height)


class EntityListWidget(Widget):
    """Widget that displays a list of Home Assistant entity states."""

    WIDGET_TYPE: ClassVar[str] = "entity_list"
    SCHEMA: ClassVar[dict[str, Any]] = {
        "name": "Entity List",
        "needs_entity": False,
        "options": [
            {"key": "title", "type": "text", "label": "Title"},
            {"key": "entities", "type": "status_entities", "label": "Entities"},
            {"key": "show_unit", "type": "boolean", "label": "Show Unit", "default": True},
            {"key": "show_icon", "type": "boolean", "label": "Show Icon", "default": True},
            {
                "key": "precision",
                "type": "number",
                "label": "Decimal Places",
                "min": 0,
                "max": 5,
            },
            {"key": "attribute", "type": "text", "label": "Attribute"},
        ],
    }

    def __init__(self, config: WidgetConfig) -> None:
        """Initialize the entity list widget."""
        super().__init__(config)
        # Uses the frontend "status_entities" array editor shape:
        # [{entity_id, label?, icon?}] (also accepts tuple/string for compatibility).
        self.entities = config.options.get("entities", [])
        self.title = config.options.get("title")
        self.show_unit = config.options.get("show_unit", True)
        self.show_icon = config.options.get("show_icon", True)
        self.precision = config.options.get("precision")
        self.attribute = config.options.get("attribute")

    def get_entities(self) -> list[str]:
        """Return list of entity IDs this widget depends on."""
        entity_ids: list[str] = []
        for entry in self.entities:
            if isinstance(entry, dict):
                entity_id = entry.get("entity_id")
                if entity_id:
                    entity_ids.append(entity_id)
            elif isinstance(entry, (list, tuple)) and entry:
                entity_ids.append(str(entry[0]))
            elif isinstance(entry, str):
                entity_ids.append(entry)
        return entity_ids

    def render(self, ctx: RenderContext, state: WidgetState) -> Component:
        """Render the entity list widget."""
        items: list[tuple[str, str, str | None]] = []
        for entry in self.entities:
            entity_id, label_override, icon_override = self._parse_entry(entry)
            if not entity_id:
                continue

            entity = state.get_entity(entity_id)
            label = label_override or self.label_for(entity, fallback=entity_id)
            value_text = self._value_text(entity)
            icon = self._icon_for(entity, icon_override)

            items.append((label, value_text, icon))

        title = self.title
        if not title and not self.entities:
            title = PLACEHOLDER_NAME

        return EntityListDisplay(items=items, title=title)

    def _parse_entry(self, entry: Any) -> tuple[str | None, str | None, str | None]:
        """Parse an entity list entry from dict/tuple/string formats."""
        if isinstance(entry, dict):
            entity_id = entry.get("entity_id")
            label = entry.get("label")
            icon = entry.get("icon")
            if isinstance(icon, str) and icon.startswith("mdi:"):
                icon = icon.removeprefix("mdi:")
            return entity_id, label, icon
        if isinstance(entry, (list, tuple)):
            entity_id = str(entry[0]) if entry else None
            label = str(entry[1]) if len(entry) > 1 else None
            icon = str(entry[2]) if len(entry) > 2 else None
            if icon and icon.startswith("mdi:"):
                icon = icon.removeprefix("mdi:")
            return entity_id, label, icon
        if isinstance(entry, str):
            return entry, None, None
        return None, None, None

    def _value_text(self, entity: EntityState | None) -> str:
        """Format displayed value (optionally from configured attribute)."""
        if entity is None:
            return PLACEHOLDER_VALUE

        if self.attribute:
            raw_value = entity.get(self.attribute)
            value = str(raw_value) if raw_value is not None else PLACEHOLDER_VALUE
        else:
            value = entity.state
            if entity.entity_id.startswith("binary_sensor."):
                value = translate_binary_state(value, entity.device_class)
            elif isinstance(value, str) and value.isalpha() and len(value) <= 16:
                value = value.title()

        if self.precision is not None:
            with suppress(ValueError, TypeError):
                value = f"{float(value):.{self.precision}f}"

        unit = entity.unit if self.show_unit else ""
        return f"{value}{unit}" if unit else value

    def _icon_for(self, entity: EntityState | None, icon_override: str | None) -> str | None:
        """Resolve icon based on per-entity override and widget options."""
        if icon_override:
            return icon_override
        if not self.show_icon:
            return None
        return _get_entity_icon(entity)
