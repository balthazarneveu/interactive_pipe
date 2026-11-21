from interactive_pipe.graphical.gradio_control import template_text


def test_template_text_neutralises_markup_and_template_code():
    name = '<img src=x onerror=alert(1)> ${document.cookie} `x` \\u0041 & "q"'
    text = template_text(name)
    for forbidden in ("<", ">", "${", "`", "\\", '"'):
        assert forbidden not in text
    assert text.startswith("&lt;img")


def test_template_text_keeps_plain_names():
    assert template_text("gain_db") == "gain_db"
