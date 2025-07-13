import numpy as np
from pettingzoo.utils import ParallelEnv
from gymnasium.spaces import Discrete, Box
from ray import tune
from ray.rllib.algorithms.ppo import PPOConfig
from ray.rllib.env.wrappers.pettingzoo_env import ParallelPettingZooEnv
from ray.tune.registry import register_env
import torch
from game import Game_Manager, AI_Player


class MafiaEnv(ParallelEnv):
    metadata = {"render_modes": ["human"]}

    def __init__(self, num_players=10, memory_dim=32):
        self.num_players = num_players
        self.memory_dim = memory_dim
        self.agents = [f"player_{i}" for i in range(num_players)]
        # self.agents is list of player names, self.game.players is list of player objects
        # self.agents is only used for the set up
        self.phase = "night"
        self.night_actions = {}
        self.active_agents = self.agents.copy()
        self.last_invalid_actions = []
        self.game = None

        self.action_spaces = {
            agent: Discrete(num_players) for agent in self.agents
        }

        # Observation space: alive mask + suspicions + memory + role one-hot + phase + round number + action mask
        # Note action mask does not actually work because ray does not support action masks
        # So, I just included it so the agent learns faster and also included a penalty for invalid actions
        self.obs_dim = num_players + num_players + memory_dim + 4 + 1 + 1 + num_players
        self.observation_spaces = {
            agent: Box(
                low=-5.0,
                high=100.0,
                shape=(self.obs_dim,),
                dtype=np.float32
            ) for agent in self.agents
        }

    def reset(self, *, seed=None, options=None):
        self.game = Game_Manager()
        for i in range(self.num_players):
            p = AI_Player(f"player_{i}")
            self.game.add_player(p)

        self.game.players[5].role = "Mafia"
        self.game.players[6].role = "Mafia"
        self.game.players[7].role = "Doctor"
        self.game.players[8].role = "Investigator"
        self.phase = "night"
        self.night_actions = {}
        self.active_agents = self.agents.copy()
        self.game.round_number = 1

        obs = self._build_obs()
        return obs, {}

    def observation_space(self, agent):
        return self.observation_spaces[agent]

    def action_space(self, agent):
        return self.action_spaces[agent]

    def step(self, actions):
        if self.phase == "night":
            self.night_actions.update(actions)
            # Wait until all roles acted
            required_idxs = [i for i, p in enumerate(self.game.players) if p.is_alive and p.role in ("Doctor", "Mafia", "Investigator")]
            required_agents = [f"player_{i}" for i in required_idxs]
            if not all(a in self.night_actions for a in required_agents):
                obs = self._build_obs()
                rewards = self._calc_rewards(None)
                truncateds = {name: False for name in self.active_agents}
                truncateds["__all__"] = False
                infos = {name: {} for name in self.active_agents}
                terminateds = self._get_terminateds()
                return obs, rewards, terminateds, truncateds, infos

            # Apply night actions
            self._apply_night_actions(required_agents)
            # Check if game is over
            rewards = self._calc_rewards(None)
            obs = self._build_obs()
            truncateds = {name: False for name in self.active_agents}
            truncateds["__all__"] = False
            infos = {name: {} for name in self.active_agents}
            terminateds = self._get_terminateds()
            self.phase = 'day'
            return obs, rewards, terminateds, truncateds, infos

        # Day phase
        votes = {}
        for player in self.game.players:
            if not player.is_alive:
                continue

            # Makes sure actions are valid else randomly chooses
            action = actions.get(player.name, None)
            action_mask = self._create_action_mask(player)
            if action_mask[action] == 0:
                action = np.random.choice(np.where(action_mask == 1)[0])
            target = self.game.players[action]
            votes[target.name] = votes.get(target.name, 0) + 1
            player.memory.write(f"{player.name} voted {target.name}")

        # Eliminate most voted
        max_votes = max(votes.values())
        candidates = [n for n, v in votes.items() if v == max_votes]
        elim = np.random.choice(candidates)
        for player in self.game.players:
            if player.name == elim:
                player.is_alive = False
                break
        eliminated = player

        rewards = self._calc_rewards(eliminated)
        done, mafia_won = self.game.check_win_condition()
        obs = self._build_obs()
        truncateds = {name: False for name in self.active_agents}
        truncateds["__all__"] = False
        infos = {name: {} for name in self.active_agents}
        terminateds = self._get_terminateds()
        self.phase = 'night'
        self.game.round_number += 1
        return obs, rewards, terminateds, truncateds, infos

    def _get_terminateds(self):
        done, mafia_won = self.game.check_win_condition()
        alive_names = {p.name for p in self.game.get_alive_players()}
        terminateds = {name: (name not in alive_names) for name in self.active_agents}
        newly_eliminated = [name for name in self.active_agents if name not in alive_names]
        for name in newly_eliminated:
            self.active_agents.remove(name)
        terminateds['__all__'] = done
        if done:
            for name, terminated in terminateds.items():
                if not terminated:
                    terminateds[name] = True
        return terminateds
    
    def _apply_night_actions(self, required_agents):
        self.game.last_protected = []
        self.game.last_targeted = []
        self.game.last_investigated = []
        self.last_invalid_actions = []

        for player in self.game.get_alive_players():
            if player.name not in required_agents or not player.is_alive:
                continue

            action = self.night_actions[player.name]
            action_mask = self._create_action_mask(player)
            if action_mask[action] == 0:
                action = np.random.choice(np.where(action_mask == 1)[0])
                self.last_invalid_actions.append(player)

            target = self.game.players[action]

            if player.role == 'Doctor':
                target.is_protected = True
                self.game.last_protected.append((player, target))
                player.memory.write(f"{player.name} protected {target.name}")

            elif player.role == 'Mafia':
                self.game.last_targeted.append((player, target))
                player.memory.write(f"{player.name} targeted {target.name}")

            elif player.role == 'Investigator':
                res = (target.role == 'Mafia')

                self.game.last_investigated.append((player, target.name, res))
                player.update_suspicion_investigation(target, res)
                player.memory.write(f"{player.name} investigated {target.name}, result: {'Mafia' if res else 'Not Mafia'}")

        # Kill
        for _, target in self.game.last_targeted:
            if not target.is_protected:
                target.is_alive = False
        self.game.last_deaths = [target for _, target in self.game.last_targeted if not target.is_protected]
        # Write death memory
        for player in self.game.get_alive_players():
            for death in self.game.last_deaths:
                player.memory.write(f"{death.name} was killed last night")
        # Clear protection
        for player in self.game.players:
            player.is_protected = False

    def _create_action_mask(self, player):
        action_mask = np.zeros(self.num_players, dtype=np.float32)
        if self.phase == "night":
            if player.role == "Mafia":
                for i, p in enumerate(self.game.players):
                    if p.is_alive and p.role != "Mafia":
                        action_mask[i] = 1.0
            elif player.role == "Doctor":
                for i, p in enumerate(self.game.players):
                    if p.is_alive and p != player:
                        action_mask[i] = 1.0
            elif player.role == "Investigator":
                valid_targets = [i for i, p in enumerate(self.game.players)
                                    if p.is_alive and p != player and p not in self.game.already_investigated]
                if valid_targets:
                    for i in valid_targets:
                        action_mask[i] = 1.0
                else:
                    # If no targets that haven't been investigated, allow all alive players
                    for i, p in enumerate(self.game.players):
                        if p.is_alive and p != player:
                            action_mask[i] = 1.0
            else:
                pass # Villager has no actions at night
        else:
            for i, p in enumerate(self.game.players):
                if p.is_alive and p != player:
                    action_mask[i] = 1.0
        
        return action_mask

    def _build_obs(self):
        obs = {}
        alive_mask = np.array([1.0 if p.is_alive else 0.0 for p in self.game.players], dtype=np.float32)
        
        for name in self.active_agents:
            for p in self.game.players:
                if p.name == name:
                    player = p
                    break

            if not player.is_alive:
                obs[name] = np.zeros(self.obs_dim, dtype=np.float32)
                continue

            suspicions = np.array([player.suspicions.get(p.name, 0.0) for p in self.game.players], dtype=np.float32)
            mem = player.memory.get_memory().astype(np.float32)
            
            role_map = {'Villager': 0, 'Mafia': 1, 'Doctor': 2, 'Investigator': 3}
            onehot = np.array([0] * 4, dtype=np.float32)
            onehot[role_map[player.role]] = 1
            
            phase = np.array([1.0 if self.phase == 'night' else 0.0], dtype=np.float32)
            round_number = np.array([float(self.game.round_number)], dtype=np.float32)

            action_mask = self._create_action_mask(player)

            vec = np.concatenate([alive_mask, suspicions, mem, onehot, phase, round_number, action_mask])
            obs[player.name] = vec.astype(np.float32)
    
        return obs

    def _calc_rewards(self, eliminated): # Eliminated is the player eliminated this round by voting, None if it was a night kill
        done, mafia_won = self.game.check_win_condition()
        rewards = {}
        for name in self.active_agents:
            for p in self.game.players:
                if p.name == name:
                    player = p
                    break

            if not player.is_alive:
                rewards[player.name] = 0.0
                continue

            if done:
                if mafia_won:
                    val = 5.0 if player.role == "Mafia" else -5.0
                else:
                    val = -5.0 if player.role == "Mafia" else 5.0
            elif eliminated:
                if eliminated.role == "Mafia":
                    val = 0.5 if player.role != "Mafia" else -0.5
                else:
                    val = 0.5 if player.role == "Mafia" else -0.5
            else: # Give small rewards for night actions
                if player.role == "Doctor":
                    for p, target in self.game.last_protected:
                        if target.is_alive and p.name == player.name:
                            val = 0.5
                    else:
                        val = 0.0
                elif player.role == "Investigator":
                    for p, target_name, res in self.game.last_investigated:
                        if p.name == player.name:
                            if res:
                                val = 0.5
                    else:
                        val = 0.0
                else:
                    val = 0.0
            rewards[player.name] = val
            for player in self.last_invalid_actions:
                if player.name == name:
                    rewards[name] -= 1.0
        return rewards

    def render(self):
        alive = [p.name for p in self.game.players if p.is_alive]
        print(f"\nRound {self.game.round_number}, alive={alive}")
        print("Rewards: ")
        for name, reward in self._calc_rewards(None).items():
            print(f"  {name}: {reward}")
        done, mafia_won = self.game.check_win_condition()
        if done:
            if mafia_won:
                print("Mafia wins!")
            else:
                print("Villagers win!")


if __name__ == "__main__":
    register_env(
        "mafia",
        lambda cfg: ParallelPettingZooEnv(MafiaEnv(**cfg))
    )

    # Sample env to fetch spaces
    env = MafiaEnv(num_players=10, memory_dim=32)
    obs_space = env.observation_spaces['player_0']
    act_space = env.action_spaces['player_0']

    policies = {
        "Villager": (None, obs_space, act_space, {}),
        "Mafia":    (None, obs_space, act_space, {}),
        "Doctor":   (None, obs_space, act_space, {}),
        "Investigator":   (None, obs_space, act_space, {}),
    }

    def policy_mapping_fn(agent_id, episode=None, worker=None, **kwargs):
        idx = int(agent_id.split("_")[1])
        if idx in [5, 6]:
            return "Mafia"
        elif idx == 7:
            return "Doctor"
        elif idx == 8:
            return "Investigator"
        else:
            return "Villager"

    torch.set_default_device('mps')
    
    config = (
        PPOConfig()
        .environment("mafia", env_config={"num_players": 10, "memory_dim": 32})
        .framework("torch")
        .multi_agent(policies=policies, policy_mapping_fn=policy_mapping_fn)
        .resources(num_gpus=0)
        .training(lr=3e-4)
        .env_runners(num_env_runners=5)
    )

    analysis = tune.run(
        "PPO",
        config=config.to_dict(),
        stop={"training_iteration": 25},
        checkpoint_at_end=True,
        checkpoint_freq=10,
        keep_checkpoints_num=5,
        metric="episode_return_mean",
        mode="max"
    )

    best_trial = analysis.get_best_trial(metric="env_runners/episode_return_mean", mode="max")
    best_checkpoint = analysis.get_best_checkpoint(
        trial=best_trial,
        metric="env_runners/episode_return_mean",
        mode="max"
    )

    print(f"Best checkpoint saved at: {best_checkpoint}")
