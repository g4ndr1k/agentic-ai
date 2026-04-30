from agent.app.rules import ACTIVE_ACTIONS


def test_phase4c1_mutation_actions_are_rule_visible():
    assert {
        "move_to_folder",
        "mark_read",
        "mark_unread",
        "mark_flagged",
        "unmark_flagged",
    }.issubset(ACTIVE_ACTIONS)
