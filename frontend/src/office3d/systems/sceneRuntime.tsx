// Ported from Claw3D retro-office systems/sceneRuntime.tsx (GameLoop + Spotlight
// only; PingPongBall/FloorRaycaster omitted as not needed for monitoring view).
import { useFrame } from "@react-three/fiber";
import { useRef, type RefObject } from "react";
import * as THREE from "three";
import { toWorld } from "../core/geometry";
import type { RenderAgent } from "../core/types";

export function GameLoop({ tick }: { tick: () => void }) {
  useFrame(() => tick());
  return null;
}

export function SpotlightEffect({
  agentId,
  agentsRef,
  agentLookupRef,
}: {
  agentId: string | null;
  agentsRef: RefObject<RenderAgent[]>;
  agentLookupRef?: RefObject<Map<string, RenderAgent>>;
}) {
  const lightRef = useRef<THREE.SpotLight>(null);
  const progressRef = useRef(0);

  useFrame((_, delta) => {
    if (!lightRef.current) return;
    if (agentId) progressRef.current = Math.min(1, progressRef.current + delta / 0.4);
    else progressRef.current = Math.max(0, progressRef.current - delta / 0.6);
    const bell = Math.sin(progressRef.current * Math.PI);
    lightRef.current.intensity = bell * 6;

    const agent =
      (agentId ? agentLookupRef?.current?.get(agentId) : undefined) ??
      agentsRef.current?.find((candidate) => candidate.id === agentId);
    if (agent) {
      const [wx, , wz] = toWorld(agent.x, agent.y);
      lightRef.current.position.set(wx, 5, wz);
      lightRef.current.target.position.set(wx, 0, wz);
      lightRef.current.target.updateMatrixWorld();
    }
  });

  return (
    <spotLight ref={lightRef} color="#ffe8a0" intensity={0} angle={0.35} penumbra={0.5} distance={12} castShadow={false} />
  );
}
