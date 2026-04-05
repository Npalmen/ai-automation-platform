# app/integrations/metadata.py

from app.integrations.enums import IntegrationType


INTEGRATION_METADATA = {
    IntegrationType.CRM: {
        "label": "CRM",
        "description": "Generic CRM webhook integration for lead delivery.",
    },
    IntegrationType.ACCOUNTING: {
        "label": "Accounting",
        "description": "Generic accounting webhook integration for invoice delivery.",
    },
    IntegrationType.SUPPORT: {
        "label": "Support",
        "description": "Generic support webhook integration for inquiry delivery.",
    },
    IntegrationType.MONDAY: {
        "label": "Monday.com",
        "description": "Monday.com integration for boards, items, and operational workflows.",
    },
    IntegrationType.FORTNOX: {
        "label": "Fortnox",
        "description": "Fortnox integration for customers and invoices.",
    },
    IntegrationType.VISMA: {
        "label": "Visma eAccounting",
        "description": "Visma eAccounting integration for customers and invoices.",
    },
    IntegrationType.GOOGLE_MAIL: {
        "label": "Google Mail",
        "description": "Google Mail integration for sending emails.",
    },
    IntegrationType.GOOGLE_CALENDAR: {
        "label": "Google Calendar",
        "description": "Google Calendar integration for creating events and meetings.",
    },
    IntegrationType.MICROSOFT_MAIL: {
        "label": "Microsoft Mail",
        "description": "Microsoft 365 mail integration for sending emails.",
    },
    IntegrationType.MICROSOFT_CALENDAR: {
        "label": "Microsoft Calendar",
        "description": "Microsoft 365 calendar integration for creating events and meetings.",
    },
}