from backend.services.simulator import DONE_TOKEN, parse_simulator_text


def test_no_done_token():
    text, done = parse_simulator_text("Hello, can you help me?")
    assert text == "Hello, can you help me?"
    assert done is False


def test_done_token_on_own_line():
    raw = f"Great, thanks for your help!\n{DONE_TOKEN}"
    text, done = parse_simulator_text(raw)
    assert text == "Great, thanks for your help!"
    assert done is True


def test_done_token_inline():
    raw = f"Awesome. {DONE_TOKEN}"
    text, done = parse_simulator_text(raw)
    assert text == "Awesome."
    assert done is True


def test_only_done_token():
    text, done = parse_simulator_text(DONE_TOKEN)
    assert text == ""
    assert done is True


def test_empty_input():
    text, done = parse_simulator_text("")
    assert text == ""
    assert done is False


def test_whitespace_around_token():
    raw = f"Thanks!\n\n  {DONE_TOKEN}  \n"
    text, done = parse_simulator_text(raw)
    assert text == "Thanks!"
    assert done is True
