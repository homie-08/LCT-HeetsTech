"""Планирование истории и подбор паттернов."""

from .match import affinity, match_deck, score
from .model import DeckPlan, DeckSpec, ScoreBreakdown, SlidePlan, SlideSpec
from .storyline import PLAN_SCHEMA, build_plan, plan_heuristic, plan_with_llm

__all__ = ["DeckPlan", "SlidePlan", "DeckSpec", "SlideSpec", "ScoreBreakdown",
           "build_plan", "plan_heuristic", "plan_with_llm", "PLAN_SCHEMA",
           "match_deck", "score", "affinity"]
