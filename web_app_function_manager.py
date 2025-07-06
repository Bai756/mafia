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
        current_phase = self.get_game_phase()
        print(f"[DEBUG] Checking if we can advance from {current_phase} phase...")
        
        if current_phase == "night":
            # Track which players with special roles need to act
            # Track which alive players with special roles still need to act
            doctors_need_to_act = [p.name for p in self.game.get_alive_players() if p.role == "Doctor" and not any(doc.name == p.name for doc, _ in self.game.last_protected)]
            mafia_need_to_act = [p.name for p in self.game.get_alive_players() if p.role == "Mafia" and not any(maf.name == p.name for maf, _ in self.game.last_targeted)]
            investigators_need_to_act = [p.name for p in self.game.get_alive_players() if p.role == "Investigator" and not any(inv.name == p.name for inv, _, _ in self.game.last_investigated)]

            # Log which players still need to act
            if doctors_need_to_act:
                print(f"[DEBUG] Waiting for doctors to act: {', '.join(doctors_need_to_act)}")
            if mafia_need_to_act:
                print(f"[DEBUG] Waiting for mafia to act: {', '.join(mafia_need_to_act)}")
            if investigators_need_to_act:
                print(f"[DEBUG] Waiting for investigators to act: {', '.join(investigators_need_to_act)}")

            # Check if any AI players with special roles still need to act
            ai_players_need_to_act = [
                p for p in self.game.players
                if p.name in doctors_need_to_act + mafia_need_to_act + investigators_need_to_act and isinstance(p, AI_Player)
            ]

            # If there are AI players who haven't acted, make them act now
            for ai_player in ai_players_need_to_act:
                valid_targets = [p for p in self.game.get_alive_players() if p != ai_player]
                if ai_player.role == "Mafia":
                    valid_targets = [p for p in valid_targets if p.role != "Mafia"]
                    if valid_targets:
                        target = ai_player.vote(self.game, valid_targets)
                        if target:
                            print(f"[DEBUG] AI {ai_player.name} (Mafia) targeting {target.name}")
                            self.mafia_action(ai_player.name, target.name)
                elif ai_player.role == "Doctor" and valid_targets:
                    target = ai_player.vote(self.game, valid_targets)
                    if target:
                        print(f"[DEBUG] AI {ai_player.name} (Doctor) protecting {target.name}")
                        self.doctor_action(ai_player.name, target.name)
                elif ai_player.role == "Investigator" and valid_targets:
                    target = ai_player.vote(self.game, valid_targets)
                    if target:
                        print(f"[DEBUG] AI {ai_player.name} (Investigator) investigating {target.name}")
                        self.investigator_action(ai_player.name, target.name)

            # Recalculate who needs to act after AI actions
            doctors_need_to_act = [p.name for p in self.game.get_alive_players() if p.role == "Doctor" and not any(doc.name == p.name for doc, _ in self.game.last_protected)]
            mafia_need_to_act = [p.name for p in self.game.get_alive_players() if p.role == "Mafia" and not any(maf.name == p.name for maf, _ in self.game.last_targeted)]
            investigators_need_to_act = [p.name for p in self.game.get_alive_players() if p.role == "Investigator" and not any(inv.name == p.name for inv, _, _ in self.game.last_investigated)]

            all_doctors_acted = len(doctors_need_to_act) == 0
            all_mafia_acted = len(mafia_need_to_act) == 0
            all_investigators_acted = len(investigators_need_to_act) == 0
            if all_doctors_acted and all_mafia_acted and all_investigators_acted:
                print("[DEBUG] All night actions completed, advancing to day phase")
                # Process night results
                self._resolve_night_actions()
                self.game.is_night = False
                
                # Add system message for night results
                round_num = self.game.round_number
                if round_num not in self.game.discussion_history:
                    self.game.discussion_history[round_num] = []
                
                deaths_text = "No one died last night."
                if self.game.last_deaths:
                    deaths_text = f"The following players died during the night: {', '.join(p.name for p in self.game.last_deaths)}."
                    
                self.game.discussion_history[round_num].append(("System", deaths_text))
                
                # Check win condition after night phase
                game_status = self.get_game_status()
                if game_status["is_over"]:
                    self.game.discussion_history[round_num].append(("System", f"Game over! {game_status['winner']} win!"))
                
                return True
        else:
            # Day phase - check if everyone has voted
            alive_players = self.game.get_alive_players()
            alive_count = len(alive_players)
            votes_count = len(getattr(self.game, 'votes', {}))
            
            print(f"[DEBUG] Day phase: {votes_count}/{alive_count} votes received")
            
            # Check if any AI players still need to vote
            ai_players = [p for p in alive_players if isinstance(p, AI_Player)]
            for ai_player in ai_players:
                if ai_player.name not in getattr(self.game, 'votes', {}):
                    # AI player hasn't voted yet, make them vote
                    valid_targets = [p for p in alive_players if p != ai_player]
                    if valid_targets:
                        target = ai_player.vote(self.game, valid_targets)
                        if target:
                            print(f"[DEBUG] AI {ai_player.name} voting for {target.name}")
                            self.vote_action(ai_player.name, target.name)
                            votes_count += 1
            
            if votes_count >= alive_count:
                print("[DEBUG] All votes received, advancing to night phase")
                self._resolve_day_votes()
                self.game.is_night = True
                self.game.round_number += 1
                
                # Reset for next round
                self.game.last_protected = []
                self.game.last_targeted = []
                self.game.last_deaths = []
                
                # Reset votes
                self.game.votes = {}
                
                # Add night beginning message
                round_num = self.game.round_number
                if round_num not in self.game.discussion_history:
                    self.game.discussion_history[round_num] = []
                    
                self.game.discussion_history[round_num].append(("System", f"Night of round {round_num} begins."))
                
                # Check win condition after day phase
                game_status = self.get_game_status()
                if game_status["is_over"]:
                    self.game.discussion_history[round_num].append(("System", f"Game over! {game_status['winner']} win!"))
                
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
        print(f"[DEBUG] add_message called for {player_name}: '{message}'")
        print(f"[DEBUG] Current phase: {self.game.get_game_phase()}")
        print(f"[DEBUG] Current speaker: {self.game.current_speaker}")
        print(f"[DEBUG] is_player_speaker: {self.game.is_player_speaker(player_name)}")
        
        if self.game.get_game_phase() == "day" and self.game.is_player_speaker(player_name):
            round_number = self.game.round_number
            print(f"[DEBUG] Adding message to round {round_number}")
            if round_number not in self.game.discussion_history:
                self.game.discussion_history[round_number] = []
            
            self.game.discussion_history[round_number].append((player_name, message))
            print(f"[DEBUG] Message added successfully, moving to next speaker")
            self.game.next_speaker()
            print(f"[DEBUG] New speaker: {self.game.current_speaker}")
            return True
        
        print(f"[DEBUG] Failed to add message")
        return False
    
    def process_ai_night_actions(self):
        print("[DEBUG] Processing AI night actions...")
        ai_actions_taken = False
        
        for player in self.game.get_alive_players():
            if not isinstance(player, AI_Player):
                continue
            
            print(f"[DEBUG] Processing AI {player.name} with role {player.role}")
            
            # Get valid targets based on role
            valid_targets = [p for p in self.game.get_alive_players() if p != player]
            if player.role == "Mafia":
                valid_targets = [p for p in valid_targets if p.role != "Mafia"]
                if valid_targets:
                    target = player.vote(self.game, valid_targets)
                    if target:
                        print(f"[DEBUG] AI {player.name} (Mafia) targeting {target.name}")
                        self.mafia_action(player.name, target.name)
                        ai_actions_taken = True
                    else:
                        print(f"[DEBUG] AI {player.name} (Mafia) returned no target!")
            elif player.role == "Doctor":
                if valid_targets:
                    target = player.vote(self.game, valid_targets)
                    if target:
                        self.doctor_action(player.name, target.name)
                        ai_actions_taken = True        
            elif player.role == "Investigator":
                # Prefer targets that haven't been investigated yet
                if hasattr(self.game, 'already_investigated') and self.game.already_investigated:
                    uninvestigated = [p for p in valid_targets if p not in self.game.already_investigated]
                    if uninvestigated:
                        valid_targets = uninvestigated
                        
                if valid_targets:
                    target = player.vote(self.game, valid_targets)
                    if target:
                        success, is_mafia = self.investigator_action(player.name, target.name)
                        if success:
                            player.update_suspicion_investigation(target, is_mafia)
                            ai_actions_taken = True

        if ai_actions_taken:
            self.try_advance()
            
        return ai_actions_taken
