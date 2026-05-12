from app_ui import theme


def test_theme_helpers_import_and_expose_system_name():
    assert "Part-Time Lecturer Claims" in theme.SYSTEM_NAME
    assert callable(theme.apply_app_theme)
    assert callable(theme.render_app_header)
    assert callable(theme.render_sidebar_user)
    assert callable(theme.render_status_badge)


def test_theme_css_avoids_broad_global_white_text_selectors():
    source = theme.apply_app_theme.__code__.co_consts
    css = "\n".join(str(value) for value in source if isinstance(value, str))

    assert '* {\n            color: #f8fafc' not in css
    assert '[data-testid="stSidebar"] *' not in css
    assert ".stApp {\n            background: var(--pt-bg);\n            color: var(--pt-charcoal);" in css
    assert "div[data-testid=\"stMetric\"] [data-testid=\"stMetricValue\"]" in css
    assert "--pt-charcoal: #111827" in css
    assert "--pt-muted: #6b7280" in css


def test_theme_css_keeps_buttons_and_inputs_readable():
    source = theme.apply_app_theme.__code__.co_consts
    css = "\n".join(str(value) for value in source if isinstance(value, str))

    assert ".stFormSubmitButton > button" in css
    assert "button[data-testid=\"baseButton-primary\"]" in css
    assert "div[data-baseweb=\"input\"] input" in css
    assert "background-color: #ffffff !important" in css
    assert "-webkit-text-fill-color: var(--pt-charcoal)" in css
    assert "caret-color: var(--pt-charcoal)" in css
    assert "input::placeholder" in css
    assert "div[data-baseweb=\"select\"] *" in css
    assert "div[data-baseweb=\"popover\"]" in css
    assert "div[data-baseweb=\"menu\"]" in css
    assert "div[role=\"listbox\"]" in css
    assert "div[role=\"option\"]" in css
    assert "div[data-baseweb=\"input\"] svg" in css
    assert "fill: var(--pt-secondary)" in css
    assert "stroke: var(--pt-secondary)" in css
    assert ".stButton > button *" in css
    assert ".stDownloadButton > button" in css
    assert "div[data-testid=\"stDownloadButton\"] > button" in css
    assert "div[data-testid=\"stLinkButton\"] a" in css
    assert "-webkit-text-fill-color: #ffffff" in css
    assert "div[data-testid=\"stCodeBlock\"]" in css
    assert ".pt-file-path" in css
    assert ".pt-file-path-meta" in css
    assert "overflow-wrap: anywhere" in css
