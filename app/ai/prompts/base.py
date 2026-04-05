def render_template(template: str, variables: dict[str, str]) -> str:
    rendered = template

    for key, value in variables.items():
        rendered = rendered.replace(f"{{{{ {key} }}}}", value)

    return rendered