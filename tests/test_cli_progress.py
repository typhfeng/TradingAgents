from cli.main import (
    ANALYST_AGENT_NAMES,
    DISPLAY_AGENT_TEAMS,
    first_selected_analyst_agent,
)


def test_display_agent_teams_cover_all_selectable_analysts():
    displayed_agents = {
        agent
        for agents in DISPLAY_AGENT_TEAMS.values()
        for agent in agents
    }

    assert set(ANALYST_AGENT_NAMES.values()).issubset(displayed_agents)


def test_first_selected_analyst_agent_uses_execution_order():
    assert first_selected_analyst_agent(["leap", "market"]) == "Market Analyst"
    assert first_selected_analyst_agent(["leap"]) == "Leap Analyst"
