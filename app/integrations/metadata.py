from app.integrations.enums import IntegrationType


INTEGRATION_METADATA = {
    IntegrationType.GOOGLE: {
        "label": "Google Workspace",
        "description": "Integration mot Gmail, Drive, Calendar och andra Google-tjänster.",
    },
    IntegrationType.MICROSOFT: {
        "label": "Microsoft 365",
        "description": "Integration mot Outlook, OneDrive, Teams och andra Microsoft-tjänster.",
    },
    IntegrationType.VISMA: {
        "label": "Visma",
        "description": "Integration mot Visma för ekonomi- och affärsflöden.",
    },
    IntegrationType.FORTNOX: {
        "label": "Fortnox",
        "description": "Integration mot Fortnox för ekonomi- och affärsflöden.",
    },
}
