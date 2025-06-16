import requests
import os
import time
import random
import json
import numpy as np
from collections import deque
from sklearn.feature_extraction.text import TfidfVectorizer


class AgentMemory:
    def __init__(self, max_size=100, embed_dim=32):
        # Raw text events
        self.events = deque(maxlen=max_size)
        # Simple TF‑IDF vectorizer to embed text → high‑dim sparse
        self.vectorizer = TfidfVectorizer(max_features=embed_dim)
        # Running corpus
        self.corpus = []

    def write(self, event: str):
        # Add event to memory
        self.events.append(event)
        self.corpus.append(event)
        self.vectorizer.fit(self.corpus)

    def read(self, query: str, top_k: int = 5) -> np.ndarray:
        # Return the average embedding of the top_k most relevant past events
        if not self.events:
            return np.zeros(self.vectorizer.max_features)

        # Embed all events + query
        all_texts = list(self.events) + [query]
        tfidf = self.vectorizer.transform(all_texts).toarray()
        query_vec = tfidf[-1]
        event_vecs = tfidf[:-1]

        # Cosine similarity
        sims = event_vecs @ query_vec / (np.linalg.norm(event_vecs, axis=1)*np.linalg.norm(query_vec)+1e-8)
        top_idxs = np.argsort(sims)[-top_k:]

        # Return the average embeddings
        return event_vecs[top_idxs].mean(axis=0)


class Player:
    def __init__(self, role, name):
        self.role = role
        self.name = name
        self.is_alive = True
        self.is_protected = False

    def vote(self, target):
        """Record a vote. Note that vote will always refer to a player class object."""
        print(f"{self.name} ({self.role}) votes {target.name} ({target.role})")
        return target


class Human_Player(Player):
    def __init__(self, name):
        super().__init__("Villager", name)

    def vote(self, valid_targets):
        # Prompt user to select a valid target by name
        while True:
            target_name = input("Enter the name of the player to vote: ").strip().lower()
            target = next((p for p in valid_targets if p.name.lower() == target_name and p.is_alive and p != self), None)
            if target:
                return super().vote(target)
            else:
                print("Invalid name.")
    
    def generate_argument(self, _alive_players, _last_deaths, _round_number, _last_protected, _last_investigated):
        print(f"{self.name}, it's your turn to speak.")
        argument = input("Type your argument: ")
        return argument


class AI_Player(Player):
    def __init__(self, name):
        super().__init__("Villager", name)
        self.suspicions = {} # Key values will be the name of another player
        self.memory = AgentMemory(max_size=100, embed_dim=32)

    def vote(self, alive_targets):
        # Vote for the most suspicious alive target
        eligible_targets = [p for p in alive_targets if p != self]
        max_suspicion = max(self.suspicions.get(p.name, 0) for p in eligible_targets)
        most_suspicious = [p for p in eligible_targets if self.suspicions.get(p.name, 0) == max_suspicion]
        return super().vote(random.choice(most_suspicious))
    
    # Mafia already have eligible targets filtered
    def vote_mafia(self, eligible_targets): 
        # Vote for the least suspicious alive target
        min_suspicion = min(self.suspicions.get(p.name, 0) for p in eligible_targets)
        least_suspicious = [p for p in eligible_targets if self.suspicions.get(p.name, 0) == min_suspicion]
        return super().vote(random.choice(least_suspicious))
    
    def vote_doctor(self, alive_targets):
        # Vote for the least suspicious alive target to protect
        eligible_targets = [p for p in alive_targets if p != self]
        min_suspicion = min(self.suspicions.get(p.name, 0) for p in eligible_targets)
        least_suspicious = [p for p in eligible_targets if self.suspicions.get(p.name, 0) == min_suspicion]
        return super().vote(random.choice(least_suspicious))

    def vote_investigator(self, alive_targets):
        # Vote for the most suspicious alive target not confirmed to be mafia to investigate
        eligible_targets = [p for p in alive_targets if p != self]
        eligible_targets = [p for p in eligible_targets if self.suspicions.get(p.name, 0) < 1.0]
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
            -1.0 (completely innocent) to 1.0 (certainly Mafia)
            If scores are already -1.0 or 1.0, do not change them.
            Do not remove any players from the suspicion scores, even if they are not mentioned in the discussion.

            Recent discussion:
            {history_str}

            Alive players: {', '.join(p.name for p in alive_players)}

            Return as JSON like:
            {{ "Alice": 0.3, "Bob": -0.2 }}
            Do not include any other text or formatting.
            """
        new_suspicions = self.call_api(prompt)
        print(f"{self.name} updated suspicion scores: {new_suspicions}")
        self.suspicions = json.loads(new_suspicions)
    
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
            protected = next((p for doctor, p in game_manager.last_protected if doctor.name == self.name))
            status = 'survived' if protected.is_alive else 'died'
            mem = f"- You protected: {protected.name} ({status})"

        elif self.role == "Investigator":
            match = next(((name, is_mafia) for investigator, name, is_mafia in game_manager.last_investigated if investigator.name == self.name))
            name, is_mafia = match
            result = "Mafia" if is_mafia else "not Mafia"
            mem += f"- You investigated: {name} ({result})"

        elif self.role == "Mafia":
            kill_names = [p.name for _, p in game_manager.last_targeted]
            mem += "- Mafia kills last night: " + ', '.join(kill_names)

        prompt = f"""
            You are {self.name}, a {self.role} in a text-based Mafia game.
            {f"The other mafia members are {mafia_names}." if self.role == "Mafia" else ""}

            Objective:
            - Villagers: eliminate all Mafia.
            - Mafia: remain hidden and outnumber the Villagers.

            Rules:
            - Night kills are always by Mafia (unless protected).
            - Doctors protect one person each night.
            - Investigators learn one player’s alignment each night.
            - Day is for discussion and voting.

            Game State:
            Alive players: {players_list}
            Last night’s deaths: {deaths_list}
            Suspicion scores: {self.suspicions}
            The current round is {game_manager.round_number}.

            Your recent role actions:
            {mem or '- None'}
            There are {number_of_mafia} Mafia members remaining.

            Current round discussion:
            {history_str}

            Instructions:
            - Speak once per turn with a new, relevant 1-2 sentence comment.
            - Do NOT repeat lines verbatim or recycle phrases.
            - Do NOT refer to events that never happened.
            - Do NOT claim kills or reveal Mafia actions.
            - Do NOT mention AI, “the game,” or real-world topics.
            - Do NOT speak in third person about yourself.
            - Do NOT mention anything previous interactions that never actually happened.
            - Do NOT claim that you interacted with other players in any way that is not true or that you interacted with players during the night.
            - Do not mourn the death or say anything like that because this is just a game.
            - Reason about the game state and your role and what you should be doing.
            - {"Never reveal your kill or accuse fellow Mafia." if self.role == "Mafia" else ""}
            - {"You play the role of a Doctor, so you can protect one player each night. You are not a actual doctor saving lives. You just help prevent mafia from killing someone." if self.role == "Doctor" else ""}
            - Do not use any special formatting like "Name: Argument", do not use quotes either.
            - Just write your argument as a single paragraph without any formatting.
            - Don't specifically say suspicion score, just say that you are suspicious of someone or that you trust someone.
            - Do not say your inner thoughts outloud, say your argument as you are speaking to the other players.

            Now, based on the above, make a new in-character statement responding to the discussion and recent events.
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


class Game_Manager:
    def __init__(self):
        self.players = []
        self.round_number = 1
        self.last_deaths = []
        self.discussion_history = {1: [("System", "Start of game - round 1. Do not accuse anyone of being quiet or not participating as this just started.")]}
        self.last_protected = []
        self.last_investigated = []
        self.last_targeted = []

    def add_player(self, player):
        self.players.append(player)

    def get_alive_players(self):
        return [p for p in self.players if p.is_alive]

    def start_game(self):
        print("Game started with players:")
        for player in self.players:
            print(f"- {player.name} as {player.role}")
            if isinstance(player, AI_Player):
                player.initialize_suspicion_meter(self.players)
        self.game_loop()
    
    def check_win_condition(self):
        alive_players = self.get_alive_players()
        mafia_count = sum(1 for p in alive_players if p.role == "Mafia")
        # Villagers win if all mafia are eliminated
        if mafia_count == 0:
            print("\nVillagers win! All Mafia members have been eliminated.")
            return True
        # Mafia win if they outnumber or equal villagers
        if mafia_count >= len(alive_players) - mafia_count:
            print("\nMafia wins! The Mafia outnumber the Villagers.")
            return True

    def game_loop(self):
        while True:
            print(f"\nRound {self.round_number} begins!")
            self.discussion_history[self.round_number] = []
            self.last_deaths = self.night_phase()
            if self.check_win_condition():
                break
            for player in self.get_alive_players():
                print(f"{player.name}'s suspicion meter: {player.suspicions if isinstance(player, AI_Player) else 'N/A'}")
            self.day_phase()
            if self.check_win_condition():
                break
            self.round_number += 1

    def day_phase(self):
        print("\nDay phase begins.")
        if self.last_deaths:
            print("\nDuring the night, the following events occurred:")
            for d in self.last_deaths:
                print(f"{d.name} has died.")

                for player in self.get_alive_players():
                    if isinstance(player, AI_Player):
                        player.memory.write(f"{d.name} was killed during the night.")
        else:
            print("\nNo one was killed during the night.")
        print("\nDiscussion starts now (2 minutes).")

        self.discussion_phase(60)

        for player in self.get_alive_players():
            if isinstance(player, AI_Player):
                player.update_suspicion(self)

        self.voting_phase()
    
    def night_phase(self):
        print("\nNight phase begins.")
        death = []
        protected = []
        alive_players = self.get_alive_players()
        self.last_deaths.clear()
        self.last_protected.clear()
        self.last_investigated.clear()
        self.last_targeted.clear()

        # Doctor's turn
        doctors = [p for p in alive_players if p.role == "Doctor"]
        eligible_targets = alive_players.copy()
        if doctors:
            for doctor in doctors:
                print("\nDoctors can choose a player to protect.")
                if isinstance(doctor, Human_Player):
                    print("Eligible players to protect:")
                    for t in eligible_targets:
                        if t.is_alive and t != doctor:
                            print(f"- {t.name}")
                target = None
                while target is None:
                    target = doctor.vote_doctor(eligible_targets)
                target.is_protected = True
                protected.append(target)
                eligible_targets.remove(target)
                self.last_protected.append((doctor, target))

                desc = f"{doctor.name} protected {target.name}"
                doctor.memory.write(desc)

        # Mafia's turn
        mafia_players = [p for p in alive_players if p.role == "Mafia"]
        eligible_targets = [p for p in alive_players if p.is_alive and p.role != "Mafia"]
        if mafia_players:
            for mafia in mafia_players:
                print("\nMafia can choose a player to eliminate.")
                if isinstance(mafia, Human_Player):
                    print("Eligible players to vote against:")
                    for t in eligible_targets:
                        if t != mafia:
                            print(f"- {t.name}")
                target = None
                while target is None:
                    target = mafia.vote_mafia(eligible_targets)
                if not target.is_protected:
                    target.is_alive = False
                    death.append(target)
                else:
                    target.is_protected = False
                eligible_targets.remove(target)
                self.last_targeted.append((mafia, target))

                desc = f"{mafia.name} targeted {target.name} for elimination"
                desc += " (killed)" if not target.is_alive else " (protected)"
                mafia.memory.write(desc)

        # Investigator's turn
        investigators = [p for p in alive_players if p.role == "Investigator"]
        if investigators:
            for investigator in investigators:
                print("\nInvestigators can choose a player to investigate.")
                if isinstance(investigator, Human_Player):
                    print("Eligible players to investigate:")
                    for t in alive_players:
                        if t.is_alive and t != investigator:
                            print(f"- {t.name}")

                target = None
                while target is None:
                    target = investigator.vote_investigator(alive_players)
                if target.role == "Mafia":
                    print(f"{investigator.name} discovers that {target.name} is a Mafia member.")
                else:
                    print(f"{investigator.name} discovers that {target.name} is not a Mafia member.")

                if isinstance(investigator, AI_Player):
                    investigator.update_suspicion_investigation(target, target.role == "Mafia")

                self.last_investigated.append((investigator, target.name, target.role == "Mafia"))

                desc = f"{investigator.name} investigated {target.name}: {'Mafia' if target.role=='Mafia' else 'Innocent'}"
                investigator.memory.write(desc)

        for p in protected:
            p.is_protected = False
        print("\nEnd of night phase.")
        return death
        
    def discussion_phase(self, time_limit):
        print(f"\nDiscussion phase begins. Players can discuss their suspicions and strategies for {time_limit} seconds.\n")

        start_time = time.time()
        alive_players = self.get_alive_players()

        while time.time() - start_time < time_limit:
            for player in alive_players:
                argument = player.generate_argument(self)
                print(f"{player.name}: {argument.strip()}\n")
                self.discussion_history[self.round_number].append((player.name, argument))

            time.sleep(5)

        print("End of discussion phase.")

    def voting_phase(self):
        print("\nVoting phase")
        votes = {}
        alive = self.get_alive_players()

        # Each player votes for someone to eliminate
        for player in alive:
            if isinstance(player, Human_Player):
                print("Eligible players to vote against:")
                for t in alive:
                    if t != player:
                        print(f"- {t.name}")
            target = None
            while target is None:
                if player.role == "Mafia":
                    target = player.vote_mafia(alive)
                else:
                    target = player.vote(alive)
            votes[target] = votes.get(target, 0) + 1

            if isinstance(player, AI_Player):
                player.memory.write(f"{player.name} voted for {target.name}")

        max_votes = max(votes.values())
        most_voted = [p for p, v in votes.items() if v == max_votes]

        if len(most_voted) == 1:
            eliminated = most_voted[0]
            print(f"\n{eliminated.name} has been eliminated.")
            if eliminated.role == "Mafia":
                print(f"{eliminated.name} was a Mafia.")
            else:
                print(f"{eliminated.name} was not a Mafia.")
            eliminated.is_alive = False
        else:
            print("\nThere is a tie between:")
            for p in most_voted:
                print(f"- {p.name}")
            print("\nAnother discussion begins (1 minute)...")
            self.discussion_phase(60)

            print("\nRevote begins.")
            revote = {}
            for player in alive:
                if isinstance(player, Human_Player):
                    print("\nEligible players to vote against (tie-break):")
                    for t in most_voted:
                        if t != player:
                            print(f"- {t.name}")
                target = None
                while target is None:
                    target = player.vote(most_voted)
                revote[target] = revote.get(target, 0) + 1

            max_revote = max(revote.values())
            final_voted = [p for p, v in revote.items() if v == max_revote]

            if len(final_voted) == 1:
                eliminated = final_voted[0]
                print(f"\n{eliminated.name} has been eliminated after the tie-break.")
                if eliminated.role == "Mafia":
                    print(f"{eliminated.name} was a Mafia.")
                else:
                    print(f"{eliminated.name} was not a Mafia.")
                eliminated.is_alive = False
            else:
                print(f"\nStill tied! Voting will be skipped for this round.")
        
        print("\nEnd of voting phase.")


if __name__ == "__main__":
    game_manager = Game_Manager()

    game_manager.add_player(AI_Player("Zoe"))
    game_manager.add_player(AI_Player("Alice"))
    game_manager.add_player(AI_Player("Bob"))
    game_manager.add_player(AI_Player("Charlie"))
    game_manager.add_player(AI_Player("Frank"))
    game_manager.add_player(AI_Player("Grace"))
    game_manager.add_player(AI_Player("Dana"))
    game_manager.add_player(AI_Player("Eve"))
    game_manager.add_player(AI_Player("Hank"))
    game_manager.add_player(AI_Player("Ivy"))

    game_manager.players[0].role = "Villager"
    game_manager.players[1].role = "Villager"
    game_manager.players[2].role = "Villager"
    game_manager.players[3].role = "Villager"
    game_manager.players[4].role = "Villager"
    game_manager.players[5].role = "Mafia"
    game_manager.players[6].role = "Mafia"
    game_manager.players[7].role = "Doctor"
    game_manager.players[8].role = "Investigator"
    game_manager.players[9].role = "Villager"

    game_manager.start_game()
