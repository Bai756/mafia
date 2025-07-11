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

NIGHT_DURATION = 20
DISCUSSION_DURATION = 10
VOTING_DURATION = 20
REVOTE_DISCUSSION_DURATION = 10

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
# Add display in the screen that displays who died last night, who got voted out, and who won the game

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
        'game': Game_Manager(use_model=False),
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
    game.sub_phase = "night_actions"

    # testing purposes
    for player in game.players:
        if isinstance(player, Human_Player):
            player.role = "Villager"
    
    # Initialize AI player suspicions
    for player in game.players:
        if isinstance(player, AI_Player):
            player.initialize_suspicion_meter(game.players)
    
    await broadcast_lobby_update(room_id, {
        "type": "game_started",
        "room_id": room_id
    })

    # Add system message about first night
    if 1 not in game.discussion_history:
        game.discussion_history[1] = []
    game.discussion_history[1].append(("System", "The game has begun. Night has fallen."))
    
    # Start night phase timer immediately
    await start_phase_timer(room_id, NIGHT_DURATION, "night", "night_actions")
    
    # Process AI night actions
    game.web_app_manager.process_ai_night_actions()

    await advance_game_phase(room_id)

    # Broadcast game state to all clients
    await broadcast_to_room(room_id, dump_state(game))
    
    return {"status": "started"}

@app.post("/room/{room_id}/advance_phase")
async def advance_game_phase(room_id: str):
    success = True
    room = get_room_or_error(room_id)
    game = room['game']
    
    # Get the current phase before advancing
    current_phase = game.get_game_phase()
    current_sub_phase = game.sub_phase
    
    # Advance the game phase
    phase_changed = game.web_app_manager.try_advance()
    
    # Get the new phase after advancing
    new_phase = game.get_game_phase()
    
    # If we're transitioning to a new round (after revote_voting)
    if current_sub_phase == "revote_voting" and new_phase == "night":
        game.round_number += 1
        
        # Reset for next round
        game.last_protected = []
        game.last_targeted = []
        game.last_deaths = []
        
        # Ensure discussion history exists for the new round
        round_num = game.round_number
        if round_num not in game.discussion_history:
            game.discussion_history[round_num] = []
            
        # Add night beginning message
        game.discussion_history[round_num].append(
            ("System", "Night has fallen. Everyone returns to their homes.")
        )
        
        # Start night phase
        await start_phase_timer(room_id, NIGHT_DURATION, "night", "night_actions")
        
        # Process AI night actions
        game.web_app_manager.process_ai_night_actions()
    
    # If we've just entered night phase
    elif new_phase == "night" and current_phase == "day":
        game.is_night = True
        
        # Add system message about night falling
        round_num = game.round_number
        if round_num not in game.discussion_history:
            game.discussion_history[round_num] = []
        game.discussion_history[round_num].append(
            ("System", "Night has fallen. Everyone returns to their homes.")
        )
            
        await start_phase_timer(room_id, NIGHT_DURATION, "night", "night_actions")
        
        # Process AI night actions
        game.web_app_manager.process_ai_night_actions()
        
    # If we've just entered day phase
    elif new_phase == "day" and current_phase == "night":
        # Start with discussion sub-phase
        game.sub_phase = "discussion"
        
        # Ensure discussion history exists for the new round
        round_num = game.round_number
        if round_num not in game.discussion_history:
            game.discussion_history[round_num] = []
            
        # Add system message about day beginning
        game.discussion_history[round_num].append(
            ("System", f"Day {game.round_number} has begun. The discussion phase will last for {DISCUSSION_DURATION//60} minutes.")
        )
        
        # Set up the discussion
        alive_players = game.get_alive_players()
        if alive_players:
            game.current_speaker = alive_players[0].name
            
            # If first speaker is AI, trigger their turn
            first_speaker = next((p for p in game.players if p.name == game.current_speaker), None)
            if first_speaker and isinstance(first_speaker, AI_Player) and first_speaker.is_alive:
                await asyncio.sleep(2)
                asyncio.create_task(process_ai_turn(game, room_id))
        
        # Start discussion timer
        await start_phase_timer(room_id, DISCUSSION_DURATION, "day", "discussion")
    else:
        success = False
        
    # Broadcast updated state
    await broadcast_to_room(room_id, dump_state(game))
    
    return {"status": "advanced" if success else "failed", "phase": new_phase, "sub_phase": game.sub_phase}

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

@app.post("/room/{room_id}/verify-player")
async def verify_player_in_room(room_id: str, player_data: dict):
    try:
        room = get_room_or_error(room_id)
        player_name = player_data.get("name")
        
        if not player_name:
            raise HTTPException(status_code=400, detail="Player name is required")
            
        # Check if player is in the room
        player_in_room = any(p.name == player_name for p in room['game'].players)
        if not player_in_room:
            raise HTTPException(status_code=403, detail="Player not in this room")
            
        # Return room info
        return {
            "status": "success",
            "room_id": room_id,
            "players": [p.name for p in room['game'].players],
            "owner": room.get('owner')
        }
        
    except KeyError:
        raise HTTPException(status_code=404, detail="Room not found")

async def process_ai_turn(game: Game_Manager, room_id: str):
    # Make sure it's actually an AI's turn
    current_speaker_name = game.current_speaker
    if not current_speaker_name:
        return
    
    current_speaker = next((p for p in game.players if p.name == current_speaker_name), None)
    if not current_speaker or not isinstance(current_speaker, AI_Player) or not current_speaker.is_alive:
        return
    
    await asyncio.sleep(2)
    
    ai_message = current_speaker.generate_argument(game)
    if not ai_message:
        ai_message = "Message not generated correctly."
    
    # Add the message to the discussion    
    result = game.web_app_manager.add_message(current_speaker_name, ai_message)
    
    if result:
        await broadcast_to_room(room_id, dump_state(game))
        
        # If there's a new speaker and it's an AI, schedule their turn
        if game.current_speaker and game.current_speaker != current_speaker_name:
            next_speaker = next((p for p in game.players if p.name == game.current_speaker), None)
            if next_speaker and isinstance(next_speaker, AI_Player) and next_speaker.is_alive:
                await asyncio.sleep(2)
                asyncio.create_task(process_ai_turn(game, room_id))

def dump_state(game: Game_Manager, player_name: str = None):
    state = {
        "phase": game.get_game_phase(),
        "round": game.round_number,
        "alive": [p.name for p in game.get_alive_players()],
        "last_deaths": list(dict.fromkeys(p.name for p in game.last_deaths)),
        "last_voted_out": game.last_voted_out,
        "discussion": game.discussion_history.get(game.round_number, []),
        "eliminated": [p.name for p in game.players if not p.is_alive],
        "game_status": game.get_game_status(),
        "current_speaker": game.current_speaker,
        "sub_phase": getattr(game, "sub_phase", None),
        "tied_candidates": game.tied_candidates if hasattr(game, 'tied_candidates') else [],
        "mafia_count": len([p for p in game.get_alive_players() if p.role == "Mafia"])
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
                state["fellow_mafia"] = [p.name for p in game.players if p.role == "Mafia" and p.name != player_name]
    
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
    
    room['clients'][player_name] = websocket
    
    await cancel_room_cleanup(room_id)
    
    try:
        # Send personalized game state
        await websocket.send_json(dump_state(room['game'], player_name))
        
        while True:
            data = await websocket.receive_json()
            result = handle_action(room['game'], player_name, data)
            
            if not result.get("phase_advanced"):
                await broadcast_to_room(room_id, dump_state(room['game']))

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
        
    room = rooms[room_id]
    game = room['game']
    clients = room.get('clients', {})
    
    # For each connected player, send them a personalized state
    for player_name, ws in list(clients.items()):
        try:
            # Create a personalized copy of the message for this specific player
            if isinstance(message, dict) and message.get("phase") is not None:
                # This appears to be a game state message, so personalize it
                personalized_msg = dump_state(game, player_name)
                
                # Copy any additional fields that were in the original message
                for key, value in message.items():
                    if key not in personalized_msg:
                        personalized_msg[key] = value
                
                await ws.send_json(personalized_msg)
            else:
                # For non-game state messages, send as is
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
    for rm_id, room in rooms.items():
        if room['game'] is game:
            room_id = rm_id
            break

    action_type = action_data.get("action")
    target_name = action_data.get("target")
    
    if action_type == "send_message":
        message = action_data.get("message")
        if message:
            success = game.web_app_manager.add_message(player_name, message)
            
            if success and game.current_speaker:
                # Find the next speaker
                next_speaker = next((p for p in game.players if p.name == game.current_speaker), None)
                
                # If next speaker is AI, trigger their turn
                if next_speaker and isinstance(next_speaker, AI_Player) and next_speaker.is_alive:
                    for room_id, room in rooms.items():
                        if room['game'] is game:
                            asyncio.create_task(process_ai_turn(game, room_id))
                            break
            
            return {"success": success}

    if not action_type or not target_name:
        return {"error": "Invalid action data"}

    current_phase = game.get_game_phase()
    phase_advanced = False
    
    # Handle night actions
    if current_phase == "night":
        player = next((p for p in game.players if p.name == player_name), None)
        if not player or not player.is_alive:
            return {"error": "Player not found or not alive"}
        
        # Process night action based on role
        if action_type == "night_kill" and player.role == "Mafia":
            game.web_app_manager.mafia_action(player_name, target_name)
        elif action_type == "night_protect" and player.role == "Doctor":
            game.web_app_manager.doctor_action(player_name, target_name)
        elif action_type == "night_investigate" and player.role == "Investigator":
            game.web_app_manager.investigator_action(player_name, target_name)
        else:
            return {"error": "Invalid action for your role"}
        
        # Check if all required night actions are complete
        doctors_need_to_act = [p.name for p in game.get_alive_players() if p.role == "Doctor" and not any(doc.name == p.name for doc, _ in game.last_protected)]
        mafia_need_to_act = [p.name for p in game.get_alive_players() if p.role == "Mafia" and not any(maf.name == p.name for maf, _ in game.last_targeted)]
        investigators_need_to_act = [p.name for p in game.get_alive_players() if p.role == "Investigator" and not any(inv.name == p.name for inv, _, _ in game.last_investigated)]
        all_doctors_acted = len(doctors_need_to_act) == 0
        all_mafia_acted = len(mafia_need_to_act) == 0
        all_investigators_acted = len(investigators_need_to_act) == 0

        # If all required actions are complete, advance to day phase
        if all_doctors_acted and all_mafia_acted and all_investigators_acted:
            # Find the room ID for this game
            for room_id, room in rooms.items():
                if room['game'] is game:
                    # Create task to advance the game phase
                    asyncio.create_task(advance_game_phase(room_id))
                    phase_advanced = True
                    break
    
        return {"success": True, "phase_advanced": phase_advanced}
    
    # Handle day actions
    elif current_phase == "day" and action_type == "vote":
        # Check if we're in a revote and the target is valid
        if hasattr(game, 'tied_candidates') and game.tied_candidates:
            if target_name not in game.tied_candidates:
                return {"success": False, "error": "You must vote for one of the tied candidates"}
        
        success = game.web_app_manager.vote_action(player_name, target_name)
        if success:
            # Check if voting is complete
            all_voted = len(game.votes) >= len([p for p in game.players if p.is_alive])
            
            if all_voted:
                if getattr(game, 'phase_timer', None):
                    game.phase_timer.cancel()
                    game.phase_timer = None
                    print(f"[TIMER] Voting phase ended early - all players have voted")

                if game.sub_phase == "revote_voting":
                    asyncio.create_task(handle_revoting_timeout(room_id))
                    phase_advanced = True
                else:
                    asyncio.create_task(handle_voting_timeout(room_id))
                    phase_advanced = True
            
        return {"success": success, "phase_advanced": phase_advanced}
    
    return {"success": False, "error": "Invalid action for current phase"}
    
async def start_phase_timer(room_id: str, duration: int, phase: str, sub_phase: str = None):
    room = get_room_or_error(room_id)
    game = room['game']
    
    # Cancel and clear any previous timer
    if getattr(game, 'phase_timer', None):
        game.phase_timer.cancel()
        game.phase_timer = None
    
    # Set the sub_phase upfront
    game.sub_phase = sub_phase or (
        "discussion" if phase == "day" else
        "night_actions"
    )
    
    # Broadcast initial phase + timer
    await broadcast_to_room(room_id, {
        **dump_state(game),
        "timer": duration,
        "sub_phase": game.sub_phase
    })
    
    # Launch the background countdown
    game.phase_timer = asyncio.create_task(phase_timer_task(room_id, duration, phase, game.sub_phase))

async def phase_timer_task(room_id: str, duration: int, phase: str, sub_phase: str):
    room = get_room_or_error(room_id)
    game = room['game']
    
    print(f"[TIMER] Starting {duration}s countdown for {phase}/{sub_phase}")
    
    try:
        # Countdown with updates
        for remaining in range(duration, 0, -1):
            await asyncio.sleep(1)
            
            if remaining % 3 == 0 or remaining <= 3:
                await broadcast_to_room(room_id, {
                    **dump_state(game),
                    "timer": remaining,
                    "sub_phase": game.sub_phase
                })
        
        # Final zero broadcast
        await broadcast_to_room(room_id, {
            **dump_state(game),
            "timer": 0,
            "sub_phase": game.sub_phase
        })
        
    finally:
        game.phase_timer = None
    
    print(f"[TIMER] Phase timer expired for {phase}/{sub_phase}")
    
    # Handle phase transitions based on current phase and sub_phase
    if phase == "night":
        print("[TIMER] Night phase ended, handling timeout")
        await handle_night_timeout(room_id)
    elif phase == "day":
        if sub_phase == "discussion":
            print("[TIMER] Day discussion ended, starting voting phase")
            await start_voting_phase(room_id)
        elif sub_phase == "voting":
            print("[TIMER] Voting ended, handling timeout")
            await handle_voting_timeout(room_id)
        elif sub_phase == "revote_discussion":
            print("[TIMER] Revote discussion ended, starting revote voting")
            await start_revote_voting_phase(room_id)
        elif sub_phase == "revote_voting":
            print("[TIMER] Revote voting ended, handling timeout")
            await handle_revoting_timeout(room_id)

async def handle_night_timeout(room_id: str):
    room = get_room_or_error(room_id)
    game = room['game']
    
    # For each player who hasn't acted, select a random action
    for player in game.get_alive_players():
        if player.role not in ["Mafia", "Doctor", "Investigator"]:
            continue
            
        # Check if this player has already acted
        has_acted = False
        
        if player.role == "Mafia":
            has_acted = any(maf.name == player.name for maf, _ in game.last_targeted)
        elif player.role == "Doctor":
            has_acted = any(doc.name == player.name for doc, _ in game.last_protected)
        elif player.role == "Investigator":
            has_acted = any(inv.name == player.name for inv, _, _ in game.last_investigated)
        
        # If they haven't acted, make them act randomly
        if not has_acted:
            possible_targets = [p.name for p in game.get_alive_players() if p.name != player.name]
            
            if possible_targets:
                target = random.choice(possible_targets)
                
                # Apply action based on role
                if player.role == "Mafia":
                    game.web_app_manager.mafia_action(player.name, target)
                elif player.role == "Doctor":
                    game.web_app_manager.doctor_action(player.name, target)
                elif player.role == "Investigator":
                    game.web_app_manager.investigator_action(player.name, target)
    
    await advance_game_phase(room_id)

async def make_ai_players_vote(room_id: str, is_revote: bool = False):
    room = get_room_or_error(room_id)
    game = room['game']
    
    ai_players = [p for p in game.get_alive_players() if isinstance(p, AI_Player)]
    for ai_player in ai_players:
        if ai_player.name in game.votes:
            continue
            
        valid_targets = [p for p in game.get_alive_players() if p != ai_player]
        
        if is_revote and hasattr(game, 'tied_candidates'):
            valid_targets = [p for p in valid_targets if p.name in game.tied_candidates]
        
        if valid_targets:
            target = ai_player.vote(game, valid_targets)
            if target:
                game.web_app_manager.vote_action(ai_player.name, target.name)
    
    await broadcast_to_room(room_id, dump_state(game))

async def start_voting_phase(room_id: str):
    room = get_room_or_error(room_id)
    game = room['game']
    game.sub_phase = "voting"
    
    game.current_speaker = None
    
    round_num = game.round_number
    if round_num not in game.discussion_history:
        game.discussion_history[round_num] = []
    game.discussion_history[round_num].append(("System", "Discussion time is over. Voting has begun."))
    
    game.votes = {}
    
    # AI players vote immediately
    await make_ai_players_vote(room_id, is_revote=False)
    
    # Start the timer with the correct sub_phase
    await start_phase_timer(room_id, VOTING_DURATION, "day", "voting")

async def handle_voting_timeout(room_id: str):
    room = get_room_or_error(room_id)
    game = room['game']
    
    # For each player who hasn't voted, cast a random vote
    for player in game.get_alive_players():
        if player.name not in game.votes:
            possible_targets = [p.name for p in game.get_alive_players() if p.name != player.name]
            
            if possible_targets:
                target = random.choice(possible_targets)
                game.web_app_manager.vote_action(player.name, target)
    
    resolved = game.web_app_manager._resolve_day_votes()
    
    if resolved:
        game.is_night = True
        await advance_game_phase(room_id)
    else:
        # Go to revote discussion
        await start_revote_discussion_phase(room_id)
    
    # Broadcast updated state
    await broadcast_to_room(room_id, dump_state(game))

async def handle_revoting_timeout(room_id: str):
    room = get_room_or_error(room_id)
    game = room['game']
    
    for player in game.get_alive_players():
        if player.name not in game.votes:
            possible_targets = [name for name in game.tied_candidates if name != player.name]
            
            if possible_targets:
                target = random.choice(possible_targets)
                game.web_app_manager.vote_action(player.name, target)
    
    resolved = game.web_app_manager._resolve_day_votes()
    
    # Add message if vote remains tied
    if not resolved:
        round_num = game.round_number
        if round_num not in game.discussion_history:
            game.discussion_history[round_num] = []
            
        game.discussion_history[round_num].append(
            ("System", "Voting remains tied. No one will be eliminated today.")
        )
        
        # Clear tied candidates and votes
        game.tied_candidates = []
        game.votes = {}
    
    game.is_night = True
    
    await advance_game_phase(room_id)

async def start_revote_discussion_phase(room_id: str):
    room = get_room_or_error(room_id)
    game = room['game']
    game.sub_phase = "revote_discussion"
    
    # Set the first speaker
    alive_players = game.get_alive_players()
    if alive_players:
        game.current_speaker = alive_players[0].name
    
    round_num = game.round_number
    if round_num not in game.discussion_history:
        game.discussion_history[round_num] = []
    game.discussion_history[round_num].append(("System", "Brief discussion before revote has begun."))
    
    await broadcast_to_room(room_id, {
        **dump_state(game),
        "sub_phase": "revote_discussion",
        "timer": REVOTE_DISCUSSION_DURATION
    })
    
    if game.current_speaker:
        first_speaker = next((p for p in game.players if p.name == game.current_speaker), None)
        if first_speaker and isinstance(first_speaker, AI_Player) and first_speaker.is_alive:
            await asyncio.sleep(1)
            asyncio.create_task(process_ai_turn(game, room_id))
    
    await start_phase_timer(room_id, REVOTE_DISCUSSION_DURATION, "day", "revote_discussion")

async def start_revote_voting_phase(room_id: str):
    room = get_room_or_error(room_id)
    game = room['game']
    game.sub_phase = "revote_voting"
    
    game.current_speaker = None
    
    round_num = game.round_number
    if round_num not in game.discussion_history:
        game.discussion_history[round_num] = []
    game.discussion_history[round_num].append(("System", "Discussion is over. Please revote now."))
    
    game.votes = {}
    
    await make_ai_players_vote(room_id, is_revote=True)

    await start_phase_timer(room_id, VOTING_DURATION, "day", "revote_voting")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
