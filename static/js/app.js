document.addEventListener('DOMContentLoaded', function() {

    class ConnectionManager {
        constructor(roomId, playerName) {
            this.roomId = roomId;
            this.playerName = playerName;
            this.socket = null;
            this.pingInterval = null;
            this.reconnectTimer = null;
            this.isClosing = false;
            this.connectionType = 'lobby'; // or 'game'
            
            // Setup visibility change detection
            document.addEventListener('visibilitychange', this.handleVisibilityChange.bind(this));
            window.addEventListener('beforeunload', this.handleBeforeUnload.bind(this));
        }
        
        connect(type = 'lobby') {
            if (this.socket && this.socket.readyState <= 1) return; // Already connecting or connected
            
            this.connectionType = type;
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const path = type === 'lobby' ? 'lobby/ws' : 'ws';
            const wsUrl = `${protocol}//${window.location.host}/${path}/${this.roomId}/${this.playerName}`;
            
            console.log(`Connecting to ${wsUrl}`);
            this.socket = new WebSocket(wsUrl);
            
            this.socket.onopen = () => {
                console.log('Connected to server');
                this.startPingInterval();
                
                // Cancel any pending reconnect
                if (this.reconnectTimer) {
                    clearTimeout(this.reconnectTimer);
                    this.reconnectTimer = null;
                }
                
                // Notify the server if we're reconnecting
                this.socket.send(JSON.stringify({
                    type: "connection_status",
                    status: "reconnected"
                }));
            };
            
            this.socket.onclose = (event) => {
                console.log('Connection closed:', event);
                this.stopPingInterval();
                
                // Don't reconnect if we're intentionally closing
                if (!this.isClosing && document.visibilityState === 'visible') {
                    this.scheduleReconnect();
                }
            };
            
            this.socket.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
            
            this.socket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    // Handle message - you'll need to customize this
                    if (this.onMessage) this.onMessage(data);
                } catch (error) {
                    console.error('Error handling message:', error);
                }
            };
            
            return this.socket;
        }
        
        scheduleReconnect() {
            // Reconnect after 2 seconds if not already scheduled
            if (!this.reconnectTimer) {
                console.log('Scheduling reconnect in 2 seconds');
                this.reconnectTimer = setTimeout(() => {
                    this.reconnectTimer = null;
                    this.connect(this.connectionType);
                }, 2000);
            }
        }
        
        startPingInterval() {
            this.stopPingInterval(); // Clear any existing interval
            
            this.pingInterval = setInterval(() => {
                if (this.socket && this.socket.readyState === WebSocket.OPEN) {
                    this.socket.send(JSON.stringify({type: "ping"}));
                }
            }, 30000); // Every 30 seconds
        }
        
        stopPingInterval() {
            if (this.pingInterval) {
                clearInterval(this.pingInterval);
                this.pingInterval = null;
            }
        }
        
        handleVisibilityChange() {
            console.log('Visibility changed:', document.visibilityState);
            
            if (document.visibilityState === 'visible') {
                // Page is visible again - reconnect if needed
                if (!this.socket || this.socket.readyState > 1) {
                    this.connect(this.connectionType);
                }
            } else {
                // Page is hidden - we'll keep the connection but notify the server
                if (this.socket && this.socket.readyState === WebSocket.OPEN) {
                    this.socket.send(JSON.stringify({
                        type: "visibility_change",
                        state: "hidden"
                    }));
                }
            }
        }
        
        handleBeforeUnload(event) {
            // Browser is actually closing
            this.isClosing = true;
            
            if (this.socket && this.socket.readyState === WebSocket.OPEN) {
                // Send a closure notification
                this.socket.send(JSON.stringify({
                    type: "browser_closing",
                    roomId: this.roomId,
                    playerName: this.playerName
                }));
            }
        }
        
        send(data) {
            if (this.socket && this.socket.readyState === WebSocket.OPEN) {
                this.socket.send(JSON.stringify(data));
                return true;
            }
            return false;
        }
        
        close() {
            this.isClosing = true;
            this.stopPingInterval();
            
            if (this.socket) {
                this.socket.close();
                this.socket = null;
            }
            
            if (this.reconnectTimer) {
                clearTimeout(this.reconnectTimer);
                this.reconnectTimer = null;
            }
        }
    }

    const state = {
        isRoomOwner: false,
        intervalId: null,
        socket: null,
        pingInterval: null
    };

    // Home page elements
    const homePage = {
        createRoomBtn: document.getElementById('createRoomBtn'),
        joinRoomBtn: document.getElementById('joinRoomBtn'),
        playerNameInput: document.getElementById('playerName'),
        roomIdInput: document.getElementById('roomId'),
        errorMessage: document.getElementById('errorMessage')
    };
    
    // Lobby page elements
    const lobbyPage = {
        roomIdDisplay: document.getElementById('roomIdDisplay'),
        playersList: document.getElementById('playersList'),
        playerCount: document.getElementById('playerCount'),
        startGameBtn: document.getElementById('startGameBtn'),
        copyRoomBtn: document.getElementById('copyRoomIdBtn'),
        chatContainer: document.getElementById('lobbyChatMessages')
    };

    // Initialize home page functionality
    initHomePage();
    
    // Initialize lobby page functionality
    initLobbyPage();
    
    // Clean up resources on page unload
    window.addEventListener('beforeunload', cleanupResources);
    

    function initHomePage() {
        // Initialize room creation
        if (homePage.createRoomBtn) {
            homePage.createRoomBtn.addEventListener('click', handleCreateRoom);
            
            // Enter key support for player name input
            if (homePage.playerNameInput) {
                homePage.playerNameInput.addEventListener('keydown', handleNameInputKeydown);
            }
        }
        
        // Initialize room joining
        if (homePage.joinRoomBtn) {
            homePage.joinRoomBtn.addEventListener('click', handleJoinRoom);
            
            // Enter key support for room ID input
            if (homePage.roomIdInput) {
                homePage.roomIdInput.addEventListener('keydown', handleRoomIdKeydown);
            }
        }
    }
    
    async function handleCreateRoom() {
        const playerName = homePage.playerNameInput.value.trim();
        
        if (!playerName) {
            showError('Please enter your name!');
            return;
        }
        
        try {
            const response = await fetch('/room', { method: 'POST' });
            
            if (!response.ok) {
                throw new Error('Failed to create room');
            }
            
            const data = await response.json();
            await joinRoom(data.room_id, playerName);
            
        } catch (error) {
            showError(error.message);
        }
    }
    
    async function handleJoinRoom() {
        const playerName = homePage.playerNameInput.value.trim();
        const roomId = homePage.roomIdInput.value.trim();
        
        if (!playerName || !roomId) {
            showError('Please enter your name and room ID!');
            return;
        }
        
        await joinRoom(roomId, playerName);
    }
    
    function handleNameInputKeydown(event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            
            // If room ID has content, join that room
            if (homePage.roomIdInput && homePage.roomIdInput.value.trim()) {
                homePage.joinRoomBtn.click();
            } else {
                // Otherwise create new room
                homePage.createRoomBtn.click();
            }
        }
    }
    
    function handleRoomIdKeydown(event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            homePage.joinRoomBtn.click();
        }
    }
    
    async function joinRoom(roomId, playerName) {
        try {
            const joinResponse = await fetch(`/room/${roomId}/join`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: playerName })
            });
            
            if (!joinResponse.ok) {
                const error = await joinResponse.json();
                throw new Error(error.detail || 'Failed to join room');
            }
            
            // Store player info and redirect with query parameters
            storePlayerInfo(roomId, playerName); // Keep localStorage as fallback
            window.location.href = `/lobby?roomId=${roomId}&name=${encodeURIComponent(playerName)}`;
            
        } catch (error) {
            showError(error.message);
        }
    }
    
    function showError(message) {
        if (homePage.errorMessage) {
            homePage.errorMessage.textContent = message;
        } else {
            console.error(message);
        }
    }
    
    // Lobby Page Functions    
    function initLobbyPage() {
        if (!lobbyPage.roomIdDisplay) return;
        
        // Get room and player info
        const roomData = getRoomData();
        if (!roomData.roomId) {
            window.location.href = '/';
            return;
        }
        
        // Display room ID
        lobbyPage.roomIdDisplay.textContent = roomData.roomId;
        
        // Update player info header
        updatePlayerInfoHeader();
        
        // Set up room status polling
        fetchRoomStatus(roomData.roomId);
        state.intervalId = setInterval(() => fetchRoomStatus(roomData.roomId), 2000);
        
        const roomId = window.ROOM_ID;
        const playerName = window.PLAYER_NAME;
        
        if (roomId && playerName) {
            state.connection = new ConnectionManager(roomId, playerName);
            
            // Handle incoming messages
            state.connection.onMessage = function(data) {
                console.log('Received lobby update:', data);
                
                // Handle different message types
                if (data.type === "lobby_update" || data.type === "player_left") {
                    state.isRoomOwner = (window.PLAYER_NAME === data.owner);
                    
                    // Update player list
                    renderPlayersList(data.players, data.ai_players || [], window.PLAYER_NAME, data.owner);
                    
                    // Update player count
                    if (lobbyPage.playerCount) {
                        lobbyPage.playerCount.textContent = `${data.players.length}/10`;
                    }
                    
                    updateStartGameButton(data.status);
                } else if (data.type === "owner_changed") {
                    state.isRoomOwner = (window.PLAYER_NAME === data.owner);
                    
                    // Update UI to reflect ownership change
                    if (state.isRoomOwner) {
                        showOwnerControls();
                    }
                }
            };
            
            // Connect to lobby
            state.connection.connect('lobby');
        }
        
        // Initialize lobby buttons
        initLobbyButtons(roomId);
    }
    
    function initLobbyButtons(roomId) {
        // Copy room ID button
        if (lobbyPage.copyRoomBtn) {
            lobbyPage.copyRoomBtn.addEventListener('click', handleCopyRoomId);
        }
        
        // Start game button
        if (lobbyPage.startGameBtn) {
            lobbyPage.startGameBtn.addEventListener('click', () => handleStartGame(roomId));
        }
    }
    
    function handleCopyRoomId() {
        const roomId = window.ROOM_ID || localStorage.getItem('roomId');
        
        if (!roomId) {
            console.error('No room ID found');
            return;
        }
        
        const originalText = lobbyPage.copyRoomBtn.textContent;
        const successful = copyTextToClipboard(roomId);
        
        // Visual feedback
        lobbyPage.copyRoomBtn.textContent = successful ? "Copied!" : "Copy failed";
        lobbyPage.copyRoomBtn.classList.add(successful ? "copied" : "copy-error");
        
        // Reset button after delay
        setTimeout(() => {
            lobbyPage.copyRoomBtn.textContent = originalText;
            lobbyPage.copyRoomBtn.classList.remove("copied", "copy-error");
        }, 1500);
    }
    
    async function handleStartGame(roomId) {
        try {
            const response = await fetch(`/room/${roomId}/start`, { method: 'POST' });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to start game');
            }
            
            // Redirect to game page
            const playerName = window.PLAYER_NAME;
            window.location.href = `/game?roomId=${roomId}&name=${encodeURIComponent(playerName)}`;
            
        } catch (error) {
            alert(error.message);
        }
    }
    
    async function fetchRoomStatus(roomId) {
        try {
            const response = await fetch(`/room/${roomId}`);
            const data = await response.json();
            
            if (!lobbyPage.playersList) return;
            
            // Update room owner status
            const currentPlayerName = window.PLAYER_NAME;
            state.isRoomOwner = (currentPlayerName === data.owner);
            
            // Update player list
            renderPlayersList(data.players, data.ai_players || [], currentPlayerName, data.owner);
            
            // Update player count
            if (lobbyPage.playerCount) {
                lobbyPage.playerCount.textContent = `${data.players.length}/10`;
            }
            
            // Update start game button
            updateStartGameButton(data.status);
            
            // Show owner controls if owner
            if (state.isRoomOwner) {
                showOwnerControls();
            }
        } catch (error) {
            console.error('Error fetching room status:', error);
        }
    }
    
    function renderPlayersList(players, aiPlayers, currentPlayerName, owner) {
        if (!lobbyPage.playersList) return;
        
        lobbyPage.playersList.innerHTML = '';
        
        // Sort players: current player first, then humans, then AI
        const sortedPlayers = [...players].sort((a, b) => {
            if (a === currentPlayerName) return -1;
            if (b === currentPlayerName) return 1;
            
            const isAI_A = aiPlayers.includes(a);
            const isAI_B = aiPlayers.includes(b);
            
            if (!isAI_A && isAI_B) return -1;
            if (isAI_A && !isAI_B) return 1;
            
            return a.localeCompare(b);
        });
        
        // Create player list items
        sortedPlayers.forEach(player => {
            const li = createPlayerListItem(player, currentPlayerName, owner, aiPlayers);
            lobbyPage.playersList.appendChild(li);
        });
    }
    
    function createPlayerListItem(player, currentPlayerName, owner, aiPlayers) {
        const li = document.createElement('li');
        li.className = 'player-item';
        
        // Player name with classes
        const nameSpan = document.createElement('span');
        nameSpan.className = 'player-name';
        nameSpan.textContent = player;
        
        if (player === currentPlayerName) nameSpan.classList.add('current-player');
        if (player === owner) nameSpan.classList.add('room-owner');
        if (aiPlayers.includes(player)) nameSpan.classList.add('ai-player');
        else nameSpan.classList.add('human-player');
        
        li.appendChild(nameSpan);
        
        // Add remove button if current player is owner
        if (state.isRoomOwner && player !== currentPlayerName) {
            const removeBtn = document.createElement('button');
            removeBtn.className = 'remove-btn';
            removeBtn.textContent = 'Remove';
            removeBtn.addEventListener('click', () => removePlayer(player));
            li.appendChild(removeBtn);
        }
        
        return li;
    }
    
    function updateStartGameButton(status) {
        if (!lobbyPage.startGameBtn) return;
        
        const canStart = status === "ready" && state.isRoomOwner;
        lobbyPage.startGameBtn.disabled = !canStart;
        
        if (!state.isRoomOwner) {
            lobbyPage.startGameBtn.textContent = "Only owner can start game";
        } else if (status !== "ready") {
            lobbyPage.startGameBtn.textContent = "Need 10 players";
        } else {
            lobbyPage.startGameBtn.textContent = "Start Game";
        }
    }
    
    function showOwnerControls() {
        if (!lobbyPage.playersList || document.getElementById('ownerControls')) return;
        
        const container = document.createElement('div');
        container.id = 'ownerControls';
        container.className = 'owner-controls';
        
        // Add bot button if room isn't full
        if (document.querySelectorAll('.player-item').length < 10) {
            const addBotBtn = document.createElement('button');
            addBotBtn.className = 'btn btn-secondary';
            addBotBtn.textContent = 'Add Bot';
            addBotBtn.addEventListener('click', addBot);
            container.appendChild(addBotBtn);
        }
        
        // Insert controls after player list
        lobbyPage.playersList.parentElement.appendChild(container);
    }
    
    async function removePlayer(playerName) {
        const roomId = window.ROOM_ID;
        if (!roomId || !state.isRoomOwner) return;
        
        try {
            const requester = encodeURIComponent(window.PLAYER_NAME);
            const response = await fetch(
                `/room/${roomId}/player/${playerName}?requester=${requester}`, 
                { method: 'DELETE' }
            );
            
            if (response.ok) {
                fetchRoomStatus(roomId);
            } else {
                console.error('Failed to remove player:', await response.text());
            }
        } catch (error) {
            console.error('Error removing player:', error);
        }
    }
    
    async function addBot() {
        const roomId = window.ROOM_ID;
        if (!roomId || !state.isRoomOwner) return;
        
        try {
            const requester = encodeURIComponent(window.PLAYER_NAME);
            const response = await fetch(
                `/room/${roomId}/add-bot?requester=${requester}`, 
                { method: 'POST' }
            );
            
            if (response.ok) {
                fetchRoomStatus(roomId);
            } else {
                console.error('Failed to add bot:', await response.text());
            }
        } catch (error) {
            console.error('Error adding bot:', error);
        }
    }
    
    // Utility Functions    
    function storePlayerInfo(roomId, playerName) {
        localStorage.setItem('roomId', roomId);
        localStorage.setItem('playerName', playerName);
    }
    
    function getRoomData() {
        return {
            roomId: window.ROOM_ID || localStorage.getItem('roomId'),
            playerName: window.PLAYER_NAME || localStorage.getItem('playerName')
        };
    }
    
    function copyTextToClipboard(text) {
        try {
            // Create temporary textarea element
            const textArea = document.createElement("textarea");
            textArea.value = text;
            textArea.style.position = "fixed";
            textArea.style.left = "-999999px";
            textArea.style.top = "-999999px";
            
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            
            // Execute copy command
            const successful = document.execCommand('copy');
            document.body.removeChild(textArea);
            
            return successful;
        } catch (err) {
            console.error('Copy failed:', err);
            return false;
        }
    }
    
    function showNotification(message) {
        const notificationDiv = document.createElement('div');
        notificationDiv.className = 'notification';
        notificationDiv.textContent = message;
        document.body.appendChild(notificationDiv);
        
        setTimeout(() => {
            notificationDiv.classList.add('fadeout');
            setTimeout(() => notificationDiv.remove(), 500);
        }, 3000);
    }
    
    function addLobbyMessage(sender, message) {
        if (!lobbyPage.chatContainer) return;
        
        const msgElement = document.createElement('div');
        msgElement.className = 'chat-message';
        
        const senderSpan = document.createElement('span');
        senderSpan.className = 'chat-sender';
        senderSpan.textContent = sender + ': ';
        
        const messageSpan = document.createElement('span');
        messageSpan.textContent = message;
        
        msgElement.appendChild(senderSpan);
        msgElement.appendChild(messageSpan);
        
        lobbyPage.chatContainer.appendChild(msgElement);
        lobbyPage.chatContainer.scrollTop = lobbyPage.chatContainer.scrollHeight;
    }
    
    function cleanupResources() {
        if (state.intervalId) {
            clearInterval(state.intervalId);
        }
        
        if (state.connection) {
            state.connection.close();
        }
        
        if (state.pingInterval) {
            clearInterval(state.pingInterval);
        }
    }
    
    function updatePlayerInfoHeader() {
        const headerPlayerName = document.getElementById('headerPlayerName');
        if (headerPlayerName) {
            const playerName = window.PLAYER_NAME;
            headerPlayerName.textContent = playerName || 'Anonymous';
        }
    }
});
