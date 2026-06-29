"""Stop-condition precedence tests for the runner.

The spec mandates this order:
    1. endpoint_error (HTTP error after retries exhausted)
    2. endpoint_signaled_end (end_flag extracted and truthy)
    3. goal_achieved (simulator returned <<<DONE>>>)
    4. max_turns (turn_number >= max_turns)
    5. cost_cap (cost exceeds configured cap)
"""

from backend.services.runner import decide_stop


def _kwargs(**overrides):
    base = dict(
        endpoint_error=False,
        end_flag_truthy=False,
        simulator_done=False,
        turn_number=1,
        max_turns=10,
        cost_so_far=0.0,
        cost_cap=None,
    )
    base.update(overrides)
    return base


def test_endpoint_error_wins_over_everything():
    d = decide_stop(
        **_kwargs(
            endpoint_error=True,
            end_flag_truthy=True,
            simulator_done=True,
            turn_number=10,
            max_turns=10,
            cost_so_far=999.0,
            cost_cap=1.0,
        )
    )
    assert d.stop is True
    assert d.reason == "endpoint_error"


def test_endpoint_signaled_end_beats_done_and_max_turns():
    d = decide_stop(
        **_kwargs(
            end_flag_truthy=True,
            simulator_done=True,
            turn_number=10,
            max_turns=10,
        )
    )
    assert d.stop is True
    assert d.reason == "endpoint_signaled_end"


def test_goal_achieved_beats_max_turns():
    d = decide_stop(
        **_kwargs(
            simulator_done=True,
            turn_number=10,
            max_turns=10,
        )
    )
    assert d.stop is True
    assert d.reason == "goal_achieved"


def test_max_turns_when_nothing_else_triggers():
    d = decide_stop(**_kwargs(turn_number=10, max_turns=10))
    assert d.stop is True
    assert d.reason == "max_turns"


def test_max_turns_when_exceeded():
    d = decide_stop(**_kwargs(turn_number=11, max_turns=10))
    assert d.stop is True
    assert d.reason == "max_turns"


def test_cost_cap_triggers_when_lower_conditions_clear():
    d = decide_stop(
        **_kwargs(
            turn_number=2,
            max_turns=10,
            cost_so_far=1.5,
            cost_cap=1.0,
        )
    )
    assert d.stop is True
    assert d.reason == "cost_cap"


def test_no_stop_in_happy_middle():
    d = decide_stop(**_kwargs(turn_number=2, max_turns=10, cost_so_far=0.1, cost_cap=1.0))
    assert d.stop is False
    assert d.reason is None


def test_cost_cap_does_not_beat_endpoint_signaled_end():
    d = decide_stop(
        **_kwargs(
            end_flag_truthy=True,
            turn_number=2,
            max_turns=10,
            cost_so_far=99.0,
            cost_cap=1.0,
        )
    )
    assert d.reason == "endpoint_signaled_end"


def test_cost_cap_none_disabled():
    d = decide_stop(**_kwargs(cost_so_far=10_000, cost_cap=None, turn_number=2, max_turns=10))
    assert d.stop is False
