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
from evolution_sim.ui.customization import PARAMETERS, PRESETS, CustomizationPanel
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
            "c": "customize",
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
        pygame.display.set_caption("Vikasa / Observatory")
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
        self.customizer = CustomizationPanel(config, seed)
        self.setup_from_running = False

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
        self.customizer = CustomizationPanel(self.config, self.seed)
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
        elif action == "customize":
            self.customizer = CustomizationPanel(self.config, self.seed)
            self.setup_from_running = True
            self.show_setup = True
            self.message = "Tune the world, then apply and restart"
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

    def _apply_customization(self) -> None:
        self.config = self.customizer.config
        self.seed = self.customizer.seed
        speed_index = self.controller.speed_index
        self.engine = SimulationEngine(self.config, seed=self.seed)
        self.controller = SimulationController(self.engine, speed_index=speed_index)
        self.selected_id = None
        self.show_setup = False
        self.setup_from_running = False
        self.message = f"World applied · seed {self.seed}"

    def _setup_geometry(self) -> dict[str, object]:
        window = self.layout.window
        box = pygame.Rect(0, 0, min(1060, window.width - 40), min(680, window.height - 40))
        box.center = window.center
        presets: list[pygame.Rect] = []
        preset_width = (box.width - 78) // len(PRESETS)
        for index in range(len(PRESETS)):
            presets.append(
                pygame.Rect(
                    box.left + 24 + index * (preset_width + 10), box.top + 108, preset_width, 42
                )
            )
        rows: list[tuple[pygame.Rect, pygame.Rect, pygame.Rect]] = []
        for index in range(len(PARAMETERS)):
            top = box.top + 182 + index * 47
            row = pygame.Rect(box.left + 26, top, min(650, box.width - 350), 39)
            minus = pygame.Rect(row.right - 112, top + 4, 32, 31)
            plus = pygame.Rect(row.right - 36, top + 4, 32, 31)
            rows.append((row, minus, plus))
        launch = pygame.Rect(box.right - 302, box.bottom - 76, 272, 46)
        trails = pygame.Rect(box.right - 302, box.top + 340, 130, 40)
        perception = pygame.Rect(box.right - 162, box.top + 340, 132, 40)
        return {
            "box": box,
            "presets": presets,
            "rows": rows,
            "launch": launch,
            "trails": trails,
            "perception": perception,
        }

    def _setup_key(self, event: pygame.event.Event) -> None:
        if event.key in {pygame.K_RETURN, pygame.K_SPACE}:
            self._apply_customization()
        elif event.key == pygame.K_ESCAPE and self.setup_from_running:
            self.show_setup = False
            self.setup_from_running = False
            self.message = "Customization cancelled"
        elif event.key == pygame.K_UP:
            self.customizer.move_selection(-1)
        elif event.key == pygame.K_DOWN:
            self.customizer.move_selection(1)
        elif event.key == pygame.K_LEFT:
            self.customizer.adjust(-1)
        elif event.key == pygame.K_RIGHT:
            self.customizer.adjust(1)
        elif pygame.K_1 <= event.key <= pygame.K_4:
            self.customizer.apply_preset(tuple(PRESETS)[event.key - pygame.K_1])
        elif event.key == pygame.K_t:
            self.show_trails = not self.show_trails
        elif event.key == pygame.K_p:
            self.show_perception = not self.show_perception

    def _setup_click(self, point: tuple[int, int]) -> None:
        geometry = self._setup_geometry()
        for name, rect in zip(PRESETS, geometry["presets"], strict=True):
            if rect.collidepoint(point):
                self.customizer.apply_preset(name)
                return
        for index, (_row, minus, plus) in enumerate(geometry["rows"]):
            if minus.collidepoint(point) or plus.collidepoint(point):
                self.customizer.selected_index = index
                self.customizer.adjust(-1 if minus.collidepoint(point) else 1)
                return
        if geometry["trails"].collidepoint(point):
            self.show_trails = not self.show_trails
        elif geometry["perception"].collidepoint(point):
            self.show_perception = not self.show_perception
        elif geometry["launch"].collidepoint(point):
            self._apply_customization()

    def _events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.VIDEORESIZE:
                size = (max(event.w, MINIMUM_SIZE[0]), max(event.h, MINIMUM_SIZE[1]))
                self.surface = pygame.display.set_mode(size, pygame.RESIZABLE)
                self.layout = compute_layout(*size)
            elif event.type == pygame.KEYDOWN:
                if self.show_setup:
                    self._setup_key(event)
                    continue
                ctrl = bool(event.mod & pygame.KMOD_CTRL)
                key = "?" if event.key == pygame.K_QUESTION else pygame.key.name(event.key)
                self._action(self.controller.action_for_key(key, ctrl=ctrl))
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                point = event.pos
                if self.show_setup:
                    self._setup_click(point)
                    continue
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
        overlay.fill((2, 8, 14, 225))
        self.surface.blit(overlay, (0, 0))
        geometry = self._setup_geometry()
        box = geometry["box"]
        pygame.draw.rect(self.surface, theme.TISSUE, box, border_radius=14)
        pygame.draw.rect(self.surface, theme.HAIRLINE, box, 1, border_radius=14)
        fonts = self.renderer.fonts
        title = fonts.display.render("CREATE A LIVING WORLD", True, theme.INK)
        self.surface.blit(title, (box.left + 26, box.top + 24))
        subtitle = fonts.small.render(
            "Choose a field preset, then tune ecology and genetics before launch.",
            True,
            theme.MUTED,
        )
        self.surface.blit(subtitle, (box.left + 28, box.top + 66))

        for name, rect in zip(PRESETS, geometry["presets"], strict=True):
            active = name == self.customizer.active_preset
            pygame.draw.rect(
                self.surface,
                theme.TISSUE_RAISED if active else theme.MIDNIGHT,
                rect,
                border_radius=8,
            )
            pygame.draw.rect(
                self.surface,
                theme.ION if active else theme.HAIRLINE,
                rect,
                1,
                border_radius=8,
            )
            label = fonts.small.render(name, True, theme.ION if active else theme.INK)
            self.surface.blit(label, label.get_rect(center=rect.center))

        rows = geometry["rows"]
        for index, (parameter, (row, minus, plus)) in enumerate(zip(PARAMETERS, rows, strict=True)):
            selected = index == self.customizer.selected_index
            if selected:
                pygame.draw.rect(self.surface, theme.TISSUE_RAISED, row, border_radius=7)
                pygame.draw.rect(self.surface, theme.ION, row, 1, border_radius=7)
            label = fonts.small.render(
                parameter.label, True, theme.INK if selected else theme.MUTED
            )
            self.surface.blit(label, (row.left + 10, row.top + 10))
            track = pygame.Rect(
                row.left + 186, row.centery - 2, max(50, minus.left - row.left - 200), 4
            )
            pygame.draw.rect(self.surface, theme.HAIRLINE, track, border_radius=2)
            fill = track.copy()
            fill.width = max(3, round(track.width * self.customizer.progress_for(index)))
            pygame.draw.rect(self.surface, theme.ION, fill, border_radius=2)
            for button, symbol in ((minus, "-"), (plus, "+")):
                pygame.draw.rect(self.surface, theme.MIDNIGHT, button, border_radius=6)
                pygame.draw.rect(self.surface, theme.HAIRLINE, button, 1, border_radius=6)
                glyph = fonts.body.render(symbol, True, theme.INK)
                self.surface.blit(glyph, glyph.get_rect(center=button.center))
            value = fonts.small.render(self.customizer.value_label_for(index), True, theme.ION)
            value_center = ((minus.right + plus.left) // 2, row.centery)
            self.surface.blit(value, value.get_rect(center=value_center))

        side = pygame.Rect(box.right - 320, box.top + 182, 290, 140)
        pygame.draw.rect(self.surface, theme.MIDNIGHT, side, border_radius=10)
        pygame.draw.rect(self.surface, theme.HAIRLINE, side, 1, border_radius=10)
        heading = fonts.title.render("Launch profile", True, theme.INK)
        self.surface.blit(heading, (side.left + 18, side.top + 16))
        summary = (
            f"{self.customizer.config.initial_population:,} founders  ·  "
            f"{self.customizer.config.resources.initial_count:,} food",
            f"{self.customizer.config.genome.mutation_probability:.0%} mutation  ·  "
            f"seed {self.customizer.seed:,}",
            f"ceiling {self.customizer.config.reproduction.population_cap:,}  ·  "
            f"life {self.customizer.config.maximum_age:,}",
        )
        for index, line in enumerate(summary):
            image = fonts.small.render(line, True, theme.MUTED)
            self.surface.blit(image, (side.left + 18, side.top + 54 + index * 24))

        for rect, label, enabled in (
            (geometry["trails"], "Trails", self.show_trails),
            (geometry["perception"], "Senses", self.show_perception),
        ):
            pygame.draw.rect(
                self.surface,
                theme.TISSUE_RAISED if enabled else theme.MIDNIGHT,
                rect,
                border_radius=8,
            )
            pygame.draw.rect(
                self.surface,
                theme.ION if enabled else theme.HAIRLINE,
                rect,
                1,
                border_radius=8,
            )
            image = fonts.small.render(f"{'●' if enabled else '○'} {label}", True, theme.INK)
            self.surface.blit(image, image.get_rect(center=rect.center))

        instructions = (
            "Up/Down select  ·  Left/Right tune  ·  1-4 presets",
            "T trails  ·  P senses  ·  C reopen anytime",
        )
        for index, line in enumerate(instructions):
            image = fonts.tiny.render(line, True, theme.MUTED)
            self.surface.blit(image, (box.right - 302, box.top + 402 + index * 24))

        launch = geometry["launch"]
        pygame.draw.rect(self.surface, theme.ION, launch, border_radius=9)
        prompt = fonts.title.render("APPLY & LAUNCH  ·  ENTER", True, theme.MIDNIGHT)
        self.surface.blit(prompt, prompt.get_rect(center=launch.center))

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
