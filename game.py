import random
from player_classes import AI_Player, Human_Player
from model_manager import ModelManager, ObservationManager
from phase_manager import PhaseManager
from web_app_function_manager import WebAppFunctionManager


class Game_Manager:
    def __init__(self, use_model=False):
        self.players = []
        self.round_number = 1
        self.last_deaths = []
        self.discussion_history = {1: [("System", "Start of game - round 1.")]}
        self.last_protected = []
        self.last_investigated = []
        self.last_targeted = []
        self.already_investigated = set()
        self.revote = []
        self.is_night = True
        self.votes = {}
        self.current_speaker = None
        self.sub_phase = None
        self.phase_timer = None
        self.tied_candidates = []
        self.last_voted_out = None
        self.game_over = False
        self.winner = None

        self.use_model = use_model
        if use_model:
            model_path = "/Users/qiaoe27/ray_results/PPO_2025-06-21_12-05-28/PPO_mafia_8cc60_00000_0_2025-06-21_12-05-28/checkpoint_000002"
            self.model = ModelManager(model_path)

        # Component managers
        self.observation_manager = ObservationManager(self)
        self.phase_manager = PhaseManager(self)
        self.web_app_manager = WebAppFunctionManager(self)

    def add_player(self, player):
        self.players.append(player)

    def get_alive_players(self):
        return [p for p in self.players if p.is_alive]
    
    def shuffle_roles(self):
        roles = ["Villager"] * 5 + ["Mafia"] * 2 + ["Doctor"] + ["Investigator"] + ["Villager"]
        random.shuffle(roles)
        for player, role in zip(self.players, roles):
            player.role = role

    def start_game(self):
        self.shuffle_roles()
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
            self.game_over = True
            self.winner = "Villagers"
            return True, "Villagers"
        # Mafia win if they outnumber or equal villagers
        if mafia_count >= len(alive_players) - mafia_count:
            self.game_over = True
            self.winner = "Mafia"
            return True, "Mafia"
        return False, None

    def game_loop(self):
        while True:
            print(f"\nRound {self.round_number} begins!")
            self.discussion_history[self.round_number] = []
            self.last_deaths = self.night_phase()
            done, winner = self.check_win_condition()
            if done:
                if winner == "Villagers":
                    print("\nVillagers win! All Mafia members have been eliminated.")
                else:
                    print("\nMafia wins! The Mafia outnumber the Villagers.")
                break
            for player in self.get_alive_players():
                if isinstance(player, AI_Player):
                    print(f"{player.name}'s suspicion meter: {player.suspicions}")
            self.day_phase()
            done, winner = self.check_win_condition()
            if done:
                if winner == "Villagers":
                    print("\nVillagers win! All Mafia members have been eliminated.")
                else:
                    print("\nMafia wins! The Mafia outnumber the Villagers.")
                break
            self.round_number += 1
            
    def night_phase(self):
        return self.phase_manager.night_phase()
    
    def day_phase(self):
        self.phase_manager.day_phase()
        
    def discussion_phase(self, time_limit):
        self.phase_manager.discussion_phase(time_limit)
        
    def voting_phase(self):
        self.phase_manager.voting_phase()
    
    def get_observation(self, player):
        return self.observation_manager.get_observation(player)
    
    def doctor_action(self, player_name, target_name):
        return self.web_app_manager.doctor_action(player_name, target_name)
        
    def mafia_action(self, player_name, target_name):
        return self.web_app_manager.mafia_action(player_name, target_name)
        
    def investigator_action(self, player_name, target_name):
        return self.web_app_manager.investigator_action(player_name, target_name)
        
    def vote_action(self, player_name, target_name):
        return self.web_app_manager.vote_action(player_name, target_name)
    
    def try_advance(self):
        return self.web_app_manager.try_advance()
    
    def get_player_role(self, player_name):
        return self.web_app_manager.get_player_role(player_name)
    
    def get_game_phase(self):
        return self.web_app_manager.get_game_phase()
    
    def get_investigation_results(self, player_name):
        return self.web_app_manager.get_investigation_results(player_name)
    
    def get_game_status(self):
        # Always return the current over/winner state
        return {
            "is_over": self.game_over,
            "winner": self.winner
        }
    
    def is_player_speaker(self, player):
        if isinstance(player, str):
            return self.get_game_phase() == "day" and self.current_speaker == player
        else:
            return self.get_game_phase() == "day" and self.current_speaker == player.name
    
    def next_speaker(self):
        alive_players = self.get_alive_players()
        if not alive_players:
            return
            
        # If no current speaker, start with first player
        if not hasattr(self, 'current_speaker') or not self.current_speaker:
            self.current_speaker = alive_players[0].name
            return
            
        # Find current player index
        current_idx = next((i for i, p in enumerate(alive_players) 
                           if p.name == self.current_speaker), 0)
                           
        # Move to next player
        next_idx = (current_idx + 1) % len(alive_players)
        self.current_speaker = alive_players[next_idx].name
    
    def add_message(self, player_name, message):
        return self.web_app_manager.add_message(player_name, message)

if __name__ == "__main__":
    game_manager = Game_Manager(use_model=True)

    game_manager.add_player(Human_Player("Mike"))
    game_manager.add_player(AI_Player("Alice"))
    game_manager.add_player(AI_Player("Bob"))
    game_manager.add_player(AI_Player("Charlie"))
    game_manager.add_player(AI_Player("Frank"))
    game_manager.add_player(AI_Player("Grace"))
    game_manager.add_player(AI_Player("Dana"))
    game_manager.add_player(AI_Player("Eve"))
    game_manager.add_player(AI_Player("Hank"))
    game_manager.add_player(AI_Player("Ivy"))

    game_manager.start_game()
