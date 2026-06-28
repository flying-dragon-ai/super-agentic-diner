import { Server } from '@colyseus/core';
import { WebSocketTransport } from '@colyseus/ws-transport';
import http from 'http';
import { CoffeeRoom } from './rooms/CoffeeRoom.js';

const port = Number(process.env.COLYSEUS_PORT ?? 2567);

const gameServer = new Server({
  transport: new WebSocketTransport({
    server: http.createServer(),
  }),
});
gameServer.define('coffee_room', CoffeeRoom);

gameServer.listen(port);
console.log(`[Colyseus] coffee_room listening on :${port}`);
