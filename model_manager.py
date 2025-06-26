import torch
import ray
from ray.rllib.algorithms.ppo import PPO
from ray.tune.registry import register_env
from ray.rllib.env import ParallelPettingZooEnv
import numpy as np

class ModelManager:
    def __init__(self, checkpoint_path):
        from train import MafiaEnv
        register_env(
            "mafia",
            lambda cfg: ParallelPettingZooEnv(MafiaEnv(**cfg))
        )
        ray.init(ignore_reinit_error=True)

        self.algo = PPO.from_checkpoint(checkpoint_path)

        self.modules = {
            policy_id: self.algo.get_module(policy_id)
            for policy_id in ["Villager", "Mafia", "Doctor", "Investigator"]
        }

        villager_module = self.modules["Villager"]
        self.obs_dim = villager_module.observation_space.shape[0]
    
    def get_action(self, obs, role):
        module = self.modules[role]
        tensor_obs = torch.as_tensor(obs, dtype=torch.float32).reshape(1, -1)
        
        output = module.forward_inference({"obs": tensor_obs})
        action_dist = output["action_dist_inputs"]
        
        action = torch.argmax(action_dist, dim=-1).item()
        return action


class ObservationManager:
    def __init__(self, game_manager):
        self.game = game_manager
        
    def get_observation(self, player):
        alive_mask = np.array([1.0 if p.is_alive else 0.0 for p in self.game.players], dtype=np.float32)

        suspicions = np.array([player.suspicions.get(p.name, 0.0) for p in self.game.players], dtype=np.float32)
        mem = player.memory.get_memory().astype(np.float32)

        role_map = {'Villager': 0, 'Mafia': 1, 'Doctor': 2, 'Investigator': 3}
        onehot = np.array([0] * 4, dtype=np.float32)
        onehot[role_map[player.role]] = 1

        phase = np.array([1.0 if self.game.is_night else 0.0], dtype=np.float32)
        round_number = np.array([float(self.game.round_number)], dtype=np.float32)

        action_mask = self.create_action_mask(player)

        return np.concatenate([alive_mask, suspicions, mem, onehot, phase, round_number, action_mask])
    
    def create_action_mask(self, player):
        action_mask = np.zeros(len(self.game.players), dtype=np.float32)
        if self.game.is_night == True:
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