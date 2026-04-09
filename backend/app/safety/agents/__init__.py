"""Domain-specific safety monitoring agents."""

from .base import SafetyAgent, SafetyVerdict, Severity, Verdict
from .legal import LegalAgent
from .ethical import EthicalAgent
from .homologation import HomologationAgent
from .privacy import PrivacyAgent
from .safety import PhysicalSafetyAgent

ALL_AGENTS: dict[str, type[SafetyAgent]] = {
    "legal": LegalAgent,
    "ethical": EthicalAgent,
    "homologation": HomologationAgent,
    "privacy": PrivacyAgent,
    "safety": PhysicalSafetyAgent,
}

__all__ = [
    "SafetyAgent",
    "SafetyVerdict",
    "Severity",
    "Verdict",
    "LegalAgent",
    "EthicalAgent",
    "HomologationAgent",
    "PrivacyAgent",
    "PhysicalSafetyAgent",
    "ALL_AGENTS",
]
