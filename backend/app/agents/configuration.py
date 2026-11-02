from typing import Literal

from app.schemas import Input


class AgentConfiguration(Input):
    agent_count: Literal[2, 3, 5] = 5
    architecture: Literal["blackboard", "direct"] = "blackboard"
    prompt_strategy: Literal["react", "few_shot"] = "react"

    @property
    def roles(self) -> tuple[str, ...]:
        return {
            2: ("generalist",),
            3: ("account_card", "loan_support"),
            5: ("account", "card", "loan", "support"),
        }[self.agent_count]


DEFAULT_CONFIGURATION = AgentConfiguration()
