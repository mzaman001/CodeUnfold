"""Static CSS for CodeUnfold's Streamlit UI, split out of main.py so the
~70 lines of pure styling don't obscure the app's actual control flow.
Nothing here depends on session state or runtime values -- the dynamic
theme colors (AMOLED vs Deep Dark) are still injected separately in
main.py, since those genuinely depend on session state.
"""

BASE_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500&family=Inter:wght@400;500;600&display=swap');

    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: #475569; }
    ::selection { background: rgba(245, 158, 11, 0.3); color: #f8fafc; }
    section.main { overflow-anchor: none !important; }

    /* Typography Hierarchy */
    h1, h2, h3, p, li, label { font-family: 'Inter', -apple-system, sans-serif !important; }

    .stTextArea textarea {
        background-color: #1e293b !important; border: 2px solid #334155 !important;
        color: #f8fafc !important; font-family: 'Fira Code', monospace !important;
        border-radius: 12px !important; padding: 16px !important; font-size: 14px !important;
        transition: all 0.3s ease !important; box-shadow: none !important;
    }
    .stTextArea textarea:focus { border-color: #f59e0b !important; box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.1) !important; }
    
    [data-testid="stExpander"] { background: #1e293b !important; border: 1px solid #334155 !important; border-radius: 12px !important; margin-bottom: 12px !important; }
    [data-testid="stExpander"] summary { font-family: 'Inter', sans-serif !important; font-weight: 600 !important; color: #f8fafc !important; }
    
    .stButton > button { border-radius: 12px !important; padding: 12px 32px !important; font-weight: 600 !important; border: none !important; transition: all 0.2s ease !important; }
    .stButton > button[kind="primary"] { background: linear-gradient(135deg, #f59e0b, #f97316) !important; color: #000 !important; box-shadow: 0 4px 12px rgba(245, 158, 11, 0.3) !important; }
    .stButton > button[kind="primary"]:hover { transform: translateY(-1px) !important; box-shadow: 0 6px 16px rgba(245, 158, 11, 0.4) !important; }
    .stButton > button[kind="secondary"] { background: rgba(59, 130, 246, 0.1) !important; border: 1px solid rgba(59, 130, 246, 0.3) !important; color: #93c5fd !important; }
    
    [data-testid="stChatMessage"] { background: #1e293b !important; border: 1px solid #334155 !important; border-left: 4px solid #f59e0b !important; border-radius: 12px !important; padding: 24px !important; box-shadow: none !important; margin-bottom: 16px !important; }
    [data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) { border-left-color: #64748b !important; }
    
    pre { background: #0f172a !important; border: 1px solid #334155 !important; border-radius: 8px !important; padding: 20px !important; }
    pre code { font-family: 'Fira Code', monospace !important; font-size: 13px !important; color: #f8fafc !important; }
    
    section[data-testid="stSidebar"] { background: #0f172a !important; border-right: 1px solid #334155 !important; }

    /* Animated Spinners */
    @keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 1; } }
    .stSpinner > div > div > div { animation: pulse 1.5s ease-in-out infinite !important; }

    /* Typography Hierarchy */
    .markdown-text-container h2 {
        border-left: 4px solid #f59e0b !important;
        padding-left: 12px !important;
        background: rgba(245, 158, 11, 0.05);
        padding-top: 4px !important;
        padding-bottom: 4px !important;
        margin-top: 2rem !important;
        margin-bottom: 1rem !important;
        font-size: 1.4rem !important;
    }
    .markdown-text-container h3 {
        font-family: 'Fira Code', monospace !important;
        font-size: 1.2rem !important;
        color: #e2e8f0 !important;
        margin-top: 1.5rem !important;
        margin-bottom: 0.8rem !important;
    }

    /* Mobile Responsive */
    @media (max-width: 768px) {
        [data-testid="stHorizontalBlock"] { flex-direction: column !important; }
        [data-testid="stChatMessage"] { padding: 12px 16px !important; }
        .stTextArea textarea { min-height: 100px !important; }
    }
</style>
"""


def theme_css(bg_color: str, sidebar_bg: str) -> str:
    """Builds the small dynamic-theme CSS block (AMOLED vs Deep Dark).

    Kept separate from BASE_CSS because these two colors genuinely
    depend on session state (`st.session_state.theme`), unlike
    everything else in this file.
    """
    return f"""
<style>
    .stApp {{ background-color: {bg_color} !important; transition: background-color 0.3s; }}
    section[data-testid="stSidebar"] {{ background-color: {sidebar_bg} !important; border-right: 1px solid #1a1a24 !important; }}
</style>
"""
