# Mafia

An interactive web-based implementation of the classic social deduction game **Mafia** (also known as **Werewolf**), featuring AI players powered by reinforcement learning.

---

## Overview

This project is a multiplayer implementation of Mafia.

- Real-time multiplayer gameplay  
- AI opponents powered by reinforcement learning (PPO)
- Special roles: Mafia, Villager, Doctor, Investigator  

---

## How it works

The AI players are trained with PPO (Proximal Policy Optimization) using 
RLlib and PettingZoo. Each role — Mafia, Villager, Doctor, Investigator — 
has its own policy trained independently through self-play. During discussion 
phases, agents communicate via an LLM.

Each agent observes:
- Which players are still alive
- Its own role and suspicion scores for every other player
- A memory vector encoding past events (deaths, votes, investigations)
- The current phase (day/night) and round number

Agents are rewarded for winning (+5), penalized for losing (-5), and get 
smaller rewards for good play mid-game — like the Doctor saving someone or 
the Investigator correctly flagging a Mafia member.

## Installation

### Requirements

- Python 3.9+
- Check `requirements.txt`

### Setup

1. **Clone the repository:**

   ```bash
   git clone https://github.com/your-username/mafia-game.git
   cd mafia-game
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Start the server:**

   ```python
   python main.py
   ```

---
