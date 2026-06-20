import { Room, Client } from '@colyseus/core';
import { CoffeeState, Player, NPC } from '../schema/CoffeeState.js';

const WORLD_WIDTH = 1280;
const WORLD_HEIGHT = 960;
const NAME_MAX_LEN = 20;
const ANIM_MAX_LEN = 60;

interface MoveMessage {
  x?: unknown;
  y?: unknown;
  anim?: unknown;
}

interface InteractMessage {
  action?: unknown;
  seatId?: unknown;
}

/**
 * 像素咖啡馆房间。权威状态由服务端推进，
 * 客户端通过 move / interact 消息请求变更。
 */
export class CoffeeRoom extends Room<CoffeeState> {
  maxClients = 50;

  onCreate(): void {
    this.setState(new CoffeeState());
    this.registerHandlers();
    this.initDefaultNPCs();
    this.setPatchRate(50);
    this.setSimulationInterval((dt) => this.simulate(dt), 1000 / 60);
  }

  onJoin(client: Client, options?: Record<string, unknown>): void {
    const p = new Player();
    p.sessionId = client.sessionId;
    p.name = String(options?.name ?? '游客').slice(0, NAME_MAX_LEN);
    p.role = String(options?.role ?? 'customer');
    p.x = 320;
    p.y = 520;
    this.state.players.set(client.sessionId, p);
  }

  onLeave(client: Client): void {
    this.state.players.delete(client.sessionId);
    // 释放该玩家占用的座位
    for (const s of this.state.seats.values()) {
      if (s.occupiedBy === client.sessionId) {
        s.occupiedBy = '';
      }
    }
  }

  private registerHandlers(): void {
    // MOVE: 限频 + 基础边界校验
    this.onMessage('move', (client: Client, msg: MoveMessage) => {
      const p = this.state.players.get(client.sessionId);
      if (!p) return;
      const nx = Number(msg?.x);
      const ny = Number(msg?.y);
      if (!Number.isFinite(nx) || !Number.isFinite(ny)) return;
      if (nx < 0 || nx > WORLD_WIDTH || ny < 0 || ny > WORLD_HEIGHT) return;
      // TODO: tile 可行走校验接入后补
      p.x = nx;
      p.y = ny;
      if (typeof msg?.anim === 'string') {
        p.anim = String(msg.anim).slice(0, ANIM_MAX_LEN);
      }
    });

    // PLACE_ORDER: 先留 stub，后续接入 web/skill 业务桥
    this.onMessage('place_order', (_client: Client, _msg: unknown) => {
      /* TODO 接业务桥 */
    });

    // INTERACT: 入座 / 起身
    this.onMessage('interact', (client: Client, msg: InteractMessage) => {
      const action = String(msg?.action);
      if (action === 'sit') {
        const seatId = String(msg?.seatId ?? '');
        const seat = this.state.seats.get(seatId);
        const p = this.state.players.get(client.sessionId);
        if (seat && p && seat.occupiedBy === '') {
          seat.occupiedBy = client.sessionId;
          p.seatId = seatId;
        }
      } else if (action === 'stand') {
        const p = this.state.players.get(client.sessionId);
        if (p && p.seatId) {
          const seat = this.state.seats.get(p.seatId);
          if (seat) seat.occupiedBy = '';
          p.seatId = '';
        }
      }
    });
  }

  private initDefaultNPCs(): void {
    const barista = new NPC();
    barista.id = 'boss_barista';
    barista.role = 'barista';
    barista.x = 640;
    barista.y = 300;
    barista.currentTask = 'idle';
    this.state.npcs.set(barista.id, barista);
  }

  private simulate(_dt: number): void {
    /* 留给后续 NPC 任务机 */
  }
}