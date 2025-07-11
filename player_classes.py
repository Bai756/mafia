import random
import json
import requests
import os
from memory import AgentMemory


class Player:
    def __init__(self, role, name):
        self.role = role
        self.name = name
        self.is_alive = True
        self.is_protected = False

    def vote(self, target):
        # Record a vote. Note that vote will always refer to a player class object
        print(f"{self.name} ({self.role}) votes {target.name} ({target.role})")
        return target


class Human_Player(Player):
    def __init__(self, name):
        super().__init__("Villager", name)

    def vote(self, game_manager, valid_targets=None):
        # Prompt user to select a valid target by name
        if valid_targets is None:
            valid_targets = [p for p in game_manager.get_alive_players() if p.is_alive and p != self]
        while True:
            target_name = input("Enter the name of the player to vote: ").strip().lower()
            target = next((p for p in valid_targets if p.name.lower() == target_name and p.is_alive and p != self), None)
            if target:
                return super().vote(target)
            else:
                print("Invalid name.")
    
    def generate_argument(self, _game_manager):
        print(f"{self.name}, it's your turn to speak.")
        argument = input("Type your argument: ")
        return argument


class AI_Player(Player):
    def __init__(self, name):
        super().__init__("Villager", name)
        self.suspicions = {} # Key values will be the name of another player
        self.memory = AgentMemory(max_size=100, embed_dim=32)

    def vote(self, game_manager, valid_targets=None):
        if not game_manager.use_model:
            # If not using model, use old voting logic
            if game_manager.get_game_phase() == "night":
                if self.role == "Mafia":
                    if valid_targets is None:
                        valid_targets = [p for p in game_manager.get_alive_players() if p != self and p.role != "Mafia"]
                    return self._vote_mafia(valid_targets)
                elif self.role == "Doctor":
                    if valid_targets is None:
                        valid_targets = [p for p in game_manager.get_alive_players() if p != self]
                    return self._vote_doctor(valid_targets)
                elif self.role == "Investigator":
                    if valid_targets is None:
                        valid_targets = [p for p in game_manager.get_alive_players() if p != self and p not in game_manager.already_investigated]
                    if not valid_targets:
                        valid_targets = [p for p in game_manager.get_alive_players() if p != self]
                    return self._vote_investigator(valid_targets)
            else:
                if valid_targets is None:
                    valid_targets = [p for p in game_manager.get_alive_players() if p != self]
                if game_manager.revote:
                    valid_targets = [p for p in valid_targets if p in game_manager.revote]

                if self.role == "Mafia":
                    return self._vote_mafia(valid_targets)
                else:
                    return self._vote_most_suspicious(valid_targets)

        obs = game_manager.get_observation(self)
        action = game_manager.model.get_action(obs, self.role)
        target = game_manager.players[action]

        if not valid_targets:
            valid_target_idx = obs[-len(game_manager.players):]
            if valid_target_idx[action] == 0:
                valid_targets = [p for p in game_manager.get_alive_players() if p != self]
                if self.role == "Mafia":
                    valid_targets = [p for p in valid_targets if p.role != "Mafia"]
                return self._vote_most_suspicious(valid_targets)
        else:
            valid_target_idx = [1 if p in valid_targets else 0 for p in game_manager.players]
            if valid_target_idx[action] == 0:
                return self._vote_most_suspicious(valid_targets)
            
        return super().vote(target)
    
    def _vote_mafia(self, eligible_targets): # Mafia already have eligible targets filtered
        # Vote for the least suspicious alive target
        min_suspicion = min(self.suspicions.get(p.name, 0) for p in eligible_targets)
        least_suspicious = [p for p in eligible_targets if self.suspicions.get(p.name, 0) == min_suspicion]
        return super().vote(random.choice(least_suspicious))
    
    def _vote_doctor(self, alive_targets):
        # Vote for the least suspicious alive target to protect
        eligible_targets = [p for p in alive_targets if p != self]
        min_suspicion = min(self.suspicions.get(p.name, 0) for p in eligible_targets)
        least_suspicious = [p for p in eligible_targets if self.suspicions.get(p.name, 0) == min_suspicion]
        return super().vote(random.choice(least_suspicious))

    def _vote_investigator(self, alive_targets):
        # Vote for the most suspicious alive target not confirmed to be mafia to investigate
        eligible_targets = [p for p in alive_targets if p != self]
        eligible_targets = [p for p in eligible_targets if self.suspicions.get(p.name, 0) < 1.0]
        max_suspicion = max(self.suspicions.get(p.name, 0) for p in eligible_targets)
        most_suspicious = [p for p in eligible_targets if self.suspicions.get(p.name, 0) == max_suspicion]
        return super().vote(random.choice(most_suspicious))
    
    def _vote_most_suspicious(self, alive_targets):
        eligible_targets = [p for p in alive_targets if p != self]
        max_suspicion = max(self.suspicions.get(p.name, 0) for p in eligible_targets)
        most_suspicious = [p for p in eligible_targets if self.suspicions.get(p.name, 0) == max_suspicion]
        return super().vote(random.choice(most_suspicious))

    def initialize_suspicion_meter(self, players):
        for player in players:
            if player != self:
                self.suspicions[player.name] = 0.0

    def update_suspicion_investigation(self, target, is_mafia):
        if is_mafia:
            self.suspicions[target.name] = 1.0
        else:
            self.suspicions[target.name] = -1.0
    
    def update_suspicion(self, game_manager):
        history = game_manager.discussion_history.get(game_manager.round_number, [])
        history_str = '\n'.join(f"{s}: {l}" for s, l in history) or "No discussion yet."
        alive_players = [p for p in game_manager.get_alive_players() if p.is_alive and p != self]
        prompt = f"""
            You are an assistant helping a member in a game of Mafia.
            There are mafia, villagers, doctors, and investigators.
            You are an AI player named {self.name} with the role of {self.role}.
            {"The other mafia members are " + ', '.join(p.name for p in alive_players if p.role == "Mafia" and p != self) + "." if self.role == "Mafia" else ""}
            Based on the recent discussion, assign suspicion scores to each alive player (excluding the speaker).
            The players are:
            {', '.join(p.name for p in alive_players)}

            Current suspicion scores:
            {self.suspicions}

            Your task is to update the suspicion scores based on the recent discussion.
            Each score should be:
            -1.0 (completely innocent) to 1.0 (completely Mafia)
            If scores are already -1.0 or 1.0, do not change them.
            Do not remove any players from the suspicion scores, even if they are not mentioned in the discussion.

            Recent discussion:
            {history_str}

            Return as JSON like:
            {{ "Alice": 0.3, "Bob": -0.2 }}
            Do not include any other text or formatting.
            """
        new_suspicions = self.call_api(prompt)
        new_suspicions = json.loads(new_suspicions)

        for player_name, score in new_suspicions.items():
            self.suspicions[player_name] = score
        
        if self.role == "Mafia":
            for player in game_manager.players:
                if player.role == "Mafia" and player != self:
                    self.suspicions[player.name] = 1.0

        if self.name in self.suspicions:
            del self.suspicions[self.name]
            
        print(f"{self.name} updated suspicion scores: {self.suspicions}")
    
    def generate_argument(self, game_manager):
        alive = game_manager.get_alive_players()
        players_list = ', '.join(p.name for p in alive)
        deaths = game_manager.last_deaths
        deaths_list = ', '.join(f"{p.name} (killed by Mafia)" for p in deaths) if deaths else 'None'
        history = game_manager.discussion_history.get(game_manager.round_number, [])
        history_str = '\n'.join(f"{s}: {l}" for s, l in history) or "No discussion yet."
        mafia_names = ', '.join(p.name for p in alive if p.role == "Mafia" and p != self)
        number_of_mafia = sum(1 for p in alive if p.role == "Mafia")

        # Create memory of recent actions based on role
        mem = ""
        if self.role == "Doctor":
            try:
                # Find who this doctor protected, if anyone
                doctor_actions = [(doctor, p) for doctor, p in game_manager.last_protected if doctor.name == self.name]
                if doctor_actions:
                    protected = doctor_actions[0][1]  # Get the protected player
                    status = 'survived' if protected.is_alive else 'died'
                    mem = f"- You protected: {protected.name} ({status})"
            except (AttributeError, IndexError):
                mem = "- You haven't protected anyone yet."

        elif self.role == "Investigator":
            try:
                # Similar defensive coding for investigator
                investigations = [(name, is_mafia) for investigator, name, is_mafia 
                                 in game_manager.last_investigated if investigator.name == self.name]
                if investigations:
                    name, is_mafia = investigations[0]
                    result = "Mafia" if is_mafia else "not Mafia"
                    mem += f"- You investigated: {name} ({result})"
            except (AttributeError, IndexError):
                mem += "- You haven't investigated anyone yet."

        elif self.role == "Mafia":
            try:
                # Be defensive here too
                if hasattr(game_manager, 'last_targeted') and game_manager.last_targeted:
                    kill_names = [p.name for _, p in game_manager.last_targeted]
                    if kill_names:
                        mem += "- Mafia kills last night: " + ', '.join(kill_names)
            except AttributeError:
                mem += "- No mafia kills recorded yet."
    
        prompt = f"""
            You are {self.name}, a {self.role} in a text-based Mafia game.
            {f"The other mafia members are {mafia_names}." if self.role == "Mafia" else ""}

            Objective:
            - Villagers: eliminate all Mafia.
            - Mafia: remain hidden and outnumber the Villagers.

            Rules:
            - Night kills are always by Mafia (unless protected).
            - Doctors protect one person each night.
            - Investigators each learn one player's role (mafia or not mafia) each night.
            - Day is for discussion and voting.

            Game State:
            Alive players: {players_list}
            Last night’s deaths: {deaths_list}
            Suspicion scores: {self.suspicions} (This is your suspicions of other players based on previous discussions and actions.)
            The current round is {game_manager.round_number}.
            {f"IMPORTANT!! This discussion is about a revote because of a tie." if game_manager.revote else ""}
            {f"The people in the revote are: {', '.join(p.name for p in game_manager.revote)}." if game_manager.revote else ""}

            Your recent role actions:
            {mem or '- None'}
            There are {number_of_mafia} Mafia members remaining. So, if that many people died last night, then all the mafia kills were successful. Each Mafia member kills one person each night.

            Current round discussion:
            {history_str}

            Instructions:
            - Do NOT repeat lines verbatim or recycle phrases. Do NOT just copy other players and say the same thing over and over again.
            - Do NOT refer to events that never happened.
            - Do NOT mention AI, “the game,” real-world topics, or anything that happened outside of the game.
            - Do NOT speak in third person about yourself.
            - Do NOT mention anything previous interactions that never actually happened.
            - Do NOT mention seeing each other at night because that doesn't happen (mafia just votes to kill and so forth).
            - Do NOT claim that you interacted with other players in any way that is not true or that you interacted with players during the night. You only interact during the discussion.
            - Do NOT mourn the death or say anything like that because this is just a game.
            - Reason about the game state and your role and what you should be doing.
            - {"Do NOT reveal your kill or accuse fellow Mafia." if self.role == "Mafia" else ""}
            - {"You play the role of the Doctor, so you can protect one player each night. You are not a actual doctor saving lives. You just help prevent mafia from killing someone." if self.role == "Doctor" else ""}
            - {"You play the role of the Doctor, you know who you chose to protect last night. If the protected player is alive and the number of deathes is less than the number of mafia, then you successfully protected someone. Otherwise, the person you protected was not targeted by the mafia last night." if self.role == "Doctor" else ""}
            - Do NOT use any special formatting like "Name: Argument", do not use quotes either.
            - Just write your argument as a single paragraph without any formatting (couple of sentences).
            - Do NOT say suspicion score or score. Do NOT say low score or high score; just say that you are suspicious of someone or that you trust someone.
            - Do NOT say your inner thoughts outloud, say your argument as you are speaking to the other players.
            - Do NOT accuse others of being quiet or not participating if the discussion just started.

            Now, based on the above, make a new in-character statement responding to the discussion and recent events. Max 200 characters.
            """

        # response = requests.post(
        #     'http://localhost:11434/api/generate',
        #     json={'model': 'mistral', 'prompt': prompt, 'temperature': 0.4}
        # )

        # text = ""
        # for line in response.text.splitlines():
        #     try:
        #         data = json.loads(line)
        #         text += data.get("response", "")
        #     except Exception:
        #         continue
        # return text.strip()

        return self.call_api(prompt)

    def call_api(self, prompt):
        payload = {
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": [
                {"role": "system", "content": "You are a role-playing agent in a Mafia game. Respond strictly in character."},
                {"role": "user",   "content": prompt}
            ],
            "temperature": 0.4,
            "max_tokens": 128,
            "stop": ["\n\n"]
        }

        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"
            },
            json=payload,
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()

        return data["choices"][0]["message"]["content"].strip()
