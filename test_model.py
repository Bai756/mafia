import ray
from ray.rllib.algorithms.ppo import PPO
from ray.tune.registry import register_env
from ray.rllib.env import ParallelPettingZooEnv
from train import MafiaEnv
import torch

register_env(
    "mafia",
    lambda cfg: ParallelPettingZooEnv(MafiaEnv(**cfg))
)

ray.init(ignore_reinit_error=True)

checkpoint_path = "/Users/qiaoe27/ray_results/PPO_2025-06-21_12-05-28/PPO_mafia_8cc60_00000_0_2025-06-21_12-05-28/checkpoint_000002"
algo = PPO.from_checkpoint(checkpoint_path)

env = MafiaEnv()
obs, _ = env.reset()
done = {"__all__": False}
total_rewards = {agent: 0 for agent in env.agents}

modules = {
    policy_id: algo.get_module(policy_id)
    for policy_id in ["Villager", "Mafia", "Doctor", "Investigator"]
}

def get_policy_id(agent_id):
    idx = int(agent_id.split("_")[1])
    if idx in [5, 6]:
        return "Mafia"
    elif idx == 7:
        return "Doctor"
    elif idx == 8:
        return "Investigator"
    else:
        return "Villager"

while not done["__all__"]:
    actions = {}
    
    # For each active agent
    for agent_id in obs.keys():
        # Get the right policy module
        policy_id = get_policy_id(agent_id)
        module = modules[policy_id]
        
        # Get action using new API
        agent_obs = obs[agent_id]
        tensor_obs = torch.as_tensor(agent_obs, dtype=torch.float32).reshape(1, -1)
        output = module.forward_inference({"obs": tensor_obs})
        
        # Convert action distribution to discrete action
        action_dist_inputs = output["action_dist_inputs"]
        action = torch.argmax(action_dist_inputs, dim=-1).item()
        actions[agent_id] = action
    
    obs, rewards, terminateds, truncateds, infos = env.step(actions)
    
    for agent_id, reward in rewards.items():
        total_rewards[agent_id] = total_rewards.get(agent_id, 0) + reward
    
    done = terminateds
    
    env.render()

print(f"Total rewards: {total_rewards}")

ray.shutdown()