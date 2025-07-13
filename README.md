# Mafia Game Web Application

An interactive web-based implementation of the classic social deduction game **Mafia** (also known as **Werewolf**), featuring AI players powered by reinforcement learning.

---

## 🕹️ Overview

This project is a complete multiplayer implementation of Mafia where players must deduce who among them is secretly part of the Mafia. The game includes:

- ✅ Real-time multiplayer gameplay  
- 🧠 AI opponents powered by reinforcement learning  
- 🔁 Turn-based discussion and voting system  
- 🧑‍⚕️ Special roles: Mafia, Villager, Doctor, Investigator  
- 🎮 Lobby system for game setup  

---

## Where to Play

You can play the game at <https://mafiagame.example.com>


## 🔧 Installation

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

   ```bash
   fastapi dev main.py
   ```

---

## 🎮 How to Play

### Game Setup

- Create a new game room or join an existing one
- Enter your player name
- Room creator can add AI players
- Game starts when there are 10 total players

### Game Phases

#### 🌙 Night Phase

- **Mafia**: Choose a player to eliminate  
- **Doctor**: Choose a player to protect  
- **Investigator**: Choose a player to investigate  
- **Villagers**: Sleep (no action)

#### 🌞 Day Phase

- **Discussion**: Players take turns speaking  
- **Voting**: All players vote to eliminate someone  
- **Revote**: If there's a tie, a short discussion and another vote occur

### 🏆 Win Conditions

- **Villagers win**: All Mafia are eliminated  
- **Mafia wins**: Mafia count is equal to or exceeds Villager count

---

## 🧑‍🤝‍🧑 Game Roles

- **Villager**: Discuss and vote to identify Mafia  
- **Mafia**: Eliminate Villagers while staying hidden  
- **Doctor**: Protect a player each night  
- **Investigator**: Learn one player's role per night  

## 🤖 AI Player System

AI players use reinforcement learning with:

- Action masking for legal actions  
- Role-specific behavior models  
- Memory of past votes and discussions  
- Suspicion meters for decision-making  

---

## 🛠️ Development

### AI Model Training

To train or update AI models:

1. Install Ray and set up RLlib  
2. Run the training script:

   ```python
   python train.py
   ```

3. Update the model path in `game.py` after training  
