// Ported from Claw3D objects/furniture.tsx. Loads the real GLB furniture models
// (copied from Claw3D public/office-assets) with Claw3D's exact per-type scale,
// tint, and rotation so the office renders faithfully instead of placeholder boxes.
import { useGLTF } from "@react-three/drei";
import { useEffect, useMemo } from "react";
import * as THREE from "three";
import { SCALE } from "../core/constants";
import {
  FURNITURE_ROTATION,
  getItemBaseSize,
  getItemRotationRadians,
  toWorld,
} from "../core/geometry";
import type { FurnitureItem } from "../core/types";

export const FURNITURE_GLB: Record<string, string> = {
  desk_cubicle: "/3d/office-assets/models/furniture/desk.glb",
  executive_desk: "/3d/office-assets/models/furniture/deskCorner.glb",
  chair: "/3d/office-assets/models/furniture/chairDesk.glb",
  round_table: "/3d/office-assets/models/furniture/tableRound.glb",
  couch: "/3d/office-assets/models/furniture/loungeSofa.glb",
  couch_v: "/3d/office-assets/models/furniture/loungeDesignChair.glb",
  bookshelf: "/3d/office-assets/models/furniture/bookcaseClosed.glb",
  plant: "/3d/office-assets/models/furniture/pottedPlant.glb",
  beanbag: "/3d/office-assets/models/furniture/loungeDesignChair.glb",
  pingpong: "/3d/office-assets/models/furniture/tableCoffee.glb",
  table_rect: "/3d/office-assets/models/furniture/table.glb",
  coffee_machine: "/3d/office-assets/models/furniture/kitchenCoffeeMachine.glb",
  fridge: "/3d/office-assets/models/furniture/kitchenFridgeSmall.glb",
  water_cooler: "/3d/office-assets/models/furniture/plantSmall1.glb",
  whiteboard: "/3d/office-assets/models/furniture/bookcaseClosed.glb",
  kanban_board: "/3d/office-assets/models/furniture/deskCorner.glb",
  cabinet: "/3d/office-assets/models/furniture/kitchenCabinet.glb",
  computer: "/3d/office-assets/models/furniture/computerScreen.glb",
  lamp: "/3d/office-assets/models/furniture/lampRoundFloor.glb",
  // Cafe extras (Poly Pizza CC0) — desktop props, see cafe-extras/README.md
  coffee_cup: "/3d/office-assets/models/cafe-extras/ppCoffeeCup.glb",
  espresso: "/3d/office-assets/models/cafe-extras/ppEspresso.glb",
};

export const FURNITURE_SCALE: Record<string, [number, number, number]> = {
  desk_cubicle: [1.5, 1.5, 1.5],
  executive_desk: [1.8, 1.8, 1.8],
  chair: [1.2, 1.2, 1.2],
  round_table: [3.2, 3.2, 3.2],
  couch: [1.8, 1.8, 1.8],
  couch_v: [1.4, 1.4, 1.4],
  bookshelf: [1.5, 2, 1.5],
  plant: [1.2, 1.8, 1.2],
  beanbag: [1, 1, 1],
  pingpong: [2.4, 1.2, 1.6],
  table_rect: [1.4, 1.2, 1.0],
  coffee_machine: [0.8, 0.8, 0.8],
  fridge: [1, 1.4, 1],
  water_cooler: [1, 2, 1],
  whiteboard: [0.6, 1.4, 0.3],
  kanban_board: [1.8, 1.8, 1.8],
  cabinet: [2.6, 1.2, 1],
  computer: [1.1, 1.1, 1.1],
  lamp: [1.2, 1.2, 1.2],
  coffee_cup: [96, 96, 96],
  espresso: [0.0019, 0.0019, 0.0019],
};

export const FURNITURE_Y_OFFSET: Record<string, number> = { computer: 0.61 };

export const FURNITURE_TINT: Record<string, string | null> = {
  desk_cubicle: "#8b5e32",
  executive_desk: "#4e342e",
  chair: "#5d4037",
  round_table: "#6b4423",
  couch: "#6d4c41",
  couch_v: "#795548",
  bookshelf: "#3e2723",
  beanbag: null,
  computer: "#363c58",
  pingpong: "#2d6048",
  table_rect: "#7a5028",
  coffee_machine: "#2d2d38",
  fridge: "#505a60",
  water_cooler: "#3a5070",
  whiteboard: "#3e2723",
  kanban_board: "#8b5e32",
  cabinet: "#5d4037",
  plant: null,
  lamp: "#c8a060",
  coffee_cup: null,
  espresso: null,
};

const SHADOW_CASTING = new Set([
  "desk_cubicle", "executive_desk", "round_table", "table_rect",
  "couch", "couch_v", "bookshelf", "cabinet", "fridge",
]);

const templateCache = new Map<string, THREE.Object3D>();

const resolveTemplate = (glbPath: string, itemType: string, itemColor: string | undefined, scene: THREE.Object3D) => {
  const cacheKey = `${glbPath}:${itemType}:${itemColor ?? ""}`;
  const cached = templateCache.get(cacheKey);
  if (cached) return cached;
  const rawTint = itemType === "beanbag" ? (itemColor ?? null) : FURNITURE_TINT[itemType];
  const tintColor = rawTint ? new THREE.Color(rawTint) : null;
  const template = scene.clone(true);
  const castShadow = SHADOW_CASTING.has(itemType);
  template.traverse((child) => {
    const mesh = child as THREE.Mesh;
    if (!mesh.isMesh) return;
    mesh.castShadow = castShadow;
    mesh.receiveShadow = true;
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    mesh.material = mats.map((material) => {
      const next = (material as THREE.MeshStandardMaterial).clone();
      if (tintColor && "color" in next) next.color.lerp(tintColor, 0.8);
      if ("roughness" in next) next.roughness = 0.65;
      if ("metalness" in next) next.metalness = 0.08;
      return next;
    });
    if (mats.length === 1) mesh.material = (mesh.material as THREE.Material[])[0];
  });
  templateCache.set(cacheKey, template);
  return template;
};

// Apply editor highlight to a cloned template's meshes: selected = warm gold
// emissive, hovered-in-edit = cool blue emissive, otherwise emissive off.
const applyHighlight = (
  cloned: THREE.Object3D,
  isSelected: boolean,
  isHovered: boolean,
  editMode: boolean,
) => {
  const highlightActive = isSelected || (isHovered && editMode);
  cloned.traverse((child) => {
    const mesh = child as THREE.Mesh;
    if (!mesh.isMesh) return;
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    const nextMats = mats.map((material) => {
      const standard = material as THREE.MeshStandardMaterial;
      if (!(standard instanceof THREE.MeshStandardMaterial)) return material;
      const next = highlightActive ? standard.clone() : standard;
      if (!("emissive" in next)) return next;
      if (isSelected) {
        next.emissive.set("#fbbf24");
        next.emissiveIntensity = 0.35;
      } else if (isHovered && editMode) {
        next.emissive.set("#4a90d9");
        next.emissiveIntensity = 0.25;
      } else {
        next.emissive.set("#000000");
        next.emissiveIntensity = 0;
      }
      return next;
    });
    mesh.material = Array.isArray(mesh.material) ? nextMats : nextMats[0];
  });
};

export type FurnitureModelProps = {
  item: FurnitureItem;
  isSelected?: boolean;
  isHovered?: boolean;
  editMode?: boolean;
  onPointerDown?: (e: THREE.Event) => void;
  onPointerOver?: (e: THREE.Event) => void;
  onPointerOut?: (e: THREE.Event) => void;
};

export function FurnitureModel({
  item,
  isSelected = false,
  isHovered = false,
  editMode = false,
  onPointerDown,
  onPointerOver,
  onPointerOut,
}: FurnitureModelProps) {
  const glbPath = FURNITURE_GLB[item.type] ?? FURNITURE_GLB.table_rect;
  const { scene } = useGLTF(glbPath);
  const template = useMemo(
    () => resolveTemplate(glbPath, item.type, item.color, scene),
    [glbPath, item.type, item.color, scene],
  );
  const cloned = useMemo(() => template.clone(true), [template]);
  const [wx, , wz] = toWorld(item.x, item.y);
  const yOffset = (FURNITURE_Y_OFFSET[item.type] ?? 0) + (item.elevation ?? 0);
  const scale = FURNITURE_SCALE[item.type] ?? [1, 1, 1];
  const rotY = getItemRotationRadians(item);
  const { width, height } = getItemBaseSize(item);
  const pivotX = width * SCALE * 0.5;
  const pivotZ = height * SCALE * 0.5;

  // Re-apply highlight whenever selection/hover/edit state changes.
  useEffect(() => {
    applyHighlight(cloned, isSelected, isHovered, editMode);
  }, [cloned, isSelected, isHovered, editMode]);

  return (
    <group
      position={[wx, yOffset, wz]}
      onPointerDown={onPointerDown}
      onPointerOver={onPointerOver}
      onPointerOut={onPointerOut}
    >
      <group position={[pivotX, 0, pivotZ]} rotation={[0, rotY, 0]}>
        <group position={[-pivotX, 0, -pivotZ]} scale={scale}>
          <primitive object={cloned} />
        </group>
      </group>
    </group>
  );
}

// Half-transparent placement preview shown while the user drags a palette item
// onto the floor (Phase 4). Reuses the item's GLB at its render scale + rotation.
export function PlacementGhost({
  itemType,
  position,
}: {
  itemType: string;
  position: [number, number, number];
}) {
  const glbPath = FURNITURE_GLB[itemType] ?? FURNITURE_GLB.table_rect;
  const { scene } = useGLTF(glbPath);
  const template = useMemo(
    () => resolveTemplate(glbPath, itemType, undefined, scene),
    [glbPath, itemType, scene],
  );
  const cloned = useMemo(() => template.clone(true), [template]);
  const scale = FURNITURE_SCALE[itemType] ?? [1, 1, 1];
  const rotY = FURNITURE_ROTATION[itemType] ?? 0;

  return (
    <group position={position} rotation={[0, rotY, 0]} scale={scale}>
      <primitive object={cloned} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 0]}>
        <planeGeometry args={[0.8, 0.8]} />
        <meshBasicMaterial color="#fbbf24" transparent opacity={0.25} />
      </mesh>
    </group>
  );
}
