"""
Titan Core - System Tools
-------------------------
Provides system information Titan can answer without AI.
"""

from datetime import datetime


def get_time():

    return datetime.now().strftime("%I:%M %p")


def get_date():

    return datetime.now().strftime("%A, %B %d %Y")