"""CSS theme constants for conv-tester UI."""

_DARK_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Inter:wght@400;600;700&display=swap');

:root {
    --ct-bg:        #0D0D0D;
    --ct-surface:   #151515;
    --ct-surface2:  #1A1A1A;
    --ct-border:    #2A2A2A;
    --ct-border2:   #1E1E1E;
    --ct-text:      #E8E8E8;
    --ct-text2:     #CCCCCC;
    --ct-text3:     #AAAAAA;
    --ct-text4:     #888888;
    --ct-text5:     #666666;
    --ct-accent:    #E87D0D;
    --ct-pill-pass: #0D1F12;
    --ct-pill-fail: #1F0D0D;
    --ct-pill-inc:  #1F1A0D;
    --ct-pill-run:  #1C2030;
    --ct-user-text: #60A5FA;
    --ct-bot-text:  #4ADE80;
    --ct-user-bg:   #0A1628;
    --ct-bot-bg:    #091A0F;
    --ct-content-font: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* ---- Base ---- */
html, body, [data-testid="stAppViewContainer"] {
    background-color: #0D0D0D !important;
    font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'SF Mono', ui-monospace, monospace !important;
    color: #E8E8E8;
}
[data-testid="stSidebar"] {
    background-color: #111111 !important;
    border-right: 1px solid #2A2A2A !important;
}
[data-testid="stSidebar"] * { color: #E8E8E8 !important; }
[data-testid="stSidebarContent"] { padding-top: 0.5rem !important; }

/* ---- Headings ---- */
h1, h2, h3 { font-weight: 700; letter-spacing: -0.01em; color: #FFFFFF; }
h1 { font-size: 1.6rem; }
h1::before { content: "> "; color: #E87D0D; }
h2 { font-size: 1.15rem; color: #E87D0D; }
h3 { font-size: 1rem; color: #CCCCCC; }

/* ---- Buttons ---- */
.stButton > button, .stFormSubmitButton > button {
    border-radius: 3px !important;
    font-weight: 600 !important;
    font-size: 0.82rem !important;
    border: 1px solid #E87D0D !important;
    padding: 0.38rem 1rem !important;
    background: #E87D0D !important;
    color: #0D0D0D !important;
    font-family: inherit !important;
    letter-spacing: 0.03em !important;
    transition: background 0.12s ease;
}
.stButton > button:hover, .stFormSubmitButton > button:hover {
    background: #FF9500 !important;
    border-color: #FF9500 !important;
}
.stButton > button[kind="secondary"] {
    background: transparent !important;
    border: 1px solid #333333 !important;
    color: #AAAAAA !important;
}
.stButton > button[kind="secondary"]:hover {
    border-color: #E87D0D !important;
    color: #E87D0D !important;
    background: transparent !important;
}

/* ---- Inputs / textareas / selects ---- */
input, textarea, [data-baseweb="select"] > div {
    border-radius: 3px !important;
    border: 1px solid #2A2A2A !important;
    background: #1A1A1A !important;
    color: #E8E8E8 !important;
    font-size: 0.88rem !important;
    font-family: inherit !important;
}
input:focus, textarea:focus {
    border-color: #E87D0D !important;
    box-shadow: 0 0 0 2px rgba(232,125,13,0.18) !important;
}
[data-baseweb="select"] svg { fill: #888888 !important; }

/* ---- Labels ---- */
label, [data-testid="stWidgetLabel"] p {
    color: #888888 !important;
    font-size: 0.78rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}

/* ---- Expanders ---- */
details { background: #151515 !important; border-radius: 3px !important; border: 1px solid #2A2A2A !important; }
details summary { color: #AAAAAA !important; font-weight: 500; padding: 0.5rem 0.75rem; font-size: 0.85rem; }
details summary:hover { color: #E87D0D !important; }

/* ---- Tabs ---- */
[data-baseweb="tab-list"] { border-bottom: 1px solid #2A2A2A !important; background: transparent !important; }
[data-baseweb="tab"] { font-weight: 500 !important; font-size: 0.85rem !important; color: #666666 !important; background: transparent !important; }
[aria-selected="true"] { color: #E87D0D !important; border-bottom: 2px solid #E87D0D !important; }

/* ---- Metrics ---- */
[data-testid="stMetricValue"] { font-weight: 700; font-size: 1.2rem; color: #FFFFFF; font-family: inherit; }
[data-testid="stMetricLabel"] { color: #888888; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; }

/* ---- Chat messages ---- */
[data-testid="stChatMessage"] {
    background: #151515 !important;
    border: 1px solid #252525 !important;
    border-radius: 3px !important;
    margin-bottom: 0.4rem !important;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    background: #1C1308 !important;
    border-color: #3A2810 !important;
}

/* ---- Captions / small text ---- */
.stCaption, small { color: #666666 !important; font-size: 0.78rem; }

/* ---- Alerts ---- */
[data-testid="stAlert"] { border-radius: 3px !important; }

/* ---- DataFrames ---- */
[data-testid="stDataFrame"] { border-radius: 3px; overflow: hidden; border: 1px solid #2A2A2A; }

/* ---- Sidebar nav radio ---- */
[data-testid="stRadio"] > div { gap: 4px !important; }
[data-testid="stRadio"] label { padding: 6px 10px !important; border-radius: 3px !important; }
[data-testid="stRadio"] label:hover { background: #1A1A1A !important; }

/* ---- Scrollbar ---- */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #0D0D0D; }
::-webkit-scrollbar-thumb { background: #2A2A2A; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #E87D0D; }

/* ---- Code / pre ---- */
code { background: #1A1A1A !important; color: #E87D0D !important; border: 1px solid #2A2A2A; border-radius: 2px; padding: 1px 5px; font-size: 0.85em; }
pre { background: #1A1A1A !important; border: 1px solid #2A2A2A !important; border-radius: 3px !important; }

/* ---- Markdown tables ---- */
thead tr th { background: #1A1A1A !important; color: #888888 !important; font-size: 0.75rem !important; text-transform: uppercase; letter-spacing: 0.06em; border-bottom: 1px solid #2A2A2A !important; }
tbody tr td { border-bottom: 1px solid #1E1E1E !important; color: #E8E8E8 !important; font-size: 0.85rem; }
tbody tr:hover td { background: #161616 !important; }

/* ---- Dividers ---- */
hr { border-color: #2A2A2A !important; }

/* ---- Number input buttons ---- */
[data-testid="stNumberInput"] button { background: #1A1A1A !important; border-color: #2A2A2A !important; color: #888888 !important; }

/* ---- Rejudge pulse animation ---- */
@keyframes rj-pulse { 0%,100% { opacity:1; } 50% { opacity:0.3; } }

/* ---- Required-field asterisk: italic em inside widget labels renders red ---- */
[data-testid="stWidgetLabel"] em {
    color: #EF4444 !important;
    font-style: normal !important;
    font-weight: 700 !important;
}

/* ---- Toggle — larger switch and bolder label ---- */
[data-testid="stToggle"] { padding: 10px 14px !important; margin: 0 !important; }
[data-testid="stToggle"] > div { gap: 10px !important; }
[data-testid="stToggle"] > div > label {
    font-size: 1rem !important;
    font-weight: 600 !important;
    color: var(--ct-text) !important;
    letter-spacing: 0 !important;
    text-transform: none !important;
}
[data-testid="stToggle"] > div > div { transform: scale(1.25); transform-origin: left center; }

/* ── Hover colour palette strips (below turn cards) ─────────────────────── */
.ct-pal-strip {
    display: flex;
    margin-top: -1px;
    margin-bottom: 10px;
    border: 1px solid #252525;
    border-top: none;
    border-radius: 0 0 6px 6px;
    overflow: visible;
}
.ct-pal {
    position: relative;
    flex: 1;
    display: flex;
}
.ct-pal:first-child { border-right: 1px solid #252525; }
.ct-pal-btn {
    flex: 1;
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 4px 12px;
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: rgba(255,255,255,0.28);
    background: #131313;
    cursor: default;
    user-select: none;
    transition: color 0.12s, background 0.12s;
    white-space: nowrap;
}
.ct-pal:first-child .ct-pal-btn { border-radius: 0 0 0 6px; }
.ct-pal:last-child  .ct-pal-btn { border-radius: 0 0 6px 0; justify-content: flex-end; }
.ct-dot {
    width: 9px; height: 9px; border-radius: 50%;
    display: inline-block; flex-shrink: 0;
    border: 1.5px solid rgba(255,255,255,0.15);
    transition: border-color 0.12s, transform 0.12s;
}
.ct-pal:hover .ct-pal-btn { color: rgba(255,255,255,0.82); background: #1C1C1C; }
.ct-pal:hover .ct-dot    { border-color: rgba(255,255,255,0.55); transform: scale(1.15); }
.ct-pal-menu {
    display: none;
    position: absolute;
    bottom: calc(100% + 6px);
    background: #191919;
    border: 1px solid #353535;
    border-radius: 8px;
    padding: 10px 12px;
    z-index: 9999;
    gap: 8px;
    flex-direction: row;
    align-items: center;
    white-space: nowrap;
    box-shadow: 0 -8px 28px rgba(0,0,0,0.70);
}
.ct-pal:first-child .ct-pal-menu { left: 0; }
.ct-pal:last-child  .ct-pal-menu { right: 0; }
.ct-pal:hover .ct-pal-menu { display: flex; }
.ct-swatch {
    width: 20px; height: 20px; border-radius: 50%;
    display: inline-block; text-decoration: none;
    border: 2px solid transparent;
    flex-shrink: 0;
    transition: transform 0.12s, border-color 0.12s;
}
.ct-swatch:hover { transform: scale(1.4); border-color: rgba(255,255,255,0.85); }
.ct-swatch-active { border-color: rgba(255,255,255,0.85) !important; }

/* ── Colour pickers embedded inside the card header bar ─────────────────── */
.ct-pal-hdr-group {
    display: flex;
    gap: 4px;
    align-items: center;
    flex-shrink: 0;
    margin: 0 4px;
}
.ct-pal-hdr { flex: 0 0 auto; }
.ct-pal-hdr .ct-pal-btn {
    padding: 2px 9px;
    font-size: 0.60rem;
    border-radius: 4px;
    border: 1px solid rgba(255,255,255,0.10);
    background: rgba(255,255,255,0.04);
}
.ct-pal-hdr:hover .ct-pal-btn {
    background: rgba(255,255,255,0.10) !important;
    color: rgba(255,255,255,0.92) !important;
    border-color: rgba(255,255,255,0.28) !important;
}
.ct-pal-hdr:hover .ct-dot {
    border-color: rgba(255,255,255,0.70) !important;
    transform: scale(1.2) !important;
}
/* Menu opens DOWNWARD (not upward) since the trigger is in the header */
.ct-pal-hdr .ct-pal-menu {
    bottom: auto !important;
    top: calc(100% + 6px) !important;
    box-shadow: 0 8px 28px rgba(0,0,0,0.75) !important;
}
.ct-pal-hdr-group .ct-pal:first-child .ct-pal-menu { left: 0; right: auto; }
.ct-pal-hdr-group .ct-pal:last-child  .ct-pal-menu { right: 0; left: auto; }

/* ---- Slim header: hide toolbar/decoration, collapse header height ---- */
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
#MainMenu { display: none !important; }
header[data-testid="stHeader"] {
    height: 0 !important;
    min-height: 0 !important;
    overflow: visible !important;
    background: transparent !important;
    pointer-events: none !important;
}
/* Sidebar always visible — hide the collapse/expand toggle entirely */
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapseButton"] { display: none !important; }
section[data-testid="stSidebar"] { display: flex !important; visibility: visible !important; }
.main .block-container,
[data-testid="stMainBlockContainer"],
.stMainBlockContainer,
section.main > div.block-container { padding-top: 0.25rem !important; padding-bottom: 1rem !important; }
</style>
"""

_LIGHT_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
    --ct-bg:        #FFFFFF;
    --ct-surface:   #F8F8F8;
    --ct-surface2:  #F0F0F0;
    --ct-border:    #D8D8D8;
    --ct-border2:   #E8E8E8;
    --ct-text:      #1D1D1F;
    --ct-text2:     #3C3C3E;
    --ct-text3:     #4A4A4E;
    --ct-text4:     #6E6E73;
    --ct-text5:     #8E8E93;
    --ct-accent:    #E87D0D;
    --ct-pill-pass: #E8F5E9;
    --ct-pill-fail: #FFEBEE;
    --ct-pill-inc:  #FFF8E1;
    --ct-pill-run:  #E3F2FD;
    --ct-user-text: #1D4ED8;
    --ct-bot-text:  #15803D;
    --ct-user-bg:   #EFF6FF;
    --ct-bot-bg:    #F0FDF4;
    --ct-content-font: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* ---- Base ---- */
html, body, [data-testid="stAppViewContainer"] {
    background-color: #FFFFFF !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    color: #1D1D1F !important;
}

/* ---- GLOBAL TEXT — forces dark text everywhere in the main area ---- */
[data-testid="stAppViewContainer"] p,
[data-testid="stAppViewContainer"] span,
[data-testid="stAppViewContainer"] li,
[data-testid="stAppViewContainer"] div,
[data-testid="stMarkdownContainer"],
[data-testid="stMarkdownContainer"] *,
[data-testid="stText"],
[data-testid="stVerticalBlock"],
[data-testid="stHorizontalBlock"],
[data-testid="stElementContainer"],
.stMarkdown, .stMarkdown *,
.element-container { color: #1D1D1F !important; }

/* keep button text white; keep colored pills from being overridden */
.stButton > button *, .stFormSubmitButton > button * { color: #FFFFFF !important; }
.stButton > button[kind="secondary"] * { color: #555555 !important; }

/* ---- Sidebar ---- */
[data-testid="stSidebar"] {
    background-color: #F5F5F7 !important;
    border-right: 1px solid #D8D8D8 !important;
}
[data-testid="stSidebar"] * { color: #1D1D1F !important; }
[data-testid="stSidebarContent"] { padding-top: 0.5rem !important; }

/* ---- Headings ---- */
h1, h2, h3 { font-weight: 700; letter-spacing: -0.01em; color: #1D1D1F !important; }
h1 { font-size: 1.6rem; }
h1::before { content: ""; }
h2 { font-size: 1.15rem; color: #E87D0D !important; }
h3 { font-size: 1rem; color: #444444 !important; }

/* ---- Buttons ---- */
.stButton > button, .stFormSubmitButton > button {
    border-radius: 6px !important;
    font-weight: 600 !important;
    font-size: 0.82rem !important;
    border: 1px solid #E87D0D !important;
    padding: 0.38rem 1rem !important;
    background: #E87D0D !important;
    color: #FFFFFF !important;
    font-family: inherit !important;
    letter-spacing: 0.02em !important;
    transition: background 0.12s ease;
}
.stButton > button:hover, .stFormSubmitButton > button:hover {
    background: #D06B00 !important;
    border-color: #D06B00 !important;
}
.stButton > button[kind="secondary"] {
    background: transparent !important;
    border: 1px solid #D0D0D0 !important;
    color: #555555 !important;
}
.stButton > button[kind="secondary"]:hover {
    border-color: #E87D0D !important;
    color: #E87D0D !important;
    background: transparent !important;
}

/* ---- Inputs / textareas / selects ---- */
input, textarea, [data-baseweb="select"] > div {
    border-radius: 6px !important;
    border: 1px solid #D8D8D8 !important;
    background: #FFFFFF !important;
    color: #1D1D1F !important;
    font-size: 0.88rem !important;
    font-family: inherit !important;
}
input:focus, textarea:focus {
    border-color: #E87D0D !important;
    box-shadow: 0 0 0 2px rgba(232,125,13,0.15) !important;
}
[data-baseweb="select"] svg { fill: #666666 !important; }
[data-baseweb="select"] * { color: #1D1D1F !important; background-color: transparent; }
[data-baseweb="select"] [class*="placeholder"] { color: #8E8E93 !important; }

/* ---- Select / dropdown popover (the list that appears) ---- */
[data-baseweb="popover"],
[data-baseweb="popover"] > div,
[data-baseweb="menu"],
[data-baseweb="menu"] * {
    background: #FFFFFF !important;
    color: #1D1D1F !important;
}
[data-baseweb="popover"] ul, [data-baseweb="popover"] li { background: #FFFFFF !important; color: #1D1D1F !important; }
[data-baseweb="popover"] li:hover,
[data-baseweb="popover"] [aria-selected="true"] { background: #F0F0F0 !important; }

/* ---- Labels ---- */
label, [data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] * {
    color: #6E6E73 !important;
    font-size: 0.78rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}

/* ---- Widget-specific text fixes ---- */
[data-testid="stSelectbox"] [data-baseweb="select"] span { color: #1D1D1F !important; }
[data-testid="stNumberInput"] input { color: #1D1D1F !important; background: #FFFFFF !important; }
[data-testid="stTextInput"] input { color: #1D1D1F !important; }
[data-testid="stTextArea"] textarea { color: #1D1D1F !important; }
[data-testid="stCheckbox"] span { color: #1D1D1F !important; }
[data-testid="stRadio"] span { color: #1D1D1F !important; }
[data-testid="stSlider"] * { color: #1D1D1F !important; }
[data-testid="stSlider"] [role="slider"] { background: #E87D0D !important; }

/* ---- Expanders ---- */
details { background: #F8F8F8 !important; border-radius: 6px !important; border: 1px solid #D8D8D8 !important; }
details summary { color: #444444 !important; font-weight: 500; padding: 0.5rem 0.75rem; font-size: 0.85rem; }
details summary:hover { color: #E87D0D !important; }
[data-testid="stExpanderDetails"] * { color: #1D1D1F !important; }

/* ---- Tabs ---- */
[data-baseweb="tab-list"] { border-bottom: 1px solid #D8D8D8 !important; background: transparent !important; }
[data-baseweb="tab"] { font-weight: 500 !important; font-size: 0.85rem !important; color: #8E8E93 !important; background: transparent !important; }
[data-baseweb="tab"] * { color: #8E8E93 !important; }
[aria-selected="true"], [aria-selected="true"] * { color: #E87D0D !important; border-bottom: 2px solid #E87D0D !important; }
[data-baseweb="tab-panel"] * { color: #1D1D1F !important; }

/* ---- Metrics ---- */
[data-testid="stMetricValue"] { font-weight: 700; font-size: 1.2rem; color: #1D1D1F !important; font-family: inherit; }
[data-testid="stMetricLabel"] { color: #6E6E73 !important; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; }
[data-testid="stMetricDelta"] { color: #444444 !important; }

/* ---- Alerts / info / warning / error boxes ---- */
[data-testid="stAlert"] {
    border-radius: 6px !important;
    background: #F8F8F8 !important;
}
[data-testid="stAlert"] *,
[data-baseweb="notification"] * { color: #1D1D1F !important; }

/* ---- Chat messages ---- */
[data-testid="stChatMessage"] {
    background: #F8F8F8 !important;
    border: 1px solid #E8E8E8 !important;
    border-radius: 6px !important;
    margin-bottom: 0.4rem !important;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    background: #FFF5EC !important;
    border-color: #FFD9B3 !important;
}
[data-testid="stChatMessage"] * { color: #1D1D1F !important; }

/* ---- Captions / small text ---- */
.stCaption, small,
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] * { color: #8E8E93 !important; font-size: 0.78rem; }

/* ---- Toast ---- */
[data-testid="stToast"],
[data-testid="stToast"] * { background: #FFFFFF !important; color: #1D1D1F !important; }

/* ---- Spinner ---- */
[data-testid="stSpinner"] * { color: #1D1D1F !important; }

/* ---- Form container ---- */
[data-testid="stForm"] { border-color: #D8D8D8 !important; background: transparent !important; }

/* ---- DataFrames ---- */
[data-testid="stDataFrame"] { border-radius: 6px; overflow: hidden; border: 1px solid #D8D8D8; background: #FFFFFF !important; }

/* ---- File uploader (Settings → Import) ---- */
[data-testid="stFileUploader"] section,
[data-testid="stFileUploaderDropzone"] {
    background: #F6F3EC !important;
    border: 1px dashed #CFC8BA !important;
    color: #1D1D1F !important;
}
[data-testid="stFileUploader"] section *,
[data-testid="stFileUploaderDropzone"] * { color: #1D1D1F !important; }
[data-testid="stFileUploaderDropzoneInstructions"] span,
[data-testid="stFileUploaderDropzoneInstructions"] small { color: #4A4A4E !important; }
[data-testid="stFileUploaderFile"] { background: #FFFFFF !important; }
[data-testid="stFileUploaderFile"] * { color: #1D1D1F !important; }
/* the "Browse files" button inside the uploader (Streamlit renders it dark) */
[data-testid="stFileUploader"] button {
    background: #FFFFFF !important;
    border: 1px solid #D0D0D0 !important;
    color: #1D1D1F !important;
}
[data-testid="stFileUploader"] button * { color: #1D1D1F !important; }
[data-testid="stFileUploader"] button:hover {
    border-color: #E87D0D !important;
    color: #E87D0D !important;
}
[data-testid="stFileUploader"] button:hover * { color: #E87D0D !important; }

/* ---- Popover trigger buttons (e.g. the Q / A colour pickers on turn cards) ---- */
[data-testid="stPopover"] button {
    background: #FFFFFF !important;
    border: 1px solid #D0D0D0 !important;
    color: #1D1D1F !important;
}
[data-testid="stPopover"] button * { color: #1D1D1F !important; }
[data-testid="stPopover"] button:hover {
    border-color: #E87D0D !important;
    color: #E87D0D !important;
}
[data-testid="stPopover"] button:hover * { color: #E87D0D !important; }

/* ---- Sidebar nav radio ---- */
[data-testid="stRadio"] > div { gap: 4px !important; }
[data-testid="stRadio"] label { padding: 6px 10px !important; border-radius: 6px !important; }
[data-testid="stRadio"] label:hover { background: #EBEBEB !important; }

/* ---- Scrollbar ---- */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #F5F5F7; }
::-webkit-scrollbar-thumb { background: #D0D0D0; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #E87D0D; }

/* ---- Code / pre ---- */
code { background: #F0F0F0 !important; color: #B85000 !important; border: 1px solid #D8D8D8; border-radius: 2px; padding: 1px 5px; font-size: 0.85em; }
pre { background: #F0F0F0 !important; border: 1px solid #D8D8D8 !important; border-radius: 6px !important; }
pre * { color: #1D1D1F !important; }

/* ---- Markdown tables ---- */
thead tr th { background: #F0F0F0 !important; color: #6E6E73 !important; font-size: 0.75rem !important; text-transform: uppercase; letter-spacing: 0.06em; border-bottom: 1px solid #D8D8D8 !important; }
tbody tr td { border-bottom: 1px solid #E8E8E8 !important; color: #1D1D1F !important; font-size: 0.85rem; }
tbody tr:hover td { background: #F5F5F7 !important; }

/* ---- Dividers ---- */
hr { border-color: #D8D8D8 !important; }

/* ---- Number input buttons ---- */
[data-testid="stNumberInput"] button { background: #F0F0F0 !important; border-color: #D8D8D8 !important; color: #555555 !important; }

/* ---- Rejudge pulse animation ---- */
@keyframes rj-pulse { 0%,100% { opacity:1; } 50% { opacity:0.3; } }

/* ---- Slim header: hide toolbar/decoration, collapse header height ---- */
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
#MainMenu { display: none !important; }
header[data-testid="stHeader"] {
    height: 0 !important;
    min-height: 0 !important;
    overflow: visible !important;
    background: transparent !important;
    pointer-events: none !important;
}
/* Sidebar always visible — hide the collapse/expand toggle entirely */
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapseButton"] { display: none !important; }
section[data-testid="stSidebar"] { display: flex !important; visibility: visible !important; }
.main .block-container,
[data-testid="stMainBlockContainer"],
.stMainBlockContainer,
section.main > div.block-container { padding-top: 0.25rem !important; padding-bottom: 1rem !important; }
</style>
"""
