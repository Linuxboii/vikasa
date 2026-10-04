"""Pygame event loop and user commands."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pygame

from evolution_sim.config import SimulationConfig
from evolution_sim.experiments.charts import export_charts
from evolution_sim.io.checkpoints import load_checkpoint, save_checkpoint
from evolution_sim.io.export import export_experiment
from evolution_sim.simulation.engine import SimulationEngine
from evolution_sim.ui import theme
from evolution_sim.ui.layout import MINIMUM_SIZE, compute_layout
from evolution_sim.ui.renderer import LaboratoryRenderer, hit_test_creature


@dataclass(slots=True)
class SimulationController:
    engine: SimulationEngine
    paused: bool = False
    speed_index: int = 0

    SPEED_STEPS = (1, 2, 4, 8, 16)

    @property
    def speed_steps(self) -> int:
        return self.SPEED_STEPS[self.speed_index]

    def toggle_pause(self) -> None:
        self.paused = not self.paused

    def set_speed_index(self, index: int) -> None:
        if not 0 <= index < len(self.SPEED_STEPS):
            raise ValueError("speed index outside supported range")
        self.speed_index = index

    def advance_frame(self) -> None:
        if not self.paused:
            self.engine.step(self.speed_steps)

    @staticmethod
    def action_for_key(key: str, *, ctrl: bool) -> str | None:
        normalized = key.lower()
        if ctrl and normalized == "s":
            return "save"
        if ctrl and normalized == "o":
            return "load"
        return {
            "space": "toggle_pause",
            "r": "restart",
            "p": "perception",
            "t": "trails",
            "e": "export",
            "?": "help",
            "escape": "help",
            "1": "speed_1",
            "2": "speed_2",
            "3": "speed_3",
            "4": "speed_4",
            "5": "speed_5",
        }.get(normalized)


class EvolutionApp:
    def __init__(
        self,
        config: SimulationConfig,
        *,
        seed: int = 2026,
        size: tuple[int, int] = (1440, 900),
        show_setup: bool = True,
    ) -> None:
        pygame.init()
        pygame.display.set_caption("EVO / Observatory")
        requested = (max(size[0], MINIMUM_SIZE[0]), max(size[1], MINIMUM_SIZE[1]))
        self.surface = pygame.display.set_mode(requested, pygame.RESIZABLE)
        self.layout = compute_layout(*requested)
        self.config = config
        self.seed = seed
        self.engine = SimulationEngine(config, seed=seed)
        self.controller = SimulationController(self.engine)
        self.renderer = LaboratoryRenderer()
        self.clock = pygame.time.Clock()
        self.running = True
        self.show_setup = show_setup
        self.show_help = False
        self.show_trails = True
        self.show_perception = True
        self.selected_id: int | None = None
        self.active_tab = "Controls"
        self.message = "Enter starts the experiment" if show_setup else ""
        self.default_checkpoint = Path("exports/checkpoints/latest.json")

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path is not None else self.default_checkpoint
        result = save_checkpoint(self.engine, target)
        self.message = f"Saved {result.name}"
        return result

    def load(self, path: str | Path | None = None) -> None:
        target = Path(path) if path is not None else self.default_checkpoint
        restored = load_checkpoint(target)
        self.engine = restored
        self.config = restored.config
        self.seed = restored.seed
        self.controller.engine = restored
        self.selected_id = None
        self.message = f"Loaded {target.name}"

    def export(self, path: str | Path | None = None) -> Path:
        target = (
            Path(path)
            if path is not None
            else Path("exports") / datetime.now().strftime("session-%Y%m%d-%H%M%S")
        )
        export_experiment(self.engine, target)
        export_charts(self.engine, target)
        self.message = f"Exported {target.name}"
        return target

    def _action(self, action: str | None) -> None:
        if action is None:
            return
        if action == "toggle_pause":
            self.controller.toggle_pause()
        elif action.startswith("speed_"):
            self.controller.set_speed_index(int(action[-1]) - 1)
        elif action == "restart":
            self.engine = SimulationEngine(self.config, seed=self.seed)
            self.controller.engine = self.engine
            self.selected_id = None
            self.message = "Restarted with the same seed"
        elif action == "perception":
            self.show_perception = not self.show_perception
        elif action == "trails":
            self.show_trails = not self.show_trails
        elif action == "help":
            self.show_help = not self.show_help
        elif action == "save":
            self.save()
        elif action == "load":
            if self.default_checkpoint.exists():
                self.load()
            else:
                self.message = "No checkpoint saved yet"
        elif action == "export":
            self.export()

    def _events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.VIDEORESIZE:
                size = (max(event.w, MINIMUM_SIZE[0]), max(event.h, MINIMUM_SIZE[1]))
                self.surface = pygame.display.set_mode(size, pygame.RESIZABLE)
                self.layout = compute_layout(*size)
            elif event.type == pygame.KEYDOWN:
                if self.show_setup and event.key in {pygame.K_RETURN, pygame.K_SPACE}:
                    self.show_setup = False
                    self.message = ""
                    continue
                ctrl = bool(event.mod & pygame.KMOD_CTRL)
                key = "?" if event.key == pygame.K_QUESTION else pygame.key.name(event.key)
                self._action(self.controller.action_for_key(key, ctrl=ctrl))
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                point = event.pos
                tabs = ("Controls", "Inspector", "Events")
                inner = self.layout.sidebar.inflate(-18, -18)
                tabs_rect = pygame.Rect(inner.left, inner.top + 32, inner.width, 32)
                if tabs_rect.collidepoint(point):
                    index = min(
                        len(tabs) - 1, (point[0] - tabs_rect.left) * len(tabs) // tabs_rect.width
                    )
                    self.active_tab = tabs[index]
                elif self.layout.world.collidepoint(point):
                    self.selected_id = hit_test_creature(
                        self.engine.snapshot(), point, self.layout.world, self.config
                    )
                    if self.selected_id is not None:
                        self.active_tab = "Inspector"

    def _setup_overlay(self) -> None:
        overlay = pygame.Surface(self.layout.window.size, pygame.SRCALPHA)
        overlay.fill((2, 8, 14, 205))
        self.surface.blit(overlay, (0, 0))
        box = pygame.Rect(0, 0, 650, 340)
        box.center = self.layout.window.center
        pygame.draw.rect(self.surface, theme.TISSUE, box, border_radius=14)
        pygame.draw.rect(self.surface, theme.HAIRLINE, box, 1, border_radius=14)
        fonts = self.renderer.fonts
        title = fonts.display.render("Begin an evolution run", True, theme.INK)
        self.surface.blit(title, (box.left + 34, box.top + 32))
        body = [
            f"Seed {self.seed} · {self.config.initial_population} founders",
            (
                f"Food {self.config.resources.initial_count} · "
                f"mutation {self.config.genome.mutation_probability:.0%}"
            ),
            "Observe equilibrium, then apply pressure through a scenario or Events view.",
        ]
        for index, line in enumerate(body):
            image = fonts.body.render(line, True, theme.MUTED)
            self.surface.blit(image, (box.left + 36, box.top + 98 + index * 42))
        prompt = fonts.title.render("Press Enter to start", True, theme.ION)
        self.surface.blit(prompt, prompt.get_rect(center=(box.centerx, box.bottom - 52)))

    def run(
        self,
        *,
        max_frames: int | None = None,
        screenshot_path: str | Path | None = None,
    ) -> int:
        frames = 0
        while self.running and (max_frames is None or frames < max_frames):
            self._events()
            if not self.show_setup:
                self.controller.advance_frame()
            self.renderer.render(
                self.surface,
                self.engine,
                self.layout,
                selected_id=self.selected_id,
                active_tab=self.active_tab,
                paused=self.controller.paused or self.show_setup,
                speed_steps=self.controller.speed_steps,
                show_trails=self.show_trails,
                show_perception=self.show_perception,
                show_help=self.show_help,
                message=self.message,
            )
            if self.show_setup:
                self._setup_overlay()
            pygame.display.flip()
            frames += 1
            if max_frames is None:
                self.clock.tick(60)
        if screenshot_path is not None:
            target = Path(screenshot_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(self.surface, target)
        return frames
