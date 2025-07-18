import random
import json
import openai
import requests
import os
from dotenv import load_dotenv
from memory import AgentMemory
from prompts import SYSTEM_BASE, SUSPICION_INSTRUCTIONS, ARGUMENT_INSTRUCTIONS

load_dotenv()
API_KEY = os.getenv("API_KEY")
openai.api_key = API_KEY

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
        
        messages = [
            {"role": "system", "content": SYSTEM_BASE},
            {"role": "user", "content": SUSPICION_INSTRUCTIONS},
            {"role": "user", "content": f"Your name: {self.name}"},
            {"role": "user", "content": f"Your role: {self.role}. {"Fellow Mafia: " + ', '.join(p.name for p in alive_players if p.role == "Mafia" and p != self) + "." if self.role == "Mafia" else ""}"},
            {"role": "user", "content": f"Alive Players: {alive_players}"},
            {"role": "user", "content": f"Current scores: {self.suspicions}"},
            {"role": "user", "content": f"Discussion:\n{history_str}"}
        ]

        new_suspicions = self.call_api(messages)
        new_suspicions = json.loads(new_suspicions)

        for player_name, score in new_suspicions.items():
            self.suspicions[player_name] = score
        
        if self.role == "Mafia":
            for player in game_manager.players:
                if player.role == "Mafia" and player != self:
                    self.suspicions[player.name] = 1.0

        if self.name in self.suspicions:
            del self.suspicions[self.name]
                
    def generate_argument(self, game_manager):
        alive_players = game_manager.get_alive_players()
        players_list = ', '.join(p.name for p in alive_players)
        deaths = game_manager.last_deaths
        deaths_list = ', '.join(f"{p.name} (killed by Mafia)" for p in deaths) if deaths else 'None'
        history = game_manager.discussion_history.get(game_manager.round_number, [])
        history_str = '\n'.join(f"{s}: {l}" for s, l in history) or "No discussion yet."
        mafia_names = ', '.join(p.name for p in alive_players if p.role == "Mafia" and p != self)
        number_of_mafia = sum(1 for p in alive_players if p.role == "Mafia")

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
            fellow_mafia = [p.name for p in alive_players if p.role == "Mafia" and p != self]
            try:
                # Be defensive here too
                if hasattr(game_manager, 'last_targeted') and game_manager.last_targeted:
                    kill_names = [p.name for _, p in game_manager.last_targeted]
                    if kill_names:
                        mem += "- Mafia kills last night: " + ', '.join(kill_names)
            except AttributeError:
                mem += "- No mafia kills recorded yet."
        
        messages = [
            {"role": "system", "content": SYSTEM_BASE},
            {"role": "user",   "content": ARGUMENT_INSTRUCTIONS},
            {"role": "user",   "content": f"Your role: {self.role}, Your name: {self.name}, {"Fellow Mafia: " + ", ".join(fellow_mafia) + "." if self.role == "Mafia" else ""}"},
            {"role": "user",   "content": f"Alive: {alive_players}"},
            {"role": "user",   "content": f"Last deaths: {deaths}"},
            {"role": "user",   "content": f"Last voted out: {game_manager.last_voted_out.name} was a {game_manager.last_voted_out.role}." if game_manager.last_voted_out else "None"},
            {"role": "user",   "content": f"Last actions taken: {mem or 'None'}"},
            {"role": "user",   "content": f"Suspicion scores: {self.suspicions}"},
            {"role": "user",   "content": f"Round: {game_manager.round_number}"},
            {"role": "user",   "content": f"Discussion: {history_str}"}
        ]

        return self.call_api(messages)

    def call_api(self, messages):
        # payload = {
        #     "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        #     "messages": messages,
        #     "temperature": 0.4,
        #     "max_tokens": 128,
        #     "stop": ["\n\n"]
        # }

        # resp = requests.post(
        #     "https://api.groq.com/openai/v1/chat/completions",
        #     headers={
        #         "Content-Type": "application/json",
        #         "Authorization": f"Bearer {API_KEY}"
        #     },
        #     json=payload,
        #     timeout=30
        # )
        # resp.raise_for_status()
        # data = resp.json()

        # return data["choices"][0]["message"]["content"].strip()

        return call_chatgpt(messages)

def call_chatgpt(messages):
    response = openai.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        temperature=0.4,
        max_tokens=128,
        stop=["\n\n"]
    )

    return response.choices[0].message.content.strip()