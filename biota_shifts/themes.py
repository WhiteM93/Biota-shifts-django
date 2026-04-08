"""Единая тема оформления: спокойная современная тёмная палитра."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Сдержанная тёмная тема: графитовый фон + холодный акцент.
APP_THEME: dict[str, Any] = {
    "primary": "#7C8CFF",
    "background": "#0F1115",
    "secondary": "#1A2130",
    "text": "#EAF0FF",
    "mode": "dark",
}


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    s = h.strip().lstrip("#")
    if len(s) == 6:
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    return 15, 17, 21


def _rgba(hex_color: str, alpha: float) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return f"rgba({r},{g},{b},{alpha})"


def _lighten(hex_color: str, amount: float = 0.12) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    r = min(255, int(r + (255 - r) * amount))
    g = min(255, int(g + (255 - g) * amount))
    b = min(255, int(b + (255 - b) * amount))
    return f"#{r:02x}{g:02x}{b:02x}"


def _darken(hex_color: str, amount: float = 0.14) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    r = max(0, int(r * (1 - amount)))
    g = max(0, int(g * (1 - amount)))
    b = max(0, int(b * (1 - amount)))
    return f"#{r:02x}{g:02x}{b:02x}"


def _streamlit_theme_toml_block(theme: dict[str, Any]) -> str:
    p = theme["primary"]
    bg = theme["background"]
    sec = theme["secondary"]
    tx = theme["text"]
    base = "dark" if theme.get("mode") == "dark" else "light"
    return (
        "[theme]\n"
        f'primaryColor = "{p}"\n'
        f'backgroundColor = "{bg}"\n'
        f'secondaryBackgroundColor = "{sec}"\n'
        f'textColor = "{tx}"\n'
        f'base = "{base}"\n'
    )


def _strip_theme_section(text: str) -> str:
    return re.sub(r"(?ms)^\[theme\]\s*\n.*?(?=^\[|\Z)", "", text).strip()


def sync_streamlit_config_theme(theme: dict[str, Any]) -> bool:
    """Пишет [theme] в .streamlit/config.toml (st.data_editor / Glide)."""
    root = Path(__file__).resolve().parent.parent
    path = root / ".streamlit" / "config.toml"
    block = _streamlit_theme_toml_block(theme)
    prev = path.read_text(encoding="utf-8") if path.exists() else ""
    stripped = _strip_theme_section(prev)
    candidate = (stripped + "\n\n" + block).strip() + "\n" if stripped else block
    if path.exists() and prev.strip() == candidate.strip():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(candidate, encoding="utf-8")
    return True


def build_app_theme_css(theme: dict[str, Any]) -> str:
    p = theme["primary"]
    bg = theme["background"]
    sec = theme["secondary"]
    tx = theme["text"]
    r1 = _rgba(p, 0.18)
    r2 = _rgba(p, 0.14)
    r3 = _rgba(p, 0.07)
    r_border = _rgba(p, 0.42)
    r_border_soft = _rgba(p, 0.28)
    sidebar_bg = "#141922"
    is_dark = theme.get("mode") == "dark"
    p_hover = _lighten(p, 0.11) if not is_dark else _lighten(p, 0.15)
    p_active = _darken(p, 0.1) if not is_dark else _darken(p, 0.06)
    sec_hover = _lighten(sec, 0.06) if not is_dark else _lighten(sec, 0.04)
    sec_active = _darken(sec, 0.05) if not is_dark else _darken(sec, 0.08)
    de = (
        'div[data-testid="stDataFrameGlideDataEditor"], '
        'div[data-testid="stDataEditor"], '
        ".stDataFrameGlideDataEditor"
    )
    return f"""
    <style>
    :root {{
        --biota-primary: {p};
        --biota-bg: {bg};
        --biota-surface: {sec};
        --biota-text: {tx};
    }}
    .stApp {{
        background-color: {bg} !important;
        color: {tx} !important;
    }}
    section[data-testid="stSidebar"] {{
        background-color: {sidebar_bg} !important;
        border-right: 1px solid {_rgba(p, 0.12)} !important;
    }}
    [data-testid="stSidebarContent"] {{
        background-color: {sidebar_bg} !important;
    }}
    [data-testid="stAppViewContainer"] .main .block-container {{
        background-color: transparent !important;
    }}
    [data-testid="stHeader"] {{
        background: {bg} !important;
    }}
    div[data-testid="stButton"] > button[kind="primary"],
    button[kind="primary"],
    [data-testid="stBaseButton-primary"] button,
    [data-testid="stBaseButton-primary"] {{
        background-color: {p} !important;
        border-color: {p} !important;
        color: #FFFFFF !important;
    }}
    div[data-testid="stButton"] > button[kind="primary"]:hover,
    button[kind="primary"]:hover,
    [data-testid="stBaseButton-primary"] button:hover,
    [data-testid="stBaseButton-primary"]:hover {{
        background-color: {p_hover} !important;
        border-color: {p_hover} !important;
        color: #FFFFFF !important;
    }}
    div[data-testid="stButton"] > button[kind="primary"]:active,
    button[kind="primary"]:active {{
        background-color: {p_active} !important;
        border-color: {p_active} !important;
    }}
    div[data-testid="stButton"] > button:focus-visible,
    button:focus-visible,
    [data-testid="stBaseButton-primary"] button:focus-visible {{
        outline: 2px solid {_rgba(p, 0.55)} !important;
        outline-offset: 2px !important;
    }}
    div[data-testid="stButton"] > button[kind="secondary"],
    button[kind="secondary"],
    [data-testid="stBaseButton-secondary"] button,
    [data-testid="stBaseButton-secondary"] {{
        background-color: {sec} !important;
        border: 1px solid {r_border} !important;
        color: {p} !important;
    }}
    div[data-testid="stButton"] > button[kind="secondary"]:hover,
    button[kind="secondary"]:hover,
    [data-testid="stBaseButton-secondary"] button:hover,
    [data-testid="stBaseButton-secondary"]:hover {{
        background-color: {sec_hover} !important;
        border-color: {r_border} !important;
        color: {p} !important;
    }}
    div[data-testid="stButton"] > button[kind="secondary"]:active,
    button[kind="secondary"]:active {{
        background-color: {sec_active} !important;
    }}
    div[data-testid="stButton"] > button:not([kind="primary"]):not([kind="secondary"]) {{
        background-color: {bg} !important;
        border: 1px solid {r_border_soft} !important;
        color: {p} !important;
    }}
    [data-testid="stDownloadButton"] button,
    [data-testid="stDownloadButton"] [data-testid="stBaseButton-secondary"] {{
        background-color: {sec} !important;
        border: 1px solid {r_border} !important;
        color: {p} !important;
    }}
    [data-testid="stDownloadButton"] button:hover {{
        background-color: {sec_hover} !important;
        border-color: {r_border} !important;
    }}
    [data-testid="stFileUploader"] button {{
        border-color: {r_border_soft} !important;
        color: {p} !important;
    }}
    [data-testid="stFileUploader"] button:hover {{
        background-color: {sec_hover} !important;
        border-color: {r_border} !important;
    }}
    div[data-testid="stSelectbox"] [data-baseweb="select"] > div,
    div[data-testid="stSelectbox"] [data-baseweb="select"] [data-baseweb="tag"] {{
        background-color: {sec} !important;
        border-color: {r_border} !important;
        color: {tx} !important;
    }}
    div[data-testid="stSelectbox"] [data-baseweb="select"] svg {{
        fill: {p} !important;
    }}
    div[data-testid="stSelectbox"] [data-baseweb="select"] > div:hover,
    div[data-testid="stSelectbox"] [data-baseweb="select"]:hover > div {{
        background-color: {sec_hover} !important;
        border-color: {r_border} !important;
    }}
    div[data-baseweb="popover"] ul[role="listbox"],
    div[data-baseweb="popover"] li {{
        background-color: {sec} !important;
        color: {tx} !important;
    }}
    div[data-baseweb="popover"] li[aria-selected="true"] {{
        background-color: {r3} !important;
    }}
    div[data-baseweb="popover"] li:hover {{
        background-color: {_rgba(p, 0.12)} !important;
    }}
    [data-testid="stDataFrame"], div.stDataFrame {{
        border: 1px solid {r_border} !important;
        border-radius: 10px !important;
        overflow: hidden !important;
    }}
    {de} button,
    {de} [role="button"],
    div[data-testid="stDataFrame"] button,
    div[data-testid="stDataFrame"] [role="button"] {{
        background-color: {sec} !important;
        border: 1px solid {r_border} !important;
        color: {p} !important;
    }}
    {de} button:hover,
    {de} [role="button"]:hover,
    div[data-testid="stDataFrame"] button:hover,
    div[data-testid="stDataFrame"] [role="button"]:hover {{
        background-color: {sec_hover} !important;
        border-color: {r_border} !important;
    }}
    a {{
        color: {p} !important;
    }}
    [data-testid="stMetricValue"] {{
        color: {p} !important;
    }}
    {de} [role="columnheader"] {{
        font-size: 11px !important;
        text-align: center !important;
        border: 1px solid {r1} !important;
    }}
    {de} [role="gridcell"] {{
        font-size: 13px !important;
        font-weight: 500 !important;
        padding: 0 !important;
        border: 1px solid {r2} !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        text-align: center !important;
    }}
    {de} [role="gridcell"] [data-testid="stMarkdownContainer"],
    {de} [role="gridcell"] p {{
        text-align: center !important;
        margin: 0 !important;
        width: 100% !important;
    }}
    {de} input[type="text"],
    {de} textarea {{
        text-align: center !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        padding: 0 1px !important;
        margin: 0 auto !important;
        width: 100% !important;
        height: 100% !important;
        min-height: 100% !important;
        box-sizing: border-box !important;
        line-height: normal !important;
    }}
    {de} [role="gridcell"] [contenteditable="true"] {{
        text-align: center !important;
        width: 100% !important;
    }}
    div[data-testid="stTabs"] [data-baseweb="tab-list"] {{
        gap: 8px;
        background: {r3};
        padding: 6px 8px;
        border-radius: 10px;
    }}
    div[data-testid="stTabs"] button[data-baseweb="tab"] {{
        border-radius: 8px;
        padding: 10px 20px;
        font-weight: 600;
    }}
    div[data-testid="stTabs"] button[data-baseweb="tab"]:hover {{
        background-color: {sec_hover} !important;
        color: {p} !important;
    }}
    div[data-testid="stTabs"] button[data-baseweb="tab"]:focus-visible {{
        outline: 2px solid {_rgba(p, 0.45)} !important;
        outline-offset: 2px !important;
    }}
    .main .block-container {{
        max-width: min(1200px, 100%);
        margin-left: auto;
        margin-right: auto;
        padding-left: 1.5rem;
        padding-right: 1.5rem;
    }}
    </style>
    """
