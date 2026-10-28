"""Keeps the bot's instructions to data/SOUL.md. Hermes is a general-purpose agent and adds blocks
written for its own users after SOUL.md. Users then heard about them: "I run on Hermes Agent by Nous
Research", "powered by GLM", its folders. config.yaml switches off the blocks Hermes has settings for
(agent: and platform_hints:); this removes the five it has none for: where Hermes' docs are, how
Hermes delivers mid-answer messages (here they wait their turn instead), the active profile and its
folders, the model and provider, and the host's OS and folders.
Written against the pinned Hermes v0.22.5. If a name moved in an upgrade, register() fails and
Hermes logs it, so check `docker logs` after changing the image.
"""
import agent.prompt_builder as prompt_builder
import agent.system_prompt as system_prompt

_timestamp_line = system_prompt._timestamp_line


def _date_only(agent):
    """The 'Conversation started' line Hermes keeps checking for, without its Model:/Provider: lines."""
    return "\n".join(line for line in _timestamp_line(agent).split("\n")
                     if not line.startswith(("Model: ", "Provider: ")))


def register(ctx):
    # Empty parts are dropped when the prompt is joined.
    system_prompt.HERMES_AGENT_HELP_GUIDANCE_NO_SKILLS = ""
    system_prompt.HERMES_AGENT_HELP_GUIDANCE = ""
    system_prompt.STEER_CHANNEL_NOTE = ""
    system_prompt._active_profile_line = lambda agent: ""
    system_prompt._timestamp_line = _date_only
    prompt_builder.build_environment_hints = lambda: ""
