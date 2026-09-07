import math
import os
from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController

app = Ursina()

# --- WINDOW & ENVIRONMENT ---
window.color = color.rgb(0.53, 0.81, 0.92) 

# --- TEXTURE CONFIGURATION ---
block_texture = load_texture('textures.png')
Texture.default_filtering = 'nearest'
ATLAS_SIZE, TILE_SIZE = 512, 16

def get_tile_uvs(tile_x, tile_y):
    step = TILE_SIZE / ATLAS_SIZE
    u0, u1 = tile_x * step, (tile_x + 1) * step
    v0, v1 = 1.0 - ((tile_y + 1) * step), 1.0 - (tile_y * step)
    return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]

def add_face(verts, uvs, cols, position, face_type, tile_x, tile_y):
    x, y, z = position
    t_uv = get_tile_uvs(tile_x, tile_y)
    
    p0, p1 = Vec3(x-0.5, y-0.5, z-0.5), Vec3(x+0.5, y-0.5, z-0.5)
    p2, p3 = Vec3(x+0.5, y+0.5, z-0.5), Vec3(x-0.5, y+0.5, z-0.5)
    p4, p5 = Vec3(x-0.5, y-0.5, z+0.5), Vec3(x+0.5, y-0.5, z+0.5)
    p6, p7 = Vec3(x+0.5, y+0.5, z+0.5), Vec3(x-0.5, y+0.5, z+0.5)
    
    shade = 1.0
    if y < SURFACE_Y:
        shade = max(0.1, 1.0 - ((SURFACE_Y - y) * 0.15))

    if face_type == 'top': 
        f, c = [p3, p2, p6, p7], color.rgba(1.0 * shade, 1.0 * shade, 1.0 * shade, 1.0)
    elif face_type == 'bottom': 
        f, c = [p4, p5, p1, p0], color.rgba(0.4 * shade, 0.4 * shade, 0.4 * shade, 1.0)
    elif face_type in ['back', 'front', 'left', 'right']:
        if face_type == 'back': f = [p0, p1, p2, p3]
        elif face_type == 'front': f = [p5, p4, p7, p6]
        elif face_type == 'left': f = [p4, p0, p3, p7]
        elif face_type == 'right': f = [p1, p5, p6, p2]
        c = color.rgba(0.7 * shade, 0.7 * shade, 0.7 * shade, 1.0)

    verts.extend([f[0], f[1], f[2], f[0], f[2], f[3]])
    uvs.extend([t_uv[0], t_uv[1], t_uv[2], t_uv[0], t_uv[2], t_uv[3]])
    cols.extend([c] * 6)

# --- TRUE DATA STORAGE & DELTA COMPRESSION ---
WORLD_SIZE = 256 
SURFACE_Y = 42
MAX_Y = 120
SAVE_FILE = "my_world.hex"

world_blocks = {}
removed_blocks = set()

def is_in_bounds(x, y, z):
    return 0 <= x < WORLD_SIZE and 0 <= z < WORLD_SIZE and 0 <= y <= MAX_Y

print("Generating Default World Data in Memory...")
for x in range(WORLD_SIZE):
    for z in range(WORLD_SIZE):
        for y in range(SURFACE_Y + 1):
            world_blocks[(x, y, z)] = 1

if os.path.exists(SAVE_FILE):
    print("Applying Delta Modifications from Save File...")
    with open(SAVE_FILE, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 4:
                x = int(parts[0], 16)
                y = int(parts[1], 16)
                z = int(parts[2], 16)
                state = parts[3]
                
                if state == "01": # Block Added
                    world_blocks[(x, y, z)] = 1
                elif state == "00": # Block Removed
                    if (x, y, z) in world_blocks:
                        del world_blocks[(x, y, z)]
                    removed_blocks.add((x, y, z))

def is_solid(x, y, z):
    return (x, y, z) in world_blocks

# --- CHUNK GENERATION ---
Y_BOUNDS = [(0, 16), (16, 32), (32, 121)]
sub_chunks = {}
chunk_queue = []
RENDER_DISTANCE = 4

def build_chunk_mesh(cx, cy, cz):
    if not (0 <= cx < 16 and 0 <= cz < 16 and 0 <= cy < 3): return
        
    verts, uvs, cols = [], [], []
    start_x, start_z = cx * 16, cz * 16
    min_y, max_y = Y_BOUNDS[cy]
    
    for x in range(start_x, start_x + 16):
        for z in range(start_z, start_z + 16):
            for y in range(min_y, max_y):
                if not is_solid(x, y, z): continue
                
                t_x = 0 if y == SURFACE_Y else 1 
                
                if not is_solid(x, y+1, z): add_face(verts, uvs, cols, (x, y, z), 'top', t_x, 0)
                if not is_solid(x, y-1, z): add_face(verts, uvs, cols, (x, y, z), 'bottom', t_x, 0)
                if not is_solid(x-1, y, z): add_face(verts, uvs, cols, (x, y, z), 'left', t_x, 0)
                if not is_solid(x+1, y, z): add_face(verts, uvs, cols, (x, y, z), 'right', t_x, 0)
                if not is_solid(x, y, z-1): add_face(verts, uvs, cols, (x, y, z), 'back', t_x, 0)
                if not is_solid(x, y, z+1): add_face(verts, uvs, cols, (x, y, z), 'front', t_x, 0)

    if (cx, cy, cz) not in sub_chunks:
        entity = Entity(texture=block_texture, unlit=True)
        entity.center = Vec3(start_x + 8, (min_y + max_y) / 2, start_z + 8)
        sub_chunks[(cx, cy, cz)] = entity
    else:
        entity = sub_chunks[(cx, cy, cz)]

    if not verts:
        entity.model, entity.collider = None, None
        return

    entity.model = Mesh(vertices=verts, uvs=uvs, colors=cols, mode='triangle')
    entity.collider = 'mesh'

def trigger_chunk_updates(bx, by, bz):
    cx, cz = bx // 16, bz // 16
    cy = 0
    for i, bounds in enumerate(Y_BOUNDS):
        if bounds[0] <= by < bounds[1]: cy = i
            
    build_chunk_mesh(cx, cy, cz)
    if bx % 16 == 0: build_chunk_mesh(cx - 1, cy, cz)
    if bx % 16 == 15: build_chunk_mesh(cx + 1, cy, cz)
    if by == Y_BOUNDS[cy][0] and cy > 0: build_chunk_mesh(cx, cy - 1, cz)
    if by == Y_BOUNDS[cy][1] - 1 and cy < 2: build_chunk_mesh(cx, cy + 1, cz)
    if bz % 16 == 0: build_chunk_mesh(cx, cy, cz - 1)
    if bz % 16 == 15: build_chunk_mesh(cx, cy, cz + 1)

# --- PRE-RENDER SPAWN CHUNKS ---
print("Rendering Spawn Chunks...")
spawn_cx, spawn_cz = 230 // 16, 128 // 16
for r_cx in range(spawn_cx - 1, spawn_cx + 2):
    for r_cz in range(spawn_cz - 1, spawn_cz + 2):
        for cy in range(3):
            build_chunk_mesh(r_cx, cy, r_cz)
print("Game Ready!")

# --- HIGHLIGHT CURSOR ---
cursor_block = Entity(model='cube', color=color.rgba(1.0, 1.0, 1.0, 0.2), scale=1.02, collider=None, enabled=False, unlit=True)

# --- PLAYER SETUP ---
player = FirstPersonController(position=(230, 120, 128)) 
player.gravity = 0 
player.y_velocity = 0

def custom_jump():
    if player.grounded:
        player.y_velocity = 9.0  
        player.grounded = False

player.jump = custom_jump

def save_game():
    print("Saving Delta Modifications to hex format...")
    with open(SAVE_FILE, 'w') as f:
        # Save explicitly added blocks
        for (x, y, z) in world_blocks:
            if SURFACE_Y < y <= 60:
                f.write(f"{x:04X} {y:04X} {z:04X} 01\n")
                
        # Save explicitly removed blocks
        for (x, y, z) in removed_blocks:
            f.write(f"{x:04X} {y:04X} {z:04X} 00\n")
    print("Save complete!")

def input(key):
    if key == 'escape':
        save_game()
        application.quit()
        
    if key in ['left mouse down', 'right mouse down']:
        hit_info = raycast(camera.world_position, camera.forward, distance=6)
        if hit_info.hit:
            hit_pos = hit_info.world_point - hit_info.normal * 0.5 if key == 'right mouse down' else hit_info.world_point + hit_info.normal * 0.5
            bx, by, bz = int(round(hit_pos.x)), int(round(hit_pos.y)), int(round(hit_pos.z))
            
            if key == 'right mouse down' and (bx, by, bz) in world_blocks:
                del world_blocks[(bx, by, bz)]
                if by <= SURFACE_Y:
                    removed_blocks.add((bx, by, bz))
                trigger_chunk_updates(bx, by, bz)
                
            elif key == 'left mouse down' and (bx, by, bz) not in world_blocks and is_in_bounds(bx, by, bz):
                overlap_x = (bx - 0.5 < player.x + 0.4) and (bx + 0.5 > player.x - 0.4)
                overlap_z = (bz - 0.5 < player.z + 0.4) and (bz + 0.5 > player.z - 0.4)
                overlap_y = (by - 0.5 < player.y + 2.0) and (by + 0.5 > player.y)

                if not (overlap_x and overlap_y and overlap_z):
                    world_blocks[(bx, by, bz)] = 1
                    if (bx, by, bz) in removed_blocks:
                        removed_blocks.remove((bx, by, bz))
                    trigger_chunk_updates(bx, by, bz)

def manage_chunk_streaming():
    player_cx = int(player.x // 16)
    player_cz = int(player.z // 16)

    for x in range(player_cx - RENDER_DISTANCE, player_cx + RENDER_DISTANCE + 1):
        for z in range(player_cz - RENDER_DISTANCE, player_cz + RENDER_DISTANCE + 1):
            if 0 <= x < 16 and 0 <= z < 16:
                for cy in range(3):
                    if (x, cy, z) not in sub_chunks and (x, cy, z) not in chunk_queue:
                        chunk_queue.append((x, cy, z))

    for key in list(sub_chunks.keys()):
        cx, cy, cz = key
        if abs(cx - player_cx) > RENDER_DISTANCE or abs(cz - player_cz) > RENDER_DISTANCE:
            destroy(sub_chunks[key])
            del sub_chunks[key]

def update():
    manage_chunk_streaming()
    
    if chunk_queue:
        cx, cy, cz = chunk_queue.pop(0)
        player_cx = int(player.x // 16)
        player_cz = int(player.z // 16)
        if abs(cx - player_cx) <= RENDER_DISTANCE and abs(cz - player_cz) <= RENDER_DISTANCE:
            build_chunk_mesh(cx, cy, cz)

    if not player.grounded:
        player.y_velocity -= 30 * time.dt
        step = player.y_velocity * time.dt
        
        if step < 0: 
            hit = raycast(player.position + Vec3(0, 0.5, 0), Vec3(0, -1, 0), distance=0.5 - step, ignore=(player,))
            if hit.hit:
                player.y = hit.world_point.y
                player.y_velocity = 0
                player.grounded = True
            else:
                player.y += step
        else: 
            player.y += step
    else:
        hit = raycast(player.position + Vec3(0, 0.5, 0), Vec3(0, -1, 0), distance=0.6, ignore=(player,))
        if not hit.hit:
            player.grounded = False

    if held_keys['space'] and player.grounded:
        player.jump()

    pulse_alpha = 0.35 + (0.15 * math.sin(time.time() * 6))
    cursor_block.color = color.rgba(1.0, 1.0, 1.0, pulse_alpha)

    hit_info = raycast(camera.world_position, camera.forward, distance=6)
    if hit_info.hit:
        hit_pos = hit_info.world_point - hit_info.normal * 0.5
        bx, by, bz = int(round(hit_pos.x)), int(round(hit_pos.y)), int(round(hit_pos.z))
        if is_in_bounds(bx, by, bz):
            cursor_block.position = (bx, by, bz)
            cursor_block.enabled = True
        else: cursor_block.enabled = False
    else: cursor_block.enabled = False

app.run()