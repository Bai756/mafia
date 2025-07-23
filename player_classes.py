import random
import json
import openai
import requests
import os
from dotenv import load_dotenv
from memory import AgentMemory
from prompts import SYSTEM_BASE, SUSPICION_INSTRUCTIONS, ARGUMENT_INSTRUCTIONS, ARGUMENT_STYLES
import logging
import time
from datetime import datetime

# load_dotenv()
# API_KEY1 = os.getenv("API_KEY1")
# API_KEY2 = os.getenv("API_KEY2")
# API_KEY3 = os.getenv("API_KEY3")
# API_KEY4 = os.getenv("API_KEY4")
# API_KEYS = [API_KEY1, API_KEY2, API_KEY3, API_KEY4]
# API_KEY = os.getenv("API_KEY")
# openai.api_key = API_KEY

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("api_calls.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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
        self.argument_style = random.choice(ARGUMENT_STYLES)
        print(f"AI Player {self.name} initialized with argument style: {self.argument_style}")

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
        history = history[-9:] if len(history) > 9 else history
        history_str = '\n'.join(f"{s}: {l}" for s, l in history) or "No discussion yet."
        alive = [p for p in game_manager.get_alive_players() if p.is_alive and p != self]

        context = (
            f"Name:{self.name} Role:{self.role}"
            + (f" MafiaTeam:{','.join(p.name for p in alive if p.role=='Mafia')}" if self.role=='Mafia' else "")
            + f" Alive:{','.join(p.name for p in alive)}"
            + f" Scores:{';'.join(f'{k}:{v:.1f}' for k,v in self.suspicions.items())}" 
        )

        messages = [
            {"role": "system", "content": SYSTEM_BASE},
            {"role": "system", "content": SUSPICION_INSTRUCTIONS},
            {"role": "user", "content": context},
            {"role": "user", "content": f"Discussion:{history_str}"}
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
        history = game_manager.discussion_history.get(game_manager.round_number, [])
        history = history[-4:] if len(history) > 4 else history
        history_str = '\n'.join(f"{s}: {l}" for s, l in history) or "No discussion yet."
        alive_players = game_manager.get_alive_players()

        context = (
            f"Role:{self.role} Name:{self.name}"
            + (f" Fellow Mafia:{','.join(p.name for p in game_manager.get_alive_players() if p.role=='Mafia' and p!=self)}" if self.role=='Mafia' else "")
            + f" Alive:{','.join(p.name for p in game_manager.get_alive_players())}"
            + f" Last Killed:{','.join(p.name for p in game_manager.last_deaths) or 'None'}"
            + (f" Voted Out:{game_manager.last_voted_out.name}({game_manager.last_voted_out.role[0]})" if game_manager.last_voted_out else " Voted Out:None")
            + f" Top Suspicions:{','.join(f'{k[:3]}:{v:.1f}' for k,v in sorted(self.suspicions.items(), key=lambda x: x[1], reverse=True)[:3])}" 
            + f" Round:{game_manager.round_number}"
            + f" Mafia Left:{sum(1 for p in game_manager.get_alive_players() if p.role=='Mafia')}"
        )
        
        # Role specific context
        if self.role == "Doctor" and hasattr(game_manager, 'last_protected'):
            doctor_actions = [(doctor, p) for doctor, p in game_manager.last_protected if doctor.name == self.name]
            if doctor_actions:
                context += f" Protected:{doctor_actions[0][1].name}"
        
        elif self.role == "Investigator" and hasattr(game_manager, 'last_investigated'):
            investigations = [(name, is_mafia) for investigator, name, is_mafia in game_manager.last_investigated if investigator.name == self.name]
            if investigations:
                name, is_mafia = investigations[0]
                context += f" Investigated:{name}({'M' if is_mafia else 'NM'})"
        
        messages = [
            {"role": "system", "content": SYSTEM_BASE},
            {"role": "system", "content": ARGUMENT_INSTRUCTIONS},
            {"role": "system", "content": f"Argument Style:{self.argument_style}"},
            {"role": "user", "content": context},
            {"role": "user", "content": f"Chat:{history_str}"}
        ]
        
        return self.call_api(messages)

    def call_api(self, messages):
        msg_content_length = sum(len(m.get("content", "")) for m in messages)
        token_estimate = msg_content_length // 4
        
        request_id = f"{self.name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        logger.info(f"API Request [{request_id}] - Role: {self.role}, Est. Tokens: {token_estimate}")
        
        for i, msg in enumerate(messages):
            content_preview = msg.get("content", "")[:50] + "..." if len(msg.get("content", "")) > 50 else msg.get("content", "")
            logger.debug(f"Message {i}: {msg.get('role')} - {content_preview}")
        
        start_time = time.time()
        
        payload = {
            # "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": messages,
            # "temperature": 0.4,
            "max_tokens": 32,
            # "stop": ["\n\n"]
        }

        # resp = requests.post(
        #     "https://api.groq.com/openai/v1/chat/completions",
        #     headers={
        #         "Content-Type": "application/json",
        #         "Authorization": f"Bearer {random.choice(API_KEYS)}"
        #     },
        #     json=payload,
        #     timeout=30
        # )

        try:
            resp = requests.post(
                "https://ai.hackclub.com/chat/completions",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=30
            )
            
            resp.raise_for_status()
            data = resp.json()
            end_time = time.time()
            duration = end_time - start_time
            
            response_content = data["choices"][0]["message"]["content"].strip()
            
            response_preview = response_content[:50] + "..." if len(response_content) > 50 else response_content
            logger.info(f"API Response [{request_id}] - Success - Duration: {duration:.2f}s - Response: {response_preview}")
            
            return response_content
            
        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            
            logger.error(f"API Error [{request_id}] - Duration: {duration:.2f}s - Error: {str(e)}")
            
            return "I need to think about the situation."

        # return call_chatgpt(messages)

def call_chatgpt(messages):
    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.4,
        max_tokens=128,
        stop=["\n\n"]
    )

    return response.choices[0].message.content.strip()
