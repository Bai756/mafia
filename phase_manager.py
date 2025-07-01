import time
from player_classes import Human_Player, AI_Player

class PhaseManager:
    def __init__(self, game_manager):
        self.game = game_manager

    def night_phase(self):
        self.game.is_night = True
        print("\nNight phase begins.")
        death = []
        protected = []
        alive_players = self.game.get_alive_players()
        self.game.last_deaths.clear()
        self.game.last_protected.clear()
        self.game.last_investigated.clear()
        self.game.last_targeted.clear()

        # Doctor's turn
        doctors = [p for p in alive_players if p.role == "Doctor"]
        eligible_targets = alive_players
        if doctors:
            for doctor in doctors:
                print("\nDoctors can choose a player to protect.")
                if isinstance(doctor, Human_Player):
                    print("Eligible players to protect:")
                    for t in eligible_targets:
                        if t.is_alive and t != doctor:
                            print(f"- {t.name}")
                
                target = doctor.vote(self.game, eligible_targets)
                target.is_protected = True
                protected.append(target)
                eligible_targets.remove(target)
                self.game.last_protected.append((doctor, target))

                if isinstance(doctor, AI_Player):
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

                target = mafia.vote(self.game, eligible_targets)
                if not target.is_protected:
                    target.is_alive = False
                    death.append(target)
                else:
                    target.is_protected = False
                eligible_targets.remove(target)
                self.game.last_targeted.append((mafia, target))

                if isinstance(mafia, AI_Player):
                    desc = f"{mafia.name} targeted {target.name} for elimination"
                    desc += " (killed)" if not target.is_alive else " (was protected)"
                    mafia.memory.write(desc)

        # Investigator's turn
        investigators = [p for p in alive_players if p.role == "Investigator"]
        eligible_targets = [p for p in alive_players if p.is_alive and p not in self.game.already_investigated]
        if investigators:
            for investigator in investigators:
                print("\nInvestigators can choose a player to investigate.")
                if isinstance(investigator, Human_Player):
                    print("Eligible players to investigate:")
                    for t in eligible_targets:
                        if t.is_alive and t != investigator:
                            print(f"- {t.name}")

                target = investigator.vote(self.game)
                if target.role == "Mafia":
                    print(f"{investigator.name} discovers that {target.name} is a Mafia member.")
                else:
                    print(f"{investigator.name} discovers that {target.name} is not a Mafia member.")

                if isinstance(investigator, AI_Player):
                    investigator.update_suspicion_investigation(target, target.role == "Mafia")

                self.game.last_investigated.append((investigator, target.name, target.role == "Mafia"))
                self.game.already_investigated.add(target)

                if isinstance(investigator, AI_Player):
                    desc = f"{investigator.name} investigated {target.name}: {'Mafia' if target.role=='Mafia' else 'Innocent'}"
                    investigator.memory.write(desc)

        for p in protected:
            p.is_protected = False

        print("\nEnd of night phase.")
        return death
    
    def day_phase(self):
        self.game.is_night = False
        print("\nDay phase begins.")
        if self.game.last_deaths:
            print("\nDuring the night, the following events occurred:")
            for d in self.game.last_deaths:
                print(f"{d.name} has died.")

                for player in self.game.get_alive_players():
                    if isinstance(player, AI_Player):
                        player.memory.write(f"{d.name} was killed during the night.")
        else:
            print("\nNo one was killed during the night.")
        print("\nDiscussion starts now (2 minutes).")

        self.discussion_phase(60)

        for player in self.game.get_alive_players():
            if isinstance(player, AI_Player):
                player.update_suspicion(self.game)

        self.voting_phase()
        
    def discussion_phase(self, time_limit):
        print(f"\nDiscussion phase begins. Players can discuss their suspicions and strategies for {time_limit} seconds.\n")

        start_time = time.time()
        alive_players = self.game.get_alive_players()

        self.game.current_speaker = None
        self.game.next_speaker()

        while time.time() - start_time < time_limit:
            player_name = self.game.current_speaker
            player = next((p for p in alive_players if p.name == player_name), None)
            argument = player.generate_argument(self.game)
            print(f"{player.name}: {argument.strip()}\n")
            self.game.discussion_history[self.game.round_number].append((player.name, argument))

            time.sleep(6)
            self.game.next_speaker()

        print("End of discussion phase.")

    def voting_phase(self):
        print("\nVoting phase")
        self.game.revote = []
        votes = {}
        alive = self.game.get_alive_players()

        # Each player votes for someone to eliminate
        for player in alive:
            if isinstance(player, Human_Player):
                print("Eligible players to vote against:")
                for t in alive:
                    if t != player:
                        print(f"- {t.name}")

            if player.role == "Mafia":
                target = player.vote(self.game)
            else:
                target = player.vote(self.game)

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
            self.game.revote = most_voted
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

                target = player.vote(self.game)

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
