"""Platform-wide constants: Snowflake objects, business thresholds and palette."""
from __future__ import annotations

import os

COMPANY_NAME = "Sample Retail Group"
APP_NAME = "Inventory 360"
APP_TAGLINE = "Enterprise supply chain intelligence"
CURRENCY = "GBP"

DATABASE = os.getenv("INV360_DATABASE", "INVENTORY_360_DB")
MARTS = f"{DATABASE}.MARTS"
STAGING = f"{DATABASE}.STAGING"
APP_SCHEMA = f"{DATABASE}.APP"

# Cache lifetimes (seconds) for the data-access layer
TTL_REFERENCE = 60 * 60
TTL_OPERATIONAL = 10 * 60

# Stock status ordering and RAG colours (shared by charts and tables)
STOCK_STATUS_ORDER = ["Out of stock", "Critical", "Low", "Healthy", "Overstock", "Excess"]
STOCK_STATUS_COLOURS = {
    "Out of stock": "#B42318",
    "Critical": "#E04F16",
    "Low": "#F79009",
    "Healthy": "#12B76A",
    "Overstock": "#2E90FA",
    "Excess": "#6941C6",
}
PRIORITY_ORDER = ["P1 - Urgent", "P2 - High", "P3 - Medium", "P4 - Routine", "None"]
RISK_ORDER = ["High", "Medium", "Low"]
RISK_COLOURS = {"High": "#B42318", "Medium": "#F79009", "Low": "#12B76A"}

# Budget variance tolerance before a line is flagged amber / red
VARIANCE_AMBER = 0.03
VARIANCE_RED = 0.07

# Service-level policy by velocity class: (target service level, z-score, review days)
SERVICE_POLICY = {
    "A": (0.95, 1.65, 7),
    "B": (0.90, 1.28, 14),
    "C": (0.85, 1.04, 28),
}
HOLDING_COST_RATE = 0.22
