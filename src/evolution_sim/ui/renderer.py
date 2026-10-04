"""Visualize simulation state without participating in outcomes."""

from __future__ import annotations

import math

import pygame

from evolution_sim.config import SimulationConfig, WorldConfig
from evolution_sim.model.genome import Trait
from evolution_sim.simulation.engine import SimulationEngine
from evolution_sim.simulation.snapshots import WorldSnapshot
from evolution_sim.ui import theme
from evolution_sim.ui.charts import render_metric_traces
from evolution_sim.ui.layout import Layout
from evolution_sim.ui.widgets import metric, panel, segmented_tabs, text


def world_to_screen(
    position: tuple[float, float],
    rect: pygame.Rect,
    config: WorldConfig,
) -> tuple[int, int]:
    return (
        round(rect.left + position[0] / config.width * rect.width),
        round(rect.top + position[1] / config.height * rect.height),
    )


def hit_test_creature(
    snapshot: WorldSnapshot,
    point: tuple[int, int],
    rect: pygame.Rect,
    config: SimulationConfig,
) -> int | None:
    candidates: list[tuple[float, int]] = []
    for creature in snapshot.creatures:
        center = world_to_screen(creature.position, rect, config.world)
        radius = max(7.0, creature.genome[0] * 1.25)
        squared = (point[0] - center[0]) ** 2 + (point[1] - center[1]) ** 2
        if squared <= radius * radius:
            candidates.append((squared, creature.id))
    return min(candidates)[1] if candidates else None


class LaboratoryRenderer:
    def __init__(self) -> None:
        self.fonts = theme.Fonts.load()

    def render(
        self,
        surface: pygame.Surface,
        engine: SimulationEngine,
        layout: Layout,
        *,
        selected_id: int | None,
        active_tab: str,
        paused: bool,
        speed_steps: int,
        show_trails: bool,
        show_perception: bool,
        show_help: bool,
        message: str,
    ) -> None:
        surface.fill(theme.MIDNIGHT)
        self._top_bar(surface, engine, layout, paused, speed_steps)
        self._world(
            surface,
            engine,
            layout.world,
            selected_id,
            show_trails,
            show_perception,
        )
        self._sidebar(surface, engine, layout.sidebar, selected_id, active_tab, message)
        panel(surface, layout.chart_strip)
        render_metric_traces(surface, self.fonts, layout.chart_strip, engine.metrics.samples)
        if show_help:
            self._help(surface, layout.window)

    def _top_bar(
        self,
        surface: pygame.Surface,
        engine: SimulationEngine,
        layout: Layout,
        paused: bool,
        speed_steps: int,
    ) -> None:
        panel(surface, layout.top_bar)
        text(
            surface,
            "VIKASA / OBSERVATORY",
            self.fonts.display,
            theme.INK,
            (layout.top_bar.left + 18, layout.top_bar.top + 11),
        )
        text(
            surface,
            "selection made visible",
            self.fonts.tiny,
            theme.MUTED,
            (layout.top_bar.left + 20, layout.top_bar.top + 42),
        )
        start = layout.top_bar.left + 390
        metrics = [
            ("tick", f"{engine.tick:,}", theme.INK),
            ("population", f"{len(engine.creatures):,}", theme.ION),
            ("food", f"{len(engine.resources):,}", theme.FOOD),
            ("births", f"{engine.total_births:,}", theme.GOOD),
            ("deaths", f"{engine.total_deaths:,}", theme.PRESSURE),
        ]
        for index, (label, value, color) in enumerate(metrics):
            metric(
                surface,
                self.fonts,
                (start + index * 112, layout.top_bar.top + 10),
                label,
                value,
                color,
            )
        status_color = theme.PRESSURE if paused else theme.ION
        status = "paused" if paused else f"live · {speed_steps} tick/frame"
        text(
            surface,
            status,
            self.fonts.small,
            status_color,
            (layout.top_bar.right - 18, layout.top_bar.centery),
            anchor="midright",
        )

    def _world(
        self,
        surface: pygame.Surface,
        engine: SimulationEngine,
        rect: pygame.Rect,
        selected_id: int | None,
        show_trails: bool,
        show_perception: bool,
    ) -> None:
        panel(surface, rect)
        viewport = rect.inflate(-2, -2)
        previous_clip = surface.get_clip()
        surface.set_clip(viewport)
        for x in range(viewport.left + 32, viewport.right, 64):
            pygame.draw.line(
                surface, pygame.Color(19, 47, 61), (x, viewport.top), (x, viewport.bottom), 1
            )
        for y in range(viewport.top + 32, viewport.bottom, 64):
            pygame.draw.line(
                surface, pygame.Color(19, 47, 61), (viewport.left, y), (viewport.right, y), 1
            )

        snapshot = engine.snapshot()
        for resource in snapshot.resources:
            center = world_to_screen(resource.position, viewport, engine.config.world)
            pygame.draw.circle(surface, pygame.Color(245, 198, 93, 35), center, 7)
            points = [
                (center[0], center[1] - 3),
                (center[0] + 3, center[1]),
                (center[0], center[1] + 3),
                (center[0] - 3, center[1]),
            ]
            pygame.draw.polygon(surface, theme.FOOD, points)

        for creature in snapshot.creatures:
            live = engine.creatures[creature.id]
            center = world_to_screen(creature.position, viewport, engine.config.world)
            size = creature.genome[0]
            speed = creature.genome[1]
            speed_bounds = engine.config.genome.traits["speed"]
            hue = (speed - speed_bounds.minimum) / (speed_bounds.maximum - speed_bounds.minimum)
            color = theme.mix(theme.ION, theme.MUTATION, hue)
            radius = max(4, round(size * 1.12))
            if show_trails and len(live.trail) > 1:
                points = [
                    world_to_screen(point, viewport, engine.config.world) for point in live.trail
                ]
                pygame.draw.lines(surface, theme.mix(theme.TISSUE, color, 0.48), False, points, 1)
            if show_perception and creature.id == selected_id:
                perception = creature.genome[2]
                screen_radius = round(perception / engine.config.world.width * viewport.width)
                pygame.draw.circle(surface, theme.ION_SOFT, center, screen_radius, 1)
            pygame.draw.circle(surface, theme.mix(theme.TISSUE, color, 0.22), center, radius + 4)
            pygame.draw.circle(surface, color, center, radius)
            energy_ratio = max(0.0, min(1.0, creature.energy / engine.config.energy.maximum))
            pygame.draw.circle(surface, theme.MIDNIGHT, center, max(1, radius - 3))
            pygame.draw.circle(
                surface, theme.mix(theme.PRESSURE, color, energy_ratio), center, max(1, radius - 4)
            )
            heading = math.atan2(creature.velocity[1], creature.velocity[0])
            nose = (
                round(center[0] + math.cos(heading) * (radius + 3)),
                round(center[1] + math.sin(heading) * (radius + 3)),
            )
            pygame.draw.line(surface, theme.INK, center, nose, 1)
            if creature.id == selected_id:
                pygame.draw.circle(surface, theme.INK, center, radius + 7, 2)

        if engine.extinct:
            text(
                surface,
                "Population extinct",
                self.fonts.title,
                theme.PRESSURE,
                viewport.center,
                anchor="center",
            )
            text(
                surface,
                "Export the run or restart with R",
                self.fonts.small,
                theme.MUTED,
                (viewport.centerx, viewport.centery + 28),
                anchor="center",
            )
        surface.set_clip(previous_clip)

    def _sidebar(
        self,
        surface: pygame.Surface,
        engine: SimulationEngine,
        rect: pygame.Rect,
        selected_id: int | None,
        active_tab: str,
        message: str,
    ) -> None:
        panel(surface, rect)
        inner = rect.inflate(-18, -18)
        text(surface, "Vikasa Lab", self.fonts.title, theme.INK, inner.topleft)
        tabs_rect = pygame.Rect(inner.left, inner.top + 32, inner.width, 32)
        segmented_tabs(
            surface, self.fonts, tabs_rect, ("Controls", "Inspector", "Events"), active_tab
        )
        y = tabs_rect.bottom + 18
        if active_tab == "Controls":
            lines = [
                ("Space", "Pause / resume"),
                ("1-5", "Simulation speed"),
                ("R", "Restart same seed"),
                ("P", "Perception overlay"),
                ("T", "Movement trails"),
                ("Ctrl+S", "Save checkpoint"),
                ("Ctrl+O", "Load checkpoint"),
                ("E", "Export experiment"),
                ("?", "Open help"),
            ]
            for key, description in lines:
                text(surface, key, self.fonts.small, theme.ION, (inner.left, y))
                text(surface, description, self.fonts.small, theme.MUTED, (inner.left + 72, y))
                y += 29
        elif active_tab == "Inspector":
            creature = engine.creatures.get(selected_id) if selected_id is not None else None
            if creature is None:
                text(
                    surface,
                    "Select an organism in the world",
                    self.fonts.small,
                    theme.MUTED,
                    (inner.left, y),
                )
            else:
                text(
                    surface, f"Organism {creature.id}", self.fonts.title, theme.ION, (inner.left, y)
                )
                y += 34
                pairs = [
                    ("age", f"{creature.age:,} ticks"),
                    ("energy", f"{creature.energy:.1f}"),
                    (
                        "parents",
                        "founder"
                        if creature.parents is None
                        else f"{creature.parents[0]} + {creature.parents[1]}",
                    ),
                    ("offspring", str(creature.offspring_count)),
                    ("food acquired", f"{creature.food_acquired:.1f}"),
                ]
                for label, value in pairs:
                    text(surface, label, self.fonts.tiny, theme.MUTED, (inner.left, y))
                    text(
                        surface,
                        value,
                        self.fonts.small,
                        theme.INK,
                        (inner.right, y),
                        anchor="topright",
                    )
                    y += 24
                y += 8
                for trait in Trait:
                    value = creature.genome[trait]
                    bounds = engine.config.genome.traits[trait.value]
                    ratio = (value - bounds.minimum) / (bounds.maximum - bounds.minimum)
                    text(
                        surface,
                        trait.value.replace("_", " "),
                        self.fonts.tiny,
                        theme.MUTED,
                        (inner.left, y),
                    )
                    bar = pygame.Rect(inner.left, y + 17, inner.width, 5)
                    pygame.draw.rect(surface, theme.HAIRLINE, bar, border_radius=3)
                    fill = bar.copy()
                    fill.width = max(2, round(bar.width * ratio))
                    pygame.draw.rect(
                        surface, theme.mix(theme.ION, theme.MUTATION, ratio), fill, border_radius=3
                    )
                    y += 38
        else:
            active = [event for event in engine.environment.events if event.active_at(engine.tick)]
            text(surface, "Environmental pressure", self.fonts.small, theme.INK, (inner.left, y))
            y += 28
            if not engine.environment.events:
                text(surface, "No events scheduled", self.fonts.small, theme.MUTED, (inner.left, y))
            for event in engine.environment.events:
                is_active = event in active
                color = theme.PRESSURE if is_active else theme.MUTED
                text(
                    surface,
                    event.label or event.kind.title(),
                    self.fonts.small,
                    color,
                    (inner.left, y),
                )
                text(
                    surface,
                    f"{event.start_tick:,}-{event.end_tick:,}",
                    self.fonts.tiny,
                    theme.MUTED,
                    (inner.right, y + 2),
                    anchor="topright",
                )
                y += 28
        if message:
            message_rect = pygame.Rect(inner.left, inner.bottom - 52, inner.width, 42)
            pygame.draw.rect(surface, theme.TISSUE_RAISED, message_rect, border_radius=7)
            text(surface, message, self.fonts.tiny, theme.INK, message_rect.center, anchor="center")

    def _help(self, surface: pygame.Surface, window: pygame.Rect) -> None:
        overlay = pygame.Surface(window.size, pygame.SRCALPHA)
        overlay.fill((2, 8, 14, 220))
        surface.blit(overlay, window.topleft)
        box = pygame.Rect(0, 0, min(680, window.width - 80), 410)
        box.center = window.center
        panel(surface, box, raised=True)
        text(
            surface,
            "Read the living system",
            self.fonts.display,
            theme.INK,
            (box.left + 30, box.top + 26),
        )
        lines = [
            "Organism size controls the glyph and raises movement cost.",
            "Hue shifts from cyan to violet as maximum speed rises.",
            "The inner disc moves from coral to cyan with available energy.",
            "Gold diamonds are food. A faint ring shows selected perception.",
            "The lower trace compares population, food, and genetic diversity.",
            "Selection emerges from food, energy, reproduction, and death—never a fixed score.",
        ]
        y = box.top + 92
        for line in lines:
            text(surface, line, self.fonts.body, theme.MUTED, (box.left + 32, y))
            y += 43
        text(
            surface,
            "Press ? or Escape to close",
            self.fonts.small,
            theme.ION,
            (box.centerx, box.bottom - 34),
            anchor="center",
        )
