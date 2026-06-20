// Ported from Claw3D objects/furniture.tsx. Loads the real GLB furniture models
// (copied from Claw3D public/office-assets) with Claw3D's exact per-type scale,
// tint, and rotation so the office renders faithfully instead of placeholder boxes.
import { useGLTF } from "@react-three/drei";
import { useMemo } from "react";
import * as THREE from "three";
import { SCALE } from "../core/constants";
import {
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
};

export const FURNITURE_Y_OFFSET: Record<string, number> = { computer: 0.61 };

export const FURNITURE_TINT: Record<string, string | null> = {
  desk_cubicle: "#8b5e32",
  executive_desk: "#6b3c1a",
  chair: "#4a5568",
  round_table: "#9a6332",
  couch: "#3d5575",
  couch_v: "#5a4870",
  bookshelf: "#5c3520",
  beanbag: null,
  computer: "#363c58",
  pingpong: "#2d6048",
  table_rect: "#7a5028",
  coffee_machine: "#2d2d38",
  fridge: "#505a60",
  water_cooler: "#3a5070",
  whiteboard: "#f4f2ee",
  kanban_board: "#8b5e32",
  cabinet: "#3c4248",
  plant: null,
  lamp: "#c8a060",
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

export function FurnitureModel({ item }: { item: FurnitureItem }) {
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

  return (
    <group position={[wx, yOffset, wz]}>
      <group position={[pivotX, 0, pivotZ]} rotation={[0, rotY, 0]}>
        <group position={[-pivotX, 0, -pivotZ]} scale={scale}>
          <primitive object={cloned} />
        </group>
      </group>
    </group>
  );
}
