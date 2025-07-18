document.addEventListener('DOMContentLoaded', function() {
    // Initialize game state
    const state = {
        socket: null,
        pingInterval: null,
        playerName: window.PLAYER_NAME || localStorage.getItem('playerName'),
        playerRole: null,
        isAlive: true,
        roomId: window.ROOM_ID || localStorage.getItem('roomId'),
        gamePhase: null,
        roundNumber: 1,
        isGameOver: false,
        timerInterval: null,
        timerSeconds: null,
        currentPhase: null,
        currentSubPhase: null,
        tiedCandidates: []
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
        gameStatus: document.getElementById('gameStatus'),
        mafiaCountDisplay: document.getElementById('mafiaCountDisplay')
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
        nightSection: document.getElementById('nightSection'),
        lastDeaths: document.getElementById('lastDeaths')
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

    function enableRevoteDiscussionMode(tiedCandidates) {
        // Show explanation in action area about the tied vote
        const actionArea = document.getElementById('actionArea');
        if (actionArea) {
            actionArea.innerHTML = '';
            const revoteMsg = document.createElement('p');
            revoteMsg.className = 'revote-notice';
            revoteMsg.innerHTML = `<strong>Vote tied!</strong> Discussion about tied candidates: 
                              <span class="tied-players">${tiedCandidates.join(', ')}</span>`;
            actionArea.appendChild(revoteMsg);
        }
        
        // Hide ALL vote buttons during revote discussion phase
        document.querySelectorAll('.action-btn.vote-btn').forEach(btn => {
            btn.style.display = 'none';
        });
    }

    function enableRevoteVotingMode(tiedCandidates) {
        // Reuse the existing updateRevoteUI function for revote voting
        updateRevoteUI(tiedCandidates);
        
        // Show vote buttons only for tied candidates
        document.querySelectorAll('.vote-btn').forEach(btn => {
            const targetName = btn.getAttribute('data-target');
            if (tiedCandidates.includes(targetName)) {
                btn.style.display = 'inline-block';
                btn.disabled = false;
                btn.classList.remove('action-selected');
                btn.classList.add('revote-btn');
            } else {
                btn.style.display = 'none';
            }
        });
    }
    
    function updatePlayerInfoHeader() {
        if (headerElements.playerNameDisplay) {
            headerElements.playerNameDisplay.textContent = state.playerName || 'Anonymous';
        }
    }
    
    function updateRoleInfo(role, isAlive) {
        if (!headerElements.playerRoleInfo || !headerElements.playerRoleDisplay) {
            return;
        }
        
        headerElements.playerRoleInfo.classList.remove('hidden');
        
        // Remove any existing role classes
        headerElements.playerRoleInfo.classList.remove(
            'role-mafia', 'role-doctor', 'role-investigator', 'role-villager'
        );
        
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
        
        // Update role display if available
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
        try {
            console.log("Received data:", event.data);
            const gameState = JSON.parse(event.data);
            
            // Check if player is now dead
            if (state.isAlive && gameState.eliminated && gameState.eliminated.includes(state.playerName)) {
                state.isAlive = false;
                
                // Show death notification
                showDeathNotification();
                
                // Update role info to show dead status
                updateRoleInfo(state.playerRole, false);
            }
            
            // Update game state
            state.gamePhase = gameState.phase;
            state.roundNumber = gameState.round;
            state.isGameOver = gameState?.game_status?.is_over || false;
            state.timer = gameState?.timer || 0;
            state.subPhase = gameState?.sub_phase || '';
            state.fellowMafia = gameState?.fellow_mafia || [];

            // Update UI
            updateGameDisplay(gameState);
        } catch (error) {
            console.error('Error processing message:', error);
        }
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
        if (gameState.game_status && gameState.game_status.is_over) {
            showGameOver(gameState.game_status);
            return; 
        }
        
        updateLastDeaths(gameState.last_deaths);

        updateLastVotedOut(gameState.last_voted_out, gameState);
        
        if (statusElements.phaseDisplay) {
            statusElements.phaseDisplay.textContent = gameState.phase === 'day' ? 'Day' : 'Night';
        }
        
        if (statusElements.roundDisplay) {
            statusElements.roundDisplay.textContent = gameState.round;
        }
        
        if (statusElements.mafiaCountDisplay) {
            statusElements.mafiaCountDisplay.textContent = gameState.mafia_count || '?';
        }
        
        // Show/hide sections based on phase
        updatePhaseVisibility(gameState.phase);
        
        // Update player lists
        updatePlayersList(gameState.alive, gameState.phase, gameState.eliminated);
        
        // Update discussion feed
        updateDiscussionFeed(gameState.discussion);
                
        // Update chat input availability
        updateChatInput(gameState);
        
        // Update action area instructions
        updateActionArea(gameState.phase);
        
        // Update investigation results if available
        if (state.playerRole === 'Investigator' && gameState.investigation_results && 
            gameState.investigation_results.length > 0) {
            updateInvestigationResults(gameState.investigation_results);
        } else {
            const container = document.getElementById('investigationResults');
            if (container) {
                container.style.display = 'none';
            }
        }
        
        // Update timer display if present
        if (gameState.timer !== undefined) {
            updateTimerDisplay(gameState.timer, gameState.phase, gameState.sub_phase, true);
        }
        
        // Update phase-specific UI based on sub_phase
        if (gameState.phase === 'day') {
            console.log("Current sub-phase:", gameState.sub_phase);
            
            if (gameState.sub_phase === 'discussion') {
                enableDiscussionMode();
            } else if (gameState.sub_phase === 'voting') {
                enableVotingMode();
            } else if (gameState.sub_phase === 'revote_discussion') {
                enableRevoteDiscussionMode(gameState.tied_candidates);
            } else if (gameState.sub_phase === 'revote_voting') {
                enableRevoteVotingMode(gameState.tied_candidates);
            }
        }
        
        // Store tied candidates info
        state.tiedCandidates = gameState.tied_candidates || [];
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
    
    function updatePlayersList(alivePlayers, currentPhase, deadPlayers = []) {
        if (!playerElements.playersList) {
            playerElements.playersList = document.createElement('ul');
            playerElements.playersList.id = 'playersList';
            playerElements.playersList.className = 'player-list';
            playerElements.playersArea.appendChild(playerElements.playersList);
        }
        
        // Clear the list
        playerElements.playersList.innerHTML = '';
        
        // Combined list of all players for display
        const allPlayers = [];
        
        // Add alive players
        if (alivePlayers && alivePlayers.length) {
            alivePlayers.forEach(player => {
                allPlayers.push({ name: player, isDead: false });
            });
        }
        
        // Add dead players
        if (deadPlayers && deadPlayers.length) {
            deadPlayers.forEach(player => {
                allPlayers.push({ name: player, isDead: true });
            });
        }
        
        // Sort players: current player first, then alive, then dead
        allPlayers.sort((a, b) => {
            // Current player comes first
            if (a.name === state.playerName) return -1;
            if (b.name === state.playerName) return 1;
            
            // Then alive players
            if (a.isDead !== b.isDead) return a.isDead ? 1 : -1;
            
            // Then alphabetically
            return a.name.localeCompare(b.name);
        });
        
        // Create player list items
        allPlayers.forEach(player => {
            const li = document.createElement('li');
            li.className = 'player-item';
            
            // Create a player info div to contain name and button
            const playerInfoDiv = document.createElement('div');
            playerInfoDiv.className = 'player-info-row';
            if (player.isDead) {
                playerInfoDiv.classList.add('player-dead');
            }
            
            // Add player name span
            const nameSpan = document.createElement('span');
            nameSpan.className = 'player-name';
            
            // Highlight fellow mafia members if the current player is mafia
            if (state.playerRole === 'Mafia' && state.fellowMafia && 
                state.fellowMafia.includes(player.name)) {
                playerInfoDiv.classList.add('fellow-mafia');
                
                if (!nameSpan.querySelector('.mafia-indicator')) {
                    const mafiaIndicator = document.createElement('span');
                    mafiaIndicator.className = 'mafia-indicator';
                }
            }
            
            // Add death indicator for dead players
            if (player.isDead) {
                const deathSign = document.createElement('span');
                deathSign.className = 'player-death-sign';
                deathSign.textContent = '☠️ ';
                deathSign.setAttribute('title', 'Eliminated');
                nameSpan.appendChild(deathSign);
            }
            
            // Add special styling for current player
            if (player.name === state.playerName) {
                nameSpan.classList.add('current-player');
                nameSpan.appendChild(document.createTextNode(`${player.name} (You)`));
            } else {
                nameSpan.appendChild(document.createTextNode(player.name));
            }
            
            playerInfoDiv.appendChild(nameSpan);
            
            // Add action button directly next to name if applicable
            if (!player.isDead && player.name !== state.playerName && state.isAlive) {
                addActionButtonToElement(player.name, currentPhase, playerInfoDiv);
            }
            
            li.appendChild(playerInfoDiv);
            playerElements.playersList.appendChild(li);
        });
    }
    
    function addActionButtonToElement(targetPlayer, phase, parentElement) {
        if (phase === 'night') {
            // Night phase actions - role specific
            switch (state.playerRole) {
                case 'Mafia':
                    // Don't allow targeting fellow mafia members
                    if (!state.fellowMafia || !state.fellowMafia.includes(targetPlayer)) {
                        addActionButton('Kill', targetPlayer, 'night_kill', parentElement);
                    } else {
                        // Add visual indicator that this is a teammate instead
                        const teamIndicator = document.createElement('span');
                        teamIndicator.className = 'team-indicator';
                        teamIndicator.textContent = '🤝 Teammate';
                        parentElement.appendChild(teamIndicator);
                    }
                    break;
                case 'Doctor':
                    addActionButton('Protect', targetPlayer, 'night_protect', parentElement);
                    break;
                case 'Investigator':
                    addActionButton('Investigate', targetPlayer, 'night_investigate', parentElement);
                    break;
            }
        } else if (phase === 'day') {
            // Day phase - everyone can vote
            addActionButton('Vote', targetPlayer, 'vote', parentElement);
        }
    }
    
    function addActionButton(text, target, action, parentElement) {
        const button = document.createElement('button');
        button.className = `action-btn ${action}-btn`;
        button.textContent = text;
        button.setAttribute('data-target', target);
        button.onclick = () => sendAction(action, target);
        parentElement.appendChild(button);
    }
    
    function updateDiscussionFeed(messages) {
        if (!discussionElements.discussionFeed) return;
        
        console.log("Updating discussion feed with:", messages);
        
        // Clear existing messages only if we have new ones to display
        if (messages && messages.length > 0) {
            discussionElements.discussionFeed.innerHTML = '';
            
            messages.forEach(msg => {
                // Check if message format is valid (array with sender and content)
                if (!Array.isArray(msg) || msg.length < 2) {
                    console.error("Invalid message format:", msg);
                    return;
                }
                
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
        if (!lastDeaths || lastDeaths.length === 0 || !phaseElements.lastDeaths) {
            // Hide the container when there are no deaths
            if (phaseElements.lastDeaths) {
                phaseElements.lastDeaths.style.display = 'none';
            }
            return;
        }
        
        // Show the container
        phaseElements.lastDeaths.style.display = 'block';
        phaseElements.lastDeaths.innerHTML = '';
        
        const heading = document.createElement('h3');
        heading.textContent = 'Recent Deaths';
        phaseElements.lastDeaths.appendChild(heading);
        
        const list = document.createElement('ul');
        list.className = 'deaths-list';
        
        lastDeaths.forEach(player => {
            const li = document.createElement('li');
            li.className = 'death-item';
            
            if (player === state.playerName) {
                li.classList.add('current-player');
            }
            
            const emoji = document.createElement('span');
            emoji.className = 'death-emoji';
            emoji.textContent = '☠️';
            
            li.appendChild(emoji);
            li.appendChild(document.createTextNode(player));
            list.appendChild(li);
        });
        
        phaseElements.lastDeaths.appendChild(list);
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
            let instructions = "Wait for the night phase to end.";
            switch (state.playerRole) {
                case 'Mafia':
                    instructions = "Select a player to eliminate tonight.";
                    break;
                case 'Doctor':
                    instructions = "Select a player to protect tonight.";
                    break;
                case 'Investigator':
                    instructions = "Select a player to investigate tonight.";
                    break;
                default:
                    instructions = "You have no special actions during the night.";
            }
            roleText.textContent = instructions;
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
        
        // Keep track of the current speaker for UI updates
        if (state.currentSpeaker !== gameState.current_speaker) {
            state.currentSpeaker = gameState.current_speaker;
        }
        
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
            
            const speakerInfo = document.getElementById('speakerInfo');
            if (speakerInfo) {
                speakerInfo.remove();
            }
        } else {
            discussionElements.chatInputArea.classList.add('chat-input-disabled');
            discussionElements.messageInput.disabled = true;
            discussionElements.sendMessageBtn.disabled = true;
            
            // Remove turn indicator
            const turnIndicator = document.getElementById('turnIndicator');
            if (turnIndicator) {
                turnIndicator.remove();
            }
            
            // Show current speaker info in day phase
            if (isDay && gameState.current_speaker && !state.isGameOver) {
                const existingSpeakerInfo = document.getElementById('speakerInfo');
                if (existingSpeakerInfo) {
                    existingSpeakerInfo.remove();
                }
                
                const speakerInfo = document.createElement('div');
                speakerInfo.className = 'current-speaker-info';
                speakerInfo.id = 'speakerInfo';
                speakerInfo.textContent = `${gameState.current_speaker} is speaking...`;
                
                if (discussionElements.chatInputArea && discussionElements.messageInput) {
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
            
            const winnerText = gameStatus.winner 
                ? `${gameStatus.winner} Win!` 
                : 'Game Ended in a Draw';
                
            const winner = document.createElement('div');
            winner.className = 'game-winner';
            winner.textContent = winnerText;
            
            const emojiSpan = document.createElement('div');
            emojiSpan.style.fontSize = '3rem';
            emojiSpan.style.marginBottom = '15px';
            
            // Add different emojis based on winner
            if (gameStatus.winner === 'Mafia') {
                emojiSpan.textContent = '😈';
            } else if (gameStatus.winner === 'Villagers') {
                emojiSpan.textContent = '👨‍👩‍👧‍👦';
            } else {
                emojiSpan.textContent = '🤝';
            }
            
            const message = document.createElement('p');
            message.textContent = gameStatus.message || '';
            
            const resultDetails = document.createElement('div');
            resultDetails.className = 'game-result-details';
            
            if (gameStatus.mafia_players) {
                const mafiaList = document.createElement('p');
                mafiaList.innerHTML = `<strong>Mafia players were:</strong> ${gameStatus.mafia_players.join(', ')}`;
                resultDetails.appendChild(mafiaList);
            }
            
            const returnButton = document.createElement('button');
            returnButton.className = 'btn btn-primary';
            returnButton.textContent = 'Return to Homepage';
            returnButton.onclick = () => window.location.href = '/';
            
            content.appendChild(heading);
            content.appendChild(emojiSpan);
            content.appendChild(winner);
            content.appendChild(message);
            if (resultDetails.children.length > 0) {
                content.appendChild(resultDetails);
            }
            content.appendChild(returnButton);
            overlay.appendChild(content);
            
            document.body.appendChild(overlay);
        }
    }
    
    // Message Input Handling
    
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
        discussionElements.charCounter.textContent = `${length}/150`;
        
        if (length > 125) {
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
    
    // Game Actions
    
    function sendAction(action, target) {
        if (!state.socket || state.socket.readyState !== WebSocket.OPEN) return;
        
        const actionData = {
            action: action,
            target: target
        };
        
        state.socket.send(JSON.stringify(actionData));
        
        console.log(`Action sent: ${action} on ${target}`);

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
        
        try {
            state.socket.send(JSON.stringify(messageData));
            
            // Debug message
            const testMsg = document.createElement('div');
            testMsg.textContent = `DEBUG: Message "${message}" sent to server`;
            testMsg.style.color = 'green';
            discussionElements.discussionFeed.appendChild(testMsg);
            
            // Clear input after sending
            discussionElements.messageInput.value = '';
            if (discussionElements.charCounter) {
                discussionElements.charCounter.textContent = '0/150';
                discussionElements.charCounter.style.color = '';
            }
            
            // Disable input until next turn
            discussionElements.chatInputArea.classList.add('chat-input-disabled');
            discussionElements.messageInput.disabled = true;
            discussionElements.sendMessageBtn.disabled = true;
            
        } catch (error) {
            console.error("Error sending message:", error);
        }
    }
    
    function disableActionButtons() {
        const buttons = document.querySelectorAll('.action-btn');
        buttons.forEach(btn => {
            btn.disabled = true;
            btn.classList.add('action-selected');
        });
        
        // Add feedback that action was registered
        const feedback = document.createElement('div');
        feedback.className = 'action-feedback';
        feedback.textContent = 'Action registered. Waiting for other players...';
        
        if (playerElements.actionsDiv && !document.querySelector('.action-feedback')) {
            playerElements.actionsDiv.appendChild(feedback);
        }
    }

    function cleanupResources() {
        console.log('Cleaning up resources...');
        
        // Close WebSocket connection if open
        if (state.socket) {
            state.socket.close();
        }
        
        // Clear any active intervals
        if (state.pingInterval) {
            clearInterval(state.pingInterval);
        }
        
        // Clear timer interval
        if (state.timerInterval) {
            clearInterval(state.timerInterval);
        }
    }
    
    async function advanceGamePhase() {
        try {
            console.log("Attempting to advance game phase...");
            const response = await fetch(`/room/${state.roomId}/advance_phase`, {
                method: 'POST'
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                console.error("Failed to advance phase:", errorData);
                return;
            }
            
            console.log("Game phase advanced successfully");
        } catch (error) {
            console.error("Error advancing game phase:", error);
        }
    }
    
    function updateInvestigationResults(results) {
        const container = document.getElementById('investigationResults');
        if (!container || !results || !results.length) {
            if (container) container.style.display = 'none';
            return;
        }
        
        container.style.display = 'block';
        container.innerHTML = '';
        
        const heading = document.createElement('h3');
        heading.textContent = 'Investigation Results';
        container.appendChild(heading);
        
        const resultsList = document.createElement('div');
        resultsList.className = 'investigation-results-list';
        
        // Process results in reverse order so newest are at the top
        [...results].reverse().forEach(result => {
            const resultDiv = document.createElement('div');
            resultDiv.className = 'investigation-result';
            
            const emoji = document.createElement('span');
            emoji.className = 'investigation-emoji';
            emoji.textContent = '🔍';
            resultDiv.appendChild(emoji);
            
            // Player name
            const nameDiv = document.createElement('div');
            nameDiv.className = 'investigated-name';
            nameDiv.innerHTML = `<strong>${result.name}</strong>`;
            resultDiv.appendChild(nameDiv);
            
            // Show the investigation result with appropriate styling
            const resultBadge = document.createElement('span');
            resultBadge.className = `result ${result.is_mafia ? 'mafia' : 'not-mafia'}`;
            resultBadge.textContent = result.is_mafia ? 'Mafia' : 'Not Mafia';
            resultDiv.appendChild(resultBadge);
            resultsList.appendChild(resultDiv);
        });
        
        container.appendChild(resultsList);
    }
    
    function updateTimerDisplay(seconds, phase, subPhase, isServerUpdate = false) {
        // Create timer element if it doesn't exist
        let timerElement = document.getElementById('phaseTimer');
        if (!timerElement) {
            timerElement = document.createElement('div');
            timerElement.id = 'phaseTimer';
            timerElement.className = 'phase-timer';
            
            // Add it to the appropriate container
            const container = document.querySelector('.game-header .stats');
            if (container) {
                container.appendChild(timerElement);
            }
        }

        // If this is a server update, update our local timer and restart the interval
        if (isServerUpdate) {
            // Clear any existing timer
            if (state.timerInterval) {
                clearInterval(state.timerInterval);
                state.timerInterval = null;
            }

            // Update state
            state.timerSeconds = seconds;
            state.currentPhase = phase;
            state.currentSubPhase = subPhase;

            // Start a new interval to update every second
            state.timerInterval = setInterval(function() {
                if (state.timerSeconds > 0) {
                    state.timerSeconds--;
                    updateTimerDisplay(state.timerSeconds, state.currentPhase, state.currentSubPhase);
                } else {
                    // Timer has reached zero, clear the interval
                    clearInterval(state.timerInterval);
                    state.timerInterval = null;
                }
            }, 1000);
        }
        
        // Format time as MM:SS
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = seconds % 60;
        const timeString = `${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
        
        // Update timer text and style based on phase
        if (phase === 'night') {
            timerElement.textContent = `Night ends: ${timeString}`;
            timerElement.className = 'phase-timer night-timer';
        } else {
            // Day phase with various sub-phases
            let phaseText = 'Day';
            if (subPhase === 'discussion') {
                phaseText = 'Discussion';
            } else if (subPhase === 'voting') {
                phaseText = 'Voting';
            } else if (subPhase === 'revote_discussion') {
                phaseText = 'Revote Discussion';
            } else if (subPhase === 'revote_voting') {
                phaseText = 'Revoting';
            }
            
            timerElement.textContent = `${phaseText} ends: ${timeString}`;
            timerElement.className = `phase-timer day-timer ${subPhase}-timer`;
        }
        
        if (seconds < 10) {
            timerElement.classList.add('timer-warning');
        } else {
            timerElement.classList.remove('timer-warning');
        }
        
        if (phase === 'night') {
            timerElement.className = 'phase-timer night-timer';
        } else if (subPhase === 'discussion') {
            timerElement.className = 'phase-timer day-timer discussion-timer';
        } else if (subPhase === 'voting') {
            timerElement.className = 'phase-timer day-timer voting-timer';
        } else if (subPhase === 'revote_discussion') {
            timerElement.className = 'phase-timer day-timer revote_discussion-timer';
        } else if (subPhase === 'revote_voting') {
            timerElement.className = 'phase-timer day-timer revote_voting-timer';
        }
        
        if (seconds < 10) {
            timerElement.classList.add('timer-warning');
        }
    }

    function enableDiscussionMode() {
        // Show explanation in action area
        const actionArea = document.getElementById('actionArea');
        if (actionArea) {
            actionArea.innerHTML = '<p>Discussion in progress. Voting will begin when the timer expires.</p>';
        }
        
        // Hide vote buttons
        document.querySelectorAll('.action-btn.vote-btn').forEach(btn => {
            btn.style.display = 'none';
        });
    }

    function enableVotingMode() {
        // Code for enabling voting mode
        const chatInputArea = document.getElementById('chatInputArea');
        if (chatInputArea) {
            chatInputArea.classList.add('chat-input-disabled');
        }
        
        const messageInput = document.getElementById('messageInput');
        if (messageInput) {
            messageInput.disabled = true;
        }
        
        const sendMessageBtn = document.getElementById('sendMessageBtn');
        if (sendMessageBtn) {
            sendMessageBtn.disabled = true;
        }
        
        // Show voting instructions
        const actionArea = document.getElementById('actionArea');
        if (actionArea) {
            actionArea.innerHTML = '<p class="voting-active">Discussion has ended. Cast your vote.</p>';
        }
        
        // Show vote buttons for alive players
        document.querySelectorAll('.action-btn.vote-btn').forEach(btn => {
            const targetName = btn.getAttribute('data-target');
            const isAlive = !btn.closest('.player-info-row')?.classList.contains('player-dead');
            if (targetName !== state.playerName && isAlive) {
                btn.style.display = 'inline-block';
                
                btn.disabled = false;
                btn.classList.remove('action-selected');
                btn.classList.remove('revote-btn');
            } else {
                btn.style.display = 'none';
            }
        });
        
        const feedbackMsg = document.querySelector('.action-feedback');
        if (feedbackMsg) {
            feedbackMsg.remove();
        }
    }
    
    function updateLastVotedOut(votedOutPlayer, gameState) {
        const container = document.getElementById('lastVotedOut');
        if (!container) return;
        
        // Hide container if no player was voted out
        if (!votedOutPlayer) {
            container.style.display = 'none';
            return;
        }
        
        // Show the container
        container.style.display = 'block';
        container.innerHTML = '';
        
        const heading = document.createElement('h3');
        heading.textContent = 'Last Voted Out';
        container.appendChild(heading);
        
        const votedOutDiv = document.createElement('div');
        votedOutDiv.className = 'voted-out-item';
        
        if (votedOutPlayer === state.playerName) {
            votedOutDiv.classList.add('current-player');
        }
        
        const emoji = document.createElement('span');
        emoji.className = 'voted-out-emoji';
        emoji.textContent = '🗳️';
        votedOutDiv.appendChild(emoji);
        
        // Player name in a wrapper
        const nameWrapper = document.createElement('div');
        nameWrapper.className = 'voted-out-name';
        nameWrapper.textContent = votedOutPlayer;
        votedOutDiv.appendChild(nameWrapper);
        
        // Check if this player was Mafia
        const isMafia = (gameState.eliminated_roles && gameState.eliminated_roles[votedOutPlayer] === "Mafia");

        const roleBadge = document.createElement('span');
        roleBadge.className = `role-badge ${isMafia ? 'mafia-badge' : 'villager-badge'}`;
        roleBadge.textContent = isMafia ? 'Mafia' : 'Not Mafia';
        votedOutDiv.appendChild(roleBadge);
        
        container.appendChild(votedOutDiv);
    }
    
    function updateRevoteUI(tiedCandidates) {
        // Show revote message
        const actionArea = document.getElementById('actionArea');
        if (actionArea) {
            actionArea.innerHTML = '';
            const revoteMsg = document.createElement('p');
            revoteMsg.className = 'revote-notice';
            revoteMsg.innerHTML = `<strong>Vote tied!</strong> Please vote again between: 
                                  <span class="tied-players">${tiedCandidates.join(', ')}</span>`;
            actionArea.appendChild(revoteMsg);
        }
        
        // Only show vote buttons for tied candidates
        document.querySelectorAll('.vote-btn').forEach(btn => {
            const targetName = btn.getAttribute('data-target');
            if (tiedCandidates.includes(targetName)) {
                btn.style.display = 'inline-block';
                btn.classList.add('revote-btn');
            } else {
                btn.style.display = 'none';
            }
        });
    }
    
    // New function to show death notification
    function showDeathNotification() {
        // Create overlay for death notification
        const deathOverlay = document.createElement('div');
        deathOverlay.className = 'death-overlay';
        
        const deathMessage = document.createElement('div');
        deathMessage.className = 'death-message';
        
        // Create death announcement
        const heading = document.createElement('h2');
        heading.textContent = 'You Are Dead';
        
        const deathIcon = document.createElement('div');
        deathIcon.className = 'death-icon';
        deathIcon.textContent = '☠️';
        
        const message = document.createElement('p');
        message.textContent = 'You have been eliminated from the game.';
        message.className = 'death-text';
        
        const subMessage = document.createElement('p');
        subMessage.textContent = 'You may continue watching the game but cannot participate.';
        subMessage.className = 'death-subtext';
        
        const continueBtn = document.createElement('button');
        continueBtn.textContent = 'Continue Watching';
        continueBtn.className = 'btn btn-primary';
        
        setTimeout(() => {
            deathOverlay.classList.add('show-overlay');
        }, 10);
        
        continueBtn.onclick = () => {
            deathOverlay.classList.remove('show-overlay');
            deathOverlay.classList.add('hide-overlay');
            setTimeout(() => {
                if (deathOverlay.parentNode) {
                    deathOverlay.parentNode.removeChild(deathOverlay);
                }
            }, 500);
        };
        
        deathMessage.appendChild(heading);
        deathMessage.appendChild(deathIcon);
        deathMessage.appendChild(message);
        deathMessage.appendChild(subMessage);
        deathMessage.appendChild(continueBtn);
        deathOverlay.appendChild(deathMessage);
        
        document.body.appendChild(deathOverlay);
        
        document.body.classList.add('player-dead');
    }
});
