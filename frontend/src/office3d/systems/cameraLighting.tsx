// Coffee-shop fixed warm-white lighting rig (formerly the Claw3D day/night cycle).
// Per user request: lights stay constant at bright daytime — the day/night
// cycle (with its too-dark night keyframes + 300s flicker) has been removed.
// Overview camera constants stay exported for OfficeScene.
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef, type MutableRefObject, type RefObject } from "react";
import * as THREE from "three";
import {
  WORLD_H,
  WORLD_W,
  DISTRICT_CAMERA_POSITION,
  DISTRICT_CAMERA_TARGET,
  DISTRICT_CAMERA_ZOOM,
} from "../core/constants";
import { toWorld } from "../core/geometry";
import type { RenderAgent } from "../core/types";

export function SceneLighting() {
  return (
    <>
      <hemisphereLight color="#fff4e0" groundColor="#6d4c41" intensity={0.6} />
      <ambientLight intensity={1.1} color="#f4e8d0" />
      <directionalLight
        position={[8, 14, 6]}
        intensity={1.8}
        color="#fff4e0"
        castShadow
        shadow-mapSize={[1024, 1024]}
        shadow-bias={-0.0002}
        shadow-normalBias={0.02}
        shadow-camera-left={-WORLD_W * 0.7}
        shadow-camera-right={WORLD_W * 0.7}
        shadow-camera-top={WORLD_H * 0.7}
        shadow-camera-bottom={-WORLD_H * 0.7}
      />
    </>
  );
}

// Overview camera positioned to frame the whole cafe floor.
export const OVERVIEW_CAMERA = DISTRICT_CAMERA_POSITION;
export const OVERVIEW_TARGET = DISTRICT_CAMERA_TARGET;
export const OVERVIEW_ZOOM = DISTRICT_CAMERA_ZOOM;

// ── Camera presets (ported from Claw3D, retuned to the three cafe zones) ──
// Coffee keeps OrbitControls as the default free-browse camera. These presets
// and the FollowCam are *focus* enhancements layered on top, never replacing
// OrbitControls (iron rule #6).
export type CameraPreset = {
  pos: [number, number, number];
  target: [number, number, number];
  zoom?: number;
};

// Three cafe viewpoints: full overview, bar-counter close-up, lounge seating.
// World coords come from toWorld() of the cafe zone centers (bar ~x120,
// seating ~x800, lounge ~x1500 on the 1800x720 canvas).
export const CAMERA_PRESETS = {
  overview: {
    pos: DISTRICT_CAMERA_POSITION,
    target: DISTRICT_CAMERA_TARGET,
    zoom: 1,
  },
  machines: {
    pos: [-18.2, 2.45, -3.2],
    target: [-13.95, 0.8, -3.78],
    zoom: 2.1,
  },
  barCounter: {
    pos: [-17.2, 3.2, -0.9],
    target: [-13.85, 0.72, -3.75],
    zoom: 1.65,
  },
  lounge: {
    pos: [8.5, 6, -4.5],
    target: [6, 0, -2],
    zoom: 1.45,
  },
} satisfies Record<string, CameraPreset>;

type OrbitControllerLike = {
  target: THREE.Vector3;
  update: () => void;
};

// Smoothly tweens the active camera toward a preset (pos lerp 0.06, target
// lerp 0.06, zoom lerp 0.08), driving OrbitControls' target so the transition
// stays consistent with free-browse. Clears the preset once settled.
export function CameraAnimator({
  presetRef,
  orbitRef,
}: {
  presetRef: MutableRefObject<CameraPreset | null>;
  orbitRef: RefObject<OrbitControllerLike | null>;
}) {
  const { camera } = useThree();
  const targetPositionRef = useRef(new THREE.Vector3());
  const targetLookAtRef = useRef(new THREE.Vector3());

  useFrame(() => {
    const preset = presetRef.current;
    const orbit = orbitRef.current;
    if (!preset || !orbit) return;
    const perspective =
      camera instanceof THREE.PerspectiveCamera ? camera : null;

    targetPositionRef.current.set(...preset.pos);
    targetLookAtRef.current.set(...preset.target);
    camera.position.lerp(targetPositionRef.current, 0.06);
    orbit.target.lerp(targetLookAtRef.current, 0.06);

    if (perspective && typeof preset.zoom === "number") {
      perspective.zoom += (preset.zoom - perspective.zoom) * 0.08;
      perspective.updateProjectionMatrix();
    }

    orbit.update();
    const zoomSettled =
      !perspective ||
      typeof preset.zoom !== "number" ||
      Math.abs(perspective.zoom - preset.zoom) < 0.5;

    if (
      camera.position.distanceTo(targetPositionRef.current) < 0.05 &&
      zoomSettled
    ) {
      presetRef.current = null;
    }
  });

  return null;
}

// Follow-cam: when an agent is focused, swap to a chase PerspectiveCamera (65
// FOV) that orbits the agent via spherical drag + wheel zoom (radius 0.8~10).
// Restores the original camera on release. OrbitControls remains the default
// when no agent is focused.
export function FollowCamController({
  followRef,
  agentsRef,
  agentLookupRef,
}: {
  followRef: MutableRefObject<string | null>;
  agentsRef: RefObject<RenderAgent[]>;
  agentLookupRef?: RefObject<Map<string, RenderAgent>>;
}) {
  const { camera, set, size, gl } = useThree();
  const perspectiveCameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const originalCameraRef = useRef<THREE.PerspectiveCamera | null>(
    camera instanceof THREE.PerspectiveCamera ? camera : null,
  );
  const wasFollowingRef = useRef(false);
  const lastAgentIdRef = useRef<string | null>(null);
  const thetaRef = useRef(0);
  const phiRef = useRef(Math.PI / 6);
  const radiusRef = useRef(2.0);
  const isDraggingRef = useRef(false);
  const lastMouseRef = useRef({ x: 0, y: 0 });
  const cameraPositionRef = useRef(new THREE.Vector3());
  const lookAtRef = useRef(new THREE.Vector3());

  useEffect(() => {
    if (camera instanceof THREE.PerspectiveCamera) {
      originalCameraRef.current = camera;
    }
  }, [camera]);

  useEffect(() => {
    const element = gl.domElement;

    const handleMouseDown = (event: MouseEvent) => {
      if (!followRef.current || event.button !== 0) return;
      isDraggingRef.current = true;
      lastMouseRef.current = { x: event.clientX, y: event.clientY };
    };
    const handleMouseMove = (event: MouseEvent) => {
      if (!isDraggingRef.current) return;
      const dx = event.clientX - lastMouseRef.current.x;
      const dy = event.clientY - lastMouseRef.current.y;
      lastMouseRef.current = { x: event.clientX, y: event.clientY };
      thetaRef.current -= dx * 0.006;
      phiRef.current = Math.max(
        0.05,
        Math.min(Math.PI / 2.2, phiRef.current + dy * 0.006),
      );
    };
    const handleMouseUp = () => {
      isDraggingRef.current = false;
    };
    const handleWheel = (event: WheelEvent) => {
      if (!followRef.current) return;
      radiusRef.current = Math.max(
        0.8,
        Math.min(10, radiusRef.current + event.deltaY * 0.005),
      );
    };

    element.addEventListener("mousedown", handleMouseDown);
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    element.addEventListener("wheel", handleWheel, { passive: true });
    return () => {
      element.removeEventListener("mousedown", handleMouseDown);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
      element.removeEventListener("wheel", handleWheel);
    };
  }, [gl, followRef]);

  useFrame(() => {
    const agentId = followRef.current;
    const isFollowing = agentId !== null;

    if (isFollowing && !wasFollowingRef.current) {
      const agent =
        (agentId ? agentLookupRef?.current?.get(agentId) : undefined) ??
        agentsRef.current?.find((candidate) => candidate.id === agentId);
      if (!agent) return;

      if (!perspectiveCameraRef.current) {
        perspectiveCameraRef.current = new THREE.PerspectiveCamera(
          65,
          size.width / size.height,
          0.1,
          100,
        );
      }
      thetaRef.current = agent.facing + Math.PI;
      lastAgentIdRef.current = agentId;
      set({ camera: perspectiveCameraRef.current });
      wasFollowingRef.current = true;
    }

    if (!isFollowing && wasFollowingRef.current) {
      if (originalCameraRef.current) set({ camera: originalCameraRef.current });
      wasFollowingRef.current = false;
      return;
    }

    if (!isFollowing || !perspectiveCameraRef.current) return;

    const agent =
      (agentId ? agentLookupRef?.current?.get(agentId) : undefined) ??
      agentsRef.current?.find((candidate) => candidate.id === agentId);
    if (!agent) return;

    if (agentId !== lastAgentIdRef.current) {
      thetaRef.current = agent.facing + Math.PI;
      lastAgentIdRef.current = agentId;
    }

    const [wx, , wz] = toWorld(agent.x, agent.y);
    const radius = radiusRef.current;
    const theta = thetaRef.current;
    const phi = phiRef.current;

    cameraPositionRef.current.set(
      wx + radius * Math.sin(phi) * Math.sin(theta),
      0.4 + radius * Math.cos(phi),
      wz + radius * Math.sin(phi) * Math.cos(theta),
    );
    perspectiveCameraRef.current.position.copy(cameraPositionRef.current);

    lookAtRef.current.set(wx, 0.5, wz);
    perspectiveCameraRef.current.lookAt(lookAtRef.current);
    perspectiveCameraRef.current.aspect = size.width / size.height;
    perspectiveCameraRef.current.updateProjectionMatrix();
  });

  return null;
}
