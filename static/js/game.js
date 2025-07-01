document.addEventListener('DOMContentLoaded', function() {
    // Game state
    const state = {
        socket: null,
        pingInterval: null,
        playerName: localStorage.getItem('playerName'),
        playerRole: null,
        isAlive: true,
        roomId: localStorage.getItem('roomId'),
        gamePhase: null,
        roundNumber: 0,
        isGameOver: false
    };
    
    // Header elements
    const headerElements = {
        playerNameDisplay: document.getElementById('headerPlayerName'),
        playerRoleInfo: document.getElementById('playerRoleInfo'),
        playerRoleDisplay: document.getElementById('headerPlayerRole')
    };
    
    // Game status elements
    const statusElements = {
        roleDisplay: document.getElementById('roleDisplay'),
        roundDisplay: document.getElementById('roundDisplay'),
        phaseDisplay: document.getElementById('phaseDisplay'),
        gameStatus: document.getElementById('gameStatus')
    };
    
    // Player and action elements
    const playerElements = {
        playersArea: document.getElementById('playersArea'),
        playersList: document.getElementById('playersList'),
        actionsDiv: document.getElementById('actionsDiv'),
        actionArea: document.getElementById('actionArea'),
        eliminatedList: document.getElementById('eliminatedList')
    };
    
    // Discussion elements
    const discussionElements = {
        discussionFeed: document.getElementById('discussionFeed'),
        chatInputArea: document.getElementById('chatInputArea'),
        messageInput: document.getElementById('messageInput'),
        sendMessageBtn: document.getElementById('sendMessageBtn'),
        charCounter: document.getElementById('charCounter')
    };
    
    // Phase sections
    const phaseElements = {
        daySection: document.getElementById('daySection'),
        nightSection: document.getElementById('nightSection')
    };

    // Initialize game
    initGame();
    
    // Clean up resources on page unload
    window.addEventListener('beforeunload', cleanupResources);
    
    function initGame() {
        // Update player header with name
        updatePlayerInfoHeader();
        
        // Validate required data
        if (!state.playerName || !state.roomId) {
            window.location.href = '/';
            return;
        }
        
        // Authenticate player to get role
        authenticatePlayer()
            .then(playerData => {
                if (playerData.error) {
                    throw new Error(playerData.error);
                }
                
                // Store role information
                state.playerRole = playerData.role;
                state.isAlive = playerData.is_alive;
                localStorage.setItem('playerRole', playerData.role);
                localStorage.setItem('isAlive', playerData.is_alive);
                
                // Update header with role information
                updateRoleInfo(playerData.role, playerData.is_alive);
                
                // Set role badge in game UI
                updateRoleBadge(playerData.role);
                
                // Store investigation results if any
                if (playerData.investigation_results && playerData.investigation_results.length > 0) {
                    localStorage.setItem('investigationResults', JSON.stringify(playerData.investigation_results));
                }
                
                // Connect to game WebSocket
                connectGameSocket();
                
                // Initialize message input handlers
                initMessageInput();
            })
            .catch(error => {
                console.error('Authentication failed:', error);
                alert('Failed to join game. Returning to homepage.');
                window.location.href = '/';
            });
    }
    
    function updatePlayerInfoHeader() {
        if (headerElements.playerNameDisplay) {
            headerElements.playerNameDisplay.textContent = state.playerName || 'Anonymous';
        }
    }
    
    function updateRoleInfo(role, isAlive) {
        if (headerElements.playerRoleInfo && headerElements.playerRoleDisplay) {
            headerElements.playerRoleInfo.classList.remove('hidden');
            
            // Remove any existing role classes
            headerElements.playerRoleInfo.classList.remove('role-mafia', 'role-doctor', 'role-investigator', 'role-villager');
            
            // Add role-specific class
            headerElements.playerRoleInfo.classList.add(`role-${role.toLowerCase()}`);
            
            // Update role text
            headerElements.playerRoleDisplay.textContent = role + (isAlive ? '' : ' (Dead)');
            
            // Add dead indicator if player is dead
            if (!isAlive) {
                headerElements.playerRoleDisplay.classList.add('dead');
            } else {
                headerElements.playerRoleDisplay.classList.remove('dead');
            }
        }
    }
    
    function updateRoleBadge(role) {
        if (statusElements.roleDisplay) {
            statusElements.roleDisplay.textContent = role;
            
            // Apply role-specific styling
            switch(role) {
                case 'Mafia':
                    statusElements.roleDisplay.style.backgroundColor = '#8b0000';
                    break;
                case 'Doctor':
                    statusElements.roleDisplay.style.backgroundColor = '#00796b';
                    break;
                case 'Investigator':
                    statusElements.roleDisplay.style.backgroundColor = '#0d47a1';
                    break;
                default:
                    statusElements.roleDisplay.style.backgroundColor = '#555';
            }
        }
    }
    
    // Initialize message input handlers
    function initMessageInput() {
        // Add character counter functionality
        if (discussionElements.messageInput && discussionElements.charCounter) {
            discussionElements.messageInput.addEventListener('input', handleMessageInput);
        }
        
        // Add send message functionality
        if (discussionElements.sendMessageBtn && discussionElements.messageInput) {
            discussionElements.sendMessageBtn.addEventListener('click', sendMessage);
            discussionElements.messageInput.addEventListener('keydown', handleMessageKeydown);
        }
    }
    
    function handleMessageInput() {
        const length = discussionElements.messageInput.value.length;
        discussionElements.charCounter.textContent = `${length}/200`;
        
        if (length > 180) {
            discussionElements.charCounter.style.color = '#f44336';
        } else {
            discussionElements.charCounter.style.color = '';
        }
    }
    
    function handleMessageKeydown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    }

    // -----------------------------------------------------
    // API Communication
    // -----------------------------------------------------
    
    // Authenticate player and get role
    async function authenticatePlayer() {
        try {
            const response = await fetch(`/room/${state.roomId}/auth`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    name: state.playerName
                })
            });
            
            if (!response.ok) {
                throw new Error('Authentication failed');
            }
            
            return await response.json();
        } catch (error) {
            console.error('Authentication error:', error);
            throw error;
        }
    }
    
    // WebSocket Connection

    function connectGameSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/${state.roomId}/${state.playerName}`;
        
        state.socket = new WebSocket(wsUrl);
        
        state.socket.onopen = handleSocketOpen;
        state.socket.onmessage = handleSocketMessage;
        state.socket.onclose = handleSocketClose;
        state.socket.onerror = handleSocketError;
    }
    
    function handleSocketOpen() {
        console.log('Connected to game server');
        
        // Start pinging to keep connection alive
        state.pingInterval = setInterval(() => {
            if (state.socket && state.socket.readyState === WebSocket.OPEN) {
                state.socket.send(JSON.stringify({type: "ping"}));
            }
        }, 30000);
    }
    
    function handleSocketMessage(event) {
        const gameState = JSON.parse(event.data);
        
        // Update game state
        state.gamePhase = gameState.phase;
        state.roundNumber = gameState.round;
        state.isGameOver = gameState.game_status && gameState.game_status.is_over;
        
        // Update UI
        updateGameDisplay(gameState);
    }
    
    function handleSocketClose() {
        console.log('Disconnected from game server');
        clearInterval(state.pingInterval);
        
        // Attempt to reconnect after 2 seconds if game is still in progress
        if (!state.isGameOver) {
            setTimeout(connectGameSocket, 2000);
        }
    }
    
    function handleSocketError(error) {
        console.error('WebSocket error:', error);
    }

    // Game UI Updates

    function updateGameDisplay(gameState) {
        // Update phase display
        if (statusElements.phaseDisplay) {
            statusElements.phaseDisplay.textContent = gameState.phase === 'day' ? 'Day' : 'Night';
        }
        
        // Update round display
        if (statusElements.roundDisplay) {
            statusElements.roundDisplay.textContent = gameState.round;
        }
        
        // Show/hide sections based on phase
        updatePhaseVisibility(gameState.phase);
        
        // Update alive players list
        updatePlayersList(gameState.alive, gameState.phase);
        
        // Update discussion feed
        updateDiscussionFeed(gameState.discussion);
        
        // Update eliminated players
        updateEliminatedPlayers(gameState.eliminated);
        
        // Show deaths from last round
        updateLastDeaths(gameState.last_deaths);
        
        // Update chat input availability based on turn
        updateChatInput(gameState);
        
        // Check for game over
        if (gameState.game_status && gameState.game_status.is_over) {
            showGameOver(gameState.game_status);
        }
        
        // Update action area instructions
        updateActionArea(gameState.phase);
    }
    
    function updatePhaseVisibility(phase) {
        if (phaseElements.daySection && phaseElements.nightSection) {
            if (phase === 'day') {
                phaseElements.daySection.classList.remove('hidden');
                phaseElements.nightSection.classList.add('hidden');
            } else {
                phaseElements.daySection.classList.add('hidden');
                phaseElements.nightSection.classList.remove('hidden');
            }
        }
    }
    
    function updatePlayersList(alivePlayers, currentPhase) {
        if (!playerElements.playersList || !playerElements.actionsDiv) return;
        
        playerElements.playersList.innerHTML = '';
        playerElements.actionsDiv.innerHTML = '';
        
        // Sort players: current player first, then others
        const sortedPlayers = [...alivePlayers].sort((a, b) => {
            if (a === state.playerName) return -1;
            if (b === state.playerName) return 1;
            return a.localeCompare(b);
        });
        
        // Create player list items
        sortedPlayers.forEach(player => {
            // Skip adding current player twice (we'll add at top)
            if (player === state.playerName && sortedPlayers.indexOf(player) !== 0) {
                return;
            }
            
            const li = document.createElement('li');
            li.className = 'player-item';
            
            // Add special styling for current player
            if (player === state.playerName) {
                li.classList.add('current-player');
                li.textContent = `${player} (You)`;
            } else {
                li.textContent = player;
                
                // Add action buttons if player is alive and it's relevant to their role
                if (state.isAlive) {
                    addActionButtonIfNeeded(player, currentPhase);
                }
            }
            
            playerElements.playersList.appendChild(li);
        });
    }
    
    function addActionButtonIfNeeded(targetPlayer, phase) {
        if (!playerElements.actionsDiv) return;
        
        if (phase === 'night') {
            // Night phase actions - role specific
            switch (state.playerRole) {
                case 'Mafia':
                    addActionButton('Kill', targetPlayer, 'night_kill');
                    break;
                case 'Doctor':
                    addActionButton('Protect', targetPlayer, 'night_protect');
                    break;
                case 'Investigator':
                    addActionButton('Investigate', targetPlayer, 'night_investigate');
                    break;
            }
        } else if (phase === 'day') {
            // Day phase - everyone can vote
            addActionButton('Vote', targetPlayer, 'vote');
        }
    }
    
    function addActionButton(text, target, action) {
        const button = document.createElement('button');
        button.className = `action-btn ${action}-btn`;
        button.textContent = `${text} ${target}`;
        button.onclick = () => sendAction(action, target);
        playerElements.actionsDiv.appendChild(button);
    }
    
    function updateDiscussionFeed(messages) {
        if (!discussionElements.discussionFeed || !messages) return;
        
        discussionElements.discussionFeed.innerHTML = '';
        
        messages.forEach(msg => {
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message';
            
            const senderSpan = document.createElement('span');
            senderSpan.className = 'sender';
            senderSpan.textContent = msg[0] + ':';
            
            // Highlight current player's messages
            if (msg[0] === state.playerName) {
                senderSpan.classList.add('own-message');
            }
            
            // Highlight system messages
            if (msg[0] === 'System') {
                messageDiv.classList.add('system-message');
            }
            
            const contentSpan = document.createElement('span');
            contentSpan.className = 'content';
            contentSpan.textContent = ' ' + msg[1];
            
            messageDiv.appendChild(senderSpan);
            messageDiv.appendChild(contentSpan);
            discussionElements.discussionFeed.appendChild(messageDiv);
        });
        
        // Auto-scroll to bottom
        discussionElements.discussionFeed.scrollTop = discussionElements.discussionFeed.scrollHeight;
    }
    
    function updateEliminatedPlayers(eliminatedPlayers) {
        if (!playerElements.eliminatedList || !eliminatedPlayers) return;
        
        playerElements.eliminatedList.innerHTML = '';
        
        if (eliminatedPlayers.length === 0) {
            const li = document.createElement('li');
            li.textContent = 'None';
            playerElements.eliminatedList.appendChild(li);
            return;
        }
        
        eliminatedPlayers.forEach(player => {
            const li = document.createElement('li');
            
            if (player === state.playerName) {
                li.classList.add('current-player');
                li.textContent = `${player} (You)`;
            } else {
                li.textContent = player;
            }
            
            playerElements.eliminatedList.appendChild(li);
        });
    }
    
    function updateLastDeaths(lastDeaths) {
        if (!lastDeaths || lastDeaths.length === 0) return;
        
        const deathsDiv = document.getElementById('lastDeaths');
        if (!deathsDiv) return;
        
        deathsDiv.innerHTML = '';
        
        const heading = document.createElement('h4');
        heading.textContent = 'Recent Deaths:';
        deathsDiv.appendChild(heading);
        
        const list = document.createElement('ul');
        lastDeaths.forEach(player => {
            const li = document.createElement('li');
            li.textContent = player;
            if (player === state.playerName) {
                li.classList.add('current-player');
            }
            list.appendChild(li);
        });
        
        deathsDiv.appendChild(list);
    }
    
    function updateActionArea(phase) {
        if (!playerElements.actionArea) return;
        
        // Clear previous content
        playerElements.actionArea.innerHTML = '';
        
        // Don't show instructions if player is dead
        if (!state.isAlive) {
            const deadText = document.createElement('p');
            deadText.className = 'dead-notice';
            deadText.textContent = 'You are dead. You cannot take actions.';
            playerElements.actionArea.appendChild(deadText);
            return;
        }
        
        if (phase === 'night') {
            const roleText = document.createElement('p');
            roleText.textContent = getNightInstructions();
            playerElements.actionArea.appendChild(roleText);
        } else {
            // Day phase
            const voteText = document.createElement('p');
            voteText.textContent = 'Select a player to vote for elimination.';
            playerElements.actionArea.appendChild(voteText);
        }
    }
    
    function updateChatInput(gameState) {
        if (!discussionElements.chatInputArea || 
            !discussionElements.messageInput || 
            !discussionElements.sendMessageBtn) return;
        
        const isDay = gameState.phase === 'day';
        const isPlayersTurn = gameState.current_speaker === state.playerName;
        
        // Only enable chat during day phase if it's the player's turn and game isn't over
        const enableChat = isDay && isPlayersTurn && !state.isGameOver && state.isAlive;
        
        if (enableChat) {
            discussionElements.chatInputArea.classList.remove('chat-input-disabled');
            discussionElements.messageInput.disabled = false;
            discussionElements.sendMessageBtn.disabled = false;
            
            // Show "Your turn" indicator
            const turnIndicator = document.createElement('div');
            turnIndicator.className = 'your-turn';
            turnIndicator.id = 'turnIndicator';
            turnIndicator.textContent = "It's your turn to speak!";
            
            // Only add if not already present
            if (!document.getElementById('turnIndicator')) {
                discussionElements.chatInputArea.insertBefore(turnIndicator, discussionElements.messageInput);
            }
        } else {
            discussionElements.chatInputArea.classList.add('chat-input-disabled');
            discussionElements.messageInput.disabled = true;
            discussionElements.sendMessageBtn.disabled = true;
            
            // Remove turn indicator if exists
            const turnIndicator = document.getElementById('turnIndicator');
            if (turnIndicator) {
                turnIndicator.remove();
            }
            
            // Show whose turn it is if in day phase
            if (isDay && gameState.current_speaker && !state.isGameOver) {
                const speakerInfo = document.createElement('div');
                speakerInfo.className = 'current-speaker-info';
                speakerInfo.id = 'speakerInfo';
                speakerInfo.textContent = `${gameState.current_speaker} is speaking...`;
                
                if (!document.getElementById('speakerInfo')) {
                    discussionElements.chatInputArea.insertBefore(speakerInfo, discussionElements.messageInput);
                }
            }
        }
    }
    
    function showGameOver(gameStatus) {
        // Create game over overlay if not exists
        if (!document.getElementById('gameOverlay')) {
            const overlay = document.createElement('div');
            overlay.id = 'gameOverlay';
            overlay.className = 'game-over-overlay';
            
            const content = document.createElement('div');
            content.className = 'game-over-content';
            
            const heading = document.createElement('h2');
            heading.textContent = 'Game Over';
            
            const winner = document.createElement('p');
            winner.className = 'game-winner';
            winner.textContent = gameStatus.winner 
                ? `${gameStatus.winner} Win!` 
                : 'Game Ended in a Draw';
            
            const message = document.createElement('p');
            message.textContent = gameStatus.message || '';
            
            const returnButton = document.createElement('button');
            returnButton.className = 'btn btn-primary';
            returnButton.textContent = 'Return to Homepage';
            returnButton.onclick = () => window.location.href = '/';
            
            content.appendChild(heading);
            content.appendChild(winner);
            content.appendChild(message);
            content.appendChild(returnButton);
            overlay.appendChild(content);
            
            document.body.appendChild(overlay);
        }
    }
    
    // -----------------------------------------------------
    // Actions
    // -----------------------------------------------------
    
    function sendAction(action, target) {
        if (!state.socket || state.socket.readyState !== WebSocket.OPEN) return;
        
        const actionData = {
            action: action,
            target: target
        };
        
        state.socket.send(JSON.stringify(actionData));
        
        // Disable action buttons after selection
        disableActionButtons();
    }
    
    function sendMessage() {
        if (!state.socket || state.socket.readyState !== WebSocket.OPEN) return;
        
        const message = discussionElements.messageInput.value.trim();
        if (!message) return;
        
        const messageData = {
            action: 'send_message',
            message: message
        };
        
        state.socket.send(JSON.stringify(messageData));
        
        // Clear input after sending
        discussionElements.messageInput.value = '';
        if (discussionElements.charCounter) {
            discussionElements.charCounter.textContent = '0/200';
        }
        
        // Disable input until next turn
        discussionElements.chatInputArea.classList.add('chat-input-disabled');
        discussionElements.messageInput.disabled = true;
        discussionElements.sendMessageBtn.disabled = true;
    }
    
    function disableActionButtons() {
        const buttons = document.querySelectorAll('.action-btn');
        buttons.forEach(btn => {
            btn.disabled = true;
            btn.classList.add('action-selected');
        });
    }
    
    // Utility Functions

    function getNightInstructions() {
        switch (state.playerRole) {
            case 'Mafia':
                return 'Choose a player to eliminate.';
            case 'Doctor':
                return 'Choose a player to protect tonight.';
            case 'Investigator':
                return 'Choose a player to investigate.';
            default:
                return 'You have no action during the night phase.';
        }
    }
    
    function cleanupResources() {
        if (state.socket) {
            state.socket.close();
        }
        
        if (state.pingInterval) {
            clearInterval(state.pingInterval);
        }
    }
});
