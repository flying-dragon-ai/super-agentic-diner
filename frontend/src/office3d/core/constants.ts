// Ported from Claw3D retro-office core/constants.ts. Canvas->world coordinate
// system: canvas pixel coords are projected into three.js world units via SCALE.
export const DESK_STICKY_MS = 10_000;
export const SNAP_GRID = 10;
// localStorage keys for the editor layout persistence + smooth layout migration.
export const STORAGE_KEY = "coffee-office-furniture-v2";
export const STORAGE_META_KEY = "coffee-office-furniture-meta-v2";
export const LAYOUT_MIGRATION_KEY = "coffee-office-layout-migration-v2";
export const ROTATION_STEP_DEG = 15;
export const WALL_THICKNESS = 8;
export const DOOR_THICKNESS = 8;
export const DOOR_LENGTH = 40;
export const MIN_WALL_LENGTH = SNAP_GRID * 2;
export const ELEVATION_STEP = 0.08;
export const WALK_SPEED = 0.3;
export const WORKING_WALK_SPEED_MULTIPLIER = 3;
export const WALK_ANIM_SPEED = 0.15;
export const AGENT_SCALE = 1.75;
// Collision tuning (3D-interaction-enhancement plan step 2): larger radius so
// agents start peeling apart earlier, stronger separation weight when picking
// the escape roam point, and shorter freeze/recovery windows so bumped agents
// resume motion quickly instead of looking "frozen".
export const BUMP_FREEZE_MS = 800;
export const BUMP_RECOVERY_MS = 600;
export const AGENT_RADIUS = 26;
export const SEPARATION_STRENGTH = 6;
// Single local office canvas (no remote-office district in this port).
export const CANVAS_W = 1800;
// Claw3D local office is 1800 wide x 720 tall; world projected via SCALE.
export const CANVAS_H = 720;
export const SCALE = 0.018;
export const WORLD_W = CANVAS_W * SCALE;
export const WORLD_H = CANVAS_H * SCALE;

// Claw3D district overview camera (3/4 perspective, not top-down).
export const DISTRICT_CAMERA_POSITION: [number, number, number] = [14, 16, 18];
export const DISTRICT_CAMERA_TARGET: [number, number, number] = [0, 0, 1];
export const DISTRICT_CAMERA_ZOOM = 34;
