// Simplified port of Claw3D retro-office scene/environment.tsx.
// Single local office floor + walls only (no remote-office district, no city path).
import { memo } from "react";
import { CANVAS_H, CANVAS_W, SCALE } from "../core/constants";
import { toWorld } from "../core/geometry";

export const FloorAndWalls = memo(function FloorAndWalls() {
  const width = CANVAS_W * SCALE;
  const height = CANVAS_H * SCALE;
  const [cx, , cz] = toWorld(CANVAS_W / 2, CANVAS_H / 2);
  const northZ = cz - height / 2;
  const southZ = cz + height / 2;
  const westX = cx - width / 2;
  const eastX = cx + width / 2;
  const wallColor = "#8d6e63";
  const wallEmissive = "#4e342e";

  return (
    <group>
      <mesh position={[cx, -0.015, cz]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[width, height, 24, 14]} />
        <meshStandardMaterial color="#263238" roughness={0.98} metalness={0.02} />
      </mesh>
      <mesh position={[cx, -0.012, cz]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[width * 0.95, height * 0.9]} />
        <meshStandardMaterial color="#1b232a" roughness={0.96} metalness={0.04} />
      </mesh>
      <mesh position={[cx, 0, cz]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[width, height, 22, 14]} />
        <meshLambertMaterial color="#c8a97e" />
      </mesh>
      {Array.from({ length: 18 }).map((_, index) => {
        const z = northZ + (index + 1) * (height / 18);
        return (
          <mesh key={`floor-line-${index}`} position={[cx, 0.001, z]} rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[width, 0.008]} />
            <meshBasicMaterial color="#a07850" transparent opacity={0.25} />
          </mesh>
        );
      })}
      <mesh position={[cx, 0.5, northZ]} receiveShadow>
        <boxGeometry args={[width, 1, 0.12]} />
        <meshStandardMaterial color={wallColor} emissive={wallEmissive} emissiveIntensity={0.4} roughness={0.9} />
      </mesh>
      <mesh position={[cx, 0.5, southZ]} receiveShadow>
        <boxGeometry args={[width, 1, 0.12]} />
        <meshStandardMaterial color={wallColor} emissive={wallEmissive} emissiveIntensity={0.4} roughness={0.9} />
      </mesh>
      <mesh position={[westX, 0.5, cz]} receiveShadow>
        <boxGeometry args={[0.12, 1, height]} />
        <meshStandardMaterial color={wallColor} emissive={wallEmissive} emissiveIntensity={0.4} roughness={0.9} />
      </mesh>
      <mesh position={[eastX, 0.5, cz]} receiveShadow>
        <boxGeometry args={[0.12, 1, height]} />
        <meshStandardMaterial color={wallColor} emissive={wallEmissive} emissiveIntensity={0.4} roughness={0.9} />
      </mesh>
    </group>
  );
});
