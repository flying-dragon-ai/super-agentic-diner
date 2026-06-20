// Ported from Claw3D retro-office objects/types.ts.
import type { AgentAvatarProfile } from "../avatars/profile";
import type { RefObject } from "react";
import type { FurnitureItem, OfficeAgent, RenderAgent } from "../core/types";

export type BasicFurnitureModelProps = {
  item: FurnitureItem;
  onPointerDown?: (uid: string) => void;
  onPointerOver?: (uid: string) => void;
  onPointerOut?: () => void;
  editMode?: boolean;
};

export type AgentModelProps = {
  agentId: string;
  name: string;
  subtitle?: string | null;
  status: OfficeAgent["status"];
  color: string;
  appearance?: AgentAvatarProfile | null;
  agentsRef: RefObject<RenderAgent[]>;
  agentLookupRef?: RefObject<Map<string, RenderAgent>>;
  onHover?: (id: string) => void;
  onUnhover?: () => void;
  onClick?: (id: string) => void;
  showSpeech?: boolean;
  speechText?: string | null;
  suppressSpeechBubble?: boolean;
};
