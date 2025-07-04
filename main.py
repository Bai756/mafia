from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import random
import asyncio
from game import Game_Manager
from player_classes import AI_Player, Human_Player
import logging

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(periodic_room_cleanup())
    yield

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

logger = logging.getLogger('uvicorn.error')
logger.setLevel(logging.DEBUG)

# TODO:
# Fix game play

rooms = {}
room_timers = {}

# Helper functions
def get_room_or_error(room_id: str):
    if room_id not in rooms:
        raise HTTPException(status_code=404, detail="Room not found")
    return rooms[room_id]

def get_player_or_error(game: Game_Manager, player_name: str):
    player = next((p for p in game.players if p.name == player_name), None)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return player

def validate_owner(room: dict, requester: str):
    if requester != room.get('owner'):
        raise HTTPException(status_code=403, detail="Only the room owner can perform this action")

def check_game_not_started(game: Game_Manager):
    if game.round_number > 0:
        raise HTTPException(status_code=400, detail="Game already started")

# HTML endpoints
@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/lobby", response_class=HTMLResponse)
async def get_lobby(request: Request, roomId: str = None, name: str = None):
    return templates.TemplateResponse(
        "lobby.html",
        {
            "request": request,
            "ROOM_ID": roomId,
            "PLAYER_NAME": name,
        },
    )

@app.get("/game", response_class=HTMLResponse)
async def get_game(request: Request, roomId: str = None, name: str = None):
    return templates.TemplateResponse(
        "game.html",
        {
            "request": request,
            "ROOM_ID": roomId,
            "PLAYER_NAME": name,
        },
    )

# API endpoints
@app.post("/room")
async def create_room(player_data: dict = None):
    # Generate unique room ID
    room_id = str(random.randint(10**5, 10**6 - 1))
    while room_id in rooms:
        room_id = str(random.randint(10**5, 10**6 - 1))
    
    # Get creator's name if provided
    creator_name = player_data.get("name") if player_data else None
    
    rooms[room_id] = {
        'game': Game_Manager(),
        'clients': {},
        'lobby_clients': {},
        'owner': creator_name
    }
    
    # Set up initial game state
    game = rooms[room_id]['game']
    game.round_number = 0
    
    if creator_name:
        game.add_player(Human_Player(creator_name))
    
    # Add some default AI players
    ai_names = ["Alice", "Bob", "Charlie", "Dana", "Eve", "Frank", "Grace", "Hank", "Ivy", "Jack"]

    for name in ai_names[:5]: # Add 5 AI players by default
        game.add_player(AI_Player(name))
    
    return {"room_id": room_id}

@app.post("/room/{room_id}/join")
async def join_room(room_id: str, player_data: dict):
    room = get_room_or_error(room_id)
    game = room['game']
    
    player_name = player_data.get("name")
    if not player_name:
        raise HTTPException(status_code=400, detail="Player name is required")
    
    # Check if the player already exists
    player_exists = any(p.name == player_name for p in game.players)
    
    # Handle owner rejoining
    if player_name == room.get('owner'):
        if player_exists:
            return {"status": "joined", "isOwner": True}
    elif player_exists:
        raise HTTPException(status_code=400, detail="Player name already taken")
    
    if not player_exists:
        if len(game.players) >= 10:
            raise HTTPException(status_code=400, detail="Room is full")
        game.add_player(Human_Player(player_name))
    
    # Set owner if none exists
    if not room.get('owner'):
        room['owner'] = player_name
    
    is_owner = player_name == room.get('owner')
    return {"status": "joined", "isOwner": is_owner}

@app.get("/room/{room_id}")
async def get_room(room_id: str):
    room = get_room_or_error(room_id)
    game = room['game']
    
    return {
        "players": [p.name for p in game.players],
        "ai_players": [p.name for p in game.players if isinstance(p, AI_Player)],
        "owner": room.get('owner'),
        "status": "ready" if len(game.players) == 10 else "waiting" # 10 players needed to start
    }

@app.post("/room/{room_id}/start")
async def start_game(room_id: str):
    room = get_room_or_error(room_id)
    game = room['game']
    
    if len(game.players) < 10:
        raise HTTPException(status_code=400, detail="Need at least 10 players to start")
    
    game.shuffle_roles()
    game.round_number = 1
    
    # Initialize AI player suspicions
    for player in game.players:
        if isinstance(player, AI_Player):
            player.initialize_suspicion_meter(game.players)
    
    return {"status": "started"}

@app.post("/room/{room_id}/advance_phase")
async def advance_game_phase(room_id: str):
    room = get_room_or_error(room_id)
    game = room['game']
    
    game.web_app_manager.try_advance()
    
    if game.get_game_phase() == "night":
        game.web_app_manager.process_ai_night_actions()
    
    elif game.get_game_phase() == "day":
        alive_players = game.get_alive_players()
        if alive_players:
            game.current_speaker = alive_players[0].name
            
            first_speaker = next((p for p in game.players if p.name == game.current_speaker), None)
            if isinstance(first_speaker, AI_Player):
                asyncio.create_task(process_ai_turn(game, room_id))
    
    # Broadcast updated state
    await broadcast_to_room(room_id, dump_state(game))
    
    return {"status": "advanced"}

@app.post("/room/{room_id}/auth")
def authenticate_player(room_id: str, auth_request: dict):
    try:
        room = get_room_or_error(room_id)
        game = room['game']
        player_name = auth_request.get("name")
        player = get_player_or_error(game, player_name)
        
        return {
            "role": player.role,
            "is_alive": player.is_alive,
            "investigation_results": game.get_investigation_results(player_name) if player.role == "Investigator" else []
        }
    except HTTPException as e:
        return {"error": e.detail}

@app.delete("/room/{room_id}/player/{player_name}")
async def remove_player(room_id: str, player_name: str, requester: str = None):
    room = get_room_or_error(room_id)
    validate_owner(room, requester)
    
    game = room['game']
    check_game_not_started(game)
    
    player = get_player_or_error(game, player_name)
    
    # Remove player
    game.players = [p for p in game.players if p.name != player_name]
    
    # Clean up connections
    if player_name in room.get('clients', {}):
        del room['clients'][player_name]
    
    if 'lobby_clients' in room and player_name in room['lobby_clients']:
        del room['lobby_clients'][player_name]
    
    return {"status": "removed"}

@app.post("/room/{room_id}/add-bot")
async def add_bot(room_id: str, requester: str = None):
    room = get_room_or_error(room_id)
    validate_owner(room, requester)
    
    game = room['game']
    check_game_not_started(game)
    
    if len(game.players) >= 10:
        raise HTTPException(status_code=400, detail="Room is full")
    
    # Find available name
    used_names = {p.name for p in game.players}
    ai_names = ["Alice", "Bob", "Charlie", "Dana", "Eve", "Frank", "Grace", "Hank", "Ivy", "Jack"]
    
    available_name = next((name for name in ai_names if name not in used_names), None)
    if not available_name:
        available_name = f"Bot-{random.randint(1000, 9999)}"
    
    game.add_player(AI_Player(available_name))
    
    return {"status": "added", "name": available_name}

async def process_ai_turn(game: Game_Manager, room_id: str):
    # Let the AI player take its turn
    if hasattr(game.web_app_manager, "ai_take_turn"):
        game.web_app_manager.ai_take_turn(game.current_speaker)
        game.web_app_manager.try_advance()
        await broadcast_to_room(room_id, dump_state(game))
    else:
        game.web_app_manager.try_advance()
        await broadcast_to_room(room_id, dump_state(game))

def dump_state(game: Game_Manager, player_name: str = None):
    state = {
        "phase": game.get_game_phase(),
        "round": game.round_number,
        "alive": [p.name for p in game.get_alive_players()],
        "last_deaths": [p.name for p in game.last_deaths],
        "discussion": game.discussion_history.get(game.round_number, []),
        "eliminated": [p.name for p in game.players if not p.is_alive],
        "game_status": game.get_game_status(),
        "current_speaker": game.current_speaker
    }
    
    # Add role-specific information if player is specified
    if player_name:
        player = next((p for p in game.players if p.name == player_name), None)
        if player:
            # Add investigation results for investigator
            if player.role == "Investigator":
                state["investigation_results"] = game.get_investigation_results(player_name)
            
            # For mafia, show who other mafia members are
            if player.role == "Mafia":
                state["fellow_mafia"] = [p.name for p in game.players 
                                         if p.role == "Mafia" and p.name != player_name]
    
    return state

@app.websocket("/ws/{room_id}/{player_name}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_name: str):
    await websocket.accept()
    
    try:
        room = get_room_or_error(room_id)
    except HTTPException as e:
        await websocket.send_json({"error": e.detail})
        await websocket.close()
        return
    
    # Register client connection
    room['clients'][player_name] = websocket
    
    # Cancel any pending cleanup
    await cancel_room_cleanup(room_id)
    
    try:
        # Send personalized game state
        await websocket.send_json(dump_state(room['game'], player_name))
        
        while True:
            data = await websocket.receive_json()
            handle_action(room['game'], player_name, data)
            
            for client_name, client_ws in room['clients'].items():
                try:
                    await client_ws.send_json(dump_state(room['game'], client_name))
                except Exception:
                    pass
                    
    except WebSocketDisconnect:
        if player_name in room['clients']:
            del room['clients'][player_name]
        check_and_schedule_cleanup(room_id)

@app.websocket("/lobby/ws/{room_id}/{player_name}")
async def lobby_websocket_endpoint(websocket: WebSocket, room_id: str, player_name: str):
    await websocket.accept()
    
    try:
        room = get_room_or_error(room_id)
    except HTTPException as e:
        await websocket.send_json({"error": e.detail})
        await websocket.close()
        return
    
    # Store connection in lobby_clients
    if 'lobby_clients' not in room:
        room['lobby_clients'] = {}
    
    room['lobby_clients'][player_name] = websocket
    
    # Cancel any pending cleanup
    await cancel_room_cleanup(room_id)
    
    await broadcast_lobby_update(room_id, {
        "type": "lobby_update",
        "players": [p.name for p in room['game'].players],
        "ai_players": [p.name for p in room['game'].players if isinstance(p, AI_Player)],
        "owner": room.get('owner')
    })
    
    try:
        # Main message loop
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        if 'lobby_clients' in room and player_name in room['lobby_clients']:
            del room['lobby_clients'][player_name]

        check_and_schedule_cleanup(room_id)

async def cancel_room_cleanup(room_id: str):
    if room_id in room_timers:
        room_timers[room_id].cancel()
        del room_timers[room_id]
        logger.info(f"Cancelled cleanup for room {room_id}")

async def broadcast_to_room(room_id: str, message: dict):
    if room_id not in rooms:
        return
        
    clients = rooms[room_id].get('clients', {})
    for ws in list(clients.values()):
        try:
            await ws.send_json(message)
        except Exception:
            pass

async def broadcast_lobby_update(room_id: str, message: dict):
    if room_id not in rooms or 'lobby_clients' not in rooms[room_id]:
        return
        
    clients = rooms[room_id]['lobby_clients']
    for ws in list(clients.values()):
        try:
            await ws.send_json(message)
        except Exception:
            pass

def check_and_schedule_cleanup(room_id: str):
    if room_id not in rooms:
        return
    
    room = rooms[room_id]
    game = room['game']
    
    is_lobby = game.round_number == 0
    
    # Check for active connections in both regular clients and lobby_clients
    active_humans = False
    for p in game.players:
        if not isinstance(p, AI_Player):
            # Check regular game websocket connections
            if p.name in room.get('clients', {}):
                active_humans = True
                break
            # Check lobby websocket connections
            if 'lobby_clients' in room and p.name in room['lobby_clients']:
                active_humans = True
                break

    if not active_humans:
        timeout = 1 if is_lobby else 300
        logger.info(f"No active humans in {'lobby' if is_lobby else 'game'} {room_id}, scheduling cleanup in {timeout} seconds")
        room_timers[room_id] = asyncio.create_task(delayed_room_cleanup(room_id, timeout))

# Periodic cleanup task to check for empty rooms
async def periodic_room_cleanup():
    while True:
        await asyncio.sleep(300)
        
        room_ids = list(rooms.keys())
        for room_id in room_ids:
            if room_id in rooms and room_id not in room_timers:
                check_and_schedule_cleanup(room_id)

async def delayed_room_cleanup(room_id: str, delay_seconds: int):
    try:
        await asyncio.sleep(delay_seconds)
        if room_id in rooms:
            room = rooms[room_id]
            game = room['game']
            
            is_lobby = game.round_number == 0
            
            active_humans = False
            for p in game.players:
                if not isinstance(p, AI_Player) and p.name in room['clients']:
                    active_humans = True
                    logger.info(f"Cleanup cancelled: Human reconnected to {'lobby' if is_lobby else 'game'} {room_id}")
                    break

            if not active_humans:
                logger.info(f"Cleaning up {'lobby' if is_lobby else 'game'} {room_id}")
                del rooms[room_id]
                if room_id in room_timers:
                    del room_timers[room_id]

    except asyncio.CancelledError:
        logger.info(f"Cleanup task for room {room_id} was cancelled")

def handle_action(game: Game_Manager, player_name: str, action_data: dict):
    action_type = action_data.get("action")
    target_name = action_data.get("target")
    
    if action_type == "send_message":
        message = action_data.get("message", "").strip()
        if message and len(message) <= 200:
            if game.web_app_manager.add_message(player_name, message):
                next_speaker = next((p for p in game.players if p.name == game.current_speaker), None)
                if next_speaker and isinstance(next_speaker, AI_Player):
                    for room_id, room in rooms.items():
                        if room['game'] is game:
                            asyncio.create_task(process_ai_turn(game, room_id))
                            break
            return {"success": True}
        return {"success": False}
    
    if not action_type or not target_name:
        return {"error": "Invalid action data"}
    
    if action_type == "night_protect" and game.get_game_phase() == "night":
        success = game.web_app_manager.doctor_action(player_name, target_name)
        
    elif action_type == "night_kill" and game.get_game_phase() == "night":
        success = game.web_app_manager.mafia_action(player_name, target_name)
        
    elif action_type == "night_investigate" and game.get_game_phase() == "night":
        success, is_mafia = game.web_app_manager.investigator_action(player_name, target_name)
        
    elif action_type == "vote" and game.get_game_phase() == "day":
        success = game.web_app_manager.vote_action(player_name, target_name)
    
    else:
        return {"error": "Invalid action for current phase"}
    
    game.web_app_manager.try_advance()
    
    return {"success": success}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)