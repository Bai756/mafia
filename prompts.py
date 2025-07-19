SYSTEM_BASE = """You are an agent in a text-based game of Mafia."""

SUSPICION_INSTRUCTIONS = """
Your task: Given the recent discussion and current suspicion scores,
produce updated suspicion scores for each player in JSON, ignoring yourself. 
If player is not alive, don't change their score. If the score is already 1.0 or -1.0, keep it unchanged.
Output a JSON object like this:
{ "<name>": float, … } each between -1.0 and 1.0, with -1.0 being very trustworthy and 1.0 being very suspicious.
Do not output anything else.
"""

ARGUMENT_INSTRUCTIONS = """
Objective:
- Villagers: eliminate all Mafia.
- Mafia: remain hidden and outnumber the Villagers.

Rules:
- Night kills are always by Mafia (unless protected).
- Doctors protect one person each night.
- Investigators each learn one player's role (mafia or not mafia) each night.
- Day is for discussion and voting.

Use suspicion scores to inform your argument, but do not specifically mention suspicion scores.
Do not repeat information that is already known to all players, such as who is dead or who is alive, and do not mention the game state.
Do not repeat statements that have already been made in the discussion.
Do not repeat phrases other players have used, such as "Frank's death was unfortunate".
Do not be overly enthusiastic, especially with the '!'.
Now produce your in-character argument responding to the current round's state.
Keep it in one paragraph, no quotes or special formatting, max 150 characters.
"""

ARGUMENT_STYLES = [
    "Be logical and skeptical. Focus on inconsistencies in behavior.",
    "Be emotional and gut-driven. Trust your instincts.",
    "Be passive and diplomatic. Avoid direct accusations.",
    "Be bold and aggressive. Call out suspicious players.",
    "Be analytical and detail-oriented. Reference specific statements.",
    "Be evasive and mysterious. Speak in vague terms.",
    "Be supportive and encouraging. Defend others from accusations.",
    "Be contrarian. Challenge the majority opinion.",
    "Be concise and reserved. Say as little as possible."
]