import { Schema, type, MapSchema, ArraySchema } from '@colyseus/schema';

/**
 * 在线玩家。sessionId 由 Colyseus 客户端连接分配，
 * role 约束见 app/domain_constants.py（此服务端只做镜像同步，不引入新枚举）。
 */
export class Player extends Schema {
  @type('string')
  sessionId = '';

  @type('string')
  name = '';

  @type('string')
  role = 'customer';

  @type('number')
  x = 0;

  @type('number')
  y = 0;

  @type('string')
  anim = 'customer_a_idle_down';

  @type('string')
  seatId = '';
}

/**
 * 服务端权威 NPC（店长咖啡师等）。
 * 位置/动画由 simulate() 推进，客户端只读。
 */
export class NPC extends Schema {
  @type('string')
  id = '';

  @type('string')
  role = 'barista';

  @type('number')
  x = 0;

  @type('number')
  y = 0;

  @type('string')
  anim = 'barista_idle_down';

  @type('string')
  currentTask = 'idle';
}

/**
 * 单杯订单的状态镜像。订单真源在 MySQL `order` 表，
 * 这里只保留多端同步所需的最小字段。
 */
export class Order extends Schema {
  @type('string')
  orderId = '';

  @type('string')
  item = '';

  @type('string')
  status = 'pending';

  @type('string')
  customerId = '';

  @type('string')
  baristaId = '';

  @type('string')
  station = '';
}

/** 座位占用状态。occupiedBy 为空字符串表示空闲。 */
export class Seat extends Schema {
  @type('string')
  seatId = '';

  @type('string')
  occupiedBy = '';
}

/** 房间权威状态根。所有同步字段必须走 @type 装饰器。 */
export class CoffeeState extends Schema {
  @type({ map: Player })
  players = new MapSchema<Player>();

  @type({ map: NPC })
  npcs = new MapSchema<NPC>();

  @type([Order])
  orders = new ArraySchema<Order>();

  @type({ map: Seat })
  seats = new MapSchema<Seat>();
}