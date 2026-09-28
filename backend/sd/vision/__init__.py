"""Компьютерное зрение поверх рендера: безопасная зона, фон под текстом, дефекты."""

from .image import (Bbox, dominant_color, ink_mask, ink_ratio, largest_free_rect,
                    load_rgb, region_luminance)
from .safe_area import (Obstacle, background_under, find_obstacles, obstacle_mask,
                        refine_safe_area)

__all__ = ["Bbox", "load_rgb", "ink_mask", "ink_ratio", "largest_free_rect",
           "region_luminance", "dominant_color", "refine_safe_area", "find_obstacles",
           "obstacle_mask", "background_under", "Obstacle"]
