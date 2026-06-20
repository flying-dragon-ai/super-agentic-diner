// Ported from Claw3D retro-office systems/sceneRuntime.tsx (GameLoop + Spotlight
// + FloorRaycaster). PingPongBall is omitted (not needed for monitoring view).
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, type RefObject } from "react";
import * as THREE from "three";
import { toWorld } from "../core/geometry";
import type { RenderAgent } from "../core/types";

export function GameLoop({ tick }: { tick: () => void }) {
  useFrame(() => tick());
  return null;
}

// Projects pointer rays onto the ground plane (y=0) and reports world x/z via
// onMove/onClick callbacks. Phase 4's furniture editor uses it for drag/place.
export function FloorRaycaster({
  enabled,
  onMove,
  onClick,
}: {
  enabled: boolean;
  onMove: (wx: number, wz: number) => void;
  onClick: (wx: number, wz: number) => void;
}) {
  const { camera, raycaster, gl } = useThree();
  const floorPlane = useMemo(
    () => new THREE.Plane(new THREE.Vector3(0, 1, 0), 0),
    [],
  );

  useEffect(() => {
    if (!enabled) return;
    const target = new THREE.Vector3();
    const ndc = new THREE.Vector2();

    const project = (
      clientX: number,
      clientY: number,
    ): { x: number; z: number } | null => {
      const rect = gl.domElement.getBoundingClientRect();
      ndc.set(
        ((clientX - rect.left) / rect.width) * 2 - 1,
        -((clientY - rect.top) / rect.height) * 2 + 1,
      );
      raycaster.setFromCamera(ndc, camera);
      if (raycaster.ray.intersectPlane(floorPlane, target)) {
        return { x: target.x, z: target.z };
      }
      return null;
    };

    const handleMove = (event: PointerEvent) => {
      const point = project(event.clientX, event.clientY);
      if (point) onMove(point.x, point.z);
    };
    const handleClick = (event: MouseEvent) => {
      const point = project(event.clientX, event.clientY);
      if (point) onClick(point.x, point.z);
    };

    gl.domElement.addEventListener("pointermove", handleMove);
    gl.domElement.addEventListener("click", handleClick);
    return () => {
      gl.domElement.removeEventListener("pointermove", handleMove);
      gl.domElement.removeEventListener("click", handleClick);
    };
  }, [enabled, camera, raycaster, gl, floorPlane, onMove, onClick]);

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
