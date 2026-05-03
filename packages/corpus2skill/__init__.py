"""Corpus2Skill — convert document corpus into navigable LLM skill hierarchy."""
from packages.corpus2skill.config import Corpus2SkillConfig
from packages.corpus2skill.runner import run_corpus2skill

__all__ = ["Corpus2SkillConfig", "run_corpus2skill"]
