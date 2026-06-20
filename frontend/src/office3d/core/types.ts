// Simplified port of Claw3D retro-office core/types.ts.
// Removes janitor/gym/qa/pingpong Claw3D-specific actor fields and the
// lib/office/places dependency. Keeps what the renderer + sim need.
import type { AgentAvatarProfile } from "../avatars/profile";

export type OfficeAgent = {
  id: string;
  name: string;
  subtitle?: string | null;
  status: "working" | "idle" | "error";
  color: string;
  item: string;
  role?: string;
  avatarProfile?: AgentAvatarProfile | null;
};

export type RenderAgent = OfficeAgent & {
  x: number;
  y: number;
  targetX: number;
  targetY: number;
  path: { x: number; y: number }[];
  facing: number;
  frame: number;
  walkSpeed: number;
  phaseOffset: number;
  state: "walking" | "sitting" | "standing" | "away" | "working_out" | "dancing";
  awayUntil?: number;
  separationReplanAt?: number;
  bumpedUntil?: number;
  bumpTalkUntil?: number;
  collisionCooldownUntil?: number;
};

export type FurnitureItem = {
  _uid: string;
  type: string;
  x: number;
  y: number;
  w?: number;
  h?: number;
  r?: number;
  color?: string;
  id?: string;
  facing?: number;
  vertical?: boolean;
  elevation?: number;
};

export type FurnitureSeed = Omit<FurnitureItem, "_uid">;
export type CanvasPoint = { x: number; y: number };
export type FacingPoint = CanvasPoint & { facing: number };
