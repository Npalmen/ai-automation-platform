from enum import Enum


class IntegrationType(str, Enum):
    GOOGLE = "google"
    MICROSOFT = "microsoft"
    VISMA = "visma"
    FORTNOX = "fortnox"