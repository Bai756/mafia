from player_classes import AI_Player

class WebAppFunctionManager:
    def __init__(self, game_manager):
        self.game = game_manager

    def doctor_action(self, player_name, target_name):
        doctor = next((p for p in self.game.players if p.name == player_name and p.is_alive), None)
        target = next((p for p in self.game.players if p.name == target_name and p.is_alive), None)

        if doctor and doctor.role == "Doctor" and target:
            target.is_protected = True
            self.game.last_protected.append((doctor, target))
            return True
        return False

    def mafia_action(self, player_name, target_name):
        mafia = next((p for p in self.game.players if p.name == player_name and p.is_alive), None)
        target = next((p for p in self.game.players if p.name == target_name and p.is_alive), None)

        if mafia and mafia.role == "Mafia" and target:
            self.game.last_targeted.append((mafia, target))
            return True
        return False

    def investigator_action(self, player_name, target_name):
        investigator = next((p for p in self.game.players if p.name == player_name and p.is_alive), None)
        target = next((p for p in self.game.players if p.name == target_name and p.is_alive), None)

        if investigator and investigator.role == "Investigator" and target:
            is_mafia = target.role == "Mafia"
            self.game.last_investigated.append((investigator, target.name, is_mafia))
            self.game.already_investigated.add(target)
            return True, is_mafia
        return False, False

    def vote_action(self, player_name, target_name):
        voter = next((p for p in self.game.players if p.name == player_name and p.is_alive), None)
        target = next((p for p in self.game.players if p.name == target_name and p.is_alive), None)

        if voter and target and target != voter:
            if not hasattr(self.game, 'votes'):
                self.game.votes = {}
            self.game.votes[voter.name] = target.name
            return True
        return False

    def try_advance(self):
        if self.is_night:
            # Check if all night actions are complete
            doctors = [p for p in self.game.get_alive_players() if p.role == "Doctor"]
            mafia = [p for p in self.game.get_alive_players() if p.role == "Mafia"]
            investigators = [p for p in self.game.get_alive_players() if p.role == "Investigator"]

            doctors_acted = len(self.game.last_protected) >= len(doctors)
            mafia_acted = len(self.game.last_targeted) >= len(mafia)
            investigators_acted = len(self.game.last_investigated) >= len(investigators)

            if doctors_acted and mafia_acted and investigators_acted:
                # Process night results
                self._resolve_night_actions()
                self.game.is_night = False
                return True
        else:
            # Day phase - check if everyone has voted
            if len(self.game.votes) == len(self.game.get_alive_players()):
                self._resolve_day_votes()
                self.game.is_night = True
                self.game.round_number += 1
                return True
        
        return False

    def _resolve_night_actions(self):
        self.game.last_deaths = []

        # Process doctor protections
        protected_players = [target for _, target in self.game.last_protected]

        # Process mafia kills
        for _, target in self.game.last_targeted:
            if target not in protected_players:
                target.is_alive = False
                self.game.last_deaths.append(target)

        # Reset protections
        for player in self.game.players:
            player.is_protected = False

    def _resolve_day_votes(self):
        vote_counts = {}
        for target_name in self.game.votes.values():
            vote_counts[target_name] = vote_counts.get(target_name, 0) + 1
        
        if not vote_counts:
            return
        
        max_votes = max(vote_counts.values())
        most_voted = [name for name, count in vote_counts.items() if count == max_votes]
        
        if len(most_voted) == 1:
            eliminated_name = most_voted[0]
            eliminated = next((p for p in self.game.players if p.name == eliminated_name), None)
            if eliminated:
                eliminated.is_alive = False
        
        self.game.votes = {}

    def get_player_role(self, player_name):
        player = next((p for p in self.game.players if p.name == player_name), None)
        return player.role if player else None

    def get_game_phase(self):
        if self.game.is_night:
            return "night"
        return "day"

    def get_investigation_results(self, player_name):
        results = []
        for investigator, target_name, is_mafia in self.game.last_investigated:
            if investigator.name == player_name:
                results.append({"name": target_name, "is_mafia": is_mafia})
        return results

    def get_game_status(self):
        is_over, winner = self.game.check_win_condition()
        return {
            "is_over": is_over,
            "winner": winner
        }
    
    def add_message(self, player_name, message):
        if self.game.get_game_phase() == "day" and self.game.is_player_speaker(player_name):
            round_number = self.game.round_number
            if round_number not in self.game.discussion_history:
                self.game.discussion_history[round_number] = []
            
            self.game.discussion_history[round_number].append((player_name, message))

            self.game.next_speaker()
            return True
        return False
    
    def process_ai_night_actions(self):
        for player in self.game.get_alive_players():
            if not isinstance(player, AI_Player):
                continue
                
            target = player.vote(self.game.get_alive_players(), self.game)
            
            if player.role == "Doctor":
                self.doctor_action(player.name, target.name)
            elif player.role == "Mafia":
                self.mafia_action(player.name, target.name)
            elif player.role == "Investigator":
                success, is_mafia = self.investigator_action(player.name, target.name)
                if success:
                    print(f"{player.name} investigated {target.name}: {'Mafia' if is_mafia else 'Not Mafia'}")
