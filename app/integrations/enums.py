from enum import Enum


class IntegrationType(str, Enum):
    CRM = "crm"
    ACCOUNTING = "accounting"
    SUPPORT = "support"
    MONDAY = "monday"
    FORTNOX = "fortnox"
    VISMA = "visma"
    GOOGLE_MAIL = "google_mail"
    GOOGLE_CALENDAR = "google_calendar"
    MICROSOFT_MAIL = "microsoft_mail"
    MICROSOFT_CALENDAR = "microsoft_calendar"